#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Ditto Manager
DIREKTIVE: Goldstandard.
ZWECK: Adaptierter Ditto-Agent, der Hardware-Probes liest und Framework-Module generiert.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

try:
    from litellm import completion
except ImportError:
    completion = None

class DittoCoder:
    """
    A specialized version of Ditto that acts as a smart template engine.
    It reads hardware probes and fills framework templates.
    """
    
    def __init__(self, model: str = "gpt-4-turbo", api_key: Optional[str] = None):
        self.model = model
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        
        # Pfade zu den Templates (im Framework enthalten)
        self.template_dir = Path(__file__).parent.parent.parent / "targets" / "_template"

    def _read_template(self, filename: str) -> str:
        """Liest ein Template ein."""
        path = self.template_dir / filename
        if not path.exists():
            # Fallback für Module, falls Pfadstruktur anders ist
            path = self.template_dir / "modules" / filename
        
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"# Error: Template {filename} not found"

    def generate_module_content(self, probe_file: Path) -> Dict[str, str]:
        """
        Analysiert die Probe-Datei und generiert den Code für das neue Modul.
        Gibt ein Dictionary zurück: {'filename': 'content'}
        """
        if not completion:
            raise RuntimeError("Missing dependency: pip install litellm")

        # 1. Hardware Daten lesen
        probe_data = probe_file.read_text(encoding="utf-8", errors="ignore")

        # 2. Templates laden
        tmpl_docker = self._read_template("Dockerfile")
        tmpl_target = self._read_template("target.yml")
        tmpl_config = self._read_template("config_module.sh")

        # 3. Der "Ditto" System Prompt
        system_prompt = """
        You are 'Ditto', an expert Embedded Systems Engineer for the LLM Cross-Compiler Framework.
        Your task is to generate configuration files for a new hardware target based on a hardware probe.
        
        RULES:
        1. Analyze the INPUT (Hardware Probe) meticulously.
        2. Fill in the TEMPLATES provided. Do NOT change the structure.
        3. Replace placeholders like [IHRE_ARCHITEKTUR] or [CPU_FLAGS] with real, optimal values.
        4. For 'target.yml', generate valid YAML.
        5. For 'Dockerfile', use Debian Bookworm as base unless CUDA is detected (then use nvidia/cuda).
        6. For 'config_module.sh', generate the correct CMake flags (-mcpu, -mfpu, etc.).
        
        Return ONLY a JSON object mapping filenames to their generated content.
        Example: { "Dockerfile": "...", "target.yml": "...", "modules/config_module.sh": "..." }
        """

        user_prompt = f"""
        --- INPUT: Hardware Probe (target_hardware_config.txt) ---
        {probe_data[:5000]}
        
        --- TEMPLATE: Dockerfile ---
        {tmpl_docker}
        
        --- TEMPLATE: target.yml ---
        {tmpl_target}
        
        --- TEMPLATE: config_module.sh ---
        {tmpl_config}
        
        Generate the filled files now.
        """

        # 4. LLM Call
        response = completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={ "type": "json_object" }
        )

        return json.loads(response.choices[0].message.content)

    def save_module(self, module_name: str, generated_files: Dict[str, str], output_base_dir: Path):
        """Speichert die generierten Dateien in die korrekte Struktur."""
        target_path = output_base_dir / module_name
        target_path.mkdir(parents=True, exist_ok=True)
        (target_path / "modules").mkdir(exist_ok=True)

        for filename, content in generated_files.items():
            # Pfadbereinigung (falls LLM 'modules/config_module.sh' oder nur 'config_module.sh' zurückgibt)
            clean_name = filename.lstrip("/")
            file_path = target_path / clean_name
            
            # Sicherstellen, dass Unterordner existieren
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            # Executable machen wenn .sh
            if file_path.suffix == ".sh":
                file_path.chmod(0o755)
