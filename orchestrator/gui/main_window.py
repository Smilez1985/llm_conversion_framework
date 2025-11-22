#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Window GUI
DIREKTIVE: Goldstandard, MVC-Pattern, Separation of Concerns.

Beinhaltet die Haupt-GUI-Logik, Worker-Threads und Dialoge.
"""

import sys
import os
import time
import socket
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTextEdit, QProgressBar,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, 
    QMessageBox, QTableWidget, QTableWidgetItem,
    QDialog, QHeaderView, QWizard, QWizardPage, QRadioButton, QButtonGroup,
    QInputDialog
)
from PySide6.QtCore import Qt, QThread, pyqtSignal, QTimer, QProcess
from PySide6.QtGui import QAction

# Core & Utils Imports
from orchestrator.Core.docker_manager import DockerManager
from orchestrator.Core.framework import FrameworkConfig, FrameworkManager
from orchestrator.Core.module_generator import ModuleGenerator
from orchestrator.utils.updater import UpdateManager
from orchestrator.utils.logging import get_logger
from orchestrator.gui.community_hub import CommunityHubWindow


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
# DIALOGS & WIZARDS
# ============================================================================

class AddSourceDialog(QDialog):
    """Dialog to add a new source repository"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Source Repository")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        self.section_edit = QComboBox()
        self.section_edit.addItems(["core", "rockchip_npu", "voice_tts", "models", "custom"])
        self.section_edit.setEditable(True)
        form.addRow("Category (Section):", self.section_edit)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., my_special_tool")
        form.addRow("Name (Key):", self.name_edit)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://github.com/...")
        form.addRow("Git URL:", self.url_edit)
        
        layout.addLayout(form)
        
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        btns = QHBoxLayout()
        self.test_btn = QPushButton("Test URL")
        self.test_btn.clicked.connect(self.test_url)
        btns.addWidget(self.test_btn)
        
        self.save_btn = QPushButton("Add Source")
        self.save_btn.clicked.connect(self.accept)
        self.save_btn.setEnabled(False)
        btns.addWidget(self.save_btn)
        
        layout.addLayout(btns)
        
    def test_url(self):
        import requests
        url = self.url_edit.text().strip()
        if not url:
            self.status_label.setText("Please enter a URL.")
            return
            
        self.status_label.setText("Testing connection...")
        
        try:
            test_url = url
            if url.endswith('.git'): test_url = url[:-4]
            response = requests.head(test_url, timeout=5, allow_redirects=True)
            if response.status_code < 400:
                self.status_label.setText("✅ URL is valid and reachable.")
                self.status_label.setStyleSheet("color: green")
                self.save_btn.setEnabled(True)
            else:
                self.status_label.setText(f"❌ URL returned status: {response.status_code}")
                self.status_label.setStyleSheet("color: red")
        except Exception as e:
            self.status_label.setText(f"❌ Connection failed: {str(e)}")
            self.status_label.setStyleSheet("color: red")

    def get_data(self):
        return {
            "section": self.section_edit.currentText(),
            "name": self.name_edit.text(),
            "url": self.url_edit.text()
        }


