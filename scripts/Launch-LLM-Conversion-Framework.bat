@echo off
TITLE LLM Cross-Compiler Framework - Launcher
CLS
SETLOCAL ENABLEDELAYEDEXPANSION

:: --- CONFIG ---
SET "REG_KEY=HKCU\Software\Smilez1985\LLM-Framework"
SET "REG_VAL=InstallPath"
SET "PYTHON_CMD=python"

:: --- 0. PFAD-NORMALISIERUNG ---
cd /d "%~dp0"
IF EXIST "..\orchestrator\main.py" (
    echo [INFO] Launcher im Unterordner. Wechsle zu Root...
    cd ..
)

:: --- 1. CHECK REGISTRY (Installiert?) ---
FOR /F "tokens=2*" %%A IN ('REG QUERY "%REG_KEY%" /v "%REG_VAL%" 2^>nul') DO SET "INSTALL_PATH=%%B"

IF DEFINED INSTALL_PATH (
    IF EXIST "%INSTALL_PATH%\orchestrator\main.py" (
        GOTO :LAUNCH_APP
    ) ELSE (
        echo [WARN] Pfad in Registry ungueltig. Starte Setup...
    )
)

:: --- 2. SETUP MODE ---
:RUN_SETUP
echo [INIT] System-Check...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL] Python fehlt. Auto-Download...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'"
    start /wait python_installer.exe /passive PrependPath=1
    del python_installer.exe
    
    python --version >nul 2>&1
    IF !ERRORLEVEL! NEQ 0 (
        echo [ERROR] Python Installation fehlgeschlagen.
        PAUSE
        EXIT /B 1
    )
)

:: Dependencies für Installer (LOUD MODE)
echo [SETUP] Pruefe Installer-Dependencies (pywin32, winshell)...
python -c "import win32com.client, winshell, requests" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [INSTALL] Installiere fehlende Pakete...
    python -m pip install --upgrade pywin32 winshell requests
    
    :: Re-Check
    python -c "import win32com.client" >nul 2>&1
    IF !ERRORLEVEL! NEQ 0 (
        echo [ERROR] Konnte pywin32 nicht installieren. Shortcuts werden nicht funktionieren.
        echo Versuchen Sie, den Launcher als Administrator zu starten.
        PAUSE
    )
)

echo [SETUP] Starte GUI...
python scripts\setup_windows.py

IF %ERRORLEVEL% EQU 0 (
    :: Nach erfolgreichem Setup nochmal prüfen
    FOR /F "tokens=2*" %%A IN ('REG QUERY "%REG_KEY%" /v "%REG_VAL%" 2^>nul') DO SET "INSTALL_PATH=%%B"
    IF DEFINED INSTALL_PATH GOTO :LAUNCH_APP
)
echo [ERROR] Setup nicht erfolgreich abgeschlossen.
PAUSE
EXIT /B

:: --- 3. LAUNCH APP ---
:LAUNCH_APP
pushd "%INSTALL_PATH%"
echo [BOOT] Starte Framework aus: %CD%

:: Update Check
git pull >nul 2>&1

:: VENV nutzen
IF EXIST ".venv\Scripts\activate.bat" (
    CALL ".venv\Scripts\activate.bat"
)

python orchestrator\main.py
IF %ERRORLEVEL% NEQ 0 PAUSE
popd
