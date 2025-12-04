@echo off
TITLE LLM Cross-Compiler Framework - Launcher
CLS
SETLOCAL ENABLEDELAYEDEXPANSION

:: --- KONFIGURATION ---
SET "VENV_DIR=.venv"
SET "MARKER_FILE=.install_complete"
SET "INSTALLER_SCRIPT=setup_windows.py"
SET "MAIN_SCRIPT=orchestrator\main.py"

:: --- 1. UMWELT PRÜFEN (Goldstandard) ---
echo [INIT] Pruefe Systemumgebung...

:: Check: Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL] Python nicht gefunden!
    echo.
    echo Das Framework benoetigt Python 3.10+.
    echo Versuche automatischen Download des Python-Installers...
    
    :: Download Python Installer via Powershell (Secure)
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'"
    
    IF EXIST "python_installer.exe" (
        echo [INFO] Starte Python Installation...
        echo BITTE WAEHLEN SIE: "Add Python to PATH" im Installer!
        start /wait python_installer.exe /passive PrependPath=1
        del python_installer.exe
        
        :: Re-Check nach Installation
        python --version >nul 2>&1
        IF !ERRORLEVEL! NEQ 0 (
            echo [ERROR] Python Installation fehlgeschlagen oder PATH nicht aktualisiert.
            echo Bitte starten Sie diesen Launcher nach einem Neustart erneut.
            PAUSE
            EXIT /B 1
        )
    ) ELSE (
        echo [ERROR] Download fehlgeschlagen. Bitte installieren Sie Python manuell.
        PAUSE
        EXIT /B 1
    )
)

:: Check: Git
git --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL] Git nicht gefunden!
    echo.
    echo Versuche automatischen Download von Git...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe' -OutFile 'git_installer.exe'"
    
    IF EXIST "git_installer.exe" (
        echo [INFO] Starte Git Installation...
        start /wait git_installer.exe /VERYSILENT /NORESTART
        del git_installer.exe
    ) ELSE (
        echo [WARNUNG] Git Download fehlgeschlagen. Auto-Updates werden nicht funktionieren.
    )
)

:: --- 2. INSTALLATIONS-CHECK ---
IF EXIST "%MARKER_FILE%" (
    GOTO :START_APP
)

:RUN_INSTALLER
echo.
echo [SETUP] Starte GUI-Installer...
echo Dies richtet Dependencies ein, laedt MSVC Runtimes und erstellt Shortcuts.
echo.

:: Aufruf des existierenden Python-Installers (setup_windows.py)
python %INSTALLER_SCRIPT%

:: Prüfen, ob der Python-Installer erfolgreich war
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Der Installer meldete einen Fehler.
    PAUSE
    EXIT /B 1
)

:: Marker setzen (falls das Python script es nicht tut)
echo Installed > "%MARKER_FILE%"
echo [SUCCESS] Installation abgeschlossen.
echo.

:START_APP
echo [UPDATE] Pruefe auf Updates...
git pull >nul 2>&1

echo [BOOT] Starte Framework...
:: Virtuelle Umgebung nutzen, falls vom Installer angelegt
IF EXIST "%VENV_DIR%\Scripts\activate.bat" (
    CALL "%VENV_DIR%\Scripts\activate.bat"
)

:: Abhängigkeiten sicherstellen (falls Update neue braucht)
pip install -r requirements.txt >nul 2>&1

python %MAIN_SCRIPT%

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CRASH] Anwendung unerwartet beendet.
    PAUSE
)
