#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Deployment Window (v1.0)
DIREKTIVE: Goldstandard GUI.

Zweck:
Ermöglicht dem Benutzer die Zusammenstellung eines Deployment-Pakets.
- Auswahl des Artefakts (Golden Artifact).
- Auswahl des Ziel-Profils (Hardware Profile).
- Konfiguration der Docker-Container (User Decision).
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QCheckBox, QGroupBox, QHeaderView, QMessageBox, QListWidget
)
from PySide6.QtCore import Qt
from orchestrator.utils.localization import get_instance as get_i18n

class DeploymentWindow(QWidget):
    def __init__(self, framework_manager, parent=None):
        super().__init__(parent)
        self.framework = framework_manager
        self.target_manager = framework_manager.get_component("target_manager") # Zugriff auf Profile
        self.i18n = get_i18n()
        
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- 1. Artifact Selection ---
        grp_artifact = QGroupBox("1. Select Golden Artifact")
        layout_art = QVBoxLayout()
        self.list_artifacts = QListWidget()
        layout_art.addWidget(self.list_artifacts)
        grp_artifact.setLayout(layout_art)
        layout.addWidget(grp_artifact)
        
        # --- 2. Target Profile Selection ---
        grp_target = QGroupBox("2. Select Target Hardware Profile")
        layout_target = QHBoxLayout()
        self.cb_profiles = QComboBox()
        layout_target.addWidget(QLabel("Profile:"))
        layout_target.addWidget(self.cb_profiles, 1)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self.refresh_data)
        layout_target.addWidget(btn_refresh)
        
        grp_target.setLayout(layout_target)
        layout.addWidget(grp_target)
        
        # --- 3. Docker Configuration ---
        grp_docker = QGroupBox("3. Docker Configuration")
        grp_docker.setCheckable(True)
        grp_docker.setChecked(False)
        grp_docker.setTitle("Use Docker Containerization?")
        
        layout_docker = QVBoxLayout()
        
        self.table_docker = QTableWidget()
        self.table_docker.setColumnCount(2)
        self.table_docker.setHorizontalHeaderLabels(["Component", "Container Type"])
        self.table_docker.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        # Mockup Rows (Wird später dynamisch)
        self._add_docker_row("Orchestrator Logic", ["Python Slim", "Full Debian"])
        self._add_docker_row("Inference Engine", ["Llama.cpp (CPU)", "RKLLM (NPU)", "TensorRT (GPU)"])
        self._add_docker_row("Knowledge Base", ["Qdrant Sidecar", "None"])
        
        layout_docker.addWidget(self.table_docker)
        grp_docker.setLayout(layout_docker)
        layout.addWidget(grp_docker)
        
        # --- 4. Action Buttons ---
        btn_layout = QHBoxLayout()
        
        self.btn_generate = QPushButton("📦 Generate Package Only")
        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_generate.setStyleSheet("background-color: #444; color: white; padding: 10px;")
        
        self.btn_deploy = QPushButton("🚀 Deploy to Target")
        self.btn_deploy.clicked.connect(self._on_deploy)
        self.btn_deploy.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 10px;")
        
        btn_layout.addWidget(self.btn_generate)
        btn_layout.addWidget(self.btn_deploy)
        layout.addLayout(btn_layout)

    def _add_docker_row(self, name, options):
        row = self.table_docker.rowCount()
        self.table_docker.insertRow(row)
        
        self.table_docker.setItem(row, 0, QTableWidgetItem(name))
        
        cb = QComboBox()
        cb.addItems(options)
        self.table_docker.setCellWidget(row, 1, cb)

    def refresh_data(self):
        # 1. Load Artifacts from Output Dir
        self.list_artifacts.clear()
        output_dir = Path(self.framework.config.output_dir)
        if output_dir.exists():
            for item in output_dir.glob("*"):
                if item.is_dir() or item.suffix in ['.zip', '.tar.gz']:
                    self.list_artifacts.addItem(item.name)
        
        # 2. Load Profiles from TargetManager
        self.cb_profiles.clear()
        if self.target_manager:
            profiles = self.target_manager.list_hardware_profiles()
            self.cb_profiles.addItems(profiles)
        else:
            self.cb_profiles.addItem("Error: TargetManager not loaded")

    def _on_generate(self):
        # Placeholder Logic
        artifact = self.list_artifacts.currentItem()
        if not artifact:
            QMessageBox.warning(self, "Warning", "Please select an artifact first.")
            return
        
        QMessageBox.information(self, "Generate", f"Generating package for {artifact.text()}...")
        # Hier würde der Aufruf an DeploymentManager.create_package() folgen

    def _on_deploy(self):
        # Placeholder Logic
        artifact = self.list_artifacts.currentItem()
        if not artifact:
            QMessageBox.warning(self, "Warning", "Please select an artifact first.")
            return
            
        QMessageBox.information(self, "Deploy", f"Starting deployment sequence for {artifact.text()}...")
        # Hier würde der Aufruf an DeploymentManager.deploy_artifact() folgen
