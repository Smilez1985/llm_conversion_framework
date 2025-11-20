import os
import sys
import subprocess
import shutil
from pathlib import Path
import json

# --- CONFIGURATION (Anpassen falls nötig) ---
INSTALL_APP_NAME = "LLM-Framework"
INSTALL_COMPANY_NAME = "MyCompany" # Wichtig für Startmenü/Registry
REPO_ROOT_MARKERS = [".git", "targets", "orchestrator"] # Marker für den Repo-Root
DEFAULT_INSTALL_DIR_SUFFIX = "LLM-Framework" # Unterordner in AppData/Local/Programs
# --- END CONFIGURATION ---

def find_repo_root(current_path: Path) -> Optional[Path]:
    """
    Sucht den Root-Ordner des Repositories, indem es nach den Markern sucht.
    Dies ist der Ordner, der alle Quellcodes, Skripte und den 'dist'-Ordner enthält.
    """
    for _ in range(10): # Max. 10 Ebenen nach oben suchen
        if all((current_path / marker).exists() for marker in REPO_ROOT_MARKERS):
            return current_path
        
        parent = current_path.parent
        if parent == current_path: # Dateisystem-Root erreicht
            break
        current_path = parent
    return None

def install_application(destination_path: Path, desktop_shortcut: bool = True):
    print(f"Starte Installation von {INSTALL_APP_NAME} nach {destination_path}...")

    # Schritt 1: Finde den Root-Ordner des Repos
    # Beim PyInstaller-Build wird das Skript setup_windows.py aus einem Temp-Ordner ausgeführt.
    # Wir müssen den echten Repo-Root finden, wo dist/ und alle anderen Ordner liegen.
    
    # Pfad, wo PyInstaller unser Skript reingepackt hat
    if getattr(sys, 'frozen', False):
        # Wenn aus EXE ausgeführt, ist der Startpfad der Ordner der EXE
        installer_start_path = Path(sys.executable).parent
    else:
        # Wenn als Skript ausgeführt, ist es das Parent-Verzeichnis
        installer_start_path = Path(__file__).resolve().parent

    repo_root = find_repo_root(installer_start_path)

    if not repo_root:
        # DIESER FEHLER würde auftreten, wenn das Installer-Skript nicht aus dem Repo-Kontext gebaut wurde
        # oder das Repo nicht im Build-Prozess mitgeliefert wurde.
        print(f"FEHLER: Repository-Root nicht gefunden ab '{installer_start_path}'. Kann Dateien nicht kopieren.")
        sys.exit(1)

    print(f"Repository-Root gefunden unter: {repo_root}")

    # Schritt 2: Sicherstellen, dass der Zielpfad sauber ist
    if destination_path.exists():
        print(f"Lösche bestehenden Ordner: {destination_path}")
        try:
            shutil.rmtree(destination_path)
        except Exception as e:
            print(f"FEHLER: Konnte bestehenden Ordner nicht löschen: {e}")
            sys.exit(1)
    
    destination_path.mkdir(parents=True, exist_ok=True)

    # Schritt 3: Kopiere alle notwendigen Ordner und Dateien
    # Jetzt wissen wir, wo alles ist (im repo_root).
    
    # Liste der Ordner, die kopiert werden sollen (relativ zum repo_root)
    # WICHTIG: 'dist' ist jetzt der Ort des LAUNCHERS, nicht des Installers!
    folders_to_copy = ["orchestrator", "targets", "docker", "configs", "scripts", "models"]
    
    # Kopiere den "Thin Client" Launcher selbst
    launcher_src = repo_root / "dist" / "LLM-Builder.exe" # Hier liegt der Launcher!
    launcher_dst = destination_path / "LLM-Builder.exe"

    if not launcher_src.exists():
        print(f"FEHLER: Launcher EXE nicht gefunden unter: {launcher_src}")
        print("Bitte zuerst 'python scripts/build_launcher.py' ausführen!")
        sys.exit(1)
        
    print(f"Kopiere Launcher: {launcher_src} -> {launcher_dst}")
    shutil.copy2(launcher_src, launcher_dst)

    # Kopiere die restlichen Ordner
    for folder_name in folders_to_copy:
        src_path = repo_root / folder_name
        dst_path = destination_path / folder_name
        if src_path.exists():
            print(f"Kopiere Ordner: {src_path} -> {dst_path}")
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        else:
            print(f"WARNUNG: Ordner nicht gefunden: {src_path}. Überspringe.")

    # Kopiere LLM-Builder.ico in den Installations-Root (für Verknüpfung)
    icon_src = repo_root / "LLM-Builder.ico"
    icon_dst = destination_path / "LLM-Builder.ico"
    if icon_src.exists():
        shutil.copy2(icon_src, icon_dst)
    else:
        print(f"WARNUNG: Icon-Datei {icon_src} nicht gefunden. Desktop-Shortcut könnte Standard-Icon haben.")


    # Schritt 4: Desktop-Shortcut erstellen
    if desktop_shortcut:
        print("Erstelle Desktop-Shortcut...")
        try:
            # Pfad zur Python-WSH-Datei für Verknüpfungen (auf den meisten Windows-Systemen vorhanden)
            import win32com.client # Erfordert 'pip install pywin32'
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut_path = os.path.join(os.path.expanduser("~"), "Desktop", f"{INSTALL_APP_NAME}.lnk")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = str(launcher_dst.absolute())
            shortcut.WorkingDirectory = str(destination_path.absolute()) # WICHTIG: Damit rel. Pfade funktionieren
            shortcut.IconLocation = str(icon_dst.absolute()) if icon_src.exists() else ""
            shortcut.Save()
            print("Desktop-Shortcut erstellt.")
        except ImportError:
            print("WARNUNG: 'pywin32' nicht installiert. Konnte Desktop-Shortcut nicht erstellen.")
        except Exception as e:
            print(f"FEHLER: Konnte Desktop-Shortcut nicht erstellen: {e}")
            
    print(f"Installation von {INSTALL_APP_NAME} abgeschlossen.")


