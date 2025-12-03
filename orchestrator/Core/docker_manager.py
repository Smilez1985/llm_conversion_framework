#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Docker Manager
DIREKTIVE: Goldstandard, robust, thread-safe.

This manager acts as the bridge between the GUI/CLI and the core BuildEngine.
It handles thread management, signal emission, and configuration mapping.

Updates v1.7.0:
- Added Native Resource Monitoring (CPU/RAM) via 'build_stats' signal.
- Implemented robust CPU percentage calculation algorithm.
"""

import os
import subprocess
import json
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional, Any
from pathlib import Path

import docker
from docker.errors import NotFound, APIError

from PySide6.QtCore import QObject, Signal

# Import Builder types
from orchestrator.Core.builder import BuildConfiguration, ModelFormat, OptimizationLevel, BuildStatus

class DockerManager(QObject):
    """
    Manages Docker lifecycle and build process via BuildEngine.
    Bridge between GUI and Core Logic.
    """
    # Signals for GUI updates
    build_started = Signal(str)
    build_progress = Signal(str, int)
    build_completed = Signal(str, bool, str)
    build_output = Signal(str, str)
    # NEW: Resource Telemetry Signal (CPU %, RAM MB, RAM Limit MB)
    build_stats = Signal(str, float, float, float)
    
    sidecar_status = Signal(str, str)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.framework = None
        self.builder = None
        self._monitor_active = False

    def initialize(self, framework_manager):
        self.framework = framework_manager
        from orchestrator.Core.builder import BuildEngine
        self.builder = BuildEngine(framework_manager)
        self.logger.info("DockerManager initialized and connected to BuildEngine")

    def ensure_qdrant_service(self) -> Optional[str]:
        """DYNAMIC SIDECAR LOGIC (v1.5.0): Checks if Qdrant is required and running."""
        rag_enabled = False
        if hasattr(self.framework.config, 'enable_rag_knowledge'):
             rag_enabled = self.framework.config.enable_rag_knowledge
        else:
             rag_enabled = self.framework.config_manager.get("enable_rag_knowledge", False)

        if not rag_enabled:
            return None

        self.sidecar_status.emit("Qdrant", "Starting...")
        client = self.builder.docker_client
        container_name = "llm-qdrant"
        image_tag = "qdrant/qdrant:v1.16.0"

        try:
            container = client.containers.get(container_name)
            if container.status != "running":
                container.start()
            self.sidecar_status.emit("Qdrant", "Running")
            return f"http://{container_name}:6333"
        except NotFound:
            try:
                try: client.images.get(image_tag)
                except NotFound: client.images.pull(image_tag)

                client.containers.run(
                    image_tag, name=container_name, ports={'6333/tcp': 6333},
                    volumes={'llm_qdrant_data': {'bind': '/qdrant/storage', 'mode': 'rw'}},
                    network="llm-framework", detach=True, restart_policy={"Name": "on-failure"}
                )
                self.sidecar_status.emit("Qdrant", "Running")
                return f"http://{container_name}:6333"
            except Exception as e:
                self.logger.error(f"Failed to start Qdrant: {e}")
                self.sidecar_status.emit("Qdrant", "Error")
                return None
        except Exception: return None

    def start_build(self, gui_config: Dict[str, Any]):
        if not self.builder:
            self.build_completed.emit("error", False, "Builder not initialized")
            return

        try:
            self.logger.info(f"Preparing build for {gui_config.get('model_name')}")

            model_path = gui_config.get("model_name", "")
            if os.path.exists(model_path): model_path = str(Path(model_path).resolve())
            
            dataset_path = gui_config.get("dataset_path")
            if dataset_path and os.path.exists(dataset_path): dataset_path = str(Path(dataset_path).resolve())

            target = gui_config.get("target", "generic")
            build_id = f"build_{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            out_dir = Path(self.framework.config.output_dir) / build_id
            
            # Map Format
            raw_fmt = gui_config.get("format", "GGUF")
            try: target_format = ModelFormat[raw_fmt.upper()]
            except: target_format = ModelFormat.GGUF

            config = BuildConfiguration(
                build_id=build_id,
                timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
                model_source=model_path,
                target_arch=target,
                target_format=target_format,
                source_format=ModelFormat.HUGGINGFACE,
                output_dir=str(out_dir),
                quantization=gui_config.get("quantization", "Q4_K_M"),
                model_task=gui_config.get("task", "LLM"),
                use_gpu=gui_config.get("use_gpu", False),
                dataset_path=dataset_path,
                base_image="debian:bookworm-slim",
                build_timeout=self.framework.config.build_timeout,
                parallel_jobs=self.framework.config.max_concurrent_builds
            )
            
            returned_id = self.builder.build_model(config)
            self.build_started.emit(returned_id)
            
            self._monitor_active = True
            monitor_thread = threading.Thread(target=self._monitor_build, args=(returned_id,), daemon=True)
            monitor_thread.start()
            
        except Exception as e:
            self.logger.error(f"Start build failed: {e}")
            self.build_completed.emit("error", False, str(e))

    def _calculate_cpu_percent(self, stats):
        """
        Calculates CPU usage percentage from Docker stats object.
        Logic adapted from Docker CLI implementation.
        """
        try:
            cpu_stats = stats['cpu_stats']
            precpu_stats = stats['precpu_stats']
            
            # Get CPU usage deltas
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - precpu_stats['cpu_usage']['total_usage']
            system_delta = cpu_stats['system_cpu_usage'] - precpu_stats['system_cpu_usage']
            
            if system_delta > 0.0 and cpu_delta > 0.0:
                # Number of CPUs (Online CPUs)
                # Some environments (WSL2) might miss online_cpus, fallback to length of percpu_usage
                online_cpus = cpu_stats.get('online_cpus', len(cpu_stats['cpu_usage'].get('percpu_usage', []))) or 1
                
                cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0
                return round(cpu_percent, 2)
            return 0.0
        except KeyError:
            return 0.0

    def _monitor_build(self, build_id: str):
        """
        Polls logs, progress AND resource stats.
        """
        last_log_idx = 0
        client = self.builder.docker_client
        
        while self._monitor_active:
            status = self.builder.get_build_status(build_id)
            if not status: break
            
            # 1. Logs & Progress
            current_logs = status.logs
            while last_log_idx < len(current_logs):
                self.build_output.emit(build_id, current_logs[last_log_idx])
                last_log_idx += 1
            self.build_progress.emit(build_id, status.progress_percent)
            
            # 2. Resource Monitoring (NEW v1.7.0)
            # Only if container is running
            try:
                # Use cached container ref from Builder or fetch fresh
                container = self.builder._active_containers.get(build_id)
                if container:
                    # Fetch snapshot (stream=False)
                    stats = container.stats(stream=False)
                    
                    # CPU
                    cpu_pct = self._calculate_cpu_percent(stats)
                    
                    # RAM
                    mem_usage = stats['memory_stats'].get('usage', 0) / (1024 * 1024) # MB
                    mem_limit = stats['memory_stats'].get('limit', 0) / (1024 * 1024) # MB
                    
                    self.build_stats.emit(build_id, cpu_pct, mem_usage, mem_limit)
                    
            except Exception:
                pass # Stats fetching is non-critical, don't crash build monitoring
            
            # 3. Check Termination
            if status.status in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]:
                success = (status.status == BuildStatus.COMPLETED)
                output_path = status.artifacts[0] if status.artifacts else "Check Output Directory"
                self.build_completed.emit(build_id, success, output_path)
                self._monitor_active = False
                break
            
            time.sleep(1.0) # 1Hz update rate for stats is sufficient

    def stop_build(self, build_id: str):
        if self.builder: self.builder.cancel_build(build_id)
