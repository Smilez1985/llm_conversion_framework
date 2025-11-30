#!/usr/bin/env python3
"""
Build Config für den INSTALLER (Setup.exe)
DIREKTIVE: Goldstandard. Konfiguration + Builder in einem.
ZWECK: Definiert PYINSTALLER_CMD_ARGS für den Bau des Installers (Single File).
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Any

# --- KONFIGURATION ---
APP_NAME = "Setup_LLM-Framework"
MAIN_SCRIPT = "scripts/setup_windows.py"
# Wir suchen das Icon erst im Root, dann in assets
ICON_CANDIDATES = ["assets/icon.ico", "LLM-Builder.ico"]
ICON_FILE = None

# Pfade auflösen
REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
WORK_DIR = REPO_ROOT / "build"

# Icon finden
for candidate in ICON_CANDIDATES:
    icon_path = REPO_ROOT / candidate
    if icon_path.exists():
        ICON_FILE = str(icon_path)
        break

# --- PYINSTALLER ARGUMENTE ---

def get_pyinstaller_args() -> List[str]:
    args = [
        "--noconfirm",
        "--clean",
        "--onefile",   # WICHTIG: Erzwingt Einzeldatei
        "--windowed",  # GUI-Modus (keine Konsole für den Installer selbst)
        f"--name={APP_NAME}",
        f"--distpath={str(DIST_DIR)}",
        f"--workpath={str(WORK_DIR)}",
        
        # Dependencies für den Installer
        "--hidden-import", "requests",
        "--collect-all", "requests",
        "--hidden-import", "tkinter",
        
        # Admin-Rechte anfordern (Standard für Setup-Programme)
        "--uac-admin",
    ]

    # Icon (falls gefunden)
    if ICON_FILE:
        args.append(f"--icon={ICON_FILE}")
    
    # Main Script (Absolut)
    args.append(str(REPO_ROOT / MAIN_SCRIPT))
    
    return args

# Globale Variable für externe Tools
PYINSTALLER_CMD_ARGS = get_pyinstaller_args()

# --- Build Metadaten ---
BUILD_METADATA: Dict[str, Any] = {
    "APP_NAME": APP_NAME,
    "ENTRY_POINT": MAIN_SCRIPT,
    "OUTPUT_FILE": DIST_DIR / f"{APP_NAME}.exe",
    "REQUIRES_EXECUTION_FROM_ROOT": True
}

# --- MAIN EXECUTION (Selbstausführung) ---
if __name__ == "__main__":
    print(f"🚀 Starting Build for {APP_NAME}...")
    print(f"📂 Root: {REPO_ROOT}")
    
    os.chdir(REPO_ROOT)
    
    if ICON_FILE:
        print(f"✅ Icon found: {ICON_FILE}")
    
    cmd = [sys.executable, "-m", "PyInstaller"] + get_pyinstaller_args()
    
    try:
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW
            
        print("🔨 Running PyInstaller...")
        subprocess.run(cmd, check=True, creationflags=flags)
        
        print(f"\n🎉 Build SUCCESSFUL!")
        print(f"📁 Output: {DIST_DIR / f'{APP_NAME}.exe'}")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build FAILED with exit code {e.returncode}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        sys.exit(1)
