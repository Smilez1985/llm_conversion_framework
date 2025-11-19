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
    QDialog, QHeaderView
)
from PySide6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings, QProcess
from PySide6.QtGui import QFont, QColor

import docker

# Import Core
from orchestrator.Core.docker_manager import DockerManager
from orchestrator.Core.framework import FrameworkConfig

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
            response = requests.head(url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
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
        self.config = FrameworkConfig()
        self.docker_manager = DockerManager()
        
        # Initialize UI
        self.init_ui()
        self.init_docker()
        
    def init_ui(self):
        self.setWindowTitle("LLM Cross-Compiler Framework")
        self.setMinimumSize(1200, 800)
        
        # Central Widget
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
        
        # Tab 2: Sources (NEW)
        self.sources_tab = QWidget()
        self.setup_sources_tab()
        self.tabs.addTab(self.sources_tab, "Sources & Repositories")
        
        self.load_sources()

    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        
        # Controls
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
        
        self.start_btn = QPushButton("Start Build")
        self.start_btn.clicked.connect(self.start_build)
        c_layout.addWidget(self.start_btn)
        
        layout.addWidget(controls)
        
        # Monitor
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Courier;")
        layout.addWidget(self.log_view)

    def setup_sources_tab(self):
        layout = QVBoxLayout(self.sources_tab)
        
        # Toolbar
        toolbar = QHBoxLayout()
        self.reload_sources_btn = QPushButton("Reload Sources")
        self.reload_sources_btn.clicked.connect(self.load_sources)
        toolbar.addWidget(self.reload_sources_btn)
        
        self.add_source_btn = QPushButton("Add Source...")
        self.add_source_btn.clicked.connect(self.add_source)
        toolbar.addWidget(self.add_source_btn)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # Table
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(3)
        self.sources_table.setHorizontalHeaderLabels(["Section", "Name (Key)", "URL"])
        self.sources_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.sources_table)
        
        info = QLabel("These sources are loaded from configs/project_sources.yml and injected into builds.")
        layout.addWidget(info)

    def load_sources(self):
        """Load project_sources.yml into table"""
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
                     # Flat structure fallback
                    self.sources_table.insertRow(row)
                    self.sources_table.setItem(row, 0, QTableWidgetItem("root"))
                    self.sources_table.setItem(row, 1, QTableWidgetItem(section))
                    self.sources_table.setItem(row, 2, QTableWidgetItem(str(items)))
                    row += 1
            
            self.log("Sources reloaded successfully.")
            
        except Exception as e:
            self.log(f"Error loading sources: {e}")

    def add_source(self):
        """Open add source dialog and save to YAML"""
        dlg = AddSourceDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            self.save_source_to_yaml(data)
            self.load_sources()

    def save_source_to_yaml(self, new_source):
        yaml_path = Path("configs/project_sources.yml")
        
        # Load existing
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
        
        # Save back
        with open(yaml_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        self.log(f"Added source: {section}.{name}")

    def init_docker(self):
        # Placeholder for docker init logic from previous main.py
        pass

    def start_build(self):
        self.log("Starting build...")
        # Here we would trigger the DockerManager
        self.log("Build triggered (Mockup)")

    def log(self, message):
        self.log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def main():
    app = QApplication(sys.argv)
    window = MainOrchestrator()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
