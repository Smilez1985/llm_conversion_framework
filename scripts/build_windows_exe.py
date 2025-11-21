#!/usr/bin/env python3
"""
Windows Build Script für LLM Cross-Compiler Framework
DIREKTIVE: Goldstandard, erstellt eine Standalone .exe ohne Signierung.
ZWECK: Erstellt die ausführbare Datei für das GUI-Frontend.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
import logging

# Konfiguration
APP_NAME = "LLM-Builder"
MAIN_SCRIPT = "orchestrator/main.py"
ICON_FILE = "assets/icon.ico"  # Optional, falls vorhanden
DIST_DIR = "dist"
BUILD_DIR = "build"

# Logging-Setup: Schreibt Logs in den lokalen Ordner
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='build_log.txt', filemode='w')
logger = logging.getLogger(__name__)

def check_pyinstaller():
    """Prüft und installiert PyInstaller falls nötig"""
    try:
        import PyInstaller
        logger.info("PyInstaller ist installiert.")
    except ImportError:
        logger.info("Installiere PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def build_exe():
    """Erstellt die .exe mit PyInstaller"""
    logger.info("Starte Build-Prozess...")
    
    # Pfade, die PyInstaller nach versteckten Imports durchsuchen soll
    try:
        site_packages = subprocess.check_output([sys.executable, "-c", "import site; print(site.getsitepackages()[0])"]).decode().strip()
    except:
        site_packages = ""
    
    # Basis-Kommando
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",  # Keine Konsole für GUI (für den GUI-Launcher)
        "--name", APP_NAME,
        
        # WICHTIG: Explicit paths für PyInstaller in komplexen VENVs
        *([f"--paths={site_packages}"] if site_packages else []),

        # FIX: Hidden Import für yaml/PyYAML. Erzwingt das Bundling der C-Erweiterungen.
        "--hidden-import", "yaml", 
        "--hidden-import", "shutil",
        
        # FIX: Collect-All für kritische, oft fehlschlagende Module
        "--collect-all", "orchestrator", 
        "--collect-all", "PySide6",
        "--collect-all", "yaml",       
        "--collect-all", "requests",
        "--collect-all", "rich", 
        
        # Pfade zu Assets/Configs einbinden
        "--add-data", f"configs{os.pathsep}configs",
        "--add-data", f"targets{os.pathsep}targets",
        "--add-data", f"Docker Setup/docker-compose.yml{os.pathsep}.",
        
        # Entry Point
        MAIN_SCRIPT
    ]
    
    if os.path.exists(ICON_FILE):
        cmd.extend(["--icon", ICON_FILE])
        
    try:
        # Führt den PyInstaller-Befehl aus
        subprocess.check_call(cmd)
        logger.info(f"Build erfolgreich! Datei liegt in: {os.path.abspath(DIST_DIR)}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Build fehlgeschlagen mit Fehlercode {e.returncode}. Details im build_log.txt.")
        sys.exit(1)


if __name__ == "__main__":
    # Root-Verzeichnis prüfen
    if not Path("orchestrator").exists():
        logger.error("Bitte führen Sie das Skript aus dem Root-Verzeichnis des Repositories aus.")
        sys.exit(1)
        
    check_pyinstaller()
    build_exe()
    
    # ACHTUNG: Die Signierung wird hier absichtlich NICHT durchgeführt,
    # um sie Ihrem externen Programm zu überlassen.
    logger.info("Build-Skript abgeschlossen. Führen Sie nun Ihr Signierungsprogramm aus.")
