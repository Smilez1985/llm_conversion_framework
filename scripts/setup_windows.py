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
except: winreg = None
try: import tkinter as tk; from tkinter import ttk, messagebox; from tkinter.scrolledtext import ScrolledText
except: sys.exit(1)

INSTALL_APP_NAME = "LLM-Builder"
MSVC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
MSVC_REDIST_FILENAME = "vc_redist.x64.exe"

# FIX: Listen statt Sets verwenden, um Type-Errors bei Addition zu vermeiden
IGNORED_NAMES = [".gitignore", ".gitattributes", ".venv", "venv", "env", "__pycache__", "dist", "build", ".spec", "tmp", "temp", ".git"]
IGNORED_EXTENSIONS = [".pyc", ".pyd", ".spec"]

def _is_msvc_installed():
    if not winreg: return False
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64", 0, winreg.KEY_READ)
        i, _ = winreg.QueryValueEx(key, "Installed"); winreg.CloseKey(key); return i == 1
    except: return False

def _should_copy(src, dst):
    if not dst.exists(): return True
    return src.stat().st_size != dst.stat().st_size

def _sync(src, dst, cb, cnt):
    dst.mkdir(parents=True, exist_ok=True)
    for i in src.iterdir():
        if i.name in IGNORED_NAMES or i.suffix in IGNORED_EXTENSIONS: continue
        s, d = i, dst / i.name
        if s.is_dir(): _sync(s, d, cb, cnt)
        elif _should_copy(s, d):
            try: shutil.copy2(s, d); cnt[0] += 1
            except Exception as e: cb(f"Err {s.name}: {e}")

def install_app(dst, sc, cb, prog):
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent.parent
    dst.mkdir(parents=True, exist_ok=True)
    prog(10, "Syncing Files...")
    _sync(root, dst, cb, [0])
    prog(80, "Updating Launcher...")
    l_src = Path(sys.executable).parent / f"{INSTALL_APP_NAME}.exe" if getattr(sys, 'frozen', False) else root / "dist" / f"{INSTALL_APP_NAME}.exe"
    if l_src.exists():
        try: shutil.copy2(l_src, dst / f"{INSTALL_APP_NAME}.exe")
        except: pass
    i_src = root / f"{INSTALL_APP_NAME}.ico"
    if i_src.exists(): shutil.copy2(i_src, dst / f"{INSTALL_APP_NAME}.ico")
    for d in ["output", "cache", "logs"]: (dst / d).mkdir(exist_ok=True)
    prog(90, "Finalizing...")
    if sc and (dst / f"{INSTALL_APP_NAME}.exe").exists():
        vbs = Path(tempfile.gettempdir()) / "sc.vbs"
        lnk = os.path.join(os.environ['USERPROFILE'], 'Desktop', f"{INSTALL_APP_NAME}.lnk")
        exe = dst / f"{INSTALL_APP_NAME}.exe"
        with open(vbs, "w") as f:
            f.write(f'Set o=WScript.CreateObject("WScript.Shell")\nSet l=o.CreateShortcut("{lnk}")\nl.TargetPath="{exe}"\nl.WorkingDirectory="{dst}"\nl.Save')
        subprocess.run(["cscript", "//Nologo", str(vbs)], check=True, creationflags=0x08000000)
        vbs.unlink()
    cb("Done.")

class Worker(threading.Thread):
    def __init__(self, td, sc, cb, pu):
        super().__init__(daemon=True); self.td=td; self.sc=sc; self.cb=cb; self.pu=pu; self.success=False; self.msg=""
    
    def run(self):
        try:
            self.pu(5, "Checking Environment...") 
            if not _is_msvc_installed():
                r = requests.get(MSVC_REDIST_URL); tmp = Path(tempfile.gettempdir())/MSVC_REDIST_FILENAME
                with open(tmp, 'wb') as f: f.write(r.content)
                subprocess.run([str(tmp), "/install", "/quiet", "/norestart"], check=True)
            self.pu(20, "Installing Files...")
            install_app(self.td, self.sc, self.cb, self.pu)
            self.pu(100, "Installation Complete.")
            self.success = True
        except Exception as e: self.success=False; self.msg=str(e)

class InstallerWindow(tk.Tk):
    def __init__(self, auto=False):
        super().__init__(); self.title("Setup"); self.geometry("500x400"); self.auto=auto; self._ui()
        if auto: self.after(500, self._start)

    def _ui(self):
        ttk.Label(self, text="LLM Framework Setup", font=('Arial', 16)).pack(pady=10)
        self.pe = ttk.Entry(self); self.pe.pack(fill='x', padx=10); self.pe.insert(0, str(Path(os.getenv('LOCALAPPDATA'))/"Programs"/"LLM-Framework"))
        self.sc = ttk.Checkbutton(self, text="Create Desktop Shortcut"); self.sc.pack(pady=5); self.sc.state(['!alternate', 'selected'])
        self.log = ScrolledText(self, height=10); self.log.pack(fill='both', expand=True, padx=10)
        self.pg = ttk.Progressbar(self, maximum=100); self.pg.pack(fill='x', padx=10, pady=5)
        self.sl = ttk.Label(self, text="Ready"); self.sl.pack()
        self.btn = ttk.Button(self, text="Install", command=self._start); self.btn.pack(pady=10)

    def log_msg(self, m): self.after(0, lambda: self.log.insert('end', str(m)+"\n"))
    
    # FIX: Methode heißt jetzt update_progress und akzeptiert optionalen msg Parameter
    def update_progress(self, v, m=""): 
        self.after(0, lambda: self._update_ui(v, m))
    
    def _update_ui(self, v, m):
        self.pg['value'] = v
        if m: self.sl['text'] = m

    def _start(self):
        self.btn['state'] = 'disabled'
        # FIX: Übergebe self.update_progress an den Worker
        self.w = Worker(Path(self.pe.get()), self.sc.instate(['selected']), self.log_msg, self.update_progress)
        self.w.start(); self._mon()

    def _mon(self):
        if self.w.is_alive(): self.after(100, self._mon)
        else:
            if self.w.success:
                self.log_msg("Success."); exe = Path(self.pe.get())/f"{INSTALL_APP_NAME}.exe"
                if exe.exists():
                    # Security Fix: Kein shell=True
                    if sys.platform=="win32": os.startfile(exe)
                    else: subprocess.Popen([str(exe)])
                if self.auto: self.destroy()
                else: messagebox.showinfo("Success", "Installation complete."); self.destroy()
            else: messagebox.showerror("Error", self.w.msg); self.btn['state'] = 'normal'

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument("--update", action="store_true"); a,_=p.parse_known_args()
    InstallerWindow(a.update).mainloop()
