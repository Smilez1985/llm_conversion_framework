import os
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Iterator
from datetime import datetime
import threading
import queue
import time

import docker
import yaml
from rich.console import Console
from rich.text import Text

from PySide6.QtCore import (
    QThread, pyqtSignal, QProcess, QByteArray, Qt, QObject, QTimer, QCoreApplication
)
# Imports aus dem lokalen Package
from orchestrator.Core.framework import FrameworkManager, BuildJob
from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError
from orchestrator.utils.helpers import check_command_exists

# ============================================================================
# DOCKER MANAGEMENT THREAD
# ============================================================================

class DockerWorker(QObject):
    """
    Arbeiterobjekt, das Build-Jobs in der Warteschlange abarbeitet.
    Läuft im DockerManager Thread.
    """
    
    # Signale
    build_output = pyqtSignal(str, str)
    build_progress = pyqtSignal(str, int)
    build_completed = pyqtSignal(str, bool)
    
    def __init__(self, framework_manager: FrameworkManager):
        super().__init__()
        self.logger = get_logger(__name__)
        self.fm = framework_manager
        self._is_running = True
        
    def process_queue(self):
        """Hauptschleife zur Abarbeitung der Build-Warteschlange."""
        while self._is_running:
            try:
                # Hole nächsten Job vom FrameworkManager
                job_data = self.fm.get_next_queued_build_status()
                
                if job_data and job_data.get('status') == 'queued':
                    build_id = job_data['id']
                    self.logger.info(f"Worker picking up build job: {build_id}")
                    self._execute_build_pipeline(build_id, job_data)
                else:
                    time.sleep(1)
                    
            except Exception as e:
                self.logger.error(f"Error in DockerWorker process_queue: {e}")
                time.sleep(5)
    
    def _execute_build_pipeline(self, build_id: str, job_data: Dict[str, Any]):
        """
        Führt die 4-Module-Cross-Compile-Pipeline in einem Docker-Container aus.
        """
        try:
            self.fm.update_build_status(build_id, "running", 1)
            config = job_data.get('config', {})
            
            self.logger.info(f"Executing pipeline for job {build_id} on target {job_data.get('target')}")
            
            # --- 1. Docker Compose Build ---
            build_cmd = self._get_docker_compose_build_command(job_data)
            self._run_shell_command(build_id, build_cmd, "Docker Image Build")
            
            # --- 2. Pipeline Execution (mit Source Injection) ---
            pipeline_cmd = self._get_docker_exec_pipeline_command(job_data)
            self._run_shell_command(build_id, pipeline_cmd, "Cross-Compile & Quantization Pipeline")
            
            # --- 3. Finalisierung ---
            self.build_completed.emit(build_id, True)
            self.fm.update_build_status(build_id, "completed", 100)
            
        except Exception as e:
            self.logger.error(f"Pipeline execution failed for {build_id}: {e}")
            self.build_completed.emit(build_id, False)
            self.fm.update_build_status(build_id, "failed", 0)

    def _run_shell_command(self, build_id: str, command: List[str], description: str):
        """Führt einen Shell-Befehl über QProcess aus."""
        self.build_output.emit(build_id, f"--- Running: {description} ---")
        
        process = QProcess()
        process.setProcessChannelMode(QProcess.MergedChannels)
        
        process.readyReadStandardOutput.connect(
            lambda: self._handle_build_output(build_id, process)
        )
        
        process.start(command[0], command[1:])
        
        if not process.waitForStarted(5000):
            raise Exception(f"Failed to start process: {process.errorString()}")
            
        if not process.waitForFinished(self.fm.config.build_timeout * 1000):
            process.kill()
            raise Exception(f"Process exceeded timeout.")
            
        if process.exitCode() != 0:
            self._handle_build_output(build_id, process) 
            raise Exception(f"Command failed with exit code {process.exitCode()}")
            
        self.build_output.emit(build_id, f"--- {description} completed successfully ---")

    def _handle_build_output(self, build_id: str, process: QProcess):
        """Verarbeitet Output und sendet ihn an GUI."""
        data = process.readAllStandardOutput().data().decode()
        for line in data.strip().split('\n'):
            if line.strip():
                self.build_output.emit(build_id, line)
                if "[" in line and "%" in line: # Simpler Progress Parser
                    try:
                        progress = int(line.split('[')[-1].split('%')[0].strip())
                        self.build_progress.emit(build_id, progress)
                    except: pass
    
    def _get_docker_compose_build_command(self, job_data: Dict[str, Any]) -> List[str]:
        """Generiert Docker Compose Build Befehl."""
        target_name = job_data['target'].lower().replace(' ', '-')
        cmd = ["docker-compose", "build", "--progress=plain"]
        cmd.extend([target_name + '-builder'])
        return cmd

    def _get_docker_exec_pipeline_command(self, job_data: Dict[str, Any]) -> List[str]:
        """Generiert Docker Exec Befehl mit INJEKTION der Sources."""
        target_name = job_data['target'].lower().replace(' ', '-')
        
        # Basis-Kommando
        pipeline_cmd = ["docker-compose", "exec", "-T"]
        
        # --- SOURCE INJECTION LOGIC (UPDATED FOR SECURE SOURCES) ---
        sources = self.fm.config.source_repositories
        
        # Helper to inject URL and Commit if available
        def inject_source(key_in_config, env_var_prefix):
            if key_in_config in sources:
                src_data = sources[key_in_config]
                
                # Check if it's a secure object (dict) or simple string
                if isinstance(src_data, dict):
                    url = src_data.get('url')
                    commit = src_data.get('commit')
                    if url: 
                        pipeline_cmd.extend(["-e", f"{env_var_prefix}_REPO_OVERRIDE={url}"])
                    if commit:
                        pipeline_cmd.extend(["-e", f"{env_var_prefix}_COMMIT={commit}"])
                else:
                    # Simple string fallback
                    pipeline_cmd.extend(["-e", f"{env_var_prefix}_REPO_OVERRIDE={src_data}"])

        # Core Mappings
        inject_source("core.llama_cpp", "LLAMA_CPP")
        
        # Rockchip Mappings
        inject_source("rockchip_npu.rknn_toolkit2", "RKNN_TOOLKIT2")
        inject_source("rockchip_npu.rknn_llm", "RKNN_LLM")
             
        # Voice Mappings
        inject_source("voice_tts.piper_tts", "PIPER_PHONEMIZE")
        inject_source("voice_tts.vosk_api", "VOSK_API")

        # Container und Script Argumente
        pipeline_cmd.extend([
            target_name + '-builder',
            "/app/entrypoint.sh", "pipeline",
            job_data.get('config', {}).get('model_path', '/models/input'), # Fallback
            job_data['model_name'],
            job_data['quantization']
        ])
        
        if job_data.get('config', {}).get('hardware_profile'):
             pipeline_cmd.append(f"--profile={job_data['config']['hardware_profile']}")
             
        return pipeline_cmd

