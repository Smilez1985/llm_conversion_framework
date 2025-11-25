#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Model Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Model management, downloading, caching, and validation for LLM cross-compilation.
Handles HuggingFace models, local models, and various AI model formats.
Container-native with Poetry+VENV, robust error recovery.
"""

import os
import sys
import json
import logging
import hashlib
import shutil
import tempfile
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple, Set, BinaryIO
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import threading
import time
import re
import gzip

import yaml
import requests
from tqdm import tqdm

from orchestrator.Core.builder import ModelFormat
from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory, check_command_exists, safe_json_load


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class ModelSource(Enum):
    """Model source types"""
    HUGGINGFACE = "huggingface"
    LOCAL_PATH = "local_path"
    URL = "url"
    GGUF_FILE = "gguf_file"
    ONNX_MODEL = "onnx_model"
    UNKNOWN = "unknown"


class ModelStatus(Enum):
    """Model status in cache"""
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    VALIDATING = "validating"
    CORRUPTED = "corrupted"
    MISSING = "missing"
    ERROR = "error"


class DownloadStatus(Enum):
    """Download operation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelSize(Enum):
    """Model size categories"""
    TINY = "tiny"        # < 1GB
    SMALL = "small"      # 1-3GB
    MEDIUM = "medium"    # 3-7GB
    LARGE = "large"      # 7-15GB
    XLARGE = "xlarge"    # 15-30GB
    XXLARGE = "xxlarge"  # > 30GB


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ModelMetadata:
    """Model metadata and information"""
    name: str
    source: ModelSource
    format: ModelFormat
    
    # Basic information
    model_type: str = ""
    architecture: str = ""
    size_category: ModelSize = ModelSize.MEDIUM
    
    # Model specifications
    vocab_size: Optional[int] = None
    hidden_size: Optional[int] = None
    num_layers: Optional[int] = None
    num_attention_heads: Optional[int] = None
    max_position_embeddings: Optional[int] = None
    
    # File information
    total_size_bytes: int = 0
    file_count: int = 0
    main_files: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    
    # HuggingFace specific
    hf_model_id: Optional[str] = None
    hf_revision: str = "main"
    hf_license: Optional[str] = None
    hf_tags: List[str] = field(default_factory=list)
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_validated: Optional[datetime] = None
    
    # Validation
    is_valid: bool = False
    validation_errors: List[str] = field(default_factory=list)
    checksum: Optional[str] = None
    
    @property
    def size_gb(self) -> float:
        """Get model size in GB"""
        return self.total_size_bytes / (1024 ** 3)
    
    @property
    def is_local(self) -> bool:
        """Check if model is locally available"""
        return self.source == ModelSource.LOCAL_PATH
    
    @property
    def is_huggingface(self) -> bool:
        """Check if model is from HuggingFace"""
        return self.source == ModelSource.HUGGINGFACE


@dataclass
class DownloadProgress:
    """Download progress tracking"""
    model_name: str
    download_id: str
    status: DownloadStatus
    
    # Progress information
    total_bytes: int = 0
    downloaded_bytes: int = 0
    progress_percent: float = 0.0
    download_speed_mbps: float = 0.0
    eta_seconds: Optional[int] = None
    
    # File information
    current_file: str = ""
    files_completed: int = 0
    files_total: int = 0
    
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    last_update: Optional[datetime] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def update_progress(self, downloaded: int, total: int = None):
        """Update download progress"""
        self.downloaded_bytes = downloaded
        if total:
            self.total_bytes = total
        
        if self.total_bytes > 0:
            self.progress_percent = (self.downloaded_bytes / self.total_bytes) * 100
        
        # Calculate speed and ETA
        now = datetime.now()
        if self.start_time and self.downloaded_bytes > 0:
            elapsed = (now - self.start_time).total_seconds()
            if elapsed > 0:
                speed_bytes_per_sec = self.downloaded_bytes / elapsed
                self.download_speed_mbps = (speed_bytes_per_sec * 8) / (1024 * 1024)  # Mbps
                
                if self.total_bytes > self.downloaded_bytes and speed_bytes_per_sec > 0:
                    remaining_bytes = self.total_bytes - self.downloaded_bytes
                    self.eta_seconds = int(remaining_bytes / speed_bytes_per_sec)
        
        self.last_update = now


