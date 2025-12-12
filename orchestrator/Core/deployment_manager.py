#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Deployment Manager (v2.2 Air-Gap & Configs)
DIREKTIVE: Goldstandard Deployment.

Features:
- Package Generation: Erstellt deployable ZIPs mit Checksummen.
- Air-Gap Support: Exportiert Docker-Images via 'docker save' ins Paket.
- Config Sync: Überträgt User-Profile (GLaDOS) auf das Target.
- Dynamic Scripting: Generiert intelligentes 'deploy.sh'.
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

# Docker Client from Framework
import docker

from orchestrator.utils.logging import get_logger

class DeploymentManager:
    """
    Orchestrates the deployment process.
    Handles Package Generation (Offline/Air-Gap capable), Transfer and Execution.
    """
    
    def __init__(self, framework_manager=None):
        self.logger = get_logger(__name__)
        self.framework = framework_manager
        # Settings
        self.timeout = 10
        self.max_retries = 5
        self.retry_delay = 5

    # --- PACKAGE GENERATION ---

    def create_deployment_package(self, 
                                artifact_path: Path, 
                                profile_name: str, 
                                docker_config: Dict[str, str],
                                output_dir: Path) -> Optional[Path]:
        """
        Schnürt ein Deployment-Paket (ZIP).
        Enthält: Artifact, deploy.sh, checksums, user_configs und (opt) Docker Images.
        """
        artifact_path = Path(artifact_path)
        if not artifact_path.exists():
            self.logger.error(f"Artifact not found: {artifact_path}")
            return None

        # 1. Hardware Flags laden
        target_mgr = self.framework.get_component("target_manager")
        docker_flags = []
        if target_mgr and profile_name:
            docker_flags = target_mgr.get_docker_flags_for_profile(profile_name)
        
        flags_str = " ".join(docker_flags)
        self.logger.info(f"Building package for '{profile_name}' (Flags: {flags_str})")

        # 2. Staging Area
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # A. Artefakt kopieren
            dest_artifact = temp_path / artifact_path.name
            shutil.copy2(artifact_path, dest_artifact)
            
            # B. User Configs (GLaDOS etc.) bündeln
            self._bundle_user_configs(temp_path / "data" / "configs")

            # C. Docker Images exportieren (Air-Gap)
            use_docker = docker_config.get("use_docker", False)
            if use_docker:
                self._export_docker_images(docker_config, temp_path / "images")

            # D. Generiere deploy.sh
            script_content = self._generate_deploy_script(
                artifact_name=artifact_path.name,
                docker_flags=flags_str,
                use_docker=use_docker
            )
            
            deploy_script = temp_path / "deploy.sh"
            with open(deploy_script, "w", newline='\n') as f:
                f.write(script_content)
            os.chmod(deploy_script, 0o755)

            # E. Checksummen
            self._generate_checksums(temp_path, temp_path / "checksums.sha256")

            # F. ZIP erstellen
            pkg_name = f"deploy_{artifact_path.stem}_{int(time.time())}.zip"
            pkg_path = output_dir / pkg_name
            
            # Recursive Zip
            self.logger.info("Zipping package...")
            with zipfile.ZipFile(pkg_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(temp_path):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(temp_path)
                        zipf.write(file_path, arcname)
            
            self.logger.info(f"Deployment Package created: {pkg_path} ({pkg_path.stat().st_size / 1024 / 1024:.2f} MB)")
            return pkg_path

    def _bundle_user_configs(self, dest_dir: Path):
        """Kopiert User-Profile (GLaDOS, Templates) ins Paket."""
        try:
            # Quelle: configs/ Ordner des Frameworks
            src_dir = Path(self.framework.config.configs_dir)
            
            # Wir kopieren nur relevante Unterordner, nicht alles (keine Secrets!)
            folders_to_copy = ["user_profiles", "voice_templates", "prompts"]
            
            for folder in folders_to_copy:
                src = src_dir / folder
                if src.exists():
                    shutil.copytree(src, dest_dir / folder, dirs_exist_ok=True)
                    self.logger.info(f"Bundled config: {folder}")
                    
        except Exception as e:
            self.logger.warning(f"Failed to bundle user configs: {e}")

    def _export_docker_images(self, docker_config: Dict, dest_dir: Path):
        """
        Exportiert Docker-Images via 'docker save' für Offline-Installation.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        client = self.framework.get_component("docker_client")
        if not client:
            self.logger.error("Docker client not available. Cannot export images.")
            return

        # TODO: Hier sollten die echten Image-Namen aus der Config kommen
        images_to_save = ["ghcr.io/llm-framework/inference-node:latest"] 
        
        for img_name in images_to_save:
            sanitized_name = img_name.replace("/", "_").replace(":", "_")
            tar_path = dest_dir / f"{sanitized_name}.tar"
            
            self.logger.info(f"Exporting Docker Image: {img_name} (this takes time)...")
            try:
                # Pull first to be sure
                try: client.images.pull(img_name)
                except: pass 

                image = client.images.get(img_name)
                with open(tar_path, "wb") as f:
                    for chunk in image.save(named=True):
                        f.write(chunk)
                self.logger.info(f"Exported to {tar_path.name}")
            except Exception as e:
                self.logger.error(f"Failed to export {img_name}: {e}")

    def _generate_checksums(self, directory: Path, output_file: Path):
        """Berechnet SHA256 rekursiv."""
        with open(output_file, "w") as f:
            for root, _, files in os.walk(directory):
                for file in files:
                    file_path = Path(root) / file
                    if file_path.name == output_file.name: continue
                    
                    sha256 = hashlib.sha256()
                    with open(file_path, "rb") as f_in:
                        for chunk in iter(lambda: f_in.read(4096), b""):
                            sha256.update(chunk)
                    
                    rel_path = file_path.relative_to(directory)
                    f.write(f"{sha256.hexdigest()}  {rel_path}\n")

    def _generate_deploy_script(self, artifact_name: str, docker_flags: str, use_docker: bool) -> str:
        """
        Generiert das Bash-Skript für das Target-Gerät.
        """
        script = [
            "#!/bin/bash",
            "set -e",
            "LOGfile=deploy.log",
            "exec > >(tee -a $LOGfile) 2>&1",
            "echo '--- Starting Deployment (v2.2 Air-Gap) ---'",
            "",
            "# 1. Integrity Check",
            "echo '[1/6] Verifying Integrity...'",
            "if command -v sha256sum &> /dev/null; then",
            "    sha256sum -c checksums.sha256",
            "    if [ $? -ne 0 ]; then echo 'CRITICAL: Checksum FAIL'; exit 1; fi",
            "    echo 'Integrity verified.'",
            "fi",
            "",
            "# 2. Config Setup",
            "echo '[2/6] Restoring User Configurations...'",
            "mkdir -p ./data/configs",
            "if [ -d 'data/configs' ]; then cp -r data/configs/* ./data/configs/; fi",
            ""
        ]

        if use_docker:
            script.extend([
                "# 3. Docker Image Import (Air-Gap)",
                "echo '[3/6] Importing Docker Images...'",
                "if [ -d 'images' ]; then",
                "    for img in images/*.tar; do",
                "        echo \"Loading $img...\"",
                "        docker load -i \"$img\"",
                "    done",
                "fi",
                "",
                "# 4. Run Container",
                "echo '[4/6] Starting Service...'",
                "CONTAINER_NAME=llm-edge-node",
                "docker rm -f $CONTAINER_NAME || true",
                f"docker run -d --name $CONTAINER_NAME \\",
                "  --restart unless-stopped \\",
                "  --network host \\",
                f"  {docker_flags} \\",
                "  -v $(pwd)/data:/app/data \\",
                "  ghcr.io/llm-framework/inference-node:latest", 
                ""
            ])
        else:
            script.extend([
                "# 3. Native Setup",
                f"chmod +x {artifact_name}",
                "echo '[4/6] Native execution setup done.'",
                ""
            ])

        script.append("echo '[SUCCESS] Deployment finished.'")
        return "\n".join(script)

    # --- EXECUTION (Transfer & SSH) ---

    def check_connectivity(self, ip: str, port: int = 22) -> bool:
        try:
            with socket.create_connection((ip, port), timeout=2): return True
        except: return False

    def deploy_artifact(self, artifact_path: Path, target_ip: str, user: str, password: Optional[str] = None) -> bool:
        """Transferiert das ZIP und führt deploy.sh aus."""
        if not self.check_connectivity(target_ip):
            self.logger.error("Target not reachable.")
            return False

        target_dir = "/tmp/llm_deploy"
        success = False
        
        self.logger.info(f"Uploading to {target_ip}...")
        
        if PARAMIKO_AVAILABLE and password:
            success = self._deploy_via_paramiko(artifact_path, target_ip, user, password, target_dir)
        else:
            success = self._deploy_via_system_ssh(artifact_path, target_ip, user, target_dir)
            
        return success

    def execute_command(self, cmd: str, target_ip: str, user: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Führt Shell-Befehl auf Remote-Gerät aus."""
        if not self.check_connectivity(target_ip): return False, "Target unreachable"
        
        if PARAMIKO_AVAILABLE and password:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(target_ip, username=user, password=password, timeout=5)
                stdin, stdout, stderr = ssh.exec_command(cmd)
                return (stdout.channel.recv_exit_status() == 0, stdout.read().decode())
            except Exception as e: return False, str(e)
            finally: ssh.close()
        else:
            target = f"{user}@{target_ip}"
            res = subprocess.run(["ssh", target, cmd], capture_output=True, text=True)
            return (res.returncode == 0, res.stdout + res.stderr)

    def _deploy_via_paramiko(self, artifact: Path, ip: str, user: str, pw: str, target_dir: str) -> bool:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(ip, username=user, password=pw)
            sftp = ssh.open_sftp()
            try: sftp.mkdir(target_dir)
            except: pass
            
            remote = f"{target_dir}/{artifact.name}"
            sftp.put(str(artifact), remote)
            
            cmd = f"cd {target_dir} && unzip -o {artifact.name} && chmod +x deploy.sh && ./deploy.sh"
            stdin, stdout, stderr = ssh.exec_command(cmd)
            
            for line in stdout: self.logger.info(f"[REMOTE] {line.strip()}")
            return stdout.channel.recv_exit_status() == 0
        except Exception as e:
            self.logger.error(f"Paramiko error: {e}")
            return False
        finally: ssh.close()

    def _deploy_via_system_ssh(self, artifact: Path, ip: str, user: str, target_dir: str) -> bool:
        target = f"{user}@{ip}"
        try:
            subprocess.run(["ssh", target, f"mkdir -p {target_dir}"], check=True)
            subprocess.run(["scp", str(artifact), f"{target}:{target_dir}/"], check=True)
            cmd = f"cd {target_dir} && unzip -o {artifact.name} && chmod +x deploy.sh && ./deploy.sh"
            res = subprocess.run(["ssh", target, cmd], capture_output=True, text=True)
            self.logger.info(f"[REMOTE] {res.stdout}")
            return res.returncode == 0
        except Exception as e:
            self.logger.error(f"System SSH error: {e}")
            return False
