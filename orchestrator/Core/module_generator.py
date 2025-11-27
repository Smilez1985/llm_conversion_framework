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
        """
        module_slug = data["module_name"].lower().replace(" ", "_")
        target_dir = self.targets_dir / module_slug
        
        self.logger.info(f"Generating new target module: {data['module_name']} at {target_dir}")
        
        # 1. Create Directory Structure
        ensure_directory(target_dir)
        ensure_directory(target_dir / "modules")
        ensure_directory(target_dir / "scripts")
        
        # 2. Generate Base Files
        self._process_template("Dockerfile", target_dir, data)
        self._process_template("target.yml", target_dir, data)
        self._process_template("modules/config_module.sh", target_dir, data)
        self._process_template("modules/source_module.sh", target_dir, data)
        self._process_template("modules/build.sh", target_dir, data)
        
        # 3. Intelligent Module Inclusion (Conditional Copying)
        self._include_hardware_modules(target_dir, data)
        
        # 4. Helper Scripts
        self._write_profile_script(target_dir, data)
        self._write_standard_modules(target_dir)
        
        self.logger.info("Module generation completed successfully.")
        return target_dir

    def _include_hardware_modules(self, target_dir: Path, data: Dict[str, Any]):
        """
        Kopiert hardware-spezifische Skripte NUR wenn nötig.
        Entscheidet anhand von SDK oder Name.
        """
        sdk = data.get("sdk", "").lower()
        name = data.get("module_name", "").lower()
        
        # --- ROCKCHIP LOGIK ---
        # Wir kopieren RKNN/RKLLM nur, wenn es wirklich ein Rockchip Board ist.
        if "rockchip" in sdk or "rknn" in sdk or "rk3" in name:
            self.logger.info("Detected Rockchip Architecture -> Injecting RKNN/RKLLM modules")
            self._process_template("modules/rknn_module.sh", target_dir, data)
            self._process_template("modules/rkllm_module.sh", target_dir, data)
            
        # --- NVIDIA LOGIK (Platzhalter für Zukunft) ---
        # elif "cuda" in sdk or "jetson" in name or "nvidia" in name:
        #     self.logger.info("Detected NVIDIA Architecture -> Injecting TensorRT modules")
        #     self._process_template("modules/tensorrt_module.sh", target_dir, data)

    def _process_template(self, filename: str, target_dir: Path, data: Dict[str, Any]):
        """Reads a template, replaces placeholders, and writes it to target_dir."""
        src = self.template_dir / filename
        dst = target_dir / filename
        
        if not src.exists():
            # Optional logging, manche Templates existieren evtl. noch nicht
            return

        content = src.read_text(encoding="utf-8")
        
        packages = data.get("packages", [])
        if isinstance(packages, str): packages = packages.split()
        packages_str = " \\\n        ".join(packages)
        
        replacements = {
            "[MODULE_NAME]": data.get("module_name", "Unknown"),
            "[Hardware-Familie]": data.get("module_name", "Unknown"),
            "[IHRE_ARCHITEKTUR]": data.get("architecture", "aarch64"),
            "[Hersteller]": "Community",
            "debian:bookworm-slim": data.get("base_os", "debian:bookworm-slim"),
            "{packages_str}": packages_str,
            "# [SDK_SETUP_COMMANDS]": data.get("setup_commands", ""),
            "[QUANTIZATION_LOGIC]": data.get("quantization_logic", ""),
            "# [PACKAGING_COMMANDS]": data.get("packaging_commands", "cp -r build/* $OUTPUT_DIR/"),
            "[CPU_FLAGS]": data.get("cpu_flags", ""),
            "[CMAKE_FLAGS]": data.get("cmake_flags", "")
        }
        
        for key, value in replacements.items():
            content = content.replace(key, str(value))
            
        if dst.suffix == ".yml":
            self._update_yaml_config(content, dst, data)
        else:
            with open(dst, "w", encoding="utf-8") as f:
                f.write(content)
            
        if dst.suffix == ".sh":
            try: os.chmod(dst, 0o755)
            except: pass

    def _update_yaml_config(self, template_content: str, dst: Path, data: Dict[str, Any]):
        try:
            config = yaml.safe_load(template_content)
            if "metadata" in config:
                config["metadata"]["name"] = data["module_name"]
                config["metadata"]["architecture_family"] = data["architecture"]
                config["metadata"]["sdk"] = data["sdk"]
            
            if "docker" in config:
                safe_name = data["module_name"].lower().replace(" ", "-")
                config["docker"]["image_name"] = f"llm-framework/{safe_name}"
            
            with open(dst, "w", encoding="utf-8") as f:
                yaml.dump(config, f, sort_keys=False)
        except Exception:
            with open(dst, "w", encoding="utf-8") as f:
                f.write(template_content)

    def _write_build_script(self, target_dir: Path, data: Dict[str, Any]):
        """Generiert das intelligente build.sh Skript."""
        quant_logic = data.get("quantization_logic", "")
        if not quant_logic:
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
        content = f'''#!/bin/bash
# Hardware Profile Generator
OUTPUT_FILE="target_hardware_config.txt"
echo "# Profile for {data['module_name']}" > "$OUTPUT_FILE"
{data.get("detection_commands", "lscpu >> $OUTPUT_FILE")}
echo "Generated $OUTPUT_FILE"
'''
        self._write_script(target_dir / "generate_profile.sh", content)

    def _write_standard_modules(self, target_dir: Path):
        # Placeholder creation if not handled by templates
        if not (target_dir / "modules/convert_module.sh").exists():
             self._write_script(target_dir / "modules/convert_module.sh", "#!/bin/bash\n# Placeholder\n")
        if not (target_dir / "modules/target_module.sh").exists():
             self._write_script(target_dir / "modules" / "target_module.sh", "#!/bin/bash\n# Placeholder\n")

    def _write_script(self, path: Path, content: str):
        with open(path, "w") as f: f.write(content)
        try: os.chmod(path, 0o755)
        except: pass
