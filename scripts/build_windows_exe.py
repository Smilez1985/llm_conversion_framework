#!/usr/bin/env python3
"""
Windows Build Script für LLM Cross-Compiler Framework
DIREKTIVE: Erstellt eine Standalone .exe und signiert sie (Self-Signed).
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
    
    # Basis-Kommando
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",  # Keine Konsole für GUI
        "--name", APP_NAME,
        "--collect-all", "orchestrator", # Wichtig für relative Imports
        "--collect-all", "PySide6",
        
        # Pfade zu Assets/Configs einbinden
        "--add-data", f"configs{os.pathsep}configs",
        "--add-data", f"targets{os.pathsep}targets",
        "--add-data", f"Docker Setup/docker-compose.yml{os.pathsep}.",
        
        # Entry Point
        MAIN_SCRIPT
    ]
    
    if os.path.exists(ICON_FILE):
        cmd.extend(["--icon", ICON_FILE])
        
    subprocess.check_call(cmd)
    logger.info(f"Build erfolgreich! Datei liegt in: {os.path.abspath(DIST_DIR)}")

def self_sign_exe():
    """Erstellt ein Zertifikat und signiert die EXE (Nur Windows)"""
    if sys.platform != "win32":
        logger.warning("Signierung übersprungen (Nur auf Windows möglich).")
        return

    exe_path = Path(DIST_DIR) / f"{APP_NAME}.exe"
    if not exe_path.exists():
        logger.error("EXE nicht gefunden, Signierung abgebrochen.")
        return

    logger.info("Beginne Self-Signing Prozess (PowerShell)...")
    
    # PowerShell-Skript zum Erstellen und Signieren
    ps_script = f"""
    $certName = "LLM-Framework-SelfSigned"
    $exePath = "{exe_path.absolute()}"
    
    Write-Host "Suche existierendes Zertifikat..."
    $cert = Get-ChildItem Cert:\\CurrentUser\\My | Where-Object {{ $_.Subject -match $certName }} | Select-Object -First 1
    
    if (-not $cert) {{
        Write-Host "Erstelle neues Code-Signing Zertifikat..."
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=$certName" -CertStoreLocation Cert:\\CurrentUser\\My
        Write-Host "Zertifikat erstellt: $($cert.Thumbprint)"
    }} else {{
        Write-Host "Zertifikat gefunden: $($cert.Thumbprint)"
    }}
    
    Write-Host "Signiere EXE..."
    Set-AuthenticodeSignature -FilePath $exePath -Certificate $cert
    
    Write-Host "Signierung abgeschlossen."
    """
    
    # PowerShell ausführen
    try:
        subprocess.run(["powershell", "-Command", ps_script], check=True)
        logger.info("✅ EXE erfolgreich signiert!")
        logger.info("HINWEIS: Damit Windows der EXE vertraut, muss das Zertifikat auf dem Ziel-PC in 'Vertrauenswürdige Stammzertifizierungsstellen' importiert werden.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Signierung fehlgeschlagen: {e}")

if __name__ == "__main__":
    # Root-Verzeichnis prüfen
    if not Path("orchestrator").exists():
        logger.error("Bitte führen Sie das Skript aus dem Root-Verzeichnis des Repositories aus.")
        sys.exit(1)
        
    check_pyinstaller()
    build_exe()
    self_sign_exe()
