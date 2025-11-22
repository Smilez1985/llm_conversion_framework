#!/usr/bin/env python3
"""
Update Manager for LLM Cross-Compiler Framework
DIREKTIVE: Goldstandard, führt sichere Updates via Git und Batch-Restart durch.
"""

import sys
import subprocess
import logging
from pathlib import Path
import tempfile
import time

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
                # Dies ist kein Fehler, sondern der Normalzustand bei einer frischen Installation
                # bevor das erste Update-Repo gecloned wurde (falls wir .git im Installer ausschließen würden)
                # Da wir .git jetzt inkludieren, sollte es da sein.
                self.logger.warning(f"Kein Git-Repo gefunden in {self.app_root}. Auto-Update deaktiviert.")
                return False

            # Fetch origin (ohne Konsole unter Windows)
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
            # Falls wir im Dev-Modus sind (python main.py), starten wir python neu
            is_frozen = getattr(sys, 'frozen', False)
            
            if is_frozen:
                exe_path = Path(sys.executable)
                restart_cmd = f'start "" "{exe_path.name}"'
            else:
                # Dev Modus: Python Neustart
                exe_path = Path(sys.executable)
                script_path = Path(sys.argv[0])
                restart_cmd = f'start "" "{exe_path}" "{script_path}"'
            
            # Temporäres Batch-Skript erstellen
            batch_file = Path(tempfile.gettempdir()) / "llm_updater.bat"
            
            batch_content = f"""
@echo off
title LLM-Builder Updater
echo Warte auf Beendigung der Anwendung...
timeout /t 3 /nobreak > NUL
cd /d "{self.app_root}"
echo.
echo ------------------------------------------------
echo Fuehre Update durch (git pull)...
echo ------------------------------------------------
git pull
echo.
echo ------------------------------------------------
echo Starte Anwendung neu...
echo ------------------------------------------------
{restart_cmd}
del "%~f0"
exit
            """
            
            with open(batch_file, "w") as f:
                f.write(batch_content)
            
            self.logger.info(f"Update-Skript erstellt: {batch_file}")
            
            # Starte das Batch-Skript detached (in neuer Konsole, damit User sieht was passiert)
            subprocess.Popen(
                [str(batch_file)], 
                shell=True, 
                cwd=self.app_root,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            # Beende DIESE Anwendung sofort
            sys.exit(0)
            
        except Exception as e:
            self.logger.error(f"Update-Start fehlgeschlagen: {e}")
            raise e
