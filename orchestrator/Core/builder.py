#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Build Engine
DIREKTIVE: Goldstandard, Universal & Data-Driven.

Der Builder ist jetzt vollständig agnostisch. Er kennt keine spezifischen Hardware-Targets.
Er liest die Konfiguration aus `targets/<name>/target.yml` und nutzt das dortige Dockerfile.
"""

import os
import sys
import json
import logging
import subprocess
import threading
import time
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
import asyncio

import yaml
import docker
from docker.models.containers import Container
from docker.models.images import Image
from packaging import version

from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory

# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class BuildStatus(Enum):
    """Build status enumeration"""
    QUEUED = "queued"
    PREPARING = "preparing"
    BUILDING = "building"
    CONVERTING = "converting"
    OPTIMIZING = "optimizing"
    PACKAGING = "packaging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CLEANING = "cleaning"

# WICHTIG: TargetArch Enum wurde entfernt! 
# Wir nutzen jetzt Strings, um beliebige Targets aus dem Ordner 'targets/' zu unterstützen.

class ModelFormat(Enum):
    """Supported model formats"""
    HUGGINGFACE = "hf"
    GGUF = "gguf"
    ONNX = "onnx"
    TENSORFLOW_LITE = "tflite"
    PYTORCH_MOBILE = "pytorch_mobile"

class OptimizationLevel(Enum):
    """Optimization levels for model conversion"""
    FAST = "fast"
    BALANCED = "balanced"
    SIZE = "size"
    SPEED = "speed"
    AGGRESSIVE = "aggressive"

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class BuildConfiguration:
    """Complete build configuration"""
    build_id: str
    timestamp: str
    model_source: str
    target_arch: str # Changed from Enum to str for flexibility
    target_format: ModelFormat
    output_dir: str
    model_branch: Optional[str] = "main"
    source_format: ModelFormat = ModelFormat.HUGGINGFACE
    target_board: Optional[str] = None
    optimization_level: OptimizationLevel = OptimizationLevel.BALANCED
    quantization: Optional[str] = None
    max_context_length: Optional[int] = None
    custom_flags: List[str] = field(default_factory=list)
    output_name: Optional[str] = None
    include_metadata: bool = True
    # Docker settings can now be overridden by target.yml
    base_image: str = "debian:bookworm-slim" 
    build_args: Dict[str, str] = field(default_factory=dict)
    parallel_jobs: int = 4
    build_timeout: int = 3600
    cleanup_after_build: bool = True
    enable_hadolint: bool = True
    poetry_version: str = "latest"

@dataclass
class BuildProgress:
    """Build progress tracking"""
    build_id: str
    status: BuildStatus
    current_stage: str
    progress_percent: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    
    def add_log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{timestamp}] [{level}] {message}")
    
    def add_error(self, error: str):
        self.errors.append(error)
        self.add_log(f"ERROR: {error}", "ERROR")
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)
        self.add_log(f"WARNING: {warning}", "WARNING")

# ============================================================================
# BUILD ENGINE CORE CLASS
# ============================================================================

class BuildEngine:
    """Container-native Build Engine for LLM Cross-Compilation."""
    
    def __init__(self, framework_manager, max_concurrent_builds: int = 2, default_timeout: int = 3600):
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        self.max_concurrent_builds = max_concurrent_builds
        self.default_timeout = default_timeout
        
        self.docker_client = framework_manager.get_component("docker_client")
        if not self.docker_client:
            raise RuntimeError("Docker client not available")
        
        self._lock = threading.Lock()
        self._builds: Dict[str, BuildProgress] = {}
        self._active_containers: Dict[str, Container] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_builds)
        
        self.base_dir = Path(framework_manager.info.installation_path)
        self.targets_dir = self.base_dir / framework_manager.config.targets_dir
        self.models_dir = self.base_dir / framework_manager.config.models_dir
        self.output_dir = self.base_dir / framework_manager.config.output_dir
        self.cache_dir = self.base_dir / framework_manager.config.cache_dir
        
        self._ensure_directories()
        self._validate_docker_environment()
        self.logger.info(f"Build Engine initialized (max: {max_concurrent_builds})")
    
    def _ensure_directories(self):
        dirs = [self.targets_dir, self.models_dir, self.output_dir, self.cache_dir, 
                self.cache_dir / "docker", self.cache_dir / "models", self.cache_dir / "tools"]
        for d in dirs: ensure_directory(d)
    
    def _validate_docker_environment(self):
        try:
            self.docker_client.ping()
            try:
                subprocess.run(["docker", "buildx", "version"], capture_output=True, check=True) # nosec B603
            except:
                self.logger.warning("Docker BuildX not available")
        except Exception as e:
            raise RuntimeError(f"Docker environment failed: {e}")

    def list_available_targets(self) -> List[Dict[str, Any]]:
        """
        Scan 'targets/' directory and return available targets dynamically.
        Replaces the hardcoded Enum logic.
        """
        targets = []
        if not self.targets_dir.exists():
            return targets

        for target_path in self.targets_dir.iterdir():
            if target_path.is_dir() and not target_path.name.startswith("_"):
                # Check if valid module
                if (target_path / "Dockerfile").exists() and (target_path / "target.yml").exists():
                    # Load metadata
                    try:
                        with open(target_path / "target.yml", "r") as f:
                            meta = yaml.safe_load(f)
                            targets.append({
                                "id": target_path.name,
                                "name": meta.get("metadata", {}).get("name", target_path.name),
                                "description": meta.get("metadata", {}).get("description", ""),
                                "path": str(target_path)
                            })
                    except:
                        # Fallback if YAML invalid
                        targets.append({"id": target_path.name, "name": target_path.name, "path": str(target_path)})
        return targets

    def build_model(self, config: BuildConfiguration) -> str:
        self._validate_build_config(config)
        
        active = len([b for b in self._builds.values() if b.status not in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]])
        if active >= self.max_concurrent_builds:
            raise RuntimeError("Max concurrent builds reached")
        
        progress = BuildProgress(config.build_id, BuildStatus.QUEUED, "Initializing", start_time=datetime.now())
        with self._lock: self._builds[config.build_id] = progress
        
        self._executor.submit(self._execute_build, config)
        self.logger.info(f"Build started: {config.build_id}")
        return config.build_id
    
    def get_build_status(self, build_id: str) -> Optional[BuildProgress]:
        return self._builds.get(build_id)
    
    def list_builds(self) -> List[BuildProgress]:
        with self._lock: return list(self._builds.values())
    
    def cancel_build(self, build_id: str) -> bool:
        progress = self._builds.get(build_id)
        if not progress or progress.status in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]:
            return False
        progress.status = BuildStatus.CANCELLED
        container = self._active_containers.get(build_id)
        if container:
            try: container.stop(timeout=10)
            except: pass
        return True

    def cleanup_build(self, build_id: str) -> bool:
        progress = self._builds.get(build_id)
        if not progress: return False
        try:
            progress.status = BuildStatus.CLEANING
            container = self._active_containers.get(build_id)
            if container:
                try: 
                    container.remove(force=True)
                    del self._active_containers[build_id]
                except: pass
            build_temp = self.cache_dir / "builds" / build_id
            if build_temp.exists(): shutil.rmtree(build_temp)
            return True
        except: return False
    
    def _execute_build(self, config: BuildConfiguration):
        bid = config.build_id
        prog = self._builds[bid]
        try:
            prog.status = BuildStatus.PREPARING
            
            # 1. Prepare paths and config
            target_path = self.targets_dir / config.target_arch
            if not target_path.exists():
                raise FileNotFoundError(f"Target '{config.target_arch}' not found in {self.targets_dir}")

            self._prepare_build_environment(config, prog)
            
            # 2. Build Image (Using the Dockerfile from the target folder!)
            # No more python string generation.
            image = self._build_docker_image(config, prog, target_path)
            
            # 3. Run Pipeline
            self._execute_build_modules(config, prog, image)
            self._extract_artifacts(config, prog)
            
            if config.cleanup_after_build: self.cleanup_build(bid)
            
            prog.status = BuildStatus.COMPLETED
            prog.end_time = datetime.now()
            prog.progress_percent = 100
        except Exception as e:
            prog.status = BuildStatus.FAILED
            prog.end_time = datetime.now()
            prog.add_error(str(e))
            self.logger.error(f"Build failed: {e}")
            try: self.cleanup_build(bid)
            except: pass

    def _validate_build_config(self, config: BuildConfiguration):
        if not config.build_id or not config.model_source or not config.output_dir:
            raise ValidationError("Missing required build config")

    def _prepare_build_environment(self, config: BuildConfiguration, progress: BuildProgress):
        progress.current_stage = "Preparing env"
        progress.progress_percent = 10
        
        # Workspace for this specific build run
        build_temp = self.cache_dir / "builds" / config.build_id
        ensure_directory(build_temp)
        
        # Only creating output/log dirs here. Code is in container or target dir.
        for d in ["output", "logs"]: ensure_directory(build_temp / d)
        
        # We don't copy modules anymore, we map them directly from the target folder
        # This ensures we use the latest version on disk.

    def _build_docker_image(self, config: BuildConfiguration, progress: BuildProgress, target_path: Path) -> Image:
        """
        Builds the Docker image defined by the target's own Dockerfile.
        """
        progress.current_stage = f"Building Image ({config.target_arch})"
        progress.progress_percent = 30
        
        dockerfile = target_path / "Dockerfile"
        if not dockerfile.exists():
            # Fallback: Check lowercase
            dockerfile = target_path / "dockerfile"
            if not dockerfile.exists():
                raise FileNotFoundError(f"No Dockerfile found in {target_path}")

        # Tag includes target name to avoid collisions
        tag = f"llm-framework/{config.target_arch}:{config.build_id}"
        
        # Context is Framework Root (so we can COPY entrypoint.sh etc.)
        context_path = self.base_dir
        
        try:
            # We pass the target's Dockerfile relative path to build command
            rel_dockerfile = dockerfile.relative_to(context_path)
            
            cmd = ["docker", "build", "-f", str(rel_dockerfile), "-t", tag, str(context_path)]
            
            # Add build args from config
            for k, v in config.build_args.items():
                cmd.extend(["--build-arg", f"{k}={v}"])
            
            progress.add_log(f"Executing Docker Build: {' '.join(cmd)}")
            
            # Run Build
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(context_path)
            )
            
            for line in process.stdout:
                progress.add_log(f"BUILD: {line.rstrip()}")
            
            process.wait()
            
            if process.returncode != 0:
                raise RuntimeError("Docker build failed")
            
            return self.docker_client.images.get(tag)
            
        except Exception as e:
            raise RuntimeError(f"Image build failed: {e}")

    def _execute_build_modules(self, config, progress, image):
        progress.current_stage = "Running Pipeline"
        progress.progress_percent = 60
        
        build_temp = self.cache_dir / "builds" / config.build_id
        target_path = self.targets_dir / config.target_arch
        
        # Volumes
        vols = {
            # Output & Cache
            str(build_temp / "output"): {"bind": "/build-cache/output", "mode": "rw"},
            str(self.cache_dir / "models"): {"bind": "/build-cache/models", "mode": "rw"},
            # IMPORTANT: Map the target's modules into the container
            str(target_path / "modules"): {"bind": "/app/modules", "mode": "ro"}
        }
        
        # Environment Variables (The "API" for the scripts)
        env = {
            "BUILD_ID": config.build_id,
            "MODEL_SOURCE": config.model_source,
            "TARGET_ARCH": config.target_arch,
            "OPTIMIZATION_LEVEL": config.optimization_level.value,
            "QUANTIZATION": config.quantization or "",
            "LLAMA_CPP_COMMIT": config.build_args.get("LLAMA_CPP_COMMIT", "b3626") # Pass args as env too
        }
        
        # Inject Sources from ConfigManager (Securely)
        if hasattr(self.framework_manager.config, 'source_repositories'):
            for k, v in self.framework_manager.config.source_repositories.items():
                key_clean = k.split('.')[-1].upper() if '.' in k else k.upper()
                # Handle dict vs string sources
                url = v['url'] if isinstance(v, dict) else v
                env[f"{key_clean}_REPO_OVERRIDE"] = url
                if isinstance(v, dict) and 'commit' in v:
                    env[f"{key_clean}_COMMIT"] = v['commit']

        try:
            # Use pipeline mode of entrypoint
            cmd_args = ["pipeline", "/build-cache/models", config.model_source, config.quantization or "Q4_K_M"]
            
            container = self.docker_client.containers.create(
                image=image.id,
                command=cmd_args, 
                volumes=vols, 
                environment=env, 
                name=f"llm-build-{config.build_id}",
                # Security: Drop root, run as user (defined in Dockerfile)
                user="llmbuilder" 
            )
            
            with self._lock: self._active_containers[config.build_id] = container
            
            container.start()
            
            # Stream logs
            for line in container.logs(stream=True, follow=True):
                progress.add_log(f"CONT: {line.decode().strip()}")
                
            res = container.wait(timeout=config.build_timeout)
            if res['StatusCode'] != 0:
                raise RuntimeError(f"Container pipeline failed (Exit Code: {res['StatusCode']})")

        except Exception as e:
            raise RuntimeError(f"Pipeline execution failed: {e}")

    def _extract_artifacts(self, config, progress):
        progress.current_stage = "Extracting"
        progress.progress_percent = 90
        src = self.cache_dir / "builds" / config.build_id / "output" / "packages"
        dst = Path(config.output_dir)
        
        if src.exists():
            count = 0
            for f in src.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(src)
                    target = dst / rel
                    ensure_directory(target.parent)
                    shutil.copy2(f, target)
                    progress.artifacts.append(str(target))
                    count += 1
            progress.add_log(f"Extracted {count} artifacts to {dst}")
        else:
            progress.add_warning("No packages found in output directory")
