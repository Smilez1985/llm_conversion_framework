#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Orchestrator GUI
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Hauptfunktionen:
- Target Discovery & Management
- Docker Container Orchestration  
- Hardware Profile Upload & Management
- Modul Creation Wizard (5-Schritt Community-System)
- Live Build Monitoring
- Framework Configuration
"""

import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTextEdit, QProgressBar,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QSpinBox, QFileDialog,
    QMessageBox, QSplitter, QListWidget, QTableWidget, QTableWidgetItem,
    QDialog, QWizard, QWizardPage, QTextBrowser, QScrollArea,
    QFrame, QGridLayout, QButtonGroup, QRadioButton, QStackedWidget
)
from PySide6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSettings, QProcess,
    QStandardPaths, QDir, QFileSystemWatcher
)
from PySide6.QtGui import (
    QFont, QTextCursor, QPalette, QIcon, QPixmap, QColor,
    QTextCharFormat, QAction, QKeySequence
)

import docker
import yaml
from rich.console import Console
from rich.text import Text


# ============================================================================
# DATA MODELS & CONFIGURATION
# ============================================================================

@dataclass
class TargetConfig:
    """Configuration for a hardware target"""
    name: str
    description: str
    architecture: str
    supported_boards: List[str]
    docker_image: str
    maintainer: str
    version: str
    status: str = "available"  # available, building, error


@dataclass
class HardwareProfile:
    """Hardware profile from target system"""
    name: str
    architecture: str
    cpu_model: str
    cpu_cores: int
    memory_mb: int
    gpu_model: Optional[str] = None
    npu_support: Optional[str] = None
    special_features: Dict[str, Any] = None


@dataclass
class BuildJob:
    """Build job configuration and status"""
    id: str
    model_name: str
    target: str
    quantization: str
    status: str  # queued, running, completed, failed
    progress: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    output_path: Optional[str] = None


class FrameworkConfig:
    """Global framework configuration"""
    
    def __init__(self):
        self.app_name = "LLM Cross-Compiler Framework"
        self.version = "1.0.0"
        self.config_dir = Path(QStandardPaths.writableLocation(
            QStandardPaths.ConfigLocation)) / "llm-framework"
        self.cache_dir = Path(QStandardPaths.writableLocation(
            QStandardPaths.CacheLocation)) / "llm-framework"
        
        # Create directories
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Paths
        self.targets_dir = Path("targets")
        self.models_dir = Path("models")
        self.output_dir = Path("output") 
        self.configs_dir = Path("configs")
        
        # Docker configuration
        self.docker_client = None
        self.docker_compose_file = Path("docker-compose.yml")


# ============================================================================
# DOCKER MANAGEMENT
# ============================================================================

class DockerManager(QThread):
    """Manages Docker containers and builds"""
    
    status_changed = pyqtSignal(str, str)  # container_name, status
    build_progress = pyqtSignal(str, int)  # build_id, progress
    build_output = pyqtSignal(str, str)   # build_id, output_line
    build_completed = pyqtSignal(str, bool, str)  # build_id, success, output_path
    
    def __init__(self):
        super().__init__()
        self.docker_client = None
        self.active_builds: Dict[str, QProcess] = {}
        self.build_queue: List[BuildJob] = []
        
    def initialize_docker(self):
        """Initialize Docker client"""
        try:
            self.docker_client = docker.from_env()
            self.docker_client.ping()
            return True
        except Exception as e:
            logging.error(f"Docker initialization failed: {e}")
            return False
    
    def get_available_targets(self) -> List[TargetConfig]:
        """Discover available targets from filesystem"""
        targets = []
        targets_dir = Path("targets")
        
        if not targets_dir.exists():
            return targets
            
        for target_path in targets_dir.iterdir():
            if target_path.is_dir():
                target_yml = target_path / "target.yml"
                if target_yml.exists():
                    try:
                        with open(target_yml, 'r') as f:
                            config_data = yaml.safe_load(f)
                        
                        metadata = config_data.get('metadata', {})
                        target = TargetConfig(
                            name=metadata.get('name', target_path.name),
                            description=metadata.get('description', ''),
                            architecture=target_path.name,
                            supported_boards=config_data.get('supported_boards', []),
                            docker_image=config_data.get('docker', {}).get('image_name', ''),
                            maintainer=metadata.get('maintainer', 'Unknown'),
                            version=metadata.get('version', '1.0.0')
                        )
                        targets.append(target)
                        
                    except Exception as e:
                        logging.error(f"Failed to load target config {target_yml}: {e}")
        
        return targets
    
    def start_build(self, build_job: BuildJob):
        """Start a build job"""
        self.build_queue.append(build_job)
        if not self.isRunning():
            self.start()
    
    def run(self):
        """Process build queue"""
        while self.build_queue:
            job = self.build_queue.pop(0)
            self._execute_build(job)
    
    def _execute_build(self, job: BuildJob):
        """Execute a single build job"""
        try:
            job.start_time = datetime.now()
            job.status = "running"
            
            # Prepare Docker command
            cmd = [
                "docker-compose", "exec", "-T", f"{job.target}-builder",
                "pipeline",
                f"/build-cache/models/{job.model_name}",
                job.model_name,
                job.quantization
            ]
            
            # Start process
            process = QProcess()
            process.readyReadStandardOutput.connect(
                lambda: self._handle_build_output(job.id, process)
            )
            process.finished.connect(
                lambda exit_code: self._handle_build_finished(job.id, exit_code)
            )
            
            self.active_builds[job.id] = process
            process.start(cmd[0], cmd[1:])
            
            # Wait for completion
            process.waitForFinished(-1)
            
        except Exception as e:
            logging.error(f"Build execution failed: {e}")
            self.build_completed.emit(job.id, False, str(e))
    
    def _handle_build_output(self, build_id: str, process: QProcess):
        """Handle build output"""
        data = process.readAllStandardOutput().data().decode()
        lines = data.strip().split('\n')
        
        for line in lines:
            if line.strip():
                self.build_output.emit(build_id, line)
                
                # Extract progress if possible
                if "%" in line:
                    try:
                        progress = int(line.split('%')[0].split()[-1])
                        self.build_progress.emit(build_id, progress)
                    except:
                        pass
    
    def _handle_build_finished(self, build_id: str, exit_code: int):
        """Handle build completion"""
        success = exit_code == 0
        output_path = f"output/packages" if success else ""
        
        if build_id in self.active_builds:
            del self.active_builds[build_id]
        
        self.build_completed.emit(build_id, success, output_path)


# ============================================================================
# MODULE CREATION WIZARD
# ============================================================================

class ModuleCreationWizard(QWizard):
    """5-Step Module Creation Wizard for Community Contributors"""
    
    # Wizard page IDs
    PAGE_HARDWARE_ID = 0
    PAGE_DOCKER_ENV = 1
    PAGE_CONFIG_AGENT = 2
    PAGE_PROFILE_SCRIPT = 3
    PAGE_SUMMARY = 4
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Module Creation Wizard")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(800, 600)
        
        # Wizard data storage
        self.module_data = {}
        
        # Create pages
        self.addPage(self.create_hardware_identification_page())
        self.addPage(self.create_docker_environment_page())
        self.addPage(self.create_configuration_agent_page())
        self.addPage(self.create_profile_script_page())
        self.addPage(self.create_summary_page())
        
    def create_hardware_identification_page(self) -> QWizardPage:
        """Step 1: Hardware Identification"""
        page = QWizardPage()
        page.setTitle("Hardware Identification")
        page.setSubTitle("Define your target hardware family")
        
        layout = QFormLayout()
        
        # Module name
        self.module_name_edit = QLineEdit()
        self.module_name_edit.setPlaceholderText("e.g., NVIDIA Jetson")
        layout.addRow("Module Name:", self.module_name_edit)
        
        # Target architecture
        self.arch_combo = QComboBox()
        self.arch_combo.addItems(["aarch64", "x86_64", "armv7l", "riscv64"])
        layout.addRow("Target Architecture:", self.arch_combo)
        
        # Special SDK/Backend
        self.sdk_combo = QComboBox()
        self.sdk_combo.setEditable(True)
        self.sdk_combo.addItems([
            "CUDA", "OpenVINO", "HailoRT", "OpenCL", "Vulkan", 
            "TensorRT", "DirectML", "Native CPU", "Custom"
        ])
        layout.addRow("Special SDK/Backend:", self.sdk_combo)
        
        # Supported boards
        self.boards_edit = QTextEdit()
        self.boards_edit.setMaximumHeight(100)
        self.boards_edit.setPlaceholderText("List supported boards, one per line\ne.g.:\nJetson Nano\nJetson Xavier NX\nJetson Orin")
        layout.addRow("Supported Boards:", self.boards_edit)
        
        # Description
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setPlaceholderText("Brief description of the hardware family")
        layout.addRow("Description:", self.description_edit)
        
        page.setLayout(layout)
        
        # Register fields for validation
        page.registerField("module_name*", self.module_name_edit)
        page.registerField("architecture", self.arch_combo, "currentText")
        page.registerField("sdk", self.sdk_combo, "currentText")
        
        return page
    
    def create_docker_environment_page(self) -> QWizardPage:
        """Step 2: Docker Environment Configuration"""
        page = QWizardPage()
        page.setTitle("Docker Environment")
        page.setSubTitle("Configure the build environment")
        
        layout = QVBoxLayout()
        
        # Base OS selection
        os_group = QGroupBox("Base Operating System")
        os_layout = QVBoxLayout()
        
        self.os_button_group = QButtonGroup()
        os_options = [
            ("debian:bookworm-slim", "Debian 12 (Recommended)"),
            ("ubuntu:22.04", "Ubuntu 22.04 LTS"),
            ("nvidia/cuda:12.2-devel-ubuntu22.04", "NVIDIA CUDA Base"),
            ("custom", "Custom Base Image")
        ]
        
        for value, label in os_options:
            radio = QRadioButton(label)
            radio.setProperty("value", value)
            self.os_button_group.addButton(radio)
            os_layout.addWidget(radio)
            if value == "debian:bookworm-slim":
                radio.setChecked(True)
        
        os_group.setLayout(os_layout)
        layout.addWidget(os_group)
        
        # Custom base image input
        self.custom_base_edit = QLineEdit()
        self.custom_base_edit.setPlaceholderText("registry/image:tag")
        self.custom_base_edit.setEnabled(False)
        layout.addWidget(QLabel("Custom Base Image:"))
        layout.addWidget(self.custom_base_edit)
        
        # Required packages
        packages_group = QGroupBox("Required Packages")
        packages_layout = QVBoxLayout()
        
        self.packages_edit = QTextEdit()
        self.packages_edit.setMaximumHeight(120)
        self.packages_edit.setPlaceholderText(
            "List required packages, one per line:\n"
            "build-essential\n"
            "cmake\n"
            "cuda-toolkit-12.2\n"
            "python3-pip"
        )
        packages_layout.addWidget(self.packages_edit)
        packages_group.setLayout(packages_layout)
        layout.addWidget(packages_group)
        
        # Additional setup commands
        commands_group = QGroupBox("Additional Setup Commands")
        commands_layout = QVBoxLayout()
        
        self.commands_edit = QTextEdit()
        self.commands_edit.setMaximumHeight(120)
        self.commands_edit.setPlaceholderText(
            "Additional shell commands for SDK installation:\n"
            "# Example:\n"
            "wget https://example.com/sdk.tar.gz\n"
            "tar -xzf sdk.tar.gz\n"
            "cd sdk && ./install.sh"
        )
        commands_layout.addWidget(self.commands_edit)
        commands_group.setLayout(commands_layout)
        layout.addWidget(commands_group)
        
        # Connect custom base image toggle
        self.os_button_group.buttonClicked.connect(self._on_os_selection_changed)
        
        page.setLayout(layout)
        return page
    
    def create_configuration_agent_page(self) -> QWizardPage:
        """Step 3: Configuration Agent (config_module.sh)"""
        page = QWizardPage()
        page.setTitle("Configuration Agent")
        page.setSubTitle("Define hardware-specific optimizations")
        
        layout = QVBoxLayout()
        
        # Important compiler flags
        flags_group = QGroupBox("Important Compiler Flags")
        flags_layout = QFormLayout()
        
        self.cpu_flags_edit = QLineEdit()
        self.cpu_flags_edit.setPlaceholderText("-mcpu=cortex-a76 -mfpu=neon")
        flags_layout.addRow("CPU Flags:", self.cpu_flags_edit)
        
        self.cmake_flags_edit = QLineEdit()
        self.cmake_flags_edit.setPlaceholderText("-DGGML_CUDA=ON -DCUBLAS=ON")
        flags_layout.addRow("CMake Flags:", self.cmake_flags_edit)
        
        self.optimization_level = QComboBox()
        self.optimization_level.addItems(["-O3", "-O2", "-Os", "-Ofast"])
        flags_layout.addRow("Optimization Level:", self.optimization_level)
        
        flags_group.setLayout(flags_layout)
        layout.addWidget(flags_group)
        
        # Hardware config parsing logic
        config_group = QGroupBox("Hardware Config Parsing Logic")
        config_layout = QVBoxLayout()
        
        config_info = QLabel(
            "Define how to read target_hardware_config.txt and map values to compiler flags.\n"
            "The wizard will generate the config_module.sh based on these mappings."
        )
        config_info.setWordWrap(True)
        config_layout.addWidget(config_info)
        
        # Mapping table
        self.config_mapping_table = QTableWidget(0, 3)
        self.config_mapping_table.setHorizontalHeaderLabels([
            "Config Key", "Expected Values", "Generated Flag"
        ])
        self.config_mapping_table.setMinimumHeight(150)
        config_layout.addWidget(self.config_mapping_table)
        
        # Add mapping button
        add_mapping_btn = QPushButton("Add Mapping")
        add_mapping_btn.clicked.connect(self._add_config_mapping)
        config_layout.addWidget(add_mapping_btn)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Default mappings for common scenarios
        self._add_default_config_mappings()
        
        page.setLayout(layout)
        return page
    
    def create_profile_script_page(self) -> QWizardPage:
        """Step 4: Profile Script Generation"""
        page = QWizardPage()
        page.setTitle("Profile Script")
        page.setSubTitle("Generate hardware detection script for target systems")
        
        layout = QVBoxLayout()
        
        info_label = QLabel(
            "This wizard will generate a script that users run on their target hardware "
            "to create the target_hardware_config.txt file. Define what information "
            "needs to be collected."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Detection commands
        detection_group = QGroupBox("Hardware Detection Commands")
        detection_layout = QVBoxLayout()
        
        self.detection_commands = QTextEdit()
        self.detection_commands.setPlaceholderText(
            "Commands to extract hardware information:\n\n"
            "# CPU Information\n"
            "lscpu | grep 'Model name'\n"
            "nproc\n\n"
            "# GPU Information (if applicable)\n"
            "nvidia-smi --query-gpu=gpu_name --format=csv,noheader\n\n"
            "# Custom SDK Version\n"
            "nvcc --version | grep 'release'"
        )
        detection_layout.addWidget(self.detection_commands)
        detection_group.setLayout(detection_layout)
        layout.addWidget(detection_group)
        
        # Target platform
        platform_group = QGroupBox("Target Platform")
        platform_layout = QFormLayout()
        
        self.target_os = QComboBox()
        self.target_os.addItems(["Linux", "Windows", "macOS", "Android"])
        platform_layout.addRow("Operating System:", self.target_os)
        
        self.requires_root = QCheckBox("Requires root/admin privileges")
        platform_layout.addRow("Privileges:", self.requires_root)
        
        platform_group.setLayout(platform_layout)
        layout.addWidget(platform_group)
        
        page.setLayout(layout)
        return page
    
    def create_summary_page(self) -> QWizardPage:
        """Step 5: Summary and Generation"""
        page = QWizardPage()
        page.setTitle("Summary")
        page.setSubTitle("Review and generate your module")
        
        layout = QVBoxLayout()
        
        # Summary display
        self.summary_display = QTextBrowser()
        self.summary_display.setMinimumHeight(400)
        layout.addWidget(self.summary_display)
        
        # Generation controls
        controls_layout = QHBoxLayout()
        
        self.use_ai_assist = QCheckBox("Use AI Assistant for code generation")
        self.use_ai_assist.setChecked(True)
        controls_layout.addWidget(self.use_ai_assist)
        
        controls_layout.addStretch()
        
        self.generate_btn = QPushButton("Generate Module Files")
        self.generate_btn.clicked.connect(self._generate_module_files)
        controls_layout.addWidget(self.generate_btn)
        
        layout.addWidget(QFrame())  # Spacer
        layout.addLayout(controls_layout)
        
        page.setLayout(layout)
        return page
    
    def _on_os_selection_changed(self, button):
        """Handle OS selection changes"""
        is_custom = button.property("value") == "custom"
        self.custom_base_edit.setEnabled(is_custom)
    
    def _add_config_mapping(self):
        """Add a new config mapping row"""
        row = self.config_mapping_table.rowCount()
        self.config_mapping_table.insertRow(row)
        
        # Add default items
        key_item = QTableWidgetItem("CPU_MODEL_NAME")
        value_item = QTableWidgetItem("Cortex-A76")
        flag_item = QTableWidgetItem("-mcpu=cortex-a76")
        
        self.config_mapping_table.setItem(row, 0, key_item)
        self.config_mapping_table.setItem(row, 1, value_item)
        self.config_mapping_table.setItem(row, 2, flag_item)
    
    def _add_default_config_mappings(self):
        """Add some default config mappings"""
        defaults = [
            ("SUPPORTS_NEON", "ON", "-mfpu=neon"),
            ("SUPPORTS_AVX2", "ON", "-mavx2"),
            ("CPU_CORES", "4", "BUILD_JOBS=4"),
        ]
        
        for key, value, flag in defaults:
            self._add_config_mapping()
            row = self.config_mapping_table.rowCount() - 1
            self.config_mapping_table.setItem(row, 0, QTableWidgetItem(key))
            self.config_mapping_table.setItem(row, 1, QTableWidgetItem(value))
            self.config_mapping_table.setItem(row, 2, QTableWidgetItem(flag))
    
    def _generate_module_files(self):
        """Generate the module files"""
        try:
            # Collect all wizard data
            self._collect_wizard_data()
            
            # Generate files
            target_dir = Path("targets") / self.module_data["module_name"].lower().replace(" ", "_")
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate each file
            self._generate_dockerfile(target_dir)
            self._generate_target_yml(target_dir)
            self._generate_config_module(target_dir)
            self._generate_profile_script(target_dir)
            
            # Show success message
            QMessageBox.information(
                self,
                "Module Generated",
                f"Module files have been generated in:\n{target_dir}\n\n"
                "You can now review and customize the files as needed."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Generation Error", f"Failed to generate module: {e}")
    
    def _collect_wizard_data(self):
        """Collect data from all wizard pages"""
        # Hardware identification
        self.module_data.update({
            "module_name": self.module_name_edit.text(),
            "architecture": self.arch_combo.currentText(),
            "sdk": self.sdk_combo.currentText(),
            "supported_boards": [line.strip() for line in self.boards_edit.toPlainText().split('\n') if line.strip()],
            "description": self.description_edit.toPlainText(),
        })
        
        # Docker environment
        selected_os = None
        for button in self.os_button_group.buttons():
            if button.isChecked():
                selected_os = button.property("value")
                break
        
        if selected_os == "custom":
            selected_os = self.custom_base_edit.text()
        
        self.module_data.update({
            "base_os": selected_os,
            "packages": [line.strip() for line in self.packages_edit.toPlainText().split('\n') if line.strip()],
            "setup_commands": self.commands_edit.toPlainText(),
        })
        
        # Configuration agent
        self.module_data.update({
            "cpu_flags": self.cpu_flags_edit.text(),
            "cmake_flags": self.cmake_flags_edit.text(),
            "optimization_level": self.optimization_level.currentText(),
            "config_mappings": self._get_config_mappings(),
        })
        
        # Profile script
        self.module_data.update({
            "detection_commands": self.detection_commands.toPlainText(),
            "target_os": self.target_os.currentText(),
            "requires_root": self.requires_root.isChecked(),
        })
    
    def _get_config_mappings(self) -> List[Dict[str, str]]:
        """Get config mappings from table"""
        mappings = []
        for row in range(self.config_mapping_table.rowCount()):
            key_item = self.config_mapping_table.item(row, 0)
            value_item = self.config_mapping_table.item(row, 1)
            flag_item = self.config_mapping_table.item(row, 2)
            
            if key_item and value_item and flag_item:
                mappings.append({
                    "key": key_item.text(),
                    "value": value_item.text(),
                    "flag": flag_item.text()
                })
        
        return mappings
    
    def _generate_dockerfile(self, target_dir: Path):
        """Generate Dockerfile"""
        dockerfile_content = f'''# Dockerfile for {self.module_data["module_name"]}
# Generated by LLM Cross-Compiler Framework Module Wizard
# Target Architecture: {self.module_data["architecture"]}

FROM {self.module_data["base_os"]} AS builder

# Metadata
LABEL maintainer="Community Contributor"
LABEL description="{self.module_data["description"]}"
LABEL target.architecture="{self.module_data["architecture"]}"
LABEL target.sdk="{self.module_data["sdk"]}"

# Environment
ENV DEBIAN_FRONTEND=noninteractive
ENV LLAMA_CPP_PATH=/usr/src/llama.cpp
ENV BUILD_CACHE_DIR=/build-cache

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
'''
        
        # Add packages
        for package in self.module_data["packages"]:
            dockerfile_content += f"        {package} \\\n"
        
        dockerfile_content += '''    && rm -rf /var/lib/apt/lists/*

'''
        
        # Add setup commands
        if self.module_data["setup_commands"].strip():
            dockerfile_content += "# Additional setup commands\n"
            dockerfile_content += self.module_data["setup_commands"]
            dockerfile_content += "\n\n"
        
        dockerfile_content += '''# Copy framework modules
WORKDIR /app
COPY modules/ ./modules/
RUN chmod +x modules/*.sh

# Set working directory
WORKDIR ${BUILD_CACHE_DIR}

# Default entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["interactive"]
'''
        
        with open(target_dir / "Dockerfile", "w") as f:
            f.write(dockerfile_content)
    
    def _generate_target_yml(self, target_dir: Path):
        """Generate target.yml configuration"""
        config = {
            "metadata": {
                "name": self.module_data["module_name"],
                "description": self.module_data["description"],
                "maintainer": "Community Contributor",
                "version": "1.0.0"
            },
            "supported_boards": self.module_data["supported_boards"],
            "docker": {
                "image_name": f"llm-framework/{self.module_data['module_name'].lower().replace(' ', '-')}",
                "build_context": ".",
                "dockerfile": "Dockerfile"
            },
            "modules": {
                "source": "modules/source_module.sh",
                "config": "modules/config_module.sh",
                "convert": "modules/convert_module.sh",
                "target": "modules/target_module.sh"
            },
            "requirements": {
                "docker_version": ">=20.10",
                "python_version": ">=3.10",
                "memory_gb": 8,
                "disk_gb": 20
            }
        }
        
        with open(target_dir / "target.yml", "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    def _generate_config_module(self, target_dir: Path):
        """Generate config_module.sh"""
        # Create modules directory
        modules_dir = target_dir / "modules"
        modules_dir.mkdir(exist_ok=True)
        
        config_content = f'''#!/bin/bash
# config_module.sh for {self.module_data["module_name"]}
# Generated by LLM Cross-Compiler Framework Module Wizard

set -euo pipefail

# Configuration
readonly BUILD_CACHE_DIR="${{BUILD_CACHE_DIR:-/build-cache}}"
readonly HARDWARE_CONFIG_FILE="${{BUILD_CACHE_DIR}}/target_hardware_config.txt"
readonly CMAKE_TOOLCHAIN_FILE="${{BUILD_CACHE_DIR}}/cross_compile_toolchain.cmake"

# Hardware configuration storage
declare -A HW_CONFIG

# Load hardware configuration
load_hardware_config() {{
    if [[ ! -f "$HARDWARE_CONFIG_FILE" ]]; then
        echo "Error: Hardware config file not found: $HARDWARE_CONFIG_FILE"
        exit 1
    fi
    
    while IFS='=' read -r key value; do
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        key=$(echo "$key" | tr -d ' \\t')
        value=$(echo "$value" | tr -d ' \\t' | sed 's/^"//;s/"$//')
        HW_CONFIG["$key"]="$value"
    done < <(grep -E '^[^#]*=' "$HARDWARE_CONFIG_FILE")
}}

# Generate CMake toolchain
generate_cmake_toolchain() {{
    echo "Generating CMake toolchain for {self.module_data['architecture']}"
    
    cat > "$CMAKE_TOOLCHAIN_FILE" << 'EOF'
# Generated CMake Toolchain for {self.module_data["module_name"]}
SET(CMAKE_SYSTEM_NAME Linux)
SET(CMAKE_SYSTEM_PROCESSOR {self.module_data["architecture"]})

'''
        
        # Add architecture-specific compiler settings
        if self.module_data["architecture"] == "aarch64":
            config_content += '''# Cross-compilation for AArch64
SET(CMAKE_C_COMPILER   /usr/bin/aarch64-linux-gnu-gcc)
SET(CMAKE_CXX_COMPILER /usr/bin/aarch64-linux-gnu-g++)

'''
        
        config_content += f'''# Compiler flags
SET(CMAKE_C_FLAGS "${{CMAKE_C_FLAGS}} {self.module_data["optimization_level"]} {self.module_data["cpu_flags"]}")
SET(CMAKE_CXX_FLAGS "${{CMAKE_CXX_FLAGS}} {self.module_data["optimization_level"]} {self.module_data["cpu_flags"]} -std=c++17")

# SDK-specific flags
{self.module_data["cmake_flags"]}

EOF
}}

# Main execution
main() {{
    echo "Starting {self.module_data['module_name']} configuration"
    
    load_hardware_config
    generate_cmake_toolchain
    
    echo "Configuration completed successfully"
}}

main "$@"
'''
        
        with open(modules_dir / "config_module.sh", "w") as f:
            f.write(config_content)
        
        # Make executable
        (modules_dir / "config_module.sh").chmod(0o755)
    
    def _generate_profile_script(self, target_dir: Path):
        """Generate hardware profile detection script"""
        script_content = f'''#!/bin/bash
# Hardware Profile Generator for {self.module_data["module_name"]}
# Generated by LLM Cross-Compiler Framework Module Wizard
# Run this script on your target hardware to generate target_hardware_config.txt

set -euo pipefail

OUTPUT_FILE="target_hardware_config.txt"

echo "Hardware Profile Generator for {self.module_data['module_name']}"
echo "=================================================="

# Clear output file
> "$OUTPUT_FILE"

echo "# Hardware Profile for {self.module_data['module_name']}" >> "$OUTPUT_FILE"
echo "# Generated on $(date)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Detection functions
run_probe() {{
    local key="$1"
    local command="$2"
    
    local result=$(eval "$command" 2>/dev/null || echo "UNKNOWN")
    echo "${{key}}=${{result}}" >> "$OUTPUT_FILE"
}}

# Basic system information
echo "# System Information" >> "$OUTPUT_FILE"
run_probe "OS_NAME" "lsb_release -d -s 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d'=' -f2 | tr -d '\"'"
run_probe "KERNEL_VERSION" "uname -r"
run_probe "ARCHITECTURE" "uname -m"

# CPU information
echo "" >> "$OUTPUT_FILE"
echo "# CPU Information" >> "$OUTPUT_FILE"
run_probe "CPU_MODEL_NAME" "lscpu | grep 'Model name' | awk -F: '{{print \\$2}}' | xargs"
run_probe "CPU_CORES" "nproc"
run_probe "CPU_CACHE_L2" "lscpu | grep 'L2 cache' | awk '{{print \\$3}}' | tr -d 'K'"

'''
        
        # Add custom detection commands
        if self.module_data["detection_commands"].strip():
            script_content += "\n# Custom hardware detection\n"
            for line in self.module_data["detection_commands"].split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Convert command to probe format
                    key = f"CUSTOM_{len(script_content.split('run_probe'))}"
                    script_content += f'run_probe "{key}" "{line}"\n'
        
        script_content += f'''
echo ""
echo "Hardware profile generated: $OUTPUT_FILE"
echo "Please upload this file to the LLM Cross-Compiler Framework GUI"
echo ""
echo "Profile contents:"
cat "$OUTPUT_FILE"
'''
        
        with open(target_dir / "generate_profile.sh", "w") as f:
            f.write(script_content)
        
        # Make executable
        (target_dir / "generate_profile.sh").chmod(0o755)
    
    def initializePage(self, page_id: int):
        """Update page content when entering"""
        if page_id == self.PAGE_SUMMARY:
            self._update_summary_display()
    
    def _update_summary_display(self):
        """Update the summary display with current wizard data"""
        self._collect_wizard_data()
        
        summary_html = f"""
        <h2>Module Summary: {self.module_data.get('module_name', 'Unknown')}</h2>
        
        <h3>Hardware Target</h3>
        <ul>
            <li><b>Architecture:</b> {self.module_data.get('architecture', 'Unknown')}</li>
            <li><b>SDK/Backend:</b> {self.module_data.get('sdk', 'Unknown')}</li>
            <li><b>Supported Boards:</b> {', '.join(self.module_data.get('supported_boards', []))}</li>
        </ul>
        
        <h3>Docker Configuration</h3>
        <ul>
            <li><b>Base Image:</b> {self.module_data.get('base_os', 'Unknown')}</li>
            <li><b>Packages:</b> {len(self.module_data.get('packages', []))} packages</li>
            <li><b>Custom Setup:</b> {'Yes' if self.module_data.get('setup_commands', '').strip() else 'No'}</li>
        </ul>
        
        <h3>Optimizations</h3>
        <ul>
            <li><b>CPU Flags:</b> {self.module_data.get('cpu_flags', 'None')}</li>
            <li><b>CMake Flags:</b> {self.module_data.get('cmake_flags', 'None')}</li>
            <li><b>Optimization Level:</b> {self.module_data.get('optimization_level', '-O3')}</li>
        </ul>
        
        <h3>Generated Files</h3>
        <ul>
            <li>📄 <b>Dockerfile</b> - Build environment configuration</li>
            <li>📄 <b>target.yml</b> - Module metadata and configuration</li>
            <li>📄 <b>modules/config_module.sh</b> - Hardware-specific optimization logic</li>
            <li>📄 <b>generate_profile.sh</b> - Hardware detection script for target systems</li>
        </ul>
        
        <p><b>Next Steps:</b></p>
        <ol>
            <li>Review and customize the generated files</li>
            <li>Test the module with a sample model</li>
            <li>Share with the community</li>
        </ol>
        """
        
        self.summary_display.setHtml(summary_html)


# ============================================================================
# MAIN ORCHESTRATOR GUI
# ============================================================================

class MainOrchestrator(QMainWindow):
    """Main LLM Cross-Compiler Framework GUI"""
    
    def __init__(self):
        super().__init__()
        self.config = FrameworkConfig()
        self.docker_manager = DockerManager()
        self.settings = QSettings("LLMFramework", "Orchestrator")
        
        # Initialize UI
        self.init_ui()
        self.init_docker()
        self.setup_connections()
        
        # Load saved settings
        self.load_settings()
        
        # Set up auto-refresh
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_targets)
        self.refresh_timer.start(30000)  # Refresh every 30 seconds
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle(f"{self.config.app_name} v{self.config.version}")
        self.setMinimumSize(1200, 800)
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout with splitter
        main_layout = QHBoxLayout(central_widget)
        main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(main_splitter)
        
        # Left panel: Targets and controls
        left_panel = self.create_left_panel()
        main_splitter.addWidget(left_panel)
        
        # Right panel: Main workspace
        right_panel = self.create_right_panel()
        main_splitter.addWidget(right_panel)
        
        # Set splitter proportions
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
    def create_menu_bar(self):
        """Create the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        new_module_action = QAction("&New Module...", self)
        new_module_action.setShortcut(QKeySequence.New)
        new_module_action.triggered.connect(self.show_module_creation_wizard)
        file_menu.addAction(new_module_action)
        
        file_menu.addSeparator()
        
        import_profile_action = QAction("&Import Hardware Profile...", self)
        import_profile_action.triggered.connect(self.import_hardware_profile)
        file_menu.addAction(import_profile_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        refresh_action = QAction("&Refresh Targets", self)
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.triggered.connect(self.refresh_targets)
        tools_menu.addAction(refresh_action)
        
        docker_status_action = QAction("&Docker Status", self)
        docker_status_action.triggered.connect(self.show_docker_status)
        tools_menu.addAction(docker_status_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_left_panel(self) -> QWidget:
        """Create the left control panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Available targets
        targets_group = QGroupBox("Available Targets")
        targets_layout = QVBoxLayout(targets_group)
        
        self.targets_tree = QTreeWidget()
        self.targets_tree.setHeaderLabels(["Target", "Status", "Version"])
        self.targets_tree.itemDoubleClicked.connect(self.on_target_selected)
        targets_layout.addWidget(self.targets_tree)
        
        # Target controls
        target_controls = QHBoxLayout()
        self.refresh_targets_btn = QPushButton("Refresh")
        self.refresh_targets_btn.clicked.connect(self.refresh_targets)
        target_controls.addWidget(self.refresh_targets_btn)
        
        self.new_module_btn = QPushButton("New Module...")
        self.new_module_btn.clicked.connect(self.show_module_creation_wizard)
        target_controls.addWidget(self.new_module_btn)
        
        targets_layout.addLayout(target_controls)
        layout.addWidget(targets_group)
        
        # Hardware profiles
        profiles_group = QGroupBox("Hardware Profiles")
        profiles_layout = QVBoxLayout(profiles_group)
        
        self.profiles_list = QListWidget()
        profiles_layout.addWidget(self.profiles_list)
        
        profile_controls = QHBoxLayout()
        self.import_profile_btn = QPushButton("Import...")
        self.import_profile_btn.clicked.connect(self.import_hardware_profile)
        profile_controls.addWidget(self.import_profile_btn)
        
        self.delete_profile_btn = QPushButton("Delete")
        self.delete_profile_btn.clicked.connect(self.delete_hardware_profile)
        profile_controls.addWidget(self.delete_profile_btn)
        
        profiles_layout.addLayout(profile_controls)
        layout.addWidget(profiles_group)
        
        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        self.start_build_btn = QPushButton("Start Build")
        self.start_build_btn.clicked.connect(self.start_build)
        self.start_build_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        actions_layout.addWidget(self.start_build_btn)
        
        self.stop_all_btn = QPushButton("Stop All")
        self.stop_all_btn.clicked.connect(self.stop_all_builds)
        self.stop_all_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; }")
        actions_layout.addWidget(self.stop_all_btn)
        
        layout.addWidget(actions_group)
        
        layout.addStretch()
        return panel
    
    def create_right_panel(self) -> QWidget:
        """Create the right workspace panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Tab widget for different views
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Build configuration tab
        self.build_config_tab = self.create_build_config_tab()
        self.tab_widget.addTab(self.build_config_tab, "Build Configuration")
        
        # Build monitor tab
        self.build_monitor_tab = self.create_build_monitor_tab()
        self.tab_widget.addTab(self.build_monitor_tab, "Build Monitor")
        
        # Framework settings tab
        self.settings_tab = self.create_settings_tab()
        self.tab_widget.addTab(self.settings_tab, "Settings")
        
        return panel
    
    def create_build_config_tab(self) -> QWidget:
        """Create the build configuration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Model selection
        model_group = QGroupBox("Model Configuration")
        model_layout = QFormLayout(model_group)
        
        self.model_path_edit = QLineEdit()
        model_path_layout = QHBoxLayout()
        model_path_layout.addWidget(self.model_path_edit)
        
        self.browse_model_btn = QPushButton("Browse...")
        self.browse_model_btn.clicked.connect(self.browse_model_path)
        model_path_layout.addWidget(self.browse_model_btn)
        
        model_layout.addRow("Model Path:", model_path_layout)
        
        self.model_name_edit = QLineEdit()
        self.model_name_edit.setPlaceholderText("e.g., granite-h-350m")
        model_layout.addRow("Model Name:", self.model_name_edit)
        
        layout.addWidget(model_group)
        
        # Target selection
        target_group = QGroupBox("Target Configuration")
        target_layout = QFormLayout(target_group)
        
        self.target_combo = QComboBox()
        target_layout.addRow("Target Architecture:", self.target_combo)
        
        self.quantization_combo = QComboBox()
        self.quantization_combo.addItems([
            "Q4_0", "Q4_1", "Q5_0", "Q5_1", "Q8_0",
            "Q2_K", "Q3_K_S", "Q3_K_M", "Q4_K_S", "Q4_K_M",
            "Q5_K_S", "Q5_K_M", "Q6_K"
        ])
        self.quantization_combo.setCurrentText("Q4_K_M")
        target_layout.addRow("Quantization:", self.quantization_combo)
        
        self.hardware_profile_combo = QComboBox()
        target_layout.addRow("Hardware Profile:", self.hardware_profile_combo)
        
        layout.addWidget(target_group)
        
        # Build options
        options_group = QGroupBox("Build Options")
        options_layout = QFormLayout(options_group)
        
        self.clean_build_check = QCheckBox("Clean build (remove previous artifacts)")
        options_layout.addRow("Options:", self.clean_build_check)
        
        self.parallel_jobs_spin = QSpinBox()
        self.parallel_jobs_spin.setRange(1, 16)
        self.parallel_jobs_spin.setValue(4)
        options_layout.addRow("Parallel Jobs:", self.parallel_jobs_spin)
        
        layout.addWidget(options_group)
        
        layout.addStretch()
        return tab
    
    def create_build_monitor_tab(self) -> QWidget:
        """Create the build monitor tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Build queue/history
        queue_group = QGroupBox("Build Queue & History")
        queue_layout = QVBoxLayout(queue_group)
        
        self.build_queue_table = QTableWidget(0, 6)
        self.build_queue_table.setHorizontalHeaderLabels([
            "Job ID", "Model", "Target", "Quantization", "Status", "Progress"
        ])
        queue_layout.addWidget(self.build_queue_table)
        
        layout.addWidget(queue_group)
        
        # Live output
        output_group = QGroupBox("Build Output")
        output_layout = QVBoxLayout(output_group)
        
        self.build_output = QTextEdit()
        self.build_output.setReadOnly(True)
        self.build_output.setFont(QFont("Courier", 9))
        self.build_output.setStyleSheet("QTextEdit { background-color: #1e1e1e; color: #ffffff; }")
        output_layout.addWidget(self.build_output)
        
        # Output controls
        output_controls = QHBoxLayout()
        
        self.clear_output_btn = QPushButton("Clear")
        self.clear_output_btn.clicked.connect(self.build_output.clear)
        output_controls.addWidget(self.clear_output_btn)
        
        self.save_log_btn = QPushButton("Save Log...")
        self.save_log_btn.clicked.connect(self.save_build_log)
        output_controls.addWidget(self.save_log_btn)
        
        output_controls.addStretch()
        
        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        output_controls.addWidget(self.auto_scroll_check)
        
        output_layout.addLayout(output_controls)
        layout.addWidget(output_group)
        
        return tab
    
    def create_settings_tab(self) -> QWidget:
        """Create the settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Paths configuration
        paths_group = QGroupBox("Paths Configuration")
        paths_layout = QFormLayout(paths_group)
        
        self.models_dir_edit = QLineEdit()
        self.models_dir_edit.setText(str(self.config.models_dir))
        models_dir_layout = QHBoxLayout()
        models_dir_layout.addWidget(self.models_dir_edit)
        browse_models_btn = QPushButton("Browse...")
        browse_models_btn.clicked.connect(lambda: self.browse_directory(self.models_dir_edit))
        models_dir_layout.addWidget(browse_models_btn)
        paths_layout.addRow("Models Directory:", models_dir_layout)
        
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setText(str(self.config.output_dir))
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(self.output_dir_edit)
        browse_output_btn = QPushButton("Browse...")
        browse_output_btn.clicked.connect(lambda: self.browse_directory(self.output_dir_edit))
        output_dir_layout.addWidget(browse_output_btn)
        paths_layout.addRow("Output Directory:", output_dir_layout)
        
        layout.addWidget(paths_group)
        
        # Docker configuration
        docker_group = QGroupBox("Docker Configuration")
        docker_layout = QFormLayout(docker_group)
        
        self.docker_compose_edit = QLineEdit()
        self.docker_compose_edit.setText(str(self.config.docker_compose_file))
        docker_layout.addRow("Docker Compose File:", self.docker_compose_edit)
        
        layout.addWidget(docker_group)
        
        # Framework configuration
        framework_group = QGroupBox("Framework Configuration")
        framework_layout = QFormLayout(framework_group)
        
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level_combo.setCurrentText("INFO")
        framework_layout.addRow("Log Level:", self.log_level_combo)
        
        self.auto_refresh_check = QCheckBox("Auto-refresh targets")
        self.auto_refresh_check.setChecked(True)
        framework_layout.addRow("Options:", self.auto_refresh_check)
        
        layout.addWidget(framework_group)
        
        # Save settings button
        save_settings_btn = QPushButton("Save Settings")
        save_settings_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_settings_btn)
        
        layout.addStretch()
        return tab
    
    def apply_dark_theme(self):
        """Apply dark theme to the application"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                border: 2px solid #555555;
                border-radius: 5px;
                margin-top: 1ex;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 5px 15px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #353535;
            }
            QComboBox, QLineEdit, QSpinBox {
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 3px;
                min-height: 20px;
            }
            QTreeWidget, QListWidget, QTableWidget {
                background-color: #353535;
                border: 1px solid #555555;
                alternate-background-color: #404040;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 5px 10px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #505050;
            }
        """)
    
    def init_docker(self):
        """Initialize Docker connection"""
        if self.docker_manager.initialize_docker():
            self.statusBar().showMessage("Docker connected")
        else:
            self.statusBar().showMessage("Docker connection failed")
            QMessageBox.warning(
                self,
                "Docker Connection",
                "Failed to connect to Docker. Please ensure Docker is running."
            )
    
    def setup_connections(self):
        """Set up signal connections"""
        # Docker manager signals
        self.docker_manager.build_progress.connect(self.on_build_progress)
        self.docker_manager.build_output.connect(self.on_build_output)
        self.docker_manager.build_completed.connect(self.on_build_completed)
    
    def refresh_targets(self):
        """Refresh the available targets list"""
        self.targets_tree.clear()
        
        try:
            targets = self.docker_manager.get_available_targets()
            
            for target in targets:
                item = QTreeWidgetItem([
                    target.name,
                    target.status,
                    target.version
                ])
                item.setData(0, Qt.UserRole, target)
                self.targets_tree.addTopLevelItem(item)
            
            # Update target combo
            self.target_combo.clear()
            self.target_combo.addItems([t.name for t in targets])
            
            self.statusBar().showMessage(f"Found {len(targets)} targets")
            
        except Exception as e:
            logging.error(f"Failed to refresh targets: {e}")
            self.statusBar().showMessage("Failed to refresh targets")
    
    def show_module_creation_wizard(self):
        """Show the module creation wizard"""
        wizard = ModuleCreationWizard(self)
        if wizard.exec() == QDialog.Accepted:
            self.refresh_targets()
    
    def import_hardware_profile(self):
        """Import a hardware profile"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Hardware Profile",
            str(self.config.configs_dir),
            "Config files (*.txt *.conf);;All files (*)"
        )
        
        if file_path:
            try:
                # Copy to configs directory
                target_path = self.config.configs_dir / Path(file_path).name
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                import shutil
                shutil.copy2(file_path, target_path)
                
                # Add to profiles list
                self.profiles_list.addItem(Path(file_path).name)
                self.hardware_profile_combo.addItem(Path(file_path).name)
                
                self.statusBar().showMessage(f"Imported profile: {Path(file_path).name}")
                
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import profile: {e}")
    
    def delete_hardware_profile(self):
        """Delete selected hardware profile"""
        current_item = self.profiles_list.currentItem()
        if current_item:
            reply = QMessageBox.question(
                self,
                "Delete Profile",
                f"Are you sure you want to delete '{current_item.text()}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                try:
                    profile_path = self.config.configs_dir / current_item.text()
                    if profile_path.exists():
                        profile_path.unlink()
                    
                    # Remove from UI
                    row = self.profiles_list.row(current_item)
                    self.profiles_list.takeItem(row)
                    
                    # Remove from combo
                    index = self.hardware_profile_combo.findText(current_item.text())
                    if index >= 0:
                        self.hardware_profile_combo.removeItem(index)
                    
                    self.statusBar().showMessage(f"Deleted profile: {current_item.text()}")
                    
                except Exception as e:
                    QMessageBox.critical(self, "Delete Error", f"Failed to delete profile: {e}")
    
    def start_build(self):
        """Start a new build job"""
        # Validate inputs
        if not self.model_path_edit.text().strip():
            QMessageBox.warning(self, "Build Error", "Please select a model path")
            return
        
        if not self.model_name_edit.text().strip():
            QMessageBox.warning(self, "Build Error", "Please enter a model name")
            return
        
        if self.target_combo.currentIndex() < 0:
            QMessageBox.warning(self, "Build Error", "Please select a target")
            return
        
        # Create build job
        job_id = f"build_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        build_job = BuildJob(
            id=job_id,
            model_name=self.model_name_edit.text().strip(),
            target=self.target_combo.currentText(),
            quantization=self.quantization_combo.currentText(),
            status="queued"
        )
        
        # Add to queue table
        self.add_build_to_queue(build_job)
        
        # Start build
        self.docker_manager.start_build(build_job)
        
        self.statusBar().showMessage(f"Started build: {job_id}")
    
    def add_build_to_queue(self, build_job: BuildJob):
        """Add build job to the queue table"""
        row = self.build_queue_table.rowCount()
        self.build_queue_table.insertRow(row)
        
        self.build_queue_table.setItem(row, 0, QTableWidgetItem(build_job.id))
        self.build_queue_table.setItem(row, 1, QTableWidgetItem(build_job.model_name))
        self.build_queue_table.setItem(row, 2, QTableWidgetItem(build_job.target))
        self.build_queue_table.setItem(row, 3, QTableWidgetItem(build_job.quantization))
        self.build_queue_table.setItem(row, 4, QTableWidgetItem(build_job.status))
        
        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setValue(build_job.progress)
        self.build_queue_table.setCellWidget(row, 5, progress_bar)
    
    def on_build_progress(self, build_id: str, progress: int):
        """Handle build progress updates"""
        # Find the build in the table and update progress
        for row in range(self.build_queue_table.rowCount()):
            if self.build_queue_table.item(row, 0).text() == build_id:
                progress_bar = self.build_queue_table.cellWidget(row, 5)
                if progress_bar:
                    progress_bar.setValue(progress)
                break
    
    def on_build_output(self, build_id: str, output_line: str):
        """Handle build output"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_line = f"[{timestamp}] [{build_id}] {output_line}"
        
        self.build_output.append(formatted_line)
        
        if self.auto_scroll_check.isChecked():
            scrollbar = self.build_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def on_build_completed(self, build_id: str, success: bool, output_path: str):
        """Handle build completion"""
        # Update status in table
        for row in range(self.build_queue_table.rowCount()):
            if self.build_queue_table.item(row, 0).text() == build_id:
                status = "completed" if success else "failed"
                self.build_queue_table.setItem(row, 4, QTableWidgetItem(status))
                
                progress_bar = self.build_queue_table.cellWidget(row, 5)
                if progress_bar:
                    progress_bar.setValue(100 if success else 0)
                break
        
        # Show notification
        if success:
            QMessageBox.information(
                self,
                "Build Completed",
                f"Build {build_id} completed successfully!\n\nOutput: {output_path}"
            )
        else:
            QMessageBox.critical(
                self,
                "Build Failed",
                f"Build {build_id} failed. Check the output for details."
            )
        
        self.statusBar().showMessage(f"Build {build_id} {'completed' if success else 'failed'}")
    
    def stop_all_builds(self):
        """Stop all running builds"""
        reply = QMessageBox.question(
            self,
            "Stop Builds",
            "Are you sure you want to stop all running builds?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Implementation would stop Docker processes
            self.statusBar().showMessage("Stopping all builds...")
    
    def browse_model_path(self):
        """Browse for model path"""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Model Directory",
            str(self.config.models_dir)
        )
        
        if path:
            self.model_path_edit.setText(path)
            
            # Auto-fill model name from directory name
            if not self.model_name_edit.text():
                self.model_name_edit.setText(Path(path).name)
    
    def browse_directory(self, line_edit: QLineEdit):
        """Browse for directory"""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            line_edit.text()
        )
        
        if path:
            line_edit.setText(path)
    
    def save_build_log(self):
        """Save build log to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Build Log",
            f"build_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text files (*.txt);;All files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(self.build_output.toPlainText())
                
                self.statusBar().showMessage(f"Build log saved: {file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save log: {e}")
    
    def on_target_selected(self, item: QTreeWidgetItem, column: int):
        """Handle target selection"""
        target = item.data(0, Qt.UserRole)
        if target:
            self.target_combo.setCurrentText(target.name)
    
    def show_docker_status(self):
        """Show Docker status dialog"""
        try:
            if self.docker_manager.docker_client:
                info = self.docker_manager.docker_client.info()
                containers = self.docker_manager.docker_client.containers.list(all=True)
                
                status_text = f"""
Docker Status: Connected
Version: {info.get('ServerVersion', 'Unknown')}
Containers: {len(containers)}
Running: {len([c for c in containers if c.status == 'running'])}

Images: {len(self.docker_manager.docker_client.images.list())}
"""
            else:
                status_text = "Docker Status: Disconnected"
            
            QMessageBox.information(self, "Docker Status", status_text)
            
        except Exception as e:
            QMessageBox.critical(self, "Docker Error", f"Failed to get Docker status: {e}")
    
    def show_about(self):
        """Show about dialog"""
        about_text = f"""
<h2>{self.config.app_name}</h2>
<p>Version: {self.config.version}</p>
<p>A professional framework for cross-compiling Large Language Models for edge hardware.</p>

<h3>Features:</h3>
<ul>
<li>Multi-architecture support (ARM, x86, RISC-V)</li>
<li>Automated hardware optimization</li>
<li>Community-driven module system</li>
<li>Professional Docker-based builds</li>
<li>GUI and CLI interfaces</li>
</ul>

<p>Developed with ❤️ for the AI community</p>
"""
        
        QMessageBox.about(self, "About", about_text)
    
    def load_settings(self):
        """Load saved settings"""
        try:
            # Restore window geometry
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
            
            # Restore paths
            models_dir = self.settings.value("models_dir")
            if models_dir:
                self.models_dir_edit.setText(models_dir)
            
            output_dir = self.settings.value("output_dir")
            if output_dir:
                self.output_dir_edit.setText(output_dir)
            
            # Restore options
            log_level = self.settings.value("log_level", "INFO")
            self.log_level_combo.setCurrentText(log_level)
            
            auto_refresh = self.settings.value("auto_refresh", True, type=bool)
            self.auto_refresh_check.setChecked(auto_refresh)
            
        except Exception as e:
            logging.error(f"Failed to load settings: {e}")
    
    def save_settings(self):
        """Save current settings"""
        try:
            # Save window geometry
            self.settings.setValue("geometry", self.saveGeometry())
            
            # Save paths
            self.settings.setValue("models_dir", self.models_dir_edit.text())
            self.settings.setValue("output_dir", self.output_dir_edit.text())
            
            # Save options
            self.settings.setValue("log_level", self.log_level_combo.currentText())
            self.settings.setValue("auto_refresh", self.auto_refresh_check.isChecked())
            
            self.statusBar().showMessage("Settings saved")
            
        except Exception as e:
            QMessageBox.critical(self, "Settings Error", f"Failed to save settings: {e}")
    
    def closeEvent(self, event):
        """Handle application close"""
        self.save_settings()
        event.accept()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main application entry point"""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("LLM Cross-Compiler Framework")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("LLMFramework")
    
    # Create and show main window
    window = MainOrchestrator()
    window.show()
    
    # Refresh targets on startup
    QTimer.singleShot(1000, window.refresh_targets)
    
    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()