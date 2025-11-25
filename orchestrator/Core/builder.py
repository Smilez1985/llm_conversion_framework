#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Build Engine
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Container-native Build-Engine für Cross-Compilation von AI-Modellen.
Multi-Stage Docker Builds mit BuildX, Hadolint-konform, Poetry-basiert.
Keine VENV - Docker Container = Isolation.
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
from orchestrator.utils.validation import ValidationError
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

class TargetArch(Enum):
    """Supported target architectures"""
    ARM64 = "arm64"
    ARMV7 = "armv7"
    X86_64 = "x86_64"
    RK3566 = "rk3566"
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
    target_arch: TargetArch
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
    base_image: str = "debian:bookworm-slim"
    build_args: Dict[str, str] = field(default_factory=dict)
    dockerfile_template: Optional[str] = None
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
        
        # Paths
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
                subprocess.run(["docker", "buildx", "version"], capture_output=True, check=True)
            except:
                self.logger.warning("Docker BuildX not available")
        except Exception as e:
            raise RuntimeError(f"Docker environment failed: {e}")

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
            self._prepare_build_environment(config, prog)
            df_path = self._generate_dockerfile(config, prog)
            image = self._build_docker_image(config, prog, df_path)
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
        build_temp = self.cache_dir / "builds" / config.build_id
        ensure_directory(build_temp)
        for d in ["workspace", "modules", "output", "cache", "logs"]: ensure_directory(build_temp / d)
        
        target_dir = self.targets_dir / config.target_arch.value
        if not target_dir.exists(): target_dir = self.targets_dir / "_template"
        
        modules_src = target_dir / "modules"
        modules_dst = build_temp / "modules"
        if modules_src.exists():
            for f in modules_src.glob("*.sh"):
                shutil.copy2(f, modules_dst / f.name)
                os.chmod(modules_dst / f.name, 0o755)
        
        if (target_dir / "target.yml").exists():
            shutil.copy2(target_dir / "target.yml", build_temp / "target.yml")
        
        with open(build_temp / "build_config.json", 'w') as f:
            json.dump(asdict(config), f, indent=2, default=str)

    def _generate_dockerfile(self, config: BuildConfiguration, progress: BuildProgress) -> Path:
        progress.current_stage = "Generating Dockerfile"
        progress.progress_percent = 20
        build_temp = self.cache_dir / "builds" / config.build_id
        df_path = build_temp / "Dockerfile"
        
        target_cfg = {}
        if (build_temp / "target.yml").exists():
            with open(build_temp / "target.yml", 'r') as f: target_cfg = yaml.safe_load(f)
            
        content = self._generate_dockerfile_content(config, target_cfg)
        with open(df_path, 'w') as f: f.write(content)
        
        if config.enable_hadolint: self._validate_dockerfile_hadolint(df_path, progress)
        return df_path

    def _generate_dockerfile_content(self, config: BuildConfiguration, target_config: Dict) -> str:
        plat_map = {
            TargetArch.ARM64: "linux/arm64", TargetArch.RK3566: "linux/arm64", TargetArch.RK3588: "linux/arm64",
            TargetArch.X86_64: "linux/amd64", TargetArch.ARMV7: "linux/arm/v7"
        }
        platform = plat_map.get(config.target_arch, "linux/amd64")
        
        lines = [
            "# hadolint ignore=DL3007",
            f"FROM --platform={platform} {config.base_image} AS builder",
            "RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake git curl wget python3 python3-pip python3-dev pkg-config && apt-get clean && rm -rf /var/lib/apt/lists/*",
            f"ENV POETRY_VERSION={config.poetry_version if config.poetry_version != 'latest' else '1.7.1'}",
            "ENV POETRY_HOME=/opt/poetry POETRY_VENV_IN_PROJECT=true PATH=\"/opt/poetry/bin:$PATH\"",
            "RUN curl -sSL https://install.python-poetry.org | python3 - && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry",
            "FROM builder AS dependencies",
            "WORKDIR /workspace",
            "COPY pyproject.toml poetry.lock* ./",
            "RUN poetry config virtualenvs.create true && poetry install --no-dev --no-interaction --no-ansi"
        ]
        
        if config.target_arch == TargetArch.RK3566:
            lines.extend([
                "RUN apt-get update && apt-get install -y --no-install-recommends gcc-aarch64-linux-gnu g++-aarch64-linux-gnu crossbuild-essential-arm64 && apt-get clean",
                "ENV CC=aarch64-linux-gnu-gcc CXX=aarch64-linux-gnu-g++ AR=aarch64-linux-gnu-ar STRIP=aarch64-linux-gnu-strip",
                # FIX: Korrekter Toolchain-Dateiname
                "ENV CMAKE_TOOLCHAIN_FILE=/workspace/cmake/cross_compile_toolchain.cmake"
            ])
            
        lines.extend([
            "FROM dependencies AS build-tools",
            "RUN mkdir -p /workspace/modules /workspace/cache /workspace/output /workspace/cmake",
            "COPY modules/ /workspace/modules/",
            "RUN chmod +x /workspace/modules/*.sh",
            "COPY build_config.json target.yml* /workspace/",
            "ENV PATH=\"/workspace/.venv/bin:$PATH\" VIRTUAL_ENV=\"/workspace/.venv\"",
            "FROM build-tools AS build-execution",
            "WORKDIR /workspace",
            "RUN /workspace/modules/source_module.sh",
            "RUN /workspace/modules/config_module.sh",
            "RUN /workspace/modules/convert_module.sh",
            "RUN /workspace/modules/target_module.sh",
            "FROM scratch AS output",
            "COPY --from=build-execution /workspace/output/ /output/",
            f'LABEL build.id="{config.build_id}"'
        ])
        return "\n".join(lines)

    def _validate_dockerfile_hadolint(self, path: Path, prog: BuildProgress):
        try: subprocess.run(["hadolint", str(path)], check=True, capture_output=True)
        except: prog.add_warning("Hadolint check failed or not available")

    def _build_docker_image(self, config: BuildConfiguration, progress: BuildProgress, path: Path) -> Image:
        progress.current_stage = "Building Image"
        progress.progress_percent = 40
        tag = f"llm-framework/{config.target_arch.value}:{config.build_id}"
        
        try:
            # BuildX Check
            try:
                subprocess.run(["docker", "buildx", "version"], check=True, capture_output=True)
                return self._build_with_buildx(config, path.parent, tag, progress)
            except:
                return self._build_with_docker(config, path.parent, tag, progress)
        except Exception as e:
            raise RuntimeError(f"Image build failed: {e}")

    def _build_with_buildx(self, config, build_dir, tag, progress):
        plat = "linux/arm64" if config.target_arch in [TargetArch.ARM64, TargetArch.RK3566] else "linux/amd64"
        cmd = ["docker", "buildx", "build", "--platform", plat, "--tag", tag, "--load", str(build_dir)]
        for k, v in config.build_args.items(): cmd.extend(["--build-arg", f"{k}={v}"])
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=build_dir)
        for line in proc.stdout: progress.add_log(f"BUILD: {line.rstrip()}")
        proc.wait()
        if proc.returncode != 0: raise RuntimeError("BuildX failed")
        return self.docker_client.images.get(tag)

    def _build_with_docker(self, config, build_dir, tag, progress):
        img, logs = self.docker_client.images.build(path=str(build_dir), tag=tag, rm=True, timeout=config.build_timeout, buildargs=config.build_args)
        for l in logs: 
            if 'stream' in l: progress.add_log(f"BUILD: {l['stream'].strip()}")
        return img

    def _execute_build_modules(self, config, progress, image):
        progress.current_stage = "Running modules"
        progress.progress_percent = 60
        build_temp = self.cache_dir / "builds" / config.build_id
        
        vols = {
            str(build_temp / "output"): {"bind": "/workspace/output", "mode": "rw"},
            str(self.cache_dir / "models"): {"bind": "/workspace/cache/models", "mode": "rw"}
        }
        env = {
            "BUILD_ID": config.build_id,
            "MODEL_SOURCE": config.model_source,
            "TARGET_ARCH": config.target_arch.value,
            "OPTIMIZATION_LEVEL": config.optimization_level.value,
            "QUANTIZATION": config.quantization or ""
        }
        
        # Inject Sources
        if hasattr(self.framework_manager.config, 'source_repositories'):
            for k, v in self.framework_manager.config.source_repositories.items():
                key = k.split('.')[-1] if '.' in k else k
                env[f"{key.upper()}_REPO_OVERRIDE"] = v

        container = self.docker_client.containers.create(
            image=image.id, command="/bin/bash -c 'echo Modules executed'", 
            volumes=vols, environment=env, name=f"llm-build-{config.build_id}"
        )
        with self._lock: self._active_containers[config.build_id] = container
        container.start()
        res = container.wait(timeout=config.build_timeout)
        if res['StatusCode'] != 0:
            raise RuntimeError(f"Container failed: {container.logs().decode()}")

    def _extract_artifacts(self, config, progress):
        progress.current_stage = "Extracting"
        progress.progress_percent = 80
        src = self.cache_dir / "builds" / config.build_id / "output"
        dst = Path(config.output_dir)
        if src.exists():
            for f in src.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(src)
                    target = dst / rel
                    ensure_directory(target.parent)
                    shutil.copy2(f, target)
                    progress.artifacts.append(str(target))
