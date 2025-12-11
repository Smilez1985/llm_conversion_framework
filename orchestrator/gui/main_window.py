#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Window (v2.0 Enterprise)
DIREKTIVE: Goldstandard GUI.

Features:
- Integration of SecretsManager UI.
- Status display for Self-Healing/Guardian.
- Central Hub for all sub-windows.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QTabWidget, QStatusBar,
    QMenu, QMenuBar, QMessageBox, QToolBar
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import Qt, QSize

# Core Integration
from orchestrator.Core.framework import FrameworkManager
from orchestrator.utils.localization import get_instance as get_i18n

# GUI Components
from orchestrator.gui.dialogs import SecretInputDialog
# Placeholder imports for other windows (assuming they exist or will be cleaned up)
# In a real scenario, we would import all sub-windows here.

class MainOrchestrator(QMainWindow):
    def __init__(self, app_root: Path):
        super().__init__()
        self.app_root = app_root
        self.i18n = get_i18n()
        
        # 1. Initialize Backend Framework
        self.framework = FrameworkManager()
        if not self.framework.initialize():
            QMessageBox.critical(self, "Fatal Error", "Framework initialization failed. Check logs.")
            sys.exit(1)
            
        self.setWindowTitle("LLM Cross-Compiler Framework (Enterprise Edition)")
        self.resize(1200, 800)
        
        # 2. Setup UI
        self._setup_menu()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_statusbar()
        
        # 3. Apply Theme (Basic Dark Mode)
        self._apply_styles()

    def _setup_menu(self):
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu(self.i18n.t("menu.file", "File"))
        exit_action = QAction(self.i18n.t("menu.exit", "Exit"), self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Security Menu (NEU!)
        sec_menu = menubar.addMenu("Security")
        
        act_openai = QAction("Set OpenAI API Key", self)
        act_openai.triggered.connect(lambda: self._open_secret_dialog("openai_api_key", "OpenAI API Key"))
        sec_menu.addAction(act_openai)
        
        act_hf = QAction("Set HuggingFace Token", self)
        act_hf.triggered.connect(lambda: self._open_secret_dialog("hf_token", "HuggingFace Token"))
        sec_menu.addAction(act_hf)
        
        act_ssh = QAction("Set Target SSH Password", self)
        act_ssh.triggered.connect(lambda: self._open_secret_dialog("target_password", "SSH Password (Root)"))
        sec_menu.addAction(act_ssh)

        # Help Menu
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(toolbar)
        
        # Hier könnten Schnellzugriff-Buttons hin
        # toolbar.addAction(QIcon(...), "Build", self._on_build_click)

    def _setup_central_widget(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Dashboard Header
        header = QLabel("<h1>Orchestrator Dashboard</h1>")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Tabs for different modules
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Placeholder Tabs (Diese müssten mit den echten Widgets gefüllt werden)
        self.tabs.addTab(QLabel("Build Manager Placeholder"), "Builds")
        self.tabs.addTab(QLabel("Model Manager Placeholder"), "Models")
        self.tabs.addTab(QLabel("Target Manager Placeholder"), "Targets")
        self.tabs.addTab(QLabel("RAG / Knowledge Placeholder"), "Knowledge Base")

    def _setup_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        
        # Security Indicator
        if self.framework.secrets_manager:
            self.lbl_sec = QLabel("🛡️ Secrets Secured")
            self.lbl_sec.setStyleSheet("color: #4CAF50; font-weight: bold; margin-right: 10px;")
            self.status.addPermanentWidget(self.lbl_sec)
        
        # Self-Healing Indicator
        if self.framework.self_healing_manager:
            self.lbl_heal = QLabel("🏥 Healing Active")
            self.lbl_heal.setStyleSheet("color: #2196F3; font-weight: bold; margin-right: 10px;")
            self.status.addPermanentWidget(self.lbl_heal)
            
        self.status.showMessage("Ready.")

    def _open_secret_dialog(self, key, name):
        """Öffnet den sicheren Dialog für Secrets."""
        if not self.framework.secrets_manager:
            QMessageBox.critical(self, "Error", "SecretsManager not available!")
            return
            
        dlg = SecretInputDialog(self.framework, key, name, self)
        dlg.exec()

    def _show_about(self):
        QMessageBox.about(self, "About", 
                          f"LLM Cross-Compiler Framework\n"
                          f"Version: {self.framework.info.version}\n"
                          f"Security Level: Enterprise")

    def _apply_styles(self):
        # Einfaches Dark Theme
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; color: #ffffff; }
            QTabWidget::pane { border: 1px solid #444; }
            QTabBar::tab { background: #333; color: #fff; padding: 8px; }
            QTabBar::tab:selected { background: #555; }
            QLabel { color: #fff; }
            QMenuBar { background-color: #333; color: #fff; }
            QMenuBar::item:selected { background-color: #555; }
            QMenu { background-color: #333; color: #fff; }
            QMenu::item:selected { background-color: #555; }
        """)

    def closeEvent(self, event):
        self.framework.shutdown()
        event.accept()
