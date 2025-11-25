#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Window GUI
DIREKTIVE: Goldstandard, MVC-Pattern, Separation of Concerns.

Beinhaltet die Haupt-GUI-Logik und Worker-Threads. 
Dialoge und Wizards sind modular ausgelagert.
"""

import sys
import os
import time
import socket
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTextEdit, QProgressBar,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, 
    QMessageBox, QTableWidget, QTableWidgetItem,
    QDialog, QInputDialog, QFileDialog 
)
from PySide6.QtCore import Qt, QThread, pyqtSignal, QTimer, QProcess
from PySide6.QtGui import QAction

# Core & Utils Imports
from orchestrator.Core.docker_manager import DockerManager
from orchestrator.Core.framework import FrameworkConfig, FrameworkManager
from orchestrator.utils.updater import UpdateManager
from orchestrator.utils.logging import get_logger

# GUI Module Imports
from orchestrator.gui.community_hub import CommunityHubWindow
from orchestrator.gui.huggingface_window import HuggingFaceWindow
from orchestrator.gui.dialogs import AddSourceDialog
from orchestrator.gui.wizards import ModuleCreationWizard


# ============================================================================
# BACKGROUND WORKER (UPDATER)
# ============================================================================

class UpdateWorker(QThread):
    """
    Worker-Thread für Update-Prüfung mit Ping-Loop (Non-Blocking).
    Prüft erst auf Internetverbindung, dann auf Git-Updates.
    """
    update_available = pyqtSignal(bool)
    
    def __init__(self, app_root):
        super().__init__()
        self.app_root = app_root
        self._is_running = True

    def run(self):
        # 1. Ping Loop: Warte auf Internet (max 10 Sekunden Versuch)
        timeout = 10
        start_time = time.time()
        connected = False
        
        while time.time() - start_time < timeout and self._is_running:
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=2)
                connected = True
                break
            except OSError:
                time.sleep(1)
        
        if not connected:
            return

        # 2. Git Check
        try:
            updater = UpdateManager(self.app_root)
            if updater.check_for_updates():
                self.update_available.emit(True)
        except Exception:
            pass 

    def stop(self):
        self._is_running = False


# ============================================================================
# MAIN WINDOW CLASS
# ============================================================================

class MainOrchestrator(QMainWindow):
    """
    Main LLM Cross-Compiler Framework GUI.
    Separated from entry point logic.
    """
    
    def __init__(self, app_root: Path):
        """
        Args:
            app_root (Path): The root directory of the application/repository.
        """
        super().__init__()
        self.app_root = app_root
        self.logger = get_logger(__name__)
        
        # Config path is relative to app_root
        config_path = self.app_root / "configs" / "framework_config.json"
        
        try:
            # Pfade im FrameworkManager relativ zum APP_ROOT setzen
            config = FrameworkConfig()
            config.targets_dir = str(self.app_root / config.targets_dir)
            config.models_dir = str(self.app_root / config.models_dir)
            config.output_dir = str(self.app_root / config.output_dir)
            config.configs_dir = str(self.app_root / config.configs_dir)
            config.cache_dir = str(self.app_root / config.cache_dir)
            config.logs_dir = str(self.app_root / config.logs_dir)
            
            self.framework_manager = FrameworkManager(config)
            self.framework_manager.initialize()
            
            self.docker_manager = DockerManager()
            self.docker_manager.initialize(self.framework_manager)
            
            self.docker_manager.build_output.connect(self.on_build_output)
            self.docker_manager.build_progress.connect(self.on_build_progress)
            self.docker_manager.build_completed.connect(self.on_build_completed)
            
        except Exception as e:
            print(f"CRITICAL INIT ERROR: {e}")
            QMessageBox.critical(None, "Initialization Error", f"Failed to init framework: {e}\nRoot: {self.app_root}")
            sys.exit(1)
            
        self.init_ui()
        
        # Start Update Check
        self.update_worker = UpdateWorker(self.app_root)
        self.update_worker.update_available.connect(self.on_update_available)
        QTimer.singleShot(2000, self.update_worker.start)

    def on_update_available(self, available):
        if available:
            reply = QMessageBox.question(
                self, "Update Verfügbar", 
                "Neue Version verfügbar. Jetzt aktualisieren?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.log("Starte Update-Prozess...")
                updater = UpdateManager(self.app_root)
                updater.perform_update_and_restart()

    def init_ui(self):
        self.setWindowTitle("LLM Cross-Compiler Framework")
        self.setMinimumSize(1200, 850)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; color: #ffffff; }
            QGroupBox { border: 1px solid #555; margin-top: 10px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit, QComboBox, QTextEdit, QTableWidget { background-color: #353535; border: 1px solid #555; color: #fff; }
            QPushButton { background-color: #404040; border: 1px solid #555; padding: 5px; }
            QPushButton:hover { background-color: #505050; }
            QProgressBar { border: 1px solid #555; text-align: center; }
            QProgressBar::chunk { background-color: #007acc; }
        """)
        
        self.create_menu_bar()
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        self.build_tab = QWidget()
        self.setup_build_tab()
        self.tabs.addTab(self.build_tab, "Build & Monitor")
        
        self.sources_tab = QWidget()
        self.setup_sources_tab()
        self.tabs.addTab(self.sources_tab, "Sources & Repositories")
        
        self.load_sources_to_table()

    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # --- File Menu ---
        file_menu = menubar.addMenu("&File")
        
        import_action = QAction("Import Hardware Profile...", self)
        import_action.setStatusTip("Import target_hardware_config.txt from target device")
        import_action.triggered.connect(self.import_hardware_profile)
        file_menu.addAction(import_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Tools Menu ---
        tools_menu = menubar.addMenu("&Tools")
        
        wizard_action = QAction("Create New Module...", self)
        wizard_action.triggered.connect(self.open_module_wizard)
        tools_menu.addAction(wizard_action)
        
        audit_action = QAction("🛡️ Audit Docker Image...", self)
        audit_action.triggered.connect(self.run_image_audit)
        tools_menu.addAction(audit_action)

        # --- Community Menu ---
        community_menu = menubar.addMenu("&Community")
        hub_action = QAction("🌍 Open Community Hub", self)
        hub_action.triggered.connect(self.open_community_hub)
        community_menu.addAction(hub_action)
        
        update_action = QAction("🔄 Check for Updates", self)
        update_action.triggered.connect(self.check_for_updates_automatic)
        community_menu.addAction(update_action)

    def import_hardware_profile(self):
        """Öffnet einen Dialog zum Importieren des Hardware-Profils."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Hardware Profil auswählen (target_hardware_config.txt)", 
            "", 
            "Config Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                # Zielverzeichnis ist der 'cache' Ordner
                cache_dir = self.app_root / "cache"
                if not cache_dir.exists():
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    
                target_path = cache_dir / "target_hardware_config.txt"
                
                shutil.copy2(file_path, target_path)
                
                self.log(f"✅ Hardware Profil importiert: {target_path}")
                QMessageBox.information(self, "Erfolg", f"Profil erfolgreich importiert.\n\nEs wird beim nächsten Build automatisch verwendet.")
                
            except Exception as e:
                self.log(f"❌ Fehler beim Profil-Import: {e}")
                QMessageBox.critical(self, "Fehler", f"Konnte Profil nicht importieren:\n{e}")

    def open_community_hub(self):
        try:
            self.community_window = CommunityHubWindow(self.framework_manager, self)
            self.community_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Community Hub:\n{e}")

    def open_hf_browser(self):
        """Öffnet den Hugging Face Model Browser"""
        try:
            self.hf_window = HuggingFaceWindow(self.framework_manager, self)
            self.hf_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open HF Browser:\n{e}")

    def check_for_updates_automatic(self):
        if not self.update_worker.isRunning():
            self.log("Prüfe auf Updates...")
            self.update_worker.start()
        else:
            self.log("Update-Prüfung läuft bereits...")

    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        controls = QGroupBox("Build Configuration")
        c_layout = QHBoxLayout(controls)
        
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Model Name (e.g. granite-3b)")
        c_layout.addWidget(QLabel("Model:"))
        c_layout.addWidget(self.model_name)
        
        # --- HuggingFace Browse Button ---
        self.hf_btn = QPushButton("🌐 Browse HF")
        self.hf_btn.setToolTip("Search models on Hugging Face Hub")
        self.hf_btn.setStyleSheet("background-color: #FFD21E; color: black; font-weight: bold;")
        self.hf_btn.clicked.connect(self.open_hf_browser)
        c_layout.addWidget(self.hf_btn)
        # --------------------------------
        
        self.target_combo = QComboBox()
        self.target_combo.addItems(["rk3566", "rk3588", "raspberry_pi", "nvidia_jetson"])
        c_layout.addWidget(QLabel("Target:"))
        c_layout.addWidget(self.target_combo)
        
        self.quant_combo = QComboBox()
        self.quant_combo.addItems(["Q4_K_M", "Q8_0", "Q5_K_M", "F16"])
        c_layout.addWidget(QLabel("Quantization:"))
        c_layout.addWidget(self.quant_combo)
        
        self.start_btn = QPushButton("Start Build")
        self.start_btn.clicked.connect(self.start_build)
        c_layout.addWidget(self.start_btn)
        layout.addWidget(controls)
        
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Courier;")
        layout.addWidget(self.log_view)

    def setup_sources_tab(self):
        layout = QVBoxLayout(self.sources_tab)
        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Reload from YAML")
        refresh_btn.clicked.connect(self.load_sources_to_table)
        toolbar.addWidget(refresh_btn)
        add_btn = QPushButton("➕ Add Source...")
        add_btn.clicked.connect(self.open_add_source_dialog)
        toolbar.addWidget(add_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(3)
        self.sources_table.setHorizontalHeaderLabels(["Category", "Key", "Repository URL"])
        self.sources_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.sources_table.setAlternatingRowColors(True)
        layout.addWidget(self.sources_table)
        layout.addWidget(QLabel("Loaded from configs/project_sources.yml"))

    def load_sources_to_table(self):
        self.framework_manager._load_extended_configuration()
        sources = self.framework_manager.config.source_repositories
        self.sources_table.setRowCount(0)
        row = 0
        for key, url in sources.items():
            if '.' in key: cat, name = key.split('.', 1)
            else: cat, name = "general", key
            self.sources_table.insertRow(row)
            self.sources_table.setItem(row, 0, QTableWidgetItem(cat))
            self.sources_table.setItem(row, 1, QTableWidgetItem(name))
            self.sources_table.setItem(row, 2, QTableWidgetItem(url))
            row += 1
            
    def open_add_source_dialog(self):
        dlg = AddSourceDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            self.save_new_source(data)
            
    def save_new_source(self, data):
        yaml_path = self.app_root / self.framework_manager.config.configs_dir / "project_sources.yml"
        if yaml_path.exists():
            with open(yaml_path, 'r') as f: import yaml; config = yaml.safe_load(f) or {}
        else: config = {}
        
        section = data['section']
        if section not in config: config[section] = {}
        config[section][data['name']] = data['url']
        
        try:
            yaml_path.parent.mkdir(parents=True, exist_ok=True)
            with open(yaml_path, 'w') as f: import yaml; yaml.dump(config, f, default_flow_style=False)
            self.log(f"Added source: {section}.{data['name']}")
            self.load_sources_to_table()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not write YAML: {e}")

    def open_module_wizard(self):
        # Use the dedicated Wizard class
        targets_dir = self.app_root / "targets"
        wizard = ModuleCreationWizard(targets_dir, self)
        wizard.exec()

    def run_image_audit(self):
        image_tag, ok = QInputDialog.getText(self, "Audit", "Image Tag:", QLineEdit.Normal, "llm-framework/rockchip:latest")
        if ok and image_tag:
            self.log(f"Starting audit for {image_tag}...")
            self.audit_process = QProcess()
            self.audit_process.setProcessChannelMode(QProcess.MergedChannels)
            self.audit_process.readyReadStandardOutput.connect(lambda: self.on_build_output("AUDIT", self.audit_process.readAllStandardOutput().data().decode().strip()))
            script_path = self.app_root / "scripts" / "ci_image_audit.sh"
            cmd = [str(script_path), image_tag]
            if sys.platform == "win32": cmd = ["bash"] + cmd
            self.audit_process.start(cmd[0], cmd[1:])

    def start_build(self):
        model = self.model_name.text().strip()
        if not model: return QMessageBox.warning(self, "Error", "Model name required")
        
        job_config = {
            "model_name": model,
            "model_path": "/models", 
            "target": self.target_combo.currentText(),
            "quantization": self.quant_combo.currentText(),
            "clean": False
        }
        try:
            self.start_btn.setEnabled(False)
            self.log(f"Starting build for {model}...")
            bid = self.docker_manager.start_build(job_config)
            self.log(f"Build ID: {bid}")
        except Exception as e:
            self.log(f"Error: {e}")
            self.start_btn.setEnabled(True)

    def on_build_output(self, bid, line):
        self.log_view.append(line)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def on_build_progress(self, bid, percent):
        self.progress_bar.setValue(percent)

    def on_build_completed(self, bid, success, path):
        self.start_btn.setEnabled(True)
        if success:
            self.log(f"✅ Success! Output: {path}")
            QMessageBox.information(self, "Done", f"Build successful.\n{path}")
        else:
            self.log("❌ Failed.")
            QMessageBox.critical(self, "Failed", "Build failed. See logs.")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {msg}")
