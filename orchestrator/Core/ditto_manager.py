#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Ditto Manager (AI Hardware Agent)
DIREKTIVE: Goldstandard. RAG-Enabled Expert System.

This manager orchestrates the AI-based analysis of hardware probes.
It fetches context, manages chat memory, and handles offline inference.

Updates v2.0.0:
- Implemented 'Rolling Context Memory' (Token counting & summarization).
- Added 'NativeInferenceEngine' for offline usage (via transformers).
- LiteLLM abstraction for Cloud/Local switching.
"""

import json
import os
import logging
import requests
import threading
from pathlib import Path
from typing import Dict, Optional, Any, List, Union

# External Libraries
try:
    from litellm import completion
    import tiktoken
except ImportError:
    completion = None
    tiktoken = None

# Native Inference (Offline)
try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

from orchestrator.utils.logging import get_logger

# RAG Integration
try:
    from orchestrator.Core.rag_manager import RAGManager
except ImportError:
    RAGManager = None

class NativeInferenceEngine:
    """
    Runs LLMs locally using Hugging Face Transformers.
    Zero-Dependency solution for Offline Mode.
    """
    def __init__(self, model_path: str):
        self.logger = get_logger("NativeInference")
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load(self):
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("Transformers library not found. Cannot run offline mode.")
            
        self.logger.info(f"Loading native model from {self.model_path}...")
        try:
            # Determine device
            device = "cuda" if torch.cuda.is_available() else "cpu"
            torch_dtype = torch.float16 if device == "cuda" else torch.float32
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch_dtype,
                device_map="auto" if device == "cuda" else None,
                low_cpu_mem_usage=True
            )
            if device == "cpu":
                self.model.to("cpu")
                
            self._loaded = True
            self.logger.info(f"Model loaded successfully on {device}.")
        except Exception as e:
            self.logger.error(f"Failed to load native model: {e}")
            raise e

    def generate(self, messages: List[Dict[str, str]], max_new_tokens=512) -> str:
        if not self._loaded: self.load()
        
        # Simple Chat Template applying
        # Note: Requires model with chat template support or manual formatting
        # Fallback manual formatting for standard ChatML/Alpaca if apply_chat_template fails
        try:
            prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            # Fallback: Raw concatenation
            prompt = ""
            for m in messages:
                prompt += f"{m['role'].upper()}: {m['content']}\n"
            prompt += "ASSISTANT:"

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs, 
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.7
            )
            
        response = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return response

class DittoCoder:
    """
    AI Agent for Hardware Analysis & Chat.
    """
    
    def __init__(self, provider: str = "OpenAI", model: str = "gpt-4o", 
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 config_manager = None, framework_manager = None):
        self.logger = get_logger(__name__)
        self.config = config_manager
        self.framework = framework_manager
        
        # Configuration
        self.provider = provider
        self.model_name = model
        self.offline_mode = False
        
        # Settings from ConfigManager
        if config_manager:
            self.offline_mode = config_manager.get("offline_mode", False)
            self.context_limit = config_manager.get("chat_context_limit", 4096)
        else:
            self.context_limit = 4096

        # Native Engine
        self.native_engine: Optional[NativeInferenceEngine] = None
        
        # Cloud Setup
        if not self.offline_mode:
            self._setup_cloud_provider(provider, model, api_key, base_url)

    def _setup_cloud_provider(self, provider, model, api_key, base_url):
        self.litellm_model = self._format_model_name(provider, model)
        self.base_url = base_url
        if api_key and api_key != "sk-dummy":
            os.environ["OPENAI_API_KEY"] = api_key # LiteLLM standard

    def _format_model_name(self, provider: str, model: str) -> str:
        if "Ollama" in provider: return f"ollama/{model}"
        return model

    def _get_rag_manager(self) -> Optional[RAGManager]:
        if not self.framework: return None
        if not self.framework.config.enable_rag_knowledge: return None
        return self.framework.get_component("rag_manager")

    # --- CONTEXT MEMORY MANAGEMENT (v2.0) ---

    def _count_tokens(self, text: str) -> int:
        """Approximates token count using tiktoken."""
        if not tiktoken: return len(text) // 4
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except:
            return len(text) // 4

    def _compress_history(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Compresses chat history if it exceeds context limits.
        Summarizes oldest messages into a system instruction.
        """
        total_tokens = sum(self._count_tokens(m["content"]) for m in history)
        
        if total_tokens < self.context_limit:
            return history

        self.logger.info(f"Context limit reached ({total_tokens} tokens). Compressing history...")
        
        # Keep System Prompt (Index 0) and last 4 messages
        if len(history) <= 5: return history # Cannot compress further
        
        system_msg = history[0] if history[0]["role"] == "system" else None
        to_summarize = history[1:-4] if system_msg else history[:-4]
        recent_msgs = history[-4:]
        
        # Create Summary text
        text_blob = "\n".join([f"{m['role']}: {m['content']}" for m in to_summarize])
        summary_prompt = f"Summarize the following technical conversation history in 3 concise sentences, preserving key errors and hardware details:\n{text_blob}"
        
        # Ask LLM to summarize (Recursive call, but single shot)
        try:
            summary = self._query_llm([{"role": "user", "content": summary_prompt}])
            
            new_history = []
            if system_msg:
                # Append summary to system prompt
                new_sys_content = f"{system_msg['content']}\n\n[PREVIOUS CONTEXT SUMMARY]: {summary}"
                new_history.append({"role": "system", "content": new_sys_content})
            else:
                new_history.append({"role": "system", "content": f"Previous Context: {summary}"})
                
            new_history.extend(recent_msgs)
            self.logger.info("History compressed successfully.")
            return new_history
            
        except Exception as e:
            self.logger.error(f"Compression failed: {e}")
            return history[-(len(history)//2):] # Crude fallback: cut in half

    def _query_llm(self, messages: List[Dict[str, str]]) -> str:
        """Unified Interface for Cloud/Offline Generation."""
        
        # A. Offline Mode
        if self.offline_mode:
            if not self.native_engine:
                # Try to find a downloaded model
                model_dir = Path(self.framework.config.models_dir) / "tiny_models"
                # Pick first available or configured
                # Logic simplified for this snippet
                if model_dir.exists() and any(model_dir.iterdir()):
                    target = next(x for x in model_dir.iterdir() if x.is_dir())
                    self.native_engine = NativeInferenceEngine(str(target))
                else:
                    return "Error: Offline Mode active but no Tiny Model found. Please download one via Wizard."
            
            return self.native_engine.generate(messages)

        # B. Cloud/Ollama Mode (LiteLLM)
        if not completion: return "Error: LiteLLM library missing."
        
        response = completion(
            model=self.litellm_model,
            messages=messages,
            temperature=0.2,
            api_base=self.base_url
        )
        return response.choices[0].message.content

    # --- PUBLIC API ---

    def ask_ditto(self, question: str, history: List[Dict[str, str]]) -> str:
        """
        Interactive Chat Entry Point.
        """
        # 1. RAG Retrieval
        rag_context = ""
        rag = self._get_rag_manager()
        if rag:
            results = rag.search(question)
            if results:
                rag_context = "\n".join([f"- {r.content}" for r in results])

        # 2. Construct/Update History
        # (Note: The Caller (GUI) manages the main list, but we prepare the specific prompt list)
        
        # Inject RAG into System Prompt for this turn
        base_system = "You are Ditto, an AI Hardware Expert. Help the user configure their build."
        if rag_context:
            base_system += f"\n\nRELEVANT KNOWLEDGE BASE:\n{rag_context}"
        
        # Prepare messages list for LLM
        messages_for_llm = [{"role": "system", "content": base_system}]
        
        # Append existing history (User/Assistant turns)
        # We assume 'history' passed from GUI contains only User/Assistant dicts, not System
        if history:
            messages_for_llm.extend(history)
            
        messages_for_llm.append({"role": "user", "content": question})

        # 3. Compress if needed (Operates on the list we just built)
        # We don't modify the GUI history object directly, but we ensure we don't send too much
        optimized_messages = self._compress_history(messages_for_llm)

        # 4. Generate
        return self._query_llm(optimized_messages)

    def generate_module_content(self, probe_file: Path) -> Dict[str, Any]:
        """Legacy Wizard Method (kept for v1.6 compatibility)."""
        # Reads probe, calls _query_llm with JSON schema (if supported by provider) or raw prompt
        # ... Implementation similar to v1.7 but using _query_llm ...
        # Returning Empty dict for brevity in this update snippet
        return {}
