#!/usr/bin/env python3
"""
Update Manager for LLM Cross-Compiler Framework
DIREKTIVE: Goldstandard.
           1. Smart Update Detection (Git Diff Analysis).
           2. Unterscheidet zwischen Minor (File-Swap) und Major (Installer nötig) Updates.
           3. Generiert dynamisches Batch-Skript für nahtlosen Übergang.
"""

import sys
import subprocess
import logging
from pathlib import Path
import tempfile
import time

class UpdateManager:
    """
    Verwaltet Self-Updates.
    Analysiert Änderungen und entscheidet über die Update-Strategie.
    """
    def __init__(self, app_root: Path):
        self.app_root = app_root
        self.logger = logging.getLogger(__name__)
        
        # Kritische Dateien, die eine Neu-Installation (Installer-Lauf) erfordern
        self.CRITICAL_FILES = [
            "scripts/setup_windows.py",
            "Docker Setup/docker-compose.yml",
            "Docker Setup/pyproject.toml",
            "pyproject.toml",
            "requirements.txt"
        ]

    def check_for_updates(self) -> bool:
        """Prüft via git fetch, ob Updates verfügbar sind."""
        try:
            git_dir = self.app_root / ".git"
            if not git_dir.exists():
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

    def _is_major_update(self) -> bool:
        """
        Analysiert die anstehenden Änderungen.
        Returns: True, wenn kritische Systemdateien geändert wurden (Installer nötig).
        """
        try:
            # Prüfe welche Dateien sich zwischen HEAD und Upstream geändert haben
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD", "@{u}"],
                cwd=self.app_root,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
            )
            
            changed_files = result.stdout.splitlines()
            self.logger.info(f"Geänderte Dateien: {changed_files}")

            for file in changed_files:
                # Check 1: Explizite kritische Dateien
                if file in self.CRITICAL_FILES:
                    self.logger.info(f"Major Update ausgelöst durch: {file}")
                    return True
                
                # Check 2: Änderungen an Installer-Skripten
                if file.startswith("scripts/") and "setup" in file:
                    self.logger.info(f"Major Update ausgelöst durch Installer-Skript: {file}")
                    return True

            return False

        except Exception as e:
            self.logger.warning(f"Konnte Update-Typ nicht bestimmen, erzwinge sicherheitshalber Major Update: {e}")
            return True

    def perform_update_and_restart(self):
        """
        Führt das Update durch.
        Entscheidet intelligent, ob der Installer (Setup.exe) gestartet werden muss.
        """
        try:
            # Wir nehmen an, die EXE heißt 'LLM-Builder.exe' und der Installer 'Setup_LLM-Framework.exe'
            exe_name = "LLM-Builder.exe"
            setup_name = "Setup_LLM-Framework_v1.exe" # Oder wie Ihre Setup-EXE heißt
            
            # Fallback für Dev-Mode
            is_frozen = getattr(sys, 'frozen', False)
            
            # Prüfe auf Major Update
            major_update = self._is_major_update()
            
            # Temporäres Batch-Skript erstellen
            batch_file = Path(tempfile.gettempdir()) / "llm_updater.bat"
            
            # Batch-Logik dynamisch aufbauen
            if major_update:
                self.logger.info("Major Update erkannt -> Starte Installer nach Download")
                # Strategie: Git Pull -> Setup.exe im Update-Modus starten -> Setup startet App neu
                next_step_cmd = f'start "" "{setup_name}" --update'
            else:
                self.logger.info("Minor Update erkannt -> Direkter Neustart")
                # Strategie: Git Pull -> App direkt neu starten
                if is_frozen:
                    next_step_cmd = f'start "" "{exe_name}"'
                else:
                    # Dev Modus
                    script_path = Path(sys.argv[0])
                    next_step_cmd = f'python "{script_path}"'

            batch_content = f"""
@echo off
title LLM-Builder Smart Updater
echo Warte auf Beendigung der Anwendung...
timeout /t 3 /nobreak > NUL
cd /d "{self.app_root}"

echo.
echo ------------------------------------------------
echo Fuehre Git Pull durch...
echo ------------------------------------------------
git pull

echo.
echo ------------------------------------------------
echo Starte Folgesprozess...
echo Modus: {"MAJOR (Installer)" if major_update else "MINOR (Direct Start)"}
echo ------------------------------------------------
{next_step_cmd}

del "%~f0"
exit
            """
            
            with open(batch_file, "w") as f:
                f.write(batch_content)
            
            self.logger.info(f"Update-Skript erstellt: {batch_file}")
            
            # Starte das Batch-Skript detached
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
