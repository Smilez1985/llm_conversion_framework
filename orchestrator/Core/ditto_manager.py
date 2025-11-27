#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Ditto Manager (AI Hardware Agent)
DIREKTIVE: Goldstandard. Pre-Fetch Docs & Smart Prompts.
"""

import json
import os
import logging
import requests
from pathlib import Path
from typing import Dict, Optional, Any

try:
    from litellm import completion
except ImportError:
    completion = None

from orchestrator.utils.logging import get_logger
from orchestrator.Core.module_generator import ModuleGenerator

class DittoCoder:
    """
    AI Agent that analyzes hardware probe dumps and generates
    optimized build configurations using LLMs.
    Supports ALL providers via litellm abstraction.
    """
    
    def __init__(self, provider: str = "OpenAI", model: str = "gpt-4o", 
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 config_manager = None):
        self.logger = get_logger(__name__)
        self.provider = provider
        self.base_url = base_url
        self.config_manager = config_manager
        self.litellm_model = self._format_model_name(provider, model)
        
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
            if "Anthropic" in provider: os.environ["ANTHROPIC_API_KEY"] = api_key
            if "Google" in provider: os.environ["GEMINI_API_KEY"] = api_key
            
        self.framework_root = Path(__file__).parent.parent.parent
        self.template_dir = self.framework_root / "targets" / "_template"

    def _format_model_name(self, provider: str, model: str) -> str:
        """Formatiert den Modellnamen für litellm."""
        if "Ollama" in provider: return f"ollama/{model}"
        if "Google" in provider: return f"gemini/{model}"
        return model

    def _fetch_documentation(self, sdk_name: str) -> str:
        """Liest Doku-Text aus der SSOT URL (Flattened Config Support)."""
        if not self.config_manager: return ""
        
        sources = self.config_manager.get("source_repositories", {})
        url = ""
        
        doc_key_suffix = "docs_workflow"
        
        for key, val in sources.items():
            if sdk_name.lower() in key.lower():
                if isinstance(val, dict) and doc_key_suffix in val:
                    url = val[doc_key_suffix]
                    break
                elif key.endswith(doc_key_suffix) and isinstance(val, str):
                    url = val
                    break
        
        if not url or not url.startswith("http"): return ""
        
        try:
            self.logger.info(f"Fetching docs from {url}...")
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.text[:15000] # Limit context
        except Exception as e:
            self.logger.warning(f"Doc fetch failed: {e}")
        return ""

    def generate_module_content(self, probe_file: Path) -> Dict[str, Any]:
        """
        Analysiert die Probe-Datei und generiert die Modul-Konfiguration.
        """
        if not completion:
            raise RuntimeError("Missing dependency: pip install litellm")

        if not probe_file.exists():
            raise FileNotFoundError(f"Probe file not found: {probe_file}")

        # 1. Hardware Daten lesen
        probe_data = probe_file.read_text(encoding="utf-8", errors="ignore")
        
        # SDK Hint für Doku-Suche
        sdk_hint = "generic"
        if "nvidia" in probe_data.lower() or "tegra" in probe_data.lower(): sdk_hint = "nvidia"
        elif "rockchip" in probe_data.lower() or "rk3" in probe_data.lower(): sdk_hint = "rockchip"
        elif "hailo" in probe_data.lower(): sdk_hint = "hailo"
        elif "intel" in probe_data.lower(): sdk_hint = "intel"
        
        doc_context = self._fetch_documentation(sdk_hint)

        # 2. System Prompt (ERWEITERT für Quantization Logic)
        system_prompt = """
        You are 'Ditto', an expert Embedded Systems Engineer.
        Analyze the hardware probe and generate a JSON configuration to fill the framework templates.
        
        TASKS:
        1. Analyze Hardware (Arch, CPU Flags, NPU).
        2. Generate Bash Code blocks for 'build.sh' based on the SDK documentation provided.
        
        REQUIRED JSON STRUCTURE:
        {
            "module_name": "Str",
            "architecture": "aarch64|x86_64",
            "sdk": "Str",
            "base_os": "Docker Image Name",
            "packages": ["list", "of", "packages"],
            "cpu_flags": "GCC Flags",
            "cmake_flags": "CMake Flags",
            "setup_commands": "Bash code for Dockerfile setup (optional)",
            "quantization_logic": "Bash CASE block content for build.sh"
        }
        
        CRITICAL RULES for 'quantization_logic':
        - Generate ONLY the case content lines (cases and commands).
        - Do not wrap in 'case ... esac', just the body.
        - Example for RKNN:
        "INT8"|"i8")
            echo "Converting to INT8..."
            rknn-llm-convert --i8 $MODEL_SOURCE ;;
        "FP16")
            echo "Keeping FP16..." ;;
        """

        user_prompt = f"""
        CONTEXT: {doc_context[:2000]}...
        PROBE DATA: {probe_data[:8000]}
        Generate JSON.
        """

        # 3. LLM Call
        try:
            # Parameter dynamisch aufbauen
            kwargs = {
                "model": self.litellm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1
            }
            
            if self.api_key and self.api_key != "sk-dummy":
                kwargs["api_key"] = self.api_key
            
            if self.base_url:
                kwargs["api_base"] = self.base_url
                
            kwargs["response_format"] = { "type": "json_object" }

            response = completion(**kwargs)
            
            content = response.choices[0].message.content
            if "```" in content:
                import re
                match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
                if match: content = match.group(1).strip()

            return json.loads(content)
            
        except Exception as e:
            self.logger.error(f"AI Analysis failed: {e}")
            raise e

    def save_module(self, module_name: str, config: Dict[str, Any], targets_dir: Path):
        """Wrapper um den ModuleGenerator aufzurufen."""
        
        packages = config.get("packages", "")
        if isinstance(packages, str):
            packages = packages.split()
            
        gen_data = {
            "module_name": module_name,
            "architecture": config.get("architecture", "aarch64"),
            "sdk": config.get("sdk", "none"),
            "description": f"AI-generated target for {module_name}",
            "base_os": config.get("base_os", "debian:bookworm-slim"),
            "packages": packages,
            "cpu_flags": config.get("cpu_flags", ""),
            "cmake_flags": config.get("cmake_flags", ""),
            "quantization_logic": config.get("quantization_logic", ""), # Hier übergeben wir die Logik
            "setup_commands": "# Auto-generated setup by Ditto",
            "detection_commands": "lscpu",
            "supported_boards": [module_name]
        }
        
        generator = ModuleGenerator(targets_dir)
        return generator.generate_module(gen_data)
