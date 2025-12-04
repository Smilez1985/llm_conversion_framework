#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows GUI Installer (v2.16 FINAL)
DIREKTIVE: Goldstandard. KORRIGIERTER PFAD-MERGE.
  FIX: Konsolidiert CHECKFILE_DIR mit DEFAULT_DATA_PATH, um nur einen Datenordner zu erstellen.
"""

import os
import sys
import shutil
import subprocess
import threading
import time
import ctypes
import winreg
import webbrowser
import yaml
from pathlib import Path
import pythoncom 

# Dependencies (vom Launcher vorinstalliert oder im Host-Environment erwartet)
try:
    import psutil
    import requests
    # Importiere winshell/pywin32 für Shortcuts
    import winshell
    from win32com.client import Dispatch
except ImportError:
    # Kann passieren, wenn die install.bat nicht korrekt vorbereitet hat
    pass

# GUI Imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

APP_NAME = "LLM-Conversion-Framework"
APP_TITLE = "LLM Conversion Framework"

# Deployment Name für den Launcher (Muss dem Quellnamen entsprechen, um Altlasten zu vermeiden)
LAUNCHER_FILE_NAME = "start-llm_convertion_framework.bat"

# Standard-Installationspfad
DEFAULT_APP_PATH = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / APP_NAME
# KORREKTUR: Hart codierter Pfad C:\Users\Public\Documents\LLM-CF für universelle Schreibrechte.
DEFAULT_DATA_PATH = Path("C:/Users/Public/Documents") / APP_NAME 

# Zentrale Config (Pointer) - Wird auf den korrekten DEFAULT_DATA_PATH gesetzt.
CHECKFILE_DIR = DEFAULT_DATA_PATH 
CHECKFILE_PATH = CHECKFILE_DIR / "checkfile.txt"

# NEU: Trennung der Verzeichnisse nach Zielort
CODE_DIRS = ["orchestrator", "configs", "assets", "Docker Setup"] # Geht in den App Path
DATA_TEMPLATES_DIRS = ["targets", "models"] # Geht DIREKT in den Data Path

INCLUDE_APP_FILES = ["pyproject.toml", "poetry.lock", "requirements.txt", ".gitignore"] # Geht in den App Path
# Launcher-Dateien werden individuell behandelt, hier nur Dokumente/Lizenzen
INCLUDE_LAUNCHER_DOCS = ["README.md", "LICENSE.txt"]
IGNORE_PATTERNS = ["__pycache__", "*.pyc", ".git", ".venv", "venv", "dist", "build", ".installer_venv"]

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} Installer v2.16")
        self.geometry("800x700")
        self.resizable(True, True)
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.docker_ok = False
        self._init_ui()
        self.after(500, self._check_docker_background)

    def _init_ui(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        header = ttk.Frame(main_frame)
        header.pack(fill=tk.X, pady=(0, 15))
        lbl_title = ttk.Label(header, text=f"Install {APP_TITLE}", font=("Segoe UI", 18, "bold"))
        lbl_title.pack(anchor=tk.W)
        
        self.lbl_status = ttk.Label(main_frame, text="Checking System Requirements...", foreground="blue")
        self.lbl_status.pack(fill=tk.X, pady=(0, 10))

        # Application Path (Source Code, VENV)
        grp_app = ttk.LabelFrame(main_frame, text="Application Path (Source Code & VENV)", padding="10")
        grp_app.pack(fill=tk.X, pady=5)
        self.var_app_path = tk.StringVar(value=str(DEFAULT_APP_PATH))
        e_app = ttk.Entry(grp_app, textvariable=self.var_app_path)
        e_app.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(grp_app, text="Browse...", command=lambda: self._browse(self.var_app_path)).pack(side=tk.RIGHT)
        
        # Data Path (Output, Logs, Cache) - NICHT versteckt
        grp_data = ttk.LabelFrame(main_frame, text="Data & Output Path (Artefakte)", padding="10")
        grp_data.pack(fill=tk.X, pady=5)
        self.var_data_path = tk.StringVar(value=str(DEFAULT_DATA_PATH))
        e_data = ttk.Entry(grp_data, textvariable=self.var_data_path)
        e_data.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(grp_data, text="Browse...", command=lambda: self._browse(self.var_data_path)).pack(side=tk.RIGHT)
        
        # Options
        opt_frame = ttk.Frame(main_frame)
        opt_frame.pack(fill=tk.X, pady=10)
        self.var_desktop = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Create Desktop Shortcuts (App & Data Folder)", variable=self.var_desktop).pack(anchor=tk.W)
        
        # Log
        log_frame = ttk.LabelFrame(main_frame, text="Installation Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.log_text = ScrolledText(log_frame, height=12, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Progress
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.btn_install = ttk.Button(btn_frame, text="Install Now", command=self._start_install, state='disabled')
        self.btn_install.pack(side=tk.RIGHT)
        self.btn_cancel = ttk.Button(btn_frame, text="Cancel", command=self.destroy)
        self.btn_cancel.pack(side=tk.RIGHT, padx=10)

    def _browse(self, var):
        # UX FIX: Stellt sicher, dass der Zielordnername angehängt wird, wenn der Benutzer einen Elternpfad auswählt.
        path_str = var.get()
        p = Path(path_str) 
        
        # 1. Bestimme den existierenden Startpfad (Elternordner, z.B. C:\Program Files)
        initial_dir = p.parent 
        
        # Defensiver Fallback
        if not initial_dir.exists():
            initial_dir = Path.home()
        
        # 2. Öffne den Dialog im existierenden Elternordner
        d = filedialog.askdirectory(initialdir=str(initial_dir))
        
        if d:
            # 3. Hänge den gewünschten Anwendungsnamen (p.name: LLM-Conversion-Framework)
            # an den vom Benutzer ausgewählten Pfad (d) an.
            final_path = Path(d) / p.name
            
            # 4. Aktualisiere das Eingabefeld mit dem vollständigen Zielpfad
            var.set(str(final_path))

    def log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.update_idletasks()

    def _check_docker_background(self):
        threading.Thread(target=self._check_docker, daemon=True).start()

    def _check_docker(self):
        self.log("Checking Docker environment...")
        
        if 'psutil' not in sys.modules or 'requests' not in sys.modules:
            self.lbl_status.config(text="Installer-Abh. fehlen. Installer neu starten.", foreground="red")
            return

        docker_exe = shutil.which("docker")
        if not docker_exe:
            self.lbl_status.config(text="Docker not found!", foreground="red")
            self.log("CRITICAL: Docker not found.")
            if messagebox.askyesno("Docker Missing", "Docker Desktop is required. Download now?"):
                webbrowser.open("https://www.docker.com/products/docker-desktop/")
            return

        running = False
        try:
            for proc in psutil.process_iter(['name']):
                if "Docker Desktop" in proc.info['name']:
                    running = True
                    break
        except:
            pass
        
        if not running:
            self.log("Starting Docker Desktop...")
            try:
                dd_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
                if os.path.exists(dd_path):
                    subprocess.Popen([dd_path], creationflags=subprocess.CREATE_NO_WINDOW)
                    for i in range(30):
                        time.sleep(1)
                        try:
                            if subprocess.run(["docker", "info"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0:
                                running = True
                                break
                        except: pass
            except Exception as e:
                self.log(f"Start failed: {e}")

        try:
            if subprocess.run(["docker", "info"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0:
                running = True
        except: pass

        if running:
            self.docker_ok = True
            self.lbl_status.config(text="System Ready.", foreground="green")
            self.btn_install.config(state='normal')
            self.log("Docker check passed.")
        else:
            self.lbl_status.config(text="Docker Error.", foreground="red")
            self.log("Docker daemon not responding.")


    def _start_install(self):
        target_dir = Path(self.var_app_path.get())
        data_dir = Path(self.var_data_path.get())
        
        if not target_dir.is_absolute() or not data_dir.is_absolute():
             messagebox.showerror("Fehler", "Pfade muessen absolut sein!")
             return

        self.btn_install.config(state='disabled')
        self.btn_cancel.config(state='disabled')
        self.progress['value'] = 0
        threading.Thread(target=self._install_process, args=(target_dir, data_dir), daemon=True).start()

    def _install_process(self, app_dir: Path, data_dir: Path):
        pythoncom.CoInitialize() # FIX: Initialisiert COM für den Installations-Thread

        try:
            self.log(f"--- Starte Installation ---")
            self.log(f"App (Code/VENV): {app_dir}")
            self.log(f"Data (Output/Log): {data_dir}")
            
            # 1. Verzeichnisse erstellen
            if not app_dir.exists(): app_dir.mkdir(parents=True, exist_ok=True)
            if not data_dir.exists(): data_dir.mkdir(parents=True, exist_ok=True)
            
            # 2. Copy Content: Source Code in den App-Pfad
            self.log("Kopiere Framework-Dateien in den App-Pfad...")
            total_items = len(CODE_DIRS) + len(DATA_TEMPLATES_DIRS) + len(INCLUDE_APP_FILES) + len(INCLUDE_LAUNCHER_DOCS) + 3 
            current = 0
            
            # Kopiere Code-Ordner (orchestrator, configs, assets, Docker Setup)
            for item in CODE_DIRS:
                src = SOURCE_DIR / item
                dst = app_dir / item
                if src.exists():
                    if dst.exists(): shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))
                    self.log(f"  Kopiert (App): {item}")
                current += 1
                self.progress['value'] = (current / total_items) * 20
            
            # Kopiere App-Dateien (pyproject.toml etc.)
            for item in INCLUDE_APP_FILES:
                src = SOURCE_DIR / item
                dst = app_dir / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1

            # 3. Copy Launcher/Uninstaller/Docs in den App-Pfad
            
            # Kopiere Readme/License
            for item in INCLUDE_LAUNCHER_DOCS:
                src = SOURCE_DIR / item
                dst = app_dir / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1
            
            # Launcher kopieren
            SRC_LAUNCHER = SOURCE_DIR / "scripts" / LAUNCHER_FILE_NAME
            if SRC_LAUNCHER.exists():
                shutil.copy2(SRC_LAUNCHER, app_dir / LAUNCHER_FILE_NAME)
                self.log(f"  Kopiert (Launcher): {LAUNCHER_FILE_NAME}")
            else:
                self.log(f"  FEHLER: Launcher-Quelle nicht gefunden: {SRC_LAUNCHER}")
            current += 1

            # Kopiere Uninstaller
            src_uninstaller = SOURCE_DIR / "scripts" / "Uninstall-LLM-Conversion-Framework.bat"
            if src_uninstaller.exists():
                shutil.copy2(src_uninstaller, app_dir / "Uninstall-LLM-Conversion-Framework.bat")
            current += 1
                
            self.progress['value'] = 30
            
            # 4. Copy Data-Templates DIREKT in den Data Path
            self.log("Kopiere Daten-Templates (Targets/Models) in den Data Path...")
            for item in DATA_TEMPLATES_DIRS:
                src = SOURCE_DIR / item
                dst = data_dir / item
                if src.exists():
                    if dst.exists(): shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))
                    self.log(f"  Kopiert (Data): {item}")
                current += 1
                self.progress['value'] = (current / total_items) * 45


            # 5. VENV Creation & Dependencies Installation im App-Pfad
            self.log("Erstelle isolierte Python-Umgebung (.venv)...")
            venv_path = app_dir / ".venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv_path)], 
                         check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            pip_exe = venv_path / "Scripts" / "pip.exe"
            cwd = str(app_dir)
            
            self.log("Installiere Abhaengigkeiten...")
            req_file = app_dir / "requirements.txt"
            if req_file.exists():
                subprocess.run([str(pip_exe), "install", "-r", "requirements.txt"], cwd=cwd,
                             capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                subprocess.run([str(pip_exe), "install", "--no-deps", "."], cwd=cwd,
                             capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.progress['value'] = 75

            # 6. Konfigurationsdateien für Output/Logs anpassen
            self.log("Konfiguriere ALLE Datenpfade...")
            
            # Sicherstellen, dass die Data-Ordner existieren (Output, Logs, Cache)
            (data_dir / "output").mkdir(parents=True, exist_ok=True)
            (data_dir / "logs").mkdir(parents=True, exist_ok=True)
            (data_dir / "cache").mkdir(parents=True, exist_ok=True) 
            
            config_file = app_dir / "configs" / "user_config.yml" 
            config_data = {}
            if config_file.exists():
                try:
                    with open(config_file, 'r') as f:
                        config_data = yaml.safe_load(f) or {}
                except: pass
            
            # Setze oder überschreibe ALLE data-relevanten Pfade auf absolute Data Path Werte
            config_data["output_dir"] = str(data_dir / "output")
            config_data["logs_dir"] = str(data_dir / "logs")
            config_data["cache_dir"] = str(data_dir / "cache")
            config_data["targets_dir"] = str(data_dir / "targets") 
            config_data["models_dir"] = str(data_dir / "models")   
            
            with open(config_file, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False)
            
            self.log(f"  Alle Datenpfade in {config_file.name} auf Data Path gesetzt.")

            # 7. Checkfile (Pointer)
            self.log("Finalisiere Registrierung...")
            
            # Pfad der Checkfile, die im Data-Ordner liegen soll
            current_checkfile_path = data_dir / "checkfile.txt"
            
            # FIX: Entfernt schützende Attribute, falls das File existiert (um Errno 13 zu vermeiden)
            if current_checkfile_path.exists():
                try:
                    # 0x00 = FILE_ATTRIBUTE_NORMAL (Clears read-only, hidden, etc.)
                    ctypes.windll.kernel32.SetFileAttributesW(str(current_checkfile_path), 0x00)
                except Exception as attr_e:
                    self.log(f"WARNUNG: Konnte Attribute nicht zurücksetzen: {attr_e}")

            # Checkfile zeigt auf den App-Pfad (Source Code + VENV)
            with open(current_checkfile_path, "w") as f:
                f.write(f'Path="{app_dir}"') 
            
            # Nur Checkfile verstecken
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(current_checkfile_path), 0x02)
            except: pass

            self.progress['value'] = 85

            # 8. Shortcuts
            if self.var_desktop.get():
                self.log("Erstelle Desktop-Verknüpfungen (App & Data)...")
                self._create_shortcut_pair(app_dir, data_dir)

            self.progress['value'] = 100
            self.log("Installation Complete!")
            
            messagebox.showinfo("Success", "Installation erfolgreich abgeschlossen!\n\nDas Framework ist nun in den Programmen und die Datenpfade getrennt.")
            self.destroy()
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Installationsfehler", f"Ein kritischer Fehler ist aufgetreten: {str(e)}")
            self.btn_install.config(state='normal')
            self.btn_cancel.config(state='normal')
        finally:
            pythoncom.CoUninitialize() # Bereinigt COM, unabhängig vom Erfolg oder Misserfolg.

    def _create_shortcut_pair(self, app_dir: Path, data_dir: Path):
        if 'winshell' not in sys.modules or 'Dispatch' not in globals():
            self.log("Shortcuts konnten nicht erstellt werden (winshell/pywin32 fehlt).")
            return
            
        shell = Dispatch('WScript.Shell')
        desktop = winshell.desktop()
        
        # Icon-Pfade (sind jetzt im app_dir/assets)
        icon_app_path = str(app_dir / "assets" / "LLM-Builder.ico")
        icon_data_path = str(app_dir / "assets" / "setup_LLM-Builder.ico")
        
        # --- Shortcut 1: Die App Launcher
        name_app = f"{APP_TITLE}"
        path_app = os.path.join(desktop, f"{name_app}.lnk")
        # ZIEL: Muss auf den korrekten Dateinamen zeigen (keine Altlast)
        target_bat = str(app_dir / LAUNCHER_FILE_NAME)
        
        shortcut_app = shell.CreateShortCut(path_app)
        shortcut_app.Targetpath = target_bat
        shortcut_app.WorkingDirectory = str(app_dir)
        shortcut_app.Description = "Startet die LLM Conversion Framework Anwendung"
        if Path(icon_app_path).exists():
            shortcut_app.IconLocation = icon_app_path
        shortcut_app.save()
        self.log(f"  Erstellt: App-Launcher")
        
        # --- Shortcut 2: Der Data/Output Ordner
        name_data = f"{APP_TITLE} Data & Output"
        path_data = os.path.join(desktop, f"{name_data}.lnk")
        
        shortcut_data = shell.CreateShortCut(path_data)
        shortcut_data.Targetpath = str(data_dir) # Ziel ist das Verzeichnis selbst
        shortcut_data.WorkingDirectory = str(data_dir)
        shortcut_data.Description = "Öffnet den Daten- und Ausgabeordner (Goldenes Artefakt)"
        if Path(icon_data_path).exists():
            shortcut_data.IconLocation = icon_data_path
        shortcut_data.save()
        self.log(f"  Erstellt: Data-Folder-Shortcut")

if __name__ == "__main__":
    app = InstallerGUI()
    app.mainloop()
