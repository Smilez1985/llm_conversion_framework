#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows GUI Installer
DIREKTIVE: Goldstandard, Robustness, User Experience.

Zweck:
Installiert die Applikation (Launcher) und richtet die Daten-Umgebung ein.
Trennt Programm (Program Files) von Daten (Public Documents).
"""

import os
import sys
import shutil
import subprocess
import threading
import time
import ctypes
from pathlib import Path

# GUI Imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

# Konfiguration
APP_NAME = "LLM-Conversion-Framework"

# Standard-Pfade
DEFAULT_APP_PATH = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / APP_NAME
DEFAULT_DATA_PATH = Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Documents" / APP_NAME

# Quelle (Wo liegt das Skript gerade?)
SOURCE_DIR = Path(__file__).resolve().parent.parent

# Dateien/Ordner, die kopiert werden sollen
# App: Nur Launcher und Entrypoints
INCLUDE_APP_FILES = ["Launch-LLM-Conversion-Framework.bat", "README.md", "LICENSE"]
# Daten: Der ganze Rest (Core, Targets, Configs)
INCLUDE_DATA_DIRS = ["orchestrator", "targets", "configs", "assets", "Docker Setup"]
INCLUDE_DATA_FILES = ["pyproject.toml", "requirements.txt", ".gitignore"]

IGNORE_PATTERNS = ["__pycache__", "*.pyc", ".git", ".venv", "venv", "dist", "build"]

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Installer")
        self.geometry("750x600") # Größer für bessere Sichtbarkeit
        self.resizable(True, True) # Skalierbar
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self._init_ui()
        
    def _init_ui(self):
        # Main Container
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header = ttk.Frame(main_frame)
        header.pack(fill=tk.X, pady=(0, 20))
        lbl_title = ttk.Label(header, text=f"Install {APP_NAME}", font=("Segoe UI", 18, "bold"))
        lbl_title.pack(anchor=tk.W)
        lbl_desc = ttk.Label(header, text="This wizard will set up the application and data directories.")
        lbl_desc.pack(anchor=tk.W)
        
        # 1. App Path (Program Files)
        grp_app = ttk.LabelFrame(main_frame, text="Application Directory (Launcher)", padding="10")
        grp_app.pack(fill=tk.X, pady=5)
        
        self.var_app_path = tk.StringVar(value=str(DEFAULT_APP_PATH))
        e_app = ttk.Entry(grp_app, textvariable=self.var_app_path)
        e_app.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        btn_app = ttk.Button(grp_app, text="Browse...", command=lambda: self._browse(self.var_app_path))
        btn_app.pack(side=tk.RIGHT)
        
        # 2. Data Path (Public Documents - Hidden)
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
        
        # Log Area
        log_frame = ttk.LabelFrame(main_frame, text="Installation Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.log_text = ScrolledText(log_frame, height=10, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Progress
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        # Buttons (Bottom)
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
        app_dir = Path(self.var_app_path.get())
        data_dir = Path(self.var_data_path.get())
        
        self.btn_install.config(state='disabled')
        self.btn_cancel.config(state='disabled')
        self.progress['value'] = 0
        
        threading.Thread(target=self._install_process, args=(app_dir, data_dir), daemon=True).start()

    def _install_process(self, app_dir: Path, data_dir: Path):
        try:
            self.log(f"Starting installation...")
            self.log(f"App:  {app_dir}")
            self.log(f"Data: {data_dir}")
            
            # 1. Create Directories
            self.log("Creating directories...")
            if not app_dir.exists(): app_dir.mkdir(parents=True, exist_ok=True)
            if not data_dir.exists(): data_dir.mkdir(parents=True, exist_ok=True)
            
            # Hide Data Dir
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(data_dir), 0x02) # Hidden
                self.log("Data directory set to hidden.")
            except: pass

            # 2. Copy Data Files (Core)
            self.log("Copying core framework to Data directory...")
            total_items = len(INCLUDE_DATA_DIRS) + len(INCLUDE_DATA_FILES) + len(INCLUDE_APP_FILES)
            current = 0
            
            for item in INCLUDE_DATA_DIRS:
                src = SOURCE_DIR / item
                dst = data_dir / item
                if src.exists():
                    if dst.exists(): shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))
                current += 1
                self.progress['value'] = (current / total_items) * 40
            
            for item in INCLUDE_DATA_FILES:
                src = SOURCE_DIR / item
                dst = data_dir / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1
            
            # 3. Copy App Files (Launcher)
            self.log("Copying launcher to App directory...")
            for item in INCLUDE_APP_FILES:
                src = SOURCE_DIR / item
                dst = app_dir / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1
                self.progress['value'] = (current / total_items) * 40

            # 4. Setup VENV in DATA DIR
            self.log("Creating Virtual Environment in Data directory...")
            self.progress['value'] = 50
            
            venv_path = data_dir / ".venv"
            python_exe = sys.executable
            
            subprocess.run([python_exe, "-m", "venv", str(venv_path)], check=True)
            
            # 5. Install Dependencies
            self.log("Installing Dependencies (this may take a while)...")
            self.progress['value'] = 70
            
            pip_exe = venv_path / "Scripts" / "pip.exe"
            
            # Upgrade pip
            subprocess.run([str(pip_exe), "install", "--upgrade", "pip"], 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Install from data dir
            cwd = str(data_dir)
            subprocess.run([str(pip_exe), "install", "."], cwd=cwd, 
                         capture_output=False, creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.progress['value'] = 90

            # 6. Link Launcher to Data
            # Wir erstellen die .install_complete im APP_DIR und schreiben den DATA_PATH rein
            self.log("Linking App to Data...")
            marker_file = app_dir / ".install_complete"
            with open(marker_file, "w") as f:
                f.write(str(data_dir))
            
            # 7. Shortcut
            if self.var_desktop.get():
                self._create_shortcut(app_dir)

            self.progress['value'] = 100
            self.log("Installation Complete!")
            
            messagebox.showinfo("Success", "Installation finished successfully!\nYou can start the app from the Desktop or Program Files.")
            self.quit()
            
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            messagebox.showerror("Error", f"Installation failed:\n{e}")
            self.btn_install.config(state='normal')
            self.btn_cancel.config(state='normal')

    def _create_shortcut(self, app_dir: Path):
        try:
            self.log("Creating Desktop Shortcut...")
            import winshell
            from win32com.client import Dispatch

            desktop = winshell.desktop()
            path = os.path.join(desktop, f"{APP_NAME}.lnk")
            target = app_dir / "Launch-LLM-Conversion-Framework.bat"
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = str(target)
            shortcut.WorkingDirectory = str(app_dir)
            
            # Icon suchen
            icon_path = app_dir / "assets" / "logo.ico"
            # Da assets im DATA dir liegen, müssen wir evtl. dort suchen, oder wir kopieren icon mit
            # Im aktuellen Skript kopieren wir assets nach DATA.
            # Fallback: Standard Icon oder Icon aus Source kopieren wenn nicht da
            
            shortcut.save()
            
        except ImportError:
            self.log("Warning: pywin32 not installed, shortcut creation skipped.")
        except Exception as e:
            self.log(f"Warning: Failed to create shortcut: {e}")

if __name__ == "__main__":
    try:
        app = InstallerGUI()
        app.mainloop()
    except Exception as e:
        with open("installer_crash.log", "w") as f:
            f.write(str(e))
        sys.exit(1)
