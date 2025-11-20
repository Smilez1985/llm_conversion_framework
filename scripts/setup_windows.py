#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Full Repo Install)
DIREKTIVE: Goldstandard, GUI-basiert, Netzwerk-Resilient.

Zweck:
- Prüft Systemvoraussetzungen (Docker, Git, Internet)
- Kopiert das GESAMTE Repository-Gerüst in den Zielordner (für Auto-Update)
- Kopiert die kompilierte Launcher-EXE hinein
- Erstellt Verknüpfungen
- Lädt Docker-Images vor
"""

import os
import sys
import shutil
import subprocess
import time
import socket
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tempfile

# Konfiguration
APP_NAME = "LLM-Builder"
# Der Installer läuft im Repo-Root/scripts. Wir brauchen das Repo-Root.
REPO_ROOT = Path(__file__).resolve().parent.parent
# Die Launcher EXE muss vor dem Bau des Installers erstellt worden sein und in dist/ liegen.
LAUNCHER_EXE_SOURCE = REPO_ROOT / "dist" / f"{APP_NAME}.exe"
PING_HOST = "8.8.8.8"

# Ordner, die NICHT zum User kopiert werden sollen
IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git", ".gitignore", ".gitattributes",
    ".venv", "venv", "env",
    "__pycache__", "*.pyc", "*.pyd",
    "dist", "build", "*.spec", # Installer-Build-Artefakte
    "output", "cache", "logs", # Laufzeit-Ordner (werden frisch erstellt)
    "tmp", "temp"
)

class InstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Install {APP_NAME}")
        self.root.geometry("600x500")
        self.root.resizable(False, False)
        
        # Styles
        style = ttk.Style()
        style.configure("TButton", padding=6)
        style.configure("TLabel", padding=5)
        
        # Header
        header = ttk.Label(root, text=f"Welcome to {APP_NAME} Setup", font=("Segoe UI", 16, "bold"))
        header.pack(pady=20)
        
        # --- Dependency Status Area ---
        self.status_frame = ttk.LabelFrame(root, text="System Requirements Check", padding=10)
        self.status_frame.pack(fill="x", padx=20, pady=5)
        
        self.lbl_docker = self.add_status_row("Docker Desktop (WSL2):", "Checking...")
        self.lbl_git = self.add_status_row("Git for Windows:", "Checking...")
        self.lbl_net = self.add_status_row("Internet Connectivity:", "Checking...")
        
        # --- Install Location Area ---
        loc_frame = ttk.LabelFrame(root, text="Installation Location", padding=10)
        loc_frame.pack(fill="x", padx=20, pady=10)
        
        ttk.Label(loc_frame, text="Where do you want to install the Framework?").pack(anchor="w")
        
        # Smart Defaults
        self.user_profile = os.environ['USERPROFILE']
        self.local_appdata = os.environ['LOCALAPPDATA']
        self.paths = {
            "Local AppData (Recommended)": os.path.join(self.local_appdata, 'Programs', 'LLM-Framework'),
            "Documents": os.path.join(self.user_profile, 'Documents', 'LLM-Framework'),
            "Desktop": os.path.join(self.user_profile, 'Desktop', 'LLM-Framework')
        }
        
        self.path_var = tk.StringVar(value=self.paths["Local AppData (Recommended)"])
        
        # Dropdown & Browse Grid
        grid_frm = ttk.Frame(loc_frame)
        grid_frm.pack(fill="x", pady=5)
        
        self.combo = ttk.Combobox(grid_frm, textvariable=self.path_var, values=list(self.paths.values()))
        self.combo.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn_browse = ttk.Button(grid_frm, text="Browse...", command=self.browse_path)
        btn_browse.pack(side="right")
        
        # Shortcut Checkbox
        self.create_shortcut = tk.BooleanVar(value=True)
        ttk.Checkbutton(loc_frame, text="Create Desktop Shortcut", variable=self.create_shortcut).pack(anchor="w", pady=5)

        # --- Progress Area ---
        self.progress_frame = ttk.Frame(root)
        self.progress_frame.pack(fill="x", padx=20, pady=10)
        
        self.lbl_action = ttk.Label(self.progress_frame, text="Ready to install")
        self.lbl_action.pack(anchor="w")
        
        self.progress = ttk.Progressbar(self.progress_frame, mode='determinate')
        self.progress.pack(fill="x", pady=5)
        
        # --- Buttons ---
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill="x", side="bottom", padx=20, pady=20)
        
        self.btn_install = ttk.Button(btn_frame, text="Install", command=self.start_installation, state="disabled")
        self.btn_install.pack(side="right")
        
        ttk.Button(btn_frame, text="Exit", command=root.destroy).pack(side="right", padx=10)
        
        # Check if source EXE exists
        if not LAUNCHER_EXE_SOURCE.exists():
             messagebox.showerror("Build Error", f"Launcher EXE not found at:\n{LAUNCHER_EXE_SOURCE}\n\nPlease run 'python scripts/build_launcher.py' first!")
             root.destroy()
             sys.exit(1)

        # Start Checks immediately
        threading.Thread(target=self.run_checks, daemon=True).start()

    def add_status_row(self, label_text, status_text):
        frm = ttk.Frame(self.status_frame)
        frm.pack(fill="x", pady=2)
        ttk.Label(frm, text=label_text, width=25).pack(side="left")
        lbl = ttk.Label(frm, text=status_text, foreground="blue")
        lbl.pack(side="left")
        return lbl

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            # Append folder name if user picked a root like "Documents"
            if not path.endswith("LLM-Framework"):
                 path = os.path.join(path, "LLM-Framework")
            self.path_var.set(path)

    # --- CHECKS ---
    def run_checks(self):
        reqs_met = True
        
        # 1. Docker Check
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.update_status(self.lbl_docker, "✅ Detected", "green")
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.update_status(self.lbl_docker, "❌ Not Found!", "red")
            reqs_met = False

        # 2. Git Check
        try:
            subprocess.run(["git", "--version"], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.update_status(self.lbl_git, "✅ Detected", "green")
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.update_status(self.lbl_git, "❌ Not Found (Required for Updates)!", "red")
            # Warning only, installation can proceed
            
        # 3. Network Check
        if self.check_connectivity():
            self.update_status(self.lbl_net, "✅ Online", "green")
        else:
            self.update_status(self.lbl_net, "⚠️ Offline / Unstable", "orange")
            # Warning only
            
        if reqs_met:
            self.root.after(0, lambda: self.btn_install.configure(state="normal"))
        else:
             messagebox.showerror("Missing Requirements", "Docker Desktop is required. Please install it first.")

    def check_connectivity(self):
        try:
            socket.create_connection((PING_HOST, 53), timeout=3)
            return True
        except OSError:
            return False

    def update_status(self, label_widget, text, color):
        self.root.after(0, lambda: label_widget.configure(text=text, foreground=color))

    # --- INSTALLATION LOGIC ---
    def start_installation(self):
        self.btn_install.configure(state="disabled")
        threading.Thread(target=self.install_process, daemon=True).start()

    def install_process(self):
        target_dir = Path(self.path_var.get())
        exe_target = target_dir / f"{APP_NAME}.exe"
        
        self.update_progress(10)
        self.update_action(f"Preparing installation target: {target_dir}...")

        try:
            # 1. Clean target directory if it exists
            if target_dir.exists():
                self.update_action("Cleaning existing installation...")
                shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)

            # 2. Copy REPO Structure (The "Rich Environment")
            self.update_progress(30)
            self.update_action("Copying framework files...")
            
            # We copy the whole REPO_ROOT to target_dir, applying ignore patterns
            shutil.copytree(REPO_ROOT, target_dir, ignore=IGNORE_PATTERNS, dirs_exist_ok=True)

            # 3. Copy the Launcher EXE into the rich environment
            self.update_progress(50)
            self.update_action("Installing launcher...")
            shutil.copy2(LAUNCHER_EXE_SOURCE, exe_target)
            
            # 4. Create necessary runtime directories (empty)
            for d in ["output", "cache", "logs"]:
                (target_dir / d).mkdir(exist_ok=True)
                
            # OPTIONAL: Initialize Git in target for future pulls if git is present
            # (Requires git command line tool on user machine)
            # subprocess.run(["git", "init"], cwd=target_dir, capture_output=True)
            # subprocess.run(["git", "remote", "add", "origin", "YOUR_REPO_URL"], cwd=target_dir, ...)


        except Exception as e:
            messagebox.showerror("Install Error", f"Failed to copy files:\n{e}")
            self.root.after(0, lambda: self.btn_install.configure(state="normal"))
            return

        # 5. Create Shortcut
        self.update_progress(70)
        if self.create_shortcut.get():
            self.update_action("Creating Desktop Shortcut...")
            self.create_desktop_shortcut(exe_target)

        # 6. Pull Docker Images (Robust Loop)
        self.update_progress(85)
        self.update_action("Pre-pulling Docker Images (may take a while)...")
        if self.check_connectivity():
             if not self.pull_docker_images_robust():
                messagebox.showwarning("Network Warning", "Could not pull all Docker images. The first build might be slower.")
        else:
             self.update_action("Skipping Docker pull (Offline).")

        self.update_progress(100)
        self.update_action("Installation Complete!")
        messagebox.showinfo("Success", f"{APP_NAME} has been successfully installed to:\n{target_dir}")
        self.root.destroy()

    def create_desktop_shortcut(self, target_path):
        desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        shortcut_path = os.path.join(desktop, f"{APP_NAME}.lnk")
        
        vbs_script = f"""
        Set oWS = WScript.CreateObject("WScript.Shell")
        sLinkFile = "{shortcut_path}"
        Set oLink = oWS.CreateShortcut(sLinkFile)
        oLink.TargetPath = "{target_path}"
        oLink.WorkingDirectory = "{target_path.parent}"
        oLink.Description = "Launch LLM Cross-Compiler Framework"
        oLink.Save
        """
        
        try:
            vbs_file = Path(tempfile.gettempdir()) / "create_shortcut.vbs"
            with open(vbs_file, "w") as f:
                f.write(vbs_script)
            subprocess.run(["cscript", "//Nologo", str(vbs_file)], check=True, capture_output=True)
            vbs_file.unlink()
        except Exception as e:
            print(f"Failed to create shortcut: {e}")

    def pull_docker_images_robust(self):
        """Pulls Docker images with Ping-Loop Pause"""
        # Images needed for the framework
        images = [
            "debian:bookworm-slim",
            "quay.io/vektorlab/ctop:latest",
            "wagoodman/dive:latest",
            # Add target-specific base images here if known, e.g.:
            # "ubuntu:22.04"
        ]
        
        for img in images:
            retries = 0
            while retries < 5:
                if self.check_connectivity():
                    self.update_action(f"Pulling {img}...")
                    try:
                        # Versuch Pull
                        subprocess.run(["docker", "pull", img], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
                        break # Success
                    except subprocess.CalledProcessError:
                        self.update_action(f"Retrying {img} (Attempt {retries+1}/5)...")
                        retries += 1
                        time.sleep(2)
                else:
                    self.update_action("Network lost. Paused. Waiting for connection...")
                    time.sleep(5) 
            if retries == 5:
                 print(f"Failed to pull {img} after retries.")
                 return False
        return True

    def update_action(self, text):
        self.root.after(0, lambda: self.lbl_action.configure(text=text))

    def update_progress(self, value):
        self.root.after(0, lambda: self.progress.configure(value=value))

if __name__ == "__main__":
    # Ensure we are running from the scripts directory so relative paths work
    os.chdir(Path(__file__).parent)
    
    root = tk.Tk()
    app = InstallerGUI(root)
    root.mainloop()
