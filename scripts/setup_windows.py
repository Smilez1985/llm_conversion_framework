#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer
DIREKTIVE: Goldstandard, GUI-basiert, Netzwerk-Resilient.

Zweck:
- Prüft Systemvoraussetzungen (Docker, Git)
- Robuster Netzwerk-Check (Ping Loop)
- GUI zur Auswahl des Installationsorts (Desktop, AppData, Custom)
- Kopiert die LLM-Builder.exe und erstellt Verknüpfungen
- Lädt Docker-Images vor (Pre-Pull)
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
EXE_SOURCE = Path("dist") / f"{APP_NAME}.exe"
PING_HOST = "8.8.8.8"

class InstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Install {APP_NAME}")
        self.root.geometry("600x450")
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
        self.lbl_net = self.add_status_row("Internet Connectivity:", "Checking...")
        
        # --- Install Location Area ---
        loc_frame = ttk.LabelFrame(root, text="Installation Location", padding=10)
        loc_frame.pack(fill="x", padx=20, pady=10)
        
        ttk.Label(loc_frame, text="Where do you want to place the App?").pack(anchor="w")
        
        # Smart Defaults
        self.user_profile = os.environ['USERPROFILE']
        self.paths = {
            "Desktop": os.path.join(self.user_profile, 'Desktop'),
            "Local AppData": os.path.join(os.environ['LOCALAPPDATA'], 'Programs', 'LLM-Framework'),
            "Documents": os.path.join(self.user_profile, 'Documents', 'LLM-Framework')
        }
        
        self.path_var = tk.StringVar(value=self.paths["Desktop"])
        
        # Dropdown & Browse Grid
        grid_frm = ttk.Frame(loc_frame)
        grid_frm.pack(fill="x", pady=5)
        
        self.combo = ttk.Combobox(grid_frm, textvariable=self.path_var, values=list(self.paths.values()))
        self.combo.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.combo.bind("<<ComboboxSelected>>", self.on_combo_change)
        
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
        
        # Start Checks immediately
        threading.Thread(target=self.run_checks, daemon=True).start()

    def add_status_row(self, label_text, status_text):
        frm = ttk.Frame(self.status_frame)
        frm.pack(fill="x", pady=2)
        ttk.Label(frm, text=label_text, width=25).pack(side="left")
        lbl = ttk.Label(frm, text=status_text, foreground="blue")
        lbl.pack(side="left")
        return lbl

    def on_combo_change(self, event):
        pass

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)

    # --- CHECKS ---
    def run_checks(self):
        # 1. Docker Check
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.update_status(self.lbl_docker, "✅ Detected", "green")
            docker_ok = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.update_status(self.lbl_docker, "❌ Not Found! Please install Docker Desktop.", "red")
            docker_ok = False
        
        # 2. Network Check
        if self.check_connectivity():
            self.update_status(self.lbl_net, "✅ Online", "green")
            net_ok = True
        else:
            self.update_status(self.lbl_net, "⚠️ Offline / Unstable", "orange")
            net_ok = False
            
        if docker_ok:
            self.root.after(0, lambda: self.btn_install.configure(state="normal"))
        else:
             messagebox.showerror("Missing Requirements", "Docker Desktop is required to run the Framework. Please install it first.")

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
        
        # 1. Check Source EXE
        if not EXE_SOURCE.exists():
            self.update_action("Building .exe first (this may take a while)...")
            try:
                subprocess.run([sys.executable, "scripts/build_windows_exe.py"], check=True)
            except Exception as e:
                messagebox.showerror("Build Error", f"Failed to build executable: {e}")
                self.root.after(0, lambda: self.btn_install.configure(state="normal"))
                return

        # 2. Copy Files
        self.update_progress(20)
        self.update_action(f"Installing to {target_dir}...")
        
        try:
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(EXE_SOURCE, exe_target)
        except Exception as e:
            messagebox.showerror("Install Error", f"Failed to copy files: {e}")
            return

        # 3. Create Shortcut
        self.update_progress(50)
        if self.create_shortcut.get():
            self.update_action("Creating Shortcut...")
            self.create_desktop_shortcut(exe_target)

        # 4. Pull Docker Images (Robust Loop)
        self.update_progress(70)
        self.update_action("Pulling Docker Images (Network resilient)...")
        if not self.pull_docker_images_robust():
            messagebox.showwarning("Network Warning", "Could not pull all Docker images. You can still run the app, but the first build will be slower.")

        self.update_progress(100)
        self.update_action("Installation Complete!")
        messagebox.showinfo("Success", f"{APP_NAME} has been successfully installed!")
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
        oLink.Save
        """
        
        try:
            vbs_file = Path(tempfile.gettempdir()) / "create_shortcut.vbs"
            with open(vbs_file, "w") as f:
                f.write(vbs_script)
            subprocess.run(["cscript", "//Nologo", str(vbs_file)], check=True)
            vbs_file.unlink()
        except Exception as e:
            print(f"Failed to create shortcut: {e}")

    def pull_docker_images_robust(self):
        """Pulls Docker images with Ping-Loop Pause"""
        # Hier sind jetzt auch ctop und das Framework-Image enthalten
        images = [
            "debian:bookworm-slim",
            "quay.io/vektorlab/ctop:latest",
            "ghcr.io/llm-framework/rockchip:latest"
        ]
        
        for img in images:
            while True:
                if self.check_connectivity():
                    self.update_action(f"Pulling {img}...")
                    try:
                        # Versuch Pull
                        subprocess.run(["docker", "pull", img], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        break # Success
                    except subprocess.CalledProcessError:
                        self.update_action(f"Retrying {img}...")
                        time.sleep(2)
                else:
                    self.update_action("Network lost. Paused. Waiting for connection...")
                    time.sleep(2) 
        return True

    def update_action(self, text):
        self.root.after(0, lambda: self.lbl_action.configure(text=text))

    def update_progress(self, value):
        self.root.after(0, lambda: self.progress.configure(value=value))

if __name__ == "__main__":
    root = tk.Tk()
    app = InstallerGUI(root)
    root.mainloop()
