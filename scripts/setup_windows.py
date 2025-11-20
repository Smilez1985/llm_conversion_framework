#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Full Repo Install - Tkinter GUI)
DIREKTIVE: Goldstandard, vollständig, GUI-basiert (Tkinter), Netzwerk-Resilient.

Zweck:
- Führt eine Tkinter-GUI für die Installation aus.
- Prüft Systemvoraussetzungen (Docker, Git, Internet).
- Kopiert das GESAMTE Repository-Gerüst (für das Auto-Update).
- Lädt Docker-Images vor.
"""

import os
import sys
import shutil
import subprocess
import time
import socket
import threading
import tempfile
from pathlib import Path
from typing import Optional, List, Callable
import requests # Für Internet-Check

# Tkinter Imports für die grafische Oberfläche
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
except ImportError:
    print("FATAL ERROR: Tkinter is not available. Please ensure it's installed or use a different installer method.")
    sys.exit(1)


# --- KONFIGURATION & GLOBALS ---
INSTALL_APP_NAME = "LLM-Builder"
DEFAULT_INSTALL_DIR_SUFFIX = "LLM-Framework"

# REPO_ROOT wird zur Laufzeit initialisiert.
REPO_ROOT: Path = Path('.')

# Ordner, die NICHT zum User kopiert werden sollen
IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git", ".gitignore", ".gitattributes",
    ".venv", "venv", "env",
    "__pycache__", "*.pyc", "*.pyd",
    "dist", "build", "*.spec",
    "output", "cache", "logs", 
    "tmp", "temp"
)

# ============================================================================
# UTILITY FUNKTIONEN (Logik unabhängig von GUI)
# ============================================================================

def _find_repo_root_at_runtime() -> Optional[Path]:
    """
    Sucht den Root-Ordner des Repositories, indem es nach Markern sucht.
    Dies ist der Ordner, der alle Quellcodes, Skripte und den 'dist'-Ordner enthält.
    """
    if getattr(sys, 'frozen', False): # Wenn als EXE ausgeführt
        start_path = Path(sys.executable).parent
    else: # Wenn als Skript ausgeführt
        start_path = Path(__file__).resolve().parent

    current_path = start_path
    REPO_ROOT_MARKERS = [f"{INSTALL_APP_NAME}.ico", "targets", "orchestrator"]

    for _ in range(10): 
        if all((current_path / marker).exists() for marker in REPO_ROOT_MARKERS):
            return current_path
        
        parent = current_path.parent
        if parent == current_path: 
            break
        current_path = parent
    return None

def _create_shortcut(target_exe_path: Path, working_directory: Path, icon_path: Optional[Path] = None) -> bool:
    """Erstellt einen Desktop-Shortcut unter Windows."""
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    shortcut_path = os.path.join(desktop, f"{INSTALL_APP_NAME}.lnk")
    
    try:
        # Hier ist die Logik für pywin32, falls installiert
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = str(target_exe_path.absolute())
            shortcut.WorkingDirectory = str(working_directory.absolute())
            if icon_path and icon_path.exists():
                shortcut.IconLocation = str(icon_path.absolute())
            shortcut.Save()
            return True
        except ImportError:
            # Fallback zu VBScript, wenn pywin32 nicht da ist
            target_exe_str = str(target_exe_path.absolute()).replace("\\", "\\\\")
            working_dir_str = str(working_directory.absolute()).replace("\\", "\\\\")
            icon_location_str = str(icon_path.absolute()).replace("\\", "\\\\") if icon_path and icon_path.exists() else ""
            
            vbs_script = f"""
            Set oWS = WScript.CreateObject("WScript.Shell")
            sLinkFile = "{shortcut_path}"
            Set oLink = oWS.CreateShortcut(sLinkFile)
            oLink.TargetPath = "{target_exe_str}"
            oLink.WorkingDirectory = "{working_dir_str}"
            oLink.IconLocation = "{icon_location_str}"
            oLink.Description = "Launch LLM Cross-Compiler Framework"
            oLink.Save
            """
            
            vbs_file = Path(tempfile.gettempdir()) / "create_shortcut.vbs"
            with open(vbs_file, "w") as f:
                f.write(vbs_script)
            subprocess.run(["cscript", "//Nologo", str(vbs_file)], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            vbs_file.unlink()
            return True
    except Exception:
        return False

# ============================================================================
# INSTALLER GUI (TKINTER)
# ============================================================================

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Install {INSTALL_APP_NAME}")
        self.geometry("600x550")
        self.resizable(False, False)
        self.repo_root: Optional[Path] = None
        self.current_install_thread: Optional[threading.Thread] = None

        self._init_ui()
        self.update_log("Installer gestartet...")
        self.after(100, self._initial_checks) # Verzögert Start der Checks

    def _init_ui(self):
        # --- Styling (Basic) ---
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('TFrame', background='#e0e0e0')
        self.style.configure('TLabel', background='#e0e0e0', font=('Arial', 10))
        self.style.configure('TButton', font=('Arial', 10, 'bold'), padding=6, background='#007bff', foreground='white') # Bessere Button-Farbe
        self.style.map('TButton', background=[('active', '#0056b3')], foreground=[('active', 'white')])
        self.style.configure('TEntry', fieldbackground='#ffffff', font=('Arial', 10))
        self.style.configure('TCheckbutton', background='#e0e0e0', font=('Arial', 10))
        
        # Spezifisches Styling für Statuslabels
        self.style.configure('Status.TLabel', font=('Arial', 10, 'bold'))
        self.style.map('Status.TLabel', 
                       foreground=[('!disabled', 'green', 'ok'),
                                   ('!disabled', 'red', 'nok'),
                                   ('!disabled', 'orange', 'checking')])

        # --- Main Frame ---
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill='both', expand=True)

        # --- Title ---
        ttk.Label(main_frame, text=f"Welcome to {INSTALL_APP_NAME} Setup", font=('Arial', 16, 'bold')).pack(pady=10)

        # --- System Requirements ---
        req_frame = ttk.LabelFrame(main_frame, text="System Requirements Check", padding=10)
        req_frame.pack(fill='x', pady=5)
        
        self.docker_status = self._create_status_label(req_frame, "Docker Desktop (WSL2):")
        self.git_status = self._create_status_label(req_frame, "Git for Windows:")
        self.internet_status = self._create_status_label(req_frame, "Internet Connectivity:")

        # --- Installation Location ---
        loc_frame = ttk.LabelFrame(main_frame, text="Installation Location", padding=10)
        loc_frame.pack(fill='x', pady=5)
        
        ttk.Label(loc_frame, text="Where do you want to install the Framework?").pack(anchor='w')
        
        path_frame = ttk.Frame(loc_frame)
        path_frame.pack(fill='x', pady=5)
        
        default_install_path = Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX
        self.install_path_var = tk.StringVar(value=str(default_install_path))
        self.install_path_entry = ttk.Entry(path_frame, textvariable=self.install_path_var, width=50)
        self.install_path_entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        ttk.Button(path_frame, text="Browse...", command=self._browse_for_folder).pack(side='right')
        
        self.desktop_shortcut_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(loc_frame, text="Create Desktop Shortcut", variable=self.desktop_shortcut_var).pack(anchor='w', pady=5)

        # --- Log & Progress ---
        ttk.Label(main_frame, text="Installation Log:").pack(anchor='w', pady=(10, 0))
        # Log-Fenster mit dunklem Hintergrund und grünem Text
        self.log_text = ScrolledText(main_frame, wrap='word', height=8, state='disabled', font=('Courier New', 9), bg='#333', fg='#0f0')
        self.log_text.pack(fill='x', pady=(0, 5))
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill='x', pady=5)

        # --- Buttons ---
        button_frame = ttk.Frame(main_frame, style='TFrame')
        button_frame.pack(fill='x', pady=10)
        
        self.install_button = ttk.Button(button_frame, text="Install", command=self._start_installation, state='disabled')
        self.install_button.pack(side='left', expand=True, padx=(0, 5))
        
        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self.destroy)
        self.cancel_button.pack(side='right', expand=True, padx=(5, 0))

    def _create_status_label(self, parent_frame: ttk.LabelFrame, text: str) -> ttk.Label:
        """Erstellt ein Label für Statusanzeigen."""
        frame = ttk.Frame(parent_frame, style='TFrame')
        frame.pack(fill='x', pady=2)
        
        ttk.Label(frame, text=text, width=25, anchor='w', style='TLabel').pack(side='left')
        status_label = ttk.Label(frame, text="Checking...", style='Status.TLabel') # Nutze Status.TLabel
        status_label.pack(side='right', anchor='e')
        return status_label

    def update_log(self, message: str, color: str = None): # Farbe ist jetzt optional
        self.log_text.config(state='normal')
        tag_name = ""
        if color:
            tag_name = f"color_{color}"
            self.log_text.tag_config(tag_name, foreground=color)
        
        self.log_text.insert('end', f"[{time.strftime('%H:%M:%S')}] {message}\n", tag_name if color else "")
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        self.update_idletasks() # UI sofort aktualisieren

    def _browse_for_folder(self):
        folder_selected = filedialog.askdirectory(parent=self, title="Select Installation Directory")
        if folder_selected:
            target_path = Path(folder_selected)
            if not target_path.name.lower().endswith(DEFAULT_INSTALL_DIR_SUFFIX.lower()):
                target_path = target_path / DEFAULT_INSTALL_DIR_SUFFIX
            self.install_path_var.set(str(target_path))

    def _set_status_label(self, label: ttk.Label, text: str, status_type: str):
        # Aktualisiert den Status und setzt den Style Tag
        label.config(text=text)
        label.state((status_type,)) # Setzt den Status 'ok', 'nok', 'checking'
        self.update_idletasks()

    def _initial_checks(self):
        self.update_log("Führe Systemvoraussetzungen-Checks durch...")
        
        self.repo_root = _find_repo_root_at_runtime()
        if not self.repo_root:
            self.update_log("FEHLER: Repository-Root konnte nicht gefunden werden. Installation abgebrochen.", "red")
            messagebox.showerror("Installation Error", "Critical: Repository root not found. Cannot proceed.")
            return

        # Docker Check
        docker_ok = self._check_docker_status()
        self._set_status_label(self.docker_status, "OK" if docker_ok else "Not Found", "ok" if docker_ok else "nok")
        if not docker_ok:
            self.update_log("KRITISCH: Docker Desktop ist erforderlich und läuft nicht. Bitte installieren Sie Docker Desktop von https://www.docker.com/products/docker-desktop/ und starten Sie es, bevor Sie fortfahren.", "red")
            messagebox.showerror("Docker Missing", "Docker Desktop ist nicht installiert oder läuft nicht. Dies ist eine kritische Voraussetzung.")
            self.install_button.config(state='disabled')
            return # Installation blockieren, wenn Docker fehlt

        # Git Check
        git_ok = self._check_git_status()
        self._set_status_label(self.git_status, "OK" if git_ok else "Not Found", "ok" if git_ok else "nok")
        if not git_ok:
            self.update_log("WARNUNG: Git for Windows ist nicht installiert. Das Auto-Update-Feature des Frameworks wird nicht funktionieren. Installation fortgesetzt.", "orange")
        
        # Internet Check
        internet_ok = self._check_internet_status()
        self._set_status_label(self.internet_status, "OK" if internet_ok else "Failed", "ok" if internet_ok else "nok")
        if not internet_ok:
            self.update_log("WARNUNG: Keine Internetverbindung. Docker-Images können nicht vorgepullt und Auto-Updates nicht durchgeführt werden.", "orange")

        self.install_button.config(state='normal')
        self.update_log("Alle Kern-Voraussetzungen erfüllt. Bereit zur Installation.")

    def _check_docker_status(self) -> bool:
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
            return result.returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def _check_git_status(self) -> bool:
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return result.returncode == 0
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def _check_internet_status(self) -> bool:
        try:
            requests.head("http://www.google.com", timeout=3)
            return True
        except requests.ConnectionError:
            return False
        except Exception:
            return False

    def _start_installation(self):
        target_dir = Path(self.install_path_var.get()).resolve()
        desktop_shortcut = self.desktop_shortcut_var.get()

        if not target_dir.parent.exists():
            messagebox.showerror("Invalid Path", f"The parent directory for {target_dir} does not exist.")
            return

        self.install_button.config(state='disabled')
        self.cancel_button.config(state='disabled')
        self.progress_var.set(0)
        self.update_log("Installation gestartet...")

        self.current_install_thread = threading.Thread(target=self._run_installation_steps, args=(target_dir, desktop_shortcut))
        self.current_install_thread.daemon = True # Wichtig, damit Thread mit GUI endet
        self.current_install_thread.start()
        self._check_installation_progress()

    def _run_installation_steps(self, destination_path: Path, desktop_shortcut: bool):
        try:
            # 1. Zielordner vorbereiten
            self.update_progress(5, f"Bereite Zielordner '{destination_path}' vor...")
            if destination_path.exists():
                shutil.rmtree(destination_path)
                self.update_log("Bestehende Installation gelöscht.")
            destination_path.mkdir(parents=True, exist_ok=True)

            # 2. Kopiere das Repo-Gerüst (ohne Dev-Artefakte)
            self.update_progress(20, "Kopiere Framework-Dateien...")
            shutil.copytree(self.repo_root, destination_path, ignore=IGNORE_PATTERNS, dirs_exist_ok=True)

            # 3. Launcher kopieren
            launcher_src = self.repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"
            launcher_dst = destination_path / f"{INSTALL_APP_NAME}.exe"
            if not launcher_src.exists():
                 raise Exception(f"KRITISCH: Launcher EXE nicht gefunden unter: {launcher_src}. Bitte zuerst kompilieren!")
            
            self.update_progress(40, "Kopiere den signierten Launcher...")
            shutil.copy2(launcher_src, launcher_dst)

            # 4. Icon und leere Ordner erstellen
            icon_src = self.repo_root / f"{INSTALL_APP_NAME}.ico"
            if icon_src.exists():
                shutil.copy2(icon_src, destination_path / f"{INSTALL_APP_NAME}.ico")
            
            for d in ["output", "cache", "logs"]:
                (destination_path / d).mkdir(exist_ok=True)
            self.update_progress(50, "Basiskonfiguration abgeschlossen.")

            # 5. Desktop-Shortcut erstellen
            if desktop_shortcut:
                self.update_progress(60, "Erstelle Desktop-Verknüpfung...")
                if not _create_shortcut(launcher_dst, destination_path, destination_path / f"{INSTALL_APP_NAME}.ico"):
                    self.update_log("WARNUNG: Desktop-Verknüpfung konnte nicht erstellt werden.", "orange")
            else:
                self.update_log("Desktop-Verknüpfung nicht gewünscht.")

            # 6. Docker Pre-Pull
            self.update_progress(70, "Starte Docker Pre-Pull (dies kann einen Moment dauern)...")
            self._pre_pull_docker_images_threaded()

            self.update_progress(100, "Installation erfolgreich abgeschlossen.")
            messagebox.showinfo("Installation Complete", "Das LLM-Framework wurde erfolgreich installiert!")
            self.after(100, self.destroy) # Schließt das Fenster nach Erfolg

        except Exception as e:
            self.update_log(f"FEHLER während der Installation: {e}", "red")
            messagebox.showerror("Installation Failed", f"Ein Fehler ist aufgetreten:\n{e}")
            self.install_button.config(state='normal')
            self.cancel_button.config(state='normal')
            self.progress_var.set(0)

    def _pre_pull_docker_images_threaded(self):
        images = ["debian:bookworm-slim", "quay.io/vektorlab/ctop:latest"]
        
        for i, img in enumerate(images):
            retries = 0
            max_retries = 5
            while retries < max_retries:
                if self._check_internet_status():
                    self.update_progress(70 + i * (20 // len(images)), f"Lade Docker Image: {img} (Versuch {retries + 1})...")
                    try:
                        subprocess.run(["docker", "pull", img], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
                        self.update_log(f"Image '{img}' erfolgreich gepullt.")
                        break 
                    except subprocess.CalledProcessError as e:
                        self.update_log(f"Pull von '{img}' fehlgeschlagen: {e.stderr.strip()}", "orange")
                        retries += 1
                        time.sleep(5)
                else:
                    self.update_log("Keine Internetverbindung. Warte 10 Sekunden...", "orange")
                    time.sleep(10) 
            
            if retries == max_retries:
                 self.update_log(f"WARNUNG: Pull von '{img}' nach mehreren Versuchen fehlgeschlagen. Installation wird fortgesetzt, aber Docker-Builds könnten langsamer sein.", "orange")


    def update_progress(self, percent: int, message: str):
        self.progress_var.set(percent)
        self.update_log(message)

    def _check_installation_progress(self):
        if self.current_install_thread and self.current_install_thread.is_alive():
            self.after(500, self._check_installation_progress) # Prüft alle 500ms
        else:
            self.update_log("Installationsthread beendet.")


if __name__ == '__main__':
    # Initialisiere Win32-COM für Desktop-Shortcuts (für direkten Import in _create_shortcut)
    # Dies geschieht HIER, um die Warnung nur einmalig in der Konsole zu zeigen, 
    # aber der VBScript-Fallback ist immer noch primär in _create_shortcut
    try:
        import win32com.client # Erfordert 'pip install pywin32'
    except ImportError:
        print("WARNUNG: 'pywin32' ist nicht installiert. Desktop-Shortcuts werden über VBScript erstellt.")

    app = InstallerGUI()
    app.mainloop()
