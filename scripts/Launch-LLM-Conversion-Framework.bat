@echo off
TITLE LLM Cross-Compiler Framework - Launcher
CLS
SETLOCAL ENABLEDELAYEDEXPANSION

:: --- 0. INTELLIGENTE PFAD-ERKENNUNG ---
:: Wo bin ich?
SET "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Check 1: Bin ich schon im Root? (Existiert orchestrator hier?)
IF EXIST "orchestrator\main.py" (
    SET "ROOT_DIR=%SCRIPT_DIR%"
    echo [INFO] Launcher im Root-Verzeichnis erkannt.
) ELSE (
    :: Check 2: Bin ich im 'scripts' Ordner? (Existiert orchestrator eins drueber?)
    IF EXIST "..\orchestrator\main.py" (
        SET "ROOT_DIR=%SCRIPT_DIR%..\"
        cd /d "%ROOT_DIR%"
        echo [INFO] Launcher im Scripts-Ordner erkannt. Wechsle zu Root...
    ) ELSE (
        echo [CRITICAL] Konnte Projekt-Struktur nicht erkennen!
        echo.
        echo Bitte stellen Sie sicher, dass der Ordner 'orchestrator' existiert
        echo und sich entweder im selben Verzeichnis oder einen Ordner darueber befindet.
        echo.
        echo Aktueller Pfad: %CD%
        PAUSE
        EXIT /B 1
    )
)

:: Ab hier sind wir garantiert im Root-Verzeichnis.
:: Alle Pfade koennen nun relativ vom Root angegeben werden.

:: --- KONFIGURATION ---
SET "VENV_DIR=.venv"
SET "MARKER_FILE=.install_complete"
SET "INSTALLER_SCRIPT=scripts\setup_windows.py"
SET "MAIN_SCRIPT=orchestrator\main.py"

:: --- 1. UMWELT PRÜFEN ---
echo [INIT] Pruefe Systemumgebung...

:: Check: Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL] Python nicht gefunden!
    echo Versuche automatischen Download...
    
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile 'python_installer.exe'"
    
    IF EXIST "python_installer.exe" (
        echo [INFO] Starte Python Installation...
        echo BITTE WAEHLEN SIE: "Add Python to PATH" im Installer!
        start /wait python_installer.exe /passive PrependPath=1
        del python_installer.exe
        
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
    echo Versuche automatischen Download...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe' -OutFile 'git_installer.exe'"
    
    IF EXIST "git_installer.exe" (
        echo [INFO] Starte Git Installation...
        start /wait git_installer.exe /VERYSILENT /NORESTART
        del git_installer.exe
    ) ELSE (
        echo [WARNUNG] Git Download fehlgeschlagen. Auto-Updates deaktiviert.
    )
)

:: --- 2. INSTALLATIONS-CHECK ---
IF EXIST "%MARKER_FILE%" (
    GOTO :START_APP
)

:RUN_INSTALLER
echo.
echo [SETUP] Starte GUI-Installer (Ersteinrichtung)...
echo.

:: Aufruf des Python-Installers
python %INSTALLER_SCRIPT%

IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Der Installer meldete einen Fehler.
    PAUSE
    EXIT /B 1
)

echo Installed > "%MARKER_FILE%"
echo [SUCCESS] Installation abgeschlossen.
echo.

:START_APP
echo [UPDATE] Pruefe auf Updates...
git pull >nul 2>&1

echo [BOOT] Starte Framework...

:: Virtuelle Umgebung aktivieren (falls vorhanden)
IF EXIST "%VENV_DIR%\Scripts\activate.bat" (
    CALL "%VENV_DIR%\Scripts\activate.bat"
)

:: Dependencies sicherstellen (Quiet Mode)
pip install -r requirements.txt >nul 2>&1

:: Hauptanwendung starten
python %MAIN_SCRIPT%

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CRASH] Anwendung unerwartet beendet.
    echo Pfad war: %CD%
    PAUSE
)
