@echo off
setlocal EnableDelayedExpansion

:: ===================================================
:: LLM Conversion Framework - Installer Launcher
:: ===================================================

:: 1. Admin-Rechte prüfen
openfiles >nul 2>&1
if %errorlevel% NEQ 0 (
    echo.
    echo [ACHTUNG] Bitte Rechtsklick auf die Datei und "Als Administrator ausfuehren".
    echo.
    pause
    exit /b
)

:: 2. Pfade setzen
pushd "%~dp0.."
set "REPO_DIR=%CD%"
popd
set "INSTALLER_VENV=%REPO_DIR%\.installer_venv"
set "SETUP_SCRIPT=%REPO_DIR%\scripts\setup_windows.py"

:: WICHTIG: Pointer File Pfad (Sichtbar lassen!)
set "GLOBAL_DATA_DIR=C:\Users\Public\Documents\llm_conversion_framework"

cls
echo ===================================================
echo      LLM Conversion Framework - Setup
echo ===================================================
echo.
echo [INFO] Framework Root: "%REPO_DIR%"
echo [INFO] Global Data:    "%GLOBAL_DATA_DIR%"
echo.

:: 3. Python Check & Bootstrapping
echo [1/3] Pruefe Python Umgebung...
python --version >nul 2>&1
if !errorlevel! NEQ 0 (
    echo [WARNUNG] Python fehlt. Versuche Installation via Winget...
    winget install -e --id Python.Python.3.11 --scope machine --accept-source-agreements --accept-package-agreements
    if !errorlevel! NEQ 0 (
        echo [FEHLER] Python Installation fehlgeschlagen.
        pause
        exit /b
    )
    echo [INFO] Python installiert. Bitte Skript neu starten!
    pause
    exit /b
)

:: 4. Installer-Umgebung (Mini-VENV für Setup)
echo.
echo [2/3] Bereite Installer-Umgebung vor...
if not exist "%INSTALLER_VENV%" (
    python -m venv "%INSTALLER_VENV%"
)
:: Installiere Abhängigkeiten für das GUI-Skript (pywin32 für Shortcuts!)
"%INSTALLER_VENV%\Scripts\python.exe" -m pip install psutil requests pywin32 winshell >nul 2>&1

:: 5. GUI Installer starten
echo.
echo [3/3] Starte grafischen Installer...
if exist "%SETUP_SCRIPT%" (
    "%INSTALLER_VENV%\Scripts\python.exe" "%SETUP_SCRIPT%"
) else (
    echo [FEHLER] setup_windows.py nicht gefunden in:
    echo %SETUP_SCRIPT%
    pause
)
