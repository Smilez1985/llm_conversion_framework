@echo off
setlocal EnableDelayedExpansion

echo ===================================================
echo      LLM Conversion Framework - Installation
echo ===================================================

:: --- PFAD KORREKTUR ---
:: %~dp0 = Pfad dieses Skripts (...\scripts\)
:: Wir wechseln eine Ebene hoch (..) ins Root-Verzeichnis.
pushd "%~dp0.."

echo [INFO] Arbeitsverzeichnis gesetzt auf: %CD%

:: -- Konfiguration --
set "SOURCE_SCRIPT=scripts\start-llm_convertion_framework.bat"
set "DEST_SCRIPT=start-llm_convertion_framework.bat"
set "ICON_PATH=assets\app_icon.ico"
set "SHORTCUT_NAME=LLM Conversion Framework.lnk"

:: 1. Data Ordner & Checkfile
echo [1/3] Konfiguriere Daten-Ordner...

if not exist "data" mkdir "data"
attrib -h "data"

:: Checkfile erstellen und verstecken
if not exist "data\checkfile.txt" echo.> "data\checkfile.txt"
attrib +h "data\checkfile.txt"
echo       [OK] Data-Ordner und verstecktes Checkfile bereit.

:: 2. Launcher kopieren
echo [2/3] Installiere Start-Skript...

if exist "%SOURCE_SCRIPT%" (
    copy /Y "%SOURCE_SCRIPT%" "%DEST_SCRIPT%" >nul
    echo       [OK] Start-Skript ins Hauptverzeichnis kopiert.
) else (
    echo       [FEHLER] Quell-Datei '%SOURCE_SCRIPT%' nicht gefunden!
    echo       Bitte sicherstellen, dass wir im richtigen Ordner sind.
    popd
    pause
    exit /b
)

:: 3. Desktop Verknüpfung erstellen
echo [3/3] Erstelle Desktop-Verknuepfung...

set "TARGET_PATH=%CD%\%DEST_SCRIPT%"
set "ICON_FULL_PATH=%CD%\%ICON_PATH%"
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "WORK_DIR=%CD%"

:: WICHTIG: Alles in einer Zeile, um "^"-Fehler zu vermeiden
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP_DIR%\%SHORTCUT_NAME%'); $s.TargetPath = '!TARGET_PATH!'; $s.WorkingDirectory = '!WORK_DIR!'; $s.IconLocation = '!ICON_FULL_PATH!'; $s.Save()"

echo       [OK] Verknuepfung auf dem Desktop erstellt.

:: Zurück zum Ursprung
popd

echo.
echo ===================================================
echo      Installation erfolgreich!
echo ===================================================
timeout /t 5 >nul
