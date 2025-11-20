#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Windows Installer (Full Repo Install)
DIREKTIVE: Goldstandard, vollständig, GUI-basiert, Netzwerk-Resilient.

Zweck:
- Führt eine PySide6-GUI für die Installation aus.
- Prüft Systemvoraussetzungen (Docker, Git, Internet)
- Kopiert das GESAMTE Repository-Gerüst (für das Auto-Update)
- Lädt Docker-Images vor
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
from typing import Optional, List, Dict, Any 

# PySide6 Imports für die grafische Oberfläche
try:
    from PySide6.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QGroupBox, QFormLayout, QLabel, QLineEdit, 
        QPushButton, QCheckBox, QTextEdit, QMessageBox, QWidget,
        QProgressDialog
    )
    from PySide6.QtCore import Qt, QObject, Signal, QThread
    from PySide6.QtGui import QFont
except ImportError:
    print("FATAL ERROR: PySide6 is not installed. This graphical installer requires PySide6.")
    sys.exit(1)


# --- KONFIGURATION & GLOBALS ---
INSTALL_APP_NAME = "LLM-Builder"
DEFAULT_INSTALL_DIR_SUFFIX = "LLM-Framework"

# Die Basisverzeichnisse werden beim Start gesucht (siehe unten)
REPO_ROOT = Path(os.getcwd())
LAUNCHER_EXE_SOURCE = REPO_ROOT / "dist" / f"{INSTALL_APP_NAME}.exe"
PING_HOST = "8.8.8.8"
INSTALL_SUCCESS = False

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
# INSTALLATION THREAD (ASYNCHRONE LOGIK)
# ============================================================================

