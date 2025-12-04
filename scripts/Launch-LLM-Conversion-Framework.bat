@echo off
TITLE LLM Cross-Compiler Framework - Launcher
CLS
SETLOCAL ENABLEDELAYEDEXPANSION

:: --- KONFIGURATION ---
:: ZENTRALER PFAD für die Checkfile (Wie angefordert)
SET "CHECKFILE_DIR=C:\Users\Public\Documents\llm_conversion_framework"
SET "CHECKFILE=%CHECKFILE_DIR%\checkfile.txt"
SET "PYTHON_CMD=python"

:: --- 0. SELF-PATH ---
cd /d "%~dp0"
IF EXIST "..\orchestrator\main.py" (
    echo [INFO] Launcher im Unterordner. Wechsle zu Root
    cd ..
)
SET "SOURCE_ROOT=%CD%"

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
    :: Lese Pfad aus Datei
    FOR /F "usebackq tokens=1,* delims==" %%A IN ("%CHECKFILE%") DO (
        IF /I "%%A"=="Path" SET "INSTALL_PATH=%%B"
    )
    
    :: Trimmen (Sicherheitsmaßnahme)
    IF DEFINED INSTALL_PATH (
        echo [INFO] Installation gefunden: "!INSTALL_PATH!"
        
        IF EXIST "!INSTALL_PATH!\orchestrator\main.py" (
            GOTO :LAUNCH_APP
        ) ELSE (
            echo [WARN] Pfad aus Checkfile ist ungueltig oder App wurde verschoben.
            echo [INFO] Starte Reparatur/Neu-Installation
        )
    )
)

:: --- 3. SETUP MODE (Wenn Checkfile fehlt oder ungültig) ---
:RUN_SETUP
echo [SETUP] Starte Installer

:: Installer-Dependencies (Minimal)
python -c "import win32com.client, winshell" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [INSTALL] Installiere Hilfs-Pakete (pywin32, winshell)
    python -m pip install --upgrade pywin32 winshell requests >nul
)

:: Starte GUI Installer
python "%SOURCE_ROOT%\scripts\setup_windows.py"

IF %ERRORLEVEL% EQU 0 (
    :: Re-Check nach erfolgreichem Installer
    IF EXIST "%CHECKFILE%" (
        FOR /F "usebackq tokens=1,* delims==" %%A IN ("%CHECKFILE%") DO (
            IF /I "%%A"=="Path" SET "INSTALL_PATH=%%B"
        )
        IF EXIST "!INSTALL_PATH!\orchestrator\main.py" GOTO :LAUNCH_APP
    )
)

echo [ERROR] Setup fehlgeschlagen oder abgebrochen.
PAUSE
EXIT /B

:: --- 4. LAUNCH APP ---
:LAUNCH_APP
:: Wechsel in das Installationsverzeichnis (WICHTIG für relative Pfade im Code)
pushd "!INSTALL_PATH!"
echo [BOOT] Starte Framework aus: %CD%

:: Update Check (Nur wenn git verfügbar)
git --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    git pull >nul 2>&1
)

:: VENV nutzen (Falls vorhanden)
IF EXIST ".venv\Scripts\activate.bat" (
    CALL ".venv\Scripts\activate.bat"
)

:: Start
python orchestrator\main.py
IF %ERRORLEVEL% NEQ 0 PAUSE
popd
