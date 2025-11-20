import sys
import os
import subprocess
from pathlib import Path
# ... deine anderen imports ...

# 1. Bestimme das BASIS-VERZEICHNIS (Wo liegt die .exe oder das Skript?)
if getattr(sys, 'frozen', False):
    # Wenn als EXE ausgeführt: Der Ordner, in dem die .exe liegt
    BASE_DIR = Path(sys.executable).parent
else:
    # Wenn als Python-Skript ausgeführt: Das Root des Repos
    BASE_DIR = Path(__file__).resolve().parent.parent

# Setze das Arbeitsverzeichnis, damit relative Pfade in der App klappen
os.chdir(BASE_DIR)

# 2. Die Auto-Update Funktion
def run_auto_update():
    """Führt git pull im App-Verzeichnis aus."""
    git_dir = BASE_DIR / ".git"
    if not git_dir.exists():
        print("Kein Git-Repo gefunden. Überspringe Auto-Update.")
        return

    print(f"Prüfe auf Updates in {BASE_DIR}...")
    try:
        # Git pull ausführen.
        # capture_output verhindert, dass ein Konsolenfenster aufpoppt (bei windowed exe)
        result = subprocess.run(
            ["git", "pull"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        if "Already up to date." in result.stdout:
            print("Anwendung ist auf dem neuesten Stand.")
        else:
            print("Update erfolgreich geladen:")
            print(result.stdout)
            # OPTIONAL: Hier könnte man fragen, ob die App neu gestartet werden soll,
            # falls sich Core-Dateien geändert haben. Für den MVP reicht weitermachen.
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Auto-Update:\n{e.stderr}")
        # Wir starten trotzdem, vielleicht geht es ja noch.
    except FileNotFoundError:
         print("Git wurde nicht gefunden. Bitte installieren Sie Git für Updates.")

# ...

if __name__ == "__main__":
    # 3. VOR dem Start der GUI das Update ausführen
    run_auto_update()

    app = QApplication(sys.argv)
    # WICHTIG: Wenn du in deiner GUI Pfade lädst (z.B. Icons, Configs),
    # nutze jetzt immer BASE_DIR als Anker!
    # z.B.: icon_path = BASE_DIR / "assets" / "icon.png"

    window = MainWindow() # Hier keine Pfade mehr hartkodieren, die auf interne Ressourcen zeigen
    window.show()
    sys.exit(app.exec())
