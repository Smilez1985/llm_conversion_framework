#!/usr/bin/env python3
"""LLM Cross-Compiler Framework - Windows Installer"""
import os
import sys
import shutil
import subprocess
import time
import threading
import tempfile
import hashlib
import argparse 
from pathlib import Path
import requests 

try: import winreg
except ImportError: winreg = None
try: import tkinter as tk; from tkinter import ttk, messagebox; from tkinter.scrolledtext import ScrolledText
except ImportError: sys.exit(1)

INSTALL_APP_NAME = "LLM-Builder"
DEFAULT_INSTALL_DIR_SUFFIX = "LLM-Framework"
MSVC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
MSVC_REDIST_FILENAME = "vc_redist.x64.exe"

IGNORED_NAMES = {".gitignore", ".gitattributes", ".venv", "venv", "env", "__pycache__", "dist", "build", ".spec", "tmp", "temp", ".git"}
IGNORED_EXTENSIONS = {".pyc", ".pyd", ".spec"}

def _is_msvc_installed():
    if not winreg: return False
    try:
        path = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
        i, _ = winreg.QueryValueEx(key, "Installed")
        winreg.CloseKey(key)
        return i == 1
    except OSError: return False

def _calculate_file_hash(p):
    h = hashlib.sha256()
    try:
        with open(p, 'rb') as f:
            while c := f.read(8192): h.update(c)
        return h.hexdigest()
    except: return ""

def _should_copy(src, dst):
    if not dst.exists(): return True
    if src.stat().st_size != dst.stat().st_size: return True
    return _calculate_file_hash(src) != _calculate_file_hash(dst)

def _is_ignored(p): return p.name in IGNORED_NAMES or p.suffix in IGNORED_EXTENSIONS

def _find_repo_root_at_runtime():
    start = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    curr = start
    for _ in range(10):
        if all((curr / m).exists() for m in ["targets", "orchestrator"]): return curr
        if curr.parent == curr: break
        curr = curr.parent
    return None

def _sync_recursive(src, dst, cb, cnt):
    dst.mkdir(parents=True, exist_ok=True)
    for i in src.iterdir():
        if _is_ignored(i): continue
        s, d = i, dst / i.name
        if s.is_dir(): _sync_recursive(s, d, cb, cnt)
        else:
            if _should_copy(s, d):
                try: shutil.copy2(s, d); cnt[0] += 1
                except Exception as e: cb(f"Error {s.name}: {e}", "error")

def _perform_differential_update(src, dst, cb):
    cnt = [0]; cb("Smart Sync...", "info"); _sync_recursive(src, dst, cb, cnt)
    cb("Alles aktuell." if cnt[0] == 0 else f"{cnt[0]} Dateien aktualisiert.", "success")

