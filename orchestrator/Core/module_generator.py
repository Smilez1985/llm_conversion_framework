#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Module Generator (Core Logic)
DIREKTIVE: Goldstandard, Separation of Concerns.

Zweck:
Zentrale Logik zur Generierung neuer Hardware-Target-Module.
Wird sowohl von der GUI (Wizard) als auch der CLI (Command) genutzt.
Enthält Templates für Dockerfile, target.yml und build.sh.
"""

import os
from pathlib import Path
from typing import Dict, List, Any
import yaml

from orchestrator.utils.logging import get_logger
from orchestrator.utils.helpers import ensure_directory

class ModuleGenerator:
    """Generates file structure and content for new hardware targets."""
    
    def __init__(self, targets_dir: Path):
        self.logger = get_logger(__name__)
        self.targets_dir = targets_dir
        # Template Verzeichnis liegt parallel zu den Targets
        self.template_dir = targets_dir / "_template"

        if not self.template_dir.exists():
             # Fallback falls wir nicht direkt im targets dir sind
             self.template_dir = Path(__file__).parent.parent.parent / "targets" / "_template"

    def generate_module(self, data: Dict[str, Any]) -> Path:
        """
        Generate a complete module from configuration data.
        
        Args:
            data: Dictionary containing configuration keys (module_name, architecture, etc.)
        
        Returns:
            Path: Path to the created module directory
        """
        module_slug = data["module_name"].lower().replace(" ", "_")
        target_dir = self.targets_dir / module_slug
        
        self.logger.info(f"Generating new target module: {data['module_name']} at {target_dir}")
        
        # 1. Create Directory Structure
        ensure_directory(target_dir)
        ensure_directory(target_dir / "modules")
        ensure_directory(target_dir / "scripts")
        
        # 2. Generate Files via Template Processing
        self._process_template("Dockerfile", target_dir, data)
        self._process_template("target.yml", target_dir, data)
        self._process_template("modules/config_module.sh", target_dir, data)
        self._process_template("modules/source_module.sh", target_dir, data)
        
        # NEU: Das Build-Skript Template verarbeiten (mit Quantisierungslogik)
        self._write_build_script(target_dir, data)
        
        # Profile Script generieren
        self._write_profile_script(target_dir, data)
        
        # 3. Create Placeholder Modules (if templates are missing or needed)
        self._write_standard_modules(target_dir)
        
        self.logger.info("Module generation completed successfully.")
        return target_dir

    def _process_template(self, filename: str, target_dir: Path, data: Dict[str, Any]):
        """Reads a template, replaces placeholders, and writes it to target_dir."""
        src = self.template_dir / filename
        dst = target_dir / filename
        
        if not src.exists():
            # Wenn Template fehlt, nicht abstürzen, sondern loggen (oder ignorieren bei optionalen Files)
            # self.logger.warning(f"Template {filename} not found in {self.template_dir}")
            return

        content = src.read_text(encoding="utf-8")
        
        # Data Preparation for Templates
        packages = data.get("packages", [])
        if isinstance(packages, str): packages = packages.split()
        packages_str = " \\\n        ".join(packages)
        
        # Replacement Map
        replacements = {
            "[MODULE_NAME]": data.get("module_name", "Unknown"),
            "[Hardware-Familie]": data.get("module_name", "Unknown"),
            "[IHRE_ARCHITEKTUR]": data.get("architecture", "aarch64"),
            "[Hersteller]": "Community",
            "debian:bookworm-slim": data.get("base_os", "debian:bookworm-slim"), # Replace default if different
            "{packages_str}": packages_str,
            # Inject Scripts / Logic Blocks
            "# [SDK_SETUP_COMMANDS]": data.get("setup_commands", ""),
            "[QUANTIZATION_LOGIC]": data.get("quantization_logic", ""),
            "# [PACKAGING_COMMANDS]": data.get("packaging_commands", "cp -r build/* $OUTPUT_DIR/"),
            "[CPU_FLAGS]": data.get("cpu_flags", ""),
            "[CMAKE_FLAGS]": data.get("cmake_flags", "")
        }
        
        for key, value in replacements.items():
            content = content.replace(key, str(value))
            
        # Write File
        if dst.suffix == ".yml":
            self._update_yaml_config(content, dst, data)
        else:
            with open(dst, "w", encoding="utf-8") as f:
                f.write(content)
            
        # Permissions
        if dst.suffix == ".sh":
            try: os.chmod(dst, 0o755)
            except: pass

    def _update_yaml_config(self, template_content: str, dst: Path, data: Dict[str, Any]):
        """Parst das YAML-Template, updated Werte und schreibt es sauber zurück."""
        try:
            config = yaml.safe_load(template_content)
            
            # Update Metadata
            if "metadata" in config:
                config["metadata"]["name"] = data["module_name"]
                config["metadata"]["architecture_family"] = data["architecture"]
                config["metadata"]["description"] = data.get("description", "")
            
            # Update Docker
            if "docker" in config:
                safe_name = data["module_name"].lower().replace(" ", "-")
                config["docker"]["image_name"] = f"llm-framework/{safe_name}"
            
            with open(dst, "w", encoding="utf-8") as f:
                yaml.dump(config, f, sort_keys=False)
        except Exception as e:
            self.logger.error(f"Failed to process YAML template: {e}")
            # Fallback: Raw write
            with open(dst, "w", encoding="utf-8") as f:
                f.write(template_content)

    def _write_build_script(self, target_dir: Path, data: Dict[str, Any]):
        """
        NEU: Generiert das intelligente build.sh Skript.
        Hier landet die Logik von Ditto (oder der Default-Case).
        """
        quant_logic = data.get("quantization_logic", "")
        if not quant_logic:
            # Fallback Default Logic
            quant_logic = """
    "FP16")
        echo ">> Default FP16 Build (No Quantization)"
        # Standard build commands would go here
        ;;
    *)
        echo ">> Unknown Quantization: $QUANT_TYPE"
        ;;
