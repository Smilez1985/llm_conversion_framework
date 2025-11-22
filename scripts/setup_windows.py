#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Smart Update & User Preservation)
DIREKTIVE: Goldstandard.
           1. MSVC: Nur installieren wenn nötig (Registry-Check), Download cachen.
           2. Update: Core-Files überschreiben, aber USER-MODULE in 'targets/' erhalten.
           3. Git: .git Ordner wird mitkopiert für Auto-Updates.
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

# Windows Registry Zugriff für MSVC Check
try:
    import winreg
except ImportError:
    # Fallback für Nicht-Windows Umgebungen (z.B. beim Testen), obwohl das Script setup_windows heißt
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

# .git ist NICHT im Ignore, damit Updates funktionieren
IGNORE_PATTERNS = shutil.ignore_patterns(
    ".gitignore", ".gitattributes",
    ".venv", "venv", "env",
    "__pycache__", "*.pyc", "*.pyd",
    "dist", "build", "*.spec",
    "tmp", "temp"
)

# Ordner, die das Framework als "seine eigenen" betrachtet und bei Updates überschreiben darf.
# Alles andere in 'targets/' wird als User-Modul betrachtet und geschützt.
FRAMEWORK_CORE_FOLDERS = ["orchestrator", "scripts", "configs", "docker"]

# ============================================================================
# LOGIK: MSVC PRÜFUNG
# ============================================================================

def _is_msvc_installed() -> bool:
    """Prüft via Registry, ob VC++ 2015-2022 (x64) Runtime installiert ist."""
    if not winreg: return False
    try:
        # GUID für VC++ 2022 Redist x64 (kann variieren, wir prüfen den generischen Key)
        # Ein zuverlässigerer Weg ist die Prüfung auf den Uninstall-Key oder Dependencies
        # Hier prüfen wir einen bekannten Key für VS 2015-2022
        path = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
        installed, _ = winreg.QueryValueEx(key, "Installed")
        winreg.CloseKey(key)
        return installed == 1
    except OSError:
        return False

# ============================================================================
# LOGIK: DATEI-OPERATIONEN
# ============================================================================

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

def _smart_copy_tree(src: Path, dst: Path, log_callback: Callable):
    """
    Kopiert Dateien intelligent:
    1. Core-Ordner im Ziel werden bereinigt und neu kopiert (sauberes Update).
    2. 'targets/': Nur Framework-Standard-Targets werden überschrieben. User-Ordner bleiben!
    3. .git: Wird komplett synchronisiert.
    """
    
    # 1. Erstelle Zielordner falls nicht existent
    dst.mkdir(parents=True, exist_ok=True)

    # Helper für Ignore
    def _get_ignored(path, names):
        return IGNORE_PATTERNS(path, names)

    # Iteriere über Root-Elemente im Quell-Repo
    for item in src.iterdir():
        if item.name in _get_ignored(src, [item.name]):
            continue

        dst_item = dst / item.name

        # SPEZIALFALL: TARGETS ORDNER (User Modules schützen!)
        if item.name == "targets" and item.is_dir():
            log_callback(f"Synchronisiere Targets (User-Module bleiben erhalten)...", "info")
            dst_item.mkdir(exist_ok=True)
            
            # Iteriere durch die Targets im QUELL-Repo
            for target_src in item.iterdir():
                if not target_src.is_dir(): continue
                target_dst = dst_item / target_src.name
                
                # Wenn es ein Framework-Target ist -> Überschreiben (Update erzwingen)
                # Wir gehen davon aus: Alles was im Source-Repo ist, ist Framework-Standard.
                if target_dst.exists():
                    shutil.rmtree(target_dst) # Lösche alte Version im Ziel
                
                shutil.copytree(target_src, target_dst, ignore=IGNORE_PATTERNS)
            
            # WICHTIG: Wir löschen NICHTS in dst/targets, was nicht in src/targets ist!
            # Das schützt "targets/my_custom_npu".
            continue

        # STANDARD: Core Ordner/Dateien (orchestrator, scripts, etc.)
        # Alte Version im Ziel löschen, neue kopieren
        if dst_item.exists():
            if dst_item.is_dir():
                shutil.rmtree(dst_item)
            else:
                dst_item.unlink()
        
        if item.is_dir():
            shutil.copytree(item, dst_item, ignore=IGNORE_PATTERNS)
        else:
            shutil.copy2(item, dst_item)

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
    
    log_callback(f"Quelle: {repo_root}", "info")
    log_callback(f"Ziel: {destination_path}", "info")
    
    progress_callback(10, "Starte Smart-Update...")
    
    # Smart Copy (Schützt User-Targets)
    _smart_copy_tree(repo_root, destination_path, log_callback)
    
    progress_callback(40, "Kopiere Launcher...")
    
    # Launcher kopieren
    installer_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else repo_root / "dist"
    launcher_src = installer_dir / f"{INSTALL_APP_NAME}.exe" 
    
    if not launcher_src.exists():
         launcher_src = repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"

    if launcher_src.exists():
        launcher_dst = destination_path / f"{INSTALL_APP_NAME}.exe"
        shutil.copy2(launcher_src, launcher_dst)
    else:
        log_callback("WARNUNG: Launcher EXE nicht gefunden.", "warning")

    # Configs & Assets
    icon_src = repo_root / f"{INSTALL_APP_NAME}.ico"
    if icon_src.exists(): shutil.copy2(icon_src, destination_path / f"{INSTALL_APP_NAME}.ico")
    for d in ["output", "cache", "logs"]: (destination_path / d).mkdir(exist_ok=True)
    
    progress_callback(50, "Konfiguration fertig.")

    if desktop_shortcut and launcher_src.exists():
        log_callback("Erstelle Desktop-Verknüpfung...", "info")
        _create_shortcut(destination_path / f"{INSTALL_APP_NAME}.exe", destination_path, destination_path / f"{INSTALL_APP_NAME}.ico")
    
    log_callback("Installation erfolgreich abgeschlossen.", "success")


