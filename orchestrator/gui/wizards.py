#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Wizards
DIREKTIVE: Goldstandard, vollständige Implementierung.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QLabel, QFormLayout, 
    QLineEdit, QComboBox, QRadioButton, QButtonGroup, QTextEdit, QMessageBox
)
from orchestrator.Core.module_generator import ModuleGenerator

class ModuleCreationWizard(QWizard):
    """
    5-Step Module Creation Wizard.
    Führt den Benutzer durch die Erstellung eines neuen Hardware-Targets.
    """
    
    def __init__(self, targets_dir: Path, parent=None):
        super().__init__(parent)
        self.targets_dir = targets_dir
        self.setWindowTitle("Module Creation Wizard")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(800, 600)
        
        self.module_data = {}
        
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
            "This wizard will guide you through creating a new hardware target for the LLM Framework.\n\n"
            "It will generate:\n"
            "- Dockerfile (Multi-Stage)\n"
            "- Target Configuration (target.yml)\n"
            "- Shell Modules (source, config, convert, target)\n"
        ))
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
        page.registerField("name*", self.name_edit) # Name ist Pflichtfeld
        return page

    def create_docker_page(self):
        page = QWizardPage()
        page.setTitle("Docker Environment")
        page.setSubTitle("Configure the build container")
        layout = QVBoxLayout()
        
        self.os_group = QButtonGroup(page)
        self.rad_debian = QRadioButton("Debian 12 (Bookworm) - Recommended")
        self.rad_ubuntu = QRadioButton("Ubuntu 22.04 LTS")
        self.rad_debian.setChecked(True)
        self.os_group.addButton(self.rad_debian)
        self.os_group.addButton(self.rad_ubuntu)
        
        layout.addWidget(QLabel("Base OS:"))
        layout.addWidget(self.rad_debian)
        layout.addWidget(self.rad_ubuntu)
        
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
        # Wenn wir auf der letzten Seite (ID 4) landen, Summary updaten
        if self.nextId() == -1: 
            self.update_summary()

    def update_summary(self):
        base_os = "debian:bookworm-slim" if self.rad_debian.isChecked() else "ubuntu:22.04"
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

    def accept(self):
        """
        Führt die Generierung durch, wenn der User auf 'Finish' klickt.
        """
        # 1. Daten sammeln
        self.module_data = {
            "module_name": self.name_edit.text(),
            "architecture": self.arch_combo.currentText(),
            "sdk": self.sdk_edit.text(),
            "description": f"Target for {self.name_edit.text()}",
            "base_os": "debian:bookworm-slim" if self.rad_debian.isChecked() else "ubuntu:22.04",
            "packages": self.packages_edit.text().split(),
            "cpu_flags": self.cpu_flags.text(),
            "supported_boards": [],
            "setup_commands": "",
            "cmake_flags": self.cmake_flags.text(),
            "detection_commands": "lscpu"
        }
        
        try:
            # 2. Verzeichnis prüfen
            if not self.targets_dir.exists():
                self.targets_dir.mkdir(parents=True, exist_ok=True)
            
            # 3. Generator instanziieren und ausführen
            generator = ModuleGenerator(self.targets_dir)
            output_path = generator.generate_module(self.module_data)
            
            # 4. Erfolgsmeldung
            QMessageBox.information(
                self,
                "Module Generated",
                f"✅ Success!\n\nModule created at:\n{output_path}\n\nYou can now edit config_module.sh for fine-tuning."
            )
            
            # Wizard schließen (Standard-Verhalten von accept)
            super().accept()
            
        except Exception as e:
            # Fehler anzeigen und Wizard NICHT schließen
            QMessageBox.critical(self, "Generation Error", f"Failed to generate module:\n{e}")
