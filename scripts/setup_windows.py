#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows GUI Installer (v3.0 Enterprise)
DIREKTIVE: Goldstandard, Docker-Guard, Admin-Mode, Robust File Copy.
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

# Dependencies (vom Launcher vorinstalliert)
import psutil
import requests

# GUI Imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

APP_NAME = "LLM-Conversion-Framework"

# Zentrale Config
CHECKFILE_DIR = Path("C:/Users/Public/Documents/llm_conversion_framework")
CHECKFILE_PATH = CHECKFILE_DIR / "checkfile.txt"

# Standard-Pfade
DEFAULT_APP_PATH = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / APP_NAME
DEFAULT_DATA_PATH = Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Documents" / APP_NAME

SOURCE_DIR = Path(__file__).resolve().parent.parent

# Kopier-Listen
INCLUDE_DATA_DIRS = ["orchestrator", "targets", "configs", "assets", "Docker Setup"]
INCLUDE_DATA_FILES = ["pyproject.toml", "requirements.txt", ".gitignore"]
IGNORE_PATTERNS = ["__pycache__", "*.pyc", ".git", ".venv", "venv", "dist", "build"]

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Installer v3.0")
        self.geometry("800x700")
        self.resizable(True, True)
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Docker Pre-Flight Check vor UI Init
        self.docker_ok = False
        
        self._init_ui()
        
        # Starte Docker Check im Hintergrund nach UI-Load
        self.after(500, self._check_docker_background)

    def _init_ui(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header = ttk.Frame(main_frame)
        header.pack(fill=tk.X, pady=(0, 15))
        lbl_title = ttk.Label(header, text=f"Install {APP_NAME}", font=("Segoe UI", 18, "bold"))
        lbl_title.pack(anchor=tk.W)
        
        # Status Banner (für Docker Check)
        self.lbl_status = ttk.Label(main_frame, text="Checking System Requirements...", foreground="blue")
        self.lbl_status.pack(fill=tk.X, pady=(0, 10))

        # Paths
        grp_app = ttk.LabelFrame(main_frame, text="Application Path (Launcher & Uninstaller)", padding="10")
        grp_app.pack(fill=tk.X, pady=5)
        self.var_app_path = tk.StringVar(value=str(DEFAULT_APP_PATH))
        e_app = ttk.Entry(grp_app, textvariable=self.var_app_path)
        e_app.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(grp_app, text="Browse...", command=lambda: self._browse(self.var_app_path)).pack(side=tk.RIGHT)
        
        grp_data = ttk.LabelFrame(main_frame, text="Data Path (Core, VENV - Hidden)", padding="10")
        grp_data.pack(fill=tk.X, pady=5)
        self.var_data_path = tk.StringVar(value=str(DEFAULT_DATA_PATH))
        e_data = ttk.Entry(grp_data, textvariable=self.var_data_path)
        e_data.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(grp_data, text="Browse...", command=lambda: self._browse(self.var_data_path)).pack(side=tk.RIGHT)
        
        # Options
        opt_frame = ttk.Frame(main_frame)
        opt_frame.pack(fill=tk.X, pady=10)
        self.var_desktop = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Create Desktop Shortcut", variable=self.var_desktop).pack(anchor=tk.W)
        
        # Log
        log_frame = ttk.LabelFrame(main_frame, text="Installation Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.log_text = ScrolledText(log_frame, height=12, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Progress
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.btn_install = ttk.Button(btn_frame, text="Install", command=self._start_install, state='disabled') # Disabled until check pass
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

    # --- DOCKER CHECK LOGIC ---
    def _check_docker_background(self):
        threading.Thread(target=self._check_docker, daemon=True).start()

    def _check_docker(self):
        self.log("Checking Docker environment...")
        
        # 1. Check if installed
        docker_exe = shutil.which("docker")
        if not docker_exe:
            self.lbl_status.config(text="Docker not found! Please install Docker Desktop.", foreground="red")
            self.log("CRITICAL: Docker not found.")
            ans = messagebox.askyesno("Docker Missing", "Docker Desktop is required but not found.\nDownload now?")
            if ans: webbrowser.open("https://www.docker.com/products/docker-desktop/")
            return # Keep Install disabled

        # 2. Check if running
        running = False
        for proc in psutil.process_iter(['name']):
            if "Docker Desktop" in proc.info['name']:
                running = True
                break
        
        if not running:
            self.log("Docker Desktop not running. Attempting start...")
            self.lbl_status.config(text="Starting Docker Desktop...", foreground="orange")
            try:
                # Try standard path
                dd_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
                if os.path.exists(dd_path):
                    subprocess.Popen([dd_path])
                    # Wait loop
                    for i in range(30):
                        self.log(f"Waiting for Docker... {i+1}/30")
                        time.sleep(1)
                        # Check API availability
                        try:
                            res = subprocess.run(["docker", "info"], capture_output=True)
                            if res.returncode == 0:
                                running = True
                                break
                        except: pass
                else:
                    self.log(f"Could not find Docker Desktop at {dd_path}")
            except Exception as e:
                self.log(f"Failed to start Docker: {e}")

        # Final Verification via CLI
        try:
            res = subprocess.run(["docker", "info"], capture_output=True)
            if res.returncode == 0:
                self.docker_ok = True
                self.lbl_status.config(text="System Ready. Docker is running.", foreground="green")
                self.btn_install.config(state='normal')
                self.log("Docker check passed.")
            else:
                self.lbl_status.config(text="Docker Error. Is WSL2 running?", foreground="red")
                self.log("Docker daemon not responding.")
                messagebox.showwarning("Docker Error", "Docker Desktop is installed but not responding.\nPlease start it manually.")
        except:
            self.lbl_status.config(text="Docker Check Failed.", foreground="red")

    # --- INSTALLATION ---
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
            
            if not app_dir.exists(): app_dir.mkdir(parents=True, exist_ok=True)
            if not data_dir.exists(): data_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(data_dir), 0x02) # Hide Data
            except: pass

            # 1. Copy DATA Files (Core)
            self.log("Copying framework core to Data directory...")
            total_items = len(INCLUDE_DATA_DIRS) + len(INCLUDE_DATA_FILES) + 2 # +2 for special files
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
            
            # 2. Copy APP Files (Launcher & Uninstaller)
            self.log("Copying executables to Application directory...")
            
            # Launcher
            src_launcher = SOURCE_DIR / "Launch-LLM-Conversion-Framework.bat"
            if src_launcher.exists():
                shutil.copy2(src_launcher, app_dir / "Launch-LLM-Conversion-Framework.bat")
            else:
                self.log("WARNING: Launcher .bat not found in source root!")
            
            # Uninstaller (liegt in scripts/)
            src_uninstaller = SOURCE_DIR / "scripts" / "Uninstall-LLM-Conversion-Framework.bat"
            if src_uninstaller.exists():
                shutil.copy2(src_uninstaller, app_dir / "Uninstall-LLM-Conversion-Framework.bat")
            else:
                self.log(f"WARNING: Uninstaller not found at {src_uninstaller}")

            self.progress['value'] = 60

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
            subprocess.run([str(pip_exe), "install", "pywin32", "winshell"], 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

            self.progress['value'] = 90

            # 5. Shortcuts
            if self.var_desktop.get():
                self._create_shortcut(app_dir, data_dir, "Desktop")

            # 6. Central Checkfile
            self.log("Writing Configuration...")
            if not CHECKFILE_DIR.exists():
                CHECKFILE_DIR.mkdir(parents=True, exist_ok=True)
            
            with open(CHECKFILE_PATH, "w") as f:
                f.write(f"Path={data_dir}") # WICHTIG: Launcher braucht Pfad zur MAIN.PY (im Data Dir)
            
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(CHECKFILE_DIR), 0x02)
                ctypes.windll.kernel32.SetFileAttributesW(str(CHECKFILE_PATH), 0x02)
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

    def _create_shortcut(self, app_dir: Path, data_dir: Path, location: str):
        try:
            import winshell
            from win32com.client import Dispatch
            
            shell = Dispatch('WScript.Shell')
            if location == "Desktop":
                folder = winshell.desktop()
            else:
                folder = winshell.programs()

            shortcut_path = os.path.join(folder, f"{APP_NAME}.lnk")
            # Target ist der LAUNCHER im APP DIR
            target_bat = str(app_dir / "Launch-LLM-Conversion-Framework.bat")
            
            # Icon suchen (Priorität: llm-builder.ico > logo.ico)
            icon_path = ""
            candidates = ["llm-builder.ico", "logo.ico", "icon.ico"]
            
            # Suche im Data-Dir/assets (da haben wir sie hin kopiert)
            asset_dir = data_dir / "assets"
            for c in candidates:
                p = asset_dir / c
                if p.exists():
                    icon_path = str(p)
                    break
            
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = target_bat
            shortcut.WorkingDirectory = str(app_dir)
            
            if icon_path:
                shortcut.IconLocation = icon_path
            
            shortcut.save()
            self.log(f"Shortcut created on {location}")
            
        except Exception as e:
            self.log(f"Shortcut Error: {e}")

if __name__ == "__main__":
    app = InstallerGUI()
    app.mainloop()
