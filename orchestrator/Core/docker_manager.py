#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Docker Manager
DIREKTIVE: Goldstandard, robust, thread-safe.

This manager acts as the bridge between the GUI/CLI and the core BuildEngine.
It handles thread management, signal emission, and configuration mapping.
"""

import os
import subprocess#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Docker Manager
DIREKTIVE: Goldstandard, robust, thread-safe.

This manager acts as the bridge between the GUI/CLI and the core BuildEngine.
It handles thread management, signal emission, and configuration mapping.
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

from PySide6.QtCore import QObject, Signal

# Import Builder types for configuration mapping
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
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.framework = None
        self.builder = None
        self._monitor_active = False

    def initialize(self, framework_manager):
        """
        Initializes the manager with the framework context.
        """
        self.framework = framework_manager
        # Lazy import to avoid circular dependency if needed, or use framework's builder instance
        from orchestrator.Core.builder import BuildEngine
        self.builder = BuildEngine(framework_manager)
        self.logger.info("DockerManager initialized and connected to BuildEngine")

    def start_build(self, gui_config: Dict[str, Any]):
        """
        Starts a build process based on GUI input dictionary.
        Maps the flat GUI config to the structured BuildConfiguration.
        """
        if not self.builder:
            self.logger.error("Builder not initialized. Call initialize() first.")
            self.build_completed.emit("error", False, "Builder not initialized")
            return

        try:
            self.logger.info(f"Preparing build for {gui_config.get('model_name')}")

            # 1. Extract & Normalize Parameters
            model_path = gui_config.get("model_name", "")
            target = gui_config.get("target", "generic")
            task = gui_config.get("task", "LLM")
            quant = gui_config.get("quantization", "Q4_K_M")
            use_gpu = gui_config.get("use_gpu", False)
            dataset_path = gui_config.get("dataset_path") # Optional: Calibration dataset
            
            # Output Directory Generation
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            build_id = f"build_{target}_{timestamp}"
            output_base = Path(self.framework.config.output_dir)
            out_dir = output_base / build_id
            
            # Ensure absolute path for model if it's local
            if os.path.exists(model_path):
                model_path = str(Path(model_path).resolve())
            
            # Ensure absolute path for dataset if exists
            if dataset_path and os.path.exists(dataset_path):
                dataset_path = str(Path(dataset_path).resolve())

            # 2. Create Configuration Object
            config = BuildConfiguration(
                build_id=build_id,
                timestamp=timestamp,
                model_source=model_path,
                target_arch=target,          # Folder name in targets/
                target_format=ModelFormat.GGUF, # Default, will be handled by build.sh logic
                source_format=ModelFormat.HUGGINGFACE,
                output_dir=str(out_dir),
                quantization=quant,
                model_task=task,             # 'LLM', 'VOICE', 'VLM'
                use_gpu=use_gpu,             # NVIDIA Passthrough
                dataset_path=dataset_path,   # Calibration data for INT8
                
                # Defaults from Framework Config or Standard
                base_image="debian:bookworm-slim", # Will be overridden by Target's Dockerfile
                build_timeout=self.framework.config.build_timeout,
                parallel_jobs=self.framework.config.max_concurrent_builds
            )
            
            # 3. Submit to Engine
            # The builder uses a ThreadPool, so this returns quickly
            returned_id = self.builder.build_model(config)
            
            self.logger.info(f"Build submitted with ID: {returned_id}")
            self.build_started.emit(returned_id)
            
            # 4. Start Monitoring Thread
            # We need a separate thread to poll the builder status and emit Qt signals
            # because the Builder is framework-agnostic and doesn't know Qt.
            self._monitor_active = True
            monitor_thread = threading.Thread(
                target=self._monitor_build, 
                args=(returned_id,), 
                daemon=True,
                name=f"Monitor-{returned_id}"
            )
            monitor_thread.start()
            
        except Exception as e:
            self.logger.error(f"Failed to start build: {e}", exc_info=True)
            self.build_completed.emit("error", False, str(e))

    def _monitor_build(self, build_id: str):
        """
        Polls the build status and relays logs/progress to the GUI via Signals.
        Runs in a separate thread.
        """
        last_log_idx = 0
        
        while self._monitor_active:
            status = self.builder.get_build_status(build_id)
            
            if not status:
                self.logger.warning(f"Build status for {build_id} lost.")
                break
            
            # 1. Process New Logs
            current_logs = status.logs
            while last_log_idx < len(current_logs):
                msg = current_logs[last_log_idx]
                self.build_output.emit(build_id, msg)
                last_log_idx += 1
            
            # 2. Update Progress
            self.build_progress.emit(build_id, status.progress_percent)
            
            # 3. Check Termination
            if status.status in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]:
                success = (status.status == BuildStatus.COMPLETED)
                
                # Determine primary artifact path
                output_path = ""
                if status.artifacts:
                    output_path = status.artifacts[0]
                elif success:
                    # Fallback to output dir if artifacts list is empty but build succeeded
                    output_path = "Check Output Directory"

                self.logger.info(f"Build {build_id} finished. Success: {success}")
                self.build_completed.emit(build_id, success, output_path)
                self._monitor_active = False
                break
            
            time.sleep(0.5)

    def stop_build(self, build_id: str):
        """Cancels a running build."""
        if self.builder:
            self.builder.cancel_build(build_id)
import json
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional, Any
from pathlib import Path

from PySide6.QtCore import QObject, Signal

# Import Builder types for configuration mapping
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
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.framework = None
        self.builder = None
        self._monitor_active = False

    def initialize(self, framework_manager):
        """
        Initializes the manager with the framework context.
        """
        self.framework = framework_manager
        # Lazy import to avoid circular dependency if needed, or use framework's builder instance
        from orchestrator.Core.builder import BuildEngine
        self.builder = BuildEngine(framework_manager)
        self.logger.info("DockerManager initialized and connected to BuildEngine")

    def start_build(self, gui_config: Dict[str, Any]):
        """
        Starts a build process based on GUI input dictionary.
        Maps the flat GUI config to the structured BuildConfiguration.
        """
        if not self.builder:
            self.logger.error("Builder not initialized. Call initialize() first.")
            self.build_completed.emit("error", False, "Builder not initialized")
            return

        try:
            self.logger.info(f"Preparing build for {gui_config.get('model_name')}")

            # 1. Extract & Normalize Parameters
            model_path = gui_config.get("model_name", "")
            target = gui_config.get("target", "generic")
            task = gui_config.get("task", "LLM")
            quant = gui_config.get("quantization", "Q4_K_M")
            use_gpu = gui_config.get("use_gpu", False)
            dataset_path = gui_config.get("dataset_path") # Optional
            
            # Output Directory Generation
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            build_id = f"build_{target}_{timestamp}"
            output_base = Path(self.framework.config.output_dir)
            out_dir = output_base / build_id
            
            # Ensure absolute path for model if it's local
            if os.path.exists(model_path):
                model_path = str(Path(model_path).resolve())

            # 2. Create Configuration Object
            config = BuildConfiguration(
                build_id=build_id,
                timestamp=timestamp,
                model_source=model_path,
                target_arch=target,          # Folder name in targets/
                target_format=ModelFormat.GGUF, # Default, will be handled by build.sh logic
                source_format=ModelFormat.HUGGINGFACE,
                output_dir=str(out_dir),
                quantization=quant,
                model_task=task,             # 'LLM', 'VOICE', 'VLM'
                use_gpu=use_gpu,             # NVIDIA Passthrough
                dataset_path=dataset_path,   # Calibration data
                
                # Defaults from Framework Config or Standard
                base_image="debian:bookworm-slim", # Will be overridden by Target's Dockerfile
                build_timeout=self.framework.config.build_timeout,
                parallel_jobs=self.framework.config.max_concurrent_builds
            )
            
            # 3. Submit to Engine
            # The builder uses a ThreadPool, so this returns quickly
            returned_id = self.builder.build_model(config)
            
            self.logger.info(f"Build submitted with ID: {returned_id}")
            self.build_started.emit(returned_id)
            
            # 4. Start Monitoring Thread
            # We need a separate thread to poll the builder status and emit Qt signals
            # because the Builder is framework-agnostic and doesn't know Qt.
            self._monitor_active = True
            monitor_thread = threading.Thread(
                target=self._monitor_build, 
                args=(returned_id,), 
                daemon=True,
                name=f"Monitor-{returned_id}"
            )
            monitor_thread.start()
            
        except Exception as e:
            self.logger.error(f"Failed to start build: {e}", exc_info=True)
            self.build_completed.emit("error", False, str(e))

    def _monitor_build(self, build_id: str):
        """
        Polls the build status and relays logs/progress to the GUI via Signals.
        Runs in a separate thread.
        """
        last_log_idx = 0
        
        while self._monitor_active:
            status = self.builder.get_build_status(build_id)
            
            if not status:
                self.logger.warning(f"Build status for {build_id} lost.")
                break
            
            # 1. Process New Logs
            current_logs = status.logs
            while last_log_idx < len(current_logs):
                msg = current_logs[last_log_idx]
                self.build_output.emit(build_id, msg)
                last_log_idx += 1
            
            # 2. Update Progress
            self.build_progress.emit(build_id, status.progress_percent)
            
            # 3. Check Termination
            if status.status in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]:
                success = (status.status == BuildStatus.COMPLETED)
                
                # Determine primary artifact path
                output_path = ""
                if status.artifacts:
                    output_path = status.artifacts[0]
                elif success:
                    # Fallback to output dir
                    # We need to reconstruct config or store it, but here we just pass a generic success msg
                    output_path = "Check Output Directory"

                self.logger.info(f"Build {build_id} finished. Success: {success}")
                self.build_completed.emit(build_id, success, output_path)
                self._monitor_active = False
                break
            
            time.sleep(0.5)

    def stop_build(self, build_id: str):
        """Cancels a running build."""
        if self.builder:
            self.builder.cancel_build(build_id)
