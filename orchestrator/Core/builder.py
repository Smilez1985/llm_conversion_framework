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
        """
        Start a new model build with the given configuration.
        
        Args:
            config: Complete build configuration
            
        Returns:
            str: Build ID for tracking
            
        Raises:
            ValidationError: If configuration is invalid
            RuntimeError: If build cannot be started
        """
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
        """Get current build status"""
        return self._builds.get(build_id)
    
    def list_builds(self) -> List[BuildProgress]:
        """List all builds"""
        with self._lock:
            return list(self._builds.values())
    
    def cancel_build(self, build_id: str) -> bool:
        """
        Cancel a running build.
        
        Args:
            build_id: Build to cancel
            
        Returns:
            bool: True if cancellation initiated
        """
        progress = self._builds.get(build_id)
        if not progress:
            return False
        
        if progress.status in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]:
            return False
        
        # Update status
        progress.status = BuildStatus.CANCELLED
        progress.add_log("Build cancellation requested")
        
        # Stop container if running
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
        """
        Cleanup resources for a completed build.
        
        Args:
            build_id: Build to cleanup
            
        Returns:
            bool: True if cleanup successful
        """
        progress = self._builds.get(build_id)
        if not progress:
            return False
        
        try:
            progress.status = BuildStatus.CLEANING
            progress.add_log("Starting cleanup")
            
            # Remove container
            container = self._active_containers.get(build_id)
            if container:
                try:
                    container.remove(force=True)
                    del self._active_containers[build_id]
                    progress.add_log("Container removed")
                except Exception as e:
                    progress.add_warning(f"Container cleanup failed: {e}")
            
            # Remove temporary build directory
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
        """
        Execute the complete build process.
        
        Args:
            config: Build configuration
        """
        build_id = config.build_id
        progress = self._builds[build_id]
        
        try:
            progress.status = BuildStatus.PREPARING
            progress.current_stage = "Preparing build environment"
            progress.add_log("Starting build execution")
            
            # Step 1: Prepare build environment
            self._prepare_build_environment(config, progress)
            
            # Step 2: Generate Dockerfile
            dockerfile_path = self._generate_dockerfile(config, progress)
            
            # Step 3: Build Docker image
            image = self._build_docker_image(config, progress, dockerfile_path)
            
            # Step 4: Execute build modules in container
            self._execute_build_modules(config, progress, image)
            
            # Step 5: Extract and validate artifacts
            self._extract_artifacts(config, progress)
            
            # Step 6: Cleanup if requested
            if config.cleanup_after_build:
                self.cleanup_build(build_id)
            
            # Mark as completed
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
            
            # Cleanup on failure
            try:
                self.cleanup_build(build_id)
            except Exception as cleanup_error:
                progress.add_warning(f"Cleanup after failure failed: {cleanup_error}")
    
