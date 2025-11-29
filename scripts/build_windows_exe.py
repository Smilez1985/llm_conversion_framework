#!/usr/bin/env python3
"""
Windows Build Script für LLM Cross-Compiler Framework (Main App)
DIREKTIVE: Goldstandard. Konfiguration + Builder in einem.
ZWECK: 
1. Definiert PYINSTALLER_CMD_ARGS für externe Frameworks.
2. Führt den Build direkt aus, wenn das Skript gestartet wird.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Any

# --- KONFIGURATION ---
APP_NAME = "LLM-Builder"
MAIN_SCRIPT = "orchestrator/main.py"
# Wir suchen das Icon erst im Root, dann in assets
ICON_CANDIDATES = ["LLM-Builder.ico", "assets/icon.ico"]
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

# Platform Separator
PATH_SEP = os.pathsep 
SITE_PACKAGES_PATH = "" # Optional: Pfad zu venv site-packages erzwingen

# Definitive Liste der PyYAML-Untermodule (Fix für Hidden Import Errors)
PYYAML_DEEP_IMPORTS = [
    'yaml.loader', 'yaml.dumper', 'yaml.scanner', 'yaml.parser',
    'yaml.composer', 'yaml.constructor', 'yaml.resolver',
    'yaml.representer', 'yaml.emitter', 'yaml.serializer',
]

# --- PYINSTALLER ARGUMENTE (Die Definition) ---
# Diese Liste wird generiert, damit sie sowohl hier als auch extern genutzt werden kann.

def get_pyinstaller_args() -> List[str]:
    args = [
        "--noconfirm",
        "--clean",
        "--windowed",  # GUI Modus (keine Konsole)
        f"--name={APP_NAME}",
        f"--distpath={DIST_DIR}",
        f"--workpath={WORK_DIR}",
        
        # WICHTIG: Fix für PyYAML C-Bindings und fehlende Module
        "--hidden-import", "yaml", 
        "--hidden-import", "shutil",
        "--hidden-import", "huggingface_hub",
        "--hidden-import", "tqdm",
        "--hidden-import", "psutil",
        "--hidden-import", "requests",
        "--hidden-import", "PySide6",
        
        # Collect All (Sichert Daten und Binaries der Pakete)
        "--collect-all", "huggingface_hub", 
        "--collect-all", "tqdm",
        "--collect-all", "orchestrator", 
        "--collect-all", "PySide6",
        "--collect-all", "yaml",       
        "--collect-all", "requests",
        "--collect-all", "rich", 
        
        # Data Files (Wichtig: Pfadtrenner beachten!)
        # Syntax: "Quelle;Ziel" (Windows)
        f"--add-data=configs{PATH_SEP}configs",
        f"--add-data=targets{PATH_SEP}targets",
        f"--add-data=Docker Setup/docker-compose.yml{PATH_SEP}.",
    ]

    # Deep Imports
    for module in PYYAML_DEEP_IMPORTS:
        args.extend(["--hidden-import", module])
        
    # Icon (falls gefunden)
    if ICON_FILE:
        args.append(f"--icon={ICON_FILE}")
    
    # Main Script (Muss am Ende stehen)
    args.append(str(REPO_ROOT / MAIN_SCRIPT))
    
    return args

# Globale Variable für externe Tools (Kompatibilität)
PYINSTALLER_CMD_ARGS = get_pyinstaller_args()

# --- MAIN EXECUTION (Selbstausführung) ---
if __name__ == "__main__":
    print(f"🚀 Starting Build for {APP_NAME}...")
    print(f"📂 Root: {REPO_ROOT}")
    
    # Arbeitsverzeichnis wechseln
    os.chdir(REPO_ROOT)
    
    # Icon Status
    if ICON_FILE:
        print(f"✅ Icon found: {ICON_FILE}")
    else:
        print("⚠️  No icon found. Using default.")

    # PyInstaller aufrufen
    cmd = [sys.executable, "-m", "PyInstaller"] + get_pyinstaller_args()
    
    try:
        # Creationflags unterdrücken Konsolenfenster beim Spawn neuer Prozesse (nur Windows)
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
