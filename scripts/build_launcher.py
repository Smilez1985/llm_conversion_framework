#!/usr/bin/env python3
"""
Helper script to build the 'Thin Client' launcher EXE using PyInstaller.
Does NOT bundle targets/docker folders. They must exist next to the EXE at runtime.
Key Fix: Ensures arguments (like --icon) come BEFORE the script path.
"""

import os
import sys
import subprocess
from pathlib import Path

# Konfiguration
APP_NAME = "LLM-Builder"
MAIN_SCRIPT = Path("orchestrator/main.py")
# Das Icon muss direkt im Hauptordner des Repos liegen (neben README.md)
ICON_FILE = Path("LLM-Builder.ico") 
DIST_DIR = Path("dist")
WORK_DIR = Path("build")

def build_exe():
    # 1. Zum Repo-Root wechseln, damit relative Pfade stimmen
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)
    print(f"Working directory set to: {repo_root}")

    # Checks
    if not MAIN_SCRIPT.exists():
        print(f"Error: Main script not found at {MAIN_SCRIPT}")
        sys.exit(1)

    print(f"Building Thin Client EXE for {APP_NAME}...")

    # 2. PyInstaller Befehl zusammenbauen (Basis-Optionen)
    # WICHTIG: Das Skript selbst kommt erst ganz am Ende dazu!
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed", # Kein Konsolenfenster
        f"--name={APP_NAME}",
        f"--distpath={DIST_DIR}",
        f"--workpath={WORK_DIR}",
    ]

    # 3. Icon hinzufügen (MUSS VOR DEM SKRIPT KOMMEN)
    if ICON_FILE.exists() and ICON_FILE.is_file():
        # Wir nutzen str(ICON_FILE) um sicherzugehen
        cmd.append(f"--icon={str(ICON_FILE)}")
        print(f"✅ Found icon. Using: {ICON_FILE}")
    else:
        print(f"⚠️ Warning: Icon file not found at '{ICON_FILE.absolute()}'.")
        print("Building with default PyInstaller icon.")

    # 4. Das Hauptskript MUSS das letzte Argument sein
    cmd.append(str(MAIN_SCRIPT))

    # Debug: Befehl anzeigen
    # print(f"Executing command: {' '.join(cmd)}")

    try:
        # Ausführen
        # creationflags verhindern kurzes Aufblitzen einer Konsole beim Build-Start unter Windows
        subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        print(f"\n🎉 Build successful!")
        print(f"Launcher EXE is ready at: {DIST_DIR / f'{APP_NAME}.exe'}")
        print("(Please check if it has the correct icon now)")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed with error code {e.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
