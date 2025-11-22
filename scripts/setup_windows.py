#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Smart Update & ETA)
DIREKTIVE: Goldstandard.
           1. CLI-Support (--update) für automatisierten Start.
           2. ETA (Time Remaining) Berechnung im UI.
           3. Auto-Launch der Hauptanwendung nach Update.
"""

import os
import sys
import shutil
import subprocess
import time
import socket
import threading
import tempfile
import hashlib
import argparse # NEU: Für CLI Argumente
from pathlib import Path
from typing import Optional, List, Callable, Set
import requests 

# Windows Registry Zugriff für MSVC Check
try:
    import winreg
except ImportError:
    winreg = None

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
except ImportError:
    print("FATAL ERROR: Tkinter is not available.")
    sys.exit(1)


# --- KONFIGURATION ---
INSTALL_APP_NAME = "LLM-Builder"
DEFAULT_INSTALL_DIR_SUFFIX = "LLM-Framework"

MSVC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
MSVC_REDIST_FILENAME = "vc_redist.x64.exe"

IGNORED_NAMES = {
    ".gitignore", ".gitattributes", ".venv", "venv", "env",
    "__pycache__", "dist", "build", ".spec", "tmp", "temp"
}
IGNORED_EXTENSIONS = {".pyc", ".pyd", ".spec"}
FRAMEWORK_CORE_FOLDERS = ["orchestrator", "scripts", "configs", "docker"]

# ============================================================================
# UTILITY FUNCTIONS (MSVC, HASHING) - Identisch zur Vorversion
# ============================================================================

def _is_msvc_installed() -> bool:
    if not winreg: return False
    try:
        path = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
        installed, _ = winreg.QueryValueEx(key, "Installed")
        winreg.CloseKey(key)
        return installed == 1
    except OSError: return False

def _calculate_file_hash(filepath: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192): hasher.update(chunk)
        return hasher.hexdigest()
    except Exception: return ""

def _should_copy(src: Path, dst: Path) -> bool:
    if not dst.exists(): return True
    if src.stat().st_size != dst.stat().st_size: return True
    return _calculate_file_hash(src) != _calculate_file_hash(dst)

def _is_ignored(path: Path) -> bool:
    if path.name in IGNORED_NAMES: return True
    if path.suffix in IGNORED_EXTENSIONS: return True
    return False

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

def _sync_recursive(src_dir: Path, dst_dir: Path, log_callback: Callable, counter: list):
    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if _is_ignored(item): continue
        src_path = item
        dst_path = dst_dir / item.name
        if src_path.is_dir():
            _sync_recursive(src_path, dst_path, log_callback, counter)
        else:
            if _should_copy(src_path, dst_path):
                try:
                    shutil.copy2(src_path, dst_path)
                    counter[0] += 1
                except Exception as e:
                    log_callback(f"Error copying {src_path.name}: {e}", "error")

def _perform_differential_update(src_root: Path, dst_root: Path, log_callback: Callable):
    counter = [0]
    log_callback(f"Prüfe Änderungen (Smart Sync)...", "info")
    _sync_recursive(src_root, dst_root, log_callback, counter)
    if counter[0] == 0: log_callback("Alles aktuell.", "success")
    else: log_callback(f"{counter[0]} Dateien aktualisiert.", "success")

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
    
    destination_path.mkdir(parents=True, exist_ok=True)
    progress_callback(10, "Synchronisiere Systemdateien...")
    _perform_differential_update(repo_root, destination_path, log_callback)
    
    progress_callback(80, "Aktualisiere Launcher...")
    installer_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else repo_root / "dist"
    launcher_src = installer_dir / f"{INSTALL_APP_NAME}.exe" 
    
    if not launcher_src.exists(): launcher_src = repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"
    if launcher_src.exists():
        launcher_dst = destination_path / f"{INSTALL_APP_NAME}.exe"
        if _should_copy(launcher_src, launcher_dst):
            try: shutil.copy2(launcher_src, launcher_dst)
            except: pass 

    icon_src = repo_root / f"{INSTALL_APP_NAME}.ico"
    if icon_src.exists(): shutil.copy2(icon_src, destination_path / f"{INSTALL_APP_NAME}.ico")
    for d in ["output", "cache", "logs"]: (destination_path / d).mkdir(exist_ok=True)
    
    progress_callback(90, "Finalisiere...")
    if desktop_shortcut and launcher_src.exists():
        _create_shortcut(destination_path / f"{INSTALL_APP_NAME}.exe", destination_path, destination_path / f"{INSTALL_APP_NAME}.ico")
    
    log_callback("Update erfolgreich abgeschlossen.", "success")


# ============================================================================
# WORKER THREAD (MIT ETA LOGIK)
# ============================================================================

class InstallationWorker(threading.Thread):
    def __init__(self, target_dir: Path, desktop_shortcut: bool, log_callback: Callable, progress_callback: Callable):
        super().__init__(daemon=True)
        self.target_dir = target_dir
        self.desktop_shortcut = desktop_shortcut
        self.log = log_callback
        self.progress_update = progress_callback # raw callback
        self.success = False
        self.message = ""
        self.start_time = 0
    
    def _smart_progress(self, percent: int, message: str = ""):
        """Berechnet ETA und formatiert die Nachricht."""
        if self.start_time == 0: self.start_time = time.time()
        
        elapsed = time.time() - self.start_time
        eta_str = ""
        
        if percent > 0 and percent < 100:
            # Simple lineare Extrapolation
            total_estimated = elapsed / (percent / 100.0)
            remaining = total_estimated - elapsed
            if remaining < 60:
                eta_str = f" (noch ca. {int(remaining)}s)"
            else:
                eta_str = f" (noch ca. {int(remaining/60)}m {int(remaining%60)}s)"
        
        full_msg = f"{message}{eta_str}" if message else ""
        self.progress_update(percent, full_msg)

    def _check_internet_status(self):
        try: requests.head("http://www.google.com", timeout=3); return True
        except: return False

    def _handle_msvc(self):
        if _is_msvc_installed():
            self.log("MSVC Runtime: OK", "success")
            return
        
        self.log("MSVC Runtime fehlt. Starte Installation...", "warning")
        temp_dir = Path(tempfile.gettempdir())
        msvc_path = temp_dir / MSVC_REDIST_FILENAME
        
        if not msvc_path.exists():
            if not self._check_internet_status(): return
            try:
                response = requests.get(MSVC_REDIST_URL, stream=True, timeout=60)
                with open(msvc_path, 'wb') as f: f.write(response.content)
            except: return

        try:
            subprocess.run([str(msvc_path), "/install", "/quiet", "/norestart"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.log("MSVC installiert.", "success")
        except: pass

    def _pre_pull_docker(self):
        # Nur wenn Internet da ist und Docker läuft
        if not self._check_internet_status(): return
        try:
             subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
             self._smart_progress(70, "Lade Docker Images...")
             subprocess.run(["docker", "pull", "debian:bookworm-slim"], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        except: pass

    def run(self):
        try:
            self.start_time = time.time()
            self._smart_progress(5, "Prüfe Voraussetzungen...")
            self._handle_msvc()
            
            install_application(self.target_dir, self.desktop_shortcut, self.log, self._smart_progress)
            
            self._pre_pull_docker()
            self._smart_progress(100, "Fertig.")
            self.success = True
            self.message = "Update erfolgreich."
        except Exception as e:
            self.success = False
            self.message = str(e)

# ============================================================================
# GUI
# ============================================================================

class InstallerWindow(tk.Tk):
    COLOR_MAPPING = {"info": "blue", "success": "green", "error": "red", "warning": "orange", "normal": "black"}
    
    def __init__(self, auto_start=False):
        super().__init__()
        self.title(f"Install {INSTALL_APP_NAME}")
        self.geometry("600x550")
        self.current_install_thread = None
        self.progress_var = tk.DoubleVar(value=0)
        self.auto_start = auto_start
        
        self._init_ui()
        
        # Wenn Auto-Start (via CLI Update), dann sofort loslegen
        if self.auto_start:
            self.after(500, self._start)
        else:
            self.after(100, lambda: threading.Thread(target=self._run_checks, daemon=True).start())

    def _init_ui(self):
        self.style = ttk.Style(self); self.style.theme_use('clam')
        main = ttk.Frame(self, padding=10); main.pack(fill='both', expand=True)
        
        title_text = "System-Update" if self.auto_start else "Setup Assistant"
        ttk.Label(main, text=title_text, font=('Arial', 16, 'bold')).pack(pady=10)
        
        self.path_ent = ttk.Entry(main); self.path_ent.pack(fill='x', pady=5)
        default_path = Path(os.getenv('LOCALAPPDATA')) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX
        self.path_ent.insert(0, str(default_path))
        
        self.check_sc = ttk.Checkbutton(main, text="Desktop Shortcut"); self.check_sc.pack(anchor='w')
        self.check_sc.state(['!alternate', 'selected'])
        
        self.log = ScrolledText(main, height=10, font=('Consolas', 9)); self.log.pack(fill='both', expand=True, pady=10)
        
        # Progress Frame mit Zeit-Label
        prog_frame = ttk.Frame(main)
        prog_frame.pack(fill='x', pady=5)
        self.prog = ttk.Progressbar(prog_frame, variable=self.progress_var, maximum=100)
        self.prog.pack(fill='x', side='top')
        self.status_lbl = ttk.Label(prog_frame, text="Bereit...", font=('Arial', 8))
        self.status_lbl.pack(anchor='e')

        self.btn = ttk.Button(main, text="Installieren", command=self._start); self.btn.pack(pady=5)
        if self.auto_start: self.btn.config(state='disabled', text="Update läuft...")

    def update_log(self, msg, color="normal"):
        self.after(0, lambda: self.log.insert('end', f"{msg}\n", self.log.tag_config(color, foreground=self.COLOR_MAPPING.get(color, "black")) or color))
        self.after(0, lambda: self.log.see('end'))

    def _run_checks(self):
        self.update_log("Initiale Prüfung...", "info")
        if _is_msvc_installed(): self.update_log("MSVC Runtime: OK", "success")

    def _start(self):
        self.btn.config(state='disabled')
        target = Path(self.path_ent.get())
        sc = self.check_sc.instate(['selected'])
        self.current_install_thread = InstallationWorker(target, sc, self.update_log, self.update_p)
        self.current_install_thread.start()
        self._monitor()

    def update_p(self, val, msg=""):
        def _u():
            self.progress_var.set(val)
            if msg: 
                self.status_lbl.config(text=msg) # Status Label updaten (mit ETA)
                # Optional: Auch ins Log schreiben, aber nicht zu oft
                if val % 10 == 0: self.update_log(msg, "info")
        self.after(0, _u)

    def _monitor(self):
        if self.current_install_thread.is_alive(): 
            self.after(500, self._monitor)
        else: 
            if self.current_install_thread.success:
                self.update_log("FERTIG! Starte Anwendung...", "success")
                # Auto-Launch nach Update
                exe_path = Path(self.path_ent.get()) / f"{INSTALL_APP_NAME}.exe"
                if exe_path.exists():
                    subprocess.Popen(str(exe_path), shell=True)
                
                if self.auto_start:
                    self.after(2000, self.destroy)
                else:
                    messagebox.showinfo("Erfolg", "Installation abgeschlossen.")
                    self.destroy()
            else:
                messagebox.showerror("Fehler", self.current_install_thread.message)
                self.btn.config(state='normal', text="Wiederholen")

if __name__ == '__main__': 
    # Argument Parsing für Update-Modus
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="Start in auto-update mode")
    args, unknown = parser.parse_known_args()

    try:
        app = InstallerWindow(auto_start=args.update)
        app.mainloop()
    except Exception as e:
        from tkinter import messagebox
        messagebox.showerror("Fatal Error", str(e))