def _create_shortcut(exe, wd, icon):
    d = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    lnk = os.path.join(d, f"{INSTALL_APP_NAME}.lnk")
    try:
        s = f'Set o=WScript.CreateObject("WScript.Shell")\nSet l=o.CreateShortcut("{lnk}")\nl.TargetPath="{str(exe)}"\nl.WorkingDirectory="{str(wd)}"\nl.IconLocation="{str(icon)}"\nl.Save'
        vbs = Path(tempfile.gettempdir()) / "cs.vbs"
        with open(vbs, "w") as f: f.write(s)
        subprocess.run(["cscript", "//Nologo", str(vbs)], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        vbs.unlink(); return True
    except: return False

def install_application(dst, sc, cb, prog):
    root = _find_repo_root_at_runtime()
    if not root: raise Exception("Repo root missing")
    dst.mkdir(parents=True, exist_ok=True)
    prog(10, "Sync Files...")
    _perform_differential_update(root, dst, cb)
    prog(80, "Launcher...")
    l_src = Path(sys.executable).parent / f"{INSTALL_APP_NAME}.exe" if getattr(sys, 'frozen', False) else root / "dist" / f"{INSTALL_APP_NAME}.exe"
    if not l_src.exists(): l_src = root / "dist" / f"{INSTALL_APP_NAME}.exe"
    if l_src.exists():
        try: shutil.copy2(l_src, dst / f"{INSTALL_APP_NAME}.exe")
        except: pass
    i_src = root / f"{INSTALL_APP_NAME}.ico"
    if i_src.exists(): shutil.copy2(i_src, dst / f"{INSTALL_APP_NAME}.ico")
    for d in ["output", "cache", "logs"]: (dst / d).mkdir(exist_ok=True)
    prog(90, "Finalize...")
    if sc and (dst / f"{INSTALL_APP_NAME}.exe").exists(): _create_shortcut(dst / f"{INSTALL_APP_NAME}.exe", dst, dst / f"{INSTALL_APP_NAME}.ico")
    cb("Fertig.", "success")

class InstallationWorker(threading.Thread):
    def __init__(self, td, sc, cb, pu):
        super().__init__(daemon=True)
        self.target_dir = td; self.desktop_shortcut = sc; self.log = cb; self.progress_update = pu
        self.success = False; self.message = ""; self.start_time = 0
    
    def _smart_progress(self, pct, msg=""):
        if self.start_time == 0: self.start_time = time.time()
        el = time.time() - self.start_time
        eta = f" (~{int((el/(pct/100.0))-el)}s)" if pct > 0 and pct < 100 else ""
        self.progress_update(pct, f"{msg}{eta}" if msg else "")

    def _check_net(self):
        try: requests.head("http://google.com", timeout=3); return True
        except: return False

    def _msvc(self):
        if _is_msvc_installed(): return
        self.log("MSVC fehlt. Installiere...", "warning")
        tmp = Path(tempfile.gettempdir()) / MSVC_REDIST_FILENAME
        if not tmp.exists():
            if not self._check_net(): return
            try:
                r = requests.get(MSVC_REDIST_URL, stream=True, timeout=60)
                with open(tmp, 'wb') as f: f.write(r.content)
            except: return
        try: subprocess.run([str(tmp), "/install", "/quiet", "/norestart"], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except: pass

    def _qemu(self):
        if not self._check_net(): return
        self.log("Installiere QEMU...", "info")
        try: subprocess.run(["docker", "run", "--rm", "--privileged", "tonistiigi/binfmt", "--install", "all"], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        except: self.log("QEMU Fehler (ignoriert)", "warning")

    def _docker(self):
        if not self._check_net(): return
        try:
             subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
             self._smart_progress(70, "Lade Docker Images...")
             subprocess.run(["docker", "pull", "debian:bookworm-slim"], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        except: pass

    def run(self):
        try:
            self.start_time = time.time()
            self._smart_progress(5, "Prüfe...")
            self._msvc()
            self._smart_progress(15, "QEMU...")
            self._qemu()
            self._smart_progress(20, "Dateien...")
            install_application(self.target_dir, self.desktop_shortcut, self.log, self._smart_progress)
            self._smart_progress(80, "Docker...")
            self._docker()
            self._smart_progress(100, "Fertig.")
            self.success = True; self.message = "OK"
        except Exception as e: self.success = False; self.message = str(e)

class InstallerWindow(tk.Tk):
    CM = {"info": "blue", "success": "green", "error": "red", "warning": "orange", "normal": "black"}
    def __init__(self, auto=False):
        super().__init__(); self.title(f"Install {INSTALL_APP_NAME}"); self.geometry("600x550")
        self.pv = tk.DoubleVar(value=0); self.auto = auto; self._ui()
        if self.auto: self.after(500, self._start)
        else: self.after(100, lambda: threading.Thread(target=self._check, daemon=True).start())
    
    def _ui(self):
        s = ttk.Style(self); s.theme_use('clam')
        m = ttk.Frame(self, padding=10); m.pack(fill='both', expand=True)
        ttk.Label(m, text="Setup", font=('Arial', 16)).pack(pady=10)
        self.pe = ttk.Entry(m); self.pe.pack(fill='x'); self.pe.insert(0, str(Path(os.getenv('LOCALAPPDATA')) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX))
        self.sc = ttk.Checkbutton(m, text="Shortcut"); self.sc.pack(); self.sc.state(['!alternate', 'selected'])
        self.log = ScrolledText(m, height=10); self.log.pack(fill='both', expand=True)
        self.pg = ttk.Progressbar(m, variable=self.pv, maximum=100); self.pg.pack(fill='x')
        self.sl = ttk.Label(m, text="Ready"); self.sl.pack()
        self.b = ttk.Button(m, text="Install", command=self._start); self.b.pack()
    
    def ul(self, m, c="normal"): self.after(0, lambda: self.log.insert('end', f"{m}\n", self.log.tag_config(c, foreground=self.CM.get(c, "black")) or c))
    def _check(self): self.ul("Check...", "info"); self.ul("MSVC OK" if _is_msvc_installed() else "MSVC fehlt", "success" if _is_msvc_installed() else "warning")
    def _start(self):
        self.b.config(state='disabled')
        self.th = InstallationWorker(Path(self.pe.get()), self.sc.instate(['selected']), self.ul, self.up)
        self.th.start(); self._mon()
    def up(self, v, m=""): self.after(0, lambda: (self.pv.set(v), self.sl.config(text=m)))
    def _mon(self):
        if self.th.is_alive(): self.after(500, self._mon)
        else:
            if self.th.success:
                self.ul("Start...", "success")
                ep = Path(self.pe.get()) / f"{INSTALL_APP_NAME}.exe"
                if ep.exists():
                    if sys.platform == "win32": os.startfile(ep)
                    else: subprocess.Popen([str(ep)])
                if self.auto: self.after(2000, self.destroy)
                else: messagebox.showinfo("OK", "Done"); self.destroy()
            else: messagebox.showerror("Err", self.th.message); self.b.config(state='normal')

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument("--update", action="store_true"); a, _ = p.parse_known_args()
    try: app = InstallerWindow(a.update); app.mainloop()
    except Exception as e: messagebox.showerror("Err", str(e))
