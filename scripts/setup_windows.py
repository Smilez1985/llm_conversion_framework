#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Full Repo Install - Tkinter GUI)
DIREKTIVE: Goldstandard, vollständig, Text-basiert (Tkinter), Netzwerk-Resilient.

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
from typing import Optional, List
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
# UTILITY FUNKTIONEN
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
    """Erstellt einen Desktop-Shortcut."""
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    shortcut_path = os.path.join(desktop, f"{INSTALL_APP_NAME}.lnk")
    
    try:
        # VBScript als Fallback, da pywin32 nicht garantiert ist
        target_exe_str = str(target_exe_path.absolute()).replace("\\", "\\\\")
        working_dir_str = str(working_directory.absolute()).replace("\\", "\\\\")
        icon_location_str = str(icon_path.absolute()).replace("\\", "\\\\") if icon_path and icon_path.exists() else ""
        
        vbs_script = f"""
        Set oWS = WScript.CreateObject("WScript.Shell")
        sLinkFile = "{shortcut_path}"
        Set oLink = oWS.CreateShortcut(sLinkFile)
        oLink.TargetPath = "{target_exe_path}"
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
# INSTALLER THREAD LOGIC
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
                        self.log(f"Image '{img}' erfolgreich gepullt.")
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
            self.repo_root = _find_repo_root_at_runtime()
            if not self.repo_root:
                raise Exception("CRITICAL: Repository-Root nicht gefunden. Installation fehlgeschlagen.")

            # 1. Zielordner vorbereiten
            self.progress(5, f"Bereite Zielordner '{self.target_dir}' vor...")
            if self.target_dir.exists():
                shutil.rmtree(self.target_dir)
            self.target_dir.mkdir(parents=True, exist_ok=True)

            # 2. Kopiere das Repo-Gerüst
            self.progress(20, "Kopiere Framework-Dateien...")
            shutil.copytree(self.repo_root, self.target_dir, ignore=IGNORE_PATTERNS, dirs_exist_ok=True)

            # 3. Launcher kopieren
            launcher_src = self.repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"
            launcher_dst = self.target_dir / f"{INSTALL_APP_NAME}.exe"
            if not launcher_src.exists():
                 raise Exception(f"KRITISCH: Launcher EXE nicht gefunden unter: {launcher_src}. Bitte zuerst kompilieren!")
            
            self.progress(40, "Kopiere den signierten Launcher...")
            shutil.copy2(launcher_src, launcher_dst)

            # 4. Icon und leere Ordner erstellen
            icon_src = self.repo_root / f"{INSTALL_APP_NAME}.ico"
            if icon_src.exists():
                shutil.copy2(icon_src, self.target_dir / f"{INSTALL_APP_NAME}.ico")
            
            for d in ["output", "cache", "logs"]:
                (self.target_dir / d).mkdir(exist_ok=True)
            self.progress(50, "Basiskonfiguration abgeschlossen.")

            # 5. Desktop-Shortcut erstellen
            if self.desktop_shortcut:
                self.progress(60, "Erstelle Desktop-Verknüpfung...")
                _create_shortcut(launcher_dst, self.target_dir, self.target_dir / f"{INSTALL_APP_NAME}.ico")

            # 6. Docker Pre-Pull
            self.progress(70, "Starte Docker Pre-Pull...")
            self._pre_pull_docker()
            
            self.success = True
            self.message = "Installation erfolgreich abgeschlossen."

        except Exception as e:
            self.success = False
            self.message = str(e)


# ============================================================================
# INSTALLER GUI (TKINTER)
# ============================================================================

class InstallerWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Install {INSTALL_APP_NAME}")
        # WICHTIGE LAYOUT-ANPASSUNG: Mindestgröße setzen, aber nicht fixieren
        self.geometry("600x550")
        self.resizable(False, False)
        
        self.current_install_thread: Optional[InstallationWorker] = None
        self.after_id = None # Für Timer
        
        self._init_ui()
        self.after(100, self._initial_checks)

    def _init_ui(self):
        # --- Styling (Basic) ---
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('TFrame', background='#e0e0e0')
        
        # --- Main Frame (Trägt alles) ---
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
        # Log-Fenster mit ScrolledText für unendliche Größe und Fixierung
        self.log_text = ScrolledText(main_frame, wrap='word', height=8, state='disabled', font=('Courier New', 9), bg='#333', fg='#0f0')
        self.log_text.pack(fill='x', pady=(0, 5)) # Füllt die Breite

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill='x', pady=5)

        # --- Buttons Frame (WICHTIG: Soll ganz unten fixiert sein) ---
        button_frame = ttk.Frame(main_frame, style='TFrame')
        button_frame.pack(fill='x', pady=10) 
        
        self.install_button = ttk.Button(button_frame, text="Install", command=self._start_installation, state='disabled')
        self.install_button.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self.destroy)
        self.cancel_button.pack(side='right', fill='x', expand=True, padx=(5, 0))


    def _create_status_label(self, parent_frame: ttk.LabelFrame, text: str) -> ttk.Label:
        """Erstellt ein Label für Statusanzeigen."""
        frame = ttk.Frame(parent_frame, style='TFrame')
        frame.pack(fill='x', pady=2)
        
        ttk.Label(frame, text=text, width=25, anchor='w', style='TLabel').pack(side='left')
        status_label = ttk.Label(frame, text="Checking...", style='Status.TLabel') 
        status_label.pack(side='right', anchor='e')
        return status_label

    def update_log(self, message: str, color: str = None):
        self.log_text.config(state='normal')
        tag_name = ""
        if color:
            tag_name = f"color_{color}"
            self.log_text.tag_config(tag_name, foreground=color)
        
        self.log_text.insert('end', f"[{time.strftime('%H:%M:%S')}] {message}\n", tag_name if color else "")
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        self.update_idletasks() 

    def _browse_for_folder(self):
        folder_selected = filedialog.askdirectory(parent=self, title="Select Installation Directory")
        if folder_selected:
            target_path = Path(folder_selected)
            if not target_path.name.lower().endswith(DEFAULT_INSTALL_DIR_SUFFIX.lower()):
                target_path = target_path / DEFAULT_INSTALL_DIR_SUFFIX
            self.install_path_var.set(str(target_path))

    def _set_status_label(self, label: ttk.Label, text: str, color: str):
        label.config(text=text, foreground=color)
        self.update_idletasks() 

    def _check_docker_status(self) -> bool:
        try:
            # Stummer Aufruf, da die Fehlermeldung nur im Log relevant ist
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
        except requests.exceptions.RequestException:
            return False
        except Exception:
            return False

    def _initial_checks(self):
        self.update_log("Führe Systemvoraussetzungen-Checks durch...")
        
        # --- Docker Check ---
        docker_ok = self._check_docker_status()
        self._set_status_label(self.docker_status, "OK" if docker_ok else "NOT FOUND", "green" if docker_ok else "red")
        
        # --- Git Check ---
        git_ok = self._check_git_status()
        self._set_status_label(self.git_status, "OK" if git_ok else "NOT FOUND", "green" if git_ok else "red")
        
        # --- Internet Check ---
        internet_ok = self._check_internet_status()
        self._set_status_label(self.internet_status, "OK" if internet_ok else "FAILED", "green" if internet_ok else "red")
        
        # --- Kritische Prüfung und Log-Meldung ---
        if not docker_ok:
            self.update_log("\nKRITISCH: Docker Desktop ist nicht gefunden oder läuft nicht.", "red")
            self.update_log("Bitte installieren Sie Docker Desktop (mit WSL2-Integration), bevor Sie das Framework nutzen.", "red")
        
        if not git_ok:
            self.update_log("WARNUNG: Git ist nicht installiert. Auto-Updates werden nicht funktionieren.", "orange")

        if docker_ok: 
            self.install_button.config(state='normal')
            self.update_log("Alle Kern-Voraussetzungen erfüllt. Bereit zur Installation.")
        else:
            self.install_button.config(state='disabled')


    def _check_installation_progress(self):
        if self.current_install_thread and self.current_install_thread.is_alive():
            self.after(500, self._check_installation_progress)
        else:
            # Ergebnisse werden im Thread verarbeitet und der Log-Call ist final
            pass


if __name__ == '__main__':
    # Initialisiere Win32-COM für Desktop-Shortcuts (VBScript wird verwendet)
    try:
        import win32com.client # Test, ob pywin32 vorhanden ist (für die Shortcut-Erstellung)
    except ImportError:
        print("WARNUNG: 'pywin32' ist nicht installiert. Desktop-Shortcuts werden über VBScript erstellt.")

    app = InstallerWindow()
    app.mainloop()
