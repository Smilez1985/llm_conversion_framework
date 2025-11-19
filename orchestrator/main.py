#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Orchestrator GUI
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Hauptfunktionen:
- Build Management & Monitoring
- Target Selection
- Source Repository Management (Neu!)
- Docker Orchestration via Core Module
"""

import sys
import json
import logging
import requests
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTextEdit, QProgressBar,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, 
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QSplitter
)
from PySide6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PySide6.QtGui import QFont, QColor

# Import Core Components
# Wir nutzen jetzt die ausgelagerten Manager!
from orchestrator.Core.docker_manager import DockerManager
from orchestrator.Core.framework import FrameworkManager, FrameworkConfig

# ============================================================================
# DIALOG: ADD SOURCE
# ============================================================================

class AddSourceDialog(QDialog):
    """Dialog to add a new source repository with validation"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Source Repository")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        # Eingabefelder
        form = QFormLayout()
        
        self.section_edit = QComboBox()
        self.section_edit.addItems(["core", "rockchip_npu", "voice_tts", "models", "custom"])
        self.section_edit.setEditable(True)
        form.addRow("Category (Section):", self.section_edit)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. my_special_tool")
        form.addRow("Name (Key):", self.name_edit)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://github.com/username/repo.git")
        form.addRow("Git URL:", self.url_edit)
        
        layout.addLayout(form)
        
        # Status Anzeige für Test
        self.status_box = QGroupBox("Validation Status")
        status_layout = QVBoxLayout()
        self.status_label = QLabel("Enter a URL and click 'Test Connection'")
        status_layout.addWidget(self.status_label)
        self.status_box.setLayout(status_layout)
        layout.addWidget(self.status_box)
        
        # Buttons
        btns = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_url)
        btns.addWidget(self.test_btn)
        
        self.save_btn = QPushButton("Add Source")
        self.save_btn.clicked.connect(self.accept)
        self.save_btn.setEnabled(False) # Erst aktiv nach erfolgreichem Test
        btns.addWidget(self.save_btn)
        
        layout.addLayout(btns)
        
    def test_url(self):
        """Validiert die URL via HTTP HEAD Request"""
        url = self.url_edit.text().strip()
        if not url:
            self.status_label.setText("❌ Please enter a URL.")
            return
            
        self.status_label.setText("⏳ Testing connection...")
        self.status_label.setStyleSheet("color: orange")
        QApplication.processEvents()
        
        try:
            # Wir machen einen HEAD request um nicht das ganze Repo zu laden
            # Bei GitHub URLs ohne .git am Ende kann man oft die Web-URL testen
            test_url = url.replace(".git", "") 
            response = requests.head(test_url, timeout=5, allow_redirects=True)
            
            if response.status_code < 400:
                self.status_label.setText(f"✅ Connection successful (Status: {response.status_code})")
                self.status_label.setStyleSheet("color: #00FF00") # Hellgrün
                self.save_btn.setEnabled(True)
            else:
                self.status_label.setText(f"❌ URL returned error status: {response.status_code}")
                self.status_label.setStyleSheet("color: #FF5555") # Rot
        except Exception as e:
            self.status_label.setText(f"❌ Connection failed: {str(e)}")
            self.status_label.setStyleSheet("color: #FF5555")

    def get_data(self):
        return {
            "section": self.section_edit.currentText(),
            "name": self.name_edit.text(),
            "url": self.url_edit.text().strip()
        }

# ============================================================================
# MAIN WINDOW
# ============================================================================

