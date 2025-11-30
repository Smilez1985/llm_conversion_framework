#!/usr/bin/env python3
"""
Windows Build Script für LLM Cross-Compiler Framework
DIREKTIVE: Goldstandard, definiert die PyInstaller-Argumente für ein externes Programm.
ZWECK: Stellt die Liste der Argumente für den Build des GUI-Launchers bereit.
"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# --- KONFIGURATION ---
APP_NAME = "LLM-Builder"
MAIN_SCRIPT = "orchestrator/main.py"
ICON_FILE = "assets/icon.ico" 

# Pfadtrenner (Windows = ;)
PATH_SEP = os.pathsep 

# --- BUILD ARGUMENTE ---
# Diese Liste wird vom ExeBuilder Framework geladen.
PYINSTALLER_CMD_ARGS: List[str] = [
    # WICHTIG: --onefile erzwingt eine einzelne EXE (löst den "Datei fehlt" Fehler)
    "--onefile",
    "--windowed",  # Kein Konsolenfenster beim Start der fertigen App
    "--noconfirm",
    "--clean",
    "--name", APP_NAME,
    
    # FIX: Hidden Imports für kritische Module
    "--hidden-import", "yaml", 
    "--hidden-import", "shutil",
    "--hidden-import", "win32api",
    "--hidden-import", "win32con",

    # FIX: Collect-All für komplexe Pakete
    "--collect-all", "orchestrator", 
    "--collect-all", "PySide6",
    "--collect-all", "yaml",       
    "--collect-all", "requests",
    "--collect-all", "rich", 
    
    # Data Files (Ordner und Configs einpacken)
    # Syntax: "Quellpfad;Zielpfad" (für Windows)
    f"--add-data=configs{PATH_SEP}configs",
    f"--add-data=targets{PATH_SEP}targets",
    f"--add-data=Docker Setup/docker-compose.yml{PATH_SEP}.",
    
    # Icon
    f"--icon={ICON_FILE}",
    
    # Das Hauptskript muss immer am Ende stehen
    MAIN_SCRIPT
]

# --- Build Metadaten (Optional für Übersicht) ---
BUILD_METADATA: Dict[str, Any] = {
    "APP_NAME": APP_NAME,
    "ENTRY_POINT": MAIN_SCRIPT,
    "OUTPUT_FILE": Path("dist") / f"{APP_NAME}.exe",
    "REQUIRES_EXECUTION_FROM_ROOT": True
}

# --- Selbst-Test (Optional: Wenn man das Skript direkt ausführt) ---
if __name__ == "__main__":
    print("Diese Datei ist eine Konfiguration für das ExeBuilder Framework.")
    print("Bitte ziehen Sie diese Datei in die GUI des Builders.")
