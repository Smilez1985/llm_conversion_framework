#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Deployment Manager (v2.1 Enterprise)
DIREKTIVE: Goldstandard Deployment & Package Generation.

Features:
- Package Generation: Erstellt deployable ZIPs mit Checksummen.
- Dynamic Scripting: Generiert 'deploy.sh' basierend auf Hardware-Profilen.
- Integrity: Berechnet SHA256 Hashes.
- Remote Execution: SSH/SCP via Paramiko oder System-Binary.
"""

import os
import sys
import time
import socket
import logging
import subprocess
import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple, Union, List, Dict

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
    - Generates Deployment Packages (Artifact + Script + Checksums)
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

    # --- PACKAGE GENERATION (NEU) ---

    def create_deployment_package(self, 
                                artifact_path: Path, 
                                profile_name: str, 
                                docker_config: Dict[str, str],
                                output_dir: Path) -> Optional[Path]:
        """
        Schnürt ein Deployment-Paket (ZIP).
        Enthält:
        1. Das Artefakt (Model/Binary).
        2. Ein dynamisch generiertes deploy.sh.
        3. Eine checksums.sha256 Datei zur Verifikation.
        """
        artifact_path = Path(artifact_path)
        if not artifact_path.exists():
            self.logger.error(f"Artifact not found: {artifact_path}")
            return None

        # 1. Hole Hardware Flags aus dem TargetManager
        target_mgr = self.framework.get_component("target_manager")
        docker_flags = []
        if target_mgr and profile_name:
            docker_flags = target_mgr.get_docker_flags_for_profile(profile_name)
        
        flags_str = " ".join(docker_flags)
        self.logger.info(f"Building package for profile '{profile_name}' (Flags: {flags_str})")

        # 2. Erstelle temporäres Staging-Verzeichnis
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Kopiere Artefakt
            dest_artifact = temp_path / artifact_path.name
            shutil.copy2(artifact_path, dest_artifact)
            
            # 3. Generiere deploy.sh
            script_content = self._generate_deploy_script(
                artifact_name=artifact_path.name,
                docker_flags=flags_str,
                docker_config=docker_config
            )
            
            deploy_script = temp_path / "deploy.sh"
            with open(deploy_script, "w", newline='\n') as f:
                f.write(script_content)
            
            # Make executable (wichtig für Linux Targets)
            os.chmod(deploy_script, 0o755)

            # 4. Generiere Checksummen (Integrität)
            checksum_file = temp_path / "checksums.sha256"
            self._generate_checksums(temp_path, checksum_file)

            # 5. ZIP Package erstellen
            pkg_name = f"deploy_{artifact_path.stem}_{int(time.time())}.zip"
            pkg_path = output_dir / pkg_name
            
            with zipfile.ZipFile(pkg_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in temp_path.iterdir():
                    zipf.write(file, file.name)
            
            self.logger.info(f"Deployment Package created: {pkg_path}")
            return pkg_path

    def _generate_checksums(self, directory: Path, output_file: Path):
        """Berechnet SHA256 für alle Dateien im Verzeichnis."""
        with open(output_file, "w") as f:
            for file_path in directory.iterdir():
                if file_path.name == output_file.name: continue
                if file_path.is_dir(): continue
                
                sha256_hash = hashlib.sha256()
                with open(file_path, "rb") as f_in:
                    for byte_block in iter(lambda: f_in.read(4096), b""):
                        sha256_hash.update(byte_block)
                
                f.write(f"{sha256_hash.hexdigest()}  {file_path.name}\n")

    def _generate_deploy_script(self, artifact_name: str, docker_flags: str, docker_config: Dict) -> str:
        """
        Baut das Bash-Skript für das Target-Gerät.
        Implementiert Network Guard, Checksum Verify, Docker Run und Systemd.
        """
        # Basis-Template
        script = [
            "#!/bin/bash",
            "# Auto-Generated Deployment Script by LLM Framework",
            "set -e",  # Exit on error
            "",
            "echo '--- Starting Deployment ---'",
            "LOGfile=deploy.log",
            "exec > >(tee -a $LOGfile) 2>&1",
            "",
            "# 1. Network Guard (Ping Loop)",
            "echo '[1/5] Checking Network Stability...'",
            "MAX_RETRIES=30",
            "count=0",
            "while ! ping -c 1 -W 1 8.8.8.8 &> /dev/null; do",
            "    echo 'Waiting for internet connection...'",
            "    sleep 2",
            "    ((count++))",
            "    if [ $count -ge $MAX_RETRIES ]; then",
            "        echo 'ERROR: Network unreachable. Aborting.'",
            "        exit 1",
            "    fi",
            "done",
            "echo 'Network is UP.'",
            "",
            "# 2. Integrity Check",
            "echo '[2/5] Verifying Integrity...'",
            "if command -v sha256sum &> /dev/null; then",
            "    sha256sum -c checksums.sha256",
            "    if [ $? -ne 0 ]; then",
            "        echo 'CRITICAL: Checksum verification FAILED! Corrupt package.'",
            "        exit 1",
            "    fi",
            "    echo 'Integrity verified.'",
            "else",
            "    echo 'WARN: sha256sum not found. Skipping check.'",
            "fi",
            ""
        ]

        # Docker Logic (Optional)
        use_docker = docker_config.get("use_docker", False)
        
        if use_docker:
            image_name = docker_config.get("image_name", "llm-inference:latest")
            container_name = "llm-inference-service"
            
            script.extend([
                "# 3. Docker Setup",
                "echo '[3/5] Setting up Docker Container...'",
                f"IMAGE_NAME='{image_name}'",
                f"CONTAINER_NAME='{container_name}'",
                "",
                "# Stop old container",
                "if [ $(docker ps -a -q -f name=$CONTAINER_NAME) ]; then",
                "    echo 'Stopping old container...'",
                "    docker rm -f $CONTAINER_NAME",
                "fi",
                "",
                "# Load Image (if present as file) or Pull",
                "if [ -f image.tar ]; then",
                "    echo 'Loading image from file...'",
                "    docker load -i image.tar",
                "else",
                "    echo 'Pulling image from registry...'",
                "    docker pull $IMAGE_NAME",
                "fi",
                "",
                "# 4. Run Container",
                "echo '[4/5] Starting Service...'",
                f"docker run -d --name $CONTAINER_NAME \\",
                "  --restart unless-stopped \\",
                "  --network host \\",
                f"  {docker_flags} \\",  # Hier kommen die Hardware-Flags rein!
                "  -v $(pwd)/data:/app/data \\", # Persistenz
                f"  $IMAGE_NAME",
                ""
            ])
            
            # Systemd Service Creation (Optional, für Container-Autostart via Docker meist nicht nötig, 
            # aber gut für nicht-Docker Apps)
        else:
            # Native Execution Logic
            script.extend([
                "# 3. Native Setup",
                "echo '[3/5] Setting up Native Environment...'",
                f"chmod +x {artifact_name}",
                "",
                "# 4. Systemd Persistence",
                "echo '[4/5] Installing Systemd Service...'",
                "SERVICE_NAME=llm-edge-node",
                "cat <<EOF > /etc/systemd/system/$SERVICE_NAME.service",
                "[Unit]",
                "Description=LLM Edge Inference Node",
                "After=network.target",
                "",
                "[Service]",
                f"ExecStart=$(pwd)/{artifact_name}",
                "Restart=always",
                "User=root",
                "WorkingDirectory=$(pwd)",
                "",
                "[Install]",
                "WantedBy=multi-user.target",
                "EOF",
                "",
                "systemctl daemon-reload",
                "systemctl enable $SERVICE_NAME",
                "systemctl restart $SERVICE_NAME",
                ""
            ])

        script.append("echo '[5/5] Deployment Finished Successfully.'")
        return "\n".join(script)

    # --- DEPLOYMENT & EXECUTION (Original) ---

    def check_connectivity(self, ip: str, port: int = 22) -> bool:
        """Prüft, ob der SSH-Port am Ziel erreichbar ist."""
        try:
            with socket.create_connection((ip, port), timeout=2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def wait_for_connection(self, ip: str, port: int = 22, max_wait: int = 300) -> bool:
        """Blockierende 'Ping Loop', die auf das Zielgerät wartet."""
        start = time.time()
        self.logger.info(f"Waiting for connection to {ip}:{port}...")
        while time.time() - start < max_wait:
            if self.check_connectivity(ip, port):
                self.logger.info(f"Connection to {ip} established.")
                return True
            time.sleep(2)
        return False

    def deploy_artifact(self, 
                       artifact_path: Path, 
                       target_ip: str, 
                       user: str, 
                       password: Optional[str] = None, 
                       target_dir: str = "/tmp/llm_deploy") -> bool:
        """Hauptmethode für das Deployment."""
        artifact_path = Path(artifact_path)
        if not artifact_path.exists():
            self.logger.error(f"Artifact not found: {artifact_path}")
            return False

        if not self.wait_for_connection(target_ip):
            return False

        self.logger.info(f"Starting deployment to {user}@{target_ip}...")

        success = False
        if PARAMIKO_AVAILABLE and password:
            success = self._deploy_via_paramiko(artifact_path, target_ip, user, password, target_dir)
        else:
            success = self._deploy_via_system_ssh(artifact_path, target_ip, user, target_dir)

        return success

    def execute_command(self, cmd: str, target_ip: str, user: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Führt Shell-Befehl auf Remote-Gerät aus (für Self-Healing)."""
        if not self.check_connectivity(target_ip):
            return False, "Target not reachable"

        if PARAMIKO_AVAILABLE and password:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(target_ip, username=user, password=password, timeout=self.timeout)
                stdin, stdout, stderr = ssh.exec_command(cmd)
                exit_status = stdout.channel.recv_exit_status()
                out_msg = stdout.read().decode().strip()
                err_msg = stderr.read().decode().strip()
                ssh.close()
                return (exit_status == 0, f"STDOUT: {out_msg}\nSTDERR: {err_msg}")
            except Exception as e:
                return False, str(e)
        else:
            target_str = f"{user}@{target_ip}"
            try:
                res = subprocess.run(["ssh", target_str, cmd], capture_output=True, text=True, timeout=30)
                return (res.returncode == 0, f"{res.stdout}\n{res.stderr}")
            except Exception as e:
                return False, str(e)

    def _deploy_via_paramiko(self, artifact_path: Path, ip: str, user: str, password: str, target_dir: str) -> bool:
        """Deployment via Paramiko (RAM-only password)."""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(ip, username=user, password=password, timeout=self.timeout)
            sftp = ssh.open_sftp()
            
            try: sftp.mkdir(target_dir)
            except OSError: pass
            
            remote_path = f"{target_dir}/{artifact_path.name}"
            sftp.put(str(artifact_path), remote_path)
            
            # Entpacken und Ausführen
            setup_cmd = f"cd {target_dir} && unzip -o {artifact_path.name} && chmod +x deploy.sh && ./deploy.sh"
            
            stdin, stdout, stderr = ssh.exec_command(setup_cmd)
            for line in stdout: self.logger.info(f"[REMOTE] {line.strip()}")
            
            return stdout.channel.recv_exit_status() == 0
        except Exception as e:
            self.logger.error(f"Paramiko Error: {e}")
            return False
        finally:
            ssh.close()

    def _deploy_via_system_ssh(self, artifact_path: Path, ip: str, user: str, target_dir: str) -> bool:
        """Fallback Deployment via System SSH."""
        target_str = f"{user}@{ip}"
        try:
            subprocess.run(["ssh", target_str, f"mkdir -p {target_dir}"], check=True)
            subprocess.run(["scp", str(artifact_path), f"{target_str}:{target_dir}/"], check=True)
            
            setup_cmd = f"cd {target_dir} && unzip -o {artifact_path.name} && chmod +x deploy.sh && ./deploy.sh"
            res = subprocess.run(["ssh", target_str, setup_cmd], capture_output=True, text=True)
            
            if res.returncode == 0:
                self.logger.info(f"[REMOTE] {res.stdout}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"System SSH Error: {e}")
            return False
