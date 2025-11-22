#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Full Repo Install - Tkinter GUI)
DIREKTIVE: Goldstandard, erlaubt Auto-Updates durch Inklusion des .git Ordners.
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
import requests 

# Tkinter Imports
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
except ImportError:
    print("FATAL ERROR: Tkinter is not available. Installation requires Tkinter.")
    sys.exit(1)


# --- KONFIGURATION ---
INSTALL_APP_NAME = "LLM-Builder"
DEFAULT_INSTALL_DIR_SUFFIX = "LLM-Framework"
MSVC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
MSVC_REDIST_FILENAME = "vc_redist.x64.exe"

# KORRIGIERT: .git wurde aus der Ignore-Liste ENTFERNT, damit Updates funktionieren!
IGNORE_PATTERNS = shutil.ignore_patterns(
    ".gitignore", ".gitattributes",
    ".venv", "venv", "env",
    "__pycache__", "*.pyc", "*.pyd",
    "dist", "build", "*.spec",
    "output", "cache", "logs", 
    "tmp", "temp"
)

# ... [Rest der Imports und Utility Funktionen wie _find_repo_root_at_runtime bleiben identisch] ...
# (Ich füge hier den relevanten geänderten Teil der `install_application` Funktion ein)

def _find_repo_root_at_runtime() -> Optional[Path]:
    if getattr(sys, 'frozen', False): 
        start_path = Path(sys.executable).parent
    else: 
        start_path = Path(__file__).resolve().parent
    current_path = start_path
    REPO_ROOT_MARKERS = ["targets", "orchestrator"]
    for _ in range(10): 
        if all((current_path / marker).exists() for marker in REPO_ROOT_MARKERS):
            return current_path
        parent = current_path.parent
        if parent == current_path: break
        current_path = parent
    return None

