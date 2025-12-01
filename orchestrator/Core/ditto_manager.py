#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Ditto Manager (AI Hardware Agent)
DIREKTIVE: Goldstandard. RAG-Enabled Expert System (v1.5.0).

This manager orchestrates the AI-based analysis of hardware probes.
It fetches context (documentation), constructs prompts, and validates
the AI's output before passing it to the ModuleGenerator.

UPDATES v1.5.0:
- Integrated RAG retrieval via Qdrant (Hybrid approach: Vector DB -> Web Fallback).
- Context-aware prompting based on indexed knowledge.
- STRICT System Prompt for Hardware Ontology understanding.
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

# V1.5.0 Integration
from orchestrator.Core.rag_manager import RAGManager

class DittoCoder:
    """
    AI Agent that analyzes hardware probe dumps and generates
    optimized build configurations using LLMs.
    
    Capabilities:
    - Multi-Provider Support (OpenAI, Anthropic, Ollama, etc.)
    - RAG Support: Queries local Qdrant vector DB for SDK specifics.
    - Web Fallback: Downloads docs if RAG is empty/disabled.
    """
    
    def __init__(self, provider: str = "OpenAI", model: str = "gpt-4o", 
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 config_manager = None, framework_manager = None):
        """
        Initialize the AI Agent.
        
        Args:
            provider: AI Service Provider
            model: Model Name
            api_key: API Credential
            base_url: Optional Endpoint (for LocalAI/Ollama)
            config_manager: Access to configuration
            framework_manager: Access to Core Components (RAGManager) - NEW in v1.5.0
        """
        self.logger = get_logger(__name__)
        self.provider = provider
        self.base_url = base_url
        self.config_manager = config_manager
        self.framework_manager = framework_manager
        self.litellm_model = self._format_model_name(provider, model)
        
        # Set API Keys securely only for this instance context if possible
        if api_key and api_key != "sk-dummy":
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

    def _get_rag_manager(self) -> Optional[RAGManager]:
        """Retrieves the RAG Manager instance if enabled and available."""
        if not self.framework_manager:
            return None
            
        # Check Config
        rag_enabled = False
        if hasattr(self.framework_manager.config, 'enable_rag_knowledge'):
            rag_enabled = self.framework_manager.config.enable_rag_knowledge
        
        if not rag_enabled:
            return None
            
        return self.framework_manager.get_component("rag_manager")

    def _fetch_documentation(self, sdk_name: str) -> str:
        """
        Fetches documentation context for the AI.
        
        Strategy (v1.5.0 Hybrid):
        1. RAG Search: Query local Vector DB for specific SDK build flags.
        2. Fallback: Fetch URL defined in SSOT (project_sources.yml).
        """
        context_text = ""
        used_source = "None"

        # --- STRATEGY 1: LOCAL RAG (Expert Mode) ---
        rag = self._get_rag_manager()
        if rag:
            self.logger.info(f"Querying Knowledge Base for '{sdk_name}'...")
            # Query design: Specific enough to find build flags, generic enough to find the SDK
            query = f"{sdk_name} SDK compilation flags build configuration optimization parameters"
            results = rag.search(query, limit=5, score_threshold=0.65)
            
            if results:
                self.logger.info(f"RAG Hit: Found {len(results)} relevant snippets.")
                context_text += "--- EXPERT KNOWLEDGE (Local RAG) ---\n"
                for res in results:
                    context_text += f"\n[Source: {res.source}]\n{res.content}\n"
                used_source = "RAG (Qdrant)"
                return context_text 

        # --- STRATEGY 2: NAIVE WEB RETRIEVAL (Fallback) ---
        if not context_text and self.config_manager:
            self.logger.info(f"RAG empty or disabled. Fallback to Web Retrieval for {sdk_name}...")
            
            sources = self.config_manager.get("source_repositories", {})
            url = ""
            doc_key_suffix = "docs_workflow"
            
            # Search logic for flattened or nested configs
            for key, val in sources.items():
                if sdk_name.lower() in key.lower():
                    if isinstance(val, dict) and doc_key_suffix in val:
                        url = val[doc_key_suffix]
                        break
                    elif key.endswith(doc_key_suffix) and isinstance(val, str):
                        url = val
                        break
            
            if url and url.startswith("http"): 
                try:
                    self.logger.info(f"Fetching docs from {url}...")
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        # Limit context to avoid token overflow
                        clean_text = resp.text[:15000] 
                        context_text = f"--- WEB KNOWLEDGE ({url}) ---\n{clean_text}"
                        used_source = "Web Scraper"
                except Exception as e:
                    self.logger.warning(f"Doc fetch failed: {e}")

        self.logger.debug(f"Documentation Context Source: {used_source}")
        return context_text

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
        
        # 2. Determine SDK Hint for Doc Fetching
        sdk_hint = "generic"
        lower_probe = probe_data.lower()
        if "nvidia" in lower_probe or "tegra" in lower_probe: sdk_hint = "nvidia"
        elif "rockchip" in lower_probe or "rk3" in lower_probe: sdk_hint = "rockchip"
        elif "hailo" in lower_probe: sdk_hint = "hailo"
        elif "intel" in lower_probe: sdk_hint = "intel"
        elif "riscv" in lower_probe: sdk_hint = "riscv"
        
        # 3. Fetch Context (RAG or Web)
        doc_context = self._fetch_documentation(sdk_hint)

        # 4. Construct System Prompt (HIGH PRECISION MODE)
        system_prompt = """
        You are 'Ditto', the Lead Architect for Edge-AI Deployment.
        Your Mission: Create a mathematically perfect, production-grade build configuration for the detected hardware.
        
        ### HARDWARE ONTOLOGY (Internalize this):
        - **SoC (System on Chip)** defines the NPU/GPU capabilities (e.g. RK3588 -> 6 TOPS NPU).
        - **CPU Architecture** defines the Instruction Set (e.g. aarch64 -> NEON, x86_64 -> AVX512).
        - **SDKs** are strictly coupled to the SoC Family (e.g. RKNN-Toolkit2 is ONLY for RK3566/88).
        - **Drivers** must match the Kernel version found in the probe.
        
        ### EXECUTION PROTOCOL:
        1. **DECODE PROBE:** Extract 'CPU_Implementer', 'NPU_Name', 'Instruction_Set', and 'Kernel_Version' from the Input.
        2. **CROSS-REFERENCE:** Search the 'Documentation Context' for these exact keywords. Find the matching CMake flags and Docker base images.
        3. **SECURE CONFIGURATION (Enterprise Security):**
           - Base Image: Must be a trusted vendor image (e.g. nvcr.io, rockchip) or Debian-Slim.
           - Packages: Only install compile-time dependencies. NO development tools in runtime.
           - Permissions: Do not use root for build execution if possible (user 'llmbuilder' is preferred).
           - Network: Use HTTPS only. Pin git commits if version is known.
        4. **CODE GENERATION:**
           - Generate 'setup_commands' that are idempotent and failure-proof (set -e).
           - 'quantization_logic' must handle the specific format required by the NPU (e.g. RKNN) vs CPU (GGUF).
        
        ### ZERO TOLERANCE POLICY:
        - Do not guess compiler flags. If `doc_context` is empty or ambiguous, use generic `-O3`.
        - Do not invent SDK versions. Use the ones from the Context.
        - If Hardware is unknown, default to "Generic CPU" mode.
        
        REQUIRED JSON STRUCTURE:
        {
            "module_name": "Str (e.g. Rockchip_RK3588_NPU)",
            "architecture": "aarch64|x86_64",
            "sdk": "Str (e.g. RKNN)",
            "base_os": "Docker Image Name",
            "packages": ["list", "of", "packages"],
            "cpu_flags": "GCC Flags",
            "cmake_flags": "CMake Flags",
            "setup_commands": "Bash code for Dockerfile setup (optional)",
            "quantization_logic": "Bash CASE block content for build.sh"
        }

        Documentation Context:
        {doc_context}
        """

        user_prompt = f"""
        --- INPUT: target_hardware_config.txt ---
        {probe_data[:8000]}
        
        Based on this probe, generate the optimal configuration JSON.
        """

        # 5. Call LLM
        try:
            # Parameter dynamisch aufbauen
            kwargs = {
                "model": self.litellm_model,
                "messages": [
                    {"role": "system", "content": system_prompt.replace("{doc_context}", doc_context)},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1 # Low temperature for precision
            }
            
            if hasattr(self, 'api_key') and self.api_key and self.api_key != "sk-dummy":
                kwargs["api_key"] = getattr(self, 'api_key', None)
            
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
            "setup_commands": config.get("setup_commands", "# Auto-generated setup by Ditto"),
            "detection_commands": "lscpu",
            "supported_boards": [module_name]
        }
        
        generator = ModuleGenerator(targets_dir)
        return generator.generate_module(gen_data)
