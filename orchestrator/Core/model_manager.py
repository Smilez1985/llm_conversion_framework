#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Model Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Model management, downloading, caching, and validation for LLM cross-compilation.
Handles HuggingFace models, local models, and various AI model formats.
Container-native with Poetry+VENV, robust error recovery.

Key Responsibilities:
- HuggingFace model downloading with resumable transfers
- Local model caching and storage management
- Model format detection and validation
- Model metadata extraction and analysis
- Size calculation and disk space management
- Integration with transformers, safetensors, GGUF
- Model conversion preparation
- Cache cleanup and organization
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

    # ========================================================================
    # ARCHIVAL SYSTEM (NEVER DELETE POLICY)
    # ========================================================================
    
    def archive_model(self, model_source: str, model_name: str = None, 
                     source_type: ModelSource = ModelSource.HUGGINGFACE,
                     version: str = None) -> str:
        """
        Archive a model with never-delete policy.
        
        Args:
            model_source: Model source (HF model ID, local path, URL)
            model_name: Custom model name (auto-generated if None)
            source_type: Type of model source
            version: Version tag (auto-generated if None)
            
        Returns:
            str: Archive key for tracking
        """
        with self._lock:
            self.logger.info(f"Archiving model: {model_source}")
            
            # Generate archive metadata
            if not model_name:
                model_name = self._generate_model_name(model_source, source_type)
            
            if not version:
                version = self._generate_version_tag(model_name)
            
            archive_key = f"{model_name}:{version}"
            
            # Check if already archived
            if archive_key in self.cache_entries:
                existing_entry = self.cache_entries[archive_key]
                existing_entry.touch_access()
                self.logger.info(f"Model already archived: {archive_key}")
                return archive_key
            
            # Create archive entry
            archive_path = self._get_archive_path(model_name, version, source_type)
            
            try:
                # Download/copy model to archive
                if source_type == ModelSource.HUGGINGFACE:
                    metadata = self._archive_huggingface_model(model_source, archive_path)
                elif source_type == ModelSource.LOCAL_PATH:
                    metadata = self._archive_local_model(model_source, archive_path)
                elif source_type == ModelSource.URL:
                    metadata = self._archive_url_model(model_source, archive_path)
                else:
                    raise ValueError(f"Unsupported source type: {source_type}")
                
                # Create archive entry
                archive_entry = ModelCacheEntry(
                    cache_key=archive_key,
                    model_name=model_name,
                    cache_path=str(archive_path),
                    metadata=metadata,
                    cached_at=datetime.now(),
                    last_accessed=datetime.now(),
                    access_count=1,
                    disk_usage_bytes=self._calculate_directory_size(archive_path),
                    is_complete=True,
                    checksum=self._calculate_directory_checksum(archive_path),
                    is_validated=True
                )
                
                # Add to registry
                self.cache_entries[archive_key] = archive_entry
                
                # Save updated index
                self._save_cache_index()
                
                self.logger.info(f"Model archived successfully: {archive_key} ({archive_entry.metadata.size_gb:.2f} GB)")
                return archive_key
                
            except Exception as e:
                self.logger.error(f"Failed to archive model {model_source}: {e}")
                raise
    
    def import_local_model(self, local_path: str, model_name: str = None, 
                          preserve_structure: bool = True) -> str:
        """
        Import a local model into the archive.
        
        Args:
            local_path: Path to local model
            model_name: Custom model name
            preserve_structure: Whether to preserve directory structure
            
        Returns:
            str: Archive key
        """
        local_model_path = Path(local_path)
        
        if not local_model_path.exists():
            raise ValueError(f"Local model path does not exist: {local_path}")
        
        # Auto-generate model name if not provided
        if not model_name:
            model_name = f"local_{local_model_path.name}"
        
        # Detect model format
        model_format = self._detect_model_format(local_model_path)
        
        self.logger.info(f"Importing local model: {local_path} -> {model_name}")
        
        return self.archive_model(
            model_source=str(local_model_path),
            model_name=model_name,
            source_type=ModelSource.LOCAL_PATH
        )
    
    def create_workflow_artifact(self, build_id: str, stage: str, source_archive_key: str, 
                               artifact_path: str) -> str:
        """
        Create workflow artifact entry (intermediate build results).
        
        Args:
            build_id: Build identifier
            stage: Build stage (e.g., 'gguf', 'quantized_q4_0')
            source_archive_key: Source model archive key
            artifact_path: Path to artifact files
            
        Returns:
            str: Artifact archive key
        """
        artifact_name = f"workflow_{build_id}_{stage}"
        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifact_key = f"{artifact_name}:{version}"
        
        # Create artifact archive path
        artifact_archive_path = self.cache_dir / "workflow-artifacts" / build_id / stage
        ensure_directory(artifact_archive_path)
        
        # Copy artifact to archive
        source_path = Path(artifact_path)
        if source_path.is_dir():
            shutil.copytree(source_path, artifact_archive_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, artifact_archive_path)
        
        # Detect format of artifact
        artifact_format = self._detect_model_format(artifact_archive_path)
        
        # Create metadata
        metadata = ModelMetadata(
            name=artifact_name,
            source=ModelSource.LOCAL_PATH,
            format=artifact_format,
            model_type="workflow_artifact",
            total_size_bytes=self._calculate_directory_size(artifact_archive_path),
            created_at=datetime.now(),
            is_valid=True
        )
        
        # Link to source model
        metadata.hf_model_id = f"derived_from:{source_archive_key}"
        
        # Create archive entry
        artifact_entry = ModelCacheEntry(
            cache_key=artifact_key,
            model_name=artifact_name,
            cache_path=str(artifact_archive_path),
            metadata=metadata,
            cached_at=datetime.now(),
            last_accessed=datetime.now(),
            access_count=1,
            disk_usage_bytes=metadata.total_size_bytes,
            is_complete=True,
            checksum=self._calculate_directory_checksum(artifact_archive_path),
            is_validated=True
        )
        
        # Add to registry
        with self._lock:
            self.cache_entries[artifact_key] = artifact_entry
            self._save_cache_index()
        
        self.logger.info(f"Workflow artifact archived: {artifact_key}")
        return artifact_key
    
    def _generate_model_name(self, model_source: str, source_type: ModelSource) -> str:
        """Generate standardized model name"""
        if source_type == ModelSource.HUGGINGFACE:
            # Convert HF model ID to safe filename
            return model_source.replace("/", "_").replace("-", "_")
        elif source_type == ModelSource.LOCAL_PATH:
            return f"local_{Path(model_source).name}"
        elif source_type == ModelSource.URL:
            # Extract filename from URL
            return f"url_{Path(model_source).name}"
        else:
            return f"model_{int(time.time())}"
    
    def _generate_version_tag(self, model_name: str) -> str:
        """Generate version tag for model"""
        # Check existing versions
        existing_versions = []
        for key in self.cache_entries.keys():
            if key.startswith(f"{model_name}:"):
                version = key.split(":", 1)[1]
                if version.startswith("v"):
                    try:
                        version_num = float(version[1:])
                        existing_versions.append(version_num)
                    except ValueError:
                        pass
        
        # Generate next version
        if existing_versions:
            next_version = max(existing_versions) + 0.1
            return f"v{next_version:.1f}"
        else:
            return "v1.0"
    
    def _get_archive_path(self, model_name: str, version: str, source_type: ModelSource) -> Path:
        """Get archive path for model"""
        if source_type == ModelSource.HUGGINGFACE:
            return self.cache_dir / "huggingface" / model_name / version
        elif source_type == ModelSource.LOCAL_PATH:
            return self.cache_dir / "local" / model_name / version
        else:
            return self.cache_dir / "external" / model_name / version
    
    def _archive_huggingface_model(self, model_id: str, archive_path: Path) -> ModelMetadata:
        """Archive HuggingFace model"""
        ensure_directory(archive_path)
        
        try:
            # Import transformers for downloading
            from transformers import AutoConfig, AutoTokenizer
            import requests
            
            # Download config first to get metadata
            try:
                config = AutoConfig.from_pretrained(model_id)
                config.save_pretrained(archive_path)
            except Exception as e:
                self.logger.warning(f"Failed to download config for {model_id}: {e}")
                config = None
            
            # Download tokenizer
            try:
                tokenizer = AutoTokenizer.from_pretrained(model_id)
                tokenizer.save_pretrained(archive_path)
            except Exception as e:
                self.logger.warning(f"Failed to download tokenizer for {model_id}: {e}")
            
            # Download model files using HF Hub API
            self._download_hf_model_files(model_id, archive_path)
            
            # Create metadata
            metadata = ModelMetadata(
                name=model_id.replace("/", "_"),
                source=ModelSource.HUGGINGFACE,
                format=ModelFormat.HUGGINGFACE,
                hf_model_id=model_id,
                total_size_bytes=self._calculate_directory_size(archive_path),
                created_at=datetime.now(),
                is_valid=True
            )
            
            # Extract config information
            if config:
                metadata.model_type = getattr(config, 'model_type', '')
                metadata.architecture = getattr(config, 'architectures', ['unknown'])[0] if hasattr(config, 'architectures') else 'unknown'
                metadata.vocab_size = getattr(config, 'vocab_size', None)
                metadata.hidden_size = getattr(config, 'hidden_size', None)
                metadata.num_layers = getattr(config, 'num_hidden_layers', None)
                metadata.num_attention_heads = getattr(config, 'num_attention_heads', None)
                metadata.max_position_embeddings = getattr(config, 'max_position_embeddings', None)
            
            # Categorize by size
            size_gb = metadata.size_gb
            if size_gb < 1:
                metadata.size_category = ModelSize.TINY
            elif size_gb < 3:
                metadata.size_category = ModelSize.SMALL
            elif size_gb < 7:
                metadata.size_category = ModelSize.MEDIUM
            elif size_gb < 15:
                metadata.size_category = ModelSize.LARGE
            elif size_gb < 30:
                metadata.size_category = ModelSize.XLARGE
            else:
                metadata.size_category = ModelSize.XXLARGE
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Failed to archive HuggingFace model {model_id}: {e}")
            raise
    
    def _archive_local_model(self, local_path: str, archive_path: Path) -> ModelMetadata:
        """Archive local model"""
        source_path = Path(local_path)
        ensure_directory(archive_path)
        
        # Copy model to archive
        if source_path.is_dir():
            shutil.copytree(source_path, archive_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, archive_path / source_path.name)
        
        # Detect format and create metadata
        model_format = self._detect_model_format(archive_path)
        
        metadata = ModelMetadata(
            name=source_path.name,
            source=ModelSource.LOCAL_PATH,
            format=model_format,
            total_size_bytes=self._calculate_directory_size(archive_path),
            created_at=datetime.now(),
            is_valid=True
        )
        
        # Try to extract additional metadata
        self._extract_model_metadata(archive_path, metadata)
        
        return metadata
    
    def _archive_url_model(self, url: str, archive_path: Path) -> ModelMetadata:
        """Archive model from URL"""
        ensure_directory(archive_path)
        
        # Download from URL
        filename = Path(url).name or "model"
        target_file = archive_path / filename
        
        self._download_file_with_progress(url, target_file)
        
        # Detect format and create metadata
        model_format = self._detect_model_format(archive_path)
        
        metadata = ModelMetadata(
            name=filename,
            source=ModelSource.URL,
            format=model_format,
            total_size_bytes=self._calculate_directory_size(archive_path),
            created_at=datetime.now(),
            is_valid=True
        )
        
        return metadata
    
    def _detect_model_format(self, model_path: Path) -> ModelFormat:
        """Detect model format from files"""
        if not model_path.exists():
            return ModelFormat.HUGGINGFACE  # Default
        
        files = list(model_path.rglob("*")) if model_path.is_dir() else [model_path]
        file_names = [f.name.lower() for f in files if f.is_file()]
        
        # Check for specific formats
        if any(name.endswith('.gguf') for name in file_names):
            return ModelFormat.GGUF
        elif any(name.endswith('.onnx') for name in file_names):
            return ModelFormat.ONNX
        elif any(name.endswith('.tflite') for name in file_names):
            return ModelFormat.TENSORFLOW_LITE
        elif any(name in ['pytorch_model.bin', 'model.safetensors'] for name in file_names):
            return ModelFormat.HUGGINGFACE
        elif any(name.endswith('.pt') or name.endswith('.pth') for name in file_names):
            return ModelFormat.PYTORCH_MOBILE
        else:
            return ModelFormat.HUGGINGFACE  # Default fallback
            
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
    
    def _download_file_with_progress(self, url: str, target_file: Path, 
                                   chunk_size: int = None) -> bool:
        """Download file from URL with progress tracking"""
        if chunk_size is None:
            chunk_size = self.chunk_size
        
        try:
            # Create download progress tracker
            download_id = f"url_{int(time.time())}"
            progress = DownloadProgress(
                model_name=str(target_file.name),
                download_id=download_id,
                status=DownloadStatus.IN_PROGRESS,
                current_file=str(target_file.name),
                start_time=datetime.now()
            )
            
            with self._lock:
                self.download_progress[download_id] = progress
            
            # Start download
            response = requests.get(url, stream=True, timeout=self.timeout_seconds)
            response.raise_for_status()
            
            # Get total size if available
            total_size = int(response.headers.get('content-length', 0))
            progress.total_bytes = total_size
            
            downloaded = 0
            
            with open(target_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress.update_progress(downloaded, total_size)
            
            # Verify download
            actual_size = target_file.stat().st_size
            if total_size > 0 and actual_size != total_size:
                raise RuntimeError(f"Download incomplete: expected {total_size}, got {actual_size}")
            
            progress.status = DownloadStatus.COMPLETED
            progress.end_time = datetime.now()
            
            self.logger.info(f"File download completed: {target_file.name} ({actual_size / (1024*1024):.1f} MB)")
            return True
            
        except Exception as e:
            if download_id in self.download_progress:
                self.download_progress[download_id].status = DownloadStatus.FAILED
                self.download_progress[download_id].error_message = str(e)
            
            # Clean up partial download
            if target_file.exists():
                target_file.unlink()
            
            self.logger.error(f"File download failed: {url} - {e}")
            return False
    
    def _extract_model_metadata(self, model_path: Path, metadata: ModelMetadata):
        """Extract detailed metadata from model files"""
        try:
            # Look for config.json (HuggingFace format)
            config_file = model_path / "config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                metadata.model_type = config.get('model_type', '')
                metadata.architecture = config.get('architectures', ['unknown'])[0] if 'architectures' in config else 'unknown'
                metadata.vocab_size = config.get('vocab_size')
                metadata.hidden_size = config.get('hidden_size')
                metadata.num_layers = config.get('num_hidden_layers')
                metadata.num_attention_heads = config.get('num_attention_heads')
                metadata.max_position_embeddings = config.get('max_position_embeddings')
                
                self.logger.debug(f"Extracted HuggingFace config metadata for {metadata.name}")
            
            # Look for GGUF metadata
            gguf_files = list(model_path.glob("*.gguf"))
            if gguf_files:
                try:
                    # Try to extract GGUF metadata (basic implementation)
                    gguf_file = gguf_files[0]
                    with open(gguf_file, 'rb') as f:
                        # Read GGUF header (simplified)
                        magic = f.read(4)
                        if magic == b'GGUF':
                            metadata.model_type = "gguf"
                            metadata.file_count = len(gguf_files)
                            self.logger.debug(f"Detected GGUF format for {metadata.name}")
                except Exception as e:
                    self.logger.warning(f"Failed to read GGUF metadata: {e}")
            
            # Count files and calculate total size
            if model_path.is_dir():
                all_files = list(model_path.rglob("*"))
                model_files = [f for f in all_files if f.is_file()]
                
                metadata.file_count = len(model_files)
                metadata.total_size_bytes = sum(f.stat().st_size for f in model_files)
                
                # Categorize files
                metadata.main_files = []
                metadata.config_files = []
                
                for f in model_files:
                    filename = f.name.lower()
                    if any(pattern in filename for pattern in ['model', 'pytorch', 'safetensors', '.gguf', '.onnx']):
                        metadata.main_files.append(f.name)
                    elif any(pattern in filename for pattern in ['config', 'tokenizer', 'vocab']):
                        metadata.config_files.append(f.name)
            
            # Update size category based on actual size
            size_gb = metadata.size_gb
            if size_gb < 1:
                metadata.size_category = ModelSize.TINY
            elif size_gb < 3:
                metadata.size_category = ModelSize.SMALL
            elif size_gb < 7:
                metadata.size_category = ModelSize.MEDIUM
            elif size_gb < 15:
                metadata.size_category = ModelSize.LARGE
            elif size_gb < 30:
                metadata.size_category = ModelSize.XLARGE
            else:
                metadata.size_category = ModelSize.XXLARGE
            
            metadata.updated_at = datetime.now()
            
        except Exception as e:
            self.logger.warning(f"Failed to extract model metadata: {e}")
    
    def _calculate_directory_size(self, directory: Path) -> int:
        """Calculate total size of directory"""
        if not directory.exists():
            return 0
        
        if directory.is_file():
            return directory.stat().st_size
        
        total_size = 0
        for item in directory.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size
        
        return total_size
    
    def _calculate_directory_checksum(self, directory: Path) -> str:
        """Calculate checksum for directory contents"""
        hasher = hashlib.sha256()
        
        if directory.is_file():
            with open(directory, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
        else:
            # Sort files for consistent checksum
            files = sorted(directory.rglob("*"))
            for file_path in files:
                if file_path.is_file():
                    # Add filename to hash for structure integrity
                    hasher.update(str(file_path.relative_to(directory)).encode())
                    
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hasher.update(chunk)
        
        return hasher.hexdigest()
    
    # ========================================================================
    # PUBLIC API METHODS
    # ========================================================================
    
    def list_archived_models(self, include_artifacts: bool = False) -> List[Dict[str, Any]]:
        """
        List all archived models.
        
        Args:
            include_artifacts: Whether to include workflow artifacts
            
        Returns:
            List[dict]: Model information
        """
        models = []
        
        for archive_key, entry in self.cache_entries.items():
            # Skip workflow artifacts unless requested
            if not include_artifacts and entry.metadata.model_type == "workflow_artifact":
                continue
            
            model_info = {
                "archive_key": archive_key,
                "name": entry.model_name,
                "source": entry.metadata.source.value,
                "format": entry.metadata.format.value,
                "size_gb": entry.metadata.size_gb,
                "size_category": entry.metadata.size_category.value,
                "archived_at": entry.cached_at.isoformat(),
                "last_accessed": entry.last_accessed.isoformat(),
                "access_count": entry.access_count,
                "is_valid": entry.metadata.is_valid,
                "archive_path": entry.cache_path
            }
            
            # Add model-specific information
            if entry.metadata.hf_model_id:
                model_info["hf_model_id"] = entry.metadata.hf_model_id
            
            if entry.metadata.architecture:
                model_info["architecture"] = entry.metadata.architecture
            
            if entry.metadata.vocab_size:
                model_info["vocab_size"] = entry.metadata.vocab_size
            
            models.append(model_info)
        
        # Sort by last accessed (most recent first)
        models.sort(key=lambda x: x["last_accessed"], reverse=True)
        
        return models
    
    def get_model_info(self, archive_key: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about an archived model.
        
        Args:
            archive_key: Model archive key
            
        Returns:
            dict: Detailed model information or None
        """
        entry = self.cache_entries.get(archive_key)
        if not entry:
            return None
        
        # Update access tracking
        entry.touch_access()
        
        model_info = {
            "archive_key": archive_key,
            "name": entry.model_name,
            "metadata": {
                "source": entry.metadata.source.value,
                "format": entry.metadata.format.value,
                "model_type": entry.metadata.model_type,
                "architecture": entry.metadata.architecture,
                "size_gb": entry.metadata.size_gb,
                "size_category": entry.metadata.size_category.value,
                "vocab_size": entry.metadata.vocab_size,
                "hidden_size": entry.metadata.hidden_size,
                "num_layers": entry.metadata.num_layers,
                "num_attention_heads": entry.metadata.num_attention_heads,
                "max_position_embeddings": entry.metadata.max_position_embeddings,
                "file_count": entry.metadata.file_count,
                "main_files": entry.metadata.main_files,
                "config_files": entry.metadata.config_files,
                "is_valid": entry.metadata.is_valid,
                "validation_errors": entry.metadata.validation_errors
            },
            "archive_info": {
                "archive_path": entry.cache_path,
                "archived_at": entry.cached_at.isoformat(),
                "last_accessed": entry.last_accessed.isoformat(),
                "access_count": entry.access_count,
                "disk_usage_bytes": entry.disk_usage_bytes,
                "is_complete": entry.is_complete,
                "checksum": entry.checksum
            },
            "huggingface": {
                "model_id": entry.metadata.hf_model_id,
                "revision": entry.metadata.hf_revision,
                "license": entry.metadata.hf_license,
                "tags": entry.metadata.hf_tags
            } if entry.metadata.hf_model_id else None
        }
        
        # Add timestamps
        if entry.metadata.created_at:
            model_info["metadata"]["created_at"] = entry.metadata.created_at.isoformat()
        if entry.metadata.updated_at:
            model_info["metadata"]["updated_at"] = entry.metadata.updated_at.isoformat()
        if entry.metadata.last_validated:
            model_info["metadata"]["last_validated"] = entry.metadata.last_validated.isoformat()
        
        return model_info
    
    def get_model_path(self, archive_key: str) -> Optional[Path]:
        """
        Get file system path to archived model.
        
        Args:
            archive_key: Model archive key
            
        Returns:
            Path: Path to model files or None
        """
        entry = self.cache_entries.get(archive_key)
        if not entry:
            return None
        
        # Update access tracking
        entry.touch_access()
        
        model_path = Path(entry.cache_path)
        if not model_path.exists():
            self.logger.warning(f"Archive path does not exist: {model_path}")
            return None
        
        return model_path
    
    def validate_model(self, archive_key: str, deep_validation: bool = False) -> Dict[str, Any]:
        """
        Validate an archived model.
        
        Args:
            archive_key: Model archive key
            deep_validation: Whether to perform deep validation (checksum verification)
            
        Returns:
            dict: Validation results
        """
        entry = self.cache_entries.get(archive_key)
        if not entry:
            return {
                "valid": False,
                "errors": [f"Model archive key not found: {archive_key}"]
            }
        
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "archive_key": archive_key,
            "validation_time": datetime.now().isoformat()
        }
        
        # Check if archive path exists
        archive_path = Path(entry.cache_path)
        if not archive_path.exists():
            validation_result["valid"] = False
            validation_result["errors"].append("Archive path does not exist")
            return validation_result
        
        # Basic file structure validation
        try:
            if archive_path.is_dir():
                files = list(archive_path.rglob("*"))
                if not files:
                    validation_result["valid"] = False
                    validation_result["errors"].append("Archive directory is empty")
                    return validation_result
                
                # Check for required files based on format
                if entry.metadata.format == ModelFormat.HUGGINGFACE:
                    required_files = ["config.json"]
                    for required_file in required_files:
                        if not (archive_path / required_file).exists():
                            validation_result["warnings"].append(f"Missing recommended file: {required_file}")
                
                # Update file count and size
                file_count = len([f for f in files if f.is_file()])
                total_size = sum(f.stat().st_size for f in files if f.is_file())
                
                if file_count != entry.metadata.file_count:
                    validation_result["warnings"].append(f"File count mismatch: expected {entry.metadata.file_count}, found {file_count}")
                
                if abs(total_size - entry.metadata.total_size_bytes) > (1024 * 1024):  # 1MB tolerance
                    validation_result["warnings"].append(f"Size mismatch: expected {entry.metadata.total_size_bytes}, found {total_size}")
            
            # Deep validation (checksum verification)
            if deep_validation and entry.checksum:
                try:
                    current_checksum = self._calculate_directory_checksum(archive_path)
                    if current_checksum != entry.checksum:
                        validation_result["valid"] = False
                        validation_result["errors"].append("Checksum verification failed - possible corruption")
                    else:
                        validation_result["checksum_verified"] = True
                except Exception as e:
                    validation_result["warnings"].append(f"Checksum verification failed: {e}")
            
            # Update validation status
            entry.metadata.is_valid = validation_result["valid"]
            entry.metadata.validation_errors = validation_result["errors"]
            entry.metadata.last_validated = datetime.now()
            
            # Save updated index
            self._save_cache_index()
            
        except Exception as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Validation error: {e}")
        
        return validation_result
    
    def search_models(self, query: str, source_filter: ModelSource = None, 
                     format_filter: ModelFormat = None) -> List[Dict[str, Any]]:
        """
        Search archived models.
        
        Args:
            query: Search query (matches name, model_id, architecture)
            source_filter: Filter by model source
            format_filter: Filter by model format
            
        Returns:
            List[dict]: Matching models
        """
        query_lower = query.lower()
        matching_models = []
        
        for archive_key, entry in self.cache_entries.items():
            # Apply filters
            if source_filter and entry.metadata.source != source_filter:
                continue
            
            if format_filter and entry.metadata.format != format_filter:
                continue
            
            # Search in various fields
            searchable_text = " ".join([
                entry.model_name.lower(),
                entry.metadata.hf_model_id.lower() if entry.metadata.hf_model_id else "",
                entry.metadata.architecture.lower(),
                entry.metadata.model_type.lower(),
                " ".join(entry.metadata.hf_tags).lower() if entry.metadata.hf_tags else ""
            ])
            
            if query_lower in searchable_text:
                model_info = {
                    "archive_key": archive_key,
                    "name": entry.model_name,
                    "source": entry.metadata.source.value,
                    "format": entry.metadata.format.value,
                    "architecture": entry.metadata.architecture,
                    "size_gb": entry.metadata.size_gb,
                    "hf_model_id": entry.metadata.hf_model_id,
                    "last_accessed": entry.last_accessed.isoformat(),
                    "relevance_score": searchable_text.count(query_lower)  # Simple relevance scoring
                }
                matching_models.append(model_info)
        
        # Sort by relevance and then by last accessed
        matching_models.sort(key=lambda x: (x["relevance_score"], x["last_accessed"]), reverse=True)
        
        return matching_models
    
    def get_archive_stats(self) -> CacheStats:
        """
        Get archive statistics.
        
        Returns:
            CacheStats: Archive statistics
        """
        stats = CacheStats()
        
        # Basic counts
        stats.total_models = len(self.cache_entries)
        stats.total_size_bytes = sum(entry.disk_usage_bytes for entry in self.cache_entries.values())
        
        # Available space
        try:
            cache_disk_usage = shutil.disk_usage(self.cache_dir)
            stats.available_space_bytes = cache_disk_usage.free
        except Exception:
            stats.available_space_bytes = 0
        
        # Breakdown by format
        for entry in self.cache_entries.values():
            format_name = entry.metadata.format.value
            stats.models_by_format[format_name] = stats.models_by_format.get(format_name, 0) + 1
        
        # Breakdown by size category
        for entry in self.cache_entries.values():
            size_name = entry.metadata.size_category.value
            stats.models_by_size[size_name] = stats.models_by_size.get(size_name, 0) + 1
        
        # Most accessed models
        sorted_by_access = sorted(
            self.cache_entries.items(),
            key=lambda x: x[1].access_count,
            reverse=True
        )
        stats.most_accessed_models = [key for key, _ in sorted_by_access[:10]]
        
        # Recently added models
        sorted_by_date = sorted(
            self.cache_entries.items(),
            key=lambda x: x[1].cached_at,
            reverse=True
        )
        stats.recently_added_models = [key for key, _ in sorted_by_date[:10]]
        
        # Health information
        stats.corrupted_models = len([
            entry for entry in self.cache_entries.values()
            if not entry.metadata.is_valid
        ])
        
        stats.incomplete_downloads = len([
            entry for entry in self.cache_entries.values()
            if not entry.is_complete
        ])
        
        return stats
    
    def get_download_progress(self, download_id: str) -> Optional[DownloadProgress]:
        """
        Get download progress for specific download.
        
        Args:
            download_id: Download identifier
            
        Returns:
            DownloadProgress: Progress information or None
        """
        return self.download_progress.get(download_id)
    
    def list_active_downloads(self) -> List[DownloadProgress]:
        """List all active downloads"""
        return [
            progress for progress in self.download_progress.values()
            if progress.status == DownloadStatus.IN_PROGRESS
        ]
    
    def cancel_download(self, download_id: str) -> bool:
        """
        Cancel an active download.
        
        Args:
            download_id: Download to cancel
            
        Returns:
            bool: True if cancellation successful
        """
        progress = self.download_progress.get(download_id)
        if not progress:
            return False
        
        if progress.status != DownloadStatus.IN_PROGRESS:
            return False
        
        progress.status = DownloadStatus.CANCELLED
        progress.end_time = datetime.now()
        
        self.logger.info(f"Download cancelled: {download_id}")
        return True
    
    # ========================================================================
    # NETWORK MONITORING SYSTEM
    # ========================================================================
    
    def _start_network_monitoring(self):
        """Start network monitoring for download resilience"""
        self.network_monitor_thread = threading.Thread(
            target=self._network_monitor_loop,
            name="network-monitor",
            daemon=True
        )
        self.network_monitor_active = True
        self.network_status = True  # Assume online initially
        self.paused_downloads = set()  # Track paused downloads
        
        self.network_monitor_thread.start()
        self.logger.info("Network monitoring started")
    
    def _network_monitor_loop(self):
        """Network monitoring loop with redundant servers"""
        # Redundant ping targets
        ping_targets = [
            "8.8.8.8",      # Google DNS
            "1.1.1.1",      # Cloudflare DNS
            "208.67.222.222" # OpenDNS
        ]
        
        ping_interval = 5  # Check every 5 seconds
        consecutive_failures = 0
        max_failures = 3  # Declare offline after 3 consecutive failures
        
        while self.network_monitor_active:
            try:
                network_available = False
                
                # Test connectivity to redundant servers
                for target in ping_targets:
                    if self._ping_server(target):
                        network_available = True
                        break  # One successful ping is enough
                
                # Handle network state changes
                if network_available and not self.network_status:
                    # Network restored
                    consecutive_failures = 0
                    self.network_status = True
                    self._resume_paused_downloads()
                    self.logger.info("Network connectivity restored")
                    
                elif not network_available:
                    consecutive_failures += 1
                    
                    if consecutive_failures >= max_failures and self.network_status:
                        # Network lost
                        self.network_status = False
                        self._pause_active_downloads()
                        self.logger.warning("Network connectivity lost - downloads paused")
                
                time.sleep(ping_interval)
                
            except Exception as e:
                self.logger.error(f"Network monitoring error: {e}")
                time.sleep(ping_interval)
    
    def _ping_server(self, target: str, timeout: int = 3) -> bool:
        """
        Ping a server to check connectivity.
        
        Args:
            target: Target IP or hostname
            timeout: Ping timeout in seconds
            
        Returns:
            bool: True if ping successful
        """
        try:
            import subprocess
            import platform
            
            # Use appropriate ping command for OS
            if platform.system().lower() == "windows":
                cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), target]
            else:
                cmd = ["ping", "-c", "1", "-W", str(timeout), target]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout + 1
            )
            
            return result.returncode == 0
            
        except Exception:
            return False
    
    def _pause_active_downloads(self):
        """Pause all active downloads due to network issues"""
        active_downloads = self.list_active_downloads()
        
        for progress in active_downloads:
            if progress.download_id not in self.paused_downloads:
                progress.status = DownloadStatus.PENDING  # Mark as paused
                self.paused_downloads.add(progress.download_id)
                self.logger.info(f"Download paused due to network: {progress.download_id}")
    
    def _resume_paused_downloads(self):
        """Resume downloads that were paused due to network issues"""
        if not self.paused_downloads:
            return
        
        for download_id in self.paused_downloads.copy():
            progress = self.download_progress.get(download_id)
            if progress and progress.status == DownloadStatus.PENDING:
                progress.status = DownloadStatus.IN_PROGRESS
                self.paused_downloads.remove(download_id)
                self.logger.info(f"Download resumed: {download_id}")
                
                # Note: Actual download resumption would need to be handled
                # by the specific download method (HuggingFace, URL, etc.)
    
    def _stop_network_monitoring(self):
        """Stop network monitoring"""
        if hasattr(self, 'network_monitor_active'):
            self.network_monitor_active = False
        
        if hasattr(self, 'network_monitor_thread') and self.network_monitor_thread.is_alive():
            self.network_monitor_thread.join(timeout=5)
        
        self.logger.info("Network monitoring stopped")
    
    # ========================================================================
    # CLEANUP AND MAINTENANCE
    # ========================================================================
    
    def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """
        Clean up temporary download files.
        
        Args:
            max_age_hours: Maximum age for temp files
            
        Returns:
            int: Number of files cleaned
        """
        cleaned_count = 0
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        try:
            temp_dirs = [self.temp_dir, self.cache_dir / "downloads"]
            
            for temp_dir in temp_dirs:
                if not temp_dir.exists():
                    continue
                
                for item in temp_dir.iterdir():
                    try:
                        if item.stat().st_mtime < cutoff_time:
                            if item.is_dir():
                                shutil.rmtree(item)
                            else:
                                item.unlink()
                            cleaned_count += 1
                            self.logger.debug(f"Cleaned temp file: {item}")
                    except Exception as e:
                        self.logger.warning(f"Failed to clean {item}: {e}")
            
            self.logger.info(f"Cleaned {cleaned_count} temporary files")
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"Temp file cleanup failed: {e}")
            return 0
    
    def repair_archive_integrity(self) -> Dict[str, Any]:
        """
        Repair archive integrity issues.
        
        Returns:
            dict: Repair results
        """
        repair_results = {
            "repaired_entries": 0,
            "removed_orphans": 0,
            "errors": []
        }
        
        try:
            # Find and remove orphaned cache entries
            orphaned_keys = []
            
            for cache_key, entry in self.cache_entries.items():
                if not Path(entry.cache_path).exists():
                    orphaned_keys.append(cache_key)
            
            for key in orphaned_keys:
                del self.cache_entries[key]
                repair_results["removed_orphans"] += 1
                self.logger.info(f"Removed orphaned cache entry: {key}")
            
            # Update metadata for existing entries
            for cache_key, entry in self.cache_entries.items():
                archive_path = Path(entry.cache_path)
                if archive_path.exists():
                    # Recalculate size and checksum
                    actual_size = self._calculate_directory_size(archive_path)
                    if abs(actual_size - entry.disk_usage_bytes) > (1024 * 1024):  # 1MB difference
                        entry.disk_usage_bytes = actual_size
                        entry.metadata.total_size_bytes = actual_size
                        repair_results["repaired_entries"] += 1
                        self.logger.info(f"Updated size for: {cache_key}")
            
            # Save updated index
            if repair_results["repaired_entries"] > 0 or repair_results["removed_orphans"] > 0:
                self._save_cache_index()
            
            self.logger.info(f"Archive repair completed: {repair_results}")
            
        except Exception as e:
            error_msg = f"Archive repair failed: {e}"
            repair_results["errors"].append(error_msg)
            self.logger.error(error_msg)
        
        return repair_results
    
    def export_archive_manifest(self, output_file: Path) -> bool:
        """
        Export complete archive manifest.
        
        Args:
            output_file: Output file path
            
        Returns:
            bool: True if export successful
        """
        try:
            manifest = {
                "metadata": {
                    "export_time": datetime.now().isoformat(),
                    "framework_version": "1.0.0",
                    "total_models": len(self.cache_entries),
                    "total_size_gb": sum(entry.metadata.size_gb for entry in self.cache_entries.values())
                },
                "archive_entries": []
            }
            
            # Export all archive entries
            for cache_key, entry in self.cache_entries.items():
                entry_data = {
                    "archive_key": cache_key,
                    "model_name": entry.model_name,
                    "source": entry.metadata.source.value,
                    "format": entry.metadata.format.value,
                    "size_gb": entry.metadata.size_gb,
                    "archive_path": entry.cache_path,
                    "archived_at": entry.cached_at.isoformat(),
                    "access_count": entry.access_count,
                    "is_valid": entry.metadata.is_valid,
                    "checksum": entry.checksum
                }
                
                if entry.metadata.hf_model_id:
                    entry_data["hf_model_id"] = entry.metadata.hf_model_id
                
                manifest["archive_entries"].append(entry_data)
            
            # Write manifest
            ensure_directory(output_file.parent)
            with open(output_file, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            self.logger.info(f"Archive manifest exported: {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export archive manifest: {e}")
            return False
    
    def get_disk_usage_report(self) -> Dict[str, Any]:
        """Get detailed disk usage report"""
        report = {
            "cache_directory": str(self.cache_dir),
            "total_archive_size_gb": 0,
            "breakdown": {
                "huggingface": {"count": 0, "size_gb": 0},
                "local": {"count": 0, "size_gb": 0},
                "workflow_artifacts": {"count": 0, "size_gb": 0},
                "temp_files": {"count": 0, "size_gb": 0}
            },
            "largest_models": [],
            "disk_space": {}
        }
        
        try:
            # Calculate breakdown by source
            for entry in self.cache_entries.items():
                cache_key, entry_obj = entry
                size_gb = entry_obj.metadata.size_gb
                report["total_archive_size_gb"] += size_gb
                
                if entry_obj.metadata.source == ModelSource.HUGGINGFACE:
                    report["breakdown"]["huggingface"]["count"] += 1
                    report["breakdown"]["huggingface"]["size_gb"] += size_gb
                elif entry_obj.metadata.source == ModelSource.LOCAL_PATH:
                    if "workflow" in entry_obj.model_name:
                        report["breakdown"]["workflow_artifacts"]["count"] += 1
                        report["breakdown"]["workflow_artifacts"]["size_gb"] += size_gb
                    else:
                        report["breakdown"]["local"]["count"] += 1
                        report["breakdown"]["local"]["size_gb"] += size_gb
            
            # Find largest models
            sorted_models = sorted(
                self.cache_entries.items(),
                key=lambda x: x[1].metadata.size_gb,
                reverse=True
            )
            
            report["largest_models"] = [
                {
                    "archive_key": key,
                    "name": entry.model_name,
                    "size_gb": entry.metadata.size_gb
                }
                for key, entry in sorted_models[:10]
            ]
            
            # Get disk space information
            try:
                disk_usage = shutil.disk_usage(self.cache_dir)
                report["disk_space"] = {
                    "total_gb": disk_usage.total / (1024**3),
                    "used_gb": (disk_usage.total - disk_usage.free) / (1024**3),
                    "free_gb": disk_usage.free / (1024**3),
                    "archive_percentage": (report["total_archive_size_gb"] / (disk_usage.total / (1024**3))) * 100
                }
            except Exception:
                report["disk_space"] = {"error": "Could not determine disk space"}
            
        except Exception as e:
            report["error"] = str(e)
        
        return report
    
    def shutdown(self):
        """Shutdown model manager and cleanup resources"""
        self.logger.info("Shutting down Model Manager...")
        
        try:
            # Stop network monitoring
            self._stop_network_monitoring()
            
            # Cancel active downloads
            for download_id in list(self.download_progress.keys()):
                self.cancel_download(download_id)
            
            # Save final cache index
            self._save_cache_index()
            
            # Cleanup temp files
            self.cleanup_temp_files(max_age_hours=0)  # Clean all temp files
            
            self.logger.info("Model Manager shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during Model Manager shutdown: {e}")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_model_manager(framework_manager) -> ModelManager:
    """
    Create and initialize model manager.
    
    Args:
        framework_manager: Framework manager instance
        
    Returns:
        ModelManager: Initialized model manager
    """
    model_manager = ModelManager(framework_manager)
    
    if not model_manager.initialize():
        raise ModelManagerError("Failed to initialize model manager")
    
    # Start network monitoring for downloads
    model_manager._start_network_monitoring()
    
    return model_manager


def validate_model_requirements() -> Dict[str, Any]:
    """
    Validate system requirements for model management.
    
    Returns:
        dict: Validation results
    """
    requirements = {
        "transformers": False,
        "safetensors": False,
        "huggingface_hub": False,
        "network_connectivity": False,
        "disk_space_gb": 0,
        "errors": [],
        "warnings": []
    }
    
    # Check required libraries
    required_libs = ["transformers", "safetensors", "huggingface_hub"]
    
    for lib in required_libs:
        try:
            __import__(lib)
            requirements[lib] = True
        except ImportError:
            requirements["errors"].append(f"Required library not available: {lib}")
    
    # Check network connectivity
    try:
        import requests
        response = requests.get("https://huggingface.co", timeout=5)
        if response.status_code == 200:
            requirements["network_connectivity"] = True
        else:
            requirements["warnings"].append("HuggingFace not accessible")
    except Exception:
        requirements["warnings"].append("Network connectivity issues detected")
    
    # Check disk space
    try:
        import shutil
        disk_usage = shutil.disk_usage(".")
        requirements["disk_space_gb"] = disk_usage.free / (1024**3)
        
        if requirements["disk_space_gb"] < 10:
            requirements["warnings"].append("Low disk space - less than 10GB available")
    except Exception:
        requirements["warnings"].append("Could not determine disk space")
    
    return requirements


def estimate_download_time(model_size_gb: float, connection_speed_mbps: float = 50) -> Dict[str, int]:
    """
    Estimate download time for model.
    
    Args:
        model_size_gb: Model size in GB
        connection_speed_mbps: Connection speed in Mbps
        
    Returns:
        dict: Time estimates
    """
    # Convert GB to bits
    model_size_bits = model_size_gb * 8 * (1024**3)
    
    # Convert Mbps to bits per second
    speed_bps = connection_speed_mbps * (1024**2)
    
    # Calculate time in seconds
    download_time_seconds = int(model_size_bits / speed_bps)
    
    return {
        "seconds": download_time_seconds,
        "minutes": download_time_seconds // 60,
        "hours": download_time_seconds // 3600,
        "estimated_for_speeds": {
            "10_mbps": int(model_size_bits / (10 * 1024**2)),
            "50_mbps": int(model_size_bits / (50 * 1024**2)),
            "100_mbps": int(model_size_bits / (100 * 1024**2))
        }
    }


# ============================================================================
# EXCEPTION CLASSES
# ============================================================================

class ModelManagerError(Exception):
    """Base exception for model manager errors"""
    pass


class ModelNotFoundError(ModelManagerError):
    """Exception raised when model is not found"""
    pass


class DownloadError(ModelManagerError):
    """Exception raised for download-related errors"""
    pass


class ArchiveError(ModelManagerError):
    """Exception raised for archive-related errors"""
    pass


class ValidationError(ModelManagerError):
    """Exception raised for model validation errors"""
    pass


# ============================================================================
# CONSTANTS
# ============================================================================

# Default configuration values
DEFAULT_MAX_CACHE_SIZE_GB = 100
DEFAULT_CHUNK_SIZE = 8192
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_CONCURRENT_DOWNLOADS = 2

# Model size thresholds (in GB)
MODEL_SIZE_THRESHOLDS = {
    ModelSize.TINY: (0, 1),
    ModelSize.SMALL: (1, 3),
    ModelSize.MEDIUM: (3, 7),
    ModelSize.LARGE: (7, 15),
    ModelSize.XLARGE: (15, 30),
    ModelSize.XXLARGE: (30, float('inf'))
}

# Network monitoring configuration
NETWORK_PING_TARGETS = [
    "8.8.8.8",        # Google DNS
    "1.1.1.1",        # Cloudflare DNS  
    "208.67.222.222"  # OpenDNS
]

NETWORK_PING_INTERVAL = 5  # seconds
NETWORK_MAX_FAILURES = 3   # consecutive failures before declaring offline