# ============================================================================
# WORKER THREAD
# ============================================================================

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

    def _handle_msvc(self):
        """Intelligente MSVC Installation."""
        # 1. Check Registry
        if _is_msvc_installed():
            self.log("MSVC Runtime bereits installiert (Registry Check OK).", "success")
            return

        # 2. Check Temp File
        temp_dir = Path(tempfile.gettempdir())
        msvc_path = temp_dir / MSVC_REDIST_FILENAME
        
        if msvc_path.exists():
             # Optional: Check file size to ensure it's valid (>10MB usually)
             if msvc_path.stat().st_size > 10000000:
                 self.log("MSVC Installer im Cache gefunden. Überspringe Download.", "info")
             else:
                 self.log("Cache-Datei ungültig. Lösche...", "warning")
                 msvc_path.unlink()

        # 3. Download (nur wenn nicht vorhanden)
        if not msvc_path.exists():
            self.log(f"Lade MSVC Redistributable herunter...", "warning")
            if not self._check_internet_status():
                self.log("Kein Internet für MSVC Download. Überspringe...", "error")
                return
                
            try:
                response = requests.get(MSVC_REDIST_URL, stream=True, timeout=60)
                with open(msvc_path, 'wb') as f: f.write(response.content)
                self.log("Download fertig.", "success")
            except Exception as e: 
                self.log(f"FEHLER MSVC Download: {e}", "error"); return

        # 4. Installieren
        self.log("Installiere MSVC Runtime...", "info")
        try:
            # /install /quiet /norestart
            subprocess.run([str(msvc_path), "/install", "/quiet", "/norestart"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.log("MSVC installiert.", "success")
        except Exception as e: 
            self.log(f"MSVC Installation fehlgeschlagen (Code {e}). Evtl. manuell prüfen.", "error")

    def _pre_pull_docker(self):
        images = ["debian:bookworm-slim"]
        for img in images:
            if self._check_internet_status():
                self.progress_update(70, f"Pre-Pull: {img}...")
                try: subprocess.run(["docker", "pull", img], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
                except: pass

    def run(self):
        try:
            self.progress_update(0, "Systemprüfung...")
            self._handle_msvc()
            
            install_application(self.target_dir, self.desktop_shortcut, self.log, self.progress_update)
            
            self._pre_pull_docker()
            self.progress_update(100, "Fertig.")
            self.success = True
            self.message = "Installation erfolgreich."
        except Exception as e:
            self.success = False
            self.message = str(e)

# ============================================================================
# GUI
# ============================================================================

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
        ttk.Label(main, text="Setup (Smart Update)", font=('Arial', 16)).pack(pady=10)
        
        self.path_ent = ttk.Entry(main); self.path_ent.pack(fill='x', pady=5)
        default_path = Path(os.getenv('LOCALAPPDATA')) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX
        self.path_ent.insert(0, str(default_path))
        
        self.check_sc = ttk.Checkbutton(main, text="Desktop Shortcut"); self.check_sc.pack(anchor='w')
        self.check_sc.state(['!alternate', 'selected'])
        
        self.log = ScrolledText(main, height=10); self.log.pack(fill='both', expand=True, pady=10)
        self.prog = ttk.Progressbar(main, variable=self.progress_var); self.prog.pack(fill='x', pady=5)
        self.btn = ttk.Button(main, text="Install / Update", command=self._start); self.btn.pack(pady=5)

    def update_log(self, msg, color="normal"):
        self.after(0, lambda: self.log.insert('end', f"{msg}\n", self.log.tag_config(color, foreground=self.COLOR_MAPPING.get(color, "black")) or color))

    def _run_checks(self):
        self.update_log("Prüfe Umgebung...", "info")
        if _is_msvc_installed():
            self.update_log("MSVC Runtime: OK (Gefunden)", "success")
        else:
            self.update_log("MSVC Runtime: Fehlt (wird installiert)", "warning")

    def _start(self):
        self.btn.config(state='disabled')
        target = Path(self.path_ent.get())
        sc = self.check_sc.instate(['selected'])
        self.current_install_thread = InstallationWorker(target, sc, self.update_log, self.update_p)
        self.current_install_thread.start()
        self._monitor()

    def update_p(self, val, msg=""):
        self.after(0, lambda: (self.progress_var.set(val), self.update_log(msg) if msg else None))

    def _monitor(self):
        if self.current_install_thread.is_alive(): self.after(500, self._monitor)
        else: 
            if self.current_install_thread.success:
                messagebox.showinfo("Done", self.current_install_thread.message)
                self.destroy()
            else:
                messagebox.showerror("Error", self.current_install_thread.message)
                self.btn.config(state='normal')

if __name__ == '__main__': 
    try:
        app = InstallerWindow()
        app.mainloop()
    except Exception as e:
        from tkinter import messagebox
        messagebox.showerror("Fatal Error", str(e))
