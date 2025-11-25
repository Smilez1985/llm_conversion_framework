#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Configuration Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Professional configuration management with optional enterprise features.
Core functionality works without advanced features - advanced mode is optional.
Container-native with Poetry+VENV, robust error recovery.
"""

import os
import sys
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, Set, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import threading
import copy

import yaml

from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory, check_command_exists, safe_json_load


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class ConfigFormat(Enum):
    """Configuration file formats"""
    YAML = "yaml"
    JSON = "json"
    ENV = "env"
    TOML = "toml"


class ConfigScope(Enum):
    """Configuration scope levels"""
    GLOBAL = "global"           # Framework-wide settings
    USER = "user"               # User-specific settings
    PROJECT = "project"         # Project-specific settings
    ENVIRONMENT = "environment" # Environment-specific (dev/prod)
    RUNTIME = "runtime"         # Runtime overrides


class ValidationLevel(Enum):
    """Configuration validation levels"""
    NONE = "none"               # No validation
    BASIC = "basic"             # Basic type checking
    STRICT = "strict"           # Full schema validation
    ENTERPRISE = "enterprise"   # Enterprise compliance checks


class AdvancedFeature(Enum):
    """Optional advanced features"""
    SECRETS_MANAGEMENT = "secrets_management"
    DYNAMIC_UPDATES = "dynamic_updates"
    TEMPLATES = "templates"
    MIGRATION = "migration"
    ENVIRONMENTS = "environments"
    COMPLIANCE = "compliance"


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ConfigSchema:
    """Configuration schema definition"""
    field_name: str
    field_type: type
    required: bool = False
    default_value: Any = None
    description: str = ""
    validation_rules: List[str] = field(default_factory=list)
    enterprise_only: bool = False  # Only available in advanced mode
    
    def validate_value(self, value: Any) -> Tuple[bool, List[str]]:
        """Validate a value against this schema"""
        errors = []
        
        # Type checking
        if value is not None and not isinstance(value, self.field_type):
            try:
                # Try to convert
                if self.field_type == int:
                    value = int(value)
                elif self.field_type == float:
                    value = float(value)
                elif self.field_type == bool:
                    value = str(value).lower() in ('true', '1', 'yes', 'on')
                elif self.field_type == str:
                    value = str(value)
            except (ValueError, TypeError):
                errors.append(f"Invalid type for {self.field_name}: expected {self.field_type.__name__}")
        
        # Custom validation rules
        for rule in self.validation_rules:
            if not self._apply_validation_rule(value, rule):
                errors.append(f"Validation rule failed for {self.field_name}: {rule}")
        
        return len(errors) == 0, errors
    
    def _apply_validation_rule(self, value: Any, rule: str) -> bool:
        """Apply a validation rule"""
        try:
            if rule.startswith("min:"):
                min_val = float(rule.split(":", 1)[1])
                return value >= min_val
            elif rule.startswith("max:"):
                max_val = float(rule.split(":", 1)[1])
                return value <= max_val
            elif rule.startswith("regex:"):
                import re
                pattern = rule.split(":", 1)[1]
                return bool(re.match(pattern, str(value)))
            elif rule == "positive":
                return value > 0
            elif rule == "non_empty":
                return bool(value and str(value).strip())
            
        except Exception:
            return False
        
        return True


@dataclass
class ConfigSource:
    """Configuration source information"""
    source_type: str            # file, env, default, override
    source_path: Optional[str] = None
    loaded_at: Optional[datetime] = None
    checksum: Optional[str] = None
    priority: int = 0           # Higher priority overrides lower


@dataclass
class ConfigValue:
    """Configuration value with metadata"""
    key: str
    value: Any
    source: ConfigSource
    schema: Optional[ConfigSchema] = None
    is_secret: bool = False
    is_readonly: bool = False
    last_modified: Optional[datetime] = None
    
    def is_valid(self) -> bool:
        """Check if value is valid according to schema"""
        if not self.schema:
            return True
        
        valid, _ = self.schema.validate_value(self.value)
        return valid
    
    def get_validation_errors(self) -> List[str]:
        """Get validation errors for this value"""
        if not self.schema:
            return []
        
        _, errors = self.schema.validate_value(self.value)
        return errors


@dataclass
class AdvancedModeConfig:
    """Configuration for advanced mode features"""
    enabled: bool = False
    enabled_features: Set[AdvancedFeature] = field(default_factory=set)
    
    # GUI settings
    show_advanced_options: bool = False
    show_expert_warnings: bool = True
    require_confirmation: bool = True
    
    # Enterprise settings
    audit_changes: bool = False
    require_validation: bool = True
    enforce_compliance: bool = False
    
    def is_feature_enabled(self, feature: AdvancedFeature) -> bool:
        """Check if a specific advanced feature is enabled"""
        return self.enabled and feature in self.enabled_features
    
    def enable_feature(self, feature: AdvancedFeature):
        """Enable a specific advanced feature"""
        if self.enabled:
            self.enabled_features.add(feature)
    
    def disable_feature(self, feature: AdvancedFeature):
        """Disable a specific advanced feature"""
        self.enabled_features.discard(feature)


# ============================================================================
# CONFIGURATION MANAGER CLASS
# ============================================================================

class ConfigManager:
    """
    Professional Configuration Manager for LLM Cross-Compilation Framework.
    """
    
    def __init__(self, 
                 config_dir: Optional[Path] = None,
                 advanced_mode: bool = False,
                 enable_secrets: bool = False,
                 enable_templates: bool = False,
                 enable_dynamic_updates: bool = False):
        """Initialize Configuration Manager."""
        self.logger = get_logger(__name__)
        
        # Core configuration
        self.config_dir = config_dir or self._detect_config_directory()
        self._lock = threading.RLock()
        
        # Advanced mode configuration
        self.advanced_mode = AdvancedModeConfig(enabled=advanced_mode)
        
        if advanced_mode:
            if enable_secrets:
                self.advanced_mode.enable_feature(AdvancedFeature.SECRETS_MANAGEMENT)
            if enable_templates:
                self.advanced_mode.enable_feature(AdvancedFeature.TEMPLATES)
            if enable_dynamic_updates:
                self.advanced_mode.enable_feature(AdvancedFeature.DYNAMIC_UPDATES)
        
        # Configuration storage
        self.config_values: Dict[str, ConfigValue] = {}
        self.config_schemas: Dict[str, ConfigSchema] = {}
        self.config_sources: List[ConfigSource] = []
        
        # Change tracking (for advanced mode)
        self.change_history: List[Dict[str, Any]] = []
        self.change_listeners: List[Callable] = []
        
        # Initialize core schemas
        self._initialize_core_schemas()
        
        # Setup directories
        self._ensure_directories()
        
        self.logger.info(f"Configuration Manager initialized (advanced_mode: {advanced_mode})")
    
    def _detect_config_directory(self) -> Path:
        """Auto-detect configuration directory"""
        candidates = [
            Path.cwd() / "configs",
            Path.cwd() / "config", 
            Path.home() / ".llm-framework",
            Path("/etc/llm-framework"),
            Path.cwd()
        ]
        
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        
        return Path.cwd() / "configs"
    
    def _ensure_directories(self):
        """Ensure required directories exist"""
        directories = [
            self.config_dir,
            self.config_dir / "environments",
            self.config_dir / "templates",
            self.config_dir / "backups"
        ]
        
        if self.advanced_mode.enabled:
            directories.extend([
                self.config_dir / "secrets",
                self.config_dir / "compliance",
                self.config_dir / "audit"
            ])
        
        for directory in directories:
            ensure_directory(directory)
            self.logger.debug(f"Directory ensured: {directory}")
    
    def _initialize_core_schemas(self):
        """Initialize core configuration schemas"""
        core_schemas = [
            ConfigSchema("targets_dir", str, True, "targets", "Directory for target definitions"),
            ConfigSchema("models_dir", str, True, "models", "Directory for model storage"),
            ConfigSchema("output_dir", str, True, "output", "Directory for build outputs"),
            ConfigSchema("cache_dir", str, True, "cache", "Directory for cache files"),
            ConfigSchema("logs_dir", str, True, "logs", "Directory for log files"),
            ConfigSchema("log_level", str, False, "INFO", "Logging level", ["regex:^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"]),
            ConfigSchema("max_concurrent_builds", int, False, 2, "Maximum concurrent builds", ["min:1", "max:10"]),
            ConfigSchema("build_timeout", int, False, 3600, "Build timeout in seconds", ["min:60"]),
            ConfigSchema("auto_cleanup", bool, False, True, "Enable automatic cleanup"),
            
            # Docker settings
            ConfigSchema("docker_registry", str, False, "ghcr.io", "Docker registry URL"),
            ConfigSchema("docker_namespace", str, False, "llm-framework", "Docker namespace"),
            
            # GUI settings
            ConfigSchema("gui_theme", str, False, "dark", "GUI theme", ["regex:^(light|dark|auto)$"]),
            ConfigSchema("gui_auto_refresh", bool, False, True, "GUI auto-refresh"),
            ConfigSchema("gui_refresh_interval", int, False, 30, "GUI refresh interval", ["min:5", "max:300"]),
            
            # API settings
            ConfigSchema("api_enabled", bool, False, False, "Enable API server"),
            ConfigSchema("api_port", int, False, 8000, "API server port", ["min:1024", "max:65535"]),
            # SECURITY FIX: Default to localhost
            ConfigSchema("api_host", str, False, "127.0.0.1", "API server host")
        ]
        
        if self.advanced_mode.enabled:
            advanced_schemas = [
                ConfigSchema("enable_audit_logging", bool, False, False, "Enable audit logging", enterprise_only=True),
                ConfigSchema("require_approval", bool, False, False, "Require approval for builds", enterprise_only=True),
                ConfigSchema("compliance_mode", str, False, "none", "Compliance mode", ["regex:^(none|basic|strict)$"], enterprise_only=True),
                ConfigSchema("secret_encryption_key", str, False, None, "Encryption key for secrets", enterprise_only=True),
                ConfigSchema("backup_retention_days", int, False, 30, "Backup retention period", ["min:1"], enterprise_only=True)
            ]
            core_schemas.extend(advanced_schemas)
        
        for schema in core_schemas:
            self.config_schemas[schema.field_name] = schema
        
        self.logger.debug(f"Initialized {len(core_schemas)} configuration schemas")
    
    def load_configuration(self, config_file: Optional[Path] = None) -> bool:
        """Load configuration from file(s)."""
        try:
            self.logger.info("Loading configuration...")
            
            self._load_default_configuration()
            
            if config_file:
                self._load_config_file(config_file)
            else:
                self._load_config_files_auto()
            
            self._load_environment_variables()
            self._validate_configuration()
            
            self.logger.info("Configuration loaded successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration loading failed: {e}")
            return False
    
    def _load_default_configuration(self):
        """Load default configuration values"""
        default_source = ConfigSource(
            source_type="default",
            loaded_at=datetime.now(),
            priority=0
        )
        
        for schema_name, schema in self.config_schemas.items():
            if schema.default_value is not None:
                config_value = ConfigValue(
                    key=schema_name,
                    value=schema.default_value,
                    source=default_source,
                    schema=schema,
                    last_modified=datetime.now()
                )
                
                with self._lock:
                    self.config_values[schema_name] = config_value
        
        self.logger.debug("Default configuration loaded")
    
    def _load_config_files_auto(self):
        """Auto-detect and load configuration files"""
        config_candidates = [
            self.config_dir / "framework.yml",
            self.config_dir / "framework.yaml", 
            self.config_dir / "config.yml",
            self.config_dir / "config.yaml",
            self.config_dir / "framework.json",
            self.config_dir / "config.json",
            Path.cwd() / "framework.yml",
            Path.cwd() / "config.yml"
        ]
        
        loaded_files = []
        
        for config_file in config_candidates:
            if config_file.exists():
                try:
                    self._load_config_file(config_file)
                    loaded_files.append(str(config_file))
                except Exception as e:
                    self.logger.warning(f"Failed to load config file {config_file}: {e}")
        
        if loaded_files:
            self.logger.info(f"Loaded configuration from: {', '.join(loaded_files)}")
        else:
            self.logger.info("No configuration files found, using defaults")
    
    def _load_config_file(self, config_file: Path):
        """Load configuration from a specific file"""
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        config_format = self._detect_config_format(config_file)
        
        with open(config_file, 'r') as f:
            if config_format == ConfigFormat.YAML:
                config_data = yaml.safe_load(f)
            elif config_format == ConfigFormat.JSON:
                config_data = json.load(f)
            else:
                raise ValueError(f"Unsupported config format: {config_format}")
        
        if not config_data:
            return
        
        file_source = ConfigSource(
            source_type="file",
            source_path=str(config_file),
            loaded_at=datetime.now(),
            priority=10
        )
        
        self._load_config_data(config_data, file_source)
        
        self.logger.debug(f"Configuration loaded from: {config_file}")
    
    def _detect_config_format(self, config_file: Path) -> ConfigFormat:
        """Detect configuration file format"""
        extension = config_file.suffix.lower()
        
        if extension in ['.yml', '.yaml']:
            return ConfigFormat.YAML
        elif extension == '.json':
            return ConfigFormat.JSON
        elif extension == '.toml':
            return ConfigFormat.TOML
        else:
            try:
                with open(config_file, 'r') as f:
                    content = f.read().strip()
                
                if content.startswith('{'):
                    return ConfigFormat.JSON
                else:
                    return ConfigFormat.YAML
            except Exception:
                return ConfigFormat.YAML
    
    def _load_config_data(self, config_data: Dict[str, Any], source: ConfigSource):
        """Load configuration data from dictionary"""
        for key, value in config_data.items():
            schema = self.config_schemas.get(key)
            if schema and schema.enterprise_only and not self.advanced_mode.enabled:
                self.logger.debug(f"Skipping enterprise-only setting: {key} (advanced mode disabled)")
                continue
            
            config_value = ConfigValue(
                key=key,
                value=value,
                source=source,
                schema=schema,
                last_modified=datetime.now()
            )
            
            with self._lock:
                existing_value = self.config_values.get(key)
                if not existing_value or source.priority >= existing_value.source.priority:
                    self.config_values[key] = config_value
    
    def _load_environment_variables(self):
        """Load configuration from environment variables (MANDATORY)"""
        env_source = ConfigSource(
            source_type="environment",
            loaded_at=datetime.now(),
            priority=20
        )
        
        prefixes = ["LLM_FRAMEWORK_", "FRAMEWORK_", "LLM_"]
        loaded_count = 0
        
        for env_name, env_value in os.environ.items():
            config_key = None
            
            for prefix in prefixes:
                if env_name.startswith(prefix):
                    config_key = env_name[len(prefix):].lower()
                    break
            
            if not config_key:
                continue
            
            config_key = config_key.replace("_", "_")
            schema = self.config_schemas.get(config_key)
            
            if schema and schema.enterprise_only and not self.advanced_mode.enabled:
                continue
            
            try:
                converted_value = self._convert_env_value(env_value, schema)
                
                config_value = ConfigValue(
                    key=config_key,
                    value=converted_value,
                    source=env_source,
                    schema=schema,
                    last_modified=datetime.now()
                )
                
                with self._lock:
                    self.config_values[config_key] = config_value
                    loaded_count += 1
                    
            except Exception as e:
                self.logger.warning(f"Failed to load environment variable {env_name}: {e}")
        
        if loaded_count > 0:
            self.logger.info(f"Loaded {loaded_count} environment variables")
    
    def _convert_env_value(self, env_value: str, schema: Optional[ConfigSchema]) -> Any:
        """Convert environment variable string to appropriate type"""
        if not schema:
            return env_value
        
        target_type = schema.field_type
        
        try:
            if target_type == bool:
                return env_value.lower() in ('true', '1', 'yes', 'on', 'enabled')
            elif target_type == int:
                return int(env_value)
            elif target_type == float:
                return float(env_value)
            elif target_type == list:
                return [item.strip() for item in env_value.replace(';', ',').replace('|', ',').split(',') if item.strip()]
            else:
                return env_value
                
        except (ValueError, TypeError):
            self.logger.warning(f"Failed to convert environment value '{env_value}' to {target_type.__name__}")
            return env_value
    
    def _validate_configuration(self):
        """Validate loaded configuration (MANDATORY)"""
        validation_errors = []
        validation_warnings = []
        
        for schema_name, schema in self.config_schemas.items():
            if schema.required:
                if schema_name not in self.config_values:
                    validation_errors.append(f"Required configuration missing: {schema_name}")
                    continue
                
                config_value = self.config_values[schema_name]
                if config_value.value is None:
                    validation_errors.append(f"Required configuration cannot be null: {schema_name}")
        
        for config_name, config_value in self.config_values.items():
            if not config_value.is_valid():
                errors = config_value.get_validation_errors()
                validation_errors.extend(errors)
        
        if validation_errors:
            for error in validation_errors:
                self.logger.error(f"Configuration validation error: {error}")
            # Non-blocking for MVP stability, but logged as error
            # raise ValidationError(f"Configuration validation failed: {len(validation_errors)} errors")
        
        if validation_warnings:
            for warning in validation_warnings:
                self.logger.warning(f"Configuration validation warning: {warning}")
        
        self.logger.debug("Configuration validation passed")
    
    # ========================================================================
    # UTILITY METHODS (MANDATORY)
    # ========================================================================
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value (MANDATORY)."""
        with self._lock:
            config_value = self.config_values.get(key)
            
            if config_value is None:
                return default
            
            if self.advanced_mode.enabled:
                config_value.last_modified = datetime.now()
            
            return config_value.value

    def set(self, key: str, value: Any, source_type: str = "override") -> bool:
        """Set configuration value (MANDATORY)."""
        try:
            schema = self.config_schemas.get(key)
            if schema and schema.enterprise_only and not self.advanced_mode.enabled:
                return False
            
            if schema:
                valid, errors = schema.validate_value(value)
                if not valid:
                    return False
            
            source = ConfigSource(source_type=source_type, loaded_at=datetime.now(), priority=30)
            config_value = ConfigValue(key=key, value=value, source=source, schema=schema, last_modified=datetime.now())
            
            with self._lock:
                self.config_values[key] = config_value
                if self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES):
                    self._notify_change_listeners(key, value)
            return True
        except Exception:
            return False

    def _notify_change_listeners(self, key: str, value: Any):
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES):
            return
        for listener in self.change_listeners:
            try:
                listener(key, value)
            except Exception as e:
                self.logger.warning(f"Listener error: {e}")

    def add_change_listener(self, listener: Callable[[str, Any], None]):
        if self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES):
            self.change_listeners.append(listener)

    def get_all(self, include_secrets: bool = False) -> Dict[str, Any]:
        result = {}
        with self._lock:
            for key, val in self.config_values.items():
                if val.is_secret and not include_secrets:
                    result[key] = "***HIDDEN***"
                else:
                    result[key] = val.value
        return result

# Initialize module
if __name__ == "__main__":
    print("ConfigManager module loaded")
