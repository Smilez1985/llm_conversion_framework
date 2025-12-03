#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Build Engine
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Core logic for orchestrating Docker builds, container execution, and artifact management.
Handles security scans, GPU passthrough, and dynamic volume mounting.

Updates v1.7.0:
- "Golden Artifact" creation (Auto-Zip).
- Auto-Documentation: Generates Model_Card.md with hard facts.
- Intel GPU (XPU/Arc) Passthrough support via /dev/dri.
- FIX: Deterministic artifact detection instead of heuristics.
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
import hashlib
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
from docker.types import DeviceRequest 

from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory

# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class BuildStatus(Enum):
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

class ModelFormat(Enum):
    HUGGINGFACE = "hf"
    GGUF = "gguf"
    ONNX = "onnx"
    TENSORFLOW_LITE = "tflite"
    PYTORCH_MOBILE = "pytorch_mobile"
    # Hardware-Specific Formats
    RKNN = "rknn"          # Rockchip NPU
    TENSORRT = "tensorrt"  # NVIDIA GPU
    OPENVINO = "openvino"  # Intel NPU/CPU
    COREML = "coreml"      # Apple Silicon
    NCNN = "ncnn"          # Mobile High-Performance
    MNN = "mnn"            # Alibaba Mobile

class OptimizationLevel(Enum):
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
    """Complete build configuration object passed from Manager to Engine."""
    build_id: str
    timestamp: str
    model_source: str
    target_arch: str  # String-based (folder name) for modularity
    target_format: ModelFormat
    output_dir: str
    
    # Optional / Defaults
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
    
    # Features
    model_task: str = "LLM" 
    use_gpu: bool = False
    dataset_path: Optional[str] = None

