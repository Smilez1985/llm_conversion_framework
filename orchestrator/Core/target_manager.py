#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Target Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Hardware target management and cross-compilation toolchain coordination.
Specializes in RK3566 MVP with extensible architecture for additional targets.
Container-native with Poetry+VENV, robust hardware detection.

Key Responsibilities:
- Hardware target discovery and validation
- Cross-compilation toolchain management
- CMake toolchain generation for different architectures
- Hardware-specific optimization profiles
- Board-specific configuration management
- Docker container integration for builds
- Target-specific module coordination
"""

import os
import sys
import json
import logging
import subprocess
import platform
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import tempfile
import re

import yaml
from packaging import version

from orchestrator.Core.builder import TargetArch, ModelFormat
from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory, check_command_exists, safe_json_load


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class TargetStatus(Enum):
    """Target availability status"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"          # Some modules missing
    UNCONFIGURED = "unconfigured" # Needs setup
    ERROR = "error"


class ToolchainType(Enum):
    """Cross-compilation toolchain types"""
    GCC_CROSS = "gcc_cross"
    CLANG_CROSS = "clang_cross"
    CUSTOM = "custom"
    NATIVE = "native"


class OptimizationProfile(Enum):
    """Hardware optimization profiles"""
    GENERIC = "generic"
    PERFORMANCE = "performance"
    SIZE = "size"
    POWER = "power"
    CUSTOM = "custom"


class BoardVariant(Enum):
    """Specific board variants for targets"""
    RK3566_GENERIC = "rk3566_generic"
    RK3566_QUARTZ64 = "rk3566_quartz64"
    RK3566_PINETAB2 = "rk3566_pinetab2"
    RK3588_ROCK5B = "rk3588_rock5b" 
    RASPBERRY_PI4 = "raspberry_pi4"
    RASPBERRY_PI5 = "raspberry_pi5"


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ToolchainInfo:
    """Cross-compilation toolchain information"""
    name: str
    type: ToolchainType
    version: str
    prefix: str = ""
    path: str = ""
    
    # Compiler paths
    cc: str = ""
    cxx: str = ""
    ar: str = ""
    strip: str = ""
    objcopy: str = ""
    
    # CMake configuration
    cmake_toolchain_file: str = ""
    cmake_system_name: str = ""
    cmake_system_processor: str = ""
    
    # Environment variables
    env_vars: Dict[str, str] = field(default_factory=dict)
    
    # Validation
    available: bool = False
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class HardwareProfile:
    """Hardware-specific optimization profile"""
    name: str
    target_arch: TargetArch
    board_variant: Optional[BoardVariant] = None
    
    # CPU specifications
    cpu_architecture: str = ""
    cpu_features: List[str] = field(default_factory=list)
    cpu_cores: int = 4
    cpu_freq_mhz: int = 1800
    
    # Memory specifications
    memory_mb: int = 4096
    memory_type: str = "LPDDR4"
    memory_bandwidth_gbps: float = 17.0
    
    # Compilation flags
    cflags: List[str] = field(default_factory=list)
    cxxflags: List[str] = field(default_factory=list)
    ldflags: List[str] = field(default_factory=list)
    
    # Optimization settings
    optimization_level: str = "O3"
    enable_neon: bool = False
    enable_fp16: bool = False
    enable_int8: bool = True
    
    # Build parameters
    parallel_jobs: int = 4
    memory_limit_mb: int = 2048
    
    def __post_init__(self):
        """Set architecture-specific defaults"""
        if not self.cflags and self.target_arch == TargetArch.RK3566:
            self.cflags = [
                "-march=armv8-a+crc+crypto",
                "-mtune=cortex-a55",
                "-mfpu=neon-fp-armv8",
                "-mfloat-abi=hard"
            ]
            self.enable_neon = True
            self.enable_fp16 = True


@dataclass
class TargetConfiguration:
    """Complete target configuration"""
    name: str
    target_arch: TargetArch
    status: TargetStatus
    
    # Metadata
    version: str = "1.0.0"
    maintainer: str = "Framework Team"
    description: str = ""
    
    # Paths
    target_dir: str = ""
    modules_dir: str = ""
    configs_dir: str = ""
    
    # Available modules
    available_modules: List[str] = field(default_factory=list)
    required_modules: List[str] = field(default_factory=lambda: [
        "source_module.sh", "config_module.sh", "convert_module.sh", "target_module.sh"
    ])
    
    # Toolchain information
    toolchain: Optional[ToolchainInfo] = None
    
    # Hardware profiles
    hardware_profiles: List[HardwareProfile] = field(default_factory=list)
    default_profile: Optional[str] = None
    
    # Docker configuration
    docker_image: str = ""
    docker_build_args: Dict[str, str] = field(default_factory=dict)
    
    # Supported features
    supported_formats: List[ModelFormat] = field(default_factory=list)
    supported_quantizations: List[str] = field(default_factory=list)
    
    # Validation results
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    last_validated: Optional[datetime] = None


