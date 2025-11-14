#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Core Framework Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Central framework coordination and lifecycle management.
Handles framework initialization, configuration, and cross-component coordination.
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import threading
import queue
import time

import yaml
import docker
from packaging import version

from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory, check_command_exists, safe_json_load


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class FrameworkInfo:
    """Framework metadata and status information"""
    version: str
    build_date: str
    git_commit: Optional[str] = None
    installation_path: Optional[str] = None
    config_path: Optional[str] = None
    docker_available: bool = False
    targets_count: int = 0
    active_builds: int = 0


@dataclass
class SystemRequirements:
    """System requirements for framework operation"""
    min_python_version: str = "3.10"
    min_docker_version: str = "20.10"
    min_memory_gb: int = 8
    min_disk_gb: int = 20
    required_commands: List[str] = None
    
    def __post_init__(self):
        if self.required_commands is None:
            self.required_commands = ["docker", "docker-compose", "git"]


@dataclass
class FrameworkConfig:
    """Complete framework configuration"""
    # Core paths
    targets_dir: str = "targets"
    models_dir: str = "models"
    output_dir: str = "output"
    configs_dir: str = "configs"
    cache_dir: str = "cache"
    logs_dir: str = "logs"
    
    # Framework settings
    log_level: str = "INFO"
    max_concurrent_builds: int = 2
    build_timeout: int = 3600
    auto_cleanup: bool = True
    
    # Docker settings
    docker_registry: str = "ghcr.io"
    docker_namespace: str = "llm-framework"
    default_build_args: Dict[str, str] = None
    
    # GUI settings
    gui_theme: str = "dark"
    gui_auto_refresh: bool = True
    gui_refresh_interval: int = 30
    
    # API settings
    api_enabled: bool = False
    api_port: int = 8000
    api_host: str = "0.0.0.0"
    
    def __post_init__(self):
        if self.default_build_args is None:
            self.default_build_args = {
                "BUILD_JOBS": "4",
                "PYTHON_VERSION": "3.11"
            }


# ============================================================================
# FRAMEWORK MANAGER
# ============================================================================

