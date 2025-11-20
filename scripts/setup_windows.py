#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Full Repo Install - Tkinter GUI)
DIREKTIVE: Goldstandard, vollständig, GUI-basiert (Tkinter), Netzwerk-Resilient.
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
    print("FATAL ERROR: Tkinter is not available. Installation requires Tkinter.")
    sys.exit(1)


# --- KONFIGURATION & GLOBALS ---
INSTALL_APP_NAME = "LLM-Builder"
DEFAULT_INSTALL_DIR_SUFFIX = "LLM-Framework"

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
# UTILITY FUNKTIONEN (Kernlogik)
# ============================================================================

def _find_repo_root_at_runtime() -> Optional[Path]:
    """Sucht den Root-Ordner des Repositories."""
    if getattr(sys, 'frozen', False): 
        start_path = Path(sys.executable).parent
    else: 
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
    """Erstellt einen Desktop-Shortcut unter Windows (VBScript als Fallback)."""
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    shortcut_path = os.path.join(desktop, f"{INSTALL_APP_NAME}.lnk")
    
    try:
        # VBScript als Fallback
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

def install_application(destination_path: Path, desktop_shortcut: bool, log_callback: Callable, progress_callback: Callable):
    """Führt die Kern-Installationslogik aus."""
    
    repo_root = _find_repo_root_at_runtime()
    if not repo_root:
        raise Exception("CRITICAL: Repository-Root nicht gefunden. Installation abgebrochen.")
        
    log_callback(f"Repository-Root gefunden unter: {repo_root}", "info")

    # 1. Zielordner vorbereiten
    log_callback(f"Bereite Zielordner '{destination_path}' vor...", "info")
    progress_callback(5)
    if destination_path.exists():
        shutil.rmtree(destination_path)
        log_callback("Bestehende Installation gelöscht.", "info")
    destination_path.mkdir(parents=True, exist_ok=True)

    # 2. Kopiere das Repo-Gerüst
    log_callback("Kopiere Framework-Dateien...", "info")
    progress_callback(20)
    shutil.copytree(repo_root, destination_path, ignore=IGNORE_PATTERNS, dirs_exist_ok=True)

    # 3. Launcher kopieren
    launcher_src = repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"
    launcher_dst = destination_path / f"{INSTALL_APP_NAME}.exe"
    if not launcher_src.exists():
         raise Exception(f"KRITISCH: Launcher EXE nicht gefunden unter: {launcher_src}. Bitte zuerst kompilieren!")
    
    log_callback("Kopiere den signierten Launcher...", "info")
    progress_callback(40)
    shutil.copy2(launcher_src, launcher_dst)

    # 4. Basiskonfiguration und leere Ordner
    icon_src = repo_root / f"{INSTALL_APP_NAME}.ico"
    if icon_src.exists(): shutil.copy2(icon_src, destination_path / f"{INSTALL_APP_NAME}.ico")
    for d in ["output", "cache", "logs"]: (destination_path / d).mkdir(exist_ok=True)
    
    log_callback("Basiskonfiguration abgeschlossen.", "success")
    progress_callback(50)

    # 5. Desktop-Shortcut erstellen
    if desktop_shortcut:
        log_callback("Erstelle Desktop-Verknüpfung...", "info")
        if not _create_shortcut(launcher_dst, destination_path, destination_path / f"{INSTALL_APP_NAME}.ico"):
            log_callback("FEHLER: Desktop-Shortcut konnte nicht erstellt werden.", "error")
    
    log_callback("Installation erfolgreich abgeschlossen.", "success")


# ============================================================================
# INSTALLATION WORKER (THREADED LOGIC)
# ============================================================================

