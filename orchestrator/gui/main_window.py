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
    QDialog, QInputDialog, QFileDialog, QCheckBox, QHeaderView,
    QMenu
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent
from PySide6.QtGui import QAction, QIcon

# Core & Utils Imports
from orchestrator.Core.docker_manager import DockerManager
from orchestrator.Core.framework import FrameworkConfig, FrameworkManager
from orchestrator.utils.updater import UpdateManager
from orchestrator.utils.logging import get_logger
from orchestrator.utils.localization import tr, get_instance as get_i18n

# GUI Module Imports
from orchestrator.gui.community_hub import CommunityHubWindow
from orchestrator.gui.huggingface_window import HuggingFaceWindow
from orchestrator.gui.dialogs import AddSourceDialog, LanguageSelectionDialog
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
    Supports Dynamic Language Switching.
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
            
            # Localization Connect
            get_i18n().language_changed.connect(self.retranslateUi)
            
        except Exception as e:
            print(f"CRITICAL INIT ERROR: {e}")
            # Fallback MsgBox if Qt is alive
            try:
                QMessageBox.critical(None, "Critical Error", f"Failed to initialize framework:\n{e}")
            except: pass
            sys.exit(1)
            
        self.init_ui()
        
        # Start Update Check
        self.update_worker = UpdateWorker(self.app_root)
        self.update_worker.update_available.connect(self.on_update_available)
        QTimer.singleShot(2000, self.update_worker.start)

    def on_update_available(self, available):
        if available:
            reply = QMessageBox.question(
                self, tr("menu.update"), 
                "A new version is available. Update now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.log("Starting update process...")
                updater = UpdateManager(self.app_root)
                updater.perform_update_and_restart()

    def init_ui(self):
        self.setWindowTitle(tr("app.title"))
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
        self.tabs.addTab(self.build_tab, tr("tab.build"))
        
        # Tab 2: Sources
        self.sources_tab = QWidget()
        self.setup_sources_tab()
        self.tabs.addTab(self.sources_tab, tr("tab.sources"))
        
        # Load Initial Data
        self.load_sources_to_table()
        self.refresh_targets()
        
        # Initial Translation
        self.retranslateUi()

    def create_menu_bar(self):
        self.menubar = self.menuBar()
        
        # File Menu
        self.file_menu = self.menubar.addMenu(tr("menu.file"))
        
        self.action_import = QAction(tr("menu.import_profile"), self)
        self.action_import.setShortcut("Ctrl+I")
        self.action_import.triggered.connect(self.import_hardware_profile)
        self.file_menu.addAction(self.action_import)
        
        self.file_menu.addSeparator()
        self.action_exit = QAction(tr("menu.exit"), self)
        self.action_exit.triggered.connect(self.close)
        self.file_menu.addAction(self.action_exit)

        # Tools Menu
        self.tools_menu = self.menubar.addMenu(tr("menu.tools"))
        
        self.action_wizard = QAction(tr("menu.create_module"), self)
        self.action_wizard.setShortcut("Ctrl+N")
        self.action_wizard.triggered.connect(self.open_module_wizard)
        self.tools_menu.addAction(self.action_wizard)
        
        self.action_audit = QAction(tr("menu.audit"), self)
        self.action_audit.triggered.connect(self.run_image_audit)
        self.tools_menu.addAction(self.action_audit)

        # Community Menu
        self.community_menu = self.menubar.addMenu(tr("menu.community"))
        self.action_hub = QAction(tr("menu.open_hub"), self)
        self.action_hub.triggered.connect(self.open_community_hub)
        self.community_menu.addAction(self.action_hub)
        
        self.action_update = QAction(tr("menu.update"), self)
        self.action_update.triggered.connect(self.check_for_updates_automatic)
        self.community_menu.addAction(self.action_update)
        
        # Language Menu
        self.lang_menu = self.menubar.addMenu(tr("menu.language"))
        action_en = QAction("🇺🇸 English", self)
        action_en.triggered.connect(lambda: self.switch_language("en"))
        self.lang_menu.addAction(action_en)
        
        action_de = QAction("🇩🇪 Deutsch", self)
        action_de.triggered.connect(lambda: self.switch_language("de"))
        self.lang_menu.addAction(action_de)

    def switch_language(self, lang):
        get_i18n().set_language(lang)
        # Save to config for next restart
        try:
            self.framework_manager.config_manager.set("language", lang)
        except: pass

    def retranslateUi(self):
        """Updates all texts in the UI dynamically."""
        self.setWindowTitle(tr("app.title"))
        
        # Menus
        self.file_menu.setTitle(tr("menu.file"))
        self.action_import.setText(tr("menu.import_profile"))
        self.action_exit.setText(tr("menu.exit"))
        
        self.tools_menu.setTitle(tr("menu.tools"))
        self.action_wizard.setText(tr("menu.create_module"))
        self.action_audit.setText(tr("menu.audit"))
        
        self.community_menu.setTitle(tr("menu.community"))
        self.action_hub.setText(tr("menu.open_hub"))
        self.action_update.setText(tr("menu.update"))
        
        self.lang_menu.setTitle(tr("menu.language"))
        
        # Tabs
        self.tabs.setTabText(0, tr("tab.build"))
        self.tabs.setTabText(1, tr("tab.sources"))
        
        # Build Tab
        self.grp_build.setTitle(tr("grp.build_config"))
        self.lbl_model.setText(tr("lbl.model"))
        self.hf_btn.setText(tr("btn.browse_hf"))
        self.lbl_target.setText(tr("lbl.target"))
        self.lbl_task.setText(tr("lbl.task"))
        self.lbl_quant.setText(tr("lbl.quant"))
        self.chk_use_gpu.setText(tr("chk.gpu"))
        self.chk_auto_bench.setText(tr("chk.autobench"))
        self.start_btn.setText(tr("btn.start"))
        self.bench_btn.setText(tr("btn.bench"))
        self.grp_progress.setTitle(tr("grp.progress"))

    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        
        # --- Configuration Area ---
        self.grp_build = QGroupBox(tr("grp.build_config"))
        c_layout = QFormLayout(self.grp_build)
        
        # Row 1: Model
        model_layout = QHBoxLayout()
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Model Path or ID (e.g. ibm-granite/granite-3b-code-instruct)")
        model_layout.addWidget(self.model_name)
        
        self.hf_btn = QPushButton(tr("btn.browse_hf"))
        self.hf_btn.setStyleSheet("background-color: #FFD21E; color: black; font-weight: bold;")
        self.hf_btn.clicked.connect(self.open_hf_browser)
        model_layout.addWidget(self.hf_btn)
        
        self.lbl_model = QLabel(tr("lbl.model"))
        c_layout.addRow(self.lbl_model, model_layout)
        
        # Row 2: Target & Task
        target_layout = QHBoxLayout()
        
        self.target_combo = QComboBox()
        target_layout.addWidget(self.target_combo)
        
        self.lbl_task = QLabel(tr("lbl.task"))
        target_layout.addWidget(self.lbl_task)
        self.task_combo = QComboBox()
        self.task_combo.addItems(["LLM", "VOICE", "VLM"])
        target_layout.addWidget(self.task_combo)
        
        self.lbl_target = QLabel(tr("lbl.target"))
        c_layout.addRow(self.lbl_target, target_layout)
        
        # Row 3: Quantization & GPU
        quant_layout = QHBoxLayout()
        
        self.quant_combo = QComboBox()
        self.quant_combo.addItems(["Q4_K_M", "Q4_0", "Q5_K_M", "Q8_0", "INT4", "INT8", "FP16"])
        quant_layout.addWidget(self.quant_combo)
        
        quant_layout.addSpacing(20)
        
        self.chk_use_gpu = QCheckBox(tr("chk.gpu"))
        self.chk_use_gpu.setToolTip("Enable NVIDIA GPU Passthrough")
        quant_layout.addWidget(self.chk_use_gpu)
        
        self.lbl_quant = QLabel(tr("lbl.quant"))
        c_layout.addRow(self.lbl_quant, quant_layout)
        
        # Row 4: Options
        opts_layout = QHBoxLayout()
        self.chk_auto_bench = QCheckBox(tr("chk.autobench"))
        self.chk_auto_bench.setChecked(True)
        opts_layout.addWidget(self.chk_auto_bench)
        
        c_layout.addRow("", opts_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton(tr("btn.start"))
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold; font-size: 14px;")
        self.start_btn.clicked.connect(self.start_build)
        btn_layout.addWidget(self.start_btn)
        
        self.bench_btn = QPushButton(tr("btn.bench"))
        self.bench_btn.clicked.connect(self.open_benchmark_window)
        btn_layout.addWidget(self.bench_btn)
        
        c_layout.addRow("", btn_layout)
        
        layout.addWidget(self.grp_build)
        
        # --- Monitoring Area ---
        self.grp_progress = QGroupBox(tr("grp.progress"))
        prog_layout = QVBoxLayout(self.grp_progress)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas, Monospace; font-size: 12px;")
        prog_layout.addWidget(self.log_view)
        
        layout.addWidget(self.grp_progress)

    def setup_sources_tab(self):
        layout = QVBoxLayout(self.sources_tab)
        toolbar = QHBoxLayout()
        btn = QPushButton("🔄 Reload"); btn.clicked.connect(self.load_sources_to_table); toolbar.addWidget(btn)
        btn2 = QPushButton("➕ Add"); btn2.clicked.connect(self.open_add_source_dialog); toolbar.addWidget(btn2)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        self.sources_table = QTableWidget(0, 3)
        self.sources_table.setHorizontalHeaderLabels(["Category", "Key", "Repository URL"])
        self.sources_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sources_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.sources_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.sources_table.setAlternatingRowColors(True)
        layout.addWidget(self.sources_table)

    def load_sources_to_table(self):
        try:
            self.framework_manager._load_extended_configuration()
            sources = self.framework_manager.config.source_repositories
            self.sources_table.setRowCount(0)
            for key, url in sources.items():
                row = self.sources_table.rowCount()
                self.sources_table.insertRow(row)
                
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
        self.target_combo.clear()
        try:
            targets_dir = Path(self.framework_manager.config.targets_dir)
            if targets_dir.exists():
                targets = [d.name for d in targets_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]
                self.target_combo.addItems(sorted(targets))
            else:
                self.target_combo.addItem("No targets found")
        except Exception:
            self.target_combo.addItem("Error")

    def import_hardware_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Profile", "", "Config (*.txt)")
        if path:
            try:
                cache_dir = self.app_root / "cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, cache_dir / "target_hardware_config.txt")
                self.log(f"Import: {path}")
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

    def open_add_source_dialog(self):
        if AddSourceDialog(self).exec(): self.load_sources_to_table()

    def open_module_wizard(self):
        ModuleCreationWizard(Path(self.framework_manager.config.targets_dir), self).exec()
        self.refresh_targets()

    def run_image_audit(self):
        QMessageBox.information(self, "Audit", "Audit feature is available via CLI: 'llm-cli system audit'")

    def check_for_updates_automatic(self):
        if not self.update_worker.isRunning():
            self.log("Checking for updates...")
            self.update_worker.start()

    def start_build(self):
        if not self.model_name.text(): 
            return QMessageBox.warning(self, tr("status.error"), "Model name required")
        
        cfg = {
            "model_name": self.model_name.text(),
            "target": self.target_combo.currentText(),
            "task": self.task_combo.currentText(),
            "quantization": self.quant_combo.currentText(),
            "auto_benchmark": self.chk_auto_bench.isChecked(),
            "use_gpu": self.chk_use_gpu.isChecked()
        }
        
        self.log(f"Building {cfg['target']} ({cfg['task']}) Quant: {cfg['quantization']} GPU: {cfg['use_gpu']}")
        self.start_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        
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
            self.log(f"✅ {tr('msg.success')}! Output: {path}")
            if self.chk_auto_bench.isChecked():
                reply = QMessageBox.question(self, "Benchmark", "Build complete. Start Benchmark?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.open_benchmark_window()
        else:
            self.log(f"❌ {tr('msg.failed')}")
            QMessageBox.critical(self, tr("msg.failed"), "Build failed. Check logs.")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {msg}")
