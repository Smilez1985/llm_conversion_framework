@echo off
TITLE LLM Cross-Compiler Framework - Launcher
CLS
SETLOCAL ENABLEDELAYEDEXPANSION

:: --- 0. PFAD-NORMALISIERUNG ---
cd /d "%~dp0"
IF EXIST "..\orchestrator\main.py" (
    echo [INFO] Launcher im Unterordner. Wechsle zu Root...
    cd ..
)

:: --- KONFIGURATION ---
SET "VENV_DIR=.venv"
SET "MARKER_FILE=.install_complete"
SET "INSTALLER_SCRIPT=scripts\setup_windows.py"
SET "PYTHON_CMD=python"

:: --- 1. PYTHON CHECK ---
echo [INIT] System-Check...
%PYTHON_CMD% --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL] Python fehlt!
    echo Bitte installieren Sie Python 3.10+ und fuegen Sie es dem PATH hinzu.
    PAUSE
    EXIT /B 1
)

:: --- 2. CHECK: BEREITS INSTALLIERT? ---
IF EXIST "%MARKER_FILE%" (
    :: Lese den Installationspfad aus der Datei
    set /p INSTALL_PATH=<"%MARKER_FILE%"
    
    :: Entferne Anführungszeichen und Leerzeichen
    set "INSTALL_PATH=!INSTALL_PATH:"=!"
    
    echo [INFO] Installation gefunden in: "!INSTALL_PATH!"
    
    IF EXIST "!INSTALL_PATH!\orchestrator\main.py" (
        GOTO :START_INSTALLED_APP
    ) ELSE (
        echo [WARNUNG] Installationspfad ungueltig oder geloescht.
        echo [REPAIR] Starte Neu-Installation...
        del "%MARKER_FILE%"
        GOTO :RUN_INSTALLER
    )
) ELSE (
    GOTO :RUN_INSTALLER
)

:RUN_INSTALLER
echo.
echo [SETUP] Starte Installer-GUI...
echo.

:: 1. VENV erstellen (lokal für den Installer)
IF NOT EXIST "%VENV_DIR%" (
    echo [INFO] Erstelle temporaere Umgebung...
    %PYTHON_CMD% -m venv %VENV_DIR%
)
CALL %VENV_DIR%\Scripts\activate

:: 2. Minimal-Dependencies für den Installer (tkinter ist stdlib, aber requests brauchen wir evtl.)
echo [INFO] Bereite Installer vor...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install requests >nul 2>&1

:: 3. GUI Starten
python %INSTALLER_SCRIPT%

IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Installation abgebrochen oder fehlgeschlagen.
    PAUSE
    EXIT /B 1
)

:: Check ob Marker jetzt da ist (vom Python Script erstellt)
IF EXIST "%MARKER_FILE%" (
    echo [SUCCESS] Setup abgeschlossen!
    GOTO :START_APP_AFTER_INSTALL
) ELSE (
    echo [ERROR] Installer hat keinen Pfad hinterlegt.
    PAUSE
    EXIT /B 1
)

:START_INSTALLED_APP
:: Wechsel in das Installationsverzeichnis
pushd "!INSTALL_PATH!"

:START_APP_AFTER_INSTALL
echo [BOOT] Starte Framework...

:: Wir nutzen das VENV der INSTALLATION (nicht des Launchers), falls vorhanden
IF EXIST ".venv\Scripts\activate.bat" (
    CALL ".venv\Scripts\activate.bat"
)

:: Start
python orchestrator\main.py

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CRASH] Anwendung beendet.
    echo.
    :: Falls wir im pushd sind, zurück
    popd 2>nul
    PAUSE
)

GOTO :EOF
