def pull_docker_images_robust(self):
        """Pulls Docker images with Ping-Loop Pause"""
        # HIER: Wir fügen ctop und das Toolkit-Image hinzu
        images = [
            "debian:bookworm-slim",           # Base OS
            "quay.io/vektorlab/ctop:latest",  # Monitoring Tool
            "ghcr.io/llm-framework/rockchip:latest" # Optional: Falls wir pre-built Images hosten wollen
        ]
        
        for img in images:
            while True:
                if self.check_connectivity():
                    self.update_action(f"Pulling {img}...")
                    try:
                        # Versuch Pull
                        subprocess.run(["docker", "pull", img], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        break # Success
                    except subprocess.CalledProcessError:
                        # Image existiert vllt. noch nicht remote oder Fehler -> wir machen weiter
                        # (Bei ctop/debian ist das aber ein Fehler, daher retry)
                        self.update_action(f"Retrying {img}...")
                        time.sleep(2)
                else:
                    self.update_action("Network lost. Paused. Waiting for connection...")
                    time.sleep(2) # Wait and check ping again
        return True
