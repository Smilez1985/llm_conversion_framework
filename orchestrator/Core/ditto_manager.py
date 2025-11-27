#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Ditto Manager (AI Hardware Agent)
DIREKTIVE: Goldstandard. Secured & Isolated.
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
    AI Agent that analyzes hardware probe dumps.
    SECURED: Enforces Local LLM usage in strict mode to prevent data leakage.
    """
    
    def __init__(self, provider: str = "Ollama (Local)", model: str = "llama3", 
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 config_manager = None):
        self.logger = get_logger(__name__)
        self.config_manager = config_manager
        
        # Security Check
        self._enforce_security_policy(provider)
        
        self.provider = provider
        self.base_url = base_url
        self.litellm_model = self._format_model_name(provider, model)
        
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
            if "Anthropic" in provider: os.environ["ANTHROPIC_API_KEY"] = api_key
            if "Google" in provider: os.environ["GEMINI_API_KEY"] = api_key
            
        self.framework_root = Path(__file__).parent.parent.parent
        self.template_dir = self.framework_root / "targets" / "_template"

    def _enforce_security_policy(self, provider: str):
        """Prevents Data Leakage to Cloud APIs if Security Level is STRICT."""
        security_level = os.environ.get("AI_SECURITY_LEVEL", "STRICT")
        
        if security_level == "STRICT":
            allowed = ["Ollama", "Local", "Compatible"]
            is_safe = any(safe in provider for safe in allowed)
            
            if not is_safe:
                raise SecurityError(
                    f"Security Alert: Cloud AI Provider '{provider}' blocked by policy (STRICT mode). "
                    "Use a local LLM (Ollama) or set AI_SECURITY_LEVEL=LOOSE to allow data egress."
                )

    def _format_model_name(self, provider: str, model: str) -> str:
        if "Ollama" in provider: return f"ollama/{model}"
        if "Google" in provider: return f"gemini/{model}"
        return model

    def _fetch_documentation(self, sdk_name: str) -> str:
        """Fetches docs from SSOT. (Safe: only GET public URLs)"""
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
                return resp.text[:15000]
        except: pass
        return ""

    def generate_module_content(self, probe_file: Path) -> Dict[str, Any]:
        if not completion: raise RuntimeError("Missing litellm")
        if not probe_file.exists(): raise FileNotFoundError("Probe file missing")

        probe_data = probe_file.read_text(encoding="utf-8", errors="ignore")
        
        sdk_hint = "generic"
        if "nvidia" in probe_data.lower(): sdk_hint = "nvidia"
        elif "rockchip" in probe_data.lower(): sdk_hint = "rockchip"
        
        doc_context = self._fetch_documentation(sdk_hint)

        system_prompt = """
        You are 'Ditto', an expert Embedded Systems Engineer.
        Analyze the hardware probe and generate a JSON configuration.
        
        TASKS:
        1. Analyze Hardware (Arch, CPU Flags, NPU).
        2. Generate Bash Code blocks for 'build.sh'.
        
        REQUIRED JSON STRUCTURE:
        {
            "module_name": "Str",
            "architecture": "aarch64|x86_64",
            "sdk": "Str",
            "base_os": "Docker Image Name",
            "packages": ["list", "of", "packages"],
            "cpu_flags": "GCC Flags",
            "cmake_flags": "CMake Flags",
            "setup_commands": "Bash code for Dockerfile setup",
            "quantization_logic": "Bash CASE block content"
        }
        
        For 'quantization_logic':
        - PREFER calling existing helper scripts (e.g. /app/modules/rkllm_module.sh) over raw code.
        - Generate ONLY the case body.
        """

        user_prompt = f"""
        CONTEXT: {doc_context[:2000]}...
        PROBE DATA: {probe_data[:8000]}
        Generate JSON.
        """

        try:
            response = completion(
                model=self.litellm_model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                response_format={ "type": "json_object" },
                temperature=0.1,
                api_base=self.base_url
            )
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
        from orchestrator.Core.module_generator import ModuleGenerator
        packages = config.get("packages", "")
        if isinstance(packages, str): packages = packages.split()
            
        gen_data = {
            "module_name": module_name,
            "architecture": config.get("architecture", "aarch64"),
            "sdk": config.get("sdk", "none"),
            "description": f"AI-generated target for {module_name}",
            "base_os": config.get("base_os", "debian:bookworm-slim"),
            "packages": packages,
            "cpu_flags": config.get("cpu_flags", ""),
            "cmake_flags": config.get("cmake_flags", ""),
            "quantization_logic": config.get("quantization_logic", ""),
            "setup_commands": "# Auto-generated setup by Ditto",
            "detection_commands": "lscpu",
            "supported_boards": [module_name]
        }
        
        generator = ModuleGenerator(targets_dir)
        return generator.generate_module(gen_data)

class SecurityError(Exception):
    pass
