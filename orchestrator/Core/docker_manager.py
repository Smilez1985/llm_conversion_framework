#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Docker Manager
DIREKTIVE: Goldstandard, robust, thread-safe.

This manager acts as the bridge between the GUI/CLI and the core BuildEngine.
It handles thread management, signal emission, and configuration mapping.

Updates v2.0.0:
- Integrated Self-Healing Hook: Triggers diagnosis on build failure.
- Emits 'healing_requested' signal with AI-generated fix proposals.
Updates v2.3.0:
- Use centralized ConfigManager for Docker images (No Hardcoding).
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

# v2.0 Self-Healing Integration
try:
    from orchestrator.Core.self_healing_manager import SelfHealingManager
except ImportError:
    SelfHealingManager = None

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
    build_stats = Signal(str, float, float, float)
    sidecar_status = Signal(str, str)
    
    # NEW v2.0: Signal when AI finds a fix for an error
    healing_requested = Signal(object) # Payload: HealingProposal
    
    def __init__(self, config_manager=None): # Update: Accept config in init
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.framework = None
        self.builder = None
        self.healing_manager = None # v2.0
        self._monitor_active = False
        self.config_manager = config_manager # Store ref

    def initialize(self, framework_manager):
        """
        Initializes the manager with the framework context.
        """
        self.framework = framework_manager
        # Lazy import to avoid circular dependency
        from orchestrator.Core.builder import BuildEngine
        self.builder = BuildEngine(framework_manager)
        
        # Initialize Self-Healing (v2.0)
        if SelfHealingManager:
            try:
                self.healing_manager = SelfHealingManager(framework_manager)
                self.logger.info("Self-Healing Manager attached to Docker Manager.")
            except Exception as e:
                self.logger.warning(f"Failed to init Self-Healing: {e}")
                
        self.logger.info("DockerManager initialized and connected to BuildEngine")

    def ensure_qdrant_service(self) -> Optional[str]:
        """DYNAMIC SIDECAR LOGIC: Checks if Qdrant is required and running."""
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
        
        # FIX V2.3: Load Image from Config
        image_tag = "qdrant/qdrant:v1.16.0" # Fallback
        if hasattr(self.framework.config, 'image_qdrant'):
            image_tag = self.framework.config.image_qdrant

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
        """Starts a build process based on GUI input dictionary."""
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
            
            raw_fmt = gui_config.get("format", "GGUF")
            try: target_format = ModelFormat[raw_fmt.upper()]
            except: target_format = ModelFormat.GGUF
            
            # FIX V2.3: Load Base Image from Config
            base_img = "debian:bookworm-slim"
            if hasattr(self.framework.config, 'image_base_debian'):
                base_img = self.framework.config.image_base_debian

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
                base_image=base_img, # Use Config
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
        try:
            cpu_stats = stats['cpu_stats']
            precpu_stats = stats['precpu_stats']
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - precpu_stats['cpu_usage']['total_usage']
            system_delta = cpu_stats['system_cpu_usage'] - precpu_stats['system_cpu_usage']
            
            if system_delta > 0.0 and cpu_delta > 0.0:
                online_cpus = cpu_stats.get('online_cpus', len(cpu_stats['cpu_usage'].get('percpu_usage', []))) or 1
                cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0
                return round(cpu_percent, 2)
            return 0.0
        except KeyError:
            return 0.0

    def _monitor_build(self, build_id: str):
        """Polls logs, progress, stats AND checks for failures (Healing)."""
        last_log_idx = 0
        
        while self._monitor_active:
            status = self.builder.get_build_status(build_id)
            if not status: break
            
            # 1. Logs & Progress
            current_logs = status.logs
            while last_log_idx < len(current_logs):
                self.build_output.emit(build_id, current_logs[last_log_idx])
                last_log_idx += 1
            self.build_progress.emit(build_id, status.progress_percent)
            
            # 2. Resource Monitoring
            try:
                container = self.builder._active_containers.get(build_id)
                if container:
                    stats = container.stats(stream=False)
                    cpu_pct = self._calculate_cpu_percent(stats)
                    mem_usage = stats['memory_stats'].get('usage', 0) / (1024 * 1024)
                    mem_limit = stats['memory_stats'].get('limit', 0) / (1024 * 1024)
                    self.build_stats.emit(build_id, cpu_pct, mem_usage, mem_limit)
            except Exception: pass
            
            # 3. Check Termination & HEALING
            if status.status in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]:
                success = (status.status == BuildStatus.COMPLETED)
                
                # --- v2.0 SELF HEALING TRIGGER ---
                if status.status == BuildStatus.FAILED and self.healing_manager:
                    self.logger.info(f"Build {build_id} failed. Attempting Self-Healing diagnosis...")
                    
                    # Extract Error Context from Logs (Last 50 lines)
                    error_context = "\n".join(status.logs[-50:])
                    
                    # Analyze
                    proposal = self.healing_manager.analyze_error(
                        error_context, 
                        f"Build Failure for ID: {build_id}"
                    )
                    
                    if proposal:
                        self.logger.info(f"Healing Proposal found: {proposal.error_summary}")
                        # Notify GUI to show Healing Dialog
                        self.healing_requested.emit(proposal)
                    else:
                        self.logger.warning("Self-Healing: No fix found.")

                output_path = status.artifacts[0] if status.artifacts else "Check Output Directory"
                self.build_completed.emit(build_id, success, output_path)
                self._monitor_active = False
                break
            
            time.sleep(1.0)

    def stop_build(self, build_id: str):
        if self.builder: self.builder.cancel_build(build_id)
