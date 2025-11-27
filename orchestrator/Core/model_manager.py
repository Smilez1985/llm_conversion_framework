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

@dataclass
class ModelMetadata:
    name: str
    source: str
    format: str
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
        try:
            from huggingface_hub import HfApi
            api = HfApi()
            models = api.list_models(
                search=query, 
                limit=limit, 
                sort="downloads", 
                direction=-1,
                expand=["gated", "downloads", "likes"] 
            )
            
            results = []
            for m in models:
                is_gated = getattr(m, "gated", False)
                if is_gated not in [False, None]: is_gated = True
                else: is_gated = False
                    
                results.append({
                    "id": m.modelId,
                    "downloads": m.downloads,
                    "likes": m.likes,
                    "gated": is_gated
                })
            return results

        except ImportError:
            self.logger.error("huggingface_hub not installed")
            return []
        except Exception as e:
            self.logger.error(f"HF Search failed: {e}")
            return []

    def list_repo_files(self, repo_id: str, token: Optional[str] = None) -> List[str]:
        """Fetches file list from a repository."""
        try:
            from huggingface_hub import HfApi
            api = HfApi(token=token)
            files = api.list_repo_files(repo_id=repo_id)
            return files
        except Exception as e:
            self.logger.error(f"Failed to list files for {repo_id}: {e}")
            return []

    def download_file(self, repo_id: str, filename: str, token: Optional[str] = None) -> Optional[str]:
        try:
            from huggingface_hub import hf_hub_download
            self.logger.info(f"Downloading {filename} from {repo_id}...")
            
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=str(self.models_dir),
                token=token
            )
            self.logger.info(f"Download successful: {path}")
            return path
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return None

    def _detect_model_format(self, model_path: Path) -> str:
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
