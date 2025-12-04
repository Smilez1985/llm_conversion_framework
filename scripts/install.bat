@echo off
setlocal EnableDelayedExpansion

:: ===================================================
:: LLM Conversion Framework - Installer Launcher
:: Startet die GUI-Installation (setup_windows.py)
:: ===================================================

:: 1. Admin-Rechte prüfen (Notwendig fuer den Python Installer)
openfiles >nul 2>&1
if %errorlevel% NEQ 0 (
    echo.
    echo [ACHTUNG] Bitte Rechtsklick auf die Datei und "Als Administrator ausfuehren".
    echo Das ist notwendig, damit der Installer Schreibrechte hat.
    echo.
    pause
    exit /b
)

:: 2. Pfade setzen (Root Verzeichnis)
pushd "%~dp0.."
set "REPO_DIR=%CD%"
popd
set "INSTALLER_VENV=%REPO_DIR%\.installer_venv"
set "SETUP_SCRIPT=%REPO_DIR%\scripts\setup_windows.py"

cls
echo ===================================================
echo      LLM Conversion Framework - Setup
echo ===================================================
echo.
echo [INFO] Framework Root: "%REPO_DIR%"
echo [INFO] Installer GUI:  "%SETUP_SCRIPT%"
echo.

:: 3. Python Check & Auto-Install (Winget Fallback)
echo [1/3] Pruefe Python Umgebung...
python --version >nul 2>&1
if !errorlevel! NEQ 0 (
    echo [WARNUNG] Python wurde nicht gefunden!
    set /p "INSTALL_PY=Soll Python 3.11 jetzt via Winget installiert werden? (j/n): "
    if /i "!INSTALL_PY!"=="j" (
        winget install -e --id Python.Python.3.11 --scope machine --accept-source-agreements --accept-package-agreements
        echo.
        echo [WICHTIG] Python wurde installiert. Bitte Skript NEU STARTEN.
        pause
        exit /b
    ) else (
        echo [FEHLER] Ohne Python kann der Installer nicht starten.
        pause
        exit /b
    )
)

:: 4. Installer-Umgebung vorbereiten (Vermeidet Dependency-Konflikte!)
:: Wir erstellen ein temporaeres VENV nur um den Installer zu starten.
echo.
echo [2/3] Bereite Installer-Umgebung vor...

if not exist "%INSTALLER_VENV%" (
    echo       Erstelle isolierte Umgebung...
    python -m venv "%INSTALLER_VENV%"
)

:: Installiere NUR die Pakete, die setup_windows.py braucht (psutil, requests, tk)
echo       Lade Hilfs-Pakete fuer den Installer...
"%INSTALLER_VENV%\Scripts\python.exe" -m pip install psutil requests >nul 2>&1

:: 5. GUI Installer starten
echo.
echo [3/3] Starte grafischen Installer...
echo.

if exist "%SETUP_SCRIPT%" (
    "%INSTALLER_VENV%\Scripts\python.exe" "%SETUP_SCRIPT%"
) else (
    echo [FEHLER] Konnte 'scripts\setup_windows.py' nicht finden!
    echo Pfad: %SETUP_SCRIPT%
    pause
    exit /b
)

:: Aufräumen (Optional: Wenn der Installer durch ist, schließt sich das Fenster)
echo.
echo Installer gestartet. Dieses Fenster kann geschlossen werden,
echo sobald die GUI erscheint.
echo.
pause