class ModuleCreationWizard(QWizard):
    """5-Step Module Creation Wizard"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Module Creation Wizard")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(800, 600)
        self.module_data = {}
        
        self.addPage(self.create_intro_page())
        self.addPage(self.create_hardware_page())
        self.addPage(self.create_docker_page())
        self.addPage(self.create_flags_page())
        self.addPage(self.create_summary_page())

    def create_intro_page(self):
        page = QWizardPage()
        page.setTitle("Welcome")
        page.setSubTitle("Create a new Hardware Target Module")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("This wizard will guide you through creating a new hardware target."))
        page.setLayout(layout)
        return page

    def create_hardware_page(self):
        page = QWizardPage()
        page.setTitle("Hardware Information")
        layout = QFormLayout()
        self.name_edit = QLineEdit()
        layout.addRow("Module Name:", self.name_edit)
        self.arch_combo = QComboBox()
        self.arch_combo.addItems(["aarch64", "x86_64", "armv7l", "riscv64"])
        layout.addRow("Architecture:", self.arch_combo)
        self.sdk_edit = QLineEdit()
        layout.addRow("SDK / Backend:", self.sdk_edit)
        page.setLayout(layout)
        page.registerField("name*", self.name_edit) 
        return page

    def create_docker_page(self):
        page = QWizardPage()
        page.setTitle("Docker Environment")
        layout = QVBoxLayout()
        self.os_group = QButtonGroup(page)
        self.rad_debian = QRadioButton("Debian 12 (Bookworm)")
        self.rad_ubuntu = QRadioButton("Ubuntu 22.04 LTS")
        self.rad_debian.setChecked(True)
        self.os_group.addButton(self.rad_debian)
        self.os_group.addButton(self.rad_ubuntu)
        layout.addWidget(QLabel("Base OS:"))
        layout.addWidget(self.rad_debian)
        layout.addWidget(self.rad_ubuntu)
        layout.addWidget(QLabel("Packages:"))
        self.packages_edit = QLineEdit("build-essential cmake git")
        layout.addWidget(self.packages_edit)
        page.setLayout(layout)
        return page

    def create_flags_page(self):
        page = QWizardPage()
        page.setTitle("Compiler Flags")
        layout = QFormLayout()
        self.cpu_flags = QLineEdit()
        layout.addRow("CPU Flags:", self.cpu_flags)
        self.cmake_flags = QLineEdit()
        layout.addRow("CMake Flags:", self.cmake_flags)
        page.setLayout(layout)
        return page

    def create_summary_page(self):
        page = QWizardPage()
        page.setTitle("Summary")
        layout = QVBoxLayout()
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)
        page.setLayout(layout)
        return page

    def initializePage(self, page_id):
        if page_id == 4: self.update_summary()

    def update_summary(self):
        base_os = "debian:bookworm-slim" if self.rad_debian.isChecked() else "ubuntu:22.04"
        summary = f"Name: {self.name_edit.text()}\nArch: {self.arch_combo.currentText()}\nOS: {base_os}"
        self.summary_text.setText(summary)

    def accept(self):
        self.module_data = {
            "module_name": self.name_edit.text(),
            "architecture": self.arch_combo.currentText(),
            "sdk": self.sdk_edit.text(),
            "base_os": "debian:bookworm-slim" if self.rad_debian.isChecked() else "ubuntu:22.04",
            "packages": self.packages_edit.text().split(),
            "cpu_flags": self.cpu_flags.text(),
            "cmake_flags": self.cmake_flags.text(),
        }
        # Signal or processing via parent would happen here, but simplified for now:
        # In a real MVC, this would emit a signal, but here we call the generator directly
        # We need access to base_dir, which we get via parent or we assume a standard location relative to cwd
        # For better design, MainOrchestrator handles the logic, Wizard just collects data.
        # But to keep it working as before:
        try:
            # Assuming CWD is correct or we pass base_dir
            # For safety, let's just set the data and let the caller handle it, 
            # BUT MainOrchestrator logic was embedded here.
            # Let's rely on the caller (MainOrchestrator) to have passed the right context if needed.
            # Actually, the original code generated files inside the wizard.
            # We'll adapt to use the passed-in base_dir if available, or raise error.
            pass
        except Exception:
            pass
        super().accept()


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
        tools_menu = menubar.addMenu("&Tools")
        
        wizard_action = QAction("Create New Module...", self)
        wizard_action.triggered.connect(self.open_module_wizard)
        tools_menu.addAction(wizard_action)
        
        audit_action = QAction("🛡️ Audit Docker Image...", self)
        audit_action.triggered.connect(self.run_image_audit)
        tools_menu.addAction(audit_action)

        community_menu = menubar.addMenu("&Community")
        hub_action = QAction("🌍 Open Community Hub", self)
        hub_action.triggered.connect(self.open_community_hub)
        community_menu.addAction(hub_action)
        
        update_action = QAction("🔄 Check for Updates", self)
        update_action.triggered.connect(self.check_for_updates_automatic)
        community_menu.addAction(update_action)

    def open_community_hub(self):
        try:
            self.community_window = CommunityHubWindow(self.framework_manager, self)
            self.community_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Community Hub:\n{e}")

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
        wizard = ModuleCreationWizard(self)
        # Fix: The wizard needs to know where to generate files. 
        # We handle the generation here or pass the targets_dir to the wizard.
        # For now, we'll execute generation here after accept if we moved logic out of wizard.
        if wizard.exec():
            # Logic copied from old wizard.accept to ensure it runs with correct paths
            data = wizard.module_data
            targets_dir = self.app_root / "targets"
            try:
                targets_dir.mkdir(exist_ok=True)
                generator = ModuleGenerator(targets_dir)
                output_path = generator.generate_module(data)
                QMessageBox.information(self, "Generated", f"Module created at:\n{output_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Generation failed: {e}")

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
