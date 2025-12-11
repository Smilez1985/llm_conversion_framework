#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Deployment Manager
DIREKTIVE: Goldstandard, Robustness, 'Zero-Dependency' (Target).

Zweck:
Verwaltet das Deployment von Artefakten auf Edge-Geräte via SSH/SCP.
Implementiert 'Network Guard' (Ping Loop) für instabile Verbindungen.
Nutzt Paramiko für Passwort-Auth (RAM-only) oder System-SSH für Key-Auth.
"""

import os
import sys
import time
import socket
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Union

# Try to import Paramiko for clean Python-native SSH
try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

from orchestrator.utils.logging import get_logger

class DeploymentManager:
    """
    Orchestrates the deployment process.
    - Connectivity Checks (Ping Loop)
    - File Transfer (SCP/SFTP)
    - Remote Execution (SSH)
    """
    
    def __init__(self, framework_manager=None):
        self.logger = get_logger(__name__)
        self.framework = framework_manager
        # Settings
        self.timeout = 10
        self.max_retries = 5
        self.retry_delay = 5

    def check_connectivity(self, ip: str, port: int = 22) -> bool:
        """
        Prüft, ob der SSH-Port am Ziel erreichbar ist (TCP Connect).
        """
        try:
            with socket.create_connection((ip, port), timeout=2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def wait_for_connection(self, ip: str, port: int = 22, max_wait: int = 300) -> bool:
        """
        Blockierende 'Ping Loop', die auf das Zielgerät wartet.
        """
        start = time.time()
        self.logger.info(f"Waiting for connection to {ip}:{port}...")
        
        while time.time() - start < max_wait:
            if self.check_connectivity(ip, port):
                self.logger.info(f"Connection to {ip} established.")
                return True
            
            # Kurze Pause um CPU zu schonen
            time.sleep(2)
            
            # Optional: Log alle 10 Sekunden
            if int(time.time() - start) % 10 == 0:
                self.logger.debug(f"Still waiting for {ip}...")
                
        self.logger.error(f"Timeout waiting for {ip} after {max_wait}s.")
        return False

    def deploy_artifact(self, 
                       artifact_path: Path, 
                       target_ip: str, 
                       user: str, 
                       password: Optional[str] = None, 
                       target_dir: str = "/tmp/llm_deploy") -> bool:
        """
        Hauptmethode für das Deployment.
        Überträgt das Artefakt und führt das enthaltene deploy.sh aus.
        """
        artifact_path = Path(artifact_path)
        if not artifact_path.exists():
            self.logger.error(f"Artifact not found: {artifact_path}")
            return False

        # 1. Connection Check
        if not self.wait_for_connection(target_ip):
            return False

        self.logger.info(f"Starting deployment to {user}@{target_ip}...")

        # 2. Transfer Strategy Selection
        success = False
        if PARAMIKO_AVAILABLE and password:
            success = self._deploy_via_paramiko(artifact_path, target_ip, user, password, target_dir)
        else:
            if password:
                self.logger.warning("Paramiko not installed. Cannot use password auth safely. Fallback to System SSH (requires Keys).")
            success = self._deploy_via_system_ssh(artifact_path, target_ip, user, target_dir)

        return success

    def execute_command(self, cmd: str, target_ip: str, user: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """
        Führt einen beliebigen Shell-Befehl auf dem Remote-Gerät aus.
        Wird vom Self-Healing-Manager genutzt.
        """
        self.logger.info(f"Remote Exec ({target_ip}): {cmd}")
        
        # Verbindung prüfen
        if not self.check_connectivity(target_ip):
            return False, "Target not reachable"

        # Paramiko (Bevorzugt)
        if PARAMIKO_AVAILABLE and password:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(target_ip, username=user, password=password, timeout=self.timeout)
                stdin, stdout, stderr = ssh.exec_command(cmd)
                exit_status = stdout.channel.recv_exit_status()
                out_msg = stdout.read().decode().strip()
                err_msg = stderr.read().decode().strip()
                
                full_log = f"STDOUT: {out_msg}\nSTDERR: {err_msg}"
                if exit_status == 0:
                    return True, full_log
                else:
                    return False, full_log
            except Exception as e:
                return False, str(e)
            finally:
                ssh.close()
        
        # System SSH (Fallback)
        else:
            target_str = f"{user}@{target_ip}"
            try:
                res = subprocess.run(
                    ["ssh", target_str, cmd], 
                    capture_output=True, 
                    text=True, 
                    timeout=30
                )
                if res.returncode == 0:
                    return True, res.stdout
                else:
                    return False, f"{res.stdout}\n{res.stderr}"
            except Exception as e:
                return False, str(e)

    def _deploy_via_paramiko(self, artifact_path: Path, ip: str, user: str, password: str, target_dir: str) -> bool:
        """
        Deployment mittels Paramiko (Python Native).
        Sicher, da Passwort nur im RAM existiert.
        """
        self.logger.info("Using Paramiko (Secure Password Auth)...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Connect
            ssh.connect(ip, username=user, password=password, timeout=self.timeout)
            
            # SFTP Transfer
            sftp = ssh.open_sftp()
            
            # Ensure target dir
            self.logger.info(f"Creating remote directory: {target_dir}")
            try:
                sftp.mkdir(target_dir)
            except OSError:
                pass # Dir exists or permission issue
            
            # Upload File
            remote_path = f"{target_dir}/{artifact_path.name}"
            self.logger.info(f"Uploading {artifact_path.name} ({artifact_path.stat().st_size / 1024 / 1024:.2f} MB)...")
            
            # Callback für Progress Tracking könnte hier eingebaut werden
            sftp.put(str(artifact_path), remote_path)
            
            # Execution
            self.logger.info("Executing setup on target...")
            
            # Entpacken und deploy.sh suchen
            # Wir nutzen 'unzip' oder 'tar' je nach Dateiendung
            if artifact_path.suffix == ".zip":
                cmd = f"cd {target_dir} && unzip -o {artifact_path.name} && chmod +x deploy.sh && ./deploy.sh"
            else:
                cmd = f"cd {target_dir} && tar -xf {artifact_path.name} && chmod +x deploy.sh && ./deploy.sh"
            
            stdin, stdout, stderr = ssh.exec_command(cmd)
            
            # Stream Output
            for line in stdout:
                self.logger.info(f"[REMOTE] {line.strip()}")
            
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status == 0:
                self.logger.info("✅ Deployment successful.")
                return True
            else:
                self.logger.error(f"Remote command failed (Exit: {exit_status})")
                for line in stderr:
                    self.logger.error(f"[REMOTE ERR] {line.strip()}")
                return False

        except Exception as e:
            self.logger.error(f"Paramiko Deployment Error: {e}")
            return False
        finally:
            ssh.close()

    def _deploy_via_system_ssh(self, artifact_path: Path, ip: str, user: str, target_dir: str) -> bool:
        """
        Fallback Deployment mittels System-Binary (scp/ssh).
        Benötigt SSH-Keys (passwordless).
        """
        self.logger.info("Using System SSH/SCP (Key Auth)...")
        target_str = f"{user}@{ip}"
        
        try:
            # 1. Prepare Dir
            subprocess.run(["ssh", target_str, f"mkdir -p {target_dir}"], check=True, timeout=10)
            
            # 2. SCP Upload
            self.logger.info("Uploading artifact via SCP...")
            subprocess.run(["scp", str(artifact_path), f"{target_str}:{target_dir}/"], check=True)
            
            # 3. Remote Exec
            self.logger.info("Executing remote script...")
            filename = artifact_path.name
            
            if filename.endswith(".zip"):
                remote_cmd = f"cd {target_dir} && unzip -o {filename} && chmod +x deploy.sh && ./deploy.sh"
            else:
                remote_cmd = f"cd {target_dir} && tar -xf {filename} && chmod +x deploy.sh && ./deploy.sh"
            
            res = subprocess.run(["ssh", target_str, remote_cmd], capture_output=True, text=True)
            
            if res.returncode == 0:
                self.logger.info(f"[REMOTE] {res.stdout}")
                self.logger.info("✅ Deployment successful.")
                return True
            else:
                self.logger.error(f"Remote Execution Failed: {res.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"System SSH Error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected Deployment Error: {e}")
            return False
