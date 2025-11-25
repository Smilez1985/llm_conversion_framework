#!/usr/bin/env python3
"""
Update Manager - Secure Process Launch
"""
import sys
import subprocess
import logging
from pathlib import Path
import tempfile

class UpdateManager:
    def __init__(self, app_root: Path):
        self.app_root = app_root
        self.logger = logging.getLogger(__name__)
        self.CRITICAL_FILES = ["scripts/setup_windows.py", "pyproject.toml"]

    def check_for_updates(self) -> bool:
        try:
            git_dir = self.app_root / ".git"
            if not git_dir.exists(): return False
            
            # Security Fix: shell=False, list args
            subprocess.run(["git", "fetch"], cwd=self.app_root, check=True, capture_output=True)
            res = subprocess.run(["git", "status", "-uno"], cwd=self.app_root, capture_output=True, text=True)
            return "Your branch is behind" in res.stdout
        except: return False

    def _is_major_update(self):
        try:
            res = subprocess.run(["git", "diff", "--name-only", "HEAD", "@{u}"], cwd=self.app_root, capture_output=True, text=True)
            return any(f in res.stdout for f in self.CRITICAL_FILES)
        except: return True

    def perform_update_and_restart(self):
        try:
            major = self._is_major_update()
            exe_name = "LLM-Builder.exe"
            setup_name = "Setup_LLM-Framework.exe"
            is_frozen = getattr(sys, 'frozen', False)
            
            batch_file = Path(tempfile.gettempdir()) / "llm_updater.bat"
            
            if major:
                self.logger.info("Major Update erkannt -> Starte Installer")
                next_step_cmd = f'start "" "{setup_name}" --update'
            else:
                self.logger.info("Minor Update erkannt -> Restart")
                if is_frozen:
                    next_step_cmd = f'start "" "{exe_name}"'
                else:
                    script_path = Path(sys.argv[0])
                    next_step_cmd = f'python "{script_path}"'

            with open(batch_file, "w") as f:
                f.write(f'@echo off\ncd /d "{self.app_root}"\ngit pull\n{next_step_cmd}\ndel "%~f0"\nexit\n')
            
            self.logger.info(f"Update-Skript erstellt: {batch_file}")
            
            # SECURITY FIX: Secure launch without shell=True
            if sys.platform == "win32":
                subprocess.Popen(["cmd.exe", "/c", str(batch_file)], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                # Linux fallback
                subprocess.Popen(["/bin/bash", "-c", f"cd {self.app_root} && git pull && ./llm-builder"])
                
            sys.exit(0)
        except Exception as e:
            self.logger.error(f"Update failed: {e}")
            raise e
