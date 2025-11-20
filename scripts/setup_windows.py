#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (PySide6 GUI)
DIREKTIVE: Goldstandard, vollständig, GUI-basiert (PySide6), Netzwerk-Resilient.

Zweck:
- Führt eine PySide6-GUI für die Installation aus (konsistent mit Framework-GUI).
- Prüft Systemvoraussetzungen (Docker, Git, Internet).
- Kopiert das GESAMTE Repository-Gerüst (für das Auto-Update).
- Lädt Docker-Images vor.
"""

import os
import sys
import shutil
import subprocess
import time
import socket
import threading
import tempfile
from pathlib import Path
from typing import Optional, List, Callable
import requests 

# PySide6 Imports für die grafische Oberfläche
try:
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QGroupBox, QFormLayout, QLabel, QLineEdit, 
        QPushButton, QCheckBox, QTextEdit, QMessageBox, QWidget,
        QProgressDialog, QFileDialog
    )
    from PySide6.QtCore import Qt, QObject, Signal, QThread, QRunnable, Slot
    from PySide6.QtGui import QFont, QAction
    import win32com.client as win32 # Muss jetzt verfügbar sein
except ImportError:
    print("FATAL ERROR: PySide6 is not available. Installation requires PySide6 in the build environment.")
    sys.exit(1)


# --- KONFIGURATION & GLOBALS ---
INSTALL_APP_NAME = "LLM-Builder"
DEFAULT_INSTALL_DIR_SUFFIX = "LLM-Framework"

# Ordner, die NICHT zum User kopiert werden sollen
IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git", ".gitignore", ".gitattributes",
    ".venv", "venv", "env",
    "__pycache__", "*.pyc", "*.pyd",
    "dist", "build", "*.spec",
    "output", "cache", "logs", 
    "tmp", "temp"
)

# ============================================================================
# UTILITY FUNKTIONEN (Kernlogik)
# ============================================================================

def _find_repo_root_at_runtime() -> Optional[Path]:
    """Sucht den Root-Ordner des Repositories."""
    if getattr(sys, 'frozen', False): 
        start_path = Path(sys.executable).parent
    else: 
        start_path = Path(__file__).resolve().parent

    current_path = start_path
    REPO_ROOT_MARKERS = [f"{INSTALL_APP_NAME}.ico", "targets", "orchestrator"]

    for _ in range(10): 
        if all((current_path / marker).exists() for marker in REPO_ROOT_MARKERS):
            return current_path
        
        parent = current_path.parent
        if parent == current_path: 
            break
        current_path = parent
    return None

def _create_shortcut(target_exe_path: Path, working_directory: Path, icon_path: Optional[Path] = None) -> bool:
    """Erstellt einen Desktop-Shortcut unter Windows (Nativ mit pywin32)."""
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    shortcut_path = os.path.join(desktop, f"{INSTALL_APP_NAME}.lnk")
    
    try:
        shell = win32.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = str(target_exe_path.absolute())
        shortcut.WorkingDirectory = str(working_directory.absolute())
        if icon_path and icon_path.exists():
            shortcut.IconLocation = str(icon_path.absolute())
        shortcut.Description = "Launch LLM Cross-Compiler Framework"
        shortcut.Save()
        return True
    except Exception:
        # Kein VBScript Fallback mehr, da pywin32 jetzt vorausgesetzt wird
        return False

def install_application(destination_path: Path, desktop_shortcut: bool, log_callback: Callable, progress_callback: Callable):
    """Führt die Kern-Installationslogik aus."""
    
    repo_root = _find_repo_root_at_runtime()
    if not repo_root:
        raise Exception("CRITICAL: Repository-Root nicht gefunden. Installation abgebrochen.")
        
    log_callback(f"Repository-Root gefunden unter: {repo_root}", "info")

    # 1. Zielordner vorbereiten
    log_callback(f"Bereite Zielordner '{destination_path}' vor...", "info")
    progress_callback(5)
    if destination_path.exists():
        shutil.rmtree(destination_path)
        log_callback("Bestehende Installation gelöscht.", "info")
    destination_path.mkdir(parents=True, exist_ok=True)

    # 2. Kopiere das Repo-Gerüst
    log_callback("Kopiere Framework-Dateien...", "info")
    progress_callback(20)
    shutil.copytree(repo_root, destination_path, ignore=IGNORE_PATTERNS, dirs_exist_ok=True)

    # 3. Launcher kopieren
    launcher_src = repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"
    launcher_dst = destination_path / f"{INSTALL_APP_NAME}.exe"
    if not launcher_src.exists():
         raise Exception(f"KRITISCH: Launcher EXE nicht gefunden unter: {launcher_src}. Bitte zuerst kompilieren!")
    
    log_callback("Kopiere den signierten Launcher...", "info")
    progress_callback(40)
    shutil.copy2(launcher_src, launcher_dst)

    # 4. Basiskonfiguration und leere Ordner
    icon_src = repo_root / f"{INSTALL_APP_NAME}.ico"
    if icon_src.exists(): shutil.copy2(icon_src, destination_path / f"{INSTALL_APP_NAME}.ico")
    for d in ["output", "cache", "logs"]: (destination_path / d).mkdir(exist_ok=True)
    
    log_callback("Basiskonfiguration abgeschlossen.", "success")
    progress_callback(50)

    # 5. Desktop-Shortcut erstellen
    if desktop_shortcut:
        log_callback("Erstelle Desktop-Verknüpfung...", "info")
        if not _create_shortcut(launcher_dst, destination_path, destination_path / f"{INSTALL_APP_NAME}.ico"):
             log_callback("FEHLER: Desktop-Shortcut konnte nicht erstellt werden. Pywin32-Fehler.", "error")

# ============================================================================
# INSTALLATION WORKER (THREADED LOGIC)
# ============================================================================

class InstallationWorker(QObject):
    """Führt alle langwierigen Installationsschritte in einem separaten Thread aus."""
    
    finished = Signal(bool, str) # Signal: Erfolg, Fehlermeldung
    progress_update = Signal(int, str) # Signal: Prozent, Aktionstext

    def __init__(self, target_dir: Path, desktop_shortcut: bool, log_callback: Callable, progress_callback: Callable):
        super().__init__()
        self.target_dir = target_dir
        self.desktop_shortcut = desktop_shortcut
        self.log = log_callback
        self.progress = progress_callback
        self.ping_host = "8.8.8.8"

    def _check_internet_status(self):
        try:
            requests.head("http://www.google.com", timeout=3)
            return True
        except:
            return False

    def _pre_pull_docker(self):
        images = ["debian:bookworm-slim", "quay.io/vektorlab/ctop:latest"]
        
        for i, img in enumerate(images):
            retries = 0
            max_retries = 5
            while retries < max_retries:
                if self._check_internet_status():
                    self.progress(70 + i * (20 // len(images)), f"Lade Docker Image: {img} (Versuch {retries + 1}/{max_retries})...")
                    try:
                        # subprocess.CREATE_NO_WINDOW = 0x08000000
                        subprocess.run(["docker", "pull", img], check=True, creationflags=0x08000000, capture_output=True)
                        self.log(f"Image '{img}' erfolgreich gepullt.", "green")
                        break 
                    except subprocess.CalledProcessError as e:
                        self.log(f"Pull von '{img}' fehlgeschlagen: {e.stderr.strip()}", "orange")
                        retries += 1
                        time.sleep(5)
                else:
                    self.log("Keine Internetverbindung. Warte 10 Sekunden...", "orange")
                    time.sleep(10) 
            
            if retries == max_retries:
                 self.log(f"WARNUNG: Pull von '{img}' nach mehreren Versuchen fehlgeschlagen. Installation wird fortgesetzt.", "orange")

    @Slot()
    def run(self):
        """Haupt-Installationsroutine des Threads."""
        try:
            # 1. Installation der Dateien
            install_application(self.target_dir, self.desktop_shortcut, self.log, self.progress)
            
            # 2. Docker Pre-Pull
            self.progress(70, "Starte Docker Pre-Pull...")
            self._pre_pull_docker()
            
            self.progress(100, "Installation abgeschlossen.")
            self.finished.emit(True, "Installation erfolgreich abgeschlossen.")

        except Exception as e:
            self.finished.emit(False, str(e))


# ============================================================================
# INSTALLER GUI (PYSIDE6)
# ============================================================================

class InstallerWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Install {INSTALL_APP_NAME}")
        self.setFixedSize(600, 550) # Fixiert die Größe, um Layout-Probleme zu vermeiden
        
        self._init_ui()
        self.after(100, self._initial_checks_start) # Startet die Checks im nächsten Zyklus

    def _init_ui(self):
        # ... (Styling und Layout wie in der letzten korrigierten Version)
        
        main_layout = QVBoxLayout(self)

        # Header/Title
        title_label = QLabel(f"Welcome to {INSTALL_APP_NAME} Setup", objectName="title")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        main_layout.addWidget(title_label)

        # System Requirements Check Group
        req_group = QGroupBox("System Requirements Check")
        req_layout = QFormLayout(req_group)
        self.docker_status_label = QLabel("Checking...", objectName="status_checking")
        self.git_status_label = QLabel("Checking...", objectName="status_checking")
        self.internet_status_label = QLabel("Checking...", objectName="status_checking")
        req_layout.addRow("Docker Desktop (WSL2):", self.docker_status_label)
        req_layout.addRow("Git for Windows:", self.git_status_label)
        req_layout.addRow("Internet Connectivity:", self.internet_status_label)
        main_layout.addWidget(req_group)

        # Installation Location Group
        loc_group = QGroupBox("Installation Location")
        loc_layout_h = QHBoxLayout()
        default_install_path = Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX
        self.install_path_edit = QLineEdit(str(default_install_path))
        loc_layout_h.addWidget(self.install_path_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_for_folder)
        loc_layout_h.addWidget(browse_btn)
        
        loc_group_layout = QVBoxLayout(loc_group)
        loc_group_layout.addWidget(QLabel("Where do you want to install the Framework?"))
        loc_group_layout.addLayout(loc_layout_h)
        
        self.desktop_shortcut_checkbox = QCheckBox("Create Desktop Shortcut")
        self.desktop_shortcut_checkbox.setChecked(True)
        loc_group_layout.addWidget(self.desktop_shortcut_checkbox)
        
        main_layout.addWidget(loc_group)

        # Status / Log Area
        self.log_text = QTextEdit("Ready to install", readOnly=True)
        self.log_text.setMinimumHeight(80)
        self.log_text.setFont(QFont("Courier New", 9))
        self.log_text.setStyleSheet("background-color: #333; color: #0f0;")
        main_layout.addWidget(self.log_text)

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # Buttons
        button_layout = QHBoxLayout()
        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self._start_installation)
        self.install_button.setEnabled(False)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.install_button)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        self._apply_styles()

    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget { font-family: Arial, sans-serif; background-color: #e0e0e0; }
            QLabel { color: #333; }
            QGroupBox { border: 1px solid #ccc; margin-top: 1ex; padding-top: 1ex; }
            QPushButton { background-color: #007bff; color: white; border: none; padding: 6px; }
            QPushButton:hover { background-color: #0056b3; }
            #status_ok { color: green; font-weight: bold; }
            #status_nok { color: red; font-weight: bold; }
            #status_checking { color: orange; font-weight: bold; }
        """)

    def _browse_for_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Installation Directory")
        if folder:
            target_path = Path(folder)
            if not target_path.name.lower().endswith(DEFAULT_INSTALL_DIR_SUFFIX.lower()):
                target_path = target_path / DEFAULT_INSTALL_DIR_SUFFIX
            self.install_path_edit.setText(str(target_path))

    def update_log(self, message: str, color: str = None):
        """Aktualisiert das Log-Fenster (für den Thread-Call)."""
        def do_update():
            self.log_text.insert(QTextEdit.EndOfDocument, f"[{time.strftime('%H:%M:%S')}] {message}\n")
            self.log_text.ensureCursorVisible()

        self.log_text.parent().thread().after(0, do_update) # Call in main thread

    def _set_status_label(self, label: QLabel, text: str, color_id: str):
        label.setText(text)
        label.setObjectName(color_id)
        self.style().polish(label)

    def _check_docker_status(self) -> bool:
        try:
            # Stummer Aufruf
            result = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            return result.returncode == 0
        except: return False

    def _check_git_status(self) -> bool:
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            return result.returncode == 0
        except: return False

    def _check_internet_status(self) -> bool:
        try:
            requests.head("http://www.google.com", timeout=3)
            return True
        except: return False

    def _initial_checks_start(self):
        """Startet den Thread für die Systemprüfung."""
        threading.Thread(target=self._run_initial_checks_threaded, daemon=True).start()

    def _run_initial_checks_threaded(self):
        """Führt alle System-Checks im Thread aus."""
        try:
            self.update_log("Führe Systemvoraussetzungen-Checks durch...", "orange")

            # --- Docker Check ---
            docker_ok = self._check_docker_status()
            self.after(0, lambda: self._set_status_label(self.docker_status_label, "OK" if docker_ok else "NOT FOUND", "#status_ok" if docker_ok else "#status_nok"))
            
            # --- Git Check ---
            git_ok = self._check_git_status()
            self.after(0, lambda: self._set_status_label(self.git_status_label, "OK" if git_ok else "NOT FOUND", "#status_ok" if git_ok else "#status_nok"))
            
            # --- Internet Check ---
            internet_ok = self._check_internet_status()
            self.after(0, lambda: self._set_status_label(self.internet_status_label, "OK" if internet_ok else "FAILED", "#status_ok" if internet_ok else "#status_nok"))

            if not docker_ok:
                self.update_log("KRITISCH: Docker Desktop wird benötigt. Installation ist gesperrt.", "red")
            
            if docker_ok: 
                self.after(0, lambda: self.install_button.setEnabled(True))
                self.update_log("Alle Kern-Voraussetzungen erfüllt. Bereit zur Installation.", "green")
            else:
                self.after(0, lambda: self.install_button.setEnabled(False))

        except Exception as e:
            self.update_log(f"Error during system check: {e}", "red")

    def _start_installation(self):
        target_dir = Path(self.install_path_edit.text()).resolve()
        desktop_shortcut = self.desktop_shortcut_checkbox.isChecked()
        
        if not target_dir.parent.exists():
            messagebox.showerror("Invalid Path", f"The parent directory for {target_dir} does not exist.")
            return

        self.install_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.update_log("Installation gestartet...", "blue")

        # Worker und Thread erstellen
        self.thread = QThread()
        self.worker = InstallationWorker(target_dir, desktop_shortcut, self.update_log, self.update_progress)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_installation_finished)
        self.thread.start()
        self.after(500, self._check_installation_progress)

    def update_progress(self, percent: int, message: str):
        """Wird vom Worker-Thread aufgerufen, muss in den Haupt-Thread zurück."""
        self.after(0, lambda: self.progress_bar.setValue(percent))
        self.update_log(message)

    def _check_installation_progress(self):
        if self.thread and self.thread.isRunning():
            self.after(500, self._check_installation_progress)
        else:
            self.update_log("Installationsthread beendet.")

    def _on_installation_finished(self, success: bool, message: str):
        self.thread.quit()
        self.thread.wait()
        
        if success:
            self.progress_bar.setValue(100)
            self.update_log("✅ Installation erfolgreich abgeschlossen.", "green")
            messagebox.showinfo("Installation Complete", message)
            self.destroy()
        else:
            self.progress_bar.setValue(0)
            self.update_log(f"❌ Installation fehlgeschlagen:\n{message}", "red")
            messagebox.showerror("Installation Failed", f"Ein Fehler ist aufgetreten:\n{message}")
            self.install_button.setEnabled(True)
            self.cancel_button.setEnabled(True)


if __name__ == '__main__':
    # PySide6-Code
    app = QApplication(sys.argv)
    installer = InstallerWindow()
    sys.exit(installer.exec())
