#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Module Generator (Core Logic)
DIREKTIVE: Goldstandard, Separation of Concerns.
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
        self.template_dir = targets_dir / "_template"

        if not self.template_dir.exists():
             self.template_dir = Path(__file__).parent.parent.parent / "targets" / "_template"

    def generate_module(self, data: Dict[str, Any]) -> Path:
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
        self._process_template("modules/build.sh", target_dir, data)
        
        # NEW: Copy specialized modules (they might be static templates)
        self._process_template("modules/rknn_module.sh", target_dir, data)
        self._process_template("modules/rkllm_module.sh", target_dir, data)
        
        self._write_profile_script(target_dir, data)
        self._write_standard_modules(target_dir)
        
        self.logger.info("Module generation completed successfully.")
        return target_dir

    def _process_template(self, filename: str, target_dir: Path, data: Dict[str, Any]):
        src = self.template_dir / filename
        dst = target_dir / filename
        
        # If template doesn't exist in _template, maybe skip or create empty?
        # For rkllm_module.sh, if it's not in _template, we skip it.
        if not src.exists():
            return

        content = src.read_text(encoding="utf-8")
        
        packages_str = " \\\n        ".join(data.get("packages", []))
        
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
            
            if "docker" in config:
                safe_name = data["module_name"].lower().replace(" ", "-")
                config["docker"]["image_name"] = f"llm-framework/{safe_name}"
            
            with open(dst, "w", encoding="utf-8") as f:
                yaml.dump(config, f, sort_keys=False)
        except:
            with open(dst, "w", encoding="utf-8") as f:
                f.write(template_content)

    def _write_profile_script(self, target_dir: Path, data: Dict[str, Any]):
        content = f'''#!/bin/bash
# Hardware Profile Generator for {data["module_name"]}
OUTPUT_FILE="target_hardware_config.txt"
echo "# Profile for {data['module_name']}" > "$OUTPUT_FILE"
{data.get("detection_commands", "lscpu >> $OUTPUT_FILE")}
echo "Generated $OUTPUT_FILE"
'''
        self._write_script(target_dir / "generate_profile.sh", content)

    def _write_standard_modules(self, target_dir: Path):
        # Helper for creating missing placeholders if templates failed
        if not (target_dir / "modules/convert_module.sh").exists():
             self._write_script(target_dir / "modules/convert_module.sh", "#!/bin/bash\n# Placeholder\n")
        if not (target_dir / "modules/target_module.sh").exists():
             self._write_script(target_dir / "modules" / "target_module.sh", "#!/bin/bash\n# Placeholder\n")

    def _write_script(self, path: Path, content: str):
        with open(path, "w") as f: f.write(content)
        try: os.chmod(path, 0o755)
        except: pass
