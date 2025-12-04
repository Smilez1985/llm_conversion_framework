#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows GUI Installer
DIREKTIVE: Goldstandard, Robustness, User Experience.

Zweck:
Installiert das Framework in ein definiertes Verzeichnis (Standard: Public Documents).
Erstellt VENV, installiert Abhängigkeiten und verknüpft den Launcher.
"""

import os
import sys
import shutil
import subprocess
import threading
import time
import ctypes
from pathlib import Path

# GUI Imports (Standard Python Library)
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

# Konfiguration
APP_NAME = "LLM-Conversion-Framework"
DEFAULT_INSTALL_PATH = Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Documents" / "llm_conversion_framework"
SOURCE_DIR = Path(__file__).resolve().parent.parent
MARKER_FILE = SOURCE_DIR / ".install_complete"

# Dateien/Ordner, die kopiert werden sollen
INCLUDE_DIRS = ["orchestrator", "targets", "configs", "assets", "Docker Setup"]
INCLUDE_FILES = ["README.md", "LICENSE", "pyproject.toml", "requirements.txt"]
IGNORE_PATTERNS = ["__pycache__", "*.pyc", ".git", ".venv", "venv", "dist", "build"]

class InstallerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} Installer")
        self.geometry("600x450")
        self.resizable(False, False)
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self._init_ui()
        
    def _init_ui(self):
        # Header
        header = ttk.Frame(self, padding="20")
        header.pack(fill=tk.X)
        lbl_title = ttk.Label(header, text=f"Install {APP_NAME}", font=("Segoe UI", 16, "bold"))
        lbl_title.pack(anchor=tk.W)
        lbl_desc = ttk.Label(header, text="This wizard will set up the framework on your computer.")
        lbl_desc.pack(anchor=tk.W)
        
        # Path Selection
        path_frame = ttk.LabelFrame(self, text="Installation Directory", padding="10")
        path_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.var_path = tk.StringVar(value=str(DEFAULT_INSTALL_PATH))
        entry_path = ttk.Entry(path_frame, textvariable=self.var_path)
        entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_browse = ttk.Button(path_frame, text="Browse...", command=self._browse_path)
        btn_browse.pack(side=tk.RIGHT)
        
        # Options
        opt_frame = ttk.Frame(self, padding="0 20")
        opt_frame.pack(fill=tk.X, padx=20)
        
        self.var_hidden = tk.BooleanVar(value=True)
        chk_hidden = ttk.Checkbutton(opt_frame, text="Hide installation folder (Recommended)", variable=self.var_hidden)
        chk_hidden.pack(anchor=tk.W)
        
        self.var_desktop = tk.BooleanVar(value=True)
        chk_desktop = ttk.Checkbutton(opt_frame, text="Create Desktop Shortcut", variable=self.var_desktop)
        chk_desktop.pack(anchor=tk.W)
        
        # Log Area
        log_frame = ttk.LabelFrame(self, text="Installation Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        
        self.log_text = ScrolledText(log_frame, height=8, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Progress
        self.progress = ttk.Progressbar(self, mode='determinate')
        self.progress.pack(fill=tk.X, padx=20, pady=(0, 5))
        
        # Buttons
        btn_frame = ttk.Frame(self, padding="20")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.btn_install = ttk.Button(btn_frame, text="Install", command=self._start_install)
        self.btn_install.pack(side=tk.RIGHT)
        
        self.btn_cancel = ttk.Button(btn_frame, text="Cancel", command=self.destroy)
        self.btn_cancel.pack(side=tk.RIGHT, padx=10)

    def _browse_path(self):
        d = filedialog.askdirectory(initialdir=self.var_path.get())
        if d: self.var_path.set(d)

    def log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.update_idletasks()

    def _start_install(self):
        target_dir = Path(self.var_path.get())
        
        # UI Lock
        self.btn_install.config(state='disabled')
        self.btn_cancel.config(state='disabled')
        self.progress['value'] = 0
        
        # Threading
        threading.Thread(target=self._install_process, args=(target_dir,), daemon=True).start()

    def _install_process(self, target: Path):
        try:
            self.log(f"Starting installation to: {target}")
            
            # 1. Prepare Directory
            self.log("Creating directories...")
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
            
            # 2. Copy Files
            self.log("Copying core files...")
            total_items = len(INCLUDE_DIRS) + len(INCLUDE_FILES)
            current = 0
            
            # Directories
            for item in INCLUDE_DIRS:
                src = SOURCE_DIR / item
                dst = target / item
                if src.exists():
                    self.log(f"  - Copying {item}...")
                    # Remove existing if present to ensure clean update
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))
                current += 1
                self.progress['value'] = (current / total_items) * 30 # Copy is 30% of work
            
            # Files
            for item in INCLUDE_FILES:
                src = SOURCE_DIR / item
                dst = target / item
                if src.exists():
                    shutil.copy2(src, dst)
                current += 1
                self.progress['value'] = (current / total_items) * 30
            
            # Make Folder Hidden?
            if self.var_hidden.get():
                self.log("Hiding installation folder...")
                try:
                    # Windows API to set file attributes (0x02 = Hidden)
                    ctypes.windll.kernel32.SetFileAttributesW(str(target), 0x02)
                except Exception as e:
                    self.log(f"Warning: Could not hide folder: {e}")

            # 3. Setup VENV in TARGET
            self.log("Creating Virtual Environment (this takes time)...")
            self.progress['value'] = 40
            
            venv_path = target / ".venv"
            python_exe = sys.executable
            
            subprocess.run([python_exe, "-m", "venv", str(venv_path)], check=True)
            
            # 4. Install Dependencies
            self.log("Installing Dependencies (pip)...")
            self.progress['value'] = 60
            
            pip_exe = venv_path / "Scripts" / "pip.exe"
            
            # Upgrade pip
            subprocess.run([str(pip_exe), "install", "--upgrade", "pip"], 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Install requirements (we copied pyproject.toml)
            # We use pip install . to install the package in editable mode or as package
            # But for robustness, we install dependencies first
            cwd = str(target)
            subprocess.run([str(pip_exe), "install", "."], cwd=cwd, 
                         capture_output=False, creationflags=subprocess.CREATE_NO_WINDOW) # Show output in console for debug if needed? Better capture.
            
            self.progress['value'] = 90

            # 5. Create Desktop Shortcut (Optional)
            if self.var_desktop.get():
                self._create_shortcut(target)

            # 6. Finalize: Write Marker to SOURCE (so Launcher knows where we installed)
            self.log("Finalizing...")
            with open(MARKER_FILE, "w") as f:
                f.write(str(target))
            
            # Hide Marker File too?
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(MARKER_FILE), 0x02)
            except: pass
            
            self.progress['value'] = 100
            self.log("Installation Complete!")
            
            messagebox.showinfo("Success", "Installation finished successfully!\nThe application will start now.")
            self.quit()
            
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            messagebox.showerror("Error", f"Installation failed:\n{e}")
            self.btn_install.config(state='normal')
            self.btn_cancel.config(state='normal')

    def _create_shortcut(self, target_path: Path):
        try:
            self.log("Creating Desktop Shortcut...")
            import winshell
            from win32com.client import Dispatch

            desktop = winshell.desktop()
            path = os.path.join(desktop, f"{APP_NAME}.lnk")
            
            # Das Ziel des Shortcuts ist der Launcher im Quellverzeichnis!
            # ODER: Wir erstellen eine neue Batch im Ziel, aber der User hat ja den Launcher.
            # User will Launcher nutzen. Also Shortcut auf den Launcher im Source-Dir?
            # NEIN: Der Launcher im Source Dir ist der Einstiegspunkt.
            
            # Strategy: Shortcut points to Launch-LLM-Conversion-Framework.bat in SOURCE_DIR
            # Reason: Updates via git pull happen in SOURCE_DIR.
            
            launcher_bat = SOURCE_DIR / "Launch-LLM-Conversion-Framework.bat"
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = str(launcher_bat)
            shortcut.WorkingDirectory = str(SOURCE_DIR)
            shortcut.IconLocation = str(target_path / "assets" / "logo.ico") # Falls icon da ist
            shortcut.save()
            
        except ImportError:
            self.log("Warning: pywin32 not installed, cannot create shortcut.")
        except Exception as e:
            self.log(f"Warning: Failed to create shortcut: {e}")

if __name__ == "__main__":
    try:
        app = InstallerGUI()
        app.mainloop()
    except Exception as e:
        # Fallback für CLI/Log
        with open("installer_crash.log", "w") as f:
            f.write(str(e))
        sys.exit(1)
