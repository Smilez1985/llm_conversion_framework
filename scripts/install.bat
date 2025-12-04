@echo off
setlocal EnableDelayedExpansion

:: ===================================================
:: LLM Conversion Framework - CLI Installer (Fix)
:: Synchronisiert mit setup_windows.py Logik
:: ===================================================

:: 1. Admin-Rechte prüfen (Zwingend für saubere Installation)
openfiles >nul 2>&1
if %errorlevel% NEQ 0 (
    echo.
    echo [ACHTUNG] Bitte Rechtsklick auf die Datei und "Als Administrator ausfuehren".
    echo Das ist notwendig, um die globalen Verknuepfungen [Public Documents] zu erstellen.
    echo.
    pause
    exit /b
)

:: 2. Installations-Verzeichnis bestimmen (Wo liegt das Repo aktuell?)
pushd "%~dp0.."
set "REPO_DIR=%CD%"
popd

:: 3. Ziel-Verzeichnis für Konfiguration (Gemäß setup_windows.py Standard)
set "GLOBAL_CONFIG_DIR=C:\Users\Public\Documents\llm_conversion_framework"
set "CHECKFILE=%GLOBAL_CONFIG_DIR%\checkfile.txt"

cls
echo ===================================================
echo      LLM Conversion Framework - Installation
echo ===================================================
echo.
echo [INFO] Framework Pfad: "%REPO_DIR%"
echo [INFO] Globaler Pfad:  "%GLOBAL_CONFIG_DIR%"
echo.

:: 4. Ordnerstruktur im Framework sicherstellen (Logs/Data)
if not exist "%REPO_DIR%\logs" mkdir "%REPO_DIR%\logs"
if not exist "%REPO_DIR%\data" mkdir "%REPO_DIR%\data"

:: 5. Globalen Konfigurations-Ordner erstellen (Public Documents)
if not exist "%GLOBAL_CONFIG_DIR%" (
    mkdir "%GLOBAL_CONFIG_DIR%"
    if %errorlevel% NEQ 0 (
        echo [FEHLER] Konnte globalen Ordner nicht erstellen: %GLOBAL_CONFIG_DIR%
        pause
        exit /b
    )
    echo [OK] Globaler Ordner erstellt.
)

:: 6. Checkfile schreiben (Der Pointer für den Launcher)
:: WICHTIG: Das Format muss 'Path="C:\..."' sein, wie in setup_windows.py
(
    echo Path="%REPO_DIR%"
) > "%CHECKFILE%" || (
    echo [FEHLER] Zugriff verweigert beim Schreiben von: %CHECKFILE%
    pause
    exit /b
)

:: Verstecke den globalen Ordner (Optional, wie im Python Skript)
attrib +h "%GLOBAL_CONFIG_DIR%" /D >nul 2>&1

echo [OK] Checkfile erfolgreich erstellt.
echo      Inhalt: Path="%REPO_DIR%"
echo.

:: 7. Umgebungsvorbereitung (Optional: Requirements checken)
echo [INFO] Pruefe Python Umgebung...
if exist "%REPO_DIR%\requirements.txt" (
    echo [TIPP] Falls noch nicht geschehen, installiere die Python-Abhaengigkeiten mit:
    echo        pip install -r "%REPO_DIR%\requirements.txt"
)

echo.
echo ===================================================
echo [ERFOLG] Installation abgeschlossen.
echo Das Framework ist nun registriert.
echo ===================================================
echo.
pause