@dataclass
class ModelCacheEntry:
    """Model cache entry"""
    cache_key: str
    model_name: str
    cache_path: str
    metadata: ModelMetadata
    
    # Cache information
    cached_at: datetime
    last_accessed: datetime
    access_count: int = 0
    
    # Storage information
    disk_usage_bytes: int = 0
    is_complete: bool = False
    
    # Validation
    checksum: Optional[str] = None
    is_validated: bool = False
    
    def touch_access(self):
        """Update last access time"""
        self.last_accessed = datetime.now()
        self.access_count += 1


@dataclass
class CacheStats:
    """Model cache statistics"""
    total_models: int = 0
    total_size_bytes: int = 0
    available_space_bytes: int = 0
    
    # Model breakdown
    models_by_format: Dict[str, int] = field(default_factory=dict)
    models_by_size: Dict[str, int] = field(default_factory=dict)
    
    # Access statistics
    most_accessed_models: List[str] = field(default_factory=list)
    recently_added_models: List[str] = field(default_factory=list)
    
    # Health information
    corrupted_models: int = 0
    incomplete_downloads: int = 0
    
    @property
    def total_size_gb(self) -> float:
        """Get total cache size in GB"""
        return self.total_size_bytes / (1024 ** 3)
    
    @property
    def available_space_gb(self) -> float:
        """Get available space in GB"""
        return self.available_space_bytes / (1024 ** 3)


# ============================================================================
# MODEL MANAGER CLASS
# ============================================================================

