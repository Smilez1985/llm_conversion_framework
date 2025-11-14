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
# Annahme: Diese Data Classes und Utilities sind im Python Path verfügbar
# Die folgenden Imports müssen in Ihrer Umgebung existieren:
from orchestrator.core.framework import FrameworkManager, BuildJob
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
    
    # Signale, die an den Haupt-Thread gesendet werden
    build_output = pyqtSignal(str, str)         # build_id, output_line
    build_progress = pyqtSignal(str, int)       # build_id, progress
    build_completed = pyqtSignal(str, bool)     # build_id, success
    
    def __init__(self, framework_manager: FrameworkManager):
        super().__init__()
        self.logger = get_logger(__name__)
        self.fm = framework_manager
        self._is_running = True
        
    def process_queue(self):
        """Hauptschleife zur Abarbeitung der Build-Warteschlange."""
        
        while self._is_running:
            try:
                # Prüfe, ob Builds aktiv sind oder in der Warteschlange
                # (Annahme: FrameworkManager hat eine Methode, um den nächsten Job zu bekommen)
                job_status = self.fm.get_next_queued_build_status() 
                
                if job_status and job_status.get('status') == 'queued':
                    build_id = job_status['id']
                    self.logger.info(f"Worker picking up build job: {build_id}")
                    self._execute_build_pipeline(build_id)
                else:
                    time.sleep(1)
                    
            except Exception as e:
                self.logger.error(f"Error in DockerWorker process_queue: {e}")
                time.sleep(5)
    
    def _execute_build_pipeline(self, build_id: str):
        """
        Führt die 4-Module-Cross-Compile-Pipeline in einem Docker-Container aus.
        """
        job = self.fm.get_build_status(build_id)
        if not job:
            return
            
        try:
            self.fm.update_build_status(build_id, "running", 1)
            self.logger.info(f"Executing pipeline for job {build_id} on target {job['config']['target']}")
            
            # --- 1. Docker Compose Build (Image erstellen) ---
            build_cmd = self._get_docker_compose_build_command(job['config'])
            self._run_shell_command(build_id, build_cmd, "Docker Image Build")
            
            # --- 2. Modul-Execution Pipeline (config -> convert -> target) ---
            # Dieser Befehl ruft den /app/entrypoint.sh auf, der die Module ausführt.
            pipeline_cmd = self._get_docker_exec_pipeline_command(job['config'])
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
        
        self.build_output.emit(build_id, f"--- Running: {description} ({' '.join(command[:3])}...) ---")
        
        process = QProcess()
        process.setProcessChannelMode(QProcess.MergedChannels)
        
        # Verbindung der Signale
        process.readyReadStandardOutput.connect(
            lambda: self._handle_build_output(build_id, process)
        )
        
        process.start(command[0], command[1:])
        
        if not process.waitForStarted(5000):
            raise Exception(f"Failed to start process: {process.errorString()}")
            
        if not process.waitForFinished(self.fm.config.build_timeout * 1000):
            process.kill()
            raise Exception(f"Process exceeded timeout of {self.fm.config.build_timeout}s.")
            
        if process.exitCode() != 0:
            # Sende den letzten Output, falls der Prozess abbricht
            self._handle_build_output(build_id, process) 
            raise Exception(f"Command failed with exit code {process.exitCode()}")
            
        self.build_output.emit(build_id, f"--- {description} completed successfully ---")

    def _handle_build_output(self, build_id: str, process: QProcess):
        """Verarbeitet den Output und sendet ihn an den Haupt-Thread."""
        data = process.readAllStandardOutput().data().decode()
        
        for line in data.strip().split('\n'):
            if line.strip():
                self.build_output.emit(build_id, line)
                
                # Progress-Extraktion (Beispiel)
                if "[" in line and "%" in line:
                    try:
                        progress_match = line.split('[')[-1].split('%')[0].strip()
                        if progress_match.isdigit():
                            progress = int(progress_match)
                            self.build_progress.emit(build_id, progress)
                    except:
                        pass
    
    def _get_docker_compose_build_command(self, job_config: Dict[str, Any]) -> List[str]:
        """Generiert den Docker Compose Build Befehl."""
        
        target_name = job_config['target'].lower().replace(' ', '-')
        
        cmd = ["docker-compose", "build", "--progress=plain"]
        if job_config.get('clean'):
            cmd.append("--no-cache")
        
        cmd.extend([target_name + '-builder'])
        
        return cmd

    def _get_docker_exec_pipeline_command(self, job_config: Dict[str, Any]) -> List[str]:
        """Generiert den Docker Exec Befehl zum Starten der 4-Module-Pipeline."""
        
        target_name = job_config['target'].lower().replace(' ', '-')
        
        # Der Befehl startet den /app/entrypoint.sh mit dem 'pipeline' Subkommando
        pipeline_cmd = [
            "docker-compose", "exec", "-T", target_name + '-builder',
            "/app/entrypoint.sh", "pipeline",
            # Pipeline-Parameter: Input-Pfad, Model-Name, Quant-Methode
            job_config['model_path'],
            job_config['model_name'],
            job_config['quantization'],
            f"--profile={job_config['hardware_profile']}" if job_config.get('hardware_profile') else ""
        ]
        
        return [c for c in pipeline_cmd if c]


