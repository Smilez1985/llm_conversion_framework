#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows GUI Installer (Fixed)
DIREKTIVE: Goldstandard. Creates Shortcuts correctly. Data folder visible.
"""

import os
import sys
import shutil
import subprocess
import threading
import time
import ctypes
import winreg
import webbrowser
from pathlib import Path

# GUI Imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

APP_NAME = "LLM-Conversion-Framework"
APP_TITLE = "LLM Conversion Framework"

# Zentrale Pfade
CHECKFILE_DIR = Path("C:/Users/Public/Documents/llm_conversion_framework")
CHECKFILE_PATH = CHECKFILE_DIR / "checkfile.txt"

# Standard-Pfade
DEFAULT_APP_PATH = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / APP_NAME
DEFAULT_DATA_PATH = Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Documents" / APP_NAME
SOURCE_DIR = Path(__file__).resolve().parent.parent

# Files to copy
INCLUDE_APP_FILES = ["Launch-LLM-Conversion-Framework.bat", "README.md", "LICENSE"]
INCLUDE_DATA_DIRS = ["orchestrator", "targets", "configs", "assets", "Docker Setup"]
INCLUDE_DATA_FILES = ["pyproject.toml", "poetry.lock", "requirements.txt", ".gitignore"]
IGNORE_PATTERNS = ["__pycache__", "*.pyc", ".git", ".venv", "venv", "dist", "build", ".installer_venv"]

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} Installer")
        self.geometry("800x700")
        self.resizable(True, True)
        
        # Versuche Icon für das Fenster zu setzen
        try:
            icon_path = SOURCE_DIR / "assets" / "setup_LLM-Builder.ico"
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
        except: pass
        
        self._init_ui()
        # Docker Check im Hintergrund
        self.after(500, self._check_docker_background)

    def _init_ui(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        lbl_title = ttk.Label(main_frame, text=f"Install {APP_TITLE}", font=("Segoe UI", 16, "bold"))
        lbl_title.pack(anchor=tk.W, pady=(0, 10))
        
        self.lbl_status = ttk.Label(main_frame, text="Checking System...", foreground="blue")
        self.lbl_status.pack(fill=tk.X, pady=(0, 10))

        # Paths
        grp_paths = ttk.LabelFrame(main_frame, text="Installation Paths", padding="10")
        grp_paths.pack(fill=tk.X, pady=5)
        
        ttk.Label(grp_paths, text="Application (Launcher):").pack(anchor=tk.W)
        self.var_app_path = tk.StringVar(value=str(DEFAULT_APP_PATH))
        e_app = ttk.Frame(grp_paths)
        e_app.pack(fill=tk.X, pady=(0,5))
        ttk.Entry(e_app, textvariable=self.var_app_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(e_app, text="Browse", command=lambda: self._browse(self.var_app_path)).pack(side=tk.RIGHT, padx=(5,0))

        ttk.Label(grp_paths, text="Data & Artifacts (Public Documents):").pack(anchor=tk.W)
        self.var_data_path = tk.StringVar(value=str(DEFAULT_DATA_PATH))
        e_data = ttk.Frame(grp_paths)
        e_data.pack(fill=tk.X)
        ttk.Entry(e_data, textvariable=self.var_data_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(e_data, text="Browse", command=lambda: self._browse(self.var_data_path)).pack(side=tk.RIGHT, padx=(5,0))
        
        # Options
        opt_frame = ttk.Frame(main_frame)
        opt_frame.pack(fill=tk.X, pady=10)
        self.var_desktop = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Create Desktop Shortcuts (App & Data Folder)", variable=self.var_desktop).pack(anchor=tk.W)
        
        # Log
        self.log_text = ScrolledText(main_frame, height=12, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Progress
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.btn_install = ttk.Button(btn_frame, text="Install Now", command=self._start_install, state='disabled')
        self.btn_install.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=10)

    def _browse(self, var):
        d = filedialog.askdirectory(initialdir=var.get())
        if d: var.set(d)

    def log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.update_idletasks()

    def _check_docker_background(self):
        threading.Thread(target=self._check_docker, daemon=True).start()

    def _check_docker(self):
        self.log("Checking Docker (Required for conversion modules)...")
        # Simple check - full verification happens in app
        docker_exe = shutil.which("docker")
        if docker_exe:
            self.lbl_status.config(text="System Ready.", foreground="green")
            self.btn_install.config(state='normal')
            self.log("Docker detected.")
        else:
            self.lbl_status.config(text="Docker not found (Warning).", foreground="orange")
            self.btn_install.config(state='normal') # Allow install anyway
            self.log("WARNING: Docker not found. You can install, but some features won't work.")

    def _start_install(self):
        target_dir = Path(self.var_app_path.get())
        data_dir = Path(self.var_data_path.get())
        
        self.btn_install.config(state='disabled')
        self.progress['value'] = 0
        threading.Thread(target=self._install_process, args=(target_dir, data_dir), daemon=True).start()

    def _install_process(self, app_dir: Path, data_dir: Path):
        try:
            self.log(f"--- Starting Installation ---")
            self.log(f"App Dir:  {app_dir}")
            self.log(f"Data Dir: {data_dir}")
            
            # 1. Directories
            if not app_dir.exists(): app_dir.mkdir(parents=True, exist_ok=True)
            if not data_dir.exists(): data_dir.mkdir(parents=True, exist_ok=True)
            
            # WICHTIG: KEIN VERSTECKEN DES DATA DIRS MEHR!
            # Wir verstecken evtl. nur das checkfile später, aber nicht den Ordner.

            # 2. Copy Content
            self.log("Copying Framework files...")
            total_items = len(INCLUDE_DATA_DIRS) + len(INCLUDE_DATA_FILES) + 2
            current = 0
            
            # Copy Directories to Data
            for item in INCLUDE_DATA_DIRS:
                src = SOURCE_DIR / item
                dst = data_dir / item
                if src.exists():
                    if dst.exists(): shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))
                    self.log(f"Copied: {item}")
                current += 1
                self.progress['value'] = (current / total_items) * 40
            
            # Copy Files to Data
            for item in INCLUDE_DATA_FILES:
                src = SOURCE_DIR / item
                dst = data_dir / item
                if src.exists(): shutil.copy2(src, dst)
                current += 1
            
            # 3. Copy Launcher & Uninstall to App Dir
            src_launcher = SOURCE_DIR / "Launch-LLM-Conversion-Framework.bat"
            if src_launcher.exists():
                shutil.copy2(src_launcher, app_dir / "Launch-LLM-Conversion-Framework.bat")
            
            src_uninstaller = SOURCE_DIR / "scripts" / "Uninstall-LLM-Conversion-Framework.bat"
            if src_uninstaller.exists():
                shutil.copy2(src_uninstaller, app_dir / "Uninstall-LLM-Conversion-Framework.bat")

            self.progress['value'] = 50

            # 4. Setup VENV in Data Dir
            self.log("Creating isolated Python environment...")
            venv_path = data_dir / ".venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv_path)], 
                         check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            pip_exe = venv_path / "Scripts" / "pip.exe"
            
            # 5. Install Requirements
            req_file = data_dir / "requirements.txt"
            if req_file.exists():
                self.log("Installing dependencies (this may take a minute)...")
                # --no-warn-script-location suppress warnings about PATH
                subprocess.run([str(pip_exe), "install", "-r", "requirements.txt", "--no-warn-script-location"], 
                             cwd=str(data_dir), capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                
                # Install package itself in editable mode or normally
                subprocess.run([str(pip_exe), "install", "."], 
                             cwd=str(data_dir), capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.progress['value'] = 80

            # 6. Shortcuts
            if self.var_desktop.get():
                self.log("Creating Desktop Shortcuts...")
                
                # Shortcut 1: Die App (Launcher)
                self._create_shortcut(
                    name="LLM Conversion Framework",
                    target=str(app_dir / "Launch-LLM-Conversion-Framework.bat"),
                    work_dir=str(app_dir),
                    icon_path=str(data_dir / "assets" / "LLM-Builder.ico"),
                    desc="Start the Framework"
                )
                
                # Shortcut 2: Der Output Ordner (Artifacts)
                self._create_shortcut(
                    name="LLM Framework Data & Output",
                    target=str(data_dir),
                    work_dir=str(data_dir),
                    icon_path=str(data_dir / "assets" / "setup_LLM-Builder.ico"),
                    desc="Access your Models and Configs"
                )

            # 7. Checkfile (Pointer)
            self.log("Finalizing registration...")
            if not CHECKFILE_DIR.exists():
                CHECKFILE_DIR.mkdir(parents=True, exist_ok=True)
            
            with open(CHECKFILE_PATH, "w") as f:
                f.write(f'Path="{data_dir}"')
            
            # Nur Checkfile verstecken, nicht den Ordner!
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(CHECKFILE_PATH), 0x02)
            except: pass

            self.progress['value'] = 100
            self.log("Installation Complete!")
            messagebox.showinfo("Success", "Installation finished!\n\nYou can find the shortcuts on your desktop.")
            self.destroy()
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Installation Error", str(e))
            self.btn_install.config(state='normal')

    def _create_shortcut(self, name, target, work_dir, icon_path, desc):
        try:
            import winshell
            from win32com.client import Dispatch
            
            desktop = winshell.desktop()
            path = os.path.join(desktop, f"{name}.lnk")
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = work_dir
            shortcut.Description = desc
            
            if os.path.exists(icon_path):
                shortcut.IconLocation = icon_path
            
            shortcut.save()
            self.log(f"Created shortcut: {name}")
        except Exception as e:
            self.log(f"Failed to create shortcut {name}: {e}")

if __name__ == "__main__":
    app = InstallerGUI()
    app.mainloop()
