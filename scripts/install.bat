@echo off
setlocal EnableDelayedExpansion

echo ===================================================
echo      LLM Conversion Framework - Installation
echo ===================================================

:: 1. ins Root wechseln und Pfad speichern
pushd "%~dp0.."
set "ROOT_DIR=%CD%"

echo [INFO] Installations-Ziel: "%ROOT_DIR%"

:: 2. Data Ordner & Checkfile (mit absoluten Pfaden)
if not exist "%ROOT_DIR%\data" (
    mkdir "%ROOT_DIR%\data"
)
:: Erst sichtbar machen, falls versteckt, um Zugriffsprobleme zu vermeiden
attrib -h "%ROOT_DIR%\data" >nul 2>&1

:: Datei explizit erstellen
echo Verified > "%ROOT_DIR%\data\checkfile.txt"

:: Attribute setzen: Ordner sichtbar, Datei versteckt
attrib -h "%ROOT_DIR%\data"
attrib +h "%ROOT_DIR%\data\checkfile.txt"

if exist "%ROOT_DIR%\data\checkfile.txt" (
    echo [OK] Checkfile erstellt: %ROOT_DIR%\data\checkfile.txt
) else (
    echo [FEHLER] Checkfile konnte nicht erstellt werden!
    pause
    exit /b
)

:: 3. Launcher kopieren
set "SOURCE=%~dp0start-llm_convertion_framework.bat"
set "DEST=%ROOT_DIR%\start-llm_convertion_framework.bat"

if exist "%SOURCE%" (
    copy /Y "%SOURCE%" "%DEST%" >nul
    echo [OK] Launcher ins Root kopiert.
) else (
    echo [FEHLER] Launcher-Vorlage nicht gefunden in: "%SOURCE%"
    pause
    exit /b
)

:: 4. Verknuepfung erstellen (PowerShell Einzeiler - KEINE Umbrueche!)
echo [INFO] Erstelle Desktop-Icon...
set "LNK_PATH=%USERPROFILE%\Desktop\LLM Conversion Framework.lnk"
set "ICON_PATH=%ROOT_DIR%\assets\app_icon.ico"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%LNK_PATH%'); $s.TargetPath = '%DEST%'; $s.WorkingDirectory = '%ROOT_DIR%'; $s.IconLocation = '%ICON_PATH%'; $s.Save()"

echo [OK] Installation sauber abgeschlossen.
echo.
pause