@dataclass
class TargetRegistry:
    """Registry of all available targets"""
    targets: Dict[str, TargetConfiguration] = field(default_factory=dict)
    last_discovery: Optional[datetime] = None
    discovery_errors: List[str] = field(default_factory=list)
    
    def get_target(self, name: str) -> Optional[TargetConfiguration]:
        """Get target configuration by name"""
        return self.targets.get(name)
    
    def list_available_targets(self) -> List[TargetConfiguration]:
        """List all available targets"""
        return [t for t in self.targets.values() if t.status == TargetStatus.AVAILABLE]
    
    def list_targets_by_arch(self, arch: TargetArch) -> List[TargetConfiguration]:
        """List targets by architecture"""
        return [t for t in self.targets.values() if t.target_arch == arch]


# ============================================================================
# TARGET MANAGER CLASS
# ============================================================================

class TargetManager:
    """
    Hardware Target Manager for LLM Cross-Compilation Framework.
    
    Manages hardware targets, cross-compilation toolchains, and build configurations.
    Specializes in RK3566 MVP with extensible architecture for additional targets.
    
    Responsibilities:
    - Target discovery and validation
    - Toolchain detection and setup
    - Hardware profile management
    - CMake toolchain generation
    - Cross-compilation environment setup
    - Docker container integration
    - Module coordination for target-specific builds
    """
    
    def __init__(self, framework_manager):
        """
        Initialize Target Manager.
        
        Args:
            framework_manager: Reference to FrameworkManager
        """
        self.framework_manager = framework_manager
        self.logger = get_logger(__name__)
        
        # Configuration
        self.config = framework_manager.config
        self.targets_dir = Path(framework_manager.info.installation_path) / self.config.targets_dir
        
        # State
        self.registry = TargetRegistry()
        self._initialized = False
        
        # Paths
        self.cache_dir = Path(framework_manager.info.installation_path) / self.config.cache_dir
        self.toolchains_dir = self.cache_dir / "toolchains"
        self.profiles_dir = self.cache_dir / "profiles"
        
        # Ensure directories exist
        self._ensure_directories()
        
        self.logger.info("Target Manager initialized")
    
    def initialize(self) -> bool:
        """
        Initialize target manager and discover targets.
        
        Returns:
            bool: True if initialization successful
        """
        try:
            self.logger.info("Initializing Target Manager...")
            
            # Step 1: Discover available targets
            self._discover_targets()
            
            # Step 2: Validate discovered targets
            self._validate_all_targets()
            
            # Step 3: Setup default toolchains
            self._setup_default_toolchains()
            
            # Step 4: Load hardware profiles
            self._load_hardware_profiles()
            
            # Step 5: Generate CMake toolchains
            self._generate_cmake_toolchains()
            
            self._initialized = True
            self.logger.info("Target Manager initialization completed")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Target Manager initialization failed: {e}")
            return False
    
    def _ensure_directories(self):
        """Ensure required directories exist"""
        directories = [
            self.targets_dir,
            self.cache_dir,
            self.toolchains_dir,
            self.profiles_dir,
            self.cache_dir / "cmake"
        ]
        
        for directory in directories:
            ensure_directory(directory)
            self.logger.debug(f"Directory ensured: {directory}")
    
    def _discover_targets(self):
        """Discover available hardware targets"""
        self.logger.info("Discovering hardware targets...")
        
        if not self.targets_dir.exists():
            self.logger.warning(f"Targets directory not found: {self.targets_dir}")
            return
        
        discovered_count = 0
        
        for target_dir in self.targets_dir.iterdir():
            if not target_dir.is_dir() or target_dir.name.startswith('_'):
                continue
            
            try:
                target_config = self._load_target_configuration(target_dir)
                if target_config:
                    self.registry.targets[target_config.name] = target_config
                    discovered_count += 1
                    self.logger.debug(f"Target discovered: {target_config.name}")
                    
            except Exception as e:
                error_msg = f"Failed to load target {target_dir.name}: {e}"
                self.registry.discovery_errors.append(error_msg)
                self.logger.error(error_msg)
        
        self.registry.last_discovery = datetime.now()
        self.logger.info(f"Target discovery completed: {discovered_count} targets found")
    
    def _load_target_configuration(self, target_dir: Path) -> Optional[TargetConfiguration]:
        """
        Load target configuration from directory.
        
        Args:
            target_dir: Target directory path
            
        Returns:
            TargetConfiguration: Loaded configuration or None
        """
        target_yml = target_dir / "target.yml"
        if not target_yml.exists():
            self.logger.warning(f"Target configuration not found: {target_yml}")
            return None
        
        try:
            with open(target_yml, 'r') as f:
                target_data = yaml.safe_load(f)
            
            # Extract metadata
            metadata = target_data.get('metadata', {})
            
            # Map architecture string to enum
            arch_str = metadata.get('architecture', target_dir.name)
            target_arch = self._string_to_target_arch(arch_str)
            
            if not target_arch:
                self.logger.error(f"Unknown architecture: {arch_str}")
                return None
            
            # Create configuration
            config = TargetConfiguration(
                name=target_dir.name,
                target_arch=target_arch,
                status=TargetStatus.UNCONFIGURED,
                version=metadata.get('version', '1.0.0'),
                maintainer=metadata.get('maintainer', 'Framework Team'),
                description=metadata.get('description', f'Target for {arch_str}'),
                target_dir=str(target_dir),
                modules_dir=str(target_dir / "modules"),
                configs_dir=str(target_dir / "configs")
            )
            
            # Load available modules
            modules_dir = target_dir / "modules"
            if modules_dir.exists():
                config.available_modules = [
                    f.name for f in modules_dir.glob("*.sh") 
                    if f.is_file() and os.access(f, os.X_OK)
                ]
            
            # Load Docker configuration
            docker_config = target_data.get('docker', {})
            config.docker_image = docker_config.get('base_image', 'debian:bookworm-slim')
            config.docker_build_args = docker_config.get('build_args', {})
            
            # Load supported features
            features = target_data.get('features', {})
            config.supported_formats = [
                self._string_to_model_format(fmt) 
                for fmt in features.get('formats', ['gguf', 'onnx'])
                if self._string_to_model_format(fmt)
            ]
            config.supported_quantizations = features.get('quantizations', ['q4_0', 'q8_0'])
            
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to load target configuration {target_dir.name}: {e}")
            return None
    
    def _string_to_target_arch(self, arch_str: str) -> Optional[TargetArch]:
        """Convert string to TargetArch enum"""
        arch_mapping = {
            "arm64": TargetArch.ARM64,
            "armv7": TargetArch.ARMV7,
            "x86_64": TargetArch.X86_64,
            "rk3566": TargetArch.RK3566,
            "rk3588": TargetArch.RK3588,
            "raspberry_pi": TargetArch.RASPBERRY_PI
        }
        return arch_mapping.get(arch_str.lower())
    
    def _string_to_model_format(self, format_str: str) -> Optional[ModelFormat]:
        """Convert string to ModelFormat enum"""
        format_mapping = {
            "hf": ModelFormat.HUGGINGFACE,
            "huggingface": ModelFormat.HUGGINGFACE,
            "gguf": ModelFormat.GGUF,
            "onnx": ModelFormat.ONNX,
            "tflite": ModelFormat.TENSORFLOW_LITE,
            "pytorch": ModelFormat.PYTORCH_MOBILE
        }
        return format_mapping.get(format_str.lower())

    def _generate_cmake_toolchain_file(self, target_config: TargetConfiguration, 
                                       cmake_dir: Path) -> Path:
        """
        Generate CMake toolchain file for target.
        
        Args:
            target_config: Target configuration
            cmake_dir: Directory for CMake files
            
        Returns:
            Path: Generated toolchain file path
        """
        toolchain = target_config.toolchain
        if not toolchain:
            raise RuntimeError(f"No toolchain available for {target_config.name}")
        
        toolchain_filename = f"{target_config.name}-toolchain.cmake"
        toolchain_file = cmake_dir / toolchain_filename
        
        # Get default hardware profile
        default_profile = None
        if target_config.hardware_profiles and target_config.default_profile:
            default_profile = next(
                (p for p in target_config.hardware_profiles if p.name == target_config.default_profile),
                target_config.hardware_profiles[0]
            )
        
        # Generate CMake toolchain content
        cmake_content = self._generate_cmake_toolchain_content(target_config, toolchain, default_profile)
        
        # Write toolchain file
        with open(toolchain_file, 'w') as f:
            f.write(cmake_content)
        
        self.logger.debug(f"CMake toolchain generated: {toolchain_file}")
        return toolchain_file
    
    def _generate_cmake_toolchain_content(self, target_config: TargetConfiguration,
                                         toolchain: ToolchainInfo,
                                         hardware_profile: Optional[HardwareProfile]) -> str:
        """Generate CMake toolchain file content"""
        
        lines = [
            "# CMake toolchain file for LLM Cross-Compiler Framework",
            f"# Target: {target_config.name}",
            f"# Architecture: {target_config.target_arch.value}",
            f"# Generated: {datetime.now().isoformat()}",
            "",
            "# System configuration",
            f'set(CMAKE_SYSTEM_NAME "{toolchain.cmake_system_name}")',
            f'set(CMAKE_SYSTEM_PROCESSOR "{toolchain.cmake_system_processor}")',
            ""
        ]
        
        # Compiler configuration
        if toolchain.type != ToolchainType.CUSTOM:
            lines.extend([
                "# Compiler configuration",
                f'set(CMAKE_C_COMPILER "{toolchain.cc}")',
                f'set(CMAKE_CXX_COMPILER "{toolchain.cxx}")',
                f'set(CMAKE_AR "{toolchain.ar}")',
                f'set(CMAKE_STRIP "{toolchain.strip}")',
                ""
            ])
            
            if toolchain.objcopy:
                lines.append(f'set(CMAKE_OBJCOPY "{toolchain.objcopy}")')
                lines.append("")
        
        # Cross-compilation specific settings
        if toolchain.type in [ToolchainType.GCC_CROSS, ToolchainType.CLANG_CROSS]:
            lines.extend([
                "# Cross-compilation settings",
                "set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)",
                "set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)",
                "set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)",
                "set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)",
                ""
            ])
        
        # Hardware-specific compilation flags
        if hardware_profile:
            lines.extend([
                "# Hardware-specific optimization flags",
                f"# Profile: {hardware_profile.name}",
                f"# CPU: {hardware_profile.cpu_architecture}",
                ""
            ])
            
            # C flags
            if hardware_profile.cflags:
                cflags = " ".join(hardware_profile.cflags)
                lines.append(f'set(CMAKE_C_FLAGS "{cflags} -O{hardware_profile.optimization_level[-1]}")')
            
            # C++ flags
            cxxflags = hardware_profile.cxxflags or hardware_profile.cflags
            if cxxflags:
                cxxflags_str = " ".join(cxxflags)
                lines.append(f'set(CMAKE_CXX_FLAGS "{cxxflags_str} -O{hardware_profile.optimization_level[-1]}")')
            
            # Linker flags
            if hardware_profile.ldflags:
                ldflags = " ".join(hardware_profile.ldflags)
                lines.append(f'set(CMAKE_EXE_LINKER_FLAGS "{ldflags}")')
                lines.append(f'set(CMAKE_SHARED_LINKER_FLAGS "{ldflags}")')
            
            lines.append("")
            
            # Feature-specific definitions
            if hardware_profile.enable_neon:
                lines.append('add_definitions(-DENABLE_NEON=1)')
            if hardware_profile.enable_fp16:
                lines.append('add_definitions(-DENABLE_FP16=1)')
            if hardware_profile.enable_int8:
                lines.append('add_definitions(-DENABLE_INT8=1)')
            
            lines.append("")
        
        # Target-specific settings
        if target_config.target_arch == TargetArch.RK3566:
            lines.extend([
                "# RK3566-specific settings",
                'add_definitions(-DRK3566=1)',
                'add_definitions(-DARM64=1)',
                'add_definitions(-DCORTEX_A55=1)',
                ""
            ])
        
        # Build configuration
        lines.extend([
            "# Build configuration",
            "set(CMAKE_BUILD_TYPE Release)",
            "set(CMAKE_POSITION_INDEPENDENT_CODE ON)",
            ""
        ])
        
        return "\n".join(lines)
    
    # ========================================================================
    # PUBLIC API METHODS
    # ========================================================================
    
    def list_available_targets(self) -> List[TargetArch]:
        """
        List all available target architectures.
        
        Returns:
            List[TargetArch]: Available target architectures
        """
        if not self._initialized:
            self.initialize()
        
        available_targets = []
        for target_config in self.registry.list_available_targets():
            if target_config.target_arch not in available_targets:
                available_targets.append(target_config.target_arch)
        
        return available_targets
    
    def get_target_info(self, target_arch: TargetArch) -> Dict[str, Any]:
        """
        Get detailed information about a target.
        
        Args:
            target_arch: Target architecture
            
        Returns:
            dict: Target information
        """
        if not self._initialized:
            self.initialize()
        
        # Find target configuration
        target_config = None
        for config in self.registry.targets.values():
            if config.target_arch == target_arch:
                target_config = config
                break
        
        if not target_config:
            return {
                "available": False,
                "error": f"Target {target_arch.value} not found"
            }
        
        # Prepare target information
        target_info = {
            "available": target_config.status == TargetStatus.AVAILABLE,
            "target_arch": target_arch.value,
            "name": target_config.name,
            "status": target_config.status.value,
            "version": target_config.version,
            "maintainer": target_config.maintainer,
            "description": target_config.description,
            "target_path": target_config.target_dir,
            "modules": target_config.available_modules,
            "required_modules": target_config.required_modules,
            "supported_formats": [fmt.value for fmt in target_config.supported_formats],
            "supported_quantizations": target_config.supported_quantizations,
            "docker_image": target_config.docker_image
        }
        
        # Add toolchain information
        if target_config.toolchain:
            toolchain = target_config.toolchain
            target_info["toolchain"] = {
                "name": toolchain.name,
                "type": toolchain.type.value,
                "version": toolchain.version,
                "available": toolchain.available,
                "cmake_toolchain_file": toolchain.cmake_toolchain_file
            }
        
        # Add hardware profiles
        if target_config.hardware_profiles:
            target_info["hardware_profiles"] = []
            for profile in target_config.hardware_profiles:
                profile_info = {
                    "name": profile.name,
                    "cpu_architecture": profile.cpu_architecture,
                    "cpu_cores": profile.cpu_cores,
                    "cpu_freq_mhz": profile.cpu_freq_mhz,
                    "memory_mb": profile.memory_mb,
                    "optimization_level": profile.optimization_level,
                    "enable_neon": profile.enable_neon,
                    "enable_fp16": profile.enable_fp16,
                    "enable_int8": profile.enable_int8
                }
                if profile.board_variant:
                    profile_info["board_variant"] = profile.board_variant.value
                
                target_info["hardware_profiles"].append(profile_info)
            
            target_info["default_profile"] = target_config.default_profile
        
        # Add validation information
        if target_config.validation_errors:
            target_info["validation_errors"] = target_config.validation_errors
        if target_config.validation_warnings:
            target_info["validation_warnings"] = target_config.validation_warnings
        if target_config.last_validated:
            target_info["last_validated"] = target_config.last_validated.isoformat()
        
        return target_info
    
    def validate_target(self, target_name: str) -> Dict[str, Any]:
        """
        Validate a specific target.
        
        Args:
            target_name: Target name to validate
            
        Returns:
            dict: Validation result
        """
        if not self._initialized:
            self.initialize()
        
        target_config = self.registry.get_target(target_name)
        if not target_config:
            return {
                "valid": False,
                "errors": [f"Target '{target_name}' not found"]
            }
        
        try:
            # Re-validate target
            self._validate_target_configuration(target_config)
            
            return {
                "valid": target_config.status == TargetStatus.AVAILABLE,
                "status": target_config.status.value,
                "errors": target_config.validation_errors,
                "warnings": target_config.validation_warnings,
                "target_path": target_config.target_dir,
                "last_validated": target_config.last_validated.isoformat() if target_config.last_validated else None
            }
            
        except ValidationError as e:
            return {
                "valid": False,
                "errors": [str(e)],
                "target_path": target_config.target_dir
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Validation error: {e}"],
                "target_path": target_config.target_dir
            }
    
    def get_hardware_profile(self, target_arch: TargetArch, profile_name: str = None) -> Optional[HardwareProfile]:
        """
        Get hardware profile for target.
        
        Args:
            target_arch: Target architecture
            profile_name: Specific profile name (uses default if None)
            
        Returns:
            HardwareProfile: Hardware profile or None
        """
        target_config = None
        for config in self.registry.targets.values():
            if config.target_arch == target_arch:
                target_config = config
                break
        
        if not target_config or not target_config.hardware_profiles:
            return None
        
        if profile_name:
            # Find specific profile
            for profile in target_config.hardware_profiles:
                if profile.name == profile_name:
                    return profile
        else:
            # Return default profile
            if target_config.default_profile:
                for profile in target_config.hardware_profiles:
                    if profile.name == target_config.default_profile:
                        return profile
            
            # Return first profile if no default set
            if target_config.hardware_profiles:
                return target_config.hardware_profiles[0]
        
        return None
    
    def get_toolchain_info(self, target_arch: TargetArch) -> Optional[ToolchainInfo]:
        """
        Get toolchain information for target.
        
        Args:
            target_arch: Target architecture
            
        Returns:
            ToolchainInfo: Toolchain information or None
        """
        target_config = None
        for config in self.registry.targets.values():
            if config.target_arch == target_arch:
                target_config = config
                break
        
        return target_config.toolchain if target_config else None
    
    def detect_host_hardware(self) -> Dict[str, Any]:
        """
        Detect host hardware capabilities.
        
        Returns:
            dict: Host hardware information
        """
        host_info = {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "architecture": platform.architecture()[0],
            "cpu_count": os.cpu_count(),
            "detected_features": []
        }
        
        # Detect specific CPU features
        try:
            # Check for specific instruction sets
            if platform.machine().lower() in ['x86_64', 'amd64']:
                host_info["detected_features"].extend(["sse", "sse2"])
                
                # Try to detect AVX
                try:
                    result = subprocess.run(
                        ["grep", "-q", "avx", "/proc/cpuinfo"],
                        capture_output=True
                    )
                    if result.returncode == 0:
                        host_info["detected_features"].append("avx")
                except:
                    pass
            
            elif platform.machine().lower() in ['aarch64', 'arm64']:
                host_info["detected_features"].extend(["neon"])
                
                # Try to detect additional ARM features
                try:
                    with open('/proc/cpuinfo', 'r') as f:
                        cpuinfo = f.read()
                    
                    if 'fp' in cpuinfo:
                        host_info["detected_features"].append("fp")
                    if 'asimd' in cpuinfo:
                        host_info["detected_features"].append("asimd")
                    if 'aes' in cpuinfo:
                        host_info["detected_features"].append("aes")
                        
                except:
                    pass
        
        except Exception as e:
            self.logger.warning(f"Failed to detect host hardware features: {e}")
        
        return host_info
    
    def suggest_optimal_target(self, model_size_mb: int = 0) -> Optional[TargetArch]:
        """
        Suggest optimal target based on model size and available hardware.
        
        Args:
            model_size_mb: Model size in MB
            
        Returns:
            TargetArch: Suggested target architecture or None
        """
        available_targets = self.list_available_targets()
        if not available_targets:
            return None
        
        # Get host hardware info
        host_info = self.detect_host_hardware()
        host_arch = host_info["machine"].lower()
        
        # Priority-based suggestions
        suggestions = []
        
        # If host is ARM64, prefer ARM64 targets
        if host_arch in ['aarch64', 'arm64']:
            if TargetArch.RK3566 in available_targets:
                suggestions.append((TargetArch.RK3566, 10))  # High priority for RK3566 MVP
            if TargetArch.ARM64 in available_targets:
                suggestions.append((TargetArch.ARM64, 8))
        
        # If host is x86_64, can build for any target
        if host_arch in ['x86_64', 'amd64']:
            if TargetArch.RK3566 in available_targets:
                suggestions.append((TargetArch.RK3566, 9))  # Slightly lower but still high
            if TargetArch.ARM64 in available_targets:
                suggestions.append((TargetArch.ARM64, 7))
            if TargetArch.X86_64 in available_targets:
                suggestions.append((TargetArch.X86_64, 6))
        
        # Consider model size for memory-constrained targets
        if model_size_mb > 7000:  # Large models (>7GB)
            # Prefer targets with more memory
            suggestions = [(arch, score-2) for arch, score in suggestions if arch != TargetArch.ARMV7]
        
        # Sort by priority and return best match
        if suggestions:
            suggestions.sort(key=lambda x: x[1], reverse=True)
            return suggestions[0][0]
        
        # Default: return first available target
        return available_targets[0] if available_targets else None
    
    def create_target_build_environment(self, target_arch: TargetArch, 
                                       profile_name: str = None) -> Dict[str, Any]:
        """
        Create build environment configuration for target.
        
        Args:
            target_arch: Target architecture
            profile_name: Hardware profile name
            
        Returns:
            dict: Build environment configuration
        """
        target_config = None
        for config in self.registry.targets.values():
            if config.target_arch == target_arch:
                target_config = config
                break
        
        if not target_config:
            raise ValueError(f"Target {target_arch.value} not available")
        
        if target_config.status != TargetStatus.AVAILABLE:
            raise ValueError(f"Target {target_arch.value} not available (status: {target_config.status.value})")
        
        # Get hardware profile
        hardware_profile = self.get_hardware_profile(target_arch, profile_name)
        if not hardware_profile:
            raise ValueError(f"No hardware profile available for {target_arch.value}")
        
        # Create build environment
        build_env = {
            "target": {
                "name": target_config.name,
                "arch": target_arch.value,
                "status": target_config.status.value
            },
            "hardware_profile": {
                "name": hardware_profile.name,
                "cpu_cores": hardware_profile.cpu_cores,
                "memory_mb": hardware_profile.memory_mb,
                "parallel_jobs": hardware_profile.parallel_jobs,
                "optimization_level": hardware_profile.optimization_level
            },
            "docker": {
                "base_image": target_config.docker_image,
                "build_args": target_config.docker_build_args
            },
            "modules": {
                "available": target_config.available_modules,
                "modules_dir": target_config.modules_dir
            }
        }
        
        # Add toolchain information
        if target_config.toolchain:
            toolchain = target_config.toolchain
            build_env["toolchain"] = {
                "type": toolchain.type.value,
                "cmake_toolchain_file": toolchain.cmake_toolchain_file,
                "env_vars": toolchain.env_vars
            }
        
        # Add compilation flags
        build_env["compilation"] = {
            "cflags": hardware_profile.cflags,
            "cxxflags": hardware_profile.cxxflags,
            "ldflags": hardware_profile.ldflags,
            "features": {
                "neon": hardware_profile.enable_neon,
                "fp16": hardware_profile.enable_fp16,
                "int8": hardware_profile.enable_int8
            }
        }
        
        return build_env

    def refresh_targets(self) -> bool:
        """
        Refresh target discovery and validation.
        
        Returns:
            bool: True if refresh successful
        """
        try:
            self.logger.info("Refreshing target discovery...")
            
            # Clear current registry
            self.registry = TargetRegistry()
            
            # Re-discover and validate targets
            self._discover_targets()
            self._validate_all_targets()
            self._setup_default_toolchains()
            self._load_hardware_profiles()
            self._generate_cmake_toolchains()
            
            self.logger.info("Target refresh completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Target refresh failed: {e}")
            return False
    
    def cleanup_cache(self) -> bool:
        """
        Clean up target manager cache.
        
        Returns:
            bool: True if cleanup successful
        """
        try:
            self.logger.info("Cleaning up target manager cache...")
            
            # Clean up generated CMake files
            cmake_dir = self.cache_dir / "cmake"
            if cmake_dir.exists():
                for cmake_file in cmake_dir.glob("*-toolchain.cmake"):
                    try:
                        cmake_file.unlink()
                        self.logger.debug(f"Removed CMake file: {cmake_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove CMake file {cmake_file}: {e}")
            
            # Clean up temporary toolchain files
            toolchains_temp = self.toolchains_dir / "temp"
            if toolchains_temp.exists():
                shutil.rmtree(toolchains_temp)
                self.logger.debug("Removed temporary toolchain files")
            
            # Clean up old profile cache
            profiles_cache = self.profiles_dir / "cache"
            if profiles_cache.exists():
                shutil.rmtree(profiles_cache)
                self.logger.debug("Removed profile cache")
            
            self.logger.info("Target manager cache cleanup completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Cache cleanup failed: {e}")
            return False
    
    def export_target_registry(self, output_file: Path) -> bool:
        """
        Export target registry to file.
        
        Args:
            output_file: Output file path
            
        Returns:
            bool: True if export successful
        """
        try:
            registry_data = {
                "metadata": {
                    "export_time": datetime.now().isoformat(),
                    "framework_version": "1.0.0",
                    "last_discovery": self.registry.last_discovery.isoformat() if self.registry.last_discovery else None
                },
                "targets": {},
                "discovery_errors": self.registry.discovery_errors
            }
            
            # Export target configurations
            for target_name, target_config in self.registry.targets.items():
                target_data = {
                    "name": target_config.name,
                    "target_arch": target_config.target_arch.value,
                    "status": target_config.status.value,
                    "version": target_config.version,
                    "maintainer": target_config.maintainer,
                    "description": target_config.description,
                    "available_modules": target_config.available_modules,
                    "supported_formats": [fmt.value for fmt in target_config.supported_formats],
                    "supported_quantizations": target_config.supported_quantizations,
                    "validation_errors": target_config.validation_errors,
                    "validation_warnings": target_config.validation_warnings,
                    "last_validated": target_config.last_validated.isoformat() if target_config.last_validated else None
                }
                
                # Add toolchain info
                if target_config.toolchain:
                    target_data["toolchain"] = {
                        "name": target_config.toolchain.name,
                        "type": target_config.toolchain.type.value,
                        "version": target_config.toolchain.version,
                        "available": target_config.toolchain.available
                    }
                
                # Add hardware profiles
                if target_config.hardware_profiles:
                    target_data["hardware_profiles"] = []
                    for profile in target_config.hardware_profiles:
                        profile_data = {
                            "name": profile.name,
                            "cpu_architecture": profile.cpu_architecture,
                            "cpu_cores": profile.cpu_cores,
                            "cpu_freq_mhz": profile.cpu_freq_mhz,
                            "memory_mb": profile.memory_mb,
                            "optimization_level": profile.optimization_level,
                            "enable_neon": profile.enable_neon,
                            "enable_fp16": profile.enable_fp16,
                            "enable_int8": profile.enable_int8
                        }
                        target_data["hardware_profiles"].append(profile_data)
                
                registry_data["targets"][target_name] = target_data
            
            # Write to file
            ensure_directory(output_file.parent)
            with open(output_file, 'w') as f:
                json.dump(registry_data, f, indent=2)
            
            self.logger.info(f"Target registry exported to: {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export target registry: {e}")
            return False
    
    def get_system_requirements(self, target_arch: TargetArch) -> Dict[str, Any]:
        """
        Get system requirements for building on target.
        
        Args:
            target_arch: Target architecture
            
        Returns:
            dict: System requirements
        """
        requirements = {
            "docker": True,
            "min_memory_gb": 4,
            "min_disk_gb": 20,
            "recommended_memory_gb": 8,
            "recommended_disk_gb": 50,
            "required_tools": ["git", "cmake"],
            "optional_tools": ["ccache", "ninja"],
            "cross_compiler": None
        }
        
        # Target-specific requirements
        if target_arch == TargetArch.RK3566:
            requirements.update({
                "min_memory_gb": 6,
                "recommended_memory_gb": 12,
                "cross_compiler": "aarch64-linux-gnu-gcc",
                "required_tools": requirements["required_tools"] + ["qemu-user-static"],
                "architecture_notes": [
                    "RK3566 is ARM64-based (Cortex-A55)",
                    "Supports NEON SIMD instructions",
                    "Hardware FP16 support available",
                    "4GB RAM recommended for medium models"
                ]
            })
        elif target_arch == TargetArch.ARM64:
            requirements.update({
                "cross_compiler": "aarch64-linux-gnu-gcc",
                "required_tools": requirements["required_tools"] + ["qemu-user-static"]
            })
        elif target_arch == TargetArch.ARMV7:
            requirements.update({
                "min_memory_gb": 3,
                "cross_compiler": "arm-linux-gnueabihf-gcc",
                "required_tools": requirements["required_tools"] + ["qemu-user-static"],
                "architecture_notes": [
                    "Limited to 32-bit addressing",
                    "Consider model size limitations"
                ]
            })
        elif target_arch == TargetArch.X86_64:
            requirements.update({
                "cross_compiler": None,  # Native compilation
                "min_memory_gb": 8,
                "recommended_memory_gb": 16
            })
        
        return requirements
    
    def shutdown(self):
        """Shutdown target manager and cleanup resources"""
        self.logger.info("Shutting down Target Manager...")
        
        try:
            # No active resources to clean up for now
            # Future: Stop any background monitoring threads
            
            self._initialized = False
            self.logger.info("Target Manager shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during Target Manager shutdown: {e}")
            
    def _setup_default_toolchains(self):
        """Setup default toolchains if not already configured"""
        # Placeholder implementation - logic would check for installed cross-compilers
        pass
        
    def _load_hardware_profiles(self):
        """Load hardware profiles from disk"""
        # Placeholder implementation - logic would load profiles from profiles_dir
        pass
        
    def _generate_cmake_toolchains(self):
        """Generate CMake toolchain files for all available targets"""
        # Placeholder implementation - calls _generate_cmake_toolchain_file for each target
        pass
        
    def _validate_target_configuration(self, target_config: TargetConfiguration):
        """Internal validation logic for a target configuration"""
        # Placeholder implementation - checks required files and settings
        pass


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_target_manager(framework_manager) -> TargetManager:
    """
    Create and initialize target manager.
    
    Args:
        framework_manager: Framework manager instance
        
    Returns:
        TargetManager: Initialized target manager
    """
    target_manager = TargetManager(framework_manager)
    
    if not target_manager.initialize():
        raise TargetManagerError("Failed to initialize target manager")
    
    return target_manager


