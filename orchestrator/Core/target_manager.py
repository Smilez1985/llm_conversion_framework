#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Target Manager (v2.1 Hybrid)
DIREKTIVE: Goldstandard.
MERGE: Kombiniert ursprüngliche Target-Discovery-Logik mit neuem Hardware-Profiling.
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

# --- DATA MODELS (Original) ---

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
    cmake_toolchain_file: str = ""
    env_vars: Dict[str, str] = field(default_factory=dict)
    available: bool = False

@dataclass
class TargetConfiguration:
    name: str
    target_arch: str
    status: TargetStatus
    version: str = "1.0.0"
    maintainer: str = "Community"
    description: str = ""
    target_dir: str = ""
    modules_dir: str = ""
    configs_dir: str = ""
    available_modules: List[str] = field(default_factory=list)
    docker_image: str = ""
    supported_formats: List[str] = field(default_factory=list)
    
@dataclass
class TargetRegistry:
    targets: Dict[str, TargetConfiguration] = field(default_factory=dict)
    
    def get_target(self, name: str) -> Optional[TargetConfiguration]:
        return self.targets.get(name)
    
    def list_available_targets(self) -> List[TargetConfiguration]:
        return list(self.targets.values())

# --- MANAGER CLASS (Merged) ---

class TargetManager:
    def __init__(self, framework_manager):
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        self.config = framework_manager.config
        
        # Pfade
        # Wir nutzen framework_manager.info.installation_path nicht zwingend, 
        # da config.targets_dir jetzt oft absolut ist (durch Installer v2.16).
        self.targets_dir = Path(self.config.targets_dir)
        self.profiles_dir = self.targets_dir / "profiles"
        
        self.registry = TargetRegistry()
        self._initialized = False
        
        self._ensure_directories()

    def initialize(self) -> bool:
        """Initialisiert den Manager und entdeckt Targets."""
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
        if not self.profiles_dir.exists():
            self.profiles_dir.mkdir(parents=True, exist_ok=True)

    # --- TARGET DISCOVERY (Original Logic) ---

    def _discover_targets(self):
        if not self.targets_dir.exists(): return
        
        self.registry.targets.clear()
        
        for td in self.targets_dir.iterdir():
            # Ignoriere _template, profiles Ordner und hidden files
            if not td.is_dir() or td.name.startswith('_') or td.name.startswith('.') or td.name == "profiles": 
                continue
            
            try:
                cfg = self._load_target_configuration(td)
                if cfg: 
                    self.registry.targets[cfg.name] = cfg
                    self.logger.debug(f"Loaded target: {cfg.name}")
            except Exception as e:
                self.logger.error(f"Failed to load {td.name}: {e}")

    def _load_target_configuration(self, target_dir: Path) -> Optional[TargetConfiguration]:
        yml = target_dir / "target.yml"
        if not yml.exists(): return None
        
        try:
            with open(yml, 'r') as f: data = yaml.safe_load(f)
            meta = data.get('metadata', {})
            
            config = TargetConfiguration(
                name=target_dir.name, # Folder name as ID
                target_arch=meta.get('architecture_family', 'unknown'),
                status=TargetStatus.AVAILABLE,
                version=meta.get('version', '1.0.0'),
                maintainer=meta.get('maintainer', 'Community'),
                description=meta.get('description', ''),
                target_dir=str(target_dir),
                modules_dir=str(target_dir / "modules"),
                configs_dir=str(target_dir / "configs")
            )
            
            if Path(config.modules_dir).exists():
                config.available_modules = [f.name for f in Path(config.modules_dir).glob("*.sh")]
            
            d_cfg = data.get('docker', {})
            config.docker_image = d_cfg.get('image_name', '')
            
            return config
        except Exception as e:
            self.logger.error(f"Load error {target_dir.name}: {e}")
            return None

    def list_available_targets(self) -> List[str]:
        if not self._initialized: self.initialize()
        return list(self.registry.targets.keys())

    def get_target_info(self, target_name: str) -> Dict[str, Any]:
        t = self.registry.get_target(target_name)
        if t: return asdict(t)
        return {"error": "Target not found"}

    def refresh_targets(self) -> bool:
        try:
            self._discover_targets()
            return True
        except Exception as e:
            self.logger.error(f"Refresh failed: {e}")
            return False

    # --- HARDWARE PROFILE MANAGEMENT (New Feature v2.0) ---

    def import_hardware_profile(self, probe_file_path: Path, profile_name: str) -> bool:
        """
        Importiert eine target_hardware_config.txt (vom Probe-Skript),
        parst sie und speichert sie als benanntes JSON-Profil.
        """
        probe_file = Path(probe_file_path)
        if not probe_file.exists():
            self.logger.error(f"Probe file not found: {probe_file}")
            return False

        profile_data = {
            "name": profile_name,
            "imported_at": str(datetime.now().isoformat()),
            "raw_data": {}
        }

        try:
            # Parsing der Shell-Variablen (KEY=VALUE)
            with open(probe_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        profile_data["raw_data"][key.strip()] = val.strip()
            
            # Speichern als JSON
            dest_file = self.profiles_dir / f"{profile_name}.json"
            with open(dest_file, "w") as f:
                json.dump(profile_data, f, indent=2)
            
            self.logger.info(f"Hardware profile '{profile_name}' imported successfully.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to import hardware profile: {e}")
            return False

    def list_hardware_profiles(self) -> List[str]:
        """Listet alle gespeicherten Hardware-Profile auf."""
        profiles = []
        if self.profiles_dir.exists():
            for item in self.profiles_dir.glob("*.json"):
                profiles.append(item.stem) # Dateiname ohne .json
        return sorted(profiles)

    def get_hardware_profile(self, profile_name: str) -> Optional[Dict]:
        """Lädt ein spezifisches Hardware-Profil."""
        profile_file = self.profiles_dir / f"{profile_name}.json"
        if profile_file.exists():
            try:
                with open(profile_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to load profile {profile_name}: {e}")
        return None

    def get_docker_flags_for_profile(self, profile_name: str) -> List[str]:
        """
        Generiert Docker --device Flags basierend auf einem Profil.
        Dies ist die Single Source of Truth für Deployment-Argumente.
        """
        profile = self.get_hardware_profile(profile_name)
        if not profile: return []
        
        data = profile.get("raw_data", {})
        flags = []

        # Rockchip NPU
        if data.get("NPU_VENDOR") == "Rockchip":
            flags.append("--device /dev/rknpu")
            flags.append("--device /dev/rga")
        
        # Hailo NPU
        if data.get("NPU_VENDOR") == "Hailo":
            flags.append("--device /dev/hailo0")
            
        # NVIDIA GPU
        if data.get("SUPPORTS_CUDA") == "ON":
            flags.append("--gpus all")
            
        # Intel NPU/GPU
        if data.get("SUPPORTS_INTEL_XPU") == "ON":
            flags.append("--device /dev/dri")

        return flags
