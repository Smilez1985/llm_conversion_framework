#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Orchestrator GUI
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
"""

import sys
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
    QDialog, QHeaderView, QWizard, QWizardPage, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings, QProcess
from PySide6.QtGui import QFont, QColor

import docker

# Import Core
from orchestrator.Core.docker_manager import DockerManager
from orchestrator.Core.framework import FrameworkConfig, FrameworkManager
from orchestrator.Core.module_generator import ModuleGenerator

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
        page.registerField("name*", self.name_edit) # Mandatory
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
        # IDs are 0-indexed based on addPage order
        if page_id == 4: # Summary Page
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
        # Collect Data
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
        
        try:
            # Use Core Generator
            targets_dir = Path("targets") 
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
        form.addRow("Section (Category):", self.section_edit)
        
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
            # Simple check if URL is reachable
            # Remove .git suffix for web check if needed, but git clone needs it. 
            # Requests handles redirects.
            test_url = url
            if url.endswith('.git'):
                 test_url = url[:-4]

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
# MAIN GUI CLASS
# ============================================================================

class MainOrchestrator(QMainWindow):
    """Main LLM Cross-Compiler Framework GUI"""
    
    def __init__(self):
        super().__init__()
        try:
            self.config = FrameworkConfig()
            self.framework_manager = FrameworkManager(self.config)
            self.framework_manager.initialize()
            
            self.docker_manager = DockerManager()
            self.docker_manager.initialize(self.framework_manager)
            
            self.docker_manager.build_output.connect(self.on_build_output)
            self.docker_manager.build_progress.connect(self.on_build_progress)
            self.docker_manager.build_completed.connect(self.on_build_completed)
            
        except Exception as e:
            QMessageBox.critical(None, "Initialization Error", f"Failed to init framework: {e}")
            sys.exit(1)
            
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("LLM Cross-Compiler Framework")
        self.setMinimumSize(1200, 800)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Build
        self.build_tab = QWidget()
        self.setup_build_tab()
        self.tabs.addTab(self.build_tab, "Build & Monitor")
        
        # Tab 2: Sources
        self.sources_tab = QWidget()
        self.setup_sources_tab()
        self.tabs.addTab(self.sources_tab, "Sources & Repositories")
        
        # Toolbar for Wizard
        toolbar = self.addToolBar("Tools")
        wizard_action = toolbar.addAction("Create New Module")
        wizard_action.triggered.connect(self.open_module_wizard)
        
        self.load_sources()

    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        
        controls = QGroupBox("Build Configuration")
        c_layout = QHBoxLayout(controls)
        
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Model Name (e.g. granite-3b)")
        c_layout.addWidget(QLabel("Model:"))
        c_layout.addWidget(self.model_name)
        
        self.target_combo = QComboBox()
        self.target_combo.addItems(["rk3566", "rk3588", "raspberry_pi"])
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
        self.reload_sources_btn = QPushButton("Reload Sources")
        self.reload_sources_btn.clicked.connect(self.load_sources)
        toolbar.addWidget(self.reload_sources_btn)
        
        self.add_source_btn = QPushButton("Add Source...")
        self.add_source_btn.clicked.connect(self.add_source)
        toolbar.addWidget(self.add_source_btn)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(3)
        self.sources_table.setHorizontalHeaderLabels(["Section", "Name (Key)", "URL"])
        self.sources_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.sources_table)

    def load_sources(self):
        self.sources_table.setRowCount(0)
        yaml_path = Path("configs/project_sources.yml")
        
        if not yaml_path.exists():
            self.log("No project_sources.yml found.")
            return
            
        try:
            with open(yaml_path, 'r') as f:
                data = yaml.safe_load(f)
            
            row = 0
            for section, items in data.items():
                if isinstance(items, dict):
                    for key, url in items.items():
                        self.sources_table.insertRow(row)
                        self.sources_table.setItem(row, 0, QTableWidgetItem(section))
                        self.sources_table.setItem(row, 1, QTableWidgetItem(key))
                        self.sources_table.setItem(row, 2, QTableWidgetItem(str(url)))
                        row += 1
                else:
                    self.sources_table.insertRow(row)
                    self.sources_table.setItem(row, 0, QTableWidgetItem("root"))
                    self.sources_table.setItem(row, 1, QTableWidgetItem(section))
                    self.sources_table.setItem(row, 2, QTableWidgetItem(str(items)))
                    row += 1
            self.log("Sources reloaded successfully.")
            
            # Also update framework config
            self.framework_manager._load_extended_configuration()
            
        except Exception as e:
            self.log(f"Error loading sources: {e}")

    def add_source(self):
        dlg = AddSourceDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            self.save_source_to_yaml(data)
            self.load_sources()

    def save_source_to_yaml(self, new_source):
        yaml_path = Path("configs/project_sources.yml")
        
        if yaml_path.exists():
            with open(yaml_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        section = new_source['section']
        name = new_source['name']
        url = new_source['url']
        
        if section not in config:
            config[section] = {}
        
        config[section][name] = url
        
        with open(yaml_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        self.log(f"Added source: {section}.{name}")

    def open_module_wizard(self):
        wizard = ModuleCreationWizard(self)
        wizard.exec()

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
            self.build_btn.setEnabled(False)
            self.log(f"Starting build for {model}...")
            build_id = self.docker_manager.start_build(job_config)
            self.log(f"Build ID: {build_id}")
        except Exception as e:
            self.log(f"Error starting build: {e}")
            self.build_btn.setEnabled(True)

    def on_build_output(self, build_id, line):
        self.log_view.append(line)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())
        
    def on_build_progress(self, build_id, percent):
        self.progress_bar.setValue(percent)
        
    def on_build_completed(self, build_id, success, output_path):
        self.build_btn.setEnabled(True)
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
    app = QApplication(sys.argv)
    window = MainOrchestrator()
    window.show()
    sys.exit(app.exec())
