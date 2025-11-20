#!/usr/bin/env python3
"""
Helper script to build the 'Thin Client' launcher EXE using PyInstaller.
Does NOT bundle targets/docker folders. They must exist next to the EXE at runtime.
"""

import os
import sys
import subprocess
from pathlib import Path

# Konfiguration
APP_NAME = "LLM-Builder"
MAIN_SCRIPT = Path("orchestrator/main.py")
ICON_FILE = Path("LLM-Builder.ico") # Icon muss im Repo-Root liegen
DIST_DIR = Path("dist")
WORK_DIR = Path("build")

def build_exe():
    # Zum Repo-Root wechseln
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    if not MAIN_SCRIPT.exists():
        print(f"Error: Main script not found at {MAIN_SCRIPT}")
        sys.exit(1)

    print(f"Building Thin Client EXE for {APP_NAME}...")

    # PyInstaller Befehl zusammenbauen
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        f"--name={APP_NAME}",
        f"--distpath={DIST_DIR}",
        f"--workpath={WORK_DIR}",
        str(MAIN_SCRIPT)
    ]

    # Icon hinzufügen falls vorhanden
    if ICON_FILE.exists():
        cmd.append(f"--icon={ICON_FILE}")
        print(f"Using icon: {ICON_FILE}")
    else:
        print("Warning: No icon file found. Building with default icon.")

    try:
        # Ausführen
        subprocess.run(cmd, check=True)
        print(f"\n✅ Build successful!")
        print(f"Launcher EXE is at: {DIST_DIR / f'{APP_NAME}.exe'}")
        print("Next step: Run 'python scripts/setup_windows.py' to test the installer.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed with error code {e.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
