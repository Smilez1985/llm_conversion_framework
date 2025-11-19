#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Build Engine
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Container-native Build-Engine für Cross-Compilation von AI-Modellen.
Multi-Stage Docker Builds mit BuildX, Hadolint-konform, Poetry-basiert.
Keine VENV - Docker Container = Isolation.

4-Module-Architektur:
- source_module.sh: llama.cpp clone/build  
- config_module.sh: Hardware-Detection + CMake-Toolchain
- convert_module.sh: HF→GGUF Conversion
- target_module.sh: Quantize + Package
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
from orchestrator.utils.helpers import ensure_directory, check_command_exists, safe_json_load


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


class TargetArch(Enum):
    """Supported target architectures"""
    ARM64 = "arm64"
    ARMV7 = "armv7"
    X86_64 = "x86_64"
    RK3566 = "rk3566"  # MVP Target
    RK3588 = "rk3588"
    RASPBERRY_PI = "raspberry_pi"


class ModelFormat(Enum):
    """Supported model formats"""
    HUGGINGFACE = "hf"
    GGUF = "gguf"
    ONNX = "onnx"
    TENSORFLOW_LITE = "tflite"
    PYTORCH_MOBILE = "pytorch_mobile"


class OptimizationLevel(Enum):
    """Optimization levels for model conversion"""
    FAST = "fast"        # Quick build, minimal optimization
    BALANCED = "balanced"  # Good balance of speed and optimization
    SIZE = "size"        # Optimize for smallest size
    SPEED = "speed"      # Optimize for fastest inference
    AGGRESSIVE = "aggressive"  # Maximum optimization


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class BuildConfiguration:
    """Complete build configuration for a model conversion"""
    # Build identification
    build_id: str
    timestamp: str
    
    # Source configuration
    model_source: str  # HuggingFace model name or local path
    model_branch: Optional[str] = "main"
    source_format: ModelFormat = ModelFormat.HUGGINGFACE
    
    # Target configuration
    target_arch: TargetArch
    target_format: ModelFormat
    target_board: Optional[str] = None  # Specific board variant
    
    # Build parameters
    optimization_level: OptimizationLevel = OptimizationLevel.BALANCED
    quantization: Optional[str] = None  # q4_0, q8_0, etc.
    max_context_length: Optional[int] = None
    custom_flags: List[str] = field(default_factory=list)
    
    # Output configuration
    output_dir: str
    output_name: Optional[str] = None
    include_metadata: bool = True
    
    # Docker configuration
    base_image: str = "debian:bookworm-slim"
    build_args: Dict[str, str] = field(default_factory=dict)
    dockerfile_template: Optional[str] = None
    
    # Advanced options
    parallel_jobs: int = 4
    build_timeout: int = 3600  # 1 hour default
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
        """Add log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.logs.append(log_entry)
    
    def add_error(self, error: str):
        """Add error and log entry"""
        self.errors.append(error)
        self.add_log(f"ERROR: {error}", "ERROR")
    
    def add_warning(self, warning: str):
        """Add warning and log entry"""
        self.warnings.append(warning)
        self.add_log(f"WARNING: {warning}", "WARNING")


@dataclass
class ModuleResult:
    """Result from a build module execution"""
    module_name: str
    success: bool
    execution_time: float
    output: str
    error_output: str
    artifacts: List[str] = field(default_factory=list)
    exit_code: int = 0


@dataclass
class BuildEnvironment:
    """Build environment configuration"""
    container_id: Optional[str] = None
    work_dir: str = "/workspace"
    modules_dir: str = "/workspace/modules"
    models_cache_dir: str = "/workspace/cache/models"
    tools_cache_dir: str = "/workspace/cache/tools"
    output_mount_dir: str = "/workspace/output"
    
    # Environment variables
    env_vars: Dict[str, str] = field(default_factory=dict)
    
    # Volume mounts
    volume_mounts: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set default environment variables"""
        if not self.env_vars:
            self.env_vars = {
                "DEBIAN_FRONTEND": "noninteractive",
                "PYTHONUNBUFFERED": "1",
                "POETRY_VENV_IN_PROJECT": "true",  # No VENV in container
                "POETRY_CACHE_DIR": "/workspace/cache/poetry",
                "HF_HOME": "/workspace/cache/huggingface",
                "TRANSFORMERS_CACHE": "/workspace/cache/transformers"
            }