def _create_shortcut(target_exe_path: Path, working_directory: Path, icon_path: Optional[Path] = None) -> bool:
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    shortcut_path = os.path.join(desktop, f"{INSTALL_APP_NAME}.lnk")
    try:
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
        with open(vbs_file, "w") as f: f.write(vbs_script)
        subprocess.run(["cscript", "//Nologo", str(vbs_file)], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        vbs_file.unlink()
        return True
    except Exception: return False

def install_application(destination_path: Path, desktop_shortcut: bool, log_callback: Callable, progress_callback: Callable):
    repo_root = _find_repo_root_at_runtime()
    if not repo_root: raise Exception("CRITICAL: Repository-Root nicht gefunden.")
    
    log_callback(f"Repository-Root gefunden unter: {repo_root}", "info")
    progress_callback(5, "Starte Installation...")
    
    if destination_path.exists():
        shutil.rmtree(destination_path)
        log_callback("Bestehende Installation gelöscht.", "info")
    destination_path.mkdir(parents=True, exist_ok=True)

    log_callback("Kopiere Framework-Dateien (inkl. Git-History)...", "info")
    progress_callback(20, "Kopiere Dateien...")
    
    # WICHTIG: Custom Ignore, das 'dist' ausschließt aber .git erlaubt (durch globale Variable oben gesteuert)
    def custom_ignore(directory, contents):
        ignored = IGNORE_PATTERNS(directory, contents)
        if Path(directory).resolve() == repo_root.resolve():
            return list(ignored) + ['dist', 'build']
        return ignored

    shutil.copytree(repo_root, destination_path, ignore=custom_ignore, dirs_exist_ok=True)
    
    # Launcher kopieren (Annahme: LLM-Builder.exe liegt neben dem Installer)
    installer_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else repo_root / "dist"
    launcher_src = installer_dir / f"{INSTALL_APP_NAME}.exe" 
    launcher_dst = destination_path / f"{INSTALL_APP_NAME}.exe"

    if not launcher_src.exists():
         # Fallback: Versuche es im dist folder des repo_root
         launcher_src = repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"
    
    if launcher_src.exists():
        log_callback("Kopiere Launcher...", "info")
        shutil.copy2(launcher_src, launcher_dst)
    else:
        log_callback("WARNUNG: LLM-Builder.exe nicht gefunden. Update wird später benötigt.", "warning")

    icon_src = repo_root / f"{INSTALL_APP_NAME}.ico"
    if icon_src.exists(): shutil.copy2(icon_src, destination_path / f"{INSTALL_APP_NAME}.ico")
    for d in ["output", "cache", "logs"]: (destination_path / d).mkdir(exist_ok=True)
    
    log_callback("Basiskonfiguration abgeschlossen.", "success")
    progress_callback(50, "Konfiguration fertig.")

    if desktop_shortcut:
        log_callback("Erstelle Desktop-Verknüpfung...", "info")
        _create_shortcut(launcher_dst, destination_path, destination_path / f"{INSTALL_APP_NAME}.ico")
    
    log_callback("Installation erfolgreich abgeschlossen.", "success")

# ... [Rest der Datei (InstallationWorker, InstallerWindow) bleibt identisch zur letzten Version] ...
# Bitte kopieren Sie den Rest der GUI-Klasse aus der vorherigen finalen Version.
# Der entscheidende Unterschied ist oben in der IGNORE_PATTERNS Variable.

class InstallationWorker(threading.Thread):
    def __init__(self, target_dir: Path, desktop_shortcut: bool, log_callback: Callable, progress_callback: Callable):
        super().__init__(daemon=True)
        self.target_dir = target_dir
        self.desktop_shortcut = desktop_shortcut
        self.log = log_callback
        self.progress_update = progress_callback
        self.success = False
        self.message = ""

    def _check_internet_status(self):
        try: requests.head("http://www.google.com", timeout=3); return True
        except: return False

    def _install_msvc_redistributable(self):
        temp_dir = Path(tempfile.gettempdir())
        msvc_path = temp_dir / MSVC_REDIST_FILENAME
        self.log(f"Prüfe auf MSVC Redistributable...", "info")
        if not msvc_path.exists():
            self.log(f"Lade MSVC Redistributable...", "warning")
            try:
                response = requests.get(MSVC_REDIST_URL, stream=True, timeout=30)
                with open(msvc_path, 'wb') as f: f.write(response.content)
            except Exception as e: 
                self.log(f"FEHLER MSVC Download: {e}", "error"); return
        try:
            subprocess.run([str(msvc_path), "/install", "/quiet", "/norestart"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.log("MSVC installiert.", "success")
        except: self.log("MSVC Installation fehlgeschlagen.", "error")

    def _pre_pull_docker(self):
        images = ["debian:bookworm-slim"]
        for img in images:
            if self._check_internet_status():
                self.progress_update(70, f"Pre-Pull: {img}...")
                try: subprocess.run(["docker", "pull", img], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
                except: pass

    def run(self):
        try:
            self.progress_update(0, "Installiere MSVC...")
            self._install_msvc_redistributable()
            install_application(self.target_dir, self.desktop_shortcut, self.log, self.progress_update)
            self._pre_pull_docker()
            self.progress_update(100, "Fertig.")
            self.success = True
            self.message = "Installation erfolgreich."
        except Exception as e:
            self.success = False
            self.message = str(e)

class InstallerWindow(tk.Tk):
    COLOR_MAPPING = {"info": "blue", "success": "green", "error": "red", "warning": "orange", "normal": "black"}
    def __init__(self):
        super().__init__()
        self.title(f"Install {INSTALL_APP_NAME}")
        self.geometry("600x550")
        self.current_install_thread = None
        self.progress_var = tk.DoubleVar(value=0)
        self._init_ui()
        self.after(100, lambda: threading.Thread(target=self._run_checks, daemon=True).start())

    def _init_ui(self):
        self.style = ttk.Style(self); self.style.theme_use('clam')
        main = ttk.Frame(self, padding=10); main.pack(fill='both', expand=True)
        ttk.Label(main, text="Setup", font=('Arial', 16)).pack(pady=10)
        
        self.path_ent = ttk.Entry(main); self.path_ent.pack(fill='x', pady=5)
        self.path_ent.insert(0, str(Path(os.getenv('LOCALAPPDATA')) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX))
        
        self.log = ScrolledText(main, height=10); self.log.pack(fill='both', expand=True, pady=10)
        self.prog = ttk.Progressbar(main, variable=self.progress_var); self.prog.pack(fill='x', pady=5)
        self.btn = ttk.Button(main, text="Install", command=self._start); self.btn.pack(pady=5)

    def update_log(self, msg, color="normal"):
        self.after(0, lambda: self.log.insert('end', f"{msg}\n", self.log.tag_config(color, foreground=self.COLOR_MAPPING.get(color, "black")) or color))

    def _run_checks(self):
        # Simplified checks
        self.update_log("System Checks...", "info")

    def _start(self):
        self.btn.config(state='disabled')
        target = Path(self.path_ent.get())
        self.current_install_thread = InstallationWorker(target, True, self.update_log, self.update_p)
        self.current_install_thread.start()
        self._monitor()

    def update_p(self, val, msg=""):
        self.after(0, lambda: (self.progress_var.set(val), self.update_log(msg) if msg else None))

    def _monitor(self):
        if self.current_install_thread.is_alive(): self.after(500, self._monitor)
        else: messagebox.showinfo("Done", self.current_install_thread.message) if self.current_install_thread.success else messagebox.showerror("Error", self.current_install_thread.message); self.destroy()

if __name__ == '__main__': app = InstallerWindow(); app.mainloop()
