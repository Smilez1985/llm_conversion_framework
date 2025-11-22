#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Differential Sync)
DIREKTIVE: Goldstandard.
           1. MSVC: Registry-Check.
           2. Update: Hash-basierter Sync (Nur geänderte Dateien kopieren).
           3. User-Schutz: Custom Targets bleiben unangetastet.
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

# Dateien/Ordner die vom Sync komplett ausgeschlossen sind
IGNORED_NAMES = {
    ".gitignore", ".gitattributes", ".venv", "venv", "env",
    "__pycache__", "dist", "build", ".spec", "tmp", "temp"
}
IGNORED_EXTENSIONS = {".pyc", ".pyd", ".spec"}

# ============================================================================
# LOGIK: MSVC PRÜFUNG
# ============================================================================

def _is_msvc_installed() -> bool:
    """Prüft via Registry, ob VC++ 2015-2022 (x64) Runtime installiert ist."""
    if not winreg: return False
    try:
        path = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
        installed, _ = winreg.QueryValueEx(key, "Installed")
        winreg.CloseKey(key)
        return installed == 1
    except OSError:
        return False

# ============================================================================
# LOGIK: HASH-BASIERTER SYNC (DIFFERENTIAL COPY)
# ============================================================================

def _calculate_file_hash(filepath: Path) -> str:
    """Berechnet SHA256 Hash einer Datei für Vergleich."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            # Lese in Chunks um Speicher zu schonen (wichtig bei großen Modellen)
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""

def _should_copy(src: Path, dst: Path) -> bool:
    """Entscheidet, ob kopiert werden muss."""
    # 1. Existiert nicht? -> Kopieren
    if not dst.exists():
        return True
    
    # 2. Größe unterschiedlich? -> Kopieren (Schneller Check)
    if src.stat().st_size != dst.stat().st_size:
        return True
        
    # 3. Hash unterschiedlich? -> Kopieren (Sicherer Check)
    # Dies fängt inhaltliche Änderungen bei gleicher Größe ab
    return _calculate_file_hash(src) != _calculate_file_hash(dst)

def _is_ignored(path: Path) -> bool:
    """Prüft gegen globale Ignore-Listen."""
    if path.name in IGNORED_NAMES: return True
    if path.suffix in IGNORED_EXTENSIONS: return True
    return False

def _sync_recursive(src_dir: Path, dst_dir: Path, log_callback: Callable, counter: list):
    """Rekursiver Sync mit Hash-Check."""
    dst_dir.mkdir(parents=True, exist_ok=True)

    for item in src_dir.iterdir():
        if _is_ignored(item): continue

        src_path = item
        dst_path = dst_dir / item.name

        # Spezialbehandlung 'targets': User-Ordner schützen
        # Wir sind im 'targets' Ordner des Repos.
        # Wenn im Ziel-Ordner 'targets' Ordner sind, die HIER NICHT existieren,
        # sind es User-Module -> Finger weg!
        # Wir müssen hier also nur das kopieren, was wir haben.
        
        if src_path.is_dir():
            _sync_recursive(src_path, dst_path, log_callback, counter)
        else:
            if _should_copy(src_path, dst_path):
                try:
                    shutil.copy2(src_path, dst_path)
                    counter[0] += 1 # Zähler für aktualisierte Dateien
                except Exception as e:
                    log_callback(f"Fehler beim Kopieren von {src_path.name}: {e}", "error")

def _perform_differential_update(src_root: Path, dst_root: Path, log_callback: Callable):
    """Startet den intelligenten Update-Prozess."""
    updated_files_count = [0]
    
    log_callback(f"Prüfe Änderungen (Hash-Vergleich)...", "info")
    
    # 1. Rekursiver Sync aller Framework-Dateien
    _sync_recursive(src_root, dst_root, log_callback, updated_files_count)
    
    # 2. Bereinigung (Optional/Vorsichtig): 
    # Wir löschen KEINE Dateien im Ziel, die im Source fehlen, 
    # um Configs und User-Daten zu schützen. 
    # Ausnahme: Veraltete Core-Skripte könnten hier explizit gelöscht werden, 
    # wenn man eine 'deprecated_files' Liste pflegen würde.
    # Aktuell: Nur additives/aktualisierendes Update -> Sicherster Weg.

    if updated_files_count[0] == 0:
        log_callback("System ist aktuell. Keine Dateien geändert.", "success")
    else:
        log_callback(f"{updated_files_count[0]} Dateien aktualisiert.", "success")


# ============================================================================
# INSTALLER LOGIK
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
    
    # Zielordner erstellen
    destination_path.mkdir(parents=True, exist_ok=True)
    
    progress_callback(10, "Synchronisiere Dateien...")
    
    # START DES NEUEN HASH-BASIERTEN SYNCS
    _perform_differential_update(repo_root, destination_path, log_callback)
    
    progress_callback(80, "Prüfe Launcher...")
    
    # Launcher kopieren (ebenfalls mit Check)
    installer_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else repo_root / "dist"
    launcher_src = installer_dir / f"{INSTALL_APP_NAME}.exe" 
    
    if not launcher_src.exists():
         launcher_src = repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"

    if launcher_src.exists():
        launcher_dst = destination_path / f"{INSTALL_APP_NAME}.exe"
        if _should_copy(launcher_src, launcher_dst):
            try:
                shutil.copy2(launcher_src, launcher_dst)
                log_callback("Launcher aktualisiert.", "info")
            except Exception as e:
                # Das kann passieren, wenn die App läuft. 
                # In einem echten Update-Szenario würde der Updater-Prozess (batch) das übernehmen.
                log_callback(f"Launcher konnte nicht kopiert werden (läuft evtl?): {e}", "warning")
    else:
        log_callback("WARNUNG: Launcher EXE nicht gefunden.", "warning")

    # Configs & Assets (Icon immer kopieren wenn da)
    icon_src = repo_root / f"{INSTALL_APP_NAME}.ico"
    if icon_src.exists(): shutil.copy2(icon_src, destination_path / f"{INSTALL_APP_NAME}.ico")
    
    # Leere Ordner sicherstellen
    for d in ["output", "cache", "logs"]: (destination_path / d).mkdir(exist_ok=True)
    
    progress_callback(90, "Finalisierung...")

    if desktop_shortcut and launcher_src.exists():
        # Shortcut nur erstellen wenn nicht da oder erzwungen, hier einfach immer (ist billig)
        _create_shortcut(destination_path / f"{INSTALL_APP_NAME}.exe", destination_path, destination_path / f"{INSTALL_APP_NAME}.ico")
    
    log_callback("Vorgang abgeschlossen.", "success")


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
        if _is_msvc_installed():
            self.log("MSVC Runtime: OK (Bereits installiert).", "success")
            return

        temp_dir = Path(tempfile.gettempdir())
        msvc_path = temp_dir / MSVC_REDIST_FILENAME
        
        if msvc_path.exists() and msvc_path.stat().st_size > 1000000:
             self.log("MSVC Installer im Cache gefunden.", "info")
        else:
            self.log(f"Lade MSVC Redistributable herunter...", "warning")
            if not self._check_internet_status():
                self.log("Kein Internet für MSVC. Überspringe...", "error"); return
            try:
                response = requests.get(MSVC_REDIST_URL, stream=True, timeout=60)
                with open(msvc_path, 'wb') as f: f.write(response.content)
            except Exception as e: 
                self.log(f"FEHLER MSVC Download: {e}", "error"); return

        self.log("Installiere MSVC Runtime...", "info")
        try:
            subprocess.run([str(msvc_path), "/install", "/quiet", "/norestart"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.log("MSVC erfolgreich installiert.", "success")
        except Exception as e: 
            self.log(f"MSVC Installation fehlgeschlagen (Code {e}).", "error")

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
            self.message = "Operation erfolgreich."
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
        ttk.Label(main, text="Setup (Differential Update)", font=('Arial', 16)).pack(pady=10)
        
        self.path_ent = ttk.Entry(main); self.path_ent.pack(fill='x', pady=5)
        default_path = Path(os.getenv('LOCALAPPDATA')) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX
        self.path_ent.insert(0, str(default_path))
        
        self.check_sc = ttk.Checkbutton(main, text="Desktop Shortcut"); self.check_sc.pack(anchor='w')
        self.check_sc.state(['!alternate', 'selected'])
        
        self.log = ScrolledText(main, height=10); self.log.pack(fill='both', expand=True, pady=10)
        self.prog = ttk.Progressbar(main, variable=self.progress_var); self.prog.pack(fill='x', pady=5)
        self.btn = ttk.Button(main, text="Start", command=self._start); self.btn.pack(pady=5)

    def update_log(self, msg, color="normal"):
        self.after(0, lambda: self.log.insert('end', f"{msg}\n", self.log.tag_config(color, foreground=self.COLOR_MAPPING.get(color, "black")) or color))

    def _run_checks(self):
        self.update_log("Initialisiere...", "info")
        if _is_msvc_installed():
            self.update_log("MSVC Runtime: OK", "success")

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
                messagebox.showinfo("Fertig", self.current_install_thread.message)
                self.destroy()
            else:
                messagebox.showerror("Fehler", self.current_install_thread.message)
                self.btn.config(state='normal')

if __name__ == '__main__': 
    try:
        app = InstallerWindow()
        app.mainloop()
    except Exception as e:
        from tkinter import messagebox
        messagebox.showerror("Fatal Error", str(e))
