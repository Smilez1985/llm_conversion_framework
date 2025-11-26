#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Wizards
DIREKTIVE: Goldstandard, vollständige Implementierung.
"""

import threading
from pathlib import Path
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QLabel, QFormLayout, 
    QLineEdit, QComboBox, QRadioButton, QButtonGroup, QTextEdit, 
    QMessageBox, QGroupBox, QPushButton, QFileDialog, QProgressBar,
    QDialog
)
from PySide6.QtCore import Qt, Signal, QObject

from orchestrator.Core.module_generator import ModuleGenerator
from orchestrator.gui.dialogs import AIConfigurationDialog

try:
    from orchestrator.Core.ditto_manager import DittoCoder
except ImportError:
    DittoCoder = None

class WizardSignals(QObject):
    """Signale für Thread-Kommunikation"""
    analysis_finished = Signal(dict)
    analysis_error = Signal(str)

class ModuleCreationWizard(QWizard):
    """
    5-Step Module Creation Wizard mit AI-Integration.
    """
    
    def __init__(self, targets_dir: Path, parent=None):
        super().__init__(parent)
        self.targets_dir = targets_dir
        self.setWindowTitle("Module Creation Wizard")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(900, 700)
        
        self.module_data = {}
        self.ai_config = {} # Speichert API Key, Model etc.
        
        self.signals = WizardSignals()
        self.signals.analysis_finished.connect(self.on_ai_finished)
        self.signals.analysis_error.connect(self.on_ai_error)
        
        # Pages hinzufügen
        self.addPage(self.create_intro_page())
        self.addPage(self.create_hardware_page())
        self.addPage(self.create_docker_page())
        self.addPage(self.create_flags_page())
        self.addPage(self.create_summary_page())

    def create_intro_page(self):
        page = QWizardPage()
        page.setTitle("Welcome")
        page.setSubTitle("Create a new Hardware Target Module")
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel(
            "This wizard will guide you through creating a new hardware target.\n"
            "You can either configure it manually or let Ditto (AI) analyze your hardware probe."
        ))
        
        # --- AI Section ---
        ai_group = QGroupBox("✨ AI Auto-Discovery (Recommended)")
        ai_layout = QVBoxLayout()
        
        lbl_info = QLabel("Upload 'target_hardware_config.txt'. Ditto will detect optimal settings.")
        ai_layout.addWidget(lbl_info)
        
        self.btn_configure_ai = QPushButton("⚙️ Configure AI Agent...")
        self.btn_configure_ai.clicked.connect(self.configure_ai)
        ai_layout.addWidget(self.btn_configure_ai)
        
        self.btn_import = QPushButton("📂 Import Probe & Generate")
        self.btn_import.clicked.connect(self.run_ai_analysis)
        self.btn_import.setStyleSheet("background-color: #6a0dad; color: white; font-weight: bold; padding: 8px;")
        self.btn_import.setEnabled(False) # Erst Config nötig
        ai_layout.addWidget(self.btn_import)
        
        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 0) 
        self.ai_progress.setVisible(False)
        ai_layout.addWidget(self.ai_progress)
        
        self.ai_status = QLabel("")
        ai_layout.addWidget(self.ai_status)
        
        ai_group.setLayout(ai_layout)
        layout.addWidget(ai_group)
        
        layout.addSpacing(20)
        layout.addWidget(QLabel("Or click 'Next' to configure manually from scratch."))
        
        page.setLayout(layout)
        return page

    def create_hardware_page(self):
        page = QWizardPage()
        page.setTitle("Hardware Information")
        page.setSubTitle("Define the target architecture")
        layout = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. NVIDIA Jetson Orin")
        layout.addRow("Module Name:", self.name_edit)
        
        self.arch_combo = QComboBox()
        self.arch_combo.addItems(["aarch64", "x86_64", "armv7l", "riscv64"])
        layout.addRow("Architecture:", self.arch_combo)
        
        self.sdk_edit = QLineEdit()
        self.sdk_edit.setPlaceholderText("e.g. CUDA, RKNN, OpenVINO")
        layout.addRow("SDK / Backend:", self.sdk_edit)
        
        page.setLayout(layout)
        page.registerField("name*", self.name_edit)
        return page

    def create_docker_page(self):
        page = QWizardPage()
        page.setTitle("Docker Environment")
        page.setSubTitle("Configure the build container")
        layout = QVBoxLayout()
        
        self.os_group = QButtonGroup(page)
        self.rad_debian = QRadioButton("Debian 12 (Bookworm) - Recommended")
        self.rad_ubuntu = QRadioButton("Ubuntu 22.04 LTS")
        self.rad_custom = QRadioButton("Custom (AI Suggested)")
        self.rad_debian.setChecked(True)
        
        self.os_group.addButton(self.rad_debian)
        self.os_group.addButton(self.rad_ubuntu)
        self.os_group.addButton(self.rad_custom)
        
        layout.addWidget(QLabel("Base OS:"))
        layout.addWidget(self.rad_debian)
        layout.addWidget(self.rad_ubuntu)
        layout.addWidget(self.rad_custom)
        
        self.custom_os_edit = QLineEdit()
        self.custom_os_edit.setPlaceholderText("e.g. nvidia/cuda:12.2-devel-ubuntu22.04")
        self.custom_os_edit.setEnabled(False)
        self.rad_custom.toggled.connect(lambda: self.custom_os_edit.setEnabled(self.rad_custom.isChecked()))
        layout.addWidget(self.custom_os_edit)
        
        layout.addWidget(QLabel("System Packages (space separated):"))
        self.packages_edit = QLineEdit()
        self.packages_edit.setText("build-essential cmake git python3-pip")
        layout.addWidget(self.packages_edit)
        
        page.setLayout(layout)
        return page

    def create_flags_page(self):
        page = QWizardPage()
        page.setTitle("Compiler Flags")
        page.setSubTitle("Set default optimization flags")
        layout = QFormLayout()
        
        self.cpu_flags = QLineEdit()
        self.cpu_flags.setPlaceholderText("-mcpu=cortex-a76 -mtune=cortex-a76")
        layout.addRow("CPU Flags:", self.cpu_flags)
        
        self.cmake_flags = QLineEdit()
        self.cmake_flags.setPlaceholderText("-DGGML_CUDA=ON")
        layout.addRow("CMake Flags:", self.cmake_flags)
        
        page.setLayout(layout)
        return page

    def create_summary_page(self):
        page = QWizardPage()
        page.setTitle("Summary & Generation")
        page.setSubTitle("Review settings before generation")
        layout = QVBoxLayout()
        
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)
        
        page.setLayout(layout)
        return page

    def initializePage(self, page_id):
        if self.nextId() == -1: # Last page
            self.update_summary()

    def update_summary(self):
        if self.rad_debian.isChecked(): base_os = "debian:bookworm-slim"
        elif self.rad_ubuntu.isChecked(): base_os = "ubuntu:22.04"
        else: base_os = self.custom_os_edit.text()
        
        summary = f"""
        [CONFIGURATION SUMMARY]
        -----------------------
        Module Name:  {self.name_edit.text()}
        Architecture: {self.arch_combo.currentText()}
        SDK Backend:  {self.sdk_edit.text()}
        
        [DOCKER]
        Base Image:   {base_os}
        Packages:     {self.packages_edit.text()}
        
        [COMPILER]
        CPU Flags:    {self.cpu_flags.text()}
        CMake Flags:  {self.cmake_flags.text()}
        """
        self.summary_text.setText(summary)

    # --- AI LOGIC ---

    def configure_ai(self):
        """Öffnet den Konfigurationsdialog für die KI."""
        dialog = AIConfigurationDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.ai_config = dialog.get_config()
            self.btn_import.setEnabled(True)
            self.ai_status.setText(f"Ready: Using {self.ai_config['provider']} ({self.ai_config['model']})")

    def run_ai_analysis(self):
        if not DittoCoder:
            QMessageBox.critical(self, "Error", "Ditto/LiteLLM not installed.\nPlease run: pip install litellm")
            return
            
        if not self.ai_config:
            self.configure_ai()
            if not self.ai_config: return

        path, _ = QFileDialog.getOpenFileName(self, "Select Hardware Probe", "", "Text (*.txt);;All Files (*)")
        if not path: return
        
        self.btn_import.setEnabled(False)
        self.btn_configure_ai.setEnabled(False)
        self.ai_progress.setVisible(True)
        self.ai_status.setText("🤖 Ditto is thinking...")
        
        # Start Background Thread
        threading.Thread(target=self._ai_worker, args=(Path(path),), daemon=True).start()

    def _ai_worker(self, path):
        try:
            coder = DittoCoder(
                provider=self.ai_config.get("provider"),
                model=self.ai_config.get("model"),
                api_key=self.ai_config.get("api_key"),
                base_url=self.ai_config.get("base_url")
            )
            config = coder.generate_module_content(path)
            self.signals.analysis_finished.emit(config)
        except Exception as e:
            self.signals.analysis_error.emit(str(e))

    def on_ai_error(self, err):
        self.btn_import.setEnabled(True)
        self.btn_configure_ai.setEnabled(True)
        self.ai_progress.setVisible(False)
        self.ai_status.setText("❌ Error")
        QMessageBox.critical(self, "AI Error", err)

    def on_ai_finished(self, config):
        self.btn_import.setEnabled(True)
        self.btn_configure_ai.setEnabled(True)
        self.ai_progress.setVisible(False)
        self.ai_status.setText("✅ Analysis complete!")
        
        # Populate Fields
        if "module_name" in config: self.name_edit.setText(config["module_name"])
        if "architecture" in config: self.arch_combo.setCurrentText(config["architecture"])
        if "sdk" in config: self.sdk_edit.setText(config["sdk"])
        
        if "base_os" in config:
            if "debian" in config["base_os"]: self.rad_debian.setChecked(True)
            elif "ubuntu" in config["base_os"]: self.rad_ubuntu.setChecked(True)
            else:
                self.rad_custom.setChecked(True)
                self.custom_os_edit.setText(config["base_os"])
                
        if "packages" in config: self.packages_edit.setText(config["packages"])
        if "cpu_flags" in config: self.cpu_flags.setText(config["cpu_flags"])
        if "cmake_flags" in config: self.cmake_flags.setText(config["cmake_flags"])
        
        QMessageBox.information(self, "Ditto", "Values filled from AI analysis.\nPlease review on next pages.")
        self.next()

    def accept(self):
        # Generate Module (via standard generator)
        self.module_data = {
            "module_name": self.name_edit.text(),
            "architecture": self.arch_combo.currentText(),
            "sdk": self.sdk_edit.text(),
            "description": f"Target for {self.name_edit.text()}",
            "base_os": self.custom_os_edit.text() if self.rad_custom.isChecked() else ("debian:bookworm-slim" if self.rad_debian.isChecked() else "ubuntu:22.04"),
            "packages": self.packages_edit.text().split(),
            "cpu_flags": self.cpu_flags.text(),
            "supported_boards": [],
            "setup_commands": "",
            "cmake_flags": self.cmake_flags.text(),
            "detection_commands": "lscpu"
        }
        
        try:
            if not self.targets_dir.exists(): self.targets_dir.mkdir(parents=True, exist_ok=True)
            generator = ModuleGenerator(self.targets_dir)
            output_path = generator.generate_module(self.module_data)
            QMessageBox.information(self, "Success", f"Module created at:\n{output_path}")
            super().accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate module:\n{e}")
