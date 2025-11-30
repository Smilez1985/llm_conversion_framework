#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Wizards
DIREKTIVE: Goldstandard, vollständige Implementierung.

Dieser Wizard führt den Benutzer durch die Erstellung eines neuen Hardware-Targets.
Er unterstützt zwei Modi:
1. Standard Import: Deterministisches Parsen von hardware_probe.sh/.ps1 Ausgaben.
2. AI Auto-Discovery: Intelligente Analyse und Optimierungsvorschläge durch Ditto (LLM).
"""

import threading
import re
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QLabel, QFormLayout, 
    QLineEdit, QComboBox, QRadioButton, QButtonGroup, QTextEdit, 
    QMessageBox, QGroupBox, QPushButton, QFileDialog, QProgressBar,
    QDialog, QHBoxLayout, QWidget
)
from PySide6.QtCore import Qt, Signal, QObject

from orchestrator.Core.module_generator import ModuleGenerator
from orchestrator.gui.dialogs import AIConfigurationDialog
from orchestrator.utils.localization import tr

# Optionale Ditto Integration
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
    5-Step Module Creation Wizard mit Dual-Mode (Standard & AI).
    """
    
    def __init__(self, targets_dir: Path, parent=None):
        super().__init__(parent)
        self.targets_dir = targets_dir
        self.setWindowTitle(tr("wiz.title"))
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(900, 700)
        
        self.module_data = {}
        self.ai_config = {} 
        
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
        page.setTitle(tr("wiz.intro.title"))
        page.setSubTitle(tr("wiz.intro.text"))
        
        layout = QVBoxLayout()
        
        # --- Import Section ---
        import_group = QGroupBox(tr("wiz.grp.import"))
        import_layout = QVBoxLayout()
        
        # Info Label
        import_layout.addWidget(QLabel(tr("wiz.lbl.ai_info")))

        hbox_btns = QHBoxLayout()
        
        # Button 1: Standard Import (Hardcoded Logic)
        self.btn_import_std = QPushButton(tr("wiz.btn.import_std"))
        self.btn_import_std.clicked.connect(self.run_standard_import)
        self.btn_import_std.setMinimumHeight(40)
        hbox_btns.addWidget(self.btn_import_std)
        
        # Button 2: AI Import (Ditto)
        self.btn_import_ai = QPushButton(tr("wiz.btn.import_ai"))
        self.btn_import_ai.clicked.connect(self.run_ai_analysis)
        self.btn_import_ai.setStyleSheet("background-color: #6a0dad; color: white; font-weight: bold;")
        self.btn_import_ai.setMinimumHeight(40)
        hbox_btns.addWidget(self.btn_import_ai)
        
        import_layout.addLayout(hbox_btns)
        
        # AI Config Button
        hbox_conf = QHBoxLayout()
        hbox_conf.addStretch()
        self.btn_configure_ai = QPushButton(tr("wiz.btn.config_ai"))
        self.btn_configure_ai.clicked.connect(self.configure_ai)
        hbox_conf.addWidget(self.btn_configure_ai)
        import_layout.addLayout(hbox_conf)

        # Progress & Status
        self.status_label = QLabel(tr("wiz.status.waiting"))
        self.status_label.setAlignment(Qt.AlignCenter)
        import_layout.addWidget(self.status_label)
        
        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 0) 
        self.ai_progress.setVisible(False)
        import_layout.addWidget(self.ai_progress)

        import_group.setLayout(import_layout)
        layout.addWidget(import_group)
        
        # --- Manual Section ---
        layout.addSpacing(20)
        layout.addWidget(QLabel(tr("wiz.lbl.manual")))
        
        page.setLayout(layout)
        return page

    def create_hardware_page(self):
        page = QWizardPage()
        page.setTitle(tr("wiz.page.hardware"))
        page.setSubTitle(tr("wiz.page.hardware.sub"))
        layout = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. NVIDIA Jetson Orin / Rockchip RK3588")
        layout.addRow(tr("wiz.lbl.name"), self.name_edit)
        
        self.arch_combo = QComboBox()
        self.arch_combo.addItems(["aarch64", "x86_64", "armv7l", "riscv64"])
        layout.addRow(tr("wiz.lbl.arch"), self.arch_combo)
        
        self.sdk_edit = QLineEdit()
        self.sdk_edit.setPlaceholderText("e.g. CUDA, RKNN, OpenVINO")
        layout.addRow(tr("wiz.lbl.sdk"), self.sdk_edit)
        
        page.setLayout(layout)
        page.registerField("name*", self.name_edit)
        return page

    def create_docker_page(self):
        page = QWizardPage()
        page.setTitle(tr("wiz.page.docker"))
        page.setSubTitle(tr("wiz.page.docker.sub"))
        layout = QVBoxLayout()
        
        self.os_group = QButtonGroup(page)
        self.rad_debian = QRadioButton(tr("wiz.rad.debian"))
        self.rad_ubuntu = QRadioButton(tr("wiz.rad.ubuntu"))
        self.rad_custom = QRadioButton(tr("wiz.rad.custom"))
        self.rad_debian.setChecked(True)
        
        self.os_group.addButton(self.rad_debian)
        self.os_group.addButton(self.rad_ubuntu)
        self.os_group.addButton(self.rad_custom)
        
        layout.addWidget(QLabel(tr("wiz.lbl.base_os")))
        layout.addWidget(self.rad_debian)
        layout.addWidget(self.rad_ubuntu)
        layout.addWidget(self.rad_custom)
        
        self.custom_os_edit = QLineEdit()
        self.custom_os_edit.setPlaceholderText("e.g. nvidia/cuda:12.2-devel-ubuntu22.04")
        self.custom_os_edit.setEnabled(False)
        self.rad_custom.toggled.connect(lambda: self.custom_os_edit.setEnabled(self.rad_custom.isChecked()))
        layout.addWidget(self.custom_os_edit)
        
        layout.addWidget(QLabel(tr("wiz.lbl.packages")))
        self.packages_edit = QLineEdit()
        # Standard-Pakete ohne Compiler, der wird dynamisch hinzugefügt
        self.packages_edit.setText("build-essential cmake git python3-pip")
        layout.addWidget(self.packages_edit)
        
        page.setLayout(layout)
        return page

    def create_flags_page(self):
        page = QWizardPage()
        page.setTitle(tr("wiz.page.flags"))
        page.setSubTitle(tr("wiz.page.flags.sub"))
        layout = QFormLayout()
        
        self.cpu_flags = QLineEdit()
        self.cpu_flags.setPlaceholderText("-mcpu=cortex-a76 -mtune=cortex-a76")
        layout.addRow(tr("wiz.lbl.cpu_flags"), self.cpu_flags)
        
        self.cmake_flags = QLineEdit()
        self.cmake_flags.setPlaceholderText("-DGGML_CUDA=ON")
        layout.addRow(tr("wiz.lbl.cmake_flags"), self.cmake_flags)
        
        # Hidden field for AI logic (Bash Case Statement)
        self.quant_logic = QTextEdit()
        self.quant_logic.setVisible(False) 
        layout.addRow(self.quant_logic)
        
        page.setLayout(layout)
        return page

    def create_summary_page(self):
        page = QWizardPage()
        page.setTitle(tr("wiz.page.summary"))
        page.setSubTitle(tr("wiz.page.summary.sub"))
        layout = QVBoxLayout()
        
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setStyleSheet("font-family: Consolas, Monospace;")
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
=======================
Module Name:  {self.name_edit.text()}
Architecture: {self.arch_combo.currentText()}
SDK Backend:  {self.sdk_edit.text()}