class InstallationWorker(threading.Thread):
    def __init__(self, target_dir: Path, desktop_shortcut: bool, log_callback: Callable, progress_callback: Callable):
        super().__init__(daemon=True)
        self.target_dir = target_dir
        self.desktop_shortcut = desktop_shortcut
        self.log = log_callback
        self.progress = progress_callback
        self.success = False
        self.message = ""

    def _check_internet_status(self):
        try:
            requests.head("http://www.google.com", timeout=3)
            return True
        except:
            return False

    def _pre_pull_docker(self):
        images = ["debian:bookworm-slim", "quay.io/vektorlab/ctop:latest"]
        
        for i, img in enumerate(images):
            retries = 0
            max_retries = 5
            while retries < max_retries:
                if self._check_internet_status():
                    self.progress(70 + i * (20 // len(images)), f"Lade Docker Image: {img} (Versuch {retries + 1}/{max_retries})...")
                    try:
                        subprocess.run(["docker", "pull", img], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
                        self.log(f"Image '{img}' erfolgreich gepullt.", "success")
                        break 
                    except subprocess.CalledProcessError as e:
                        self.log(f"Pull von '{img}' fehlgeschlagen: {e.stderr.strip()}", "orange")
                        retries += 1
                        time.sleep(5)
                else:
                    self.log("Keine Internetverbindung. Warte 10 Sekunden...", "orange")
                    time.sleep(10) 
            
            if retries == max_retries:
                 self.log(f"WARNUNG: Pull von '{img}' nach mehreren Versuchen fehlgeschlagen. Installation wird fortgesetzt.", "orange")

    def run(self):
        try:
            # 1. Installation der Dateien
            install_application(self.target_dir, self.desktop_shortcut, self.log, self.progress)
            
            # 2. Docker Pre-Pull
            self.progress(70, "Starte Docker Pre-Pull...")
            self._pre_pull_docker()
            
            self.progress(100, "Installation abgeschlossen.")
            self.success = True
            self.message = "Installation erfolgreich abgeschlossen."

        except Exception as e:
            self.success = False
            self.message = str(e)


# ============================================================================
# INSTALLER GUI (TKINTER)
# ============================================================================

class InstallerWindow(tk.Tk):
    """Hauptfenster des Tkinter Installers."""
    def __init__(self):
        super().__init__()
        self.title(f"Install {INSTALL_APP_NAME}")
        self.geometry("600x550")
        self.minsize(500, 450) # Mindestgröße festlegen
        self.resizable(True, True) # Skalierung aktivieren!
        
        self.current_install_thread: Optional[InstallationWorker] = None
        self.progress_var = tk.DoubleVar(value=0) # Muss im __init__ des Tk-Root liegen
        
        self._init_ui()
        
        # FINALER FIX: Ruft die Methode des Objekts korrekt auf
        self.after(100, self._run_initial_checks_start) 

    def _init_ui(self):
        # --- Styling ---
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('TFrame', background='#e0e0e0')
        self.style.configure('TLabel', background='#e0e0e0', font=('Arial', 10))
        self.style.configure('TButton', font=('Arial', 10, 'bold'), padding=6, background='#007bff', foreground='white')
        self.style.map('TButton', background=[('active', '#0056b3')], foreground=[('active', 'white')])

        # --- Main Frame (Gitter-Manager für Skalierung) ---
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill='both', expand=True)

        # Konfiguriere Zeilen- und Spaltengewichte für Skalierung
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(4, weight=1) # Log-Fenster soll sich ausdehnen

        # --- Title ---
        ttk.Label(main_frame, text=f"Welcome to {INSTALL_APP_NAME} Setup", font=('Arial', 16, 'bold')).grid(row=0, column=0, pady=10, sticky='ew')

        # --- System Requirements (Row 1) ---
        req_frame = ttk.LabelFrame(main_frame, text="System Requirements Check", padding=10)
        req_frame.grid(row=1, column=0, sticky='ew', pady=5)
        
        self.docker_status = self._create_status_label(req_frame, "Docker Desktop (WSL2):")
        # KORREKTUR DER FEHLERHAFTEN ZEILE: 'req(req_frame)' entfernt
        self.git_status = self._create_status_label(req_frame, "Git for Windows:") 
        self.internet_status = self._create_status_label(req_frame, "Internet Connectivity:")

        # --- Installation Location (Row 2) ---
        loc_frame = ttk.LabelFrame(main_frame, text="Installation Location", padding=10)
        loc_frame.grid(row=2, column=0, sticky='ew', pady=5)
        
        ttk.Label(loc_frame, text="Where do you want to install the Framework?").pack(anchor='w')
        
        path_frame = ttk.Frame(loc_frame)
        path_frame.pack(fill='x', pady=5)
        
        default_install_path = Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX
        self.install_path_entry = ttk.Entry(path_frame, textvariable=tk.StringVar(value=str(default_install_path)), width=50)
        self.install_path_entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        ttk.Button(path_frame, text="Browse...", command=self._browse_for_folder).pack(side='right')
        
        self.desktop_shortcut_checkbox = ttk.Checkbutton(loc_frame, text="Create Desktop Shortcut")
        self.desktop_shortcut_checkbox.state(['!alternate', 'selected']) # Setzt Default auf True
        self.desktop_shortcut_checkbox.pack(anchor='w', pady=5)

        # --- Log & Progress (Row 3, 4) ---
        ttk.Label(main_frame, text="Installation Log:").grid(row=3, column=0, sticky='w', pady=(10, 0))
        
        self.log_text = ScrolledText(main_frame, wrap='word', height=8, state='disabled', font=('Courier New', 9), bg='#333', fg='#0f0')
        self.log_text.grid(row=4, column=0, sticky='nsew', pady=(0, 5)) 

        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.grid(row=5, column=0, sticky='ew', pady=5)

        # --- Buttons Frame (Row 6: WICHTIG: Fixiert die Buttons ganz unten) ---
        button_frame = ttk.Frame(main_frame, style='TFrame')
        button_frame.grid(row=6, column=0, sticky='ew', pady=10) 
        
        self.install_button = ttk.Button(button_frame, text="Install", command=self._start_installation, state='disabled')
        self.install_button.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self.destroy)
        self.cancel_button.pack(side='right', fill='x', expand=True, padx=(5, 0))


    def _create_status_label(self, parent_frame: ttk.LabelFrame, text: str) -> ttk.Label:
        frame = ttk.Frame(parent_frame, style='TFrame')
        frame.pack(fill='x', pady=2)
        
        ttk.Label(frame, text=text, width=25, anchor='w', style='TLabel').pack(side='left')
        status_label = ttk.Label(frame, text="Checking...", style='Status.TLabel', foreground='orange') 
        status_label.pack(side='right', anchor='e')
        return status_label

    def update_log(self, message: str, color: str = None):
        """Aktualisiert das Log-Fenster im Haupt-Thread (safe call)."""
        def do_update():
            self.log_text.config(state='normal')
            tag_name = ""
            if color:
                tag_name = f"color_{color}"
                if tag_name not in self.log_text.tag_names():
                    self.log_text.tag_config(tag_name, foreground=color)
            
            self.log_text.insert('end', f"[{time.strftime('%H:%M:%S')}] {message}\n", tag_name if color else "")
            self.log_text.see('end')
            self.log_text.config(state='disabled')
            self.update_idletasks()

        if threading.current_thread() != threading.main_thread():
            self.after(0, do_update)
        else:
            do_update()

    def _set_status_label(self, label: ttk.Label, text: str, color: str):
        label.config(text=text, foreground=color)
        self.update_idletasks() 

    def _browse_for_folder(self):
        folder_selected = filedialog.askdirectory(parent=self, title="Select Installation Directory")
        if folder_selected:
            target_path = Path(folder_selected)
            if not target_path.name.lower().endswith(DEFAULT_INSTALL_DIR_SUFFIX.lower()):
                target_path = target_path / DEFAULT_INSTALL_DIR_SUFFIX
            self.install_path_entry.delete(0, 'end')
            self.install_path_entry.insert(0, str(target_path))


    def _check_docker_status(self) -> bool:
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
            return result.returncode == 0
        except: return False

    def _check_git_status(self) -> bool:
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return result.returncode == 0
        except: return False

    def _check_internet_status(self) -> bool:
        try:
            requests.head("http://www.google.com", timeout=3)
            return True
        except: return False

    def _run_initial_checks_start(self):
        """Startet den Thread für die Systemprüfung."""
        threading.Thread(target=self._run_initial_checks_threaded, daemon=True).start()

    def _run_initial_checks_threaded(self):
        """Führt alle System-Checks im Thread aus."""
        try:
            self.update_log("Führe Systemvoraussetzungen-Checks durch...", "orange")

            docker_ok = self._check_docker_status()
            self._set_status_label(self.docker_status, "OK" if docker_ok else "NOT FOUND", "green" if docker_ok else "red")
            
            git_ok = self._check_git_status()
            self._set_status_label(self.git_status, "OK" if git_ok else "NOT FOUND", "green" if git_ok else "red")
            
            internet_ok = self._check_internet_status()
            self._set_status_label(self.internet_status, "OK" if internet_ok else "FAILED", "green" if internet_ok else "red")

            if not docker_ok:
                self.update_log("KRITISCH: Docker Desktop ist erforderlich und läuft nicht. Installation gesperrt.", "red")
            
            if docker_ok: 
                self.after(0, lambda: self.install_button.config(state='normal'))
                self.update_log("Alle Kern-Voraussetzungen erfüllt. Bereit zur Installation.", "green")
            else:
                self.after(0, lambda: self.install_button.config(state='disabled'))

        except Exception as e:
            self.update_log(f"Error during system check: {e}", "red")

    def _start_installation(self):
        
        target_dir = Path(self.install_path_entry.get()).resolve()
        desktop_shortcut = self.desktop_shortcut_checkbox.instate(['selected'])
        
        if not target_dir.parent.exists():
            messagebox.showerror("Invalid Path", f"The parent directory for {target_dir} does not exist.")
            return

        self.install_button.config(state='disabled')
        self.cancel_button.config(state='disabled')
        
        # Setze den Wert auf die Variable
        self.progress_var.set(0) 
        self.update_log("Installation gestartet...", "blue")

        # Worker und Thread erstellen
        self.current_install_thread = InstallationWorker(target_dir, desktop_shortcut, self.update_log, self.update_progress)
        self.current_install_thread.start()
        self.after(500, self._check_installation_progress)

    def update_progress(self, percent: int, message: str):
        """Wird vom Worker-Thread aufgerufen, muss in den Haupt-Thread zurück."""
        def do_update():
            # Setze den Wert auf die Variable
            self.progress_var.set(percent)
            # Log-Nachricht nur aktualisieren, wenn sie nicht leer ist (oder 100%)
            if message or percent == 100:
                 self.update_log(message)
        
        self.after(0, do_update)

    def _check_installation_progress(self):
        if self.current_install_thread and self.current_install_thread.is_alive():
            self.after(500, self._check_installation_progress)
        else:
            if self.current_install_thread:
                success = self.current_install_thread.success
                message = self.current_install_thread.message
                
                if success:
                    self.progress_var.set(100)
                    self.update_log("✅ Installation erfolgreich abgeschlossen.", "green")
                    messagebox.showinfo("Installation Complete", message)
                    self.destroy()
                else:
                    self.progress_var.set(0)
                    self.update_log(f"❌ Installation fehlgeschlagen:\n{message}", "red")
                    messagebox.showerror("Installation Failed", f"Ein Fehler ist aufgetreten:\n{message}")
                    self.install_button.config(state='normal')
                    self.cancel_button.config(state='normal')


if __name__ == '__main__':
    app = InstallerWindow()
    app.mainloop()
