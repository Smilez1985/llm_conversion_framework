#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows GUI Installer (v2.5 Final)
DIREKTIVE: Goldstandard, Robustness, Central Config.
"""

import os
import sys
import shutil
import subprocess
import threading
import time
import ctypes
import winreg
from pathlib import Path

# GUI Imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

APP_NAME = "LLM-Conversion-Framework"

# ZENTRALER CONFIG PFAD (Fix vorgegeben)
CHECKFILE_DIR = Path("C:/Users/Public/Documents/llm_conversion_framework")
CHECKFILE_PATH = CHECKFILE_DIR / "checkfile.txt"

# Standard-Installationspfad
DEFAULT_APP_PATH = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / APP_NAME

SOURCE_DIR = Path(__file__).resolve().parent.parent

INCLUDE_APP_FILES = ["Launch-LLM-Conversion-Framework.bat", "README.md", "LICENSE"]
INCLUDE_DATA_DIRS = ["orchestrator", "targets", "configs", "assets", "Docker Setup"]
INCLUDE_DATA_FILES = ["pyproject.toml", "requirements.txt", ".gitignore"]
IGNORE_PATTERNS = ["__pycache__", "*.pyc", ".git", ".venv", "venv", "dist", "build"]

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Installer v2.5")
        self.geometry("750x550")
        self.resizable(True, True)
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._init_ui()
        
    def _init_ui(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        lbl_title = ttk.Label(main_frame, text=f"Install {APP_NAME}", font=("Segoe UI", 18, "bold"))
        lbl_title.pack(anchor=tk.W, pady=(0, 5))
        
        lbl_desc = ttk.Label(main_frame, text="Choose installation folder. The configuration will be stored globally.")
        lbl_desc.pack(anchor=tk.W, pady=(0, 20))
        
        # Installation Directory
        grp_app = ttk.LabelFrame(main_frame, text="Installation Directory", padding="10")
        grp_app.pack(fill=tk.X, pady=5)
        
        self.var_app_path = tk.StringVar(value=str(DEFAULT_APP_PATH))
        e_app = ttk.Entry(grp_app, textvariable=self.var_app_path)
        e_app.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        btn_app = ttk.Button(grp_app, text="Browse...", command=lambda: self._browse(self.var_app_path))
        btn_app.pack(side=tk.RIGHT)
        
        # Options
        opt_frame = ttk.Frame(main_frame)
        opt_frame.pack(fill=tk.X, pady=10)
        
        self.var_desktop = tk.BooleanVar(value=True)
        chk_desktop = ttk.Checkbutton(opt_frame, text="Create Desktop Shortcut", variable=self.var_desktop)
        chk_desktop.pack(anchor=tk.W)
        
        # Log
        log_frame = ttk.LabelFrame(main_frame, text="Installation Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.log_text = ScrolledText(log_frame, height=10, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Progress
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.btn_install = ttk.Button(btn_frame, text="Install", command=self._start_install)
        self.btn_install.pack(side=tk.RIGHT)
        self.btn_cancel = ttk.Button(btn_frame, text="Cancel", command=self.destroy)
        self.btn_cancel.pack(side=tk.RIGHT, padx=10)

    def _browse(self, var):
        d = filedialog.askdirectory(initialdir=var.get())
        if d: var.set(d)

    def log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.update_idletasks()

    def _start_install(self):
        target_dir = Path(self.var_app_path.get())
        self.btn_install.config(state='disabled')
        self.btn_cancel.config(state='disabled')
        self.progress['value'] = 0
        threading.Thread(target=self._install_process, args=(target_dir,), daemon=True).start()

    def _install_process(self, target: Path):
        try:
            self.log(f"Installing to: {target}")
            
            if not target.exists(): target.mkdir(parents=True, exist_ok=True)
            
            # 1. Copy Content
            self.log("Copying files...")
            total_items = len(INCLUDE_DATA_DIRS) + len(INCLUDE_DATA_FILES) + len(INCLUDE_APP_FILES)
            current = 0
            
            # Dirs
            for item in INCLUDE_DATA_DIRS:
                src = SOURCE_DIR / item
                dst = target / item
                if src.exists():
                    if dst.exists(): shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))
                current += 1
                self.progress['value'] = (current / total_items) * 60
            
            # Files
            for item in INCLUDE_DATA_FILES + INCLUDE_APP_FILES:
                src = SOURCE_DIR / item
                dst = target / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1
                self.progress['value'] = (current / total_items) * 60

            # 2. Setup VENV (im Zielordner)
            self.log("Setting up Python Environment (VENV)...")
            venv_path = target / ".venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
            
            # 3. Install Dependencies
            self.log("Installing dependencies...")
            pip_exe = venv_path / "Scripts" / "pip.exe"
            
            subprocess.run([str(pip_exe), "install", "--upgrade", "pip"], 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Install Framework Deps
            subprocess.run([str(pip_exe), "install", "."], cwd=str(target), 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Install Shortcut Deps (PyWin32) in VENV
            subprocess.run([str(pip_exe), "install", "pywin32", "winshell"], 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

            self.progress['value'] = 90

            # 4. Shortcuts
            if self.var_desktop.get():
                self._create_shortcut(target, "Desktop")

            # 5. Central Checkfile
            self.log("Writing Configuration...")
            
            # Ordner erstellen falls nicht da
            if not CHECKFILE_DIR.exists():
                CHECKFILE_DIR.mkdir(parents=True, exist_ok=True)
            
            # Datei schreiben: Path=C:\...
            with open(CHECKFILE_PATH, "w") as f:
                f.write(f"Path={target}")
            
            # Attribute setzen (Hidden)
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(CHECKFILE_DIR), 0x02) # Folder hidden
                ctypes.windll.kernel32.SetFileAttributesW(str(CHECKFILE_PATH), 0x02) # File hidden
            except: pass

            self.progress['value'] = 100
            self.log("Installation Complete!")
            
            messagebox.showinfo("Success", "Installation finished successfully!")
            self.btn_cancel.config(text="Close", state='normal', command=self.destroy)
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
            self.btn_install.config(state='normal')
            self.btn_cancel.config(state='normal')

    def _create_shortcut(self, target_dir: Path, location: str):
        # Wir nutzen hier direkt winshell, da wir es im VENV haben, 
        # aber das laufende Skript hat es evtl. nicht (wenn der User es nicht hat).
        # Fallback auf PowerShell für Shortcut Creation (Zero Dependency auf Host)
        
        try:
            import winshell
            from win32com.client import Dispatch
            
            shell = Dispatch('WScript.Shell')
            desktop = winshell.desktop()
            path = os.path.join(desktop, f"{APP_NAME}.lnk")
            target_bat = str(target_dir / "Launch-LLM-Conversion-Framework.bat")
            icon_path = str(target_dir / "assets" / "logo.ico")

            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target_bat
            shortcut.WorkingDirectory = str(target_dir)
            if os.path.exists(icon_path):
                shortcut.IconLocation = icon_path
            shortcut.save()
            self.log(f"Shortcut created on Desktop")
            
        except ImportError:
            # Fallback: PowerShell
            self.log("Using PowerShell fallback for shortcut...")
            target_bat = str(target_dir / "Launch-LLM-Conversion-Framework.bat")
            icon_path = str(target_dir / "assets" / "logo.ico")
            desktop = os.path.join(os.environ["USERPROFILE"], "Desktop", f"{APP_NAME}.lnk")
            
            ps_cmd = f'$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut("{desktop}"); $s.TargetPath = "{target_bat}"; $s.WorkingDirectory = "{target_dir}"; $s.IconLocation = "{icon_path}"; $s.Save()'
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)

if __name__ == "__main__":
    app = InstallerGUI()
    app.mainloop()
