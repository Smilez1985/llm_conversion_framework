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

# Bestimme den Pfadtrenner (z.B. ';' unter Windows, ':' unter Linux)
PATH_SEP = os.pathsep 
SITE_PACKAGES_PATH = "" 

# --- BUILD ARGUMENTE (Für die externe PyInstaller-Ausführung) ---
# HINWEIS: Das externe Programm MUSS 'PyInstaller' aus dem Root-Verzeichnis
# des Repositories ausführen, um die relativen Pfade (configs, targets etc.) korrekt aufzulösen.

PYINSTALLER_CMD_ARGS: List[str] = [
    # Allgemeine Optionen
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", APP_NAME,
    
    # FIX: Hidden Import für yaml/PyYAML. Dies zwingt PyInstaller, alle C-Komponenten zu bündeln.
    "--hidden-import", "yaml", 
    "--hidden-import", "shutil", # Hilft beim Einbinden von OS-Helfern

    # FIX: Collect-All für kritische, oft fehlschlagende Module
    "--collect-all", "orchestrator", 
    "--collect-all", "PySide6",
    "--collect-all", "yaml",       
    "--collect-all", "requests",
    "--collect-all", "rich", 
    
    # Data Files (Verwendet PATH_SEP als Trenner, um Cross-Plattform-Daten zu bündeln)
    "--add-data", f"configs{PATH_SEP}configs",
    "--add-data", f"targets{PATH_SEP}targets",
    "--add-data", f"Docker Setup/docker-compose.yml{PATH_SEP}.",
    
    # Optional: Icon
    # Der externe Prozess muss prüfen, ob die Datei existiert, bevor er diese Zeilen anhängt.
    # *([f"--icon={ICON_FILE}"] if Path(ICON_FILE).exists() else []),
    
    # Main Script (MUSS die letzte Position einnehmen)
    MAIN_SCRIPT
]

# --- Build Metadaten (für die Logik des externen Programms) ---
BUILD_METADATA: Dict[str, Any] = {
    "APP_NAME": APP_NAME,
    "ENTRY_POINT": MAIN_SCRIPT,
    "OUTPUT_FILE": Path("dist") / f"{APP_NAME}.exe",
    "REQUIRES_EXECUTION_FROM_ROOT": True,
    "ICON_FILE": ICON_FILE,
    "DEPENDENCY_HINT": "ModuleNotFoundError: No module named 'yaml' is fixed by '--hidden-import yaml'"
}
