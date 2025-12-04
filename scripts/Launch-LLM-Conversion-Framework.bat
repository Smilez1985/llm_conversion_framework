@echo off
TITLE LLM Cross-Compiler Framework - Launcher
CLS
SETLOCAL ENABLEDELAYEDEXPANSION

:: --- 0. ADMIN CHECK & AUTO-ELEVATION ---
fsutil dirty query %systemdrive% >nul
IF %ERRORLEVEL% NEQ 0 (
    echo [INFO] Keine Admin-Rechte. Fordere an...
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B
)

:: --- 1. PFAD-NORMALISIERUNG ---
cd /d "%~dp0"
IF EXIST "..\orchestrator\main.py" (
    echo [INFO] Launcher im Unterordner. Wechsle zu Root...
    cd ..
)
SET "ROOT_DIR=%CD%"

:: --- KONFIGURATION ---
SET "CHECKFILE_DIR=C:\Users\Public\Documents\llm_conversion_framework"
SET "CHECKFILE=%CHECKFILE_DIR%\checkfile.txt"
SET "PYTHON_CMD=python"

:: --- 2. SYSTEM-CHECK ---
echo [INIT] Pruefe Systemumgebung (Admin-Mode)...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL] Python fehlt! Auto-Download...
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

:: --- 3. CHECKFILE PRÜFUNG ---
IF EXIST "%CHECKFILE%" (
    FOR /F "usebackq tokens=1,* delims==" %%A IN ("%CHECKFILE%") DO (
        IF /I "%%A"=="Path" SET "INSTALL_PATH=%%B"
    )
    
    IF DEFINED INSTALL_PATH (
        echo [INFO] Installation gefunden: "!INSTALL_PATH!"
        
        IF EXIST "!INSTALL_PATH!\orchestrator\main.py" (
            GOTO :LAUNCH_APP
        ) ELSE (
            echo [WARN] Pfad aus Checkfile ist ungueltig.
            echo [INFO] Starte Reparatur...
        )
    )
)

:: --- 4. SETUP MODE ---
:RUN_SETUP
echo [SETUP] Starte Installer...

:: Installer-Dependencies (Minimal)
python -c "import win32com.client, winshell" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [INSTALL] Installiere Hilfs-Pakete (pywin32, winshell)...
    python -m pip install --upgrade pywin32 winshell requests psutil >nul
)

:: Starte GUI Installer
python "%ROOT_DIR%\scripts\setup_windows.py"

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

:: --- 5. LAUNCH APP ---
:LAUNCH_APP
pushd "!INSTALL_PATH!"
echo [BOOT] Starte Framework aus: %CD%

:: Update Check
git --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    git pull >nul 2>&1
)

:: VENV nutzen
IF EXIST ".venv\Scripts\activate.bat" (
    CALL ".venv\Scripts\activate.bat"
)

python orchestrator\main.py
IF %ERRORLEVEL% NEQ 0 PAUSE
popd
