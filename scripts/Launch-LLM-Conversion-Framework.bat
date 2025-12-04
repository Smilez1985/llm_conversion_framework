@echo off
TITLE LLM Cross-Compiler Framework - Launcher
CLS
SETLOCAL ENABLEDELAYEDEXPANSION

:: --- KONFIGURATION ---
SET "CHECKFILE_DIR=C:\Users\Public\Documents\llm_conversion_framework"
SET "CHECKFILE=%CHECKFILE_DIR%\checkfile.txt"
SET "PYTHON_CMD=python"

:: --- 0. SELF-PATH ---
cd /d "%~dp0"
IF EXIST "..\orchestrator\main.py" (
    echo [INFO] Launcher im Unterordner. Wechsle zu Root
    cd ..
)

:: --- 1. SYSTEM-CHECK ---
echo [INIT] Pruefe Systemumgebung
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL] Python fehlt! Auto-Download
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

:: --- 2. CHECKFILE PRÜFUNG ---
IF EXIST "%CHECKFILE%" (
    FOR /F "usebackq tokens=1,* delims==" %%A IN ("%CHECKFILE%") DO (
        IF /I "%%A"=="Path" SET "INSTALL_PATH=%%B"
    )
    
    IF DEFINED INSTALL_PATH (
        set "INSTALL_PATH=!INSTALL_PATH:"=!"
        echo [INFO] Installation gefunden: "!INSTALL_PATH!"
        
        IF EXIST "!INSTALL_PATH!\orchestrator\main.py" (
            GOTO :LAUNCH_APP
        ) ELSE (
            echo [WARN] Pfad ungueltig. Starte Reparatur
        )
    )
)

:: --- 3. SETUP MODE ---
:RUN_SETUP
echo [SETUP] Starte Installer

python -c "import win32com.client, winshell" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [INSTALL] Installiere Hilfs-Pakete
    python -m pip install --upgrade pywin32 winshell requests >nul
)

python scripts\setup_windows.py

IF %ERRORLEVEL% EQU 0 (
    IF EXIST "%CHECKFILE%" (
        FOR /F "usebackq tokens=1,* delims==" %%A IN ("%CHECKFILE%") DO (
            IF /I "%%A"=="Path" SET "INSTALL_PATH=%%B"
        )
        if defined INSTALL_PATH set "INSTALL_PATH=!INSTALL_PATH:"=!"
        IF EXIST "!INSTALL_PATH!\orchestrator\main.py" GOTO :LAUNCH_APP
    )
)
echo [ERROR] Setup fehlgeschlagen.
PAUSE
EXIT /B

:: --- 4. LAUNCH APP ---
:LAUNCH_APP
pushd "!INSTALL_PATH!"
echo [BOOT] Starte Framework aus: %CD%

:: VENV aktivieren
IF EXIST ".venv\Scripts\activate.bat" (
    CALL ".venv\Scripts\activate.bat"
)

:: --- DEPENDENCY GUARD (SELF-HEALING) ---
echo [CHECK] Pruefe kritische Bibliotheken

:: 1. PyYAML Check
python -c "import yaml" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [MISSING] PyYAML fehlt. Installiere nach
    python -m pip install PyYAML
)

:: 2. PySide6 Check
python -c "import PySide6" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [MISSING] PySide6 fehlt. Installiere nach
    python -m pip install PySide6
)

:: 3. Docker Check
python -c "import docker" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [MISSING] Docker SDK fehlt. Installiere nach
    python -m pip install docker
)

:: 4. Requests/Psutil Check
python -c "import requests, psutil" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [MISSING] Utils fehlen. Installiere nach
    python -m pip install requests psutil
)

:: Start Main
echo [START] GUI wird geladen
python orchestrator\main.py

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CRASH] Anwendung unerwartet beendet (Code: %ERRORLEVEL%).
    PAUSE
)
popd
