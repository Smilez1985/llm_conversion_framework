@echo off
setlocal EnableDelayedExpansion

:: ===================================================
:: LLM Conversion Framework - Smart Installer
:: ===================================================

:: 1. Admin-Rechte prüfen
openfiles >nul 2>&1
if %errorlevel% NEQ 0 (
    echo.
    echo [ACHTUNG] Bitte Rechtsklick auf die Datei und "Als Administrator ausfuehren".
    echo Das ist notwendig fuer Installation und System-Updates.
    echo.
    pause
    exit /b
)

:: 2. Pfade bestimmen
pushd "%~dp0.."
set "REPO_DIR=%CD%"
popd
set "GLOBAL_CONFIG_DIR=C:\Users\Public\Documents\llm_conversion_framework"
set "CHECKFILE=%GLOBAL_CONFIG_DIR%\checkfile.txt"

cls
echo ===================================================
echo      LLM Conversion Framework - Installation
echo ===================================================
echo.
echo [INFO] Framework Root: "%REPO_DIR%"
echo.

:: 3. Python Check & Auto-Install
echo [1/4] Pruefe Python Installation...
python --version >nul 2>&1
if !errorlevel! NEQ 0 (
    echo [WARNUNG] Python wurde nicht gefunden!
    echo.
    set /p "INSTALL_PY=Soll Python 3.11 jetzt via Winget installiert werden? (j/n): "
    
    if /i "!INSTALL_PY!"=="j" (
        echo [INFO] Starte Winget Installation...
        winget install -e --id Python.Python.3.11 --scope machine --accept-source-agreements --accept-package-agreements
        
        echo.
        echo [WICHTIG] Python wurde installiert.
        echo Damit die Pfade aktualisiert werden, muss dieses Skript NEU GESTARTET werden.
        echo Bitte druecke eine Taste, um zu beenden, und starte die install.bat erneut.
        pause
        exit /b
    ) else (
        echo [FEHLER] Ohne Python kann die Installation nicht fortgesetzt werden.
        pause
        exit /b
    )
) else (
    for /f "tokens=*" %%v in ('python --version') do echo [OK] %%v gefunden.
)

:: 4. Ordnerstruktur erstellen
echo.
echo [2/4] Erstelle Ordnerstruktur...
if not exist "%REPO_DIR%\logs" mkdir "%REPO_DIR%\logs"
if not exist "%REPO_DIR%\data" mkdir "%REPO_DIR%\data"

if not exist "%GLOBAL_CONFIG_DIR%" (
    mkdir "%GLOBAL_CONFIG_DIR%"
    echo [OK] Globaler Config-Ordner erstellt.
)

:: 5. Checkfile schreiben (Pointer)
echo.
echo [3/4] Registriere Framework...
(
    echo Path="%REPO_DIR%"
) > "%CHECKFILE%" || (
    echo [FEHLER] Schreibzugriff auf Checkfile verweigert!
    pause
    exit /b
)
attrib +h "%GLOBAL_CONFIG_DIR%" /D >nul 2>&1
echo [OK] Checkfile aktualisiert.

:: 6. Abhängigkeiten installieren
echo.
echo [4/4] Installiere Python-Abhaengigkeiten...
if exist "%REPO_DIR%\requirements.txt" (
    pip install -r "%REPO_DIR%\requirements.txt"
    if !errorlevel! NEQ 0 (
        echo [FEHLER] Bei der Installation der Requirements ist ein Fehler aufgetreten.
        echo Pruefe deine Internetverbindung oder Proxy-Einstellungen.
    ) else (
        echo [OK] Alle Abhaengigkeiten erfolgreich installiert.
    )
) else (
    echo [INFO] Keine requirements.txt gefunden - ueberspringe pip install.
)

echo.
echo ===================================================
echo [ERFOLG] Installation vollstaendig abgeschlossen.
echo ===================================================
echo.
pause