class FrameworkManager:
    """
    Central framework manager coordinating all framework components.
    
    Responsibilities:
    - Framework initialization and configuration
    - System requirements validation
    - Component lifecycle management
    - Global state coordination
    - Error handling and recovery
    """
    
    def __init__(self, config: Optional[Union[Dict[str, Any], FrameworkConfig]] = None):
        """
        Initialize the framework manager.
        
        Args:
            config: Framework configuration (dict or FrameworkConfig object)
        """
        self.logger = get_logger(__name__)
        self._lock = threading.Lock()
        self._initialized = False
        self._shutdown_event = threading.Event()
        
        # Initialize configuration
        if isinstance(config, dict):
            self.config = FrameworkConfig(**config)
        elif isinstance(config, FrameworkConfig):
            self.config = config
        else:
            self.config = FrameworkConfig()
        
        # Framework info
        self.info = FrameworkInfo(
            version="1.0.0",
            build_date=datetime.now().isoformat(),
            installation_path=str(Path(__file__).parent.parent.parent)
        )
        
        # Component registry
        self._components: Dict[str, Any] = {}
        self._event_queue = queue.Queue()
        
        # State tracking
        self._build_counter = 0
        self._active_builds: Dict[str, Dict[str, Any]] = {}
        
        self.logger.info(f"Framework Manager initialized (version {self.info.version})")
    
    def initialize(self) -> bool:
        """
        Initialize the framework and all components.
        
        Returns:
            bool: True if initialization successful
            
        Raises:
            FrameworkError: If initialization fails
        """
        with self._lock:
            if self._initialized:
                self.logger.warning("Framework already initialized")
                return True
            
            try:
                self.logger.info("Initializing LLM Cross-Compiler Framework...")
                
                # Step 1: Validate system requirements
                self._validate_system_requirements()
                
                # Step 2: Setup directories
                self._setup_directories()
                
                # Step 3: Load configuration
                self._load_extended_configuration()
                
                # Step 4: Initialize Docker
                self._initialize_docker()
                
                # Step 5: Register core components
                self._register_core_components()
                
                # Step 6: Validate framework installation
                self._validate_installation()
                
                self._initialized = True
                self.logger.info("Framework initialization completed successfully")
                return True
                
            except Exception as e:
                self.logger.error(f"Framework initialization failed: {e}")
                raise FrameworkError(f"Initialization failed: {e}") from e
    
    def shutdown(self):
        """Gracefully shutdown the framework and all components"""
        with self._lock:
            if not self._initialized:
                return
            
            self.logger.info("Shutting down framework...")
            self._shutdown_event.set()
            
            # Stop all active builds
            self._stop_all_builds()
            
            # Shutdown components
            self._shutdown_components()
            
            # Cleanup resources
            self._cleanup_resources()
            
            self._initialized = False
            self.logger.info("Framework shutdown completed")
    
    def get_info(self) -> FrameworkInfo:
        """Get current framework information"""
        # Update dynamic info
        self.info.docker_available = self._check_docker_availability()
        self.info.targets_count = self._count_available_targets()
        self.info.active_builds = len(self._active_builds)
        
        return self.info
    
    def get_config(self) -> FrameworkConfig:
        """Get current framework configuration"""
        return self.config
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        Update framework configuration.
        
        Args:
            updates: Configuration updates to apply
            
        Returns:
            bool: True if update successful
        """
        try:
            # Validate updates
            for key, value in updates.items():
                if not hasattr(self.config, key):
                    raise ValidationError(f"Unknown configuration key: {key}")
            
            # Apply updates
            for key, value in updates.items():
                setattr(self.config, key, value)
                self.logger.debug(f"Config updated: {key} = {value}")
            
            # Persist configuration if needed
            self._persist_configuration()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration update failed: {e}")
            return False
    
    def register_component(self, name: str, component: Any):
        """Register a framework component"""
        with self._lock:
            self._components[name] = component
            self.logger.debug(f"Component registered: {name}")
    
    def get_component(self, name: str) -> Optional[Any]:
        """Get a registered component"""
        return self._components.get(name)
    
    def validate_target(self, target_name: str) -> Dict[str, Any]:
        """
        Validate a hardware target configuration.
        
        Args:
            target_name: Name of the target to validate
            
        Returns:
            dict: Validation result with 'valid' bool and 'errors' list
        """
        try:
            target_path = Path(self.config.targets_dir) / target_name
            
            if not target_path.exists():
                return {
                    "valid": False,
                    "errors": [f"Target directory does not exist: {target_path}"]
                }
            
            errors = []
            
            # Check required files
            required_files = [
                "target.yml",
                "Dockerfile",
                "modules/source_module.sh",
                "modules/config_module.sh", 
                "modules/convert_module.sh",
                "modules/target_module.sh"
            ]
            
            for required_file in required_files:
                file_path = target_path / required_file
                if not file_path.exists():
                    errors.append(f"Missing required file: {required_file}")
                elif required_file.endswith('.sh') and not os.access(file_path, os.X_OK):
                    errors.append(f"Script not executable: {required_file}")
            
            # Validate target.yml
            target_yml = target_path / "target.yml"
            if target_yml.exists():
                try:
                    with open(target_yml, 'r') as f:
                        target_config = yaml.safe_load(f)
                    
                    # Check required sections
                    required_sections = ["metadata", "supported_boards", "docker", "modules"]
                    for section in required_sections:
                        if section not in target_config:
                            errors.append(f"Missing required section in target.yml: {section}")
                    
                except yaml.YAMLError as e:
                    errors.append(f"Invalid YAML in target.yml: {e}")
            
            # Validate Dockerfile
            dockerfile = target_path / "Dockerfile"
            if dockerfile.exists():
                try:
                    with open(dockerfile, 'r') as f:
                        dockerfile_content = f.read()
                    
                    # Basic Dockerfile validation
                    if not dockerfile_content.strip().startswith('FROM'):
                        errors.append("Dockerfile must start with FROM instruction")
                    
                    # Check for multi-stage build (our standard)
                    if ' AS ' not in dockerfile_content.upper():
                        errors.append("Dockerfile should use multi-stage build pattern")
                        
                except Exception as e:
                    errors.append(f"Error reading Dockerfile: {e}")
            
            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "target_path": str(target_path)
            }
            
        except Exception as e:
            self.logger.error(f"Target validation failed: {e}")
            return {
                "valid": False,
                "errors": [f"Validation error: {e}"]
            }
    
    def create_build_id(self) -> str:
        """Generate a unique build ID"""
        with self._lock:
            self._build_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"build_{timestamp}_{self._build_counter:04d}"
    
    def register_build(self, build_id: str, build_config: Dict[str, Any]):
        """Register an active build"""
        with self._lock:
            self._active_builds[build_id] = {
                "id": build_id,
                "config": build_config,
                "status": "queued",
                "start_time": datetime.now().isoformat(),
                "progress": 0
            }
            self.logger.info(f"Build registered: {build_id}")
    
    def update_build_status(self, build_id: str, status: str, progress: int = None):
        """Update build status"""
        with self._lock:
            if build_id in self._active_builds:
                self._active_builds[build_id]["status"] = status
                if progress is not None:
                    self._active_builds[build_id]["progress"] = progress
                if status in ["completed", "failed"]:
                    self._active_builds[build_id]["end_time"] = datetime.now().isoformat()
    
    def get_build_status(self, build_id: str) -> Optional[Dict[str, Any]]:
        """Get build status"""
        return self._active_builds.get(build_id)
    
    def list_builds(self) -> List[Dict[str, Any]]:
        """List all builds"""
        with self._lock:
            return list(self._active_builds.values())
    
    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================
    
    def _validate_system_requirements(self):
        """Validate system meets framework requirements"""
        requirements = SystemRequirements()
        
        # Check Python version
        current_python = f"{sys.version_info.major}.{sys.version_info.minor}"
        if version.parse(current_python) < version.parse(requirements.min_python_version):
            raise FrameworkError(
                f"Python {requirements.min_python_version}+ required, found {current_python}"
            )
        
        # Check required commands
        missing_commands = []
        for cmd in requirements.required_commands:
            if not check_command_exists(cmd):
                missing_commands.append(cmd)
        
        if missing_commands:
            raise FrameworkError(
                f"Required commands not found: {', '.join(missing_commands)}"
            )
        
        # Check Docker version
        try:
            result = subprocess.run(
                ["docker", "--version"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            docker_version_str = result.stdout.split()[2].rstrip(',')
            if version.parse(docker_version_str) < version.parse(requirements.min_docker_version):
                raise FrameworkError(
                    f"Docker {requirements.min_docker_version}+ required, found {docker_version_str}"
                )
        except subprocess.CalledProcessError:
            raise FrameworkError("Docker is not available or not functional")
        
        self.logger.info("System requirements validation passed")
    
    def _setup_directories(self):
        """Setup required framework directories"""
        directories = [
            self.config.targets_dir,
            self.config.models_dir,
            self.config.output_dir,
            self.config.configs_dir,
            self.config.cache_dir,
            self.config.logs_dir
        ]
        
        for directory in directories:
            path = Path(directory)
            try:
                ensure_directory(path)
                self.logger.debug(f"Directory ensured: {path}")
            except Exception as e:
                raise FrameworkError(f"Failed to create directory {path}: {e}")
    
    def _load_extended_configuration(self):
        """Load extended configuration from files"""
        # Try to load from various config file locations
        config_candidates = [
            Path(".env"),
            Path("config.yml"),
            Path("framework.yml"),
            Path(self.config.configs_dir) / "framework.yml"
        ]
        
        for config_file in config_candidates:
            if config_file.exists():
                try:
                    self._load_config_file(config_file)
                    self.info.config_path = str(config_file)
                    self.logger.info(f"Configuration loaded from: {config_file}")
                    break
                except Exception as e:
                    self.logger.warning(f"Failed to load config from {config_file}: {e}")
    
    def _load_config_file(self, config_path: Path):
        """Load configuration from a specific file"""
        if config_path.suffix in ['.yml', '.yaml']:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
        elif config_path.suffix == '.json':
            config_data = safe_json_load(config_path)
        elif config_path.name == '.env':
            # Simple .env parsing
            config_data = {}
            with open(config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config_data[key.lower()] = value
        else:
            raise ValueError(f"Unsupported config file format: {config_path}")
        
        # Apply configuration updates
        if config_data:
            self.update_config(config_data)
    
    def _initialize_docker(self):
        """Initialize Docker client and validate"""
        try:
            docker_client = docker.from_env()
            docker_client.ping()
            self.register_component("docker_client", docker_client)
            self.info.docker_available = True
            self.logger.info("Docker client initialized successfully")
        except Exception as e:
            self.logger.error(f"Docker initialization failed: {e}")
            self.info.docker_available = False
            # Don't raise here - framework can work without Docker for some operations
    
    def _register_core_components(self):
        """Register core framework components"""
        # Components will be registered by their respective modules
        # This method is a placeholder for future component registration
        pass
    
    def _validate_installation(self):
        """Validate framework installation completeness"""
        # Check for required target templates
        template_path = Path(self.config.targets_dir) / "_template"
        if not template_path.exists():
            self.logger.warning("Template target not found - community contributions may be limited")
        
        # Check for at least one working target
        targets_found = self._count_available_targets()
        if targets_found == 0:
            self.logger.warning("No valid targets found - framework functionality limited")
        else:
            self.logger.info(f"Found {targets_found} valid targets")
    
    def _check_docker_availability(self) -> bool:
        """Check if Docker is available"""
        docker_client = self.get_component("docker_client")
        if not docker_client:
            return False
        
        try:
            docker_client.ping()
            return True
        except:
            return False
    
    def _count_available_targets(self) -> int:
        """Count available valid targets"""
        targets_dir = Path(self.config.targets_dir)
        if not targets_dir.exists():
            return 0
        
        count = 0
        for target_dir in targets_dir.iterdir():
            if target_dir.is_dir() and target_dir.name != "_template":
                target_yml = target_dir / "target.yml"
                if target_yml.exists():
                    count += 1
        
        return count
    
    def _stop_all_builds(self):
        """Stop all active builds"""
        for build_id in list(self._active_builds.keys()):
            try:
                self.update_build_status(build_id, "stopped")
                self.logger.info(f"Build stopped: {build_id}")
            except Exception as e:
                self.logger.error(f"Failed to stop build {build_id}: {e}")
    
    def _shutdown_components(self):
        """Shutdown all registered components"""
        for name, component in self._components.items():
            try:
                if hasattr(component, 'close'):
                    component.close()
                elif hasattr(component, 'shutdown'):
                    component.shutdown()
                self.logger.debug(f"Component shutdown: {name}")
            except Exception as e:
                self.logger.error(f"Failed to shutdown component {name}: {e}")
    
    def _cleanup_resources(self):
        """Cleanup framework resources"""
        # Clear component registry
        self._components.clear()
        
        # Clear active builds
        self._active_builds.clear()
        
        # Clear event queue
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except queue.Empty:
                break
    
    def _persist_configuration(self):
        """Persist current configuration to file"""
        config_file = Path(self.config.configs_dir) / "framework.yml"
        try:
            ensure_directory(config_file.parent)
            with open(config_file, 'w') as f:
                yaml.dump(asdict(self.config), f, default_flow_style=False)
            self.logger.debug(f"Configuration persisted to: {config_file}")
        except Exception as e:
            self.logger.error(f"Failed to persist configuration: {e}")


# ============================================================================
# EXCEPTIONS
# ============================================================================

class FrameworkError(Exception):
    """Base exception for framework errors"""
    pass


class FrameworkInitializationError(FrameworkError):
    """Exception raised during framework initialization"""
    pass


class FrameworkConfigurationError(FrameworkError):
    """Exception raised for configuration errors"""
    pass


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_framework_info() -> Dict[str, Any]:
    """Get framework information without full initialization"""
    return {
        "version": "1.0.0",
        "name": "LLM Cross-Compiler Framework",
        "description": "Professional cross-compilation for edge AI",
        "repository": "https://github.com/llm-framework/llm-cross-compiler-framework",
        "license": "MIT",
        "python_requirements": ">=3.10",
        "docker_requirements": ">=20.10"
    }


def create_default_config() -> FrameworkConfig:
    """Create a default framework configuration"""
    return FrameworkConfig()


def validate_framework_installation(install_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Validate framework installation without full initialization.
    
    Args:
        install_path: Path to framework installation (default: current directory)
        
    Returns:
        dict: Validation result with status and details
    """
    if install_path is None:
        install_path = Path.cwd()
    
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "install_path": str(install_path)
    }
    
    # Check required files
    required_files = [
        "pyproject.toml",
        "orchestrator/__init__.py",
        "orchestrator/main.py",
        "orchestrator/cli.py"
    ]
    
    for file_path in required_files:
        full_path = install_path / file_path
        if not full_path.exists():
            result["errors"].append(f"Missing required file: {file_path}")
            result["valid"] = False
    
    # Check for targets directory
    targets_dir = install_path / "targets"
    if not targets_dir.exists():
        result["warnings"].append("No targets directory found")
    else:
        # Count valid targets
        target_count = 0
        for target_dir in targets_dir.iterdir():
            if target_dir.is_dir() and (target_dir / "target.yml").exists():
                target_count += 1
        
        if target_count == 0:
            result["warnings"].append("No valid targets found")
        else:
            result["target_count"] = target_count
    
    return result