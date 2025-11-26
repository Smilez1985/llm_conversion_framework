#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Ditto Manager (AI Hardware Agent)
DIREKTIVE: Goldstandard.
ZWECK: Nutzt LLMs, um aus Hardware-Probe-Daten fertige Module zu generieren.
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Optional, Any

# Optional: litellm für AI-Kommunikation
try:
    from litellm import completion
except ImportError:
    completion = None

from orchestrator.utils.logging import get_logger

class DittoCoder:
    """
    AI-Agent, der Hardware-Probes analysiert und Konfigurationen generiert.
    """
    
    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None):
        self.logger = get_logger(__name__)
        self.model = model
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
            
        # Pfad zu den Templates (relativ zu dieser Datei)
        # orchestrator/Core/ -> targets/_template
        self.framework_root = Path(__file__).parent.parent.parent
        self.template_dir = self.framework_root / "targets" / "_template"

    def _read_template(self, filename: str) -> str:
        """Liest ein Template ein."""
        # Versuche direkten Pfad oder modules/ Unterordner
        paths = [
            self.template_dir / filename,
            self.template_dir / "modules" / filename
        ]
        
        for path in paths:
            if path.exists():
                return path.read_text(encoding="utf-8")
        
        return f"# Error: Template {filename} not found"

    def generate_module_content(self, probe_file: Path) -> Dict[str, Any]:
        """
        Analysiert die Probe-Datei und generiert die Modul-Konfiguration.
        Gibt ein Dictionary mit den erkannten Werten zurück.
        """
        if not completion:
            raise RuntimeError("Missing dependency: pip install litellm")

        if not probe_file.exists():
            raise FileNotFoundError(f"Probe file not found: {probe_file}")

        # 1. Hardware Daten lesen
        probe_data = probe_file.read_text(encoding="utf-8", errors="ignore")
        self.logger.info(f"Analyzing probe data ({len(probe_data)} bytes)...")

        # 2. Der "Ditto" System Prompt
        system_prompt = """
        You are 'Ditto', an expert Embedded Systems Engineer.
        Your task is to analyze a raw 'hardware_probe.sh' output and extract configuration values 
        for the LLM Cross-Compiler Framework.
        
        Analyze the hardware flags (neon, avx, cuda, npu) and suggest the optimal build configuration.
        
        Return a JSON object with exactly these keys:
        {
            "module_name": "Suggested Name (e.g. 'Raspberry Pi 5')",
            "architecture": "arch (aarch64, x86_64, armv7l, riscv64)",
            "sdk": "sdk_name (cuda, rknn, openvino, or none)",
            "base_os": "docker_image (debian:bookworm-slim, nvidia/cuda:..., etc.)",
            "cpu_flags": "gcc_flags (e.g. -march=armv8.2-a+fp16 -mcpu=cortex-a76)",
            "cmake_flags": "cmake_flags (e.g. -DGGML_CUDA=ON)",
            "packages": "space_separated_apt_packages"
        }
        """

        user_prompt = f"""
        --- INPUT: target_hardware_config.txt ---
        {probe_data[:8000]}
        
        Based on this probe, generate the optimal configuration JSON.
        """

        # 3. LLM Call
        try:
            response = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            config = json.loads(content)
            self.logger.info("AI analysis completed successfully")
            return config
            
        except Exception as e:
            self.logger.error(f"AI Analysis failed: {e}")
            raise e

    def save_module(self, module_name: str, config: Dict[str, Any], targets_dir: Path):
        """
        Nutzt den ModuleGenerator (bestehende Logik), um das Modul physisch zu erstellen.
        """
        from orchestrator.Core.module_generator import ModuleGenerator
        
        # Daten für den Generator aufbereiten
        gen_data = {
            "module_name": module_name,
            "architecture": config.get("architecture", "aarch64"),
            "sdk": config.get("sdk", "none"),
            "description": f"AI-generated target for {module_name}",
            "base_os": config.get("base_os", "debian:bookworm-slim"),
            "packages": config.get("packages", "").split(),
            "cpu_flags": config.get("cpu_flags", ""),
            "cmake_flags": config.get("cmake_flags", ""),
            "setup_commands": "# Auto-generated setup",
            "detection_commands": "lscpu",
            "supported_boards": [module_name]
        }
        
        generator = ModuleGenerator(targets_dir)
        return generator.generate_module(gen_data)
