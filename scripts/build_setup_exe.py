#!/usr/bin/env python3
"""
Build Config für den INSTALLER (Setup.exe)
DIREKTIVE: Goldstandard, Konfiguration für externes Build-Tool.
ZWECK: Definiert die Argumente für den Bau des Installers via PyInstaller.
"""

import os
from pathlib import Path

# --- KONFIGURATION ---
APP_NAME = "Setup_LLM-Framework"
# Der Entry-Point für den Installer
MAIN_SCRIPT = "scripts/setup_windows.py"
ICON_FILE = "assets/icon.ico" # Optional, falls vorhanden

# --- PYINSTALLER ARGUMENTE ---
# Ihr externes Programm liest diese Liste aus und übergibt sie an PyInstaller
PYINSTALLER_CMD_ARGS = [
    "--noconfirm",
    "--clean",
    "--windowed", # GUI-Modus (keine Konsole)
    f"--name={APP_NAME}",
    
    # WICHTIG: Der Installer braucht 'requests' für den MSVC Download
    "--hidden-import", "requests",
    "--collect-all", "requests",
    
    # Der Installer braucht tkinter (meist automatisch, aber sicher ist sicher)
    "--hidden-import", "tkinter",
    
    # Optional: Icon einbinden
    # f"--icon={ICON_FILE}", 
    
    # Admin-Rechte (UAC) anfordern?
    # "--uac-admin",  # Einkommentieren, falls Schreibrechte in C:\Program Files benötigt werden
    
    # Das Hauptskript (Muss das letzte Argument sein)
    MAIN_SCRIPT
]
