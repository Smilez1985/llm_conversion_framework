#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Deployment Manager (v2.3 Multi-Container)
DIREKTIVE: Goldstandard Deployment.

Features:
- Package Generation with Multi-Container Support (Inference + Qdrant).
- Air-Gap Image Export.
- Config Sync.
"""

import os
import time
import socket
import logging
import subprocess
import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, List, Dict

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

import docker
from orchestrator.utils.logging import get_logger

class DeploymentManager:
    def __init__(self, framework_manager=None):
        self.logger = get_logger(__name__)
        self.framework = framework_manager

    # --- PACKAGE GENERATION ---

    def create_deployment_package(self, artifact_path: Path, profile_name: str, docker_config: Dict, output_dir: Path) -> Optional[Path]:
        artifact_path = Path(artifact_path)
        if not artifact_path.exists(): return None

        # Hardware Flags
        target_mgr = self.framework.get_component("target_manager")
        docker_flags = []
        if target_mgr and profile_name:
            docker_flags = target_mgr.get_docker_flags_for_profile(profile_name)
        flags_str = " ".join(docker_flags)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # A. Copy Artifact
            shutil.copy2(artifact_path, temp_path / artifact_path.name)
            
            # B. Configs
            self._bundle_user_configs(temp_path / "data" / "configs")

            # C. Docker Images (Multi-Container Support)
            use_docker = docker_config.get("use_docker", False)
            if use_docker:
                # Wir brauchen Inference Node UND Qdrant
                images = ["ghcr.io/llm-framework/inference-node:latest"]
                # Optional Qdrant if RAG is enabled in request or config
                if self.framework.config.enable_rag_knowledge:
                    images.append("qdrant/qdrant:latest")
                
                self._export_docker_images(images, temp_path / "images")

            # D. Script Generation (Deploy + Compose)
            script_content = self._generate_deploy_script(artifact_path.name, flags_str, use_docker)
            
            with open(temp_path / "deploy.sh", "w", newline='\n') as f:
                f.write(script_content)
            os.chmod(temp_path / "deploy.sh", 0o755)

            # E. Checksums & Zip
            self._generate_checksums(temp_path, temp_path / "checksums.sha256")
            
            pkg_name = f"deploy_{artifact_path.stem}_{int(time.time())}.zip"
            pkg_path = output_dir / pkg_name
            
            with zipfile.ZipFile(pkg_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(temp_path):
                    for file in files:
                        p = Path(root) / file
                        zipf.write(p, p.relative_to(temp_path))
            
            return pkg_path

    def _bundle_user_configs(self, dest_dir: Path):
        src_dir = Path(self.framework.config.configs_dir)
        for folder in ["user_profiles", "voice_templates", "prompts"]:
            src = src_dir / folder
            if src.exists(): shutil.copytree(src, dest_dir / folder, dirs_exist_ok=True)

    def _export_docker_images(self, images: List[str], dest_dir: Path):
        dest_dir.mkdir(parents=True, exist_ok=True)
        client = self.framework.get_component("docker_client")
        if not client: return

        for img_name in images:
            sanitized = img_name.replace("/", "_").replace(":", "_")
            tar_path = dest_dir / f"{sanitized}.tar"
            self.logger.info(f"Exporting {img_name}...")
            try:
                try: client.images.pull(img_name)
                except: pass
                img = client.images.get(img_name)
                with open(tar_path, "wb") as f:
                    for chunk in img.save(named=True): f.write(chunk)
            except Exception as e:
                self.logger.error(f"Export failed for {img_name}: {e}")

    def _generate_checksums(self, directory: Path, output_file: Path):
        with open(output_file, "w") as f:
            for root, _, files in os.walk(directory):
                for file in files:
                    p = Path(root) / file
                    if p.name == output_file.name: continue
                    sha = hashlib.sha256()
                    with open(p, "rb") as f_in:
                        for chunk in iter(lambda: f_in.read(4096), b""): sha.update(chunk)
                    f.write(f"{sha.hexdigest()}  {p.relative_to(directory)}\n")

    def _generate_deploy_script(self, artifact, flags, use_docker) -> str:
        script = [
            "#!/bin/bash",
            "set -e",
            "echo '[1/5] Checking Integrity...'",
            "sha256sum -c checksums.sha256",
            ""
        ]
        
        if use_docker:
            # Multi-Container Logic
            script.extend([
                "echo '[2/5] Loading Images...'",
                "for img in images/*.tar; do docker load -i \"$img\"; done",
                "",
                "echo '[3/5] Starting Stack (Inference + Qdrant)...'",
                "# Create Network",
                "docker network create llm-net || true",
                "",
                "# 1. Qdrant Sidecar",
                "docker run -d --name qdrant-sidecar \\",
                "  --network llm-net \\",
                "  -v $(pwd)/data/qdrant:/qdrant/storage \\",
                "  --restart unless-stopped \\",
                "  qdrant/qdrant:latest",
                "",
                "# 2. Inference Node (with Hardware Access)",
                f"docker run -d --name llm-node \\",
                "  --network llm-net \\",
                f"  {flags} \\", # Hardware Flags here!
                "  -e QDRANT_HOST=qdrant-sidecar \\",
                "  -v $(pwd)/data:/app/data \\",
                "  --restart unless-stopped \\",
                "  ghcr.io/llm-framework/inference-node:latest",
                ""
            ])
        else:
            script.append(f"chmod +x {artifact} && ./{artifact}")

        script.append("echo 'Deployment Complete.'")
        return "\n".join(script)

    # --- EXECUTION ---
    def deploy_artifact(self, artifact_path: Path, target_ip: str, user: str, password: Optional[str] = None) -> bool:
        if not self._check_conn(target_ip): return False
        
        target_dir = "/tmp/llm_deploy"
        self.logger.info(f"Deploying to {target_ip}...")
        
        if PARAMIKO_AVAILABLE and password:
            return self._deploy_paramiko(artifact_path, target_ip, user, password, target_dir)
        return self._deploy_system(artifact_path, target_ip, user, target_dir)

    def _check_conn(self, ip, port=22):
        try:
            socket.create_connection((ip, port), timeout=2)
            return True
        except: return False

    def _deploy_paramiko(self, artifact, ip, user, pw, target_dir):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(ip, username=user, password=pw)
            sftp = ssh.open_sftp()
            try: sftp.mkdir(target_dir)
            except: pass
            sftp.put(str(artifact), f"{target_dir}/{artifact.name}")
            
            cmd = f"cd {target_dir} && unzip -o {artifact.name} && chmod +x deploy.sh && ./deploy.sh"
            stdin, stdout, stderr = ssh.exec_command(cmd)
            for line in stdout: self.logger.info(f"[REMOTE] {line.strip()}")
            return stdout.channel.recv_exit_status() == 0
        finally: ssh.close()

    def _deploy_system(self, artifact, ip, user, target_dir):
        target = f"{user}@{ip}"
        subprocess.run(["ssh", target, f"mkdir -p {target_dir}"], check=True)
        subprocess.run(["scp", str(artifact), f"{target}:{target_dir}/"], check=True)
        cmd = f"cd {target_dir} && unzip -o {artifact.name} && chmod +x deploy.sh && ./deploy.sh"
        res = subprocess.run(["ssh", target, cmd], capture_output=True, text=True)
        self.logger.info(res.stdout)
        return res.returncode == 0