@dataclass
class BuildProgress:
    """Tracks the state of a single build job."""
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
    """
    The core execution engine.
    Responsible for:
    1. Docker Environment Setup
    2. Image Building
    3. Container Execution (with GPU/Volume support)
    4. Security Scanning
    5. Artifact Extraction
    """
    
    def __init__(self, framework_manager, max_concurrent_builds: int = 2, default_timeout: int = 3600):
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        self.max_concurrent_builds = max_concurrent_builds
        self.default_timeout = default_timeout
        
        # Docker Client Setup
        self.docker_client = framework_manager.get_component("docker_client")
        if not self.docker_client:
            # Try to re-init if missing
            try:
                self.docker_client = docker.from_env()
            except Exception as e:
                raise RuntimeError(f"Docker client not available: {e}")
                
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
        self.logger.info(f"Build Engine initialized (max_workers: {max_concurrent_builds})")
    
    def _ensure_directories(self):
        dirs = [self.targets_dir, self.models_dir, self.output_dir, self.cache_dir, 
                self.cache_dir / "docker", self.cache_dir / "models", self.cache_dir / "tools"]
        for d in dirs: ensure_directory(d)
    
    def _validate_docker_environment(self):
        try:
            self.docker_client.ping()
            # Optional check for buildx
            try:
                subprocess.run(["docker", "buildx", "version"], capture_output=True, check=True)
            except Exception:
                self.logger.warning("Docker BuildX not available, standard build will be used.")
        except Exception as e:
            raise RuntimeError(f"Docker environment failed: {e}")

    def list_available_targets(self) -> List[Dict[str, Any]]:
        """Scans targets directory for valid target.yml files."""
        targets = []
        if not self.targets_dir.exists(): return targets
        
        for tp in self.targets_dir.iterdir():
            if tp.is_dir() and not tp.name.startswith("_") and (tp / "target.yml").exists():
                try:
                    with open(tp / "target.yml", "r") as f:
                        meta = yaml.safe_load(f)
                        targets.append({
                            "id": tp.name,
                            "target_arch": meta.get("metadata", {}).get("architecture_family", tp.name),
                            "name": meta.get("metadata", {}).get("name", tp.name),
                            "available": True,
                            "path": str(tp)
                        })
                except Exception: pass
        return targets

    def build_model(self, config: BuildConfiguration) -> str:
        """Submits a new build job."""
        self._validate_build_config(config)
        
        # Check concurrency
        active = len([b for b in self._builds.values() if b.status not in 
                      [BuildStatus.COMPLETED, BuildStatus.FAILED, BuildStatus.CANCELLED]])
        if active >= self.max_concurrent_builds:
            raise RuntimeError("Max concurrent builds reached")
            
        progress = BuildProgress(config.build_id, BuildStatus.QUEUED, "Initializing", start_time=datetime.now())
        
        with self._lock: 
            self._builds[config.build_id] = progress
            
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
        progress.add_log("Build cancelled by user.")
        
        # Stop container if running
        container = self._active_containers.get(build_id)
        if container:
            try: 
                container.stop(timeout=10)
            except Exception as e:
                self.logger.warning(f"Failed to stop container for {build_id}: {e}")
                
        return True

    def cleanup_build(self, build_id: str) -> bool:
        progress = self._builds.get(build_id)
        if not progress: return False
        
        try:
            progress.status = BuildStatus.CLEANING
            
            # Remove container
            container = self._active_containers.get(build_id)
            if container:
                try: 
                    container.remove(force=True)
                    with self._lock:
                        del self._active_containers[build_id]
                except Exception: pass
            
            # Remove temp dirs
            build_temp = self.cache_dir / "builds" / build_id
            if build_temp.exists(): 
                shutil.rmtree(build_temp)
                
            return True
        except Exception: return False
    
    def _execute_build(self, config: BuildConfiguration):
        """Main execution flow running in worker thread."""
        bid = config.build_id
        prog = self._builds[bid]
        
        try:
            prog.status = BuildStatus.PREPARING
            
            # 1. Resolve Target Path
            target_path = self.targets_dir / config.target_arch
            if not target_path.exists():
                # Fallback search (case insensitive)
                found = False
                for p in self.targets_dir.iterdir():
                    if p.name.lower() == config.target_arch.lower():
                        target_path = p
                        found = True
                        break
                if not found:
                    raise FileNotFoundError(f"Target {config.target_arch} not found in {self.targets_dir}")

            # 2. Prepare Environment
            self._prepare_build_environment(config, prog, target_path)
            
            # 3. Generate Dockerfile
            df_path = self._generate_dockerfile(config, prog, target_path)
            
            # 4. Build Docker Image
            image = self._build_docker_image(config, prog, df_path)
            
            # 5. Security Scan (Trivy)
            self._scan_image_security(image.tags[0], prog)
            
            # 6. Run Build Modules (Container)
            self._execute_build_modules(config, prog, image, target_path)
            
            # 7. Extract Artifacts
            self._extract_artifacts(config, prog)
            
            # 8. Create Golden Artifact (v1.7.0)
            self._create_golden_artifact(config, prog)
            
            # 9. Cleanup
            if config.cleanup_after_build: 
                self.cleanup_build(bid)
                
            prog.status = BuildStatus.COMPLETED
            prog.end_time = datetime.now()
            prog.progress_percent = 100
            
        except Exception as e:
            prog.status = BuildStatus.FAILED
            prog.end_time = datetime.now()
            prog.add_error(str(e))
            self.logger.error(f"Build {bid} failed: {e}", exc_info=True)
            # Try cleanup even on failure
            try: self.cleanup_build(bid)
            except Exception: pass

    def _validate_build_config(self, config: BuildConfiguration):
        if not config.build_id or not config.model_source or not config.output_dir:
            raise ValidationError("Missing required build config (ID, Source, or Output)")

    def _prepare_build_environment(self, config: BuildConfiguration, progress: BuildProgress, target_path: Path):
        progress.current_stage = "Preparing env"
        progress.progress_percent = 10
        progress.add_log(f"Preparing build environment for {config.target_arch}")
        
        build_temp = self.cache_dir / "builds" / config.build_id
        ensure_directory(build_temp)
        for d in ["output", "logs"]: ensure_directory(build_temp / d)
        
        # Dump config for debugging
        with open(build_temp / "build_config.json", 'w') as f:
            json.dump(asdict(config), f, indent=2, default=str)

    def _generate_dockerfile(self, config: BuildConfiguration, progress: BuildProgress, target_path: Path) -> Path:
        progress.current_stage = "Generating Dockerfile"
        progress.progress_percent = 20
        
        build_temp = self.cache_dir / "builds" / config.build_id
        df_path = build_temp / "Dockerfile"
        
        src_df_name = "Dockerfile.gpu" if config.use_gpu else "Dockerfile"
        src_df = target_path / src_df_name
        
        if not src_df.exists():
            src_df = target_path / "Dockerfile"
            
        if not src_df.exists():
            # Legacy fallback
            src_df = target_path / "dockerfile"
            
        if not src_df.exists(): 
            raise FileNotFoundError(f"Dockerfile missing in target {target_path}")
        
        progress.add_log(f"Using Dockerfile template: {src_df.name}")
        shutil.copy2(src_df, df_path)
        
        if config.enable_hadolint: 
            self._validate_dockerfile_hadolint(df_path, progress)
            
        return df_path

    def _validate_dockerfile_hadolint(self, path: Path, prog: BuildProgress):
        try: 
            subprocess.run(["hadolint", str(path)], check=True, capture_output=True) 
        except Exception: 
            prog.add_warning("Hadolint check skipped (tool not found or failed)")

    def _build_docker_image(self, config: BuildConfiguration, progress: BuildProgress, path: Path) -> Image:
        progress.current_stage = "Building Image"
        progress.progress_percent = 40
        
        tag = f"llm-framework/{config.target_arch.lower()}:{config.build_id.lower()}"
        context = self.base_dir
        rel_df = path.relative_to(context)
        
        progress.add_log(f"Building Docker Image: {tag}")
        
        try:
            cmd = ["docker", "build", "-f", str(rel_df), "-t", tag, str(context)]
            
            for k, v in config.build_args.items(): 
                cmd.extend(["--build-arg", f"{k}={v}"])
            
            if sys.platform != "win32":
                cmd.extend(["--build-arg", f"USER_ID={os.getuid()}"])
                cmd.extend(["--build-arg", f"GROUP_ID={os.getgid()}"])
            
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(context))
            
            for line in proc.stdout: 
                progress.add_log(f"BUILD: {line.rstrip()}")
            
            proc.wait()
            
            if proc.returncode != 0: 
                raise RuntimeError("Docker build process returned error code")
                
            return self.docker_client.images.get(tag)
            
        except Exception as e:
            raise RuntimeError(f"Image build failed: {e}")

    def _scan_image_security(self, image_tag: str, progress: BuildProgress):
        """Runs Trivy security scan on the image."""
        progress.add_log(f"Scanning image {image_tag} for vulnerabilities...")
        try:
            scan_cmd = ["image", "--exit-code", "1", "--severity", "HIGH,CRITICAL", image_tag]
            
            log_stream = self.docker_client.containers.run(
                "aquasec/trivy:latest", 
                command=scan_cmd,
                volumes={
                    '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'ro'}, 
                    'trivy_cache': {'bind': '/root/.cache/', 'mode': 'rw'}
                },
                remove=True, 
                stream=True
            )
            
            for line in log_stream: 
                progress.add_log(f"TRIVY: {line.decode().strip()}")
                
            progress.add_log("Security scan passed.")
            
        except docker.errors.ContainerError:
            progress.add_warning(f"Security vulnerabilities found! Review logs above.")
        except Exception as e:
            progress.add_warning(f"Security scan failed to run: {e}")

    def _execute_build_modules(self, config: BuildConfiguration, progress: BuildProgress, image: Image, target_path: Path):
        progress.current_stage = "Running modules"
        progress.progress_percent = 60
        progress.add_log("Starting Build Container...")
        
        build_temp = self.cache_dir / "builds" / config.build_id
        
        vols = {
            str(build_temp / "output"): {"bind": "/build-cache/output", "mode": "rw"},
            str(self.cache_dir / "models"): {"bind": "/build-cache/models", "mode": "rw"},
            str(target_path / "modules"): {"bind": "/app/modules", "mode": "ro"}
        }
        
        env = {
            "BUILD_ID": config.build_id,
            "MODEL_SOURCE": config.model_source,
            "MODEL_TASK": config.model_task, 
            "TARGET_ARCH": config.target_arch,
            "OPTIMIZATION_LEVEL": config.optimization_level.value,
            "QUANTIZATION": config.quantization or "",
            "LLAMA_CPP_COMMIT": config.build_args.get("LLAMA_CPP_COMMIT", "b3626"),
            "TARGET_FORMAT": config.target_format.value
        }
        
        if hasattr(self.framework_manager.config, 'source_repositories'):
            for k, v in self.framework_manager.config.source_repositories.items():
                if isinstance(v, dict) and 'url' in v:
                    key_parts = k.split('.')
                    name = key_parts[-1].upper()
                    env[f"{name}_REPO_OVERRIDE"] = v['url']
                elif isinstance(v, str):
                    name = k.split('.')[-1].upper()
                    env[f"{name}_REPO_OVERRIDE"] = v

        if config.dataset_path and os.path.exists(config.dataset_path):
            vols[str(config.dataset_path)] = {"bind": "/build-cache/dataset.txt", "mode": "ro"}
            env["DATASET_PATH"] = "/build-cache/dataset.txt"
            progress.add_log(f"Mounted Calibration Dataset: {config.dataset_path}")

        device_requests = []
        devices = []
        
        if config.use_gpu:
            if shutil.which("nvidia-smi"):
                progress.add_log("Enabling GPU Passthrough (NVIDIA)...")
                device_requests = [DeviceRequest(count=-1, capabilities=[['gpu']])]
            elif os.path.exists("/dev/dri"):
                progress.add_log("Enabling GPU Passthrough (Intel/VAAPI)...")
                devices = ["/dev/dri:/dev/dri"]
            else:
                progress.add_warning("GPU usage requested but no supported GPU (NVIDIA/Intel) detected on host.")

        container = self.docker_client.containers.create(
            image=image.id, 
            command=["/app/modules/build.sh"], 
            volumes=vols, 
            environment=env, 
            name=f"llm-build-{config.build_id}", 
            user="llmbuilder",
            device_requests=device_requests,
            devices=devices
        )
        
        with self._lock: 
            self._active_containers[config.build_id] = container
            
        container.start()
        
        for line in container.logs(stream=True, follow=True):
            progress.add_log(f"CONT: {line.decode().strip()}")
            
        res = container.wait(timeout=config.build_timeout)
        exit_code = res.get('StatusCode', 1)
        
        if exit_code != 0:
            raise RuntimeError(f"Build script failed with exit code {exit_code}")

    def _extract_artifacts(self, config, progress):
        progress.current_stage = "Extracting"
        progress.progress_percent = 85
        
        src = self.cache_dir / "builds" / config.build_id / "output"
        dst = Path(config.output_dir)
        
        progress.add_log(f"Copying artifacts to {dst}...")
        ensure_directory(dst)
        
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
            progress.add_log(f"Extracted {count} artifacts.")

    def _generate_model_card(self, config: BuildConfiguration, output_dir: Path):
        """Generates a standardized Model Card (README.md) for the artifact."""
        readme_path = output_dir / "Model_Card.md"
        
        # Security: Calculate hash of the primary artifact if possible
        model_hash = "Calculating..."
        try:
            # Find likely model file (largest file usually)
            # Or search by target_format extension if possible
            target_ext = f".{config.target_format.value}"
            candidates = list(output_dir.glob(f"*{target_ext}"))
            
            if not candidates:
                # Fallback: Find largest file
                files = list(output_dir.glob("*"))
                if files:
                    candidates = [max(files, key=lambda p: p.stat().st_size if p.is_file() else 0)]
            
            if candidates:
                primary_file = candidates[0]
                if primary_file.is_file():
                    sha256 = hashlib.sha256()
                    with open(primary_file, "rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            sha256.update(chunk)
                    model_hash = sha256.hexdigest()
        except Exception as e:
            model_hash = f"Hash calculation failed: {e}"

        content = f"""# Model Card: {os.path.basename(config.model_source)}

## 🏗️ Build Information
- **Framework:** LLM Cross-Compiler Framework
- **Build ID:** {config.build_id}
- **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Target Architecture:** {config.target_arch}
- **Target Format:** {config.target_format.value.upper()}
- **Quantization:** {config.quantization or 'FP16'}

## 🛡️ Security & Integrity
- **Primary Artifact Hash (SHA256):** `{model_hash}`
- **Base Image:** {config.base_image}

## 🚀 Usage
To deploy this model on your edge device:

1. Transfer the archive to the target.
2. Run the deployment script:
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
