#!/usr/bin/env python3
import subprocess
import logging

class DeploymentManager:
    def deploy_artifact(self, artifact_path, target_ip, user, target_path="/tmp"):
        """Deploys an artifact via SCP and runs setup via SSH."""
        try:
            # 1. SCP
            scp_cmd = ["scp", str(artifact_path), f"{user}@{target_ip}:{target_path}"]
            subprocess.run(scp_cmd, check=True)
            
            # 2. SSH Extract & Run
            filename = artifact_path.name
            ssh_cmd = [
                "ssh", f"{user}@{target_ip}",
                f"cd {target_path} && unzip -o {filename} && chmod +x deploy.sh && ./deploy.sh"
            ]
            subprocess.run(ssh_cmd, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Deployment failed: {e}")
            return False
