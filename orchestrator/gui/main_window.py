#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Window GUI
DIREKTIVE: Goldstandard, MVC-Pattern, Separation of Concerns.

Updates v1.5.0:
- Added Output Format Selection (GGUF, RKNN, ONNX, etc.)
- Connected Format selection to Build Configuration
"""

import sys
import os
import time
import socket
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List

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
from orchestrator.Core.dataset_manager import DatasetManager
from orchestrator.utils.updater import UpdateManager
from orchestrator.utils.logging import get_logger
from orchestrator.utils.localization import tr, get_instance as get_i18n

# GUI Module Imports
from orchestrator.gui.community_hub import CommunityHubWindow
from orchestrator.gui.huggingface_window import HuggingFaceWindow
from orchestrator.gui.dialogs import AddSourceDialog, LanguageSelectionDialog, DatasetReviewDialog, AIConfigurationDialog
from orchestrator.gui.wizards import ModuleCreationWizard
from orchestrator.gui.benchmark_window import BenchmarkWindow

class UpdateWorker(QThread):
    update_available = Signal(bool)
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
                connected = True; break
            except OSError: time.sleep(1)
        if not connected: return
        try:
            updater = UpdateManager(self.app_root)
            if updater.check_for_updates(): self.update_available.emit(True)
        except: pass
    def stop(self): self._is_running = False

class DatasetGenWorker(QThread):
    """Worker to generate synthetic data via Ditto without freezing GUI."""
    finished = Signal(list)
    error = Signal(str)
    
    def __init__(self, manager, domain, count=50):
        super().__init__()
        self.manager = manager
        self.domain = domain
        self.count = count
        
    def run(self):
        try:
            # Calls Ditto via DatasetManager
            data = self.manager.generate_synthetic_dataset(self.domain, self.count)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))

class MainOrchestrator(QMainWindow):
    """
    Main GUI Application Window.
    Orchestrates all UI components and connects to Core Logic.
    """
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
            if not self.framework_manager.initialize(): raise RuntimeError("Framework Manager failed")
            
            self.docker_manager = DockerManager()
            self.docker_manager.initialize(self.framework_manager)
            
            # New: Dataset Manager for Smart Calibration
            self.dataset_manager = DatasetManager(self.framework_manager)
            
            self.docker_manager.build_output.connect(self.on_build_output)
            self.docker_manager.build_progress.connect(self.on_build_progress)
            self.docker_manager.build_completed.connect(self.on_build_completed)
            # New: Sidecar Status (v1.5.0)
            self.docker_manager.sidecar_status.connect(self.on_sidecar_status)
            
            get_i18n().language_changed.connect(self.retranslateUi)
            
        except Exception as e:
            print(f"CRITICAL INIT ERROR: {e}")
            sys.exit(1)
            
        self.init_ui()
        self.update_worker = UpdateWorker(self.app_root)
        self.update_worker.update_available.connect(self.on_update_available)
        QTimer.singleShot(2000, self.update_worker.start)

    def on_update_available(self, available):
        if available:
            if QMessageBox.question(self, tr("menu.update"), "Update available. Update now?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                UpdateManager(self.app_root).perform_update_and_restart()

    def init_ui(self):
        self.setWindowTitle(tr("app.title"))
        self.setMinimumSize(1200, 850)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; color: #ffffff; }
            QGroupBox { border: 1px solid #555; margin-top: 10px; font-weight: bold; border-radius: 4px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit, QComboBox, QTextEdit, QTableWidget { background-color: #353535; border: 1px solid #555; color: #fff; border-radius: 3px; padding: 4px;}
            QLineEdit:focus, QComboBox:focus { border: 1px solid #007acc; }
            QPushButton { background-color: #404040; border: 1px solid #555; padding: 6px 12px; border-radius: 3px; }
            QPushButton:hover { background-color: #505050; }
            QProgressBar { border: 1px solid #555; text-align: center; border-radius: 3px; }
            QProgressBar::chunk { background-color: #007acc; }
            QTabWidget::pane { border: 1px solid #555; }
            QTabBar::tab { background: #353535; padding: 8px 20px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background: #404040; border-bottom: 2px solid #007acc; }
            QHeaderView::section { background-color: #404040; padding: 4px; border: none; }
        """)
        self.create_menu_bar()
        central = QWidget(); self.setCentralWidget(central); main_layout = QHBoxLayout(central)
        self.tabs = QTabWidget(); main_layout.addWidget(self.tabs)
        self.build_tab = QWidget(); self.setup_build_tab(); self.tabs.addTab(self.build_tab, tr("tab.build"))
        self.sources_tab = QWidget(); self.setup_sources_tab(); self.tabs.addTab(self.sources_tab, tr("tab.sources"))
        self.load_sources_to_table(); self.refresh_targets(); self.retranslateUi()

    def create_menu_bar(self):
        self.menubar = self.menuBar()
        self.file_menu = self.menubar.addMenu(tr("menu.file"))
        act_imp = QAction(tr("menu.import_profile"), self); act_imp.triggered.connect(self.import_hardware_profile); self.file_menu.addAction(act_imp)
        self.file_menu.addSeparator(); act_ex = QAction(tr("menu.exit"), self); act_ex.triggered.connect(self.close); self.file_menu.addAction(act_ex)
        self.tools_menu = self.menubar.addMenu(tr("menu.tools"))
        act_wiz = QAction(tr("menu.create_module"), self); act_wiz.triggered.connect(self.open_module_wizard); self.tools_menu.addAction(act_wiz)
        act_aud = QAction(tr("menu.audit"), self); act_aud.triggered.connect(self.run_image_audit); self.tools_menu.addAction(act_aud)
        
        # New AI Config Action
        act_ai = QAction(tr("wiz.btn.config_ai"), self); act_ai.triggered.connect(self.open_ai_config); self.tools_menu.addAction(act_ai)
        
        self.comm_menu = self.menubar.addMenu(tr("menu.community"))
        act_hub = QAction(tr("menu.open_hub"), self); act_hub.triggered.connect(self.open_community_hub); self.comm_menu.addAction(act_hub)
        act_upd = QAction(tr("menu.update"), self); act_upd.triggered.connect(self.check_for_updates_automatic); self.comm_menu.addAction(act_upd)
        self.lang_menu = self.menubar.addMenu(tr("menu.language"))
        self.lang_menu.addAction("🇺🇸 English", lambda: self.switch_language("en")); self.lang_menu.addAction("🇩🇪 Deutsch", lambda: self.switch_language("de"))

    def switch_language(self, lang):
        get_i18n().set_language(lang)
        try: self.framework_manager.config_manager.set("language", lang)
        except: pass

    def retranslateUi(self):
        self.setWindowTitle(tr("app.title"))
        self.file_menu.setTitle(tr("menu.file")); self.tools_menu.setTitle(tr("menu.tools")); self.comm_menu.setTitle(tr("menu.community")); self.lang_menu.setTitle(tr("menu.language"))
        self.tabs.setTabText(0, tr("tab.build")); self.tabs.setTabText(1, tr("tab.sources"))
        self.grp_build.setTitle(tr("grp.build_config")); self.lbl_model.setText(tr("lbl.model")); self.hf_btn.setText(tr("btn.browse_hf"))
        self.lbl_target.setText(tr("lbl.target")); self.lbl_task.setText(tr("lbl.task")); self.lbl_quant.setText(tr("lbl.quant"))
        self.chk_use_gpu.setText(tr("chk.gpu")); self.chk_auto_bench.setText(tr("chk.autobench"))
        self.start_btn.setText(tr("btn.start")); self.bench_btn.setText(tr("btn.bench")); self.grp_progress.setTitle(tr("grp.progress"))

    def setup_build_tab(self):
        layout = QVBoxLayout(self.build_tab)
        self.grp_build = QGroupBox(tr("grp.build_config")); c_layout = QFormLayout(self.grp_build)
        
        m_layout = QHBoxLayout()
        self.model_name = QLineEdit(); self.model_name.setPlaceholderText("Model Path or ID")
        m_layout.addWidget(self.model_name)
        self.hf_btn = QPushButton(tr("btn.browse_hf")); self.hf_btn.clicked.connect(self.open_hf_browser); m_layout.addWidget(self.hf_btn)
        self.lbl_model = QLabel(tr("lbl.model")); c_layout.addRow(self.lbl_model, m_layout)
        
        t_layout = QHBoxLayout()
        self.target_combo = QComboBox(); t_layout.addWidget(self.target_combo)
        self.lbl_task = QLabel(tr("lbl.task")); t_layout.addWidget(self.lbl_task)
        self.task_combo = QComboBox(); self.task_combo.addItems(["LLM", "VOICE", "VLM"]); t_layout.addWidget(self.task_combo)
        self.lbl_target = QLabel(tr("lbl.target")); c_layout.addRow(self.lbl_target, t_layout)
        
        # New Output Format Selection (v1.5.0 Update)
        f_layout = QHBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "GGUF (Universal)", 
            "RKNN (Rockchip NPU)", 
            "ONNX (Universal)", 
            "TensorRT (NVIDIA)", 
            "TFLite (Mobile/Pi)", 
            "OpenVINO (Intel)", 
            "CoreML (Apple)",
            "NCNN (Mobile)"
        ])
        f_layout.addWidget(self.format_combo)
        c_layout.addRow("Format:", f_layout)

        q_layout = QHBoxLayout()
        self.quant_combo = QComboBox()
        self.quant_combo.addItems(["FP16 (Original)", "INT8", "INT4", "Q4_K_M", "Q8_0", "W8A8 (NPU)", "W4A16 (NPU)"])
        q_layout.addWidget(self.quant_combo); q_layout.addSpacing(20)
        self.chk_use_gpu = QCheckBox(tr("chk.gpu")); q_layout.addWidget(self.chk_use_gpu)
        self.lbl_quant = QLabel(tr("lbl.quant")); c_layout.addRow(self.lbl_quant, q_layout)
        
        o_layout = QHBoxLayout()
        self.chk_auto_bench = QCheckBox(tr("chk.autobench")); self.chk_auto_bench.setChecked(True); o_layout.addWidget(self.chk_auto_bench)
        c_layout.addRow("", o_layout)
        
        b_layout = QHBoxLayout()
        self.start_btn = QPushButton(tr("btn.start")); self.start_btn.clicked.connect(self.start_build); b_layout.addWidget(self.start_btn)
        self.bench_btn = QPushButton(tr("btn.bench")); self.bench_btn.clicked.connect(self.open_benchmark_window); b_layout.addWidget(self.bench_btn)
        c_layout.addRow("", b_layout)
        layout.addWidget(self.grp_build)
        
        self.grp_progress = QGroupBox(tr("grp.progress")); p_layout = QVBoxLayout(self.grp_progress)
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); p_layout.addWidget(self.progress_bar)
        self.log_view = QTextEdit(); self.log_view.setReadOnly(True); p_layout.addWidget(self.log_view)
        layout.addWidget(self.grp_progress)

    def setup_sources_tab(self):
        layout = QVBoxLayout(self.sources_tab); tb = QHBoxLayout()
        btn_r = QPushButton("Reload"); btn_r.clicked.connect(self.load_sources_to_table); tb.addWidget(btn_r)
        btn_a = QPushButton("Add"); btn_a.clicked.connect(self.open_add_source_dialog); tb.addWidget(btn_a)
        tb.addStretch(); layout.addLayout(tb)
        self.sources_table = QTableWidget(0, 3); layout.addWidget(self.sources_table)

    def load_sources_to_table(self):
        try:
            self.framework_manager._load_extended_configuration()
            src = self.framework_manager.config.source_repositories
            self.sources_table.setRowCount(0)
            for k, v in src.items():
                r = self.sources_table.rowCount(); self.sources_table.insertRow(r)
                self.sources_table.setItem(r, 0, QTableWidgetItem("Src"))
                self.sources_table.setItem(r, 1, QTableWidgetItem(k))
                self.sources_table.setItem(r, 2, QTableWidgetItem(str(v)))
        except: pass

    def refresh_targets(self):
        self.target_combo.clear()
        try:
            d = Path(self.framework_manager.config.targets_dir)
            if d.exists(): self.target_combo.addItems(sorted([x.name for x in d.iterdir() if x.is_dir() and not x.name.startswith('_')]))
        except: pass

    def import_hardware_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import", "", "Config (*.txt)")
        if path: shutil.copy2(path, self.app_root / "cache" / "target_hardware_config.txt")

    def open_community_hub(self): CommunityHubWindow(self.framework_manager, self).show()
    def open_hf_browser(self): HuggingFaceWindow(self.framework_manager, self).show()
    def open_benchmark_window(self): BenchmarkWindow(self.framework_manager, self).show()
    def open_add_source_dialog(self): AddSourceDialog(self).exec(); self.load_sources_to_table()
    def open_module_wizard(self): ModuleCreationWizard(Path(self.framework_manager.config.targets_dir), self).exec(); self.refresh_targets()
    def run_image_audit(self): QMessageBox.information(self, "Info", "Audit via CLI: llm-cli system audit")
    def check_for_updates_automatic(self): self.update_worker.start()
    
    def open_ai_config(self):
        """Open AI Configuration Dialog (Ditto / RAG)"""
        dlg = AIConfigurationDialog(self)
        # Pre-Load current settings if possible
        if dlg.exec() == QDialog.Accepted:
            cfg = dlg.get_config()
            # Save relevant parts to config manager
            self.framework_manager.config_manager.set("enable_rag_knowledge", cfg.get("enable_rag_knowledge", False))
            self.framework_manager.config.enable_rag_knowledge = cfg.get("enable_rag_knowledge", False)
            
            # Persist user config
            self.framework_manager.config_manager.save_user_config()
            
            # Start/Stop RAG Service immediately if changed
            if self.docker_manager:
                self.docker_manager.ensure_qdrant_service()

    def start_build(self):
        """Handles pre-build checks (Dataset) and triggers DockerManager."""
        model_path = self.model_name.text()
        if not model_path: return QMessageBox.warning(self, tr("status.error"), "Model required")
        
        quant = self.quant_combo.currentText()
        
        # --- Smart Dataset Check ---
        needs_ds = "INT" in quant or "W8" in quant or "W4" in quant
        ds_path = None
        
        if needs_ds:
            # 1. Auto-Detect
            if os.path.exists(model_path):
                check = os.path.join(model_path, "dataset.json")
                if os.path.exists(check):
                    ds_path = check
                    self.log(f"Auto-Detected Dataset: {ds_path}")
            
            # 2. Prompt User if missing
            if not ds_path:
                ans = QMessageBox.question(self, "Calibration Data Missing", 
                                           f"Quantization '{quant}' requires a dataset.\n"
                                           "Generate via AI (Ditto) or Select File?", 
                                           QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                
                if ans == QMessageBox.Yes: # Generate AI
                    self.start_ai_dataset_gen(model_path)
                    return # Stop here, resume in callback
                elif ans == QMessageBox.No: # Manual Select
                    f, _ = QFileDialog.getOpenFileName(self, "Select Dataset", "", "JSON (*.json);;TXT (*.txt)")
                    if f: ds_path = f
                else:
                    return # Cancel
        
        self._trigger_docker_build(model_path, quant, ds_path)

    def start_ai_dataset_gen(self, model_path):
        """Starts the background worker for Ditto dataset generation."""
        domain = self.dataset_manager.detect_domain(model_path)
        
        # Fallback if domain unknown
        if not domain:
             d, ok = QInputDialog.getItem(self, "Select Domain", "Could not detect model domain.\nPlease select:", 
                                          ["code", "chat", "medical", "legal", "general_text"], 0, False)
             if ok: domain = d
             else: return

        self.log(f"Generating synthetic dataset for '{domain}' via Ditto...")
        self.set_controls_enabled(False)
        
        self.ds_worker = DatasetGenWorker(self.dataset_manager, domain)
        self.ds_worker.finished.connect(lambda data: self.on_dataset_generated(data, model_path))
        self.ds_worker.error.connect(self.on_dataset_error)
        self.ds_worker.start()

    def on_dataset_generated(self, data, model_path):
        self.set_controls_enabled(True)
        # Review Dialog (HitL)
        dlg = DatasetReviewDialog(data, "AI Generated Data", self)
        if dlg.exec():
            # Save
            save_path = Path(model_path) / "dataset.json" if os.path.exists(model_path) else Path(self.framework_manager.config.cache_dir) / "dataset.json"
            if self.dataset_manager.save_dataset(dlg.final_data, save_path):
                self.log(f"Dataset saved to {save_path}")
                # Resume Build
                self._trigger_docker_build(model_path, self.quant_combo.currentText(), str(save_path))
            else:
                QMessageBox.critical(self, "Error", "Failed to save dataset.")

    def on_dataset_error(self, err):
        self.set_controls_enabled(True)
        QMessageBox.critical(self, "AI Error", str(err))

    def _trigger_docker_build(self, model, quant, ds_path):
        # Extract Format (GGUF, RKNN...) from Combo string (e.g. "GGUF (Universal)" -> "GGUF")
        raw_format = self.format_combo.currentText()
        target_format = raw_format.split()[0].strip() # Takes "GGUF" from "GGUF (Universal)"

        cfg = {
            "model_name": model,
            "target": self.target_combo.currentText(),
            "task": self.task_combo.currentText(),
            "quantization": quant,
            "format": target_format, # NEW Field
            "auto_benchmark": self.chk_auto_bench.isChecked(),
            "use_gpu": self.chk_use_gpu.isChecked(),
            "dataset_path": ds_path
        }
        self.log(f"Build Start: {cfg['target']} [{cfg['format']} / {cfg['quantization']}]")
        self.set_controls_enabled(False)
        self.docker_manager.start_build(cfg)

    def set_controls_enabled(self, enabled):
        self.start_btn.setEnabled(enabled)
        self.grp_build.setEnabled(enabled)

    def on_build_output(self, bid, line): self.log_view.append(line); self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
    def on_build_progress(self, bid, pct): self.progress_bar.setValue(pct)
    def on_build_completed(self, bid, success, p): 
        self.set_controls_enabled(True)
        self.progress_bar.setValue(100 if success else 0)
        self.log(f"{'✅' if success else '❌'} Done. Artifact: {p}")
    
    def on_sidecar_status(self, service, status):
        self.log(f"Sidecar [{service}]: {status}")

    def log(self, msg): self.log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
