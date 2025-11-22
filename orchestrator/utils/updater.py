import os
import sys
import subprocess
import logging
from pathlib import Path
import tempfile

class UpdateManager:
    """
    Manages self-updates for the LLM-Builder.
    Uses a temporary batch script to replace the running executable.
    """
    def __init__(self, app_root: Path):
        self.app_root = app_root
        self.logger = logging.getLogger(__name__)

    def check_for_updates(self) -> bool:
        """Prüft via git fetch, ob Updates verfügbar sind."""
        try:
            git_dir = self.app_root / ".git"
            if not git_dir.exists():
                self.logger.warning(f"Kein Git-Repo gefunden in {self.app_root}. Auto-Update deaktiviert.")
                return False

            # Fetch origin
            subprocess.run(
                ["git", "fetch"], 
                cwd=self.app_root, 
                check=True, 
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
            )
            
            # Checkstatus: HEAD vs @{u} (Upstream)
            result = subprocess.run(
                ["git", "status", "-uno"], 
                cwd=self.app_root, 
                capture_output=True, 
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
            )
            
            if "Your branch is behind" in result.stdout:
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Update-Check fehlgeschlagen: {e}")
            return False

    def perform_update_and_restart(self):
        """Erstellt ein Batch-Skript, das die App schließt, git pull ausführt und neu startet."""
        try:
            # Wir nehmen an, die EXE heißt 'LLM-Builder.exe'
            exe_name = "LLM-Builder.exe"
            exe_path = self.app_root / exe_name
            
            # Temporäres Batch-Skript erstellen
            batch_file = Path(tempfile.gettempdir()) / "llm_updater.bat"
            
            # Batch-Logik:
            # 1. Warte 2 Sekunden (damit sich die GUI schließen kann)
            # 2. Gehe ins App-Verzeichnis
            # 3. Führe git pull aus (überschreibt auch die EXE, da sie dann nicht mehr läuft!)
            # 4. Starte die EXE neu
            # 5. Lösche das Batch-Skript
            
            batch_content = f"""
@echo off
timeout /t 2 /nobreak > NUL
cd /d "{self.app_root}"
echo Updating Repository...
git pull
echo Starting Application...
start "" "{exe_name}"
del "%~f0"
            """
            
            with open(batch_file, "w") as f:
                f.write(batch_content)
            
            self.logger.info(f"Update-Skript erstellt: {batch_file}")
            
            # Starte das Batch-Skript detached (in neuer Konsole, damit User sieht was passiert)
            subprocess.Popen(
                [str(batch_file)], 
                shell=True, 
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            # Beende DIESE Anwendung sofort
            sys.exit(0)
            
        except Exception as e:
            self.logger.error(f"Update-Start fehlgeschlagen: {e}")
            raise e
