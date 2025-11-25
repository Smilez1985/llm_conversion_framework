#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Window GUI
DIREKTIVE: Goldstandard, MVC-Pattern.
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
from orchestrator.gui.benchmark_window import BenchmarkWindow # NEU


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
            except OSError: time.sleep(1)
        if not connected: return
        try:
            updater = UpdateManager(self.app_root)
            if updater.check_for_updates(): self.update_available.emit(True)
        except: pass 
    def stop(self): self._is_running = False


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
            print(f"INIT ERROR: {e}")
            sys.exit(1)
            
        self.init_ui()
        self.update_worker = UpdateWorker(self.app_root)
        self.update_worker.update_available.connect(self.on_update_available)
        QTimer.singleShot(2000, self.update_worker.start)

    def on_update_available(self, available):
        if available:
            if QMessageBox.question(self, "Update", "New version available. Update now?") == QMessageBox.Yes:
                UpdateManager(self.app_root).perform_update_and_restart()

    def init_ui(self):
        self.setWindowTitle("LLM Cross-Compiler Framework")
        self.setMinimumSize(1200, 850)
        self.setStyleSheet("QMainWindow { background-color: #2b2b2b; color: #fff; } QGroupBox { border: 1px solid #555; margin-top: 10px; }")
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
        bar = self.menuBar()
        file = bar.addMenu("&File")
        file.addAction("Import Hardware Profile...", self.import_hardware_profile)
        file.addSeparator()
        file.addAction("Exit", self.close)
        tools = bar.addMenu("&Tools")
        tools.addAction("Create New Module...", self.open_module_wizard)
        tools.addAction("Audit Docker Image...", self.run_image_audit)
        comm = bar.addMenu("&Community")
        comm.addAction("Open Community Hub", self.open_community_hub)
        comm.addAction("Check for Updates", self.check_for_updates_automatic)

    def import_hardware_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Profile", "", "Config (*.txt)")
        if path:
            try:
                dest = self.app_root / "cache" / "target_hardware_config.txt"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                self.log(f"Profile imported: {dest}")
                QMessageBox.information(self, "Success", "Profile imported.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def open_community_hub(self):
        CommunityHubWindow(self.framework_manager, self).show()

    def open_hf_browser(self):
        HuggingFaceWindow(self.framework_manager, self).show()
    
    def open_benchmark_window(self):
        BenchmarkWindow(self.framework_manager, self).show()

    def check_for_updates_automatic(self):
        if not self.update_worker.isRunning(): self.update_worker.start()

    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        controls = QGroupBox("Build Configuration")
        c_layout = QHBoxLayout(controls)
        
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Model Name (Granite-3b)")
        c_layout.addWidget(QLabel("Model:"))
        c_layout.addWidget(self.model_name)
        
        self.hf_btn = QPushButton("🌐 Browse HF")
        self.hf_btn.setStyleSheet("background-color: #FFD21E; color: black; font-weight: bold;")
        self.hf_btn.clicked.connect(self.open_hf_browser)
        c_layout.addWidget(self.hf_btn)
        
        self.target_combo = QComboBox()
        self.target_combo.addItems(["rk3566", "rk3588", "raspberry_pi", "nvidia_jetson"])
        c_layout.addWidget(QLabel("Target:"))
        c_layout.addWidget(self.target_combo)
        
        self.quant_combo = QComboBox()
        self.quant_combo.addItems(["Q4_K_M", "Q8_0", "Q5_K_M", "F16"])
        c_layout.addWidget(QLabel("Quant:"))
        c_layout.addWidget(self.quant_combo)
        
        # --- AUTO BENCHMARK CHECKBOX ---
        self.chk_auto_bench = QCheckBox("Auto-Benchmark")
        self.chk_auto_bench.setToolTip("Run benchmark after build")
        self.chk_auto_bench.setChecked(True)
        c_layout.addWidget(self.chk_auto_bench)
        
        self.start_btn = QPushButton("Start Build")
        self.start_btn.clicked.connect(self.start_build)
        c_layout.addWidget(self.start_btn)
        
        # --- MANUAL BENCHMARK BUTTON ---
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
        self.sources_table.setHorizontalHeaderLabels(["Category", "Key", "URL"])
        layout.addWidget(self.sources_table)

    def load_sources_to_table(self):
        self.framework_manager._load_extended_configuration()
        src = self.framework_manager.config.source_repositories
        self.sources_table.setRowCount(0)
        for k, v in src.items():
            r = self.sources_table.rowCount()
            self.sources_table.insertRow(r)
            cat = k.split('.')[0] if '.' in k else "gen"
            name = k.split('.')[1] if '.' in k else k
            # Handle dict values (secure sources)
            url_display = v['url'] if isinstance(v, dict) else v
            self.sources_table.setItem(r, 0, QTableWidgetItem(cat))
            self.sources_table.setItem(r, 1, QTableWidgetItem(name))
            self.sources_table.setItem(r, 2, QTableWidgetItem(url_display))

    def open_add_source_dialog(self):
        if AddSourceDialog(self).exec(): self.load_sources_to_table() # Simplified logic

    def open_module_wizard(self):
        ModuleCreationWizard(self.app_root / "targets", self).exec()

    def run_image_audit(self):
        # Existing audit logic ...
        pass

    def start_build(self):
        if not self.model_name.text(): return
        cfg = {
            "model_name": self.model_name.text(),
            "target": self.target_combo.currentText(),
            "quantization": self.quant_combo.currentText(),
            "auto_benchmark": self.chk_auto_bench.isChecked() # Pass flag
        }
        self.start_btn.setEnabled(False)
        self.docker_manager.start_build(cfg)

    def on_build_output(self, bid, line):
        self.log_view.append(line)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
    
    def on_build_progress(self, bid, pct): self.progress_bar.setValue(pct)
    
    def on_build_completed(self, bid, success, path):
        self.start_btn.setEnabled(True)
        if success:
            self.log(f"Success: {path}")
            if self.chk_auto_bench.isChecked():
                self.log("Starting Auto-Benchmark...")
                # Hier würde man das Benchmark-Fenster automatisch öffnen oder den Prozess triggern
                self.open_benchmark_window() 
        else: self.log("Failed.")

    def log(self, msg): self.log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
