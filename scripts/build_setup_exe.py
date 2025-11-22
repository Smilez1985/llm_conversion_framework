#!/usr/bin/env python3
"""
Build Config für den INSTALLER (Setup.exe)
DIREKTIVE: Goldstandard, Konfiguration für externes Build-Tool.
"""

import os
from pathlib import Path

# --- KONFIGURATION ---
APP_NAME = "Setup_LLM-Framework"
# Der Installer ist das Skript setup_windows.py
MAIN_SCRIPT = "scripts/setup_windows.py"
ICON_FILE = "assets/icon.ico" # Optional, falls vorhanden

# --- PYINSTALLER ARGUMENTE ---
PYINSTALLER_CMD_ARGS = [
    "--noconfirm",
    "--clean",
    "--windowed", # GUI-Modus (keine Konsole)
    f"--name={APP_NAME}",
    
    # Der Installer braucht 'requests' für den MSVC Download
    "--hidden-import", "requests",
    "--collect-all", "requests",
    
    # Der Installer braucht tkinter (meist automatisch, aber sicher ist sicher)
    "--hidden-import", "tkinter",
    
    # Icon (optional)
    # f"--icon={ICON_FILE}", # Einkommentieren wenn Icon existiert
    
    # WICHTIG: Der Installer braucht Admin-Rechte für Schreibzugriff auf Programme?
    # Nein, wir installieren ins User-Verzeichnis (AppData), daher --uac-admin NICHT zwingend,
    # aber für Docker-Checks manchmal hilfreich. Wir lassen es für User-Install weg.
    
    MAIN_SCRIPT
]
