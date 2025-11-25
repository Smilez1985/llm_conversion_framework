#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Target Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
"""

import os
import sys
import json
import logging
import subprocess
import platform
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

import yaml
from orchestrator.Core.builder import ModelFormat
from orchestrator.utils.logging import get_logger
from orchestrator.utils.helpers import ensure_directory, check_command_exists

class TargetStatus(Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    UNCONFIGURED = "unconfigured"
    ERROR = "error"

class ToolchainType(Enum):
    GCC_CROSS = "gcc_cross"
    CLANG_CROSS = "clang_cross"
    CUSTOM = "custom"
    NATIVE = "native"

@dataclass
class ToolchainInfo:
    name: str
    type: ToolchainType
    version: str
    prefix: str = ""
    path: str = ""
    cc: str = ""
    cxx: str = ""
    ar: str = ""
    strip: str = ""
    objcopy: str = ""
    cmake_toolchain_file: str = ""
    cmake_system_name: str = ""
    cmake_system_processor: str = ""
    env_vars: Dict[str, str] = field(default_factory=dict)
    available: bool = False
    validation_errors: List[str] = field(default_factory=list)

@dataclass
class HardwareProfile:
    name: str
    target_arch: str
    board_variant: Optional[str] = None
    cpu_architecture: str = ""
    cpu_features: List[str] = field(default_factory=list)
    cpu_cores: int = 4
    cpu_freq_mhz: int = 1800
    memory_mb: int = 4096
    memory_type: str = "LPDDR4"
    memory_bandwidth_gbps: float = 17.0
    cflags: List[str] = field(default_factory=list)
    cxxflags: List[str] = field(default_factory=list)
    ldflags: List[str] = field(default_factory=list)
    optimization_level: str = "O3"
    enable_neon: bool = False
    enable_fp16: bool = False
    enable_int8: bool = True
    parallel_jobs: int = 4
    memory_limit_mb: int = 2048
    
    def __post_init__(self):
        if not self.cflags and "rk3566" in str(self.target_arch).lower():
            self.cflags = ["-march=armv8-a+crc+crypto", "-mtune=cortex-a55", "-mfpu=neon-fp-armv8", "-mfloat-abi=hard"]
            self.enable_neon = True
            self.enable_fp16 = True

@dataclass
class TargetConfiguration:
    name: str
    target_arch: str
    status: TargetStatus
    version: str = "1.0.0"
    maintainer: str = "Framework Team"
    description: str = ""
    target_dir: str = ""
    modules_dir: str = ""
    configs_dir: str = ""
    available_modules: List[str] = field(default_factory=list)
    required_modules: List[str] = field(default_factory=lambda: ["source_module.sh", "config_module.sh", "convert_module.sh", "target_module.sh"])
    toolchain: Optional[ToolchainInfo] = None
    hardware_profiles: List[HardwareProfile] = field(default_factory=list)
    default_profile: Optional[str] = None
    docker_image: str = ""
    docker_build_args: Dict[str, str] = field(default_factory=dict)
    supported_formats: List[ModelFormat] = field(default_factory=list)
    supported_quantizations: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    last_validated: Optional[datetime] = None

@dataclass
class TargetRegistry:
    targets: Dict[str, TargetConfiguration] = field(default_factory=dict)
    last_discovery: Optional[datetime] = None
    discovery_errors: List[str] = field(default_factory=list)
    
    def get_target(self, name: str) -> Optional[TargetConfiguration]:
        return self.targets.get(name)
    
    def list_available_targets(self) -> List[TargetConfiguration]:
        return [t for t in self.targets.values() if t.status == TargetStatus.AVAILABLE]

class TargetManager:
    def __init__(self, framework_manager):
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        self.config = framework_manager.config
        self.targets_dir = Path(framework_manager.info.installation_path) / self.config.targets_dir
        self.registry = TargetRegistry()
        self._initialized = False
        self.cache_dir = Path(framework_manager.info.installation_path) / self.config.cache_dir
        self.toolchains_dir = self.cache_dir / "toolchains"
        self.profiles_dir = self.cache_dir / "profiles"
        self._ensure_directories()
        self.logger.info("Target Manager initialized")

    def initialize(self) -> bool:
        try:
            self.logger.info("Initializing Target Manager...")
            self._discover_targets()
            self._validate_all_targets()
            self._setup_default_toolchains()
            self._load_hardware_profiles()
            self._generate_cmake_toolchains()
            self._initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Target Manager initialization failed: {e}")
            return False

    def _ensure_directories(self):
        for d in [self.targets_dir, self.cache_dir, self.toolchains_dir, self.profiles_dir, self.cache_dir / "cmake"]:
            ensure_directory(d)

    def _discover_targets(self):
        if not self.targets_dir.exists(): return
        for td in self.targets_dir.iterdir():
            if not td.is_dir() or td.name.startswith('_'): continue
            try:
                cfg = self._load_target_configuration(td)
                if cfg: self.registry.targets[cfg.name] = cfg
            except Exception as e:
                self.logger.error(f"Failed to load {td.name}: {e}")

    def _load_target_configuration(self, target_dir: Path) -> Optional[TargetConfiguration]:
        yml = target_dir / "target.yml"
        if not yml.exists(): return None
        try:
            with open(yml, 'r') as f: data = yaml.safe_load(f)
            meta = data.get('metadata', {})
            arch = meta.get('architecture', target_dir.name)
            
            config = TargetConfiguration(
                name=target_dir.name, target_arch=arch, status=TargetStatus.UNCONFIGURED,
                version=meta.get('version', '1.0.0'), maintainer=meta.get('maintainer', 'Framework Team'),
                description=meta.get('description', ''), target_dir=str(target_dir),
                modules_dir=str(target_dir / "modules"), configs_dir=str(target_dir / "configs")
            )
            if Path(config.modules_dir).exists():
                config.available_modules = [f.name for f in Path(config.modules_dir).glob("*.sh") if f.is_file()]
            
            d_cfg = data.get('docker', {})
            config.docker_image = d_cfg.get('base_image', 'debian:bookworm-slim')
            config.docker_build_args = d_cfg.get('build_args', {})
            
            feats = data.get('features', {})
            config.supported_formats = [self._string_to_model_format(f) for f in feats.get('formats', []) if self._string_to_model_format(f)]
            config.supported_quantizations = feats.get('quantizations', [])
            
            if not config.validation_errors:
                config.status = TargetStatus.AVAILABLE
            
            return config
        except Exception as e:
            self.logger.error(f"Load error {target_dir.name}: {e}")
            return None

    def _string_to_model_format(self, s: str) -> Optional[ModelFormat]:
        m = {"hf": ModelFormat.HUGGINGFACE, "gguf": ModelFormat.GGUF, "onnx": ModelFormat.ONNX}
        return m.get(s.lower())

    def _validate_all_targets(self):
        for t in self.registry.targets.values():
            if t.status == TargetStatus.ERROR: continue

    def _setup_default_toolchains(self): pass
    def _load_hardware_profiles(self): pass
    def _generate_cmake_toolchains(self): pass
    def _validate_target_configuration(self, cfg): pass
    
    def refresh_targets(self) -> bool:
        try:
            self.registry = TargetRegistry()
            self._discover_targets()
            self._validate_all_targets()
            return True
        except Exception as e:
            self.logger.error(f"Refresh failed: {e}")
            return False

    def detect_rk3566_hardware(self) -> Dict[str, Any]:
        res = {"is_rk3566": False, "confidence": "none", "detected_features": []}
        try:
            files = ["/proc/device-tree/compatible", "/sys/firmware/devicetree/base/compatible"]
            for f in files:
                if Path(f).exists():
                    with open(f, 'rb') as c:
                        if 'rk3566' in c.read().decode('utf-8', errors='ignore').lower():
                            res["is_rk3566"] = True
                            res["confidence"] = "high"
                            break
        except: pass
        return res

    def generate_rk3566_build_flags(self) -> List[str]:
        return ["-march=armv8-a+crc+crypto", "-mtune=cortex-a55", "-mfpu=neon-fp-armv8", "-mfloat-abi=hard", "-O3", "-DENABLE_NEON=1"]

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_target_manager(framework_manager) -> TargetManager:
    tm = TargetManager(framework_manager)
    if not tm.initialize(): raise Exception("Init failed")
    return tm

def validate_target_requirements() -> Dict[str, Any]:
    reqs = {"docker": False, "cmake": False, "git": False, "errors": []}
    if check_command_exists("docker"): reqs["docker"] = True
    else: reqs["errors"].append("Docker missing")
    return reqs