class DockerManager(QObject):
    """API für Docker-Management."""
    build_output = pyqtSignal(str, str)
    build_progress = pyqtSignal(str, int)
    build_completed = pyqtSignal(str, bool, str)
    
    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__)
        self._thread = QThread()
        self._worker: Optional[DockerWorker] = None
        self._is_ready = False
        
    def initialize(self, fm: FrameworkManager):
        if self._is_ready: return
        self._worker = DockerWorker(fm)
        self._worker.moveToThread(self._thread)
        self._worker.build_output.connect(self.build_output)
        self._worker.build_progress.connect(self.build_progress)
        self._worker.build_completed.connect(lambda bid, suc: self._handle_comp(bid, suc, fm))
        self._thread.start()
        QTimer.singleShot(0, self._worker.process_queue)
        self._is_ready = True
        
    def _handle_comp(self, build_id, success, fm):
        out = f"{fm.config.output_dir}/packages/{build_id}" if success else ""
        self.build_completed.emit(build_id, success, out)

    def start_build(self, job_config: Dict[str, Any]) -> str:
        if not self._is_ready: raise Exception("DockerManager not init")
        fm = self._worker.fm
        bid = fm.create_build_id()
        job = BuildJob(
            id=bid,
            model_name=job_config.get('model_name', 'Unknown'),
            target=job_config.get('target', 'Unknown'),
            quantization=job_config.get('quantization', 'Q4_K_M'),
            status="queued",
            config=job_config
        )
        fm.register_build(bid, job)
        return bid