def validate_target_requirements() -> Dict[str, Any]:
    """
    Validate system requirements for target management.
    
    Returns:
        dict: Validation results
    """
    requirements = {
        "docker": False,
        "cmake": False,
        "git": False,
        "cross_compilers": {},
        "errors": [],
        "warnings": []
    }
    
    # Check Docker
    if check_command_exists("docker"):
        requirements["docker"] = True
    else:
        requirements["errors"].append("Docker not available")
    
    # Check CMake
    if check_command_exists("cmake"):
        requirements["cmake"] = True
    else:
        requirements["warnings"].append("CMake not available - will limit build capabilities")
    
    # Check Git
    if check_command_exists("git"):
        requirements["git"] = True
    else:
        requirements["warnings"].append("Git not available - may limit source management")
    
    # Check cross-compilers
    cross_compilers = {
        "aarch64-linux-gnu-gcc": "ARM64/RK3566 cross-compilation",
        "arm-linux-gnueabihf-gcc": "ARMv7 cross-compilation"
    }
    
    for compiler, description in cross_compilers.items():
        if check_command_exists(compiler):
            requirements["cross_compilers"][compiler] = {
                "available": True,
                "description": description
            }
        else:
            requirements["cross_compilers"][compiler] = {
                "available": False,
                "description": description
            }
            requirements["warnings"].append(f"{compiler} not available - {description} will use Docker")
    
    return requirements