# ============================================================================
# BUILD ENGINE CORE CLASS
# ============================================================================

class BuildEngine:
    """
    Container-native Build Engine for LLM Cross-Compilation.
    
    Orchestrates Docker-based builds using Multi-Stage Dockerfiles with:
    - BuildX multi-architecture support
    - Hadolint-compliant Dockerfile generation
    - Poetry dependency management (no VENV)
    - 4-Module build pipeline
    
    Responsibilities:
    - Build configuration validation
    - Docker container orchestration
    - Module execution coordination
    - Progress tracking and logging
    - Error handling and recovery
    - Artifact management
    """
    
    def __init__(self, 
                 framework_manager,
                 max_concurrent_builds: int = 2,
                 default_timeout: int = 3600):
        """
        Initialize the Build Engine.
        
        Args:
            framework_manager: Reference to FrameworkManager
            max_concurrent_builds: Maximum concurrent builds
            default_timeout: Default build timeout in seconds
        """
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        
        # Configuration
        self.max_concurrent_builds = max_concurrent_builds
        self.default_timeout = default_timeout
        
        # Docker client
        self.docker_client = framework_manager.get_component("docker_client")
        if not self.docker_client:
            raise RuntimeError("Docker client not available")
        
        # State management
        self._lock = threading.Lock()
        self._builds: Dict[str, BuildProgress] = {}
        self._active_containers: Dict[str, Container] = {}
        self._build_queue = asyncio.Queue()
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_builds)
        
        # Paths
        self.base_dir = Path(framework_manager.info.installation_path)
        self.targets_dir = self.base_dir / framework_manager.config.targets_dir
        self.models_dir = self.base_dir / framework_manager.config.models_dir
        self.output_dir = self.base_dir / framework_manager.config.output_dir
        self.cache_dir = self.base_dir / framework_manager.config.cache_dir
        
        # Ensure required directories exist
        self._ensure_directories()
        
        # Validate Docker environment
        self._validate_docker_environment()
        
        self.logger.info(f"Build Engine initialized (max_concurrent: {max_concurrent_builds})")
    
    def _ensure_directories(self):
        """Ensure all required directories exist"""
        required_dirs = [
            self.targets_dir,
            self.models_dir, 
            self.output_dir,
            self.cache_dir,
            self.cache_dir / "docker",
            self.cache_dir / "models",
            self.cache_dir / "tools"
        ]
        
        for directory in required_dirs:
            ensure_directory(directory)
            self.logger.debug(f"Directory ensured: {directory}")
    
    def _validate_docker_environment(self):
        """Validate Docker environment and capabilities"""
        try:
            # Test Docker availability
            self.docker_client.ping()
            
            # Check Docker version
            docker_version = self.docker_client.version()
            self.logger.info(f"Docker version: {docker_version.get('Version', 'unknown')}")
            
            # Check BuildX availability
            try:
                result = subprocess.run(
                    ["docker", "buildx", "version"], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                self.logger.info("Docker BuildX available")
            except subprocess.CalledProcessError:
                self.logger.warning("Docker BuildX not available - multi-arch builds disabled")
            
            # Check available platforms
            try:
                result = subprocess.run(
                    ["docker", "buildx", "ls"], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                self.logger.debug(f"BuildX platforms: {result.stdout}")
            except subprocess.CalledProcessError:
                pass
            
        except Exception as e:
            raise RuntimeError(f"Docker environment validation failed: {e}")

    def build_model(self, config: BuildConfiguration) -> str:
        """Start a new model build"""
        # Validate configuration
        self._validate_build_config(config)
        
        # Check concurrent build limit
        active_count = len([b for b in self._builds.values() 
                           if b.status not in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]])
        
        if active_count >= self.max_concurrent_builds:
            raise RuntimeError(f"Maximum concurrent builds ({self.max_concurrent_builds}) reached")
        
        # Initialize build tracking
        progress = BuildProgress(
            build_id=config.build_id,
            status=BuildStatus.QUEUED,
            current_stage="Initializing",
            start_time=datetime.now()
        )
        
        with self._lock:
            self._builds[config.build_id] = progress
        
        # Submit build to executor
        future = self._executor.submit(self._execute_build, config)
        
        self.logger.info(f"Build started: {config.build_id}")
        progress.add_log(f"Build queued for execution")
        
        return config.build_id
    
    def get_build_status(self, build_id: str) -> Optional[BuildProgress]:
        return self._builds.get(build_id)
    
    def list_builds(self) -> List[BuildProgress]:
        with self._lock:
            return list(self._builds.values())
    
    def cancel_build(self, build_id: str) -> bool:
        progress = self._builds.get(build_id)
        if not progress: return False
        
        if progress.status in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]:
            return False
        
        progress.status = BuildStatus.CANCELLED
        progress.add_log("Build cancellation requested")
        
        container = self._active_containers.get(build_id)
        if container:
            try:
                container.stop(timeout=10)
                progress.add_log("Container stopped")
            except Exception as e:
                progress.add_error(f"Failed to stop container: {e}")
        
        self.logger.info(f"Build cancelled: {build_id}")
        return True
    
    def cleanup_build(self, build_id: str) -> bool:
        progress = self._builds.get(build_id)
        if not progress: return False
        
        try:
            progress.status = BuildStatus.CLEANING
            progress.add_log("Starting cleanup")
            
            container = self._active_containers.get(build_id)
            if container:
                try:
                    container.remove(force=True)
                    del self._active_containers[build_id]
                    progress.add_log("Container removed")
                except Exception as e:
                    progress.add_warning(f"Container cleanup failed: {e}")
            
            build_temp_dir = self.cache_dir / "builds" / build_id
            if build_temp_dir.exists():
                shutil.rmtree(build_temp_dir)
                progress.add_log("Temporary files removed")
            
            progress.add_log("Cleanup completed")
            return True
            
        except Exception as e:
            progress.add_error(f"Cleanup failed: {e}")
            return False
    
    def _execute_build(self, config: BuildConfiguration):
        build_id = config.build_id
        progress = self._builds[build_id]
        
        try:
            progress.status = BuildStatus.PREPARING
            progress.current_stage = "Preparing build environment"
            progress.add_log("Starting build execution")
            
            self._prepare_build_environment(config, progress)
            dockerfile_path = self._generate_dockerfile(config, progress)
            image = self._build_docker_image(config, progress, dockerfile_path)
            self._execute_build_modules(config, progress, image)
            self._extract_artifacts(config, progress)
            
            if config.cleanup_after_build:
                self.cleanup_build(build_id)
            
            progress.status = BuildStatus.COMPLETED
            progress.end_time = datetime.now()
            progress.progress_percent = 100
            progress.add_log("Build completed successfully")
            self.logger.info(f"Build completed: {build_id}")
            
        except Exception as e:
            progress.status = BuildStatus.FAILED
            progress.end_time = datetime.now()
            progress.add_error(f"Build failed: {str(e)}")
            self.logger.error(f"Build failed: {build_id} - {e}")
            try:
                self.cleanup_build(build_id)
            except: pass
    
    def _validate_build_config(self, config: BuildConfiguration):
        errors = []
        if not config.build_id: errors.append("build_id is required")
        if not config.model_source: errors.append("model_source is required")
        if not config.target_arch: errors.append("target_arch is required")
        if not config.target_format: errors.append("target_format is required")
        if not config.output_dir: errors.append("output_dir is required")
        
        try:
            output_path = Path(config.output_dir)
            if not output_path.parent.exists():
                errors.append(f"Output directory parent does not exist: {output_path.parent}")
        except Exception as e:
            errors.append(f"Invalid output_dir: {e}")
        
        if config.target_arch == TargetArch.RK3566:
            target_dir = self.targets_dir / "rk3566"
            if not target_dir.exists():
                errors.append("RK3566 target not found - missing target configuration")
        
        if config.source_format == ModelFormat.HUGGINGFACE and config.target_format == ModelFormat.HUGGINGFACE:
            errors.append("Source and target format cannot both be HuggingFace")
        
        if config.quantization and config.target_format != ModelFormat.GGUF:
            errors.append("Quantization is only supported for GGUF target format")
        
        if errors:
            raise ValidationError(f"Build configuration validation failed: {'; '.join(errors)}")
        
        self.logger.debug(f"Build configuration validated: {config.build_id}")
    
    def _prepare_build_environment(self, config: BuildConfiguration, progress: BuildProgress):
        progress.current_stage = "Preparing build environment"
        progress.progress_percent = 10
        
        build_temp_dir = self.cache_dir / "builds" / config.build_id
        ensure_directory(build_temp_dir)
        
        subdirs = ["workspace", "modules", "output", "cache", "logs"]
        for subdir in subdirs:
            ensure_directory(build_temp_dir / subdir)
        
        target_dir = self.targets_dir / config.target_arch.value
        if not target_dir.exists():
            raise RuntimeError(f"Target directory not found: {target_dir}")
        
        modules_src = target_dir / "modules"
        modules_dst = build_temp_dir / "modules"
        
        if modules_src.exists():
            for module_file in modules_src.glob("*.sh"):
                dst_file = modules_dst / module_file.name
                shutil.copy2(module_file, dst_file)
                os.chmod(dst_file, 0o755)
                progress.add_log(f"Module copied: {module_file.name}")
        
        target_config_src = target_dir / "target.yml"
        if target_config_src.exists():
            shutil.copy2(target_config_src, build_temp_dir / "target.yml")
        
        build_config_data = {
            "build_id": config.build_id,
            "model_source": config.model_source,
            "model_branch": config.model_branch,
            "target_arch": config.target_arch.value,
            "target_format": config.target_format.value,
            "optimization_level": config.optimization_level.value,
            "quantization": config.quantization,
            "parallel_jobs": config.parallel_jobs,
            "output_name": config.output_name or f"model_{config.build_id}"
        }
        
        config_file = build_temp_dir / "build_config.json"
        with open(config_file, 'w') as f:
            json.dump(build_config_data, f, indent=2)
        
        progress.add_log("Build environment prepared")
    
    def _generate_dockerfile(self, config: BuildConfiguration, progress: BuildProgress) -> Path:
        progress.current_stage = "Generating Dockerfile"
        progress.progress_percent = 20
        
        build_temp_dir = self.cache_dir / "builds" / config.build_id
        dockerfile_path = build_temp_dir / "Dockerfile"
        
        target_config_path = build_temp_dir / "target.yml"
        target_config = {}
        if target_config_path.exists():
            with open(target_config_path, 'r') as f:
                target_config = yaml.safe_load(f)
        
        dockerfile_content = self._generate_dockerfile_content(config, target_config)
        
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        if config.enable_hadolint:
            self._validate_dockerfile_hadolint(dockerfile_path, progress)
        
        progress.add_log("Dockerfile generated")
        return dockerfile_path
    
    def _generate_dockerfile_content(self, config: BuildConfiguration, target_config: Dict) -> str:
        arch_mapping = {
            TargetArch.ARM64: "linux/arm64",
            TargetArch.ARMV7: "linux/arm/v7", 
            TargetArch.X86_64: "linux/amd64",
            TargetArch.RK3566: "linux/arm64",
            TargetArch.RK3588: "linux/arm64"
        }
        
        platform = arch_mapping.get(config.target_arch, "linux/amd64")
        
        dockerfile_lines = [
            "# hadolint ignore=DL3007",
            f"FROM --platform={platform} {config.base_image} AS builder",
            "RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake git curl wget python3 python3-pip python3-dev pkg-config && apt-get clean && rm -rf /var/lib/apt/lists/*",
            "ENV POETRY_VERSION=" + (config.poetry_version if config.poetry_version != "latest" else "1.7.1"),
            "ENV POETRY_HOME=/opt/poetry",
            "ENV POETRY_CACHE_DIR=/workspace/cache/poetry",
            "ENV POETRY_VENV_IN_PROJECT=true",
            "RUN curl -sSL https://install.python-poetry.org | python3 - && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry",
            "FROM builder AS dependencies",
            "WORKDIR /workspace",
            "COPY pyproject.toml poetry.lock* ./",
            "RUN poetry config virtualenvs.create false && poetry install --no-dev --no-interaction --no-ansi",
        ]
        
        if config.target_arch == TargetArch.RK3566:
            dockerfile_lines.extend([
                "RUN apt-get update && apt-get install -y --no-install-recommends gcc-aarch64-linux-gnu g++-aarch64-linux-gnu crossbuild-essential-arm64 && apt-get clean && rm -rf /var/lib/apt/lists/*",
                "ENV CC=aarch64-linux-gnu-gcc",
                "ENV CXX=aarch64-linux-gnu-g++", 
                "ENV AR=aarch64-linux-gnu-ar",
                "ENV STRIP=aarch64-linux-gnu-strip",
                "ENV CMAKE_TOOLCHAIN_FILE=/workspace/cmake/rk3566-toolchain.cmake",
            ])
        
        dockerfile_lines.extend([
            "FROM dependencies AS build-tools",
            "RUN mkdir -p /workspace/modules /workspace/cache /workspace/output /workspace/cmake",
            "COPY modules/ /workspace/modules/",
            "RUN chmod +x /workspace/modules/*.sh",
            "COPY build_config.json target.yml* /workspace/",
            "ENV DEBIAN_FRONTEND=noninteractive",
            "ENV PYTHONUNBUFFERED=1",
            "ENV HF_HOME=/workspace/cache/huggingface",
            "ENV TRANSFORMERS_CACHE=/workspace/cache/transformers",
            f"ENV BUILD_JOBS={config.parallel_jobs}",
            f"ENV OPTIMIZATION_LEVEL={config.optimization_level.value}",
        ])
        
        for key, value in config.build_args.items():
            dockerfile_lines.append(f"ENV {key}={value}")
        
        dockerfile_lines.extend([
            "FROM build-tools AS build-execution",
            "WORKDIR /workspace",
            "RUN echo 'Executing source_module.sh...' && /workspace/modules/source_module.sh",
            "RUN echo 'Executing config_module.sh...' && /workspace/modules/config_module.sh",
            "RUN echo 'Executing convert_module.sh...' && /workspace/modules/convert_module.sh",
            "RUN echo 'Executing target_module.sh...' && /workspace/modules/target_module.sh",
            "FROM scratch AS output",
            "COPY --from=build-execution /workspace/output/ /output/",
            f'LABEL build.id="{config.build_id}"',
        ])
        
        return "\n".join(dockerfile_lines)
    
    def _validate_dockerfile_hadolint(self, dockerfile_path: Path, progress: BuildProgress):
        try:
            subprocess.run(["hadolint", "--version"], capture_output=True, check=True)
            subprocess.run(["hadolint", str(dockerfile_path)], capture_output=True)
        except:
            pass
    
    def _build_docker_image(self, config: BuildConfiguration, progress: BuildProgress, dockerfile_path: Path) -> Image:
        progress.current_stage = "Building Docker image"
        progress.progress_percent = 40
        
        build_temp_dir = dockerfile_path.parent
        image_tag = f"llm-framework/{config.target_arch.value}:{config.build_id}"
        
        try:
            image, logs = self.docker_client.images.build(
                path=str(build_temp_dir),
                tag=image_tag,
                rm=True,
                timeout=config.build_timeout,
                buildargs=config.build_args
            )
            for log_entry in logs:
                if 'stream' in log_entry:
                    progress.add_log(f"BUILD: {log_entry['stream'].rstrip()}")
            return image
        except Exception as e:
            raise RuntimeError(f"Docker image build failed: {e}")
    
    def _execute_build_modules(self, config: BuildConfiguration, progress: BuildProgress, image: Image):
        """
        Execute the 4-module build pipeline in container.
        Now with INJECTION of Source Repositories.
        """
        progress.current_stage = "Executing build modules"
        progress.progress_percent = 60
        
        build_temp_dir = self.cache_dir / "builds" / config.build_id
        
        volumes = {
            str(build_temp_dir / "output"): {"bind": "/workspace/output", "mode": "rw"},
            str(self.cache_dir / "models"): {"bind": "/workspace/cache/models", "mode": "rw"},
            str(self.cache_dir / "tools"): {"bind": "/workspace/cache/tools", "mode": "rw"}
        }
        
        environment = {
            "BUILD_ID": config.build_id,
            "MODEL_SOURCE": config.model_source,
            "TARGET_ARCH": config.target_arch.value,
            "TARGET_FORMAT": config.target_format.value,
            "OPTIMIZATION_LEVEL": config.optimization_level.value
        }
        
        if config.quantization:
            environment["QUANTIZATION"] = config.quantization
            
        # --- INJECT SOURCE REPOSITORIES FROM CONFIG ---
        # This ensures CLI builds use the same overrides as GUI
        if hasattr(self.framework_manager.config, 'source_repositories'):
            for key, url in self.framework_manager.config.source_repositories.items():
                # Convention: core.llama_cpp -> LLAMA_CPP_REPO_OVERRIDE
                # Split by dot, take last part, uppercase, append _REPO_OVERRIDE
                if '.' in key:
                    name_part = key.split('.')[-1]
                else:
                    name_part = key
                
                env_var_name = f"{name_part.upper()}_REPO_OVERRIDE"
                environment[env_var_name] = url
                # progress.add_log(f"Injected Source: {env_var_name}={url}")

        try:
            container = self.docker_client.containers.create(
                image=image.id,
                command="/bin/bash -c 'echo Build modules executed in Dockerfile stages'",
                volumes=volumes,
                environment=environment,
                working_dir="/workspace",
                name=f"llm-build-{config.build_id}"
            )
            
            with self._lock:
                self._active_containers[config.build_id] = container
            
            progress.add_log("Container created for module execution")
            container.start()
            result = container.wait(timeout=config.build_timeout)
            exit_code = result['StatusCode']
            
            if exit_code != 0:
                logs = container.logs(stdout=True, stderr=True).decode('utf-8')
                progress.add_error(f"Module execution failed with exit code {exit_code}")
                progress.add_error(f"Container logs: {logs}")
                raise RuntimeError(f"Build modules failed with exit code {exit_code}")
            
            progress.add_log("All build modules executed successfully")
            
        except Exception as e:
            progress.add_error(f"Module execution failed: {e}")
            raise
    
    def _check_buildx_availability(self) -> bool:
        try:
            subprocess.run(["docker", "buildx", "version"], capture_output=True, check=True)
            return True
        except:
            return False

    def _extract_artifacts(self, config: BuildConfiguration, progress: BuildProgress):
        progress.current_stage = "Extracting artifacts"
        progress.progress_percent = 80
        
        build_temp_dir = self.cache_dir / "builds" / config.build_id
        output_temp_dir = build_temp_dir / "output"
        final_output_dir = Path(config.output_dir)
        
        ensure_directory(final_output_dir)
        
        if output_temp_dir.exists():
            for artifact_path in output_temp_dir.rglob("*"):
                if artifact_path.is_file():
                    relative_path = artifact_path.relative_to(output_temp_dir)
                    final_path = final_output_dir / relative_path
                    ensure_directory(final_path.parent)
                    shutil.copy2(artifact_path, final_path)
                    progress.artifacts.append(str(final_path))
        
        progress.add_log(f"Artifacts extracted to: {final_output_dir}")

def validate_build_requirements() -> Dict[str, Any]:
    requirements = {"docker": False, "poetry": False, "errors": []}
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        requirements["docker"] = True
    except:
        requirements["errors"].append("Docker not available")
    return requirements
