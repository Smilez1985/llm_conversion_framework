#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows GUI Installer (v2.1 Fixed)
DIREKTIVE: Goldstandard, Robustness, Registry-Based Config.
"""

import os
import sys
import shutil
import subprocess
import threading
import time
import ctypes
import winreg  # NATIVE WINDOWS REGISTRY SUPPORT
from pathlib import Path

# GUI Imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

APP_NAME = "LLM-Conversion-Framework"
REG_PATH = r"Software\Smilez1985\LLM-Framework"

# Standard-Pfade
DEFAULT_APP_PATH = Path(os.environ.get("LocalAppData", "C:")) / "Programs" / APP_NAME
# Wir nutzen LocalAppData statt ProgramFiles, um Admin-Zwang zu vermeiden (User-Mode Install)
# Wer Admin ist, kann es ändern.

SOURCE_DIR = Path(__file__).resolve().parent.parent

INCLUDE_APP_FILES = ["Launch-LLM-Conversion-Framework.bat", "README.md", "LICENSE"]
INCLUDE_DATA_DIRS = ["orchestrator", "targets", "configs", "assets", "Docker Setup"]
INCLUDE_DATA_FILES = ["pyproject.toml", "requirements.txt", ".gitignore"]
IGNORE_PATTERNS = ["__pycache__", "*.pyc", ".git", ".venv", "venv", "dist", "build"]

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Installer v2.1")
        self.geometry("750x600")
        self.resizable(True, True)
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._init_ui()
        
    def _init_ui(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        header = ttk.Frame(main_frame)
        header.pack(fill=tk.X, pady=(0, 20))
        lbl_title = ttk.Label(header, text=f"Install {APP_NAME}", font=("Segoe UI", 18, "bold"))
        lbl_title.pack(anchor=tk.W)
        
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
        
        self.var_startmenu = tk.BooleanVar(value=True)
        chk_start = ttk.Checkbutton(opt_frame, text="Create Start Menu Entry", variable=self.var_startmenu)
        chk_start.pack(anchor=tk.W)
        
        # Log
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
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
            
            # 1. Copy Files
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
                self.progress['value'] = (current / total_items) * 50
            
            # Data Files
            for item in INCLUDE_DATA_FILES:
                src = SOURCE_DIR / item
                dst = target / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1
                
            # App Files
            for item in INCLUDE_APP_FILES:
                src = SOURCE_DIR / item
                dst = target / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1

            # 2. Setup VENV
            self.log("Setting up Python Environment...")
            venv_path = target / ".venv"
            python_exe = sys.executable
            subprocess.run([python_exe, "-m", "venv", str(venv_path)], check=True)
            
            self.log("Installing dependencies...")
            pip_exe = venv_path / "Scripts" / "pip.exe"
            cwd = str(target)
            subprocess.run([str(pip_exe), "install", "."], cwd=cwd, 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.progress['value'] = 90

            # 3. Create Shortcuts (Desktop & Start Menu)
            if self.var_desktop.get():
                self._create_shortcut(target, "Desktop")
            
            if self.var_startmenu.get():
                self._create_shortcut(target, "StartMenu")

            # 4. Write Registry Key (The reliable Marker)
            self.log("Registering application...")
            try:
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
                winreg.SetValueEx(key, "InstallPath", 0, winreg.REG_SZ, str(target))
                winreg.CloseKey(key)
            except Exception as e:
                self.log(f"Registry Warning: {e}")

            self.progress['value'] = 100
            self.log("Done!")
            messagebox.showinfo("Success", f"Installation complete.\nYou can find the app on your Desktop.")
            self.quit()
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
            self.btn_install.config(state='normal')

    def _create_shortcut(self, target_dir: Path, location: str):
        try:
            import winshell
            from win32com.client import Dispatch

            shell = Dispatch('WScript.Shell')
            
            if location == "Desktop":
                folder = winshell.desktop()
            else:
                folder = winshell.programs() # Start Menu

            shortcut_path = os.path.join(folder, f"{APP_NAME}.lnk")
            target_bat = str(target_dir / "Launch-LLM-Conversion-Framework.bat")
            
            icon_path = str(target_dir / "assets" / "logo.ico")
            if not os.path.exists(icon_path): icon_path = target_bat # Fallback

            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = target_bat
            shortcut.WorkingDirectory = str(target_dir)
            shortcut.IconLocation = icon_path
            shortcut.save()
            self.log(f"Shortcut created in {location}")
            
        except ImportError:
            self.log("Warning: pywin32/winshell missing. Cannot create shortcut.")
            # Try PowerShell fallback if pywin32 fails?
            # For now, we log warning. 'pip install pywin32' is in requirements?
        except Exception as e:
            self.log(f"Shortcut Error ({location}): {e}")

if __name__ == "__main__":
    app = InstallerGUI()
    app.mainloop()
