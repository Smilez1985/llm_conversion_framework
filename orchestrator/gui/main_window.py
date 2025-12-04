#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Window GUI
DIREKTIVE: Goldstandard, MVC-Pattern, Separation of Concerns.

Updates v2.0.0:
- Integrated Self-Healing Workflow (HealingDialog + HealingWorker).
- Added logic to execute AI-proposed fixes (Local & Remote via SSH).
- Maintained Ditto Chat and v1.7 features.
"""

import sys
import os
import time
import socket
import logging
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTextEdit, QProgressBar,
    QGroupBox, QFormLayout, QLineEdit, QComboBox, 
    QMessageBox, QTableWidget, QTableWidgetItem,
    QDialog, QInputDialog, QFileDialog, QCheckBox, QHeaderView,
    QMenu, QDockWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent
from PySide6.QtGui import QAction, QIcon

# Core & Utils Imports
from orchestrator.Core.docker_manager import DockerManager
from orchestrator.Core.framework import FrameworkConfig, FrameworkManager
from orchestrator.Core.dataset_manager import DatasetManager
from orchestrator.Core.deployment_manager import DeploymentManager
from orchestrator.utils.updater import UpdateManager
from orchestrator.utils.logging import get_logger
from orchestrator.utils.localization import tr, get_instance as get_i18n

# GUI Module Imports
from orchestrator.gui.community_hub import CommunityHubWindow
from orchestrator.gui.huggingface_window import HuggingFaceWindow
from orchestrator.gui.dialogs import (
    AddSourceDialog, LanguageSelectionDialog, DatasetReviewDialog, 
    AIConfigurationDialog, DeploymentDialog, URLInputDialog, HealingDialog
)
from orchestrator.gui.wizards import ModuleCreationWizard
from orchestrator.gui.benchmark_window import BenchmarkWindow
from orchestrator.gui.chat_window import ChatWindow

# Optional: Ditto Manager for Chat
try:
    from orchestrator.Core.ditto_manager import DittoCoder
except ImportError:
    DittoCoder = None

# SSH Support for Healing
try:
    import paramiko
except ImportError:
    paramiko = None

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
    finished = Signal(list)
    error = Signal(str)
    def __init__(self, manager, domain, count=50):
        super().__init__()
        self.manager = manager
        self.domain = domain
        self.count = count
    def run(self):
        try:
            data = self.manager.generate_synthetic_dataset(self.domain, self.count)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))

class DeploymentWorker(QThread):
    log_signal = Signal(str)
    finished = Signal(bool)
    def __init__(self, manager, artifact, creds):
        super().__init__()
        self.manager = manager
        self.artifact = artifact
        self.creds = creds
    def run(self):
        try:
            self.log_signal.emit(f"Starting deployment to {self.creds['ip']}...")
            success = self.manager.deploy_artifact(
                self.artifact, self.creds['ip'], self.creds['user'],
                self.creds['password'], self.creds['path']
            )
            if success: self.log_signal.emit("✅ Deployment successful!")
            else: self.log_signal.emit("❌ Deployment failed. Check logs.")
            self.finished.emit(success)
        except Exception as e:
            self.log_signal.emit(f"Deployment Error: {e}")
            self.finished.emit(False)

# --- NEW v2.0: HEALING WORKER ---
class HealingWorker(QThread):
    """
    Executes the fix proposed by Ditto (Self-Healing).
    Supports Local (Subprocess) and Remote (SSH) fixes.
    """
    log_signal = Signal(str)
    finished = Signal(bool)
    
    def __init__(self, proposal, creds: Dict = None):
        super().__init__()
        self.proposal = proposal
        self.creds = creds # Only needed for remote
        
    def run(self):
        cmd = self.proposal.fix_command
        
        try:
            if self.proposal.is_remote_fix:
                self._run_remote(cmd)
            else:
                self._run_local(cmd)
        except Exception as e:
            self.log_signal.emit(f"❌ Healing Failed: {e}")
            self.finished.emit(False)

    def _run_local(self, cmd):
        self.log_signal.emit(f"🚑 Applying Local Fix: {cmd}")
        # Security Note: cmd comes from AI, user approved it in dialog.
        process = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in process.stdout:
            self.log_signal.emit(f"[FIX] {line.strip()}")
        process.wait()
        
        if process.returncode == 0:
            self.log_signal.emit("✅ Fix applied successfully.")
            self.finished.emit(True)
        else:
            self.log_signal.emit(f"❌ Fix failed with code {process.returncode}")
            self.finished.emit(False)

    def _run_remote(self, cmd):
        if not self.creds or not paramiko:
            raise RuntimeError("SSH Credentials missing or Paramiko not installed.")
            
        self.log_signal.emit(f"🚑 Applying Remote Fix on {self.creds['ip']}: {cmd}")
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.creds['ip'], username=self.creds['user'], password=self.creds['password'], timeout=10)
        
        stdin, stdout, stderr = ssh.exec_command(f"sudo {cmd}" if "sudo" not in cmd else cmd, get_pty=True)
        
        # Simple password injection for sudo if needed (Naive implementation)
        # Ideally user should provide passwordless sudo or we assume root
        if self.creds['password']:
            stdin.write(self.creds['password'] + "\n")
            stdin.flush()
        
        for line in stdout:
            self.log_signal.emit(f"[REMOTE] {line.strip()}")
            
        exit_status = stdout.channel.recv_exit_status()
        ssh.close()
        
        if exit_status == 0:
            self.log_signal.emit("✅ Remote fix applied.")
            self.finished.emit(True)
        else:
            self.log_signal.emit(f"❌ Remote fix failed (Exit {exit_status})")
            self.finished.emit(False)

class MainOrchestrator(QMainWindow):
    """
    Main GUI Application Window.
    Orchestrates all UI components and connects to Core Logic.
    """
    def __init__(self, app_root: Path):
        super().__init__()
        self.app_root = app_root
        self.logger = get_logger(__name__)
        self.last_artifact_path = None 
        
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
            
            self.dataset_manager = DatasetManager(self.framework_manager)
            self.deployment_manager = DeploymentManager(self.framework_manager)
            
            # Initialize Ditto Manager
            self.ditto_manager = None
            if DittoCoder:
                try:
                    self.ditto_manager = DittoCoder(
                        config_manager=self.framework_manager.config,
                        framework_manager=self.framework_manager
                    )
                except Exception as e:
                    self.logger.warning(f"Could not init Ditto for Chat: {e}")

            # Connect Signals
            self.docker_manager.build_output.connect(self.on_build_output)
            self.docker_manager.build_progress.connect(self.on_build_progress)
            self.docker_manager.build_completed.connect(self.on_build_completed)
            self.docker_manager.sidecar_status.connect(self.on_sidecar_status)
            self.docker_manager.build_stats.connect(self.on_build_stats)
            
            # NEW v2.0: Connect Self-Healing Signal
            self.docker_manager.healing_requested.connect(self.on_healing_requested)
            
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
        self.setMinimumSize(1300, 850)
        
        logo_path = self.app_root / "assets" / "logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))
        else:
            logo_ico = self.app_root / "assets" / "icon.ico"
            if logo_ico.exists():
                self.setWindowIcon(QIcon(str(logo_ico)))

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
            QDockWidget::title { background: #353535; padding-left: 5px; }
        """)
        self.create_menu_bar()
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        self.build_tab = QWidget(); self.setup_build_tab(); self.tabs.addTab(self.build_tab, tr("tab.build"))
        self.sources_tab = QWidget(); self.setup_sources_tab(); self.tabs.addTab(self.sources_tab, tr("tab.sources"))
        
        self.load_sources_to_table()
        self.refresh_targets()
        
        self.create_chat_dock()
        self.retranslateUi()

    def create_chat_dock(self):
        self.chat_dock = QDockWidget("Ditto AI Assistant", self)
        self.chat_dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.chat_window = ChatWindow(self.ditto_manager, self)
        self.chat_dock.setWidget(self.chat_window)
        self.addDockWidget(Qt.RightDockWidgetArea, self.chat_dock)
        
        self.act_chat_toggle = QAction("Show/Hide AI Chat", self)
        self.act_chat_toggle.setCheckable(True)
        self.act_chat_toggle.setChecked(True)
        self.act_chat_toggle.triggered.connect(self.toggle_chat_dock)
        self.tools_menu.addAction(self.act_chat_toggle)

    def toggle_chat_dock(self):
        if self.chat_dock.isVisible():
            self.chat_dock.hide()
            self.act_chat_toggle.setChecked(False)
        else:
            self.chat_dock.show()
            self.act_chat_toggle.setChecked(True)

    def create_menu_bar(self):
        self.menubar = self.menuBar()
        self.file_menu = self.menubar.addMenu(tr("menu.file"))
        act_imp = QAction(tr("menu.import_profile"), self); act_imp.triggered.connect(self.import_hardware_profile); self.file_menu.addAction(act_imp)
        self.file_menu.addSeparator(); act_ex = QAction(tr("menu.exit"), self); act_ex.triggered.connect(self.close); self.file_menu.addAction(act_ex)
        
        self.tools_menu = self.menubar.addMenu(tr("menu.tools"))
        act_wiz = QAction(tr("menu.create_module"), self); act_wiz.triggered.connect(self.open_module_wizard); self.tools_menu.addAction(act_wiz)
        act_aud = QAction(tr("menu.audit"), self); act_aud.triggered.connect(self.run_image_audit); self.tools_menu.addAction(act_aud)
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
        
        f_layout = QHBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "GGUF (Universal)", "RKNN (Rockchip NPU)", "ONNX (Universal)", "TensorRT (NVIDIA)", 
            "TFLite (Mobile/Pi)", "OpenVINO (Intel)", "CoreML (Apple)", "NCNN (Mobile)"
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
        
        self.deploy_btn = QPushButton("Deploy to Target")
        self.deploy_btn.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        self.deploy_btn.clicked.connect(self.open_deployment_dialog)
        self.deploy_btn.setEnabled(False) 
        b_layout.addWidget(self.deploy_btn)
        
        c_layout.addRow("", b_layout)
        layout.addWidget(self.grp_build)
        
        self.grp_progress = QGroupBox(tr("grp.progress")); p_layout = QVBoxLayout(self.grp_progress)
        
        p_layout.addWidget(QLabel("Overall Progress:"))
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); p_layout.addWidget(self.progress_bar)
        
        stats_layout = QHBoxLayout()
        self.lbl_cpu = QLabel("CPU: 0%")
        self.cpu_bar = QProgressBar(); self.cpu_bar.setRange(0, 100); self.cpu_bar.setTextVisible(False)
        self.cpu_bar.setStyleSheet("QProgressBar::chunk { background-color: #d9534f; }") 
        self.lbl_ram = QLabel("RAM: 0MB")
        self.ram_bar = QProgressBar(); self.ram_bar.setRange(0, 100); self.ram_bar.setTextVisible(False)
        self.ram_bar.setStyleSheet("QProgressBar::chunk { background-color: #5bc0de; }") 
        stats_layout.addWidget(self.lbl_cpu); stats_layout.addWidget(self.cpu_bar)
        stats_layout.addSpacing(20)
        stats_layout.addWidget(self.lbl_ram); stats_layout.addWidget(self.ram_bar)
        p_layout.addLayout(stats_layout)
        
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
        dlg = AIConfigurationDialog(self)
        if dlg.exec() == QDialog.Accepted:
            cfg = dlg.get_config()
            self.framework_manager.config_manager.set("enable_rag_knowledge", cfg.get("enable_rag_knowledge", False))
            self.framework_manager.config.enable_rag_knowledge = cfg.get("enable_rag_knowledge", False)
            self.framework_manager.config_manager.save_user_config()
            if self.docker_manager:
                self.docker_manager.ensure_qdrant_service()
            if self.ditto_manager:
                self.ditto_manager.config = self.framework_manager.config

    def open_deployment_dialog(self):
        if not self.last_artifact_path or not os.path.exists(self.last_artifact_path):
            QMessageBox.warning(self, "Deployment", "No valid artifact found. Please build a model first.")
            return
            
        dlg = DeploymentDialog(self)
        if dlg.exec() == QDialog.Accepted:
            creds = dlg.get_credentials()
            self.log(f"Initializing Deployment to {creds['ip']}...")
            self.set_controls_enabled(False)
            
            self.deploy_worker = DeploymentWorker(self.deployment_manager, self.last_artifact_path, creds)
            self.deploy_worker.log_signal.connect(self.log)
            self.deploy_worker.finished.connect(self.on_deployment_finished)
            self.deploy_worker.start()

    def on_deployment_finished(self, success):
        self.set_controls_enabled(True)
        if success:
            QMessageBox.information(self, "Deployment", "Successfully deployed to target device.")
        else:
            QMessageBox.critical(self, "Deployment Failed", "Deployment failed. See logs for details.")

    # --- NEW v2.0: Self-Healing Handler ---
    def on_healing_requested(self, proposal):
        """Slots called when DockerManager detects a build error and has a fix."""
        self.log(f"🚑 Healing Proposed: {proposal.error_summary}")
        
        dlg = HealingDialog(proposal, self)
        if dlg.exec() == QDialog.Accepted:
            self.log("Applying Fix...")
            
            # Credentials for Remote Fix (if needed)
            creds = None
            if proposal.is_remote_fix:
                # Reuse deployment dialog to ask for credentials if not cached or needed
                # For v2.0 MVP we assume the user must provide them or we use defaults
                dep_dlg = DeploymentDialog(self)
                if dep_dlg.exec() == QDialog.Accepted:
                    creds = dep_dlg.get_credentials()
                else:
                    self.log("Healing cancelled (Credentials missing).")
                    return
            
            # Start Healing Worker
            self.healing_worker = HealingWorker(proposal, creds)
            self.healing_worker.log_signal.connect(self.log)
            self.healing_worker.finished.connect(lambda success: self.log("Healing Complete." if success else "Healing Failed."))
            self.healing_worker.start()
        else:
            self.log("Healing ignored by user.")

    def start_build(self):
        model_path = self.model_name.text()
        if not model_path: return QMessageBox.warning(self, tr("status.error"), "Model required")
        
        quant = self.quant_combo.currentText()
        needs_ds = "INT" in quant or "W8" in quant or "W4" in quant
        ds_path = None
        
        if needs_ds:
            if os.path.exists(model_path):
                check = os.path.join(model_path, "dataset.json")
                if os.path.exists(check):
                    ds_path = check
                    self.log(f"Auto-Detected Dataset: {ds_path}")
            
            if not ds_path:
                ans = QMessageBox.question(self, "Calibration Data Missing", 
                                           f"Quantization '{quant}' requires a dataset.\n"
                                           "Generate via AI (Ditto) or Select File?", 
                                           QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                
                if ans == QMessageBox.Yes:
                    self.start_ai_dataset_gen(model_path)
                    return
                elif ans == QMessageBox.No:
                    f, _ = QFileDialog.getOpenFileName(self, "Select Dataset", "", "JSON (*.json);;TXT (*.txt)")
                    if f: ds_path = f
                else:
                    return
        
        self._trigger_docker_build(model_path, quant, ds_path)

    def start_ai_dataset_gen(self, model_path):
        domain = self.dataset_manager.detect_domain(model_path)
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
        dlg = DatasetReviewDialog(data, "AI Generated Data", self)
        if dlg.exec():
            save_path = Path(model_path) / "dataset.json" if os.path.exists(model_path) else Path(self.framework_manager.config.cache_dir) / "dataset.json"
            if self.dataset_manager.save_dataset(dlg.final_data, save_path):
                self.log(f"Dataset saved to {save_path}")
                self._trigger_docker_build(model_path, self.quant_combo.currentText(), str(save_path))
            else:
                QMessageBox.critical(self, "Error", "Failed to save dataset.")

    def on_dataset_error(self, err):
        self.set_controls_enabled(True)
        QMessageBox.critical(self, "AI Error", str(err))

    def _trigger_docker_build(self, model, quant, ds_path):
        raw_format = self.format_combo.currentText()
        target_format = raw_format.split()[0].strip()

        cfg = {
            "model_name": model,
            "target": self.target_combo.currentText(),
            "task": self.task_combo.currentText(),
            "quantization": quant,
            "format": target_format,
            "auto_benchmark": self.chk_auto_bench.isChecked(),
            "use_gpu": self.chk_use_gpu.isChecked(),
            "dataset_path": ds_path
        }
        self.log(f"Build Start: {cfg['target']} [{cfg['quantization']}]")
        self.set_controls_enabled(False)
        self.deploy_btn.setEnabled(False)
        self.docker_manager.start_build(cfg)

    def set_controls_enabled(self, enabled):
        self.start_btn.setEnabled(enabled)
        self.grp_build.setEnabled(enabled)

    def on_build_output(self, bid, line): self.log_view.append(line); self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
    def on_build_progress(self, bid, pct): self.progress_bar.setValue(pct)
    
    def on_build_completed(self, bid, success, p): 
        self.set_controls_enabled(True)
        self.progress_bar.setValue(100 if success else 0)
        
        if success and p and os.path.exists(p):
            self.last_artifact_path = p
            self.deploy_btn.setEnabled(True)
            self.log(f"✅ Build Success. Golden Artifact: {p}")
        else:
            self.log(f"❌ Build Failed. {p}")
    
    def on_build_stats(self, bid, cpu, ram_usage, ram_limit):
        self.lbl_cpu.setText(f"CPU: {cpu}%")
        self.cpu_bar.setValue(int(cpu))
        ram_pct = (ram_usage / ram_limit) * 100 if ram_limit > 0 else 0
        self.lbl_ram.setText(f"RAM: {int(ram_usage)} MB")
        self.ram_bar.setValue(int(ram_pct))
    
    def on_sidecar_status(self, service, status):
        self.log(f"Sidecar [{service}]: {status}")

    def log(self, msg): self.log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
