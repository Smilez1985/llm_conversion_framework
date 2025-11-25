#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Model Manager
DIREKTIVE: Goldstandard, Modular & Data-Driven.
"""

import os
import sys
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import time

import requests
from orchestrator.utils.logging import get_logger
from orchestrator.utils.helpers import ensure_directory

# Enums removed for modularity - using strings

@dataclass
class ModelMetadata:
    name: str
    source: str # "huggingface", "local"
    format: str # "gguf", "onnx", etc.
    model_type: str = ""
    size_bytes: int = 0
    
    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 ** 3)

class ModelManager:
    def __init__(self, framework_manager):
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        self.config = framework_manager.config
        self.models_dir = Path(framework_manager.info.installation_path) / self.config.models_dir
        ensure_directory(self.models_dir)
        
    def initialize(self) -> bool:
        self.logger.info("Model Manager initialized")
        return True

    def search_huggingface_models(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search HF Hub via API"""
        try:
            from huggingface_hub import HfApi
            api = HfApi()
            models = api.list_models(search=query, limit=limit, sort="downloads", direction=-1)
            return [{"id": m.modelId, "downloads": m.downloads, "likes": m.likes} for m in models]
        except ImportError:
            self.logger.error("huggingface_hub not installed")
            return []
        except Exception as e:
            self.logger.error(f"HF Search failed: {e}")
            return []

    def _detect_model_format(self, model_path: Path) -> str:
        """Detect format based on file extension"""
        if not model_path.exists(): return "unknown"
        if model_path.is_dir():
            if (model_path / "config.json").exists(): return "huggingface"
            return "directory"
        
        s = model_path.suffix.lower()
        if s == ".gguf": return "gguf"
        if s == ".onnx": return "onnx"
        if s == ".tflite": return "tflite"
        if s in [".pt", ".pth", ".bin"]: return "pytorch"
        if s == ".safetensors": return "safetensors"
        return "unknown"