class InstallationWorker(QObject):
    """Führt alle langwierigen Installationsschritte in einem separaten Thread aus."""
    
    finished = Signal(bool, str) # Signal: Erfolg, Fehlermeldung
    progress_update = Signal(int, str) # Signal: Prozent, Aktionstext

    def __init__(self, target_dir: Path, desktop_shortcut: bool):
        super().__init__()
        self.target_dir = target_dir
        self.desktop_shortcut = desktop_shortcut
        self.repo_root = self._find_repo_root_safely()

    def _find_repo_root_safely(self):
        """Findet den Repo-Root basierend auf Markern."""
        current_path = Path(os.getcwd())
        markers = ["targets", "orchestrator", "scripts"]
        
        for _ in range(10): 
            if all((current_path / marker).is_dir() for marker in markers):
                return current_path
            parent = current_path.parent
            if parent == current_path:
                break
            current_path = parent
        return None

    def run(self):
        """Haupt-Installationsroutine."""
        try:
            if not self.repo_root:
                raise Exception("CRITICAL: Repository-Root nicht gefunden. Installation abgebrochen.")
            
            self._install_files()
            self._create_shortcuts()
            self._pre_pull_docker()
            
            self.finished.emit(True, "Installation erfolgreich abgeschlossen.")

        except Exception as e:
            self.finished.emit(False, str(e))

    def _install_files(self):
        self.progress_update.emit(10, "Lösche bestehende Installation...")
        
        # 1. Zielordner vorbereiten
        if self.target_dir.exists():
            shutil.rmtree(self.target_dir)
        self.target_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Repo-Struktur kopieren (Der "Rich Environment")
        self.progress_update.emit(30, "Kopiere Framework-Struktur (Targets, Scripts, Configs)...")
        shutil.copytree(self.repo_root, self.target_dir, ignore=IGNORE_PATTERNS, dirs_exist_ok=True)

        # 3. Launcher kopieren (Muss signiert sein!)
        launcher_src = self.repo_root / "dist" / f"{INSTALL_APP_NAME}.exe"
        launcher_dst = self.target_dir / f"{INSTALL_APP_NAME}.exe"
        if not launcher_src.exists():
             raise Exception(f"CRITICAL: Launcher EXE nicht gefunden unter {launcher_src}. Bitte zuerst kompilieren!")
        
        self.progress_update.emit(50, "Kopiere signierten Launcher...")
        shutil.copy2(launcher_src, launcher_dst)

        # 4. Icon und leere Ordner erstellen
        icon_src = self.repo_root / f"{INSTALL_APP_NAME}.ico"
        if icon_src.exists():
            shutil.copy2(icon_src, self.target_dir / f"{INSTALL_APP_NAME}.ico")
        
        for d in ["output", "cache", "logs"]:
            (self.target_dir / d).mkdir(exist_ok=True)
        
        self.progress_update.emit(60, "Dateien erfolgreich kopiert.")

    def _create_shortcuts(self):
        if not self.desktop_shortcut:
            return
        
        self.progress_update.emit(70, "Erstelle Desktop-Shortcut...")
        
        # Windows-spezifische Verknüpfungserstellung (via VBScript Fallback)
        desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
        shortcut_path = os.path.join(desktop, f"{INSTALL_APP_NAME}.lnk")
        target_exe_path = str((self.target_dir / f"{INSTALL_APP_NAME}.exe").absolute()).replace("\\", "\\\\")
        working_directory = str(self.target_dir.absolute()).replace("\\", "\\\\")
        icon_location = str(self.target_dir / f"{INSTALL_APP_NAME}.ico").replace("\\", "\\\\")

        vbs_script = f"""
        Set oWS = WScript.CreateObject("WScript.Shell")
        sLinkFile = "{shortcut_path}"
        Set oLink = oWS.CreateShortcut(sLinkFile)
        oLink.TargetPath = "{target_exe_path}"
        oLink.WorkingDirectory = "{working_directory}"
        oLink.IconLocation = "{icon_location}"
        oLink.Description = "Launch LLM Cross-Compiler Framework"
        oLink.Save
        """
        
        vbs_file = Path(tempfile.gettempdir()) / "create_shortcut.vbs"
        with open(vbs_file, "w") as f:
            f.write(vbs_script)
        subprocess.run(["cscript", "//Nologo", str(vbs_file)], check=True, capture_output=True)
        vbs_file.unlink()

    def _check_connectivity(self):
        """Einfacher Ping-Check"""
        try:
            socket.create_connection((PING_HOST, 53), timeout=3)
            return True
        except OSError:
            return False

    def _pre_pull_docker(self):
        """Robuster Pre-Pull von Basis-Images mit Netzwerk-Check"""
        images = ["debian:bookworm-slim", "quay.io/vektorlab/ctop:latest"]
        
        for i, img in enumerate(images):
            retries = 0
            while retries < 5:
                if self._check_connectivity():
                    self.progress_update.emit(80 + i * 5, f"Lade Docker Image: {img}...")
                    try:
                        subprocess.run(["docker", "pull", img], check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
                        break 
                    except subprocess.CalledProcessError:
                        retries += 1
                        time.sleep(2)
                else:
                    self.progress_update.emit(75, "Netzwerk unterbrochen. Warte auf Verbindung...")
                    time.sleep(5) 
            
            if retries == 5:
                 self.progress_update.emit(90, f"Pull von {img} fehlgeschlagen. Installation fortgesetzt.")

        self.progress_update.emit(100, "Installation abgeschlossen.")


# ============================================================================
# INSTALLER GUI (PYQT/PYSIDE6)
# ============================================================================

class InstallerWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Install {INSTALL_APP_NAME}")
        self.setFixedSize(600, 500)
        
        # Pfad-Setzung (Standard)
        default_install_path = Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX
        
        self._init_ui(default_install_path)
        self.check_requirements()

    def _init_ui(self, default_path: Path):
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
        self.install_path_edit = QLineEdit(str(default_path))
        loc_layout_h.addWidget(self.install_path_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_for_folder)
        loc_layout_h.addWidget(browse_btn)
        
        loc_group_layout = QVBoxLayout(loc_group)
        loc_group_layout.addWidget(QLabel("Where do you want to install the Framework?"))
        loc_group_layout.addLayout(loc_layout_h)
        
        self.desktop_shortcut_checkbox = QCheckBox("Create Desktop Shortcut")
        self.desktop_shortcut_checkbox.setChecked(True)
        loc_group_layout.addWidget(self.desktop_shortcut_checkbox)
        
        main_layout.addWidget(loc_group)

        # Status / Log Area
        self.status_text_edit = QTextEdit("Ready to install", readOnly=True)
        self.status_text_edit.setMinimumHeight(80)
        main_layout.addWidget(self.status_text_edit)

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # Buttons
        button_layout = QHBoxLayout()
        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self.start_installation)
        self.install_button.setEnabled(False)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.install_button)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        self.apply_styles()

    def apply_styles(self):
        # Apply standard styles not covered by stylesheets (Qt needs this)
        self.setStyleSheet("""
            #status_ok { color: green; }
            #status_nok { color: red; }
            #status_checking { color: orange; }
        """)

    def browse_for_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Installation Directory")
        if folder:
            # Füge den Standard-Suffix hinzu, wenn es nicht das Root-Verzeichnis ist
            if not folder.endswith(DEFAULT_INSTALL_DIR_SUFFIX):
                 folder = os.path.join(folder, DEFAULT_INSTALL_DIR_SUFFIX)
            self.install_path_edit.setText(folder)

    def update_status_label(self, label: QLabel, text: str, color_id: str):
        label.setText(text)
        label.setObjectName(color_id)
        self.style().polish(label)

    def check_requirements(self):
        # Checks werden in einem Thread ausgeführt, um die UI nicht zu blockieren
        def background_check():
            try:
                docker_ok = self._check_docker()
                git_ok = self._check_git()
                internet_ok = self._check_internet_connection()
                
                self.update_status_label(self.docker_status_label, "OK" if docker_ok else "Not Found", "status_ok" if docker_ok else "status_nok")
                self.update_status_label(self.git_status_label, "OK" if git_ok else "Not Found", "status_ok" if git_ok else "status_nok")
                self.update_status_label(self.internet_status_label, "OK" if internet_ok else "Failed", "status_ok" if internet_ok else "status_nok")

                if docker_ok:
                    self.install_button.setEnabled(True)
                    self.status_text_edit.setText("All requirements met. Ready to install.")
                else:
                    self.install_button.setEnabled(False)
                    self.status_text_edit.setText("CRITICAL: Docker Desktop is required and not running.")

            except Exception as e:
                self.status_text_edit.setText(f"Error during system check: {e}")

        threading.Thread(target=background_check, daemon=True).start()

    def _check_docker(self):
        try:
            result = subprocess.run(["docker", "info"], timeout=5, check=False, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            return result.returncode == 0
        except: return False

    def _check_git(self):
        try:
            result = subprocess.run(["git", "--version"], timeout=5, check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            return result.returncode == 0
        except: return False

    def _check_internet_connection(self):
        try:
            requests.get("http://www.google.com", timeout=5)
            return True
        except: return False

    def start_installation(self):
        target_dir = Path(self.install_path_edit.text()).resolve()
        desktop_shortcut = self.desktop_shortcut_checkbox.isChecked()
        
        self.install_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_text_edit.setText("Installation gestartet...")
        QApplication.processEvents()
        
        # Worker und Thread erstellen
        self.thread = QThread()
        self.worker = InstallationWorker(target_dir, desktop_shortcut)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_installation_finished)
        self.worker.progress_update.connect(self.on_progress_update)
        self.thread.start()

    def on_progress_update(self, percent: int, text: str):
        self.progress_bar.setValue(percent)
        self.status_text_edit.append(f"[{percent}%] {text}")

    def on_installation_finished(self, success: bool, message: str):
        self.thread.quit()
        self.thread.wait()
        
        if success:
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "Installation Complete", message)
            self.accept()
        else:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Installation Failed", f"Ein Fehler ist aufgetreten:\n{message}")
            self.install_button.setEnabled(True)
            self.cancel_button.setEnabled(True)


if __name__ == '__main__':
    # Initialisiere Win32-COM für Desktop-Shortcuts
    try:
        import win32com.client # Erfordert 'pip install pywin32'
    except ImportError:
        print("WARNUNG: 'pywin32' ist nicht installiert. Desktop-Shortcuts werden über VBScript erstellt.")

    app = QApplication(sys.argv)
    installer = InstallerWindow()
    sys.exit(installer.exec())