def _validate_build_config(self, config: BuildConfiguration):
        """
        Validate build configuration.
        
        Args:
            config: Configuration to validate
            
        Raises:
            ValidationError: If configuration is invalid
        """
        errors = []
        
        # Required fields
        if not config.build_id:
            errors.append("build_id is required")
        
        if not config.model_source:
            errors.append("model_source is required")
        
        if not config.target_arch:
            errors.append("target_arch is required")
        
        if not config.target_format:
            errors.append("target_format is required")
        
        if not config.output_dir:
            errors.append("output_dir is required")
        
        # Validate paths
        try:
            output_path = Path(config.output_dir)
            if not output_path.parent.exists():
                errors.append(f"Output directory parent does not exist: {output_path.parent}")
        except Exception as e:
            errors.append(f"Invalid output_dir: {e}")
        
        # Validate target architecture support
        if config.target_arch == TargetArch.RK3566:
            # RK3566 specific validations for MVP
            target_dir = self.targets_dir / "rk3566"
            if not target_dir.exists():
                errors.append("RK3566 target not found - missing target configuration")
            
            required_modules = ["source_module.sh", "config_module.sh", "convert_module.sh", "target_module.sh"]
            for module in required_modules:
                module_path = target_dir / "modules" / module
                if not module_path.exists():
                    errors.append(f"Missing required module: {module}")
                elif not os.access(module_path, os.X_OK):
                    errors.append(f"Module not executable: {module}")
        
        # Validate model format compatibility
        if config.source_format == ModelFormat.HUGGINGFACE and config.target_format == ModelFormat.HUGGINGFACE:
            errors.append("Source and target format cannot both be HuggingFace")
        
        # Validate quantization options
        if config.quantization and config.target_format != ModelFormat.GGUF:
            errors.append("Quantization is only supported for GGUF target format")
        
        if errors:
            raise ValidationError(f"Build configuration validation failed: {'; '.join(errors)}")
        
        self.logger.debug(f"Build configuration validated: {config.build_id}")
    
    def _prepare_build_environment(self, config: BuildConfiguration, progress: BuildProgress):
        """
        Prepare build environment and temporary directories.
        
        Args:
            config: Build configuration
            progress: Progress tracker
        """
        progress.current_stage = "Preparing build environment"
        progress.progress_percent = 10
        
        # Create build-specific temporary directory
        build_temp_dir = self.cache_dir / "builds" / config.build_id
        ensure_directory(build_temp_dir)
        
        # Create subdirectories
        subdirs = ["workspace", "modules", "output", "cache", "logs"]
        for subdir in subdirs:
            ensure_directory(build_temp_dir / subdir)
        
        # Copy target modules to build directory
        target_dir = self.targets_dir / config.target_arch.value
        if not target_dir.exists():
            raise RuntimeError(f"Target directory not found: {target_dir}")
        
        modules_src = target_dir / "modules"
        modules_dst = build_temp_dir / "modules"
        
        if modules_src.exists():
            # Copy all modules
            for module_file in modules_src.glob("*.sh"):
                dst_file = modules_dst / module_file.name
                shutil.copy2(module_file, dst_file)
                # Ensure executable
                os.chmod(dst_file, 0o755)
                progress.add_log(f"Module copied: {module_file.name}")
        
        # Copy target configuration
        target_config_src = target_dir / "target.yml"
        if target_config_src.exists():
            shutil.copy2(target_config_src, build_temp_dir / "target.yml")
            progress.add_log("Target configuration copied")
        
        # Create build configuration file for modules
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
        self.logger.debug(f"Build environment prepared: {build_temp_dir}")
    def _generate_dockerfile(self, config: BuildConfiguration, progress: BuildProgress) -> Path:
        
        """
        Generate Hadolint-compliant Multi-Stage Dockerfile with Poetry.
        
        Args:
            config: Build configuration
            progress: Progress tracker
            
        Returns:
            Path: Path to generated Dockerfile
        """
        progress.current_stage = "Generating Dockerfile"
        progress.progress_percent = 20
        
        build_temp_dir = self.cache_dir / "builds" / config.build_id
        dockerfile_path = build_temp_dir / "Dockerfile"
        
        # Load target-specific configuration
        target_config_path = build_temp_dir / "target.yml"
        target_config = {}
        if target_config_path.exists():
            with open(target_config_path, 'r') as f:
                target_config = yaml.safe_load(f)
        
        # Generate Dockerfile content
        dockerfile_content = self._generate_dockerfile_content(config, target_config)
        
        # Write Dockerfile
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        # Validate with Hadolint if enabled
        if config.enable_hadolint:
            self._validate_dockerfile_hadolint(dockerfile_path, progress)
        
        progress.add_log("Dockerfile generated")
        return dockerfile_path
    
    def _generate_dockerfile_content(self, config: BuildConfiguration, target_config: Dict) -> str:
        """
        Generate Multi-Stage Dockerfile content.
        
        Args:
            config: Build configuration
            target_config: Target-specific configuration
            
        Returns:
            str: Complete Dockerfile content
        """
        # Architecture mapping for Docker
        arch_mapping = {
            TargetArch.ARM64: "linux/arm64",
            TargetArch.ARMV7: "linux/arm/v7", 
            TargetArch.X86_64: "linux/amd64",
            TargetArch.RK3566: "linux/arm64",  # RK3566 is ARM64-based
            TargetArch.RK3588: "linux/arm64"
        }
        
        platform = arch_mapping.get(config.target_arch, "linux/amd64")
        
        dockerfile_lines = [
            "# hadolint ignore=DL3007",
            "# Multi-Stage Build for LLM Cross-Compilation",
            "# DIREKTIVE: BuildX + Hadolint + Poetry + Container-native (no VENV)",
            "",
            "# =============================================================================",
            "# STAGE 1: Base Builder Environment", 
            "# =============================================================================",
            f"FROM --platform={platform} {config.base_image} AS builder",
            "",
            "# Hadolint: Use specific versions and minimize layers",
            "# hadolint ignore=DL3008,DL3009",
            "RUN apt-get update && apt-get install -y --no-install-recommends \\",
            "    build-essential \\",
            "    cmake \\", 
            "    git \\",
            "    curl \\",
            "    wget \\",
            "    python3 \\",
            "    python3-pip \\",
            "    python3-dev \\",
            "    pkg-config \\",
            "    && apt-get clean \\",
            "    && rm -rf /var/lib/apt/lists/*",
            "",
            "# Install Poetry (no VENV in container)",
            "ENV POETRY_VERSION=" + (config.poetry_version if config.poetry_version != "latest" else "1.7.1"),
            "ENV POETRY_HOME=/opt/poetry",
            "ENV POETRY_CACHE_DIR=/workspace/cache/poetry",
            "ENV POETRY_VENV_IN_PROJECT=true",
            "RUN curl -sSL https://install.python-poetry.org | python3 - \\",
            "    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry",
            "",
            "# =============================================================================", 
            "# STAGE 2: Dependencies Installation",
            "# =============================================================================",
            "FROM builder AS dependencies",
            "",
            "WORKDIR /workspace",
            "",
            "# Copy Poetry configuration",
            "COPY pyproject.toml poetry.lock* ./",
            "",
            "# Install Python dependencies without VENV",
            "RUN poetry config virtualenvs.create false \\",
            "    && poetry install --no-dev --no-interaction --no-ansi",
            "",
        ]
        
        # Add target-specific dependencies
        if config.target_arch == TargetArch.RK3566:
            dockerfile_lines.extend([
                "# RK3566 specific dependencies",
                "RUN apt-get update && apt-get install -y --no-install-recommends \\",
                "    gcc-aarch64-linux-gnu \\",
                "    g++-aarch64-linux-gnu \\",
                "    crossbuild-essential-arm64 \\",
                "    && apt-get clean \\",
                "    && rm -rf /var/lib/apt/lists/*",
                "",
                "# Set cross-compilation environment for RK3566",
                "ENV CC=aarch64-linux-gnu-gcc",
                "ENV CXX=aarch64-linux-gnu-g++", 
                "ENV AR=aarch64-linux-gnu-ar",
                "ENV STRIP=aarch64-linux-gnu-strip",
                "ENV CMAKE_TOOLCHAIN_FILE=/workspace/cmake/rk3566-toolchain.cmake",
                "",
            ])
        
        # Continue with stage 3
        dockerfile_lines.extend([
            "# =============================================================================",
            "# STAGE 3: Build Tools Setup",
            "# =============================================================================", 
            "FROM dependencies AS build-tools",
            "",
            "# Create required directories",
            "RUN mkdir -p /workspace/modules /workspace/cache /workspace/output /workspace/cmake",
            "",
            "# Copy build modules",
            "COPY modules/ /workspace/modules/",
            "RUN chmod +x /workspace/modules/*.sh",
            "",
            "# Copy build configuration",
            "COPY build_config.json target.yml* /workspace/",
            "",
            "# Set environment variables",
            "ENV DEBIAN_FRONTEND=noninteractive",
            "ENV PYTHONUNBUFFERED=1",
            "ENV HF_HOME=/workspace/cache/huggingface",
            "ENV TRANSFORMERS_CACHE=/workspace/cache/transformers",
            f"ENV BUILD_JOBS={config.parallel_jobs}",
            f"ENV OPTIMIZATION_LEVEL={config.optimization_level.value}",
            "",
        ])
        
        # Add custom build args
        for key, value in config.build_args.items():
            dockerfile_lines.append(f"ENV {key}={value}")
        
        dockerfile_lines.extend([
            "",
            "# =============================================================================",
            "# STAGE 4: Build Execution", 
            "# =============================================================================",
            "FROM build-tools AS build-execution",
            "",
            "WORKDIR /workspace",
            "",
            "# Execute build modules in sequence",
            "# Each module is self-contained and validates dependencies",
            "",
            "# Module 1: Source Module (llama.cpp clone/build)",
            "RUN echo 'Executing source_module.sh...' \\",
            "    && /workspace/modules/source_module.sh \\",
            "    && echo 'Source module completed'",
            "",
            "# Module 2: Config Module (Hardware detection + CMake toolchain)",
            "RUN echo 'Executing config_module.sh...' \\", 
            "    && /workspace/modules/config_module.sh \\",
            "    && echo 'Config module completed'",
            "",
            "# Module 3: Convert Module (Model conversion HF→GGUF/ONNX)",
            "RUN echo 'Executing convert_module.sh...' \\",
            "    && /workspace/modules/convert_module.sh \\",
            "    && echo 'Convert module completed'",
            "",
            "# Module 4: Target Module (Quantization + Packaging)",
            "RUN echo 'Executing target_module.sh...' \\",
            "    && /workspace/modules/target_module.sh \\",
            "    && echo 'Target module completed'",
            "",
            "# =============================================================================",
            "# STAGE 5: Final Output",
            "# =============================================================================",
            "FROM scratch AS output",
            "",
            "# Copy only the final artifacts",
            "COPY --from=build-execution /workspace/output/ /output/",
            "",
            "# Metadata",
            f'LABEL build.id="{config.build_id}"',
            f'LABEL build.target="{config.target_arch.value}"',
            f'LABEL build.format="{config.target_format.value}"',
            f'LABEL build.timestamp="{config.timestamp}"',
            ""
        ])
        
        return "\n".join(dockerfile_lines)
    
    def _validate_dockerfile_hadolint(self, dockerfile_path: Path, progress: BuildProgress):
        """
        Validate Dockerfile with Hadolint.
        
        Args:
            dockerfile_path: Path to Dockerfile
            progress: Progress tracker
        """
        try:
            # Check if hadolint is available
            result = subprocess.run(
                ["hadolint", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Run hadolint validation
            result = subprocess.run(
                ["hadolint", str(dockerfile_path)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                progress.add_log("Dockerfile validated with Hadolint")
            else:
                # Log warnings but don't fail build
                progress.add_warning(f"Hadolint warnings: {result.stdout}")
                
        except subprocess.CalledProcessError:
            progress.add_warning("Hadolint not available - skipping validation")
        except Exception as e:
            progress.add_warning(f"Hadolint validation failed: {e}")
    
    def _build_docker_image(self, config: BuildConfiguration, progress: BuildProgress, dockerfile_path: Path) -> Image:
        """
        Build Docker image using BuildX.
        
        Args:
            config: Build configuration
            progress: Progress tracker
            dockerfile_path: Path to Dockerfile
            
        Returns:
            Image: Built Docker image
        """
        progress.current_stage = "Building Docker image"
        progress.progress_percent = 40
        
        build_temp_dir = dockerfile_path.parent
        image_tag = f"llm-framework/{config.target_arch.value}:{config.build_id}"
        
        try:
            # Use BuildX for multi-arch support
            buildx_available = self._check_buildx_availability()
            
            if buildx_available:
                progress.add_log("Using Docker BuildX for multi-architecture build")
                image = self._build_with_buildx(config, build_temp_dir, image_tag, progress)
            else:
                progress.add_log("Using standard Docker build")
                image = self._build_with_docker(config, build_temp_dir, image_tag, progress)
            
            progress.add_log(f"Docker image built: {image_tag}")
            return image
            
        except Exception as e:
            raise RuntimeError(f"Docker image build failed: {e}")
    
    def _build_with_buildx(self, config: BuildConfiguration, build_dir: Path, image_tag: str, progress: BuildProgress) -> Image:
        """Build with Docker BuildX for multi-arch support"""
        arch_mapping = {
            TargetArch.ARM64: "linux/arm64",
            TargetArch.ARMV7: "linux/arm/v7",
            TargetArch.X86_64: "linux/amd64", 
            TargetArch.RK3566: "linux/arm64",
            TargetArch.RK3588: "linux/arm64"
        }
        
        platform = arch_mapping.get(config.target_arch, "linux/amd64")
        
        # Build command
        cmd = [
            "docker", "buildx", "build",
            "--platform", platform,
            "--tag", image_tag,
            "--load",  # Load into Docker daemon
            str(build_dir)
        ]
        
        # Add build args
        for key, value in config.build_args.items():
            cmd.extend(["--build-arg", f"{key}={value}"])
        
        # Execute build
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=build_dir
        )
        
        # Stream output
        for line in process.stdout:
            progress.add_log(f"BUILD: {line.rstrip()}")
        
        process.wait()
        
        if process.returncode != 0:
            raise RuntimeError("BuildX build failed")
        
        # Get the built image
        return self.docker_client.images.get(image_tag)
    
    def _build_with_docker(self, config: BuildConfiguration, build_dir: Path, image_tag: str, progress: BuildProgress) -> Image:
        """Build with standard Docker API"""
        # Build the image
        image, logs = self.docker_client.images.build(
            path=str(build_dir),
            tag=image_tag,
            rm=True,
            timeout=config.build_timeout,
            buildargs=config.build_args
        )
        
        # Log build output
        for log_entry in logs:
            if 'stream' in log_entry:
                progress.add_log(f"BUILD: {log_entry['stream'].rstrip()}")
        
        return image
    
    def _execute_build_modules(self, config: BuildConfiguration, progress: BuildProgress, image: Image):
        """
        Execute the 4-module build pipeline in container.
        
        Args:
            config: Build configuration
            progress: Progress tracker
            image: Docker image to run
        """
        progress.current_stage = "Executing build modules"
        progress.progress_percent = 60
        
        build_temp_dir = self.cache_dir / "builds" / config.build_id
        
        # Prepare volume mounts
        volumes = {
            str(build_temp_dir / "output"): {"bind": "/workspace/output", "mode": "rw"},
            str(self.cache_dir / "models"): {"bind": "/workspace/cache/models", "mode": "rw"},
            str(self.cache_dir / "tools"): {"bind": "/workspace/cache/tools", "mode": "rw"}
        }
        
        # Environment variables
        environment = {
            "BUILD_ID": config.build_id,
            "MODEL_SOURCE": config.model_source,
            "TARGET_ARCH": config.target_arch.value,
            "TARGET_FORMAT": config.target_format.value,
            "OPTIMIZATION_LEVEL": config.optimization_level.value
        }
        
        if config.quantization:
            environment["QUANTIZATION"] = config.quantization
        
        try:
            # Create and start container
            container = self.docker_client.containers.create(
                image=image.id,
                command="/bin/bash -c 'echo Build modules executed in Dockerfile stages'",
                volumes=volumes,
                environment=environment,
                working_dir="/workspace",
                name=f"llm-build-{config.build_id}"
            )
            
            # Register container for potential cleanup
            with self._lock:
                self._active_containers[config.build_id] = container
            
            progress.add_log("Container created for module execution")
            
            # Start container (modules already executed in Dockerfile)
            container.start()
            
            # Wait for completion
            result = container.wait(timeout=config.build_timeout)
            exit_code = result['StatusCode']
            
            if exit_code != 0:
                # Get logs for debugging
                logs = container.logs(stdout=True, stderr=True).decode('utf-8')
                progress.add_error(f"Module execution failed with exit code {exit_code}")
                progress.add_error(f"Container logs: {logs}")
                raise RuntimeError(f"Build modules failed with exit code {exit_code}")
            
            progress.add_log("All build modules executed successfully")
            
        except Exception as e:
            progress.add_error(f"Module execution failed: {e}")
            raise
        
        finally:
            # Container cleanup will be handled by cleanup_build()
            pass
    
    def _check_buildx_availability(self) -> bool:
        """Check if Docker BuildX is available"""
        try:
            subprocess.run(
                ["docker", "buildx", "version"],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    def _extract_artifacts(self, config: BuildConfiguration, progress: BuildProgress):
        """
        Extract and validate build artifacts from container.
        
        Args:
            config: Build configuration
            progress: Progress tracker
        """
        progress.current_stage = "Extracting artifacts"
        progress.progress_percent = 80
        
        build_temp_dir = self.cache_dir / "builds" / config.build_id
        output_temp_dir = build_temp_dir / "output"
        final_output_dir = Path(config.output_dir)
        
        # Ensure final output directory exists
        ensure_directory(final_output_dir)
        
        # Check if artifacts were generated
        if not output_temp_dir.exists() or not any(output_temp_dir.iterdir()):
            raise RuntimeError("No build artifacts found")
        
        # List and validate artifacts
        artifacts = []
        for artifact_file in output_temp_dir.rglob("*"):
            if artifact_file.is_file():
                artifacts.append(str(artifact_file.relative_to(output_temp_dir)))
        
        if not artifacts:
            raise RuntimeError("No valid artifacts found")
        
        progress.add_log(f"Found {len(artifacts)} artifacts")
        
        # Copy artifacts to final output directory
        for artifact_path in output_temp_dir.rglob("*"):
            if artifact_path.is_file():
                relative_path = artifact_path.relative_to(output_temp_dir)
                final_path = final_output_dir / relative_path
                
                # Ensure target directory exists
                ensure_directory(final_path.parent)
                
                # Copy artifact
                shutil.copy2(artifact_path, final_path)
                progress.artifacts.append(str(final_path))
                progress.add_log(f"Artifact copied: {relative_path}")
        
        # Generate build manifest
        self._generate_build_manifest(config, progress, final_output_dir)
        
        # Validate artifacts based on target format
        self._validate_artifacts(config, progress, final_output_dir)
        
        progress.add_log(f"Artifacts extracted to: {final_output_dir}")
    
    def _generate_build_manifest(self, config: BuildConfiguration, progress: BuildProgress, output_dir: Path):
        """
        Generate build manifest with metadata.
        
        Args:
            config: Build configuration
            progress: Progress tracker
            output_dir: Output directory
        """
        if not config.include_metadata:
            return
        
        manifest = {
            "build_info": {
                "build_id": config.build_id,
                "timestamp": config.timestamp,
                "framework_version": self.framework_manager.info.version,
                "build_duration_seconds": None
            },
            "source": {
                "model_source": config.model_source,
                "model_branch": config.model_branch,
                "source_format": config.source_format.value
            },
            "target": {
                "architecture": config.target_arch.value,
                "format": config.target_format.value,
                "board": config.target_board,
                "optimization_level": config.optimization_level.value,
                "quantization": config.quantization
            },
            "artifacts": progress.artifacts,
            "build_log": progress.logs[-50:] if len(progress.logs) > 50 else progress.logs  # Last 50 entries
        }
        
        # Calculate build duration if completed
        if progress.start_time and progress.end_time:
            duration = (progress.end_time - progress.start_time).total_seconds()
            manifest["build_info"]["build_duration_seconds"] = duration
        
        # Write manifest
        manifest_path = output_dir / "build_manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2, default=str)
        
        progress.add_log("Build manifest generated")
    
    def _validate_artifacts(self, config: BuildConfiguration, progress: BuildProgress, output_dir: Path):
        """
        Validate generated artifacts based on target format.
        
        Args:
            config: Build configuration
            progress: Progress tracker
            output_dir: Output directory
        """
        expected_extensions = {
            ModelFormat.GGUF: [".gguf"],
            ModelFormat.ONNX: [".onnx"],
            ModelFormat.TENSORFLOW_LITE: [".tflite"],
            ModelFormat.PYTORCH_MOBILE: [".pt", ".pth"],
            ModelFormat.HUGGINGFACE: [".safetensors", ".bin", "config.json"]
        }
        
        expected_exts = expected_extensions.get(config.target_format, [])
        
        if not expected_exts:
            progress.add_warning(f"No validation rules for format: {config.target_format.value}")
            return
        
        # Check for expected files
        found_artifacts = []
        for ext in expected_exts:
            artifacts = list(output_dir.rglob(f"*{ext}"))
            found_artifacts.extend(artifacts)
        
        if not found_artifacts:
            progress.add_warning(f"No artifacts found with expected extensions: {expected_exts}")
        else:
            progress.add_log(f"Validated {len(found_artifacts)} artifacts for format {config.target_format.value}")
        
        # Additional format-specific validation
        if config.target_format == ModelFormat.GGUF:
            self._validate_gguf_artifacts(output_dir, progress)
        elif config.target_format == ModelFormat.ONNX:
            self._validate_onnx_artifacts(output_dir, progress)
    
    def _validate_gguf_artifacts(self, output_dir: Path, progress: BuildProgress):
        """Validate GGUF-specific artifacts"""
        gguf_files = list(output_dir.rglob("*.gguf"))
        
        for gguf_file in gguf_files:
            # Basic file size check
            file_size_mb = gguf_file.stat().st_size / (1024 * 1024)
            if file_size_mb < 1:
                progress.add_warning(f"GGUF file unusually small: {gguf_file.name} ({file_size_mb:.1f}MB)")
            else:
                progress.add_log(f"GGUF file validated: {gguf_file.name} ({file_size_mb:.1f}MB)")
    
    def _validate_onnx_artifacts(self, output_dir: Path, progress: BuildProgress):
        """Validate ONNX-specific artifacts"""
        onnx_files = list(output_dir.rglob("*.onnx"))
        
        for onnx_file in onnx_files:
            # Basic file size check
            file_size_mb = onnx_file.stat().st_size / (1024 * 1024)
            if file_size_mb < 1:
                progress.add_warning(f"ONNX file unusually small: {onnx_file.name} ({file_size_mb:.1f}MB)")
            else:
                progress.add_log(f"ONNX file validated: {onnx_file.name} ({file_size_mb:.1f}MB)")
    
    def get_build_logs(self, build_id: str) -> List[str]:
        """
        Get build logs for a specific build.
        
        Args:
            build_id: Build identifier
            
        Returns:
            List[str]: Build log entries
        """
        progress = self._builds.get(build_id)
        return progress.logs if progress else []
    
    def get_build_artifacts(self, build_id: str) -> List[str]:
        """
        Get build artifacts for a specific build.
        
        Args:
            build_id: Build identifier
            
        Returns:
            List[str]: Artifact file paths
        """
        progress = self._builds.get(build_id)
        return progress.artifacts if progress else []
    
    def shutdown(self):
        """Shutdown the build engine and cleanup resources"""
        self.logger.info("Shutting down Build Engine...")
        
        # Cancel all active builds
        for build_id in list(self._builds.keys()):
            progress = self._builds[build_id]
            if progress.status not in [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]:
                self.cancel_build(build_id)
        
        # Stop and remove all containers
        for build_id, container in list(self._active_containers.items()):
            try:
                container.stop(timeout=10)
                container.remove(force=True)
                self.logger.debug(f"Container cleaned up: {build_id}")
            except Exception as e:
                self.logger.error(f"Failed to cleanup container {build_id}: {e}")
        
        # Shutdown executor
        self._executor.shutdown(wait=True, timeout=30)
        
        self.logger.info("Build Engine shutdown completed")
    
    def get_target_info(self, target_arch: TargetArch) -> Dict[str, Any]:
        """
        Get information about a specific target.
        
        Args:
            target_arch: Target architecture
            
        Returns:
            dict: Target information
        """
        target_dir = self.targets_dir / target_arch.value
        
        if not target_dir.exists():
            return {"available": False, "error": "Target directory not found"}
        
        # Load target configuration
        target_yml = target_dir / "target.yml"
        target_config = {}
        if target_yml.exists():
            try:
                with open(target_yml, 'r') as f:
                    target_config = yaml.safe_load(f)
            except Exception as e:
                return {"available": False, "error": f"Failed to load target config: {e}"}
        
        # Check modules
        modules_dir = target_dir / "modules"
        available_modules = []
        if modules_dir.exists():
            for module_file in modules_dir.glob("*.sh"):
                if os.access(module_file, os.X_OK):
                    available_modules.append(module_file.name)
        
        return {
            "available": True,
            "target_arch": target_arch.value,
            "config": target_config,
            "modules": available_modules,
            "target_path": str(target_dir)
        }
    
    def list_available_targets(self) -> List[Dict[str, Any]]:
        """
        List all available targets.
        
        Returns:
            List[dict]: Available target information
        """
        targets = []
        
        for target_arch in TargetArch:
            target_info = self.get_target_info(target_arch)
            if target_info.get("available", False):
                targets.append(target_info)
        
        return targets
    
    def estimate_build_time(self, config: BuildConfiguration) -> Dict[str, Any]:
        """
        Estimate build time based on configuration.
        
        Args:
            config: Build configuration
            
        Returns:
            dict: Time estimates
        """
        base_times = {
            OptimizationLevel.FAST: 300,      # 5 minutes
            OptimizationLevel.BALANCED: 600,  # 10 minutes  
            OptimizationLevel.SIZE: 900,      # 15 minutes
            OptimizationLevel.SPEED: 1200,    # 20 minutes
            OptimizationLevel.AGGRESSIVE: 1800 # 30 minutes
        }
        
        base_time = base_times.get(config.optimization_level, 600)
        
        # Adjust for target architecture
        arch_multipliers = {
            TargetArch.X86_64: 1.0,
            TargetArch.ARM64: 1.3,
            TargetArch.ARMV7: 1.5,
            TargetArch.RK3566: 1.4,  # Cross-compilation overhead
            TargetArch.RK3588: 1.3
        }
        
        arch_multiplier = arch_multipliers.get(config.target_arch, 1.2)
        
        # Adjust for target format
        format_multipliers = {
            ModelFormat.GGUF: 1.0,
            ModelFormat.ONNX: 1.2,
            ModelFormat.TENSORFLOW_LITE: 1.5,
            ModelFormat.PYTORCH_MOBILE: 1.3,
            ModelFormat.HUGGINGFACE: 0.8
        }
        
        format_multiplier = format_multipliers.get(config.target_format, 1.0)
        
        # Calculate estimate
        estimated_seconds = int(base_time * arch_multiplier * format_multiplier)
        
        return {
            "estimated_seconds": estimated_seconds,
            "estimated_minutes": estimated_seconds // 60,
            "factors": {
                "base_time": base_time,
                "arch_multiplier": arch_multiplier,
                "format_multiplier": format_multiplier
            }
        }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_build_config(
    model_source: str,
    target_arch: TargetArch,
    target_format: ModelFormat,
    output_dir: str,
    build_id: Optional[str] = None,
    **kwargs
) -> BuildConfiguration:
    """
    Create a build configuration with sensible defaults.
    
    Args:
        model_source: Model source (HuggingFace name or path)
        target_arch: Target architecture
        target_format: Target format
        output_dir: Output directory
        build_id: Build ID (auto-generated if None)
        **kwargs: Additional configuration options
        
    Returns:
        BuildConfiguration: Complete build configuration
    """
    if not build_id:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        build_id = f"build_{timestamp}"
    
    timestamp = datetime.now().isoformat()
    
    return BuildConfiguration(
        build_id=build_id,
        timestamp=timestamp,
        model_source=model_source,
        target_arch=target_arch,
        target_format=target_format,
        output_dir=output_dir,
        **kwargs
    )


    def validate_build_requirements() -> Dict[str, Any]:
    """
    Validate system requirements for building.
    
    Returns:
        dict: Validation results
    """
    requirements = {
        "docker": False,
        "buildx": False,
        "hadolint": False,
        "poetry": False,
        "errors": []
    }
    
    # Check Docker
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        requirements["docker"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        requirements["errors"].append("Docker not available")
    
    # Check BuildX
    try:
        subprocess.run(["docker", "buildx", "version"], capture_output=True, check=True)
        requirements["buildx"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        requirements["errors"].append("Docker BuildX not available")
    
    # Check Hadolint
    try:
        subprocess.run(["hadolint", "--version"], capture_output=True, check=True)
        requirements["hadolint"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        requirements["errors"].append("Hadolint not available (optional)")
    
    # Check Poetry
    try:
        subprocess.run(["poetry", "--version"], capture_output=True, check=True)
        requirements["poetry"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        requirements["errors"].append("Poetry not available")
    
    return requirements