"""

        content = f'''#!/bin/bash
# build.sh for {data["module_name"]}
# Generated by LLM Cross-Compiler Framework (Ditto/Wizard)
#
# Environment Variables:
# $MODEL_SOURCE    - Path to input model
# $QUANTIZATION    - Target Quantization (e.g. Q4_K_M, INT8)
# $OUTPUT_DIR      - Destination for artifacts
# $BUILD_JOBS      - Number of parallel jobs

set -euo pipefail

WORK_DIR="${{BUILD_CACHE_DIR:-/build-cache}}"
OUTPUT_DIR="${{WORK_DIR}}/output"
mkdir -p "$OUTPUT_DIR"

echo "=== Build Started: {data['module_name']} ==="
echo "Model: $MODEL_SOURCE"
echo "Quantization: ${{QUANTIZATION:-None}}"

QUANT_TYPE="${{QUANTIZATION:-FP16}}"

case "$QUANT_TYPE" in
{quant_logic}
esac

echo "=== Build Completed ==="
'''
        self._write_script(target_dir / "modules" / "build.sh", content)

    def _write_profile_script(self, target_dir: Path, data: Dict[str, Any]):
        """Generate generate_profile.sh"""
        content = f'''#!/bin/bash
# Hardware Profile Generator for {data["module_name"]}
# Run on target hardware

OUTPUT_FILE="target_hardware_config.txt"
echo "# Profile for {data['module_name']}" > "$OUTPUT_FILE"
{data.get("detection_commands", "lscpu >> $OUTPUT_FILE")}
echo "Generated $OUTPUT_FILE"
'''
        self._write_script(target_dir / "generate_profile.sh", content)

    def _write_standard_modules(self, target_dir: Path):
        """Write standard templates for other modules if not handled by templates"""
        # Falls keine Templates da waren, erzeugen wir Placeholders
        # convert und target werden oft durch build.sh ersetzt, aber wir lassen sie da
        if not (target_dir / "modules/convert_module.sh").exists():
             self._write_script(target_dir / "modules" / "convert_module.sh", "#!/bin/bash\n# Placeholder\n")
        if not (target_dir / "modules/target_module.sh").exists():
             self._write_script(target_dir / "modules" / "target_module.sh", "#!/bin/bash\n# Placeholder\n")

    def _write_script(self, path: Path, content: str):
        """Write content to file and make executable"""
        with open(path, "w") as f:
            f.write(content)
        try:
            os.chmod(path, 0o755)
        except:
            pass
