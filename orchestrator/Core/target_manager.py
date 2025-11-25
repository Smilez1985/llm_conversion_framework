#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Target Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
"""

import os
import sys
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

import yaml
from orchestrator.utils.logging import get_logger
from orchestrator.utils.helpers import ensure_directory

# Note: Enums removed for modularity. Strings used instead.

@dataclass
class ToolchainInfo:
    name: str
    type: str # "gcc_cross", "native", etc.
    version: str
    path: str = ""
    cmake_toolchain_file: str = ""
    env_vars: Dict[str, str] = field(default_factory=dict)
    available: bool = False

@dataclass
class HardwareProfile:
    name: str
    target_arch: str
    cpu_architecture: str = ""
    cpu_cores: int = 4
    memory_mb: int = 4096
    cflags: List[str] = field(default_factory=list)
    cxxflags: List[str] = field(default_factory=list)
    optimization_level: str = "O3"
    
    def __post_init__(self):
        pass

@dataclass
class TargetConfiguration:
    name: str # e.g. "Rockchip"
    target_arch: str # e.g. "aarch64"
    status: str = "available"
    version: str = "1.0.0"
    maintainer: str = "Community"
    description: str = ""
    target_dir: str = ""
    modules_dir: str = ""
    available_modules: List[str] = field(default_factory=list)
    hardware_profiles: List[HardwareProfile] = field(default_factory=list)
    default_profile: Optional[str] = None
    docker_image: str = ""
    supported_formats: List[str] = field(default_factory=list)
    supported_quantizations: List[str] = field(default_factory=list)

@dataclass
class TargetRegistry:
    targets: Dict[str, TargetConfiguration] = field(default_factory=dict)
    
    def get_target(self, name: str) -> Optional[TargetConfiguration]:
        return self.targets.get(name)
    
    def list_available_targets(self) -> List[TargetConfiguration]:
        return list(self.targets.values())

class TargetManager:
    def __init__(self, framework_manager):
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        self.config = framework_manager.config
        self.targets_dir = Path(framework_manager.info.installation_path) / self.config.targets_dir
        self.registry = TargetRegistry()
        self._initialized = False
        self._ensure_directories()

    def initialize(self) -> bool:
        try:
            self.logger.info("Initializing Target Manager...")
            self._discover_targets()
            self._initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Target Manager initialization failed: {e}")
            return False

    def _ensure_directories(self):
        if not self.targets_dir.exists():
            self.targets_dir.mkdir(parents=True, exist_ok=True)

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
            
            config = TargetConfiguration(
                name=target_dir.name, # Use directory name as ID
                target_arch=meta.get('architecture_family', 'unknown'),
                version=meta.get('version', '1.0.0'),
                maintainer=meta.get('maintainer', 'Community'),
                description=meta.get('description', ''),
                target_dir=str(target_dir),
                modules_dir=str(target_dir / "modules")
            )
            
            # Load modules
            if Path(config.modules_dir).exists():
                config.available_modules = [f.name for f in Path(config.modules_dir).glob("*.sh")]
            
            # Load Docker info
            d_cfg = data.get('docker', {})
            config.docker_image = d_cfg.get('image_name', '')
            
            # Load Formats
            feats = data.get('features', {})
            config.supported_formats = feats.get('formats', [])
            config.supported_quantizations = feats.get('quantizations', [])
            
            return config
        except Exception as e:
            self.logger.error(f"Load error {target_dir.name}: {e}")
            return None

    def list_available_targets(self) -> List[str]:
        """Returns list of target names (folder names)"""
        if not self._initialized: self.initialize()
        return list(self.registry.targets.keys())

    def get_target_info(self, target_name: str) -> Dict[str, Any]:
        t = self.registry.get_target(target_name)
        if t: return asdict(t)
        return {"error": "Target not found"}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_target_manager(framework_manager) -> TargetManager:
    tm = TargetManager(framework_manager)
    if not tm.initialize(): raise Exception("Init failed")
    return tm
