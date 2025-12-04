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

IF NOT EXIST "orchestrator\main.py" (
    echo [CRITICAL] Falsches Verzeichnis! 'orchestrator\main.py' nicht gefunden.
    PAUSE
    EXIT /B 1
)

:: --- KONFIGURATION ---
SET "VENV_DIR=.venv"
SET "MARKER_FILE=.install_complete"
SET "INSTALLER_SCRIPT=scripts\setup_windows.py"
SET "MAIN_SCRIPT=orchestrator\main.py"
SET "PYTHON_CMD=python"

:: --- 1. PYTHON CHECK ---
echo [INIT] System-Check...
%PYTHON_CMD% --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL] Python fehlt!
    echo Starten Sie das Skript nach der Installation von Python 3.10+ erneut.
    PAUSE
    EXIT /B 1
)

:: --- 2. SETUP (Wenn Marker fehlt) ---
IF NOT EXIST "%MARKER_FILE%" (
    echo [SETUP] Ersteinrichtung...
    
    :: VENV erstellen
    IF NOT EXIST "%VENV_DIR%" (
        echo [INFO] Erstelle VENV...
        %PYTHON_CMD% -m venv %VENV_DIR%
    )
    
    :: Aktivieren
    CALL %VENV_DIR%\Scripts\activate
    
    :: Pip Upgrade
    python -m pip install --upgrade pip
    
    :: Abhängigkeiten installieren (Mit Ping Loop)
    CALL :INSTALL_DEPS
    
    :: GUI Installer (Shortcuts etc.)
    python %INSTALLER_SCRIPT%
    
    echo Installed > "%MARKER_FILE%"
) ELSE (
    :: Aktivieren für Run
    CALL %VENV_DIR%\Scripts\activate
)

:: --- 3. DEPENDENCY GUARD (Der Fix) ---
:: Wir prüfen explizit, ob die GUI-Lib da ist. Wenn nicht: Nachinstallieren!
python -c "import PySide6" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [WARNUNG] PySide6 fehlt oder Umgebung defekt.
    echo [AUTO-FIX] Starte Reparatur...
    CALL :INSTALL_DEPS
)

:: --- 4. START ---
echo [BOOT] Starte Framework...
python %MAIN_SCRIPT%

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CRASH] Anwendung mit Fehlercode %ERRORLEVEL% beendet.
    echo Bitte pr?fen Sie die Ausgabe oben.
    PAUSE
)

GOTO :EOF

:: ====================================================
:: FUNKTION: INSTALL_DEPS (Mit Ping Loop & Fallback)
:: ====================================================
:INSTALL_DEPS
    echo [NET] Pruefe Verbindung...
    :PING_LOOP
    ping -n 1 8.8.8.8 >nul 2>&1
    IF %ERRORLEVEL% NEQ 0 (
        echo [WAIT] Kein Internet. Warte auf Verbindung...
        timeout /t 2 >nul
        GOTO :PING_LOOP
    )
    
    echo [INSTALL] Installiere Bibliotheken...
    
    :: Strategie 1: PyProject (Best Practice)
    if exist "pyproject.toml" (
        echo   - Methode: pyproject.toml
        pip install -e .
        IF !ERRORLEVEL! EQU 0 GOTO :EOF
    )
    
    :: Strategie 2: Requirements (Fallback)
    if exist "requirements.txt" (
        echo   - Methode: requirements.txt
        pip install -r requirements.txt
        IF !ERRORLEVEL! EQU 0 GOTO :EOF
    )
    
    :: Strategie 3: Manuell (Notfall)
    echo   - Methode: Manueller Fallback
    echo [WARNUNG] Keine Config gefunden. Installiere Kern-Pakete manuell...
    pip install PySide6 docker pyyaml requests psutil cryptography
    
    IF !ERRORLEVEL! NEQ 0 (
        echo [ERROR] Installation fehlgeschlagen!
        PAUSE
        EXIT /B 1
    )
    GOTO :EOF
