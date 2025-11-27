#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Module Generator (Core Logic)
DIREKTIVE: Goldstandard, Separation of Concerns.

Zweck:
Zentrale Logik zur Generierung neuer Hardware-Target-Module.
Wird sowohl von der GUI (Wizard) als auch der CLI (Command) genutzt.
Verarbeitet Templates aus 'targets/_template/' und füllt diese mit
konfigurationsspezifischen Daten.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml

from orchestrator.utils.logging import get_logger
from orchestrator.utils.helpers import ensure_directory

class ModuleGenerator:
    """
    Generates file structure and content for new hardware targets.
    Uses a template-based approach to ensure consistency across all modules.
    """
    
    def __init__(self, targets_dir: Path):
        """
        Initialize the ModuleGenerator.
        
        Args:
            targets_dir: Base directory where targets are stored (e.g. /app/targets)
        """
        self.logger = get_logger(__name__)
        self.targets_dir = targets_dir
        
        # Template Verzeichnis liegt parallel zu den Targets
        # Wir suchen es relativ zum targets_dir oder via absolutem Fallback
        self.template_dir = targets_dir / "_template"

        if not self.template_dir.exists():
             # Fallback für Development-Umgebung
             possible_path = Path(__file__).parent.parent.parent / "targets" / "_template"
             if possible_path.exists():
                 self.template_dir = possible_path
             else:
                 self.logger.warning(f"Template directory not found at {self.template_dir} or {possible_path}")

    def generate_module(self, data: Dict[str, Any]) -> Path:
        """
        Generate a complete module from configuration data.
        
        Args:
            data: Dictionary containing configuration keys:
                  - module_name (str): Display name of the module
                  - architecture (str): CPU Arch (aarch64, x86_64)
                  - sdk (str): Associated SDK (cuda, rknn, none)
                  - base_os (str): Docker base image
                  - packages (List[str] or str): Apt packages
                  - cpu_flags (str): GCC optimization flags
                  - cmake_flags (str): CMake build flags
                  - quantization_logic (str): Bash case block for build.sh
                  - setup_commands (str): Custom Dockerfile commands
                  - detection_commands (str): Commands for profile script
        
        Returns:
            Path: Path to the created module directory
        """
        # Slugify name for folder
        module_slug = data["module_name"].lower().replace(" ", "_")
        target_dir = self.targets_dir / module_slug
        
        self.logger.info(f"Generating new target module: '{data['module_name']}' at {target_dir}")
        
        try:
            # 1. Create Directory Structure
            # ========================================================================
            ensure_directory(target_dir)
            ensure_directory(target_dir / "modules")
            ensure_directory(target_dir / "scripts")
            
            # 2. Generate Files via Template Processing
            # ========================================================================
            
            # Core Configuration
            self._process_template("target.yml", target_dir, data)
            
            # Container Definition
            self._process_template("Dockerfile", target_dir, data)
            
            # Build Modules (Shell Scripts)
            self._process_template("modules/config_module.sh", target_dir, data)
            self._process_template("modules/source_module.sh", target_dir, data)
            
            # NEU: Das intelligente Build-Skript (Dispatcher)
            self._write_build_script(target_dir, data)
            
            # Specialized Modules (Optional copy if template exists)
            # Diese werden nur kopiert, wenn sie im Template-Ordner existieren
            self._process_template("modules/rknn_module.sh", target_dir, data)
            self._process_template("modules/rkllm_module.sh", target_dir, data)
            self._process_template("modules/benchmark_module.sh", target_dir, data)
            
            # 3. Generate Helper Scripts (Dynamic)
            # ========================================================================
            self._write_profile_script(target_dir, data)
            
            # 4. Create Placeholder/Fallback Modules
            # ========================================================================
            self._write_standard_modules(target_dir)
            
            self.logger.info(f"Module generation for '{data['module_name']}' completed successfully.")
            return target_dir
            
        except Exception as e:
            self.logger.error(f"Failed to generate module: {e}")
            raise e

    def _process_template(self, filename: str, target_dir: Path, data: Dict[str, Any]):
        """
        Reads a template file, replaces placeholders with data, and writes to target.
        Handles both file content replacement and YAML parsing.
        """
        src = self.template_dir / filename
        dst = target_dir / filename
        
        if not src.exists():
            # Das ist kein Fehler, manche Templates (wie rkllm_module) sind optional
            self.logger.debug(f"Skipping optional template {filename} (not found)")
            return

        try:
            content = src.read_text(encoding="utf-8")
            
            # Prepare Data for Replacements
            packages = data.get("packages", [])
            if isinstance(packages, str): packages = packages.split()
            packages_str = " \\\n        ".join(packages)
            
            # Define Replacements Map
            # Keys must match [PLACEHOLDERS] in templates
            replacements = {
                "[MODULE_NAME]": data.get("module_name", "Unknown"),
                "[Hardware-Familie]": data.get("module_name", "Unknown"),
                "[IHRE_ARCHITEKTUR]": data.get("architecture", "aarch64"),
                "[Hersteller]": "Community",
                "debian:bookworm-slim": data.get("base_os", "debian:bookworm-slim"),
                "{packages_str}": packages_str,
                # Code Injection
                "# [SDK_SETUP_COMMANDS]": data.get("setup_commands", ""),
                "[QUANTIZATION_LOGIC]": data.get("quantization_logic", ""),
                "# [PACKAGING_COMMANDS]": data.get("packaging_commands", "cp -r build/* $OUTPUT_DIR/"),
                "[CPU_FLAGS]": data.get("cpu_flags", ""),
                "[CMAKE_FLAGS]": data.get("cmake_flags", "")
            }
            
            # Apply Replacements
            for key, value in replacements.items():
                if value is not None:
                    content = content.replace(key, str(value))
            
            # Write Output
            # Special handling for YAML to ensure validity if needed, but string replacement usually safer for comments
            if dst.suffix == ".yml":
                # We try to parse and update nicely, fall back to string replace if it fails
                try:
                    self._update_yaml_config(content, dst, data)
                except:
                    self._write_file(dst, content)
            else:
                self._write_file(dst, content)
                
            # Set Permissions for Scripts
            if dst.suffix == ".sh":
                self._make_executable(dst)
                
        except Exception as e:
            self.logger.error(f"Error processing template {filename}: {e}")

    def _update_yaml_config(self, template_content: str, dst: Path, data: Dict[str, Any]):
        """Parses YAML content, updates fields structurally, and saves."""
        config = yaml.safe_load(template_content)
        
        # Update Metadata
        if "metadata" in config:
            config["metadata"]["name"] = data["module_name"]
            config["metadata"]["architecture_family"] = data["architecture"]
            config["metadata"]["sdk"] = data.get("sdk", "none")
            config["metadata"]["description"] = data.get("description", "")
        
        # Update Docker Image Name
        if "docker" in config:
            safe_name = data["module_name"].lower().replace(" ", "-")
            config["docker"]["image_name"] = f"llm-framework/{safe_name}"
        
        with open(dst, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    def _write_build_script(self, target_dir: Path, data: Dict[str, Any]):
        """
        Generates the intelligent 'build.sh' dispatcher script.
        This uses the specific template for build.sh if available, or generates it.
        """
        # Check if we have a template first
        src = self.template_dir / "modules/build.sh"
        if src.exists():
            self._process_template("modules/build.sh", target_dir, data)
            return

        # Fallback: Generate from code if template missing
        quant_logic = data.get("quantization_logic", "")
        if not quant_logic:
            quant_logic = """
    "FP16")
        echo ">> Default FP16 Build (No Quantization)"
        # Standard build commands would go here
        ;;
    *)
        echo ">> Unknown Quantization: $QUANT_TYPE. Defaulting to FP16."
        ;;
"""

        content = f'''#!/bin/bash
# build.sh for {data["module_name"]}
# Generated by LLM Cross-Compiler Framework (ModuleGenerator)
#
# Environment Variables:
# $MODEL_SOURCE    - Path to input model
# $QUANTIZATION    - Target Quantization (e.g. Q4_K_M, INT8)
# $OUTPUT_DIR      - Destination for artifacts
# $BUILD_JOBS      - Number of parallel jobs
# $MODEL_TASK      - LLM, VOICE, or VLM

set -euo pipefail

WORK_DIR="${{BUILD_CACHE_DIR:-/build-cache}}"
OUTPUT_DIR="${{WORK_DIR}}/output"
mkdir -p "$OUTPUT_DIR"

echo "=== Build Started: {data['module_name']} ==="
echo "Model: $MODEL_SOURCE"
echo "Task:  ${{MODEL_TASK:-LLM}}"
echo "Quantization: ${{QUANTIZATION:-None}}"

# --- SDK SETUP ---
# {data.get("setup_commands", "")}

# --- CONVERSION & QUANTIZATION LOGIC ---
QUANT_TYPE="${{QUANTIZATION:-FP16}}"

case "$QUANT_TYPE" in
{quant_logic}
esac

# --- PACKAGING ---
echo "=== Packaging Artifacts ==="
cd "$OUTPUT_DIR" && tar -czf "deployment.tar.gz" ./*
echo "Build completed successfully."
'''
        dst = target_dir / "modules" / "build.sh"
        self._write_file(dst, content)
        self._make_executable(dst)

    def _write_profile_script(self, target_dir: Path, data: Dict[str, Any]):
        """Generates the hardware probe script for the target."""
        content = f'''#!/bin/bash
# Hardware Profile Generator for {data["module_name"]}
# Run this on the target hardware to generate a config for the framework.

OUTPUT_FILE="target_hardware_config.txt"
echo "# Profile for {data['module_name']}" > "$OUTPUT_FILE"

# Detection Commands
{data.get("detection_commands", "lscpu >> $OUTPUT_FILE")}

echo "Generated $OUTPUT_FILE"
'''
        dst = target_dir / "generate_profile.sh"
        self._write_file(dst, content)
        self._make_executable(dst)

    def _write_standard_modules(self, target_dir: Path):
        """Creates placeholder modules to ensure build pipeline compatibility."""
        # Source Module (Standard)
        if not (target_dir / "modules/source_module.sh").exists():
            source_content = '''#!/bin/bash
# source_module.sh (Standard Template)
# Uses injected environment variables from SSOT for repositories.

set -euo pipefail
echo "Source module initialized."
# Logic to clone Repositories handled by Builder or here
'''
            self._write_script(target_dir / "modules" / "source_module.sh", source_content)
        
        # Convert Module (Placeholder - functionality moved to build.sh)
        if not (target_dir / "modules/convert_module.sh").exists():
             self._write_script(target_dir / "modules" / "convert_module.sh", 
                                "#!/bin/bash\n# Legacy placeholder. Conversion is handled by build.sh.\nexit 0")
        
        # Target Module (Placeholder)
        if not (target_dir / "modules/target_module.sh").exists():
             self._write_script(target_dir / "modules" / "target_module.sh", 
                                "#!/bin/bash\n# Legacy placeholder. Packaging is handled by build.sh.\nexit 0")

    def _write_script(self, path: Path, content: str):
        """Helper to write and chmod a script."""
        self._write_file(path, content)
        self._make_executable(path)

    def _write_file(self, path: Path, content: str):
        """Writes text content to a file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _make_executable(self, path: Path):
        """Sets +x permission."""
        try:
            os.chmod(path, 0o755)
        except Exception:
            pass # Ignore on Windows/Non-POSIX
