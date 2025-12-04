@echo off
setlocal EnableDelayedExpansion

:: ===================================================
:: LLM Conversion Framework - Installer
:: ===================================================

:: 1. Admin-Rechte prüfen
openfiles >nul 2>&1
if %errorlevel% NEQ 0 (
    echo.
    echo [ACHTUNG] Dieses Skript benoetigt Administrator-Rechte.
    echo Bitte Rechtsklick auf die Datei und "Als Administrator ausfuehren" waehlen.
    echo.
    pause
    exit /b
)

:: 2. Pfade bestimmen
:: %~dp0 ist der Pfad, in dem das Skript liegt (z.B. ...\llm_conversion_framework\scripts\)
:: Wir wollen aber das Hauptverzeichnis (eins drueber)
pushd "%~dp0.."
set "INSTALL_DIR=%CD%"
popd

cls
echo ===================================================
echo      LLM Conversion Framework - Installation
echo ===================================================
echo.
echo [INFO] Installations-Ziel (Root): "%INSTALL_DIR%"
echo.

:: 3. Ordnerstruktur sicherstellen
if not exist "%INSTALL_DIR%\data" (
    mkdir "%INSTALL_DIR%\data"
    echo [OK] Ordner 'data' erstellt.
) else (
    echo [INFO] Ordner 'data' existiert bereits.
)

if not exist "%INSTALL_DIR%\logs" (
    mkdir "%INSTALL_DIR%\logs"
    echo [OK] Ordner 'logs' erstellt.
)

:: 4. Checkfile erstellen (Test Schreibrechte)
set "CHECKFILE=%INSTALL_DIR%\data\checkfile.txt"
(
    echo Installation Test: %DATE% %TIME%
    echo Installiert in: %INSTALL_DIR%
) > "%CHECKFILE%" || (
    echo [FEHLER] Konnte Checkfile nicht schreiben! Zugriff verweigert.
    pause
    exit /b
)

echo [OK] Checkfile erfolgreich erstellt: %CHECKFILE%

:: 5. Umgebungsvariable setzen (Optional - verursacht oft "Zugriff verweigert" ohne Admin)
:: Hier wird der Pfad permanent in Windows registriert, falls gewuenscht.
:: Entferne "REM" vor der naechsten Zeile, wenn du das willst:
REM setx LLM_FRAMEWORK_HOME "%INSTALL_DIR%" /M

echo.
echo ===================================================
echo [ERFOLG] Installation abgeschlossen.
echo ===================================================
echo.
pause
