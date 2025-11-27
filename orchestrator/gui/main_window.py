#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Window GUI
DIREKTIVE: Goldstandard, MVC-Pattern, Separation of Concerns.
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
    QDialog, QInputDialog, QFileDialog, QCheckBox 
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
from orchestrator.gui.benchmark_window import BenchmarkWindow

class UpdateWorker(QThread):
    update_available = pyqtSignal(bool)
    def __init__(self, app_root):
        super().__init__()
        self.app_root = app_root
        self._is_running = True

    def run(self):
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
        
        if not connected: return
        try:
            updater = UpdateManager(self.app_root)
            if updater.check_for_updates():
                self.update_available.emit(True)
        except: pass 

    def stop(self):
        self._is_running = False


class MainOrchestrator(QMainWindow):
    def __init__(self, app_root: Path):
        super().__init__()
        self.app_root = app_root
        self.logger = get_logger(__name__)
        
        config_path = self.app_root / "configs" / "framework_config.json"
        try:
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
            sys.exit(1)
            
        self.init_ui()
        
        self.update_worker = UpdateWorker(self.app_root)
        self.update_worker.update_available.connect(self.on_update_available)
        QTimer.singleShot(2000, self.update_worker.start)

    def on_update_available(self, available):
        if available:
            reply = QMessageBox.question(
                self, "Update Verfügbar", 
                "Eine neue Version des LLM-Builders ist verfügbar.\n\n"
                "Jetzt herunterladen und neu starten?",
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
        self.tabs.addTab(self.sources_tab, "Sources")
        
        self.load_sources_to_table()

    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("&File")
        import_action = QAction("Import Hardware Profile...", self)
        import_action.triggered.connect(self.import_hardware_profile)
        file_menu.addAction(import_action)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

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

    def import_hardware_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Profile", "", "Config (*.txt)")
        if path:
            try:
                cache_dir = self.app_root / "cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, cache_dir / "target_hardware_config.txt")
                self.log(f"Hardware-Profil importiert: {path}")
                QMessageBox.information(self, "Success", "Profile imported.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def open_community_hub(self):
        try:
            self.community_window = CommunityHubWindow(self.framework_manager, self)
            self.community_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Hub: {e}")

    def open_hf_browser(self):
        try:
            self.hf_window = HuggingFaceWindow(self.framework_manager, self)
            self.hf_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open HF Browser: {e}")

    def open_benchmark_window(self):
        try:
            self.bench_window = BenchmarkWindow(self.framework_manager, self)
            self.bench_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Benchmark: {e}")

    def check_for_updates_automatic(self):
        if not self.update_worker.isRunning():
            self.log("Prüfe auf Updates...")
            self.update_worker.start()

    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        controls = QGroupBox("Build Configuration")
        c_layout = QHBoxLayout(controls)
        
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Model Name (e.g. granite-3b)")
        c_layout.addWidget(QLabel("Model:"))
        c_layout.addWidget(self.model_name)
        
        self.hf_btn = QPushButton("🌐 Browse HF")
        self.hf_btn.setStyleSheet("background-color: #FFD21E; color: black; font-weight: bold;")
        self.hf_btn.clicked.connect(self.open_hf_browser)
        c_layout.addWidget(self.hf_btn)
        
        self.target_combo = QComboBox()
        self.target_combo.addItems(["rockchip", "nvidia_jetson", "raspberry_pi", "hailo"]) 
        c_layout.addWidget(QLabel("Target:"))
        c_layout.addWidget(self.target_combo)
        
        # NEU: Task Auswahl
        self.task_combo = QComboBox()
        self.task_combo.addItems(["LLM", "VOICE", "VLM"])
        c_layout.addWidget(QLabel("Task:"))
        c_layout.addWidget(self.task_combo)
        
        # NEU: Quantisierung
        self.quant_combo = QComboBox()
        self.quant_combo.addItems(["Q4_K_M", "Q8_0", "INT4", "INT8", "FP16"])
        c_layout.addWidget(QLabel("Quant:"))
        c_layout.addWidget(self.quant_combo)
        
        self.chk_auto_bench = QCheckBox("Auto-Benchmark")
        self.chk_auto_bench.setChecked(True)
        c_layout.addWidget(self.chk_auto_bench)
        
        self.start_btn = QPushButton("Start Build")
        self.start_btn.clicked.connect(self.start_build)
        c_layout.addWidget(self.start_btn)
        
        self.bench_btn = QPushButton("📊 Bench")
        self.bench_btn.clicked.connect(self.open_benchmark_window)
        c_layout.addWidget(self.bench_btn)
        
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
        btn = QPushButton("🔄 Reload"); btn.clicked.connect(self.load_sources_to_table); toolbar.addWidget(btn)
        btn2 = QPushButton("➕ Add"); btn2.clicked.connect(self.open_add_source_dialog); toolbar.addWidget(btn2)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        self.sources_table = QTableWidget(0, 3)
        self.sources_table.setHorizontalHeaderLabels(["Category", "Key", "Repository URL"])
        layout.addWidget(self.sources_table)
        layout.addWidget(QLabel("Loaded from configs/project_sources.yml"))

    def load_sources_to_table(self):
        self.framework_manager._load_extended_configuration()
        sources = self.framework_manager.config.source_repositories
        self.sources_table.setRowCount(0)
        for key, url in sources.items():
            row = self.sources_table.rowCount()
            self.sources_table.insertRow(row)
            cat = key.split('.')[0] if '.' in key else "gen"
            name = key.split('.')[1] if '.' in key else key
            url_display = url['url'] if isinstance(url, dict) else url
            self.sources_table.setItem(row, 0, QTableWidgetItem(cat))
            self.sources_table.setItem(row, 1, QTableWidgetItem(name))
            self.sources_table.setItem(row, 2, QTableWidgetItem(url_display))

    def open_add_source_dialog(self):
        if AddSourceDialog(self).exec(): self.load_sources_to_table()

    def open_module_wizard(self):
        ModuleCreationWizard(self.app_root / "targets", self).exec()

    def run_image_audit(self):
        pass

    def start_build(self):
        if not self.model_name.text(): return QMessageBox.warning(self, "Error", "Model name required")
        
        # Build Config zusammenstellen
        cfg = {
            "model_name": self.model_name.text(),
            "target": self.target_combo.currentText(),
            "task": self.task_combo.currentText(),
            "quantization": self.quant_combo.currentText(),
            "auto_benchmark": self.chk_auto_bench.isChecked()
        }
        
        self.log(f"Starting build for {cfg['target']} ({cfg['task']}) with {cfg['quantization']}...")
        self.start_btn.setEnabled(False)
        
        # Start via DockerManager
        self.docker_manager.start_build(cfg)

    def on_build_output(self, bid, line):
        self.log_view.append(line)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def on_build_progress(self, bid, pct):
        self.progress_bar.setValue(pct)

    def on_build_completed(self, bid, success, path):
        self.start_btn.setEnabled(True)
        if success:
            self.log(f"✅ Success! Output: {path}")
            if self.chk_auto_bench.isChecked():
                self.log("Starting Auto-Benchmark...")
                self.open_benchmark_window()
        else:
            self.log("❌ Failed.")
            QMessageBox.critical(self, "Failed", "Build failed.")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {msg}")