# ============================================================================
# INSTALLER GUI (basiert auf dem alten Ansatz)
# ============================================================================

class InstallerWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Install {INSTALL_APP_NAME}")
        self.setFixedSize(600, 500) # Feste Größe für einfachere Layouts
        self.setStyleSheet("""
            QWidget { font-family: Arial, sans-serif; }
            QLabel#title { font-size: 24px; font-weight: bold; margin-bottom: 20px; }
            QGroupBox { border: 1px solid #ccc; border-radius: 5px; margin-top: 1em; padding-top: 1em; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QLineEdit, QPushButton, QComboBox, QCheckBox { padding: 5px; border-radius: 3px; }
            QPushButton { background-color: #0078d7; color: white; border: none; }
            QPushButton:hover { background-color: #005a9e; }
            QTextEdit { background-color: #f0f0f0; border: 1px solid #ccc; }
            .status_ok { color: green; }
            .status_nok { color: red; }
            .status_checking { color: orange; }
        """)

        main_layout = QVBoxLayout(self)

        title_label = QLabel(f"Welcome to {INSTALL_APP_NAME} Setup", objectName="title")
        title_label.setAlignment(Qt.AlignCenter)
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
        loc_layout = QHBoxLayout(loc_group)
        
        # Standardpfad: AppData/Local/Programs
        # C:\Users\[USERNAME]\AppData\Local\Programs\[INSTALL_APP_NAME]
        default_install_path = Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / "Programs" / DEFAULT_INSTALL_DIR_SUFFIX
        self.install_path_edit = QLineEdit(str(default_install_path))
        loc_layout.addWidget(self.install_path_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_for_folder)
        loc_layout.addWidget(browse_btn)
        
        loc_group_layout = QVBoxLayout(loc_group)
        loc_group_layout.addWidget(QLabel("Where do you want to install the Framework?"))
        loc_group_layout.addLayout(loc_layout)
        
        self.desktop_shortcut_checkbox = QCheckBox("Create Desktop Shortcut")
        self.desktop_shortcut_checkbox.setChecked(True)
        loc_group_layout.addWidget(self.desktop_shortcut_checkbox)
        
        main_layout.addWidget(loc_group)

        # Status / Ready to Install
        self.status_text_edit = QTextEdit("Ready to install", readOnly=True)
        self.status_text_edit.setMinimumHeight(80)
        main_layout.addWidget(self.status_text_edit)

        # Buttons
        button_layout = QHBoxLayout()
        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self.start_installation)
        self.install_button.setEnabled(False) # Deaktiviert, bis Checks durch sind
        button_layout.addWidget(self.install_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        
        self.check_requirements() # Startet die Checks beim Initialisieren

    def browse_for_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Installation Directory")
        if folder:
            self.install_path_edit.setText(folder)

    def check_requirements(self):
        self.status_text_edit.setText("Performing system checks...")
        QApplication.processEvents() # UI aktualisieren

        docker_ok = self._check_docker()
        git_ok = self._check_git()
        internet_ok = self._check_internet()

        self.docker_status_label.setText("OK" if docker_ok else "Not Found")
        self.docker_status_label.setObjectName("status_ok" if docker_ok else "status_nok")
        self.git_status_label.setText("OK" if git_ok else "Not Found")
        self.git_status_label.setObjectName("status_ok" if git_ok else "status_nok")
        self.internet_status_label.setText("OK" if internet_ok else "Failed")
        self.internet_status_label.setObjectName("status_ok" if internet_ok else "status_nok")
        
        if docker_ok and git_ok and internet_ok:
            self.status_text_edit.setText("All requirements met. Ready to install.")
            self.install_button.setEnabled(True)
        else:
            self.status_text_edit.setText("Some requirements are not met. Installation cannot proceed.")
            self.install_button.setEnabled(False)
        self.style().polish(self.docker_status_label) # Style neu anwenden
        self.style().polish(self.git_status_label)
        self.style().polish(self.internet_status_label)


    def _check_docker(self):
        try:
            # Check if docker daemon is running
            result = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            if result.returncode == 0 and "Server Version" in result.stdout:
                return True
            else:
                self.status_text_edit.append(f"Docker check failed: {result.stderr.strip()}")
                return False
        except FileNotFoundError:
            self.status_text_edit.append("Docker command not found. Is Docker Desktop installed and in PATH?")
            return False
        except Exception as e:
            self.status_text_edit.append(f"Error checking Docker: {e}")
            return False

    def _check_git(self):
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            return result.returncode == 0
        except FileNotFoundError:
            self.status_text_edit.append("Git command not found. Is Git for Windows installed and in PATH?")
            return False
        except Exception as e:
            self.status_text_edit.append(f"Error checking Git: {e}")
            return False

    def _check_internet(self):
        try:
            requests.get("http://www.google.com", timeout=5)
            return True
        except requests.ConnectionError:
            self.status_text_edit.append("Internet connection failed.")
            return False
        except Exception as e:
            self.status_text_edit.append(f"Error checking internet: {e}")
            return False

    def start_installation(self):
        destination_path = Path(self.install_path_edit.text()).resolve()
        desktop_shortcut = self.desktop_shortcut_checkbox.isChecked()

        try:
            self.install_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.status_text_edit.setText("Installation started...")
            QApplication.processEvents()

            install_application(destination_path, desktop_shortcut)
            
            self.status_text_edit.append(f"\nInstallation erfolgreich abgeschlossen nach:\n{destination_path}")
            QMessageBox.information(self, "Installation Complete", 
                                    f"{INSTALL_APP_NAME} wurde erfolgreich installiert.")
            self.accept() # Schließt den Dialog erfolgreich

        except Exception as e:
            self.status_text_edit.setText(f"\nFEHLER während der Installation: {e}")
            QMessageBox.critical(self, "Installation Failed", 
                                 f"Ein Fehler ist während der Installation aufgetreten:\n{e}")
            self.install_button.setEnabled(True)
            self.cancel_button.setEnabled(True)


if __name__ == '__main__':
    # Initialisiere Win32-COM für Desktop-Shortcuts (falls pywin32 installiert ist)
    try:
        import win32com.client # Dies ist nur ein Test, ob es importiert werden kann
    except ImportError:
        print("WARNUNG: 'pywin32' ist nicht installiert. Desktop-Shortcuts werden nicht erstellt.")

    app = QApplication(sys.argv)
    installer = InstallerWindow()
    sys.exit(installer.exec())
