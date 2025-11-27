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
    QDialog, QInputDialog, QFileDialog, QCheckBox, QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QProcess
from PySide6.QtGui import QAction, QIcon

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
    update_available = Signal(bool)
    
    def __init__(self, app_root):
        super().__init__()
        self.app_root = app_root
        self._is_running = True

    def run(self):
        # Check connectivity first
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
        except Exception: 
            pass 

    def stop(self):
        self._is_running = False


class MainOrchestrator(QMainWindow):
    """
    Main GUI Application Window.
    Orchestrates all UI components and connects to Core Logic.
    """
    def __init__(self, app_root: Path):
        super().__init__()
        self.app_root = app_root
        self.logger = get_logger(__name__)
        
        # Initialize Framework Core
        config_path = self.app_root / "configs" / "framework_config.json"
        try:
            # Initialize Config
            config = FrameworkConfig()
            # Resolve paths relative to app root
            config.targets_dir = str(self.app_root / config.targets_dir)
            config.models_dir = str(self.app_root / config.models_dir)
            config.output_dir = str(self.app_root / config.output_dir)
            config.configs_dir = str(self.app_root / config.configs_dir)
            config.cache_dir = str(self.app_root / config.cache_dir)
            config.logs_dir = str(self.app_root / config.logs_dir)
            
            self.framework_manager = FrameworkManager(config)
            if not self.framework_manager.initialize():
                raise RuntimeError("Framework Manager failed to initialize")
            
            self.docker_manager = DockerManager()
            self.docker_manager.initialize(self.framework_manager)
            
            # Connect Docker Signals
            self.docker_manager.build_output.connect(self.on_build_output)
            self.docker_manager.build_progress.connect(self.on_build_progress)
            self.docker_manager.build_completed.connect(self.on_build_completed)
            
        except Exception as e:
            print(f"CRITICAL INIT ERROR: {e}")
            QMessageBox.critical(None, "Critical Error", f"Failed to initialize framework:\n{e}")
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
        
        # Apply Dark Theme Stylesheet
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; color: #ffffff; }
            QGroupBox { border: 1px solid #555; margin-top: 10px; font-weight: bold; border-radius: 4px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit, QComboBox, QTextEdit, QTableWidget { background-color: #353535; border: 1px solid #555; color: #fff; border-radius: 3px; padding: 4px;}
            QLineEdit:focus, QComboBox:focus { border: 1px solid #007acc; }
            QPushButton { background-color: #404040; border: 1px solid #555; padding: 6px 12px; border-radius: 3px; }
            QPushButton:hover { background-color: #505050; }
            QPushButton:pressed { background-color: #2d2d2d; }
            QProgressBar { border: 1px solid #555; text-align: center; border-radius: 3px; }
            QProgressBar::chunk { background-color: #007acc; }
            QTabWidget::pane { border: 1px solid #555; }
            QTabBar::tab { background: #353535; padding: 8px 20px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background: #404040; border-bottom: 2px solid #007acc; }
            QHeaderView::section { background-color: #404040; padding: 4px; border: none; }
        """)
        
        self.create_menu_bar()
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Build
        self.build_tab = QWidget()
        self.setup_build_tab()
        self.tabs.addTab(self.build_tab, "Build & Monitor")
        
        # Tab 2: Sources
        self.sources_tab = QWidget()
        self.setup_sources_tab()
        self.tabs.addTab(self.sources_tab, "Sources & Config")
        
        # Load Initial Data
        self.load_sources_to_table()
        self.refresh_targets()

    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("&File")
        
        import_action = QAction("Import Hardware Profile...", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self.import_hardware_profile)
        file_menu.addAction(import_action)
        
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        tools_menu = menubar.addMenu("&Tools")
        
        wizard_action = QAction("Create New Module...", self)
        wizard_action.setShortcut("Ctrl+N")
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
                QMessageBox.information(self, "Success", "Profile imported successfully.\nThe Wizard will now use this data.")
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
        else:
            self.log("Update-Check läuft bereits...")

    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        
        # --- Configuration Area ---
        controls = QGroupBox("Build Configuration")
        c_layout = QFormLayout(controls)
        
        # Row 1: Model
        model_layout = QHBoxLayout()
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Model Path or ID (e.g. ibm-granite/granite-3b-code-instruct)")
        model_layout.addWidget(self.model_name)
        
        self.hf_btn = QPushButton("🌐 Browse HF")
        self.hf_btn.setStyleSheet("background-color: #FFD21E; color: black; font-weight: bold;")
        self.hf_btn.setToolTip("Open Hugging Face Model Browser")
        self.hf_btn.clicked.connect(self.open_hf_browser)
        model_layout.addWidget(self.hf_btn)
        c_layout.addRow("Model Source:", model_layout)
        
        # Row 2: Target & Task
        target_layout = QHBoxLayout()
        
        self.target_combo = QComboBox()
        self.target_combo.setToolTip("Select the hardware target architecture")
        target_layout.addWidget(self.target_combo)
        
        target_layout.addWidget(QLabel("Task:"))
        self.task_combo = QComboBox()
        self.task_combo.addItems(["LLM", "VOICE", "VLM"])
        self.task_combo.setToolTip("Select the type of model task (optimizes build pipeline)")
        target_layout.addWidget(self.task_combo)
        
        c_layout.addRow("Target Hardware:", target_layout)
        
        # Row 3: Quantization & GPU
        quant_layout = QHBoxLayout()
        
        self.quant_combo = QComboBox()
        self.quant_combo.addItems(["Q4_K_M", "Q4_0", "Q5_K_M", "Q8_0", "INT4", "INT8", "FP16"])
        self.quant_combo.setToolTip("Select target quantization precision")
        quant_layout.addWidget(self.quant_combo)
        
        quant_layout.addSpacing(20)
        
        # GPU Support Checkbox
        self.chk_use_gpu = QCheckBox("Use GPU Acceleration")
        self.chk_use_gpu.setToolTip("Enable NVIDIA GPU Passthrough for build container (Requires NVIDIA Toolkit)")
        quant_layout.addWidget(self.chk_use_gpu)
        
        c_layout.addRow("Quantization:", quant_layout)
        
        # Row 4: Options
        opts_layout = QHBoxLayout()
        self.chk_auto_bench = QCheckBox("Run Benchmark after Build")
        self.chk_auto_bench.setChecked(True)
        opts_layout.addWidget(self.chk_auto_bench)
        
        self.chk_clean_build = QCheckBox("Clean Build (No Cache)")
        opts_layout.addWidget(self.chk_clean_build)
        
        c_layout.addRow("Options:", opts_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("🚀 Start Build Process")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold; font-size: 14px;")
        self.start_btn.clicked.connect(self.start_build)
        btn_layout.addWidget(self.start_btn)
        
        self.bench_btn = QPushButton("📊 Open Benchmark Tool")
        self.bench_btn.clicked.connect(self.open_benchmark_window)
        btn_layout.addWidget(self.bench_btn)
        
        c_layout.addRow("", btn_layout)
        
        layout.addWidget(controls)
        
        # --- Monitoring Area ---
        self.progress_group = QGroupBox("Build Progress")
        prog_layout = QVBoxLayout(self.progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas, Monospace; font-size: 12px;")
        prog_layout.addWidget(self.log_view)
        
        layout.addWidget(self.progress_group)

    def setup_sources_tab(self):
        layout = QVBoxLayout(self.sources_tab)
        
        toolbar = QHBoxLayout()
        btn_reload = QPushButton("🔄 Reload")
        btn_reload.clicked.connect(self.load_sources_to_table)
        toolbar.addWidget(btn_reload)
        
        btn_add = QPushButton("➕ Add Source")
        btn_add.clicked.connect(self.open_add_source_dialog)
        toolbar.addWidget(btn_add)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        self.sources_table = QTableWidget(0, 3)
        self.sources_table.setHorizontalHeaderLabels(["Category", "Key", "Repository URL"])
        self.sources_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sources_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.sources_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.sources_table.setAlternatingRowColors(True)
        layout.addWidget(self.sources_table)
        
        layout.addWidget(QLabel("Data loaded from configs/project_sources.yml"))

    def load_sources_to_table(self):
        try:
            self.framework_manager._load_extended_configuration()
            sources = self.framework_manager.config.source_repositories
            self.sources_table.setRowCount(0)
            for key, url in sources.items():
                row = self.sources_table.rowCount()
                self.sources_table.insertRow(row)
                
                # Flattened key "core.llama_cpp" splitting
                if '.' in key:
                    cat, name = key.split('.', 1)
                else:
                    cat, name = "general", key
                
                url_display = url
                if isinstance(url, dict):
                    url_display = url.get('url', str(url))
                
                self.sources_table.setItem(row, 0, QTableWidgetItem(cat))
                self.sources_table.setItem(row, 1, QTableWidgetItem(name))
                self.sources_table.setItem(row, 2, QTableWidgetItem(str(url_display)))
        except Exception as e:
            self.log(f"Error loading sources: {e}")

    def refresh_targets(self):
        """Loads available targets from the targets/ directory."""
        self.target_combo.clear()
        try:
            # This should ideally come from TargetManager via FrameworkManager
            # For now we list directories in targets/
            targets_dir = Path(self.framework_manager.config.targets_dir)
            if targets_dir.exists():
                targets = [d.name for d in targets_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]
                self.target_combo.addItems(sorted(targets))
            else:
                self.target_combo.addItem("No targets found")
        except Exception:
            self.target_combo.addItem("Error loading targets")

    def open_add_source_dialog(self):
        dialog = AddSourceDialog(self)
        if dialog.exec():
            self.load_sources_to_table()
            QMessageBox.information(self, "Success", "Source added. Please restart framework to apply changes fully.")

    def open_module_wizard(self):
        wizard = ModuleCreationWizard(Path(self.framework_manager.config.targets_dir), self)
        wizard.exec()
        self.refresh_targets() # Refresh dropdown after creation

    def run_image_audit(self):
        # This would trigger the Audit window or CLI command
        QMessageBox.information(self, "Audit", "Audit feature is available via CLI: 'llm-cli system audit'")

    def start_build(self):
        if not self.model_name.text(): 
            return QMessageBox.warning(self, "Validation Error", "Please specify a Model Name or Path.")
        
        # Build Config zusammenstellen
        cfg = {
            "model_name": self.model_name.text(),
            "target": self.target_combo.currentText(),
            "task": self.task_combo.currentText(),
            "quantization": self.quant_combo.currentText(),
            "auto_benchmark": self.chk_auto_bench.isChecked(),
            "use_gpu": self.chk_use_gpu.isChecked()
        }
        
        self.log(f"Initializing build sequence for {cfg['target']}...")
        self.log(f"Task: {cfg['task']} | Quant: {cfg['quantization']} | GPU: {cfg['use_gpu']}")
        
        self.start_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        
        # Start via DockerManager
        self.docker_manager.start_build(cfg)

    def on_build_output(self, bid, line):
        self.log_view.append(line)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def on_build_progress(self, bid, pct):
        self.progress_bar.setValue(pct)

    def on_build_completed(self, bid, success, path):
        self.start_btn.setEnabled(True)
        self.progress_bar.setValue(100 if success else 0)
        
        if success:
            self.log(f"✅ Build successfully completed!")
            self.log(f"Artifacts located at: {path}")
            
            if self.chk_auto_bench.isChecked():
                reply = QMessageBox.question(self, "Benchmark", "Build complete. Start Benchmark now?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.open_benchmark_window()
        else:
            self.log("❌ Build failed. Check logs for details.")
            QMessageBox.critical(self, "Build Failed", "The build process encountered an error.\nSee log output for details.")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {msg}")