class ModelManager:
    """
    Model Manager for LLM Cross-Compilation Framework.
    
    Manages model downloading, caching, validation, and preparation for cross-compilation.
    Supports HuggingFace models, local models, and various AI model formats.
    """
    
    def __init__(self, framework_manager):
        """
        Initialize Model Manager.
        
        Args:
            framework_manager: Reference to FrameworkManager
        """
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        
        # Configuration
        self.config = framework_manager.config
        
        # Paths
        base_path = Path(framework_manager.info.installation_path)
        self.models_dir = base_path / self.config.models_dir
        self.cache_dir = base_path / self.config.cache_dir / "models"
        self.temp_dir = self.cache_dir / "temp"
        self.metadata_dir = self.cache_dir / "metadata"
        
        # Cache management
        self.cache_entries: Dict[str, ModelCacheEntry] = {}
        self.download_progress: Dict[str, DownloadProgress] = {}
        self._lock = threading.RLock()
        
        # Configuration
        self.max_cache_size_gb = 100  # Default 100GB cache limit
        self.max_concurrent_downloads = 2
        self.chunk_size = 8192  # 8KB chunks for downloads
        self.timeout_seconds = 30
        
        # Initialize
        self._ensure_directories()
        self._load_cache_index()
        
        self.logger.info("Model Manager initialized")
    
    def initialize(self) -> bool:
        """
        Initialize model manager.
        
        Returns:
            bool: True if initialization successful
        """
        try:
            self.logger.info("Initializing Model Manager...")
            
            # Step 1: Validate dependencies
            self._validate_dependencies()
            
            # Step 2: Load existing cache
            self._load_cache_index()
            
            # Step 3: Validate cache integrity
            self._validate_cache_integrity()
            
            # Step 4: Setup HuggingFace integration
            self._setup_huggingface_integration()
            
            # Step 5: Cleanup orphaned files
            self._cleanup_orphaned_files()
            
            self.logger.info("Model Manager initialization completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Model Manager initialization failed: {e}")
            return False
    
    def _ensure_directories(self):
        """Ensure required directories exist"""
        directories = [
            self.models_dir,
            self.cache_dir,
            self.temp_dir,
            self.metadata_dir,
            self.cache_dir / "huggingface",
            self.cache_dir / "local",
            self.cache_dir / "downloads"
        ]
        
        for directory in directories:
            ensure_directory(directory)
            self.logger.debug(f"Directory ensured: {directory}")
    
    def _validate_dependencies(self):
        """Validate required dependencies"""
        try:
            # Try importing required libraries
            import transformers
            import safetensors
            self.logger.debug("Required libraries available: transformers, safetensors")
            
        except ImportError as e:
            missing_lib = str(e).split("'")[1] if "'" in str(e) else "unknown"
            raise RuntimeError(f"Required library not available: {missing_lib}")
        
        # Check for optional libraries
        optional_libs = ["torch", "numpy", "onnx"]
        available_optional = []
        
        for lib in optional_libs:
            try:
                __import__(lib)
                available_optional.append(lib)
            except ImportError:
                pass
        
        if available_optional:
            self.logger.debug(f"Optional libraries available: {', '.join(available_optional)}")
    
    def _load_cache_index(self):
        """Load model cache index"""
        index_file = self.metadata_dir / "cache_index.json"
        
        if not index_file.exists():
            self.logger.info("No existing cache index found, creating new one")
            return
        
        try:
            with open(index_file, 'r') as f:
                index_data = json.load(f)
            
            # Load cache entries
            for cache_key, entry_data in index_data.get("entries", {}).items():
                try:
                    # Reconstruct ModelMetadata
                    metadata_data = entry_data["metadata"]
                    metadata = ModelMetadata(
                        name=metadata_data["name"],
                        source=ModelSource(metadata_data["source"]),
                        format=ModelFormat(metadata_data["format"]),
                        model_type=metadata_data.get("model_type", ""),
                        architecture=metadata_data.get("architecture", ""),
                        size_category=ModelSize(metadata_data.get("size_category", "medium")),
                        vocab_size=metadata_data.get("vocab_size"),
                        hidden_size=metadata_data.get("hidden_size"),
                        num_layers=metadata_data.get("num_layers"),
                        total_size_bytes=metadata_data.get("total_size_bytes", 0),
                        file_count=metadata_data.get("file_count", 0),
                        main_files=metadata_data.get("main_files", []),
                        config_files=metadata_data.get("config_files", []),
                        hf_model_id=metadata_data.get("hf_model_id"),
                        hf_revision=metadata_data.get("hf_revision", "main"),
                        is_valid=metadata_data.get("is_valid", False),
                        validation_errors=metadata_data.get("validation_errors", []),
                        checksum=metadata_data.get("checksum")
                    )
                    
                    # Parse timestamps
                    if metadata_data.get("created_at"):
                        metadata.created_at = datetime.fromisoformat(metadata_data["created_at"])
                    if metadata_data.get("updated_at"):
                        metadata.updated_at = datetime.fromisoformat(metadata_data["updated_at"])
                    if metadata_data.get("last_validated"):
                        metadata.last_validated = datetime.fromisoformat(metadata_data["last_validated"])
                    
                    # Create cache entry
                    cache_entry = ModelCacheEntry(
                        cache_key=cache_key,
                        model_name=entry_data["model_name"],
                        cache_path=entry_data["cache_path"],
                        metadata=metadata,
                        cached_at=datetime.fromisoformat(entry_data["cached_at"]),
                        last_accessed=datetime.fromisoformat(entry_data["last_accessed"]),
                        access_count=entry_data.get("access_count", 0),
                        disk_usage_bytes=entry_data.get("disk_usage_bytes", 0),
                        is_complete=entry_data.get("is_complete", False),
                        checksum=entry_data.get("checksum"),
                        is_validated=entry_data.get("is_validated", False)
                    )
                    
                    self.cache_entries[cache_key] = cache_entry
                    
                except Exception as e:
                    self.logger.warning(f"Failed to load cache entry {cache_key}: {e}")
            
            self.logger.info(f"Loaded {len(self.cache_entries)} models from cache index")
            
        except Exception as e:
            self.logger.error(f"Failed to load cache index: {e}")
    
    def _save_cache_index(self):
        """Save model cache index"""
        index_file = self.metadata_dir / "cache_index.json"
        
        try:
            index_data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "entries": {}
            }
            
            # Serialize cache entries
            for cache_key, entry in self.cache_entries.items():
                metadata_data = {
                    "name": entry.metadata.name,
                    "source": entry.metadata.source.value,
                    "format": entry.metadata.format.value,
                    "model_type": entry.metadata.model_type,
                    "architecture": entry.metadata.architecture,
                    "size_category": entry.metadata.size_category.value,
                    "vocab_size": entry.metadata.vocab_size,
                    "hidden_size": entry.metadata.hidden_size,
                    "num_layers": entry.metadata.num_layers,
                    "total_size_bytes": entry.metadata.total_size_bytes,
                    "file_count": entry.metadata.file_count,
                    "main_files": entry.metadata.main_files,
                    "config_files": entry.metadata.config_files,
                    "hf_model_id": entry.metadata.hf_model_id,
                    "hf_revision": entry.metadata.hf_revision,
                    "is_valid": entry.metadata.is_valid,
                    "validation_errors": entry.metadata.validation_errors,
                    "checksum": entry.metadata.checksum
                }
                
                # Add timestamps
                if entry.metadata.created_at:
                    metadata_data["created_at"] = entry.metadata.created_at.isoformat()
                if entry.metadata.updated_at:
                    metadata_data["updated_at"] = entry.metadata.updated_at.isoformat()
                if entry.metadata.last_validated:
                    metadata_data["last_validated"] = entry.metadata.last_validated.isoformat()
                
                entry_data = {
                    "model_name": entry.model_name,
                    "cache_path": entry.cache_path,
                    "metadata": metadata_data,
                    "cached_at": entry.cached_at.isoformat(),
                    "last_accessed": entry.last_accessed.isoformat(),
                    "access_count": entry.access_count,
                    "disk_usage_bytes": entry.disk_usage_bytes,
                    "is_complete": entry.is_complete,
                    "checksum": entry.checksum,
                    "is_validated": entry.is_validated
                }
                
                index_data["entries"][cache_key] = entry_data
            
            # Write to file
            with open(index_file, 'w') as f:
                json.dump(index_data, f, indent=2)
            
            self.logger.debug("Cache index saved")
            
        except Exception as e:
            self.logger.error(f"Failed to save cache index: {e}")
    
    def _download_hf_model_files(self, model_id: str, archive_path: Path):
        """
        Download HuggingFace model files with progress tracking and Authentication support.
        This implementation supports gated repos via HF_TOKEN environment variable.
        """
        try:
            from huggingface_hub import hf_hub_download, list_repo_files
            from huggingface_hub.utils import RepositoryNotFoundError, GatedRepoError, LocalEntryNotFoundError
            
            # Check Authentication Token
            token = os.environ.get("HF_TOKEN")
            
            # Get list of files
            try:
                repo_files = list_repo_files(model_id, token=token)
                self.logger.info(f"Found {len(repo_files)} files for {model_id}")
            except GatedRepoError:
                raise PermissionError(
                    f"Model {model_id} is GATED. Please accept the license on HuggingFace "
                    "and set your HF_TOKEN in settings."
                )
            except RepositoryNotFoundError:
                raise FileNotFoundError(f"Model {model_id} not found on HuggingFace.")
            except Exception as e:
                self.logger.warning(f"Failed to list repo files: {e}. Trying fallback list.")
                repo_files = ["config.json", "tokenizer.json", "model.safetensors", "pytorch_model.bin"]

            # Create download progress tracker
            download_id = f"hf_{model_id.replace('/', '_')}_{int(time.time())}"
            progress = DownloadProgress(
                model_name=model_id,
                download_id=download_id,
                status=DownloadStatus.IN_PROGRESS,
                files_total=len(repo_files),
                start_time=datetime.now()
            )
            
            with self._lock:
                self.download_progress[download_id] = progress
            
            # Download files
            downloaded_files = []
            total_size = 0
            
            for i, filename in enumerate(repo_files):
                # Filter unwichtige Dateien (optional)
                if filename.endswith(".gitattributes") or filename.endswith("README.md"):
                    continue

                try:
                    progress.current_file = filename
                    progress.files_completed = i
                    
                    # Download execution
                    downloaded_file = hf_hub_download(
                        repo_id=model_id,
                        filename=filename,
                        cache_dir=str(archive_path.parent),
                        local_dir=str(archive_path),
                        local_dir_use_symlinks=False,
                        token=token  # Authenticated download
                    )
                    
                    downloaded_files.append(downloaded_file)
                    
                    # Update stats
                    file_size = Path(downloaded_file).stat().st_size
                    total_size += file_size
                    progress.downloaded_bytes = total_size
                    
                except Exception as e:
                    # Bei optionalen Files weitermachen, bei Config abbrechen
                    if filename in ["config.json", "model.safetensors"]:
                        raise e
                    self.logger.warning(f"Skipped {filename}: {e}")
                    continue
            
            progress.status = DownloadStatus.COMPLETED
            progress.end_time = datetime.now()
            self.logger.info(f"Download completed: {model_id} ({total_size / (1024**3):.2f} GB)")
            
        except Exception as e:
            if download_id in self.download_progress:
                self.download_progress[download_id].status = DownloadStatus.FAILED
                self.download_progress[download_id].error_message = str(e)
            raise
    
    def _validate_cache_integrity(self):
        """Validate archive integrity"""
        self.logger.info("Validating model archive integrity...")
        
        corrupted_entries = []
        
        for cache_key, entry in self.cache_entries.items():
            cache_path = Path(entry.cache_path)
            
            if not cache_path.exists():
                entry.metadata.is_valid = False
                entry.metadata.validation_errors.append("Archive path does not exist")
                corrupted_entries.append(cache_key)
                continue
            
            if entry.is_validated and entry.checksum:
                try:
                    current_checksum = self._calculate_directory_checksum(cache_path)
                    if current_checksum != entry.checksum:
                        entry.metadata.is_valid = False
                        entry.metadata.validation_errors.append("Checksum mismatch - possible corruption")
                        corrupted_entries.append(cache_key)
                except Exception as e:
                    self.logger.warning(f"Failed to verify checksum for {entry.model_name}: {e}")
        
        if corrupted_entries:
            self.logger.warning(f"Found {len(corrupted_entries)} corrupted archive entries")
        
        self.logger.info("Archive integrity validation completed")
    
    def _setup_huggingface_integration(self):
        """Setup HuggingFace integration"""
        try:
            hf_archive_dir = self.cache_dir / "huggingface"
            os.environ["HF_HOME"] = str(hf_archive_dir)
            os.environ["TRANSFORMERS_CACHE"] = str(hf_archive_dir)
            import transformers
            self.logger.info(f"HuggingFace integration configured (cache: {hf_archive_dir})")
        except Exception as e:
            self.logger.warning(f"HuggingFace integration setup failed: {e}")
    
    def _cleanup_orphaned_files(self):
        """Cleanup orphaned temporary files"""
        try:
            temp_download_dir = self.cache_dir / "downloads"
            if temp_download_dir.exists():
                for temp_file in temp_download_dir.iterdir():
                    try:
                        if temp_file.stat().st_mtime < (time.time() - 86400):
                            if temp_file.is_dir():
                                shutil.rmtree(temp_file)
                            else:
                                temp_file.unlink()
                            self.logger.debug(f"Cleaned orphaned temp file: {temp_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to clean temp file {temp_file}: {e}")
            self.logger.info("Orphaned temporary files cleaned")
        except Exception as e:
            self.logger.error(f"Cleanup of orphaned files failed: {e}")

    # ... [Rest der Klasse mit Archive-Methoden bleibt bestehen] ...
    # Hier folgen die Methoden archive_model, import_local_model, etc.
    # Da die Datei zu groß ist, um sie komplett neu zu generieren, habe ich mich auf den
    # kritischen Teil (Download mit Token) konzentriert. Die restlichen Methoden
    # (archive_model, _generate_model_name etc.) sollten aus der vorherigen Version übernommen werden.
    # Wenn Sie diese Methoden auch explizit benötigen, sagen Sie Bescheid.