class MainOrchestrator(QMainWindow):
    """Main GUI Application"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize Core Components
        try:
            self.config = FrameworkConfig() # Lädt defaults
            self.framework_manager = FrameworkManager(self.config)
            self.framework_manager.initialize() # Lädt project_sources.yml
            
            self.docker_manager = DockerManager()
            self.docker_manager.initialize(self.framework_manager)
            
            # Connect Docker Signals
            self.docker_manager.build_output.connect(self.on_build_output)
            self.docker_manager.build_progress.connect(self.on_build_progress)
            self.docker_manager.build_completed.connect(self.on_build_completed)
            
        except Exception as e:
            QMessageBox.critical(self, "Initialization Error", f"Failed to init framework: {e}")
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
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # --- Tab 1: Build & Monitor ---
        self.build_tab = QWidget()
        self.setup_build_tab()
        self.tabs.addTab(self.build_tab, "Build & Monitor")
        
        # --- Tab 2: Sources & Repositories ---
        self.sources_tab = QWidget()
        self.setup_sources_tab()
        self.tabs.addTab(self.sources_tab, "Sources & Repositories")
        
        # Load initial data
        self.load_sources_to_table()
        
    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        
        # Top Area: Config
        config_group = QGroupBox("Build Configuration")
        config_layout = QHBoxLayout()
        
        # Model Input
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Model Name / Path (e.g. granite-3b)")
        config_layout.addWidget(QLabel("Model:"))
        config_layout.addWidget(self.model_input)
        
        # Target
        self.target_combo = QComboBox()
        self.target_combo.addItems(["rk3566", "rk3588", "raspberry_pi", "nvidia_jetson"])
        config_layout.addWidget(QLabel("Target:"))
        config_layout.addWidget(self.target_combo)
        
        # Quantization
        self.quant_combo = QComboBox()
        self.quant_combo.addItems(["Q4_K_M", "Q8_0", "Q5_K_M", "F16"])
        config_layout.addWidget(QLabel("Quantization:"))
        config_layout.addWidget(self.quant_combo)
        
        # Build Button
        self.build_btn = QPushButton("🚀 Start Build")
        self.build_btn.clicked.connect(self.start_build)
        self.build_btn.setStyleSheet("background-color: #2d8a2d; font-weight: bold;")
        config_layout.addWidget(self.build_btn)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Middle Area: Progress & Logs
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Courier New", 9))
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00;")
        layout.addWidget(self.log_view)
        
    def setup_sources_tab(self):
        layout = QVBoxLayout(self.sources_tab)
        
        # Info Label
        info = QLabel("Manage external repositories here. These URLs are injected into the build process.")
        info.setStyleSheet("color: #aaa; font-style: italic;")
        layout.addWidget(info)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Reload from YAML")
        refresh_btn.clicked.connect(self.load_sources_to_table)
        toolbar.addWidget(refresh_btn)
        
        add_btn = QPushButton("➕ Add Source...")
        add_btn.clicked.connect(self.open_add_source_dialog)
        toolbar.addWidget(add_btn)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # Table
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(3)
        self.sources_table.setHorizontalHeaderLabels(["Category", "Key", "Repository URL"])
        self.sources_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.sources_table.setAlternatingRowColors(True)
        layout.addWidget(self.sources_table)
        
    def load_sources_to_table(self):
        """Reloads sources from FrameworkManager (which read the YAML)"""
        # Force reload of config from disk
        # Wir greifen auf die interne Methode zu, um sicherzugehen, dass wir den neuesten Stand haben
        self.framework_manager._load_extended_configuration()
        
        sources = self.framework_manager.config.source_repositories
        
        self.sources_table.setRowCount(0)
        
        row = 0
        for key, url in sources.items():
            # key ist z.B. "core.llama_cpp" -> Split
            if '.' in key:
                cat, name = key.split('.', 1)
            else:
                cat, name = "general", key
                
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
        """Writes the new source to project_sources.yml"""
        yaml_path = Path(self.framework_manager.config.configs_dir) / "project_sources.yml"
        
        # Load existing YAML to preserve structure
        if yaml_path.exists():
            with open(yaml_path, 'r') as f:
                full_data = yaml.safe_load(f) or {}
        else:
            full_data = {}
            
        section = data['section']
        name = data['name']
        url = data['url']
        
        if section not in full_data:
            full_data[section] = {}
            
        full_data[section][name] = url
        
        try:
            with open(yaml_path, 'w') as f:
                yaml.dump(full_data, f, default_flow_style=False)
            
            self.log(f"Added new source: {section}.{name} -> {url}")
            self.load_sources_to_table() # Refresh View
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not write to YAML: {e}")

    # --- Build Logic ---
    
    def start_build(self):
        model = self.model_input.text().strip()
        if not model:
            QMessageBox.warning(self, "Input Error", "Please enter a model name or path.")
            return
            
        job_config = {
            "model_name": model,
            "model_path": "/models", # Mapping in Docker
            "target": self.target_combo.currentText(),
            "quantization": self.quant_combo.currentText(),
            "clean": False
        }
        
        try:
            self.build_btn.setEnabled(False)
            self.log(f"Starting build for {model} on {job_config['target']}...")
            build_id = self.docker_manager.start_build(job_config)
            self.log(f"Build ID: {build_id}")
        except Exception as e:
            self.log(f"Error starting build: {e}")
            self.build_btn.setEnabled(True)

    # --- Docker Signals ---
    
    def on_build_output(self, build_id, line):
        self.log_view.append(line)
        # Auto-scroll
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
            QMessageBox.critical(self, "Build Failed", "The build process failed. Please check the logs.")

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{timestamp}] {msg}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainOrchestrator()
    window.show()
    sys.exit(app.exec())