[DOCKER]
Base Image:   {base_os}
Packages:     {self.packages_edit.text()}
+ Auto-Added: Cross-Compiler for {self.arch_combo.currentText()}

[COMPILER]
CPU Flags:    {self.cpu_flags.text()}
CMake Flags:  {self.cmake_flags.text()}

[LOGIC]
Quantization Script provided: {'Yes' if self.quant_logic.toPlainText() else 'No (Default)'}
"""
        self.summary_text.setText(summary)

    # --- STANDARD IMPORT LOGIC (Rule Based) ---

    def run_standard_import(self):
        """
        Parses target_hardware_config.txt using regex and deterministic rules.
        No AI involved. Robust and fast.
        """
        path, _ = QFileDialog.getOpenFileName(self, tr("menu.import_profile"), "", "Config (*.txt);;All Files (*)")
        if not path: return
        
        self.status_label.setText("Parsing probe data...")
        
        try:
            # Read config file into dictionary
            config = {}
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        config[key.strip()] = val.strip()
            
            if not config:
                raise ValueError("File format invalid or empty.")

            # 1. Architecture Detection
            arch_map = {
                "aarch64": "aarch64", "arm64": "aarch64", 
                "x86_64": "x86_64", "amd64": "x86_64",
                "armv7l": "armv7l"
            }
            detected_arch = config.get("Architecture", "").lower()
            if detected_arch in arch_map:
                self.arch_combo.setCurrentText(arch_map[detected_arch])
            
            # 2. Name & SDK Recommendation
            sdk = "None"
            name_hint = "Generic_Target"
            
            if config.get("SUPPORTS_CUDA") == "ON": 
                sdk = "CUDA"
                name_hint = f"NVIDIA_{config.get('GPU_MODEL', 'GPU').replace(' ', '_')}"
            elif config.get("SUPPORTS_RKNN") == "ON": 
                sdk = "RKNN"
                name_hint = f"Rockchip_{config.get('NPU_MODEL', 'NPU')}"
                if config.get("SUPPORTS_RKLLM") == "ON":
                    sdk = "RKLLM / RKNN"
            elif config.get("SUPPORTS_HAILO") == "ON": 
                sdk = "Hailo"
                name_hint = "Hailo_AI_Kit"
            elif config.get("SUPPORTS_INTEL_NPU") == "ON": 
                sdk = "OpenVINO"
                name_hint = "Intel_NPU"

            self.sdk_edit.setText(sdk)
            self.name_edit.setText(name_hint)
            
            # 3. Docker Base Image Logic
            if sdk == "CUDA":
                self.rad_custom.setChecked(True)
                self.custom_os_edit.setText("nvidia/cuda:12.2.2-devel-ubuntu22.04")
            elif sdk == "OpenVINO":
                self.rad_ubuntu.setChecked(True) 
            else:
                self.rad_debian.setChecked(True) 

            # 4. Flags (CPU & CMake)
            cpu_flags = []
            cmake_flags = []
            
            if config.get("SUPPORTS_NEON") == "ON": cmake_flags.append("-DGGML_NEON=ON")
            if config.get("SUPPORTS_FP16") == "ON":
                cmake_flags.append("-DGGML_FP16=ON")
                if detected_arch in ["aarch64", "arm64"]:
                    cpu_flags.append("-march=armv8.2-a+fp16")
                
            if config.get("SUPPORTS_AVX") == "ON": cmake_flags.append("-DGGML_AVX=ON")
            if config.get("SUPPORTS_AVX2") == "ON": 
                cmake_flags.append("-DGGML_AVX2=ON")
                cpu_flags.append("-mavx2")
            if config.get("SUPPORTS_AVX512") == "ON": 
                cmake_flags.append("-DGGML_AVX512=ON")
                cpu_flags.append("-mavx512f")
            if config.get("SUPPORTS_F16C") == "ON":
                cmake_flags.append("-DGGML_F16C=ON")
                cpu_flags.append("-mf16c")

            self.cpu_flags.setText(" ".join(cpu_flags))
            self.cmake_flags.setText(" ".join(cmake_flags))
            
            self.status_label.setText(tr("msg.import_success"))
            QMessageBox.information(self, tr("msg.import_success"), 
                                  f"Hardware profile loaded.\nDetected Arch: {detected_arch}\nSuggested SDK: {sdk}")
            self.next()
            
        except Exception as e:
            self.status_label.setText(tr("status.error"))
            QMessageBox.critical(self, tr("status.error"), f"Failed to parse probe file:\n{str(e)}")

    # --- AI LOGIC (Ditto) ---

    def configure_ai(self):
        dialog = AIConfigurationDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.ai_config = dialog.get_config()
            self.btn_import_ai.setEnabled(True)
            self.status_label.setText(f"{tr('msg.ai_ready')}: {self.ai_config.get('provider')}")

    def run_ai_analysis(self):
        if not DittoCoder:
            QMessageBox.critical(self, tr("status.error"), "Ditto/LiteLLM not installed.\nPlease run: pip install litellm")
            return
            
        if not self.ai_config:
            self.configure_ai()
            if not self.ai_config: return

        path, _ = QFileDialog.getOpenFileName(self, tr("menu.import_profile"), "", "Config (*.txt);;All Files (*)")
        if not path: return
        
        self.btn_import_ai.setEnabled(False)
        self.btn_import_std.setEnabled(False)
        self.ai_progress.setVisible(True)
        self.status_label.setText(tr("msg.ai_thinking"))
        
        threading.Thread(target=self._ai_worker, args=(Path(path),), daemon=True).start()

    def _ai_worker(self, path):
        try:
            fm_config = None
            if self.wizard() and self.wizard().parent() and hasattr(self.wizard().parent(), 'framework_manager'):
                fm_config = self.wizard().parent().framework_manager.config

            coder = DittoCoder(
                provider=self.ai_config.get("provider"),
                model=self.ai_config.get("model"),
                api_key=self.ai_config.get("api_key"),
                base_url=self.ai_config.get("base_url"),
                config_manager=fm_config
            )
            config = coder.generate_module_content(path)
            self.signals.analysis_finished.emit(config)
        except Exception as e:
            self.signals.analysis_error.emit(str(e))

    def on_ai_error(self, err):
        self.btn_import_ai.setEnabled(True)
        self.btn_import_std.setEnabled(True)
        self.ai_progress.setVisible(False)
        self.status_label.setText(f"❌ {tr('status.error')}")
        QMessageBox.critical(self, "AI Error", err)

    def on_ai_finished(self, config):
        self.btn_import_ai.setEnabled(True)
        self.btn_import_std.setEnabled(True)
        self.ai_progress.setVisible(False)
        self.status_label.setText(tr("msg.ai_complete"))
        
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
        if "quantization_logic" in config: self.quant_logic.setText(config["quantization_logic"])
        
        QMessageBox.information(self, "Ditto", "Values filled from AI analysis.\nPlease review on next pages.")
        self.next()

    def accept(self):
        # --- CROSS-COMPILER AUTO-INJECTION ---
        packages_list = self.packages_edit.text().split()
        arch = self.arch_combo.currentText()
        
        # Wenn wir nicht x86_64 sind, brauchen wir den Compiler
        if arch == "aarch64":
            if "gcc-aarch64-linux-gnu" not in packages_list:
                packages_list.append("gcc-aarch64-linux-gnu")
            if "g++-aarch64-linux-gnu" not in packages_list:
                packages_list.append("g++-aarch64-linux-gnu")
                
        elif arch == "armv7l":
             if "gcc-arm-linux-gnueabihf" not in packages_list:
                 packages_list.append("gcc-arm-linux-gnueabihf")
             if "g++-arm-linux-gnueabihf" not in packages_list:
                 packages_list.append("g++-arm-linux-gnueabihf")

        elif arch == "riscv64":
             if "gcc-riscv64-linux-gnu" not in packages_list:
                 packages_list.append("gcc-riscv64-linux-gnu")
             if "g++-riscv64-linux-gnu" not in packages_list:
                 packages_list.append("g++-riscv64-linux-gnu")

        self.module_data = {
            "module_name": self.name_edit.text(),
            "architecture": arch,
            "sdk": self.sdk_edit.text(),
            "description": f"Target for {self.name_edit.text()}",
            "base_os": self.custom_os_edit.text() if self.rad_custom.isChecked() else ("debian:bookworm-slim" if self.rad_debian.isChecked() else "ubuntu:22.04"),
            "packages": packages_list, # Updated List
            "cpu_flags": self.cpu_flags.text(),
            "supported_boards": [],
            "setup_commands": "",
            "cmake_flags": self.cmake_flags.text(),
            "quantization_logic": self.quant_logic.toPlainText(),
            "detection_commands": "lscpu"
        }
        
        try:
            if not self.targets_dir.exists(): self.targets_dir.mkdir(parents=True, exist_ok=True)
            generator = ModuleGenerator(self.targets_dir)
            output_path = generator.generate_module(self.module_data)
            QMessageBox.information(self, tr("msg.success"), f"{tr('msg.module_created')}\n{output_path}")
            super().accept()
        except Exception as e:
            QMessageBox.critical(self, tr("status.error"), f"Failed to generate module:\n{e}")