class DockerManager(QObject):
    """
    Der DockerManager, der im Haupt-Thread läuft und die API bereitstellt.
    """
    
    # API-Signale
    build_output = pyqtSignal(str, str)
    build_progress = pyqtSignal(str, int)
    build_completed = pyqtSignal(str, bool, str) # build_id, success, output_path
    
    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__)
        self._thread = QThread()
        self._worker: Optional[DockerWorker] = None
        self._is_ready = False
        
    def initialize(self, fm: FrameworkManager):
        """Initialisiert den Worker-Thread und verbindet Signale."""
        
        if self._is_ready:
            return
            
        self._worker = DockerWorker(fm)
        self._worker.moveToThread(self._thread)
        
        # Verbindung der Signale vom Worker zum Manager (im Haupt-Thread)
        self._worker.build_output.connect(self.build_output)
        self._worker.build_progress.connect(self.build_progress)
        self._worker.build_completed.connect(lambda build_id, success: 
            self._handle_worker_completion(build_id, success, fm)
        )
        
        # Starten des Threads und des Worker-Prozesses
        self._thread.start()
        # SingleShot stellt sicher, dass der Worker im neuen Thread gestartet wird
        QTimer.singleShot(0, self._worker.process_queue) 
        
        self._is_ready = True
        self.logger.info("DockerManager thread initialized")
        
    def _handle_worker_completion(self, build_id: str, success: bool, fm: FrameworkManager):
        """Verarbeitet den Abschluss des Builds und sendet das Finale Signal."""
        
        job_status = fm.get_build_status(build_id)
        # Annahme: output_path wird im Worker gesetzt und ist in job_status['config'] enthalten
        output_path = job_status.get('config', {}).get('output_path', '') if job_status else ""
        
        self.build_completed.emit(build_id, success, output_path)
        
    def start_build(self, build_config: Dict[str, Any]) -> str:
        """API: Fügt einen neuen Build-Job zur Warteschlange hinzu."""
        
        if not self._is_ready:
            raise Exception("DockerManager not initialized.")
            
        fm = self._worker.fm
        build_id = fm.create_build_id()
        
        # Registriere BuildJob im FrameworkManager
        build_job = BuildJob(
            id=build_id,
            model_name=build_config.get('model_name', 'Unknown'),
            target=build_config.get('target', 'Unknown'),
            quantization=build_config.get('quantization', 'Q4_K_M'),
            status="queued",
            config=build_config,
            # output_path ist der Zielordner
            output_path=f"{fm.config.output_dir}/packages/{build_id}" 
        )
        fm.register_build(build_id, build_job)
        
        return build_id

    def stop_build(self, build_id: str):
        """API: Stoppt einen laufenden Build (Muss die Logik in DockerWorker/QProcess/Docker-Client aufrufen)."""
        # Diese Logik müsste den QProcess stoppen oder den Docker-Client Container beenden.
        self.logger.warning(f"Stop command issued for build: {build_id}")
        # Die Implementierung des Stopps des QProcess/Docker-Containers erfolgt im tatsächlichen Orchestrator.
        
    def follow_build(self, build_id: str) -> Iterator[str]:
        """API: Liefert Output-Linien für die CLI (Muss Asynchron implementiert werden)."""
        self.logger.warning("Follow build API requires log reading/queue implementation.")
        yield f"Error: Cannot follow build {build_id} directly in this architecture."