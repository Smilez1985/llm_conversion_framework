#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Ditto Manager (AI Hardware Agent)
DIREKTIVE: Goldstandard. Pre-Fetch Docs & Smart Prompts.

This manager orchestrates the AI-based analysis of hardware probes.
It fetches context (documentation), constructs prompts, and validates
the AI's output before passing it to the ModuleGenerator.
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
    """
    
    def __init__(self, provider: str = "OpenAI", model: str = "gpt-4o", 
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 config_manager = None):
        self.logger = get_logger(__name__)
        self.provider = provider
        self.base_url = base_url
        self.config_manager = config_manager
        self.litellm_model = self._format_model_name(provider, model)
        
        # Set API Keys securely
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
            if "Anthropic" in provider: os.environ["ANTHROPIC_API_KEY"] = api_key
            if "Google" in provider: os.environ["GEMINI_API_KEY"] = api_key
            
        self.framework_root = Path(__file__).parent.parent.parent
        self.template_dir = self.framework_root / "targets" / "_template"

    def _format_model_name(self, provider: str, model: str) -> str:
        """Formats model name for litellm (e.g. adds 'ollama/' prefix)."""
        if "Ollama" in provider: return f"ollama/{model}"
        if "Google" in provider: return f"gemini/{model}"
        return model

    def _fetch_documentation(self, sdk_name: str) -> str:
        """
        Fetches documentation text from URLs defined in SSOT (project_sources.yml).
        This gives the AI 'Ground Truth' knowledge.
        """
        if not self.config_manager: return ""
        
        sources = self.config_manager.get("source_repositories", {})
        url = ""
        
        # Search logic for flattened or nested configs
        doc_key_suffix = "docs_workflow"
        
        for key, val in sources.items():
            # Check if key matches SDK (e.g. 'rockchip' in 'rockchip_npu')
            if sdk_name.lower() in key.lower():
                if isinstance(val, dict) and doc_key_suffix in val:
                    url = val[doc_key_suffix]
                    break
                elif key.endswith(doc_key_suffix) and isinstance(val, str):
                    url = val
                    break
        
        if not url or not url.startswith("http"): 
            self.logger.debug(f"No documentation URL found for SDK: {sdk_name}")
            return ""
        
        try:
            self.logger.info(f"Fetching docs from {url}...")
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                # Limit context to prevent token overflow, but keep enough for instructions
                return resp.text[:15000] 
        except Exception as e:
            self.logger.warning(f"Doc fetch failed: {e}")
        return ""

    def generate_module_content(self, probe_file: Path) -> Dict[str, Any]:
        """
        Analyzes the probe file and generates module configuration.
        Returns a dict suitable for ModuleGenerator.
        """
        if not completion:
            raise RuntimeError("Missing dependency: pip install litellm")

        if not probe_file.exists():
            raise FileNotFoundError(f"Probe file not found: {probe_file}")

        # 1. Read Hardware Data
        probe_data = probe_file.read_text(encoding="utf-8", errors="ignore")
        
        # 2. Determine SDK Hint for Doc Fetching
        sdk_hint = "generic"
        if "nvidia" in probe_data.lower() or "tegra" in probe_data.lower(): sdk_hint = "nvidia"
        elif "rockchip" in probe_data.lower() or "rk3" in probe_data.lower(): sdk_hint = "rockchip"
        elif "hailo" in probe_data.lower(): sdk_hint = "hailo"
        elif "intel" in probe_data.lower(): sdk_hint = "intel"
        
        # 3. Load Documentation Context
        doc_context = self._fetch_documentation(sdk_hint)

        # 4. Construct System Prompt
        system_prompt = """
        You are 'Ditto', an expert Embedded Systems Engineer.
        Your task is to analyze a raw 'hardware_probe.sh' output and extract configuration values 
        for the LLM Cross-Compiler Framework.
        
        Analyze the hardware flags (neon, avx, cuda, npu) and suggest the optimal build configuration.
        
        CRITICAL RULES:
        1. Identify Architecture (aarch64, x86_64, armv7l).
        2. Identify SDK (CUDA, RKNN, Hailo).
        3. Generate 'cpu_flags' (GCC) tailored to the specific CPU core found in probe.
        4. Suggest a 'base_os' Docker image (e.g. 'nvidia/cuda:...' if CUDA found).
        
        BUILD SCRIPT LOGIC (quantization_logic):
        You must generate the Bash 'case' statement content for the variable '$QUANTIZATION'.
        This logic will be injected into 'build.sh'.
        It must handle cases like "INT8", "INT4", "FP16".
        Use the provided DOCUMENTATION CONTEXT to find the correct conversion commands.
        
        IMPORTANT: Prefer calling existing helper scripts if available in context (e.g. /app/modules/rkllm_module.sh).
        
        Documentation Context:
        {doc_context}
        
        Return a JSON object with exactly these keys:
        {
            "module_name": "Suggested Name",
            "architecture": "arch",
            "sdk": "sdk_name",
            "base_os": "docker_image",
            "cpu_flags": "gcc_flags",
            "cmake_flags": "cmake_flags",
            "packages": "space_separated_apt_packages",
            "quantization_logic": "bash case content (strings only, no markdown)"
        }
        """

        user_prompt = f"""
        --- INPUT: target_hardware_config.txt ---
        {probe_data[:8000]}
        
        Based on this probe, generate the optimal configuration JSON.
        """

        # 5. Call LLM
        try:
            # Construct params dynamically
            kwargs = {
                "model": self.litellm_model,
                "messages": [
                    {"role": "system", "content": system_prompt.replace("{doc_context}", doc_context)},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1
            }
            
            # Inject API Key if needed
            if self.api_key and self.api_key != "sk-dummy":
                kwargs["api_key"] = self.api_key
            
            # Inject Base URL (for LocalAI)
            if self.base_url:
                kwargs["api_base"] = self.base_url
                
            # Enforce JSON output
            kwargs["response_format"] = { "type": "json_object" }

            response = completion(**kwargs)
            
            content = response.choices[0].message.content
            
            # Clean Potential Markdown Wrappers
            if "```" in content:
                import re
                match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
                if match: content = match.group(1).strip()

            return json.loads(content)
            
        except Exception as e:
            self.logger.error(f"AI Analysis failed: {e}")
            raise e

    def save_module(self, module_name: str, config: Dict[str, Any], targets_dir: Path):
        """
        Passes the AI-generated config to the ModuleGenerator to create files on disk.
        """
        # Ensure packages is a list
        packages = config.get("packages", "")
        if isinstance(packages, str):
            packages = packages.split()
            
        # Construct Generator Data
        gen_data = {
            "module_name": module_name,
            "architecture": config.get("architecture", "aarch64"),
            "sdk": config.get("sdk", "none"),
            "description": f"AI-generated target for {module_name}",
            "base_os": config.get("base_os", "debian:bookworm-slim"),
            "packages": packages,
            "cpu_flags": config.get("cpu_flags", ""),
            "cmake_flags": config.get("cmake_flags", ""),
            "quantization_logic": config.get("quantization_logic", ""), # The Magic Logic
            "setup_commands": "# Auto-generated setup by Ditto",
            "detection_commands": "lscpu",
            "supported_boards": [module_name]
        }
        
        generator = ModuleGenerator(targets_dir)
        return generator.generate_module(gen_data)
