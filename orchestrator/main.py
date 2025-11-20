#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Orchestrator GUI
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
THIN CLIENT VERSION: Führt Auto-Update im Basisverzeichnis aus.
"""

import sys
import os
import json
import logging
import subprocess
import yaml
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTextEdit, QProgressBar,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QSpinBox, QFileDialog,
    QMessageBox, QSplitter, QListWidget, QTableWidget, QTableWidgetItem,
    QDialog, QHeaderView, QWizard, QWizardPage, QRadioButton, QButtonGroup,
    QInputDialog
)
from PySide6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings, QProcess
from PySide6.QtGui import QFont, QColor, QAction

import docker

# Import Core
from orchestrator.Core.docker_manager import DockerManager
from orchestrator.Core.framework import FrameworkConfig, FrameworkManager
from orchestrator.Core.module_generator import ModuleGenerator


# ============================================================================
# AUTO-UPDATE LOGIC (THIN CLIENT STARTUP)
# ============================================================================

def get_base_dir():
    """Determine the absolute base directory of the application."""
    if getattr(sys, 'frozen', False):
        # If run as compiled EXE, the base dir is where the EXE is located
        return Path(sys.executable).parent
    else:
        # If run as script, the base dir is the repo root
        return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()

def run_auto_update():
    """Attempts to run 'git pull' in the application's base directory."""
    git_dir = BASE_DIR / ".git"
    if not git_dir.exists():
        print(f"[Auto-Update] No .git directory found in {BASE_DIR}. Skipping update.")
        return

    print(f"[Auto-Update] Checking for updates in {BASE_DIR}...")
    try:
        # On Windows, call git directly. Ensure git is in PATH.
        # Using shell=True to avoid console window popping up if possible, 
        # though capture_output helps too.
        result = subprocess.run(
            ["git", "pull"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        if "Already up to date." in result.stdout:
            print("[Auto-Update] Application is up to date.")
        else:
            print("[Auto-Update] Successfully updated.")
            print(result.stdout)
            # In a production app, you might prompt for restart here if core DLLs changed.
            # For this Python app, changes often apply next run anyway.
            
    except subprocess.CalledProcessError as e:
        print(f"[Auto-Update] Failed:\n{e.stderr}")
    except FileNotFoundError:
         print("[Auto-Update] 'git' command not found. Please install Git for auto-updates.")
    except Exception as e:
        print(f"[Auto-Update] Unexpected error: {e}")

# Change working directory to base dir so relative paths act correctly
os.chdir(BASE_DIR)


# ============================================================================
# ADD SOURCE DIALOG
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
        url = self.url_edit.text().strip()
        if not url:
            self.status_label.setText("Please enter a URL.")
            return
            
        self.status_label.setText("Testing connection...")
        QApplication.processEvents()
        
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

# ============================================================================
# MODULE CREATION WIZARD
# ============================================================================

class ModuleCreationWizard(QWizard):
    """5-Step Module Creation Wizard using Core Generator"""
    
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
        layout.addWidget(QLabel("This wizard will guide you through creating a new hardware target for the LLM Framework."))
        layout.addWidget(QLabel("It will generate:\n- Dockerfile\n- Target Configuration (YAML)\n- Shell Scripts for the build pipeline"))
        page.setLayout(layout)
        return page

    def create_hardware_page(self):
        page = QWizardPage()
        page.setTitle("Hardware Information")
        page.setSubTitle("Define the target architecture")
        layout = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. NVIDIA Jetson Orin")
        layout.addRow("Module Name:", self.name_edit)
        
        self.arch_combo = QComboBox()
        self.arch_combo.addItems(["aarch64", "x86_64", "armv7l", "riscv64"])
        layout.addRow("Architecture:", self.arch_combo)
        
        self.sdk_edit = QLineEdit()
        self.sdk_edit.setPlaceholderText("e.g. CUDA, RKNN, OpenVINO")
        layout.addRow("SDK / Backend:", self.sdk_edit)
        
        page.setLayout(layout)
        page.registerField("name*", self.name_edit) 
        return page

    def create_docker_page(self):
        page = QWizardPage()
        page.setTitle("Docker Environment")
        page.setSubTitle("Configure the build container")
        layout = QVBoxLayout()
        
        self.os_group = QButtonGroup(page)
        self.rad_debian = QRadioButton("Debian 12 (Bookworm) - Recommended")
        self.rad_ubuntu = QRadioButton("Ubuntu 22.04 LTS")
        self.rad_debian.setChecked(True)
        self.os_group.addButton(self.rad_debian)
        self.os_group.addButton(self.rad_ubuntu)
        
        layout.addWidget(QLabel("Base OS:"))
        layout.addWidget(self.rad_debian)
        layout.addWidget(self.rad_ubuntu)
        
        layout.addWidget(QLabel("Additional Packages (space separated):"))
        self.packages_edit = QLineEdit()
        self.packages_edit.setText("build-essential cmake git")
        layout.addWidget(self.packages_edit)
        
        page.setLayout(layout)
        return page

    def create_flags_page(self):
        page = QWizardPage()
        page.setTitle("Compiler Flags")
        page.setSubTitle("Set default optimization flags")
        layout = QFormLayout()
        
        self.cpu_flags = QLineEdit()
        self.cpu_flags.setPlaceholderText("-mcpu=cortex-a76")
        layout.addRow("CPU Flags:", self.cpu_flags)
        
        self.cmake_flags = QLineEdit()
        layout.addRow("CMake Flags:", self.cmake_flags)
        
        page.setLayout(layout)
        return page

    def create_summary_page(self):
        page = QWizardPage()
        page.setTitle("Summary & Generation")
        page.setSubTitle("Review settings before generation")
        layout = QVBoxLayout()
        
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)
        
        page.setLayout(layout)
        return page

    def initializePage(self, page_id):
        if page_id == 4: 
            self.update_summary()

    def update_summary(self):
        base_os = "debian:bookworm-slim" if self.rad_debian.isChecked() else "ubuntu:22.04"
        summary = f"""
        Module Name: {self.name_edit.text()}
        Architecture: {self.arch_combo.currentText()}
        SDK: {self.sdk_edit.text()}
        Base OS: {base_os}
        Packages: {self.packages_edit.text()}
        CPU Flags: {self.cpu_flags.text()}
        """
        self.summary_text.setText(summary)

    def accept(self):
        self.module_data = {
            "module_name": self.name_edit.text(),
            "architecture": self.arch_combo.currentText(),
            "sdk": self.sdk_edit.text(),
            "description": f"Target for {self.name_edit.text()}",
            "base_os": "debian:bookworm-slim" if self.rad_debian.isChecked() else "ubuntu:22.04",
            "packages": self.packages_edit.text().split(),
            "cpu_flags": self.cpu_flags.text(),
            "supported_boards": [],
            "setup_commands": "",
            "cmake_flags": self.cmake_flags.text(),
            "detection_commands": "lscpu"
        }
        
        # NOTE: In thin client mode, BASE_DIR is the app root.
        # The targets folder should be relative to BASE_DIR.
        targets_dir = BASE_DIR / "targets"
        
        try:
            # Ensure targets directory exists if running from fresh install
            targets_dir.mkdir(exist_ok=True)
            
            generator = ModuleGenerator(targets_dir)
            output_path = generator.generate_module(self.module_data)
            
            QMessageBox.information(
                self,
                "Module Generated",
                f"✅ Success!\n\nModule created at:\n{output_path}\n\nYou can now select this target in the CLI or GUI."
            )
            super().accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Generation Error", f"Failed to generate module: {e}")


# ============================================================================
# MAIN GUI CLASS
# ============================================================================

class MainOrchestrator(QMainWindow):
    """Main LLM Cross-Compiler Framework GUI"""
    
    def __init__(self):
        super().__init__()
        # Config path is relative to BASE_DIR in thin client mode
        config_path = BASE_DIR / "configs" / "framework_config.json"
        
        try:
            self.config = FrameworkConfig(config_path=str(config_path) if config_path.exists() else None)
            
            # Adjust paths in config to be absolute based on BASE_DIR
            self.config.targets_dir = str(BASE_DIR / self.config.targets_dir)
            self.config.models_dir = str(BASE_DIR / self.config.models_dir)
            self.config.output_dir = str(BASE_DIR / self.config.output_dir)
            self.config.configs_dir = str(BASE_DIR / self.config.configs_dir)
            self.config.cache_dir = str(BASE_DIR / self.config.cache_dir)
            self.config.logs_dir = str(BASE_DIR / self.config.logs_dir)
            
            self.framework_manager = FrameworkManager(self.config)
            self.framework_manager.initialize()
            
            self.docker_manager = DockerManager()
            self.docker_manager.initialize(self.framework_manager)
            
            self.docker_manager.build_output.connect(self.on_build_output)
            self.docker_manager.build_progress.connect(self.on_build_progress)
            self.docker_manager.build_completed.connect(self.on_build_completed)
            
        except Exception as e:
            QMessageBox.critical(None, "Initialization Error", f"Failed to init framework: {e}\nBase Dir: {BASE_DIR}")
            sys.exit(1)
            
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("LLM Cross-Compiler Framework")
        self.setMinimumSize(1200, 850)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; color: #ffffff; }
            QGroupBox { border: 1px solid #555; margin-top: 10px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit, QComboBox, QTextEdit, QTableWidget { 
                background-color: #353535; border: 1px solid #555; color: #fff; 
            }
            QPushButton { 
                background-color: #404040; border: 1px solid #555; padding: 5px; 
            }
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
        
        layout.addWidget(QLabel("These sources are loaded from configs/project_sources.yml"))

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
        # Use BASE_DIR to find the configs folder in thin client mode
        yaml_path = BASE_DIR / self.framework_manager.config.configs_dir / "project_sources.yml"
        
        if yaml_path.exists():
            with open(yaml_path, 'r') as f: config = yaml.safe_load(f) or {}
        else: config = {}
        
        section = data['section']
        name = data['name']
        url = data['url']
        
        if section not in config: config[section] = {}
        config[section][name] = url
        
        try:
            # Ensure directory exists
            yaml_path.parent.mkdir(parents=True, exist_ok=True)
            with open(yaml_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            self.log(f"Added new source: {section}.{name}")
            self.load_sources_to_table()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not write to YAML: {e}")

    def open_module_wizard(self):
        wizard = ModuleCreationWizard(self)
        wizard.exec()

    def run_image_audit(self):
        """Runs the CI Image Audit script via GUI"""
        image_tag, ok = QInputDialog.getText(
            self, "Docker Image Audit", 
            "Enter Image Tag to audit (e.g. llm-framework/rockchip:latest):",
            QLineEdit.Normal, "llm-framework/rockchip:latest"
        )
        
        if ok and image_tag:
            self.log(f"Starting audit for {image_tag}...")
            
            self.audit_process = QProcess()
            self.audit_process.setProcessChannelMode(QProcess.MergedChannels)
            
            self.audit_process.readyReadStandardOutput.connect(
                lambda: self.on_build_output("AUDIT", self.audit_process.readAllStandardOutput().data().decode().strip())
            )
            
            # Use BASE_DIR to find scripts in thin client mode
            script_path = BASE_DIR / "scripts" / "ci_image_audit.sh"
            
            cmd = [str(script_path), image_tag]
            if sys.platform == "win32":
                 cmd = ["bash"] + cmd
                 
            self.audit_process.start(cmd[0], cmd[1:])

    def start_build(self):
        model = self.model_name.text().strip()
        if not model:
            QMessageBox.warning(self, "Input Error", "Please enter a model name.")
            return
            
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
            build_id = self.docker_manager.start_build(job_config)
            self.log(f"Build ID: {build_id}")
        except Exception as e:
            self.log(f"Error starting build: {e}")
            self.start_btn.setEnabled(True)

    def on_build_output(self, build_id, line):
        self.log_view.append(line)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())
        
    def on_build_progress(self, build_id, percent):
        self.progress_bar.setValue(percent)
        
    def on_build_completed(self, build_id, success, output_path):
        self.start_btn.setEnabled(True)
        if success:
            self.log(f"✅ Build SUCCESS! Output: {output_path}")
            QMessageBox.information(self, "Build Complete", f"Successfully built model.\nLocation: {output_path}")
        else:
            self.log("❌ Build FAILED. Check logs above.")
            QMessageBox.critical(self, "Build Failed", "The build process failed.")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{timestamp}] {message}")

if __name__ == "__main__":
    # RUN AUTO-UPDATE BEFORE GUI STARTS
    run_auto_update()

    app = QApplication(sys.argv)
    window = MainOrchestrator()
    window.show()
    sys.exit(app.exec())
