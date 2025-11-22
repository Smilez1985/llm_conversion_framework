#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Application Entry Point
DIREKTIVE: Goldstandard.
           Nur noch Bootstrap-Logik. GUI ist ausgelagert.
"""

import sys
import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import QApplication

# Import der ausgelagerten GUI-Klasse
from orchestrator.gui.main_window import MainOrchestrator

# ============================================================================
# STARTUP LOGIC
# ============================================================================

def find_repo_root() -> Path:
    """Findet das Root-Verzeichnis (Entwicklung oder Frozen EXE)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def run_startup_git_pull(base_dir: Path):
    """Silent Git Pull beim Start (Best Effort)."""
    if not (base_dir / ".git").exists():
        return
    try:
        subprocess.run(
            ["git", "pull"], cwd=base_dir, capture_output=True, timeout=5,
            creationflags=0x08000000 if sys.platform == 'win32' else 0
        )
    except Exception:
        pass

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # 1. Pfade bestimmen
    BASE_DIR = find_repo_root()
    
    # 2. Arbeitsverzeichnis setzen (Wichtig für relative Pfade in Configs)
    try:
        os.chdir(BASE_DIR)
    except Exception as e:
        print(f"CRITICAL: Failed to set CWD to {BASE_DIR}: {e}")
        sys.exit(1)

    # 3. Silent Update Check
    run_startup_git_pull(BASE_DIR)

    # 4. App Starten
    app = QApplication(sys.argv)
    
    # GUI initialisieren und Root-Pfad übergeben
    window = MainOrchestrator(app_root=BASE_DIR)
    window.show()
    
    sys.exit(app.exec())
