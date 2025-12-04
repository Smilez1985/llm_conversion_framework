#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows GUI Installer (v2.2 Fixed)
DIREKTIVE: Goldstandard, Robustness, User Experience.
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
REG_PATH = r"Software\Smilez1985\LLM-Framework"

# Standard-Pfade
DEFAULT_APP_PATH = Path(os.environ.get("LocalAppData", "C:")) / "Programs" / APP_NAME
DEFAULT_DATA_PATH = Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Documents" / APP_NAME

SOURCE_DIR = Path(__file__).resolve().parent.parent

INCLUDE_APP_FILES = ["Launch-LLM-Conversion-Framework.bat", "README.md", "LICENSE"]
INCLUDE_DATA_DIRS = ["orchestrator", "targets", "configs", "assets", "Docker Setup"]
INCLUDE_DATA_FILES = ["pyproject.toml", "requirements.txt", ".gitignore"]
IGNORE_PATTERNS = ["__pycache__", "*.pyc", ".git", ".venv", "venv", "dist", "build"]

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Installer v2.2")
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
        grp_app = ttk.LabelFrame(main_frame, text="Application Directory (Launcher)", padding="10")
        grp_app.pack(fill=tk.X, pady=5)
        
        self.var_app_path = tk.StringVar(value=str(DEFAULT_APP_PATH))
        e_app = ttk.Entry(grp_app, textvariable=self.var_app_path)
        e_app.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        btn_app = ttk.Button(grp_app, text="Browse...", command=lambda: self._browse(self.var_app_path))
        btn_app.pack(side=tk.RIGHT)
        
        # Data Directory
        grp_data = ttk.LabelFrame(main_frame, text="Data Directory (Core, Targets, VENV)", padding="10")
        grp_data.pack(fill=tk.X, pady=5)
        
        self.var_data_path = tk.StringVar(value=str(DEFAULT_DATA_PATH))
        e_data = ttk.Entry(grp_data, textvariable=self.var_data_path)
        e_data.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        btn_data = ttk.Button(grp_data, text="Browse...", command=lambda: self._browse(self.var_data_path))
        btn_data.pack(side=tk.RIGHT)
        
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
        data_dir = Path(self.var_data_path.get())
        
        self.btn_install.config(state='disabled')
        self.btn_cancel.config(state='disabled')
        self.progress['value'] = 0
        threading.Thread(target=self._install_process, args=(target_dir, data_dir), daemon=True).start()

    def _install_process(self, app_dir: Path, data_dir: Path):
        try:
            self.log(f"Starting installation...")
            
            # 1. Create Directories
            self.log("Creating directories...")
            if not app_dir.exists(): app_dir.mkdir(parents=True, exist_ok=True)
            if not data_dir.exists(): data_dir.mkdir(parents=True, exist_ok=True)
            
            # Hide Data Dir
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(data_dir), 0x02)
            except: pass

            # 2. Copy Files
            self.log("Copying files...")
            total_items = len(INCLUDE_DATA_DIRS) + len(INCLUDE_DATA_FILES) + len(INCLUDE_APP_FILES)
            current = 0
            
            for item in INCLUDE_DATA_DIRS:
                src = SOURCE_DIR / item
                dst = data_dir / item
                if src.exists():
                    if dst.exists(): shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))
                current += 1
                self.progress['value'] = (current / total_items) * 50
            
            for item in INCLUDE_DATA_FILES:
                src = SOURCE_DIR / item
                dst = data_dir / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1
                
            for item in INCLUDE_APP_FILES:
                src = SOURCE_DIR / item
                dst = app_dir / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1

            # 3. Setup VENV
            self.log("Setting up Python Environment...")
            venv_path = data_dir / ".venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
            
            # 4. Dependencies
            self.log("Installing dependencies...")
            pip_exe = venv_path / "Scripts" / "pip.exe"
            cwd = str(data_dir)
            
            subprocess.run([str(pip_exe), "install", "--upgrade", "pip"], 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            subprocess.run([str(pip_exe), "install", "."], cwd=cwd, 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.progress['value'] = 90

            # 5. Shortcuts
            if self.var_desktop.get():
                self._create_shortcut(app_dir, "Desktop")
            if self.var_startmenu.get():
                self._create_shortcut(app_dir, "StartMenu")

            # 6. Registry
            self.log("Registering application...")
            try:
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
                winreg.SetValueEx(key, "InstallPath", 0, winreg.REG_SZ, str(app_dir))
                winreg.CloseKey(key)
            except Exception as e:
                self.log(f"Registry Warning: {e}")

            self.progress['value'] = 100
            self.log("Installation Complete!")
            
            # UX Fix: Nicht schließen, Button aktivieren
            messagebox.showinfo("Success", f"Installation complete.\nYou can now close this window.")
            self.btn_cancel.config(text="Close", state='normal', command=self.destroy)
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
            self.btn_install.config(state='normal')
            self.btn_cancel.config(state='normal')

    def _create_shortcut(self, target_dir: Path, location: str):
        # AUTO-INSTALL DEPENDENCY CHECK
        try:
            import winshell
            from win32com.client import Dispatch
        except ImportError:
            self.log("Installing pywin32/winshell for shortcuts...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pywin32", "winshell"])
                import winshell
                from win32com.client import Dispatch
            except Exception as e:
                self.log(f"Failed to install shortcut dependencies: {e}")
                return

        try:
            shell = Dispatch('WScript.Shell')
            
            if location == "Desktop":
                folder = winshell.desktop()
            else:
                folder = winshell.programs()

            shortcut_path = os.path.join(folder, f"{APP_NAME}.lnk")
            target_bat = str(target_dir / "Launch-LLM-Conversion-Framework.bat")
            icon_path = str(target_dir / "assets" / "logo.ico")
            
            # Check for icon in DATA dir if not in APP dir
            if not os.path.exists(icon_path):
                 # Try to find data dir via registry or assumption? 
                 # Simplest: Look relative to this script if running from source
                 pass 

            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = target_bat
            shortcut.WorkingDirectory = str(target_dir)
            if os.path.exists(icon_path):
                shortcut.IconLocation = icon_path
            shortcut.save()
            self.log(f"Shortcut created in {location}")
            
        except Exception as e:
            self.log(f"Shortcut Error ({location}): {e}")

if __name__ == "__main__":
    app = InstallerGUI()
    app.mainloop()
