#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Configuration Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Professional configuration management with optional enterprise features.
Core functionality works without advanced features - advanced mode is optional.
Container-native with Poetry+VENV, robust error recovery.

Key Responsibilities:
- MANDATORY: YAML/JSON configuration loading and saving
- MANDATORY: Environment variable handling
- MANDATORY: Configuration validation and defaults
- OPTIONAL: Secrets management (API keys, tokens)
- OPTIONAL: Dynamic configuration updates
- OPTIONAL: Configuration templates and environments
- OPTIONAL: Migration system for framework updates
- GUI Advanced Mode Toggle support
"""

import os
import sys
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, Set
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
    
    Provides robust configuration management with optional enterprise features.
    Core functionality works without advanced features enabled.
    
    MANDATORY Features:
    - YAML/JSON configuration loading and saving
    - Environment variable handling
    - Configuration validation and defaults
    - Multi-scope configuration management
    
    OPTIONAL Features (Advanced Mode):
    - Secrets management (API keys, tokens)
    - Dynamic configuration updates
    - Configuration templates and environments  
    - Migration system for framework updates
    - Enterprise compliance features
    
    Usage:
    Basic Mode:  config = ConfigManager()
    Advanced:    config = ConfigManager(advanced_mode=True, enable_secrets=True)
    """
    
    def __init__(self, 
                 config_dir: Optional[Path] = None,
                 advanced_mode: bool = False,
                 enable_secrets: bool = False,
                 enable_templates: bool = False,
                 enable_dynamic_updates: bool = False):
        """
        Initialize Configuration Manager.
        
        Args:
            config_dir: Configuration directory (auto-detected if None)
            advanced_mode: Enable advanced enterprise features
            enable_secrets: Enable secrets management (requires advanced_mode)
            enable_templates: Enable configuration templates (requires advanced_mode)
            enable_dynamic_updates: Enable runtime updates (requires advanced_mode)
        """
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
        # Try common locations
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
        
        # Default to current directory
        return Path.cwd() / "configs"
    
    def _ensure_directories(self):
        """Ensure required directories exist"""
        directories = [
            self.config_dir,
            self.config_dir / "environments",
            self.config_dir / "templates",
            self.config_dir / "backups"
        ]
        
        # Only create advanced directories if advanced mode is enabled
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
        # Framework core settings (MANDATORY)
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
            ConfigSchema("api_host", str, False, "127.0.0.1", "API server host")
        ]
        
        # Advanced/Enterprise schemas (OPTIONAL)
        if self.advanced_mode.enabled:
            advanced_schemas = [
                ConfigSchema("enable_audit_logging", bool, False, False, "Enable audit logging", enterprise_only=True),
                ConfigSchema("require_approval", bool, False, False, "Require approval for builds", enterprise_only=True),
                ConfigSchema("compliance_mode", str, False, "none", "Compliance mode", ["regex:^(none|basic|strict)$"], enterprise_only=True),
                ConfigSchema("secret_encryption_key", str, False, None, "Encryption key for secrets", enterprise_only=True),
                ConfigSchema("backup_retention_days", int, False, 30, "Backup retention period", ["min:1"], enterprise_only=True)
            ]
            core_schemas.extend(advanced_schemas)
        
        # Register schemas
        for schema in core_schemas:
            self.config_schemas[schema.field_name] = schema
        
        self.logger.debug(f"Initialized {len(core_schemas)} configuration schemas")
    
    def load_configuration(self, config_file: Optional[Path] = None) -> bool:
        """
        Load configuration from file(s).
        
        Args:
            config_file: Specific config file (auto-detect if None)
            
        Returns:
            bool: True if loading successful
        """
        try:
            self.logger.info("Loading configuration...")
            
            # Step 1: Load defaults
            self._load_default_configuration()
            
            # Step 2: Load from files
            if config_file:
                self._load_config_file(config_file)
            else:
                self._load_config_files_auto()
            
            # Step 3: Load environment variables
            self._load_environment_variables()
            
            # Step 4: Validate configuration
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
        # Configuration file candidates (in priority order)
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
        
        # Detect format
        config_format = self._detect_config_format(config_file)
        
        # Load data
        with open(config_file, 'r') as f:
            if config_format == ConfigFormat.YAML:
                config_data = yaml.safe_load(f)
            elif config_format == ConfigFormat.JSON:
                config_data = json.load(f)
            else:
                raise ValueError(f"Unsupported config format: {config_format}")
        
        if not config_data:
            return
        
        # Create source info
        file_source = ConfigSource(
            source_type="file",
            source_path=str(config_file),
            loaded_at=datetime.now(),
            priority=10  # Higher than defaults
        )
        
        # Load values
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
            # Try to detect from content
            try:
                with open(config_file, 'r') as f:
                    content = f.read().strip()
                
                if content.startswith('{'):
                    return ConfigFormat.JSON
                else:
                    return ConfigFormat.YAML  # Default
            except Exception:
                return ConfigFormat.YAML  # Default fallback
    
    def _load_config_data(self, config_data: Dict[str, Any], source: ConfigSource):
        """Load configuration data from dictionary"""
        for key, value in config_data.items():
            # Skip advanced-only settings if advanced mode is disabled
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
                # Only override if this source has higher priority
                existing_value = self.config_values.get(key)
                if not existing_value or source.priority >= existing_value.source.priority:
                    self.config_values[key] = config_value
     def _load_environment_variables(self):
        """Load configuration from environment variables (MANDATORY)"""
        env_source = ConfigSource(
            source_type="environment",
            loaded_at=datetime.now(),
            priority=20  # Higher than file configs
        )
        
        # Common environment variable prefixes
        prefixes = ["LLM_FRAMEWORK_", "FRAMEWORK_", "LLM_"]
        
        loaded_count = 0
        
        for env_name, env_value in os.environ.items():
            config_key = None
            
            # Check if env var matches our prefixes
            for prefix in prefixes:
                if env_name.startswith(prefix):
                    config_key = env_name[len(prefix):].lower()
                    break
            
            # Skip if no matching prefix
            if not config_key:
                continue
            
            # Convert common naming patterns
            config_key = config_key.replace("_", "_")  # Keep underscores
            
            # Check if we have a schema for this key
            schema = self.config_schemas.get(config_key)
            
            # Skip enterprise-only settings if advanced mode disabled
            if schema and schema.enterprise_only and not self.advanced_mode.enabled:
                continue
            
            # Convert environment string to appropriate type
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
                    # Override with environment value (high priority)
                    self.config_values[config_key] = config_value
                    loaded_count += 1
                    
            except Exception as e:
                self.logger.warning(f"Failed to load environment variable {env_name}: {e}")
        
        if loaded_count > 0:
            self.logger.info(f"Loaded {loaded_count} environment variables")
    
    def _convert_env_value(self, env_value: str, schema: Optional[ConfigSchema]) -> Any:
        """Convert environment variable string to appropriate type"""
        if not schema:
            return env_value  # Return as string if no schema
        
        target_type = schema.field_type
        
        try:
            if target_type == bool:
                return env_value.lower() in ('true', '1', 'yes', 'on', 'enabled')
            elif target_type == int:
                return int(env_value)
            elif target_type == float:
                return float(env_value)
            elif target_type == list:
                # Split by comma, semicolon, or pipe
                return [item.strip() for item in env_value.replace(';', ',').replace('|', ',').split(',') if item.strip()]
            else:
                return env_value  # String or other types
                
        except (ValueError, TypeError):
            self.logger.warning(f"Failed to convert environment value '{env_value}' to {target_type.__name__}")
            return env_value
    
    def _validate_configuration(self):
        """Validate loaded configuration (MANDATORY)"""
        validation_errors = []
        validation_warnings = []
        
        # Check required fields
        for schema_name, schema in self.config_schemas.items():
            if schema.required:
                if schema_name not in self.config_values:
                    validation_errors.append(f"Required configuration missing: {schema_name}")
                    continue
                
                config_value = self.config_values[schema_name]
                if config_value.value is None:
                    validation_errors.append(f"Required configuration cannot be null: {schema_name}")
        
        # Validate individual values
        for config_name, config_value in self.config_values.items():
            if not config_value.is_valid():
                errors = config_value.get_validation_errors()
                validation_errors.extend(errors)
        
        # Log validation results
        if validation_errors:
            for error in validation_errors:
                self.logger.error(f"Configuration validation error: {error}")
            raise ValidationError(f"Configuration validation failed: {len(validation_errors)} errors")
        
        if validation_warnings:
            for warning in validation_warnings:
                self.logger.warning(f"Configuration validation warning: {warning}")
        
        self.logger.debug("Configuration validation passed")
    
    # ========================================================================
    # CORE CONFIGURATION METHODS (MANDATORY)
    # ========================================================================
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value (MANDATORY).
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Any: Configuration value
        """
        with self._lock:
            config_value = self.config_values.get(key)
            
            if config_value is None:
                return default
            
            # Update access tracking (for advanced mode)
            if self.advanced_mode.enabled:
                config_value.last_modified = datetime.now()
            
            return config_value.value
    
    def set(self, key: str, value: Any, source_type: str = "override") -> bool:
        """
        Set configuration value (MANDATORY).
        
        Args:
            key: Configuration key
            value: Configuration value
            source_type: Source of the change
            
        Returns:
            bool: True if set successful
        """
        try:
            # Get schema for validation
            schema = self.config_schemas.get(key)
            
            # Skip enterprise-only settings if advanced mode disabled
            if schema and schema.enterprise_only and not self.advanced_mode.enabled:
                self.logger.warning(f"Cannot set enterprise-only setting '{key}' (advanced mode disabled)")
                return False
            
            # Validate value if schema exists
            if schema:
                valid, errors = schema.validate_value(value)
                if not valid:
                    self.logger.error(f"Configuration validation failed for {key}: {'; '.join(errors)}")
                    return False
            
            # Create override source
            override_source = ConfigSource(
                source_type=source_type,
                loaded_at=datetime.now(),
                priority=30  # Highest priority
            )
            
            # Create config value
            config_value = ConfigValue(
                key=key,
                value=value,
                source=override_source,
                schema=schema,
                last_modified=datetime.now()
            )
            
            with self._lock:
                old_value = self.config_values.get(key)
                self.config_values[key] = config_value
                
                # Track change (for advanced mode)
                if self.advanced_mode.enabled:
                    self._track_config_change(key, old_value.value if old_value else None, value, source_type)
                
                # Notify listeners (for advanced mode)
                if self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES):
                    self._notify_change_listeners(key, value)
            
            self.logger.debug(f"Configuration set: {key} = {value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set configuration {key}: {e}")
            return False
    
    def has(self, key: str) -> bool:
        """
        Check if configuration key exists (MANDATORY).
        
        Args:
            key: Configuration key
            
        Returns:
            bool: True if key exists
        """
        return key in self.config_values
    
    def delete(self, key: str) -> bool:
        """
        Delete configuration key (MANDATORY).
        
        Args:
            key: Configuration key to delete
            
        Returns:
            bool: True if deletion successful
        """
        try:
            with self._lock:
                if key not in self.config_values:
                    return False
                
                # Check if key is required
                schema = self.config_schemas.get(key)
                if schema and schema.required:
                    self.logger.warning(f"Cannot delete required configuration: {key}")
                    return False
                
                old_value = self.config_values[key].value
                del self.config_values[key]
                
                # Track change (for advanced mode)
                if self.advanced_mode.enabled:
                    self._track_config_change(key, old_value, None, "deletion")
            
            self.logger.debug(f"Configuration deleted: {key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete configuration {key}: {e}")
            return False
    
    def get_all(self, include_secrets: bool = False) -> Dict[str, Any]:
        """
        Get all configuration values (MANDATORY).
        
        Args:
            include_secrets: Whether to include secret values
            
        Returns:
            dict: All configuration values
        """
        result = {}
        
        with self._lock:
            for key, config_value in self.config_values.items():
                # Skip secrets unless explicitly requested
                if config_value.is_secret and not include_secrets:
                    result[key] = "***HIDDEN***"
                else:
                    result[key] = config_value.value
        
        return result
    
    def get_schema(self, key: str) -> Optional[ConfigSchema]:
        """
        Get configuration schema for key (MANDATORY).
        
        Args:
            key: Configuration key
            
        Returns:
            ConfigSchema: Schema or None
        """
        return self.config_schemas.get(key)
    
    def list_keys(self, include_enterprise: bool = None) -> List[str]:
        """
        List all configuration keys (MANDATORY).
        
        Args:
            include_enterprise: Whether to include enterprise-only keys
            
        Returns:
            List[str]: Configuration keys
        """
        if include_enterprise is None:
            include_enterprise = self.advanced_mode.enabled
        
        keys = []
        
        for key, config_value in self.config_values.items():
            schema = config_value.schema
            
            # Filter enterprise-only keys if requested
            if schema and schema.enterprise_only and not include_enterprise:
                continue
            
            keys.append(key)
        
        return sorted(keys)
    
    def save_configuration(self, config_file: Optional[Path] = None, 
                          format: ConfigFormat = ConfigFormat.YAML) -> bool:
        """
        Save configuration to file (MANDATORY).
        
        Args:
            config_file: Target config file (auto-generate if None)
            format: Configuration format
            
        Returns:
            bool: True if save successful
        """
        try:
            # Determine output file
            if not config_file:
                if format == ConfigFormat.YAML:
                    config_file = self.config_dir / "framework.yml"
                elif format == ConfigFormat.JSON:
                    config_file = self.config_dir / "framework.json"
                else:
                    raise ValueError(f"Unsupported format for auto-naming: {format}")
            
            # Prepare data for saving
            config_data = {}
            
            with self._lock:
                for key, config_value in self.config_values.items():
                    # Skip default values (don't save unnecessary defaults)
                    schema = config_value.schema
                    if (schema and 
                        schema.default_value is not None and 
                        config_value.value == schema.default_value and
                        config_value.source.source_type == "default"):
                        continue
                    
                    # Skip secrets (save separately in advanced mode)
                    if config_value.is_secret:
                        continue
                    
                    # Skip enterprise-only if advanced mode disabled
                    if (schema and 
                        schema.enterprise_only and 
                        not self.advanced_mode.enabled):
                        continue
                    
                    config_data[key] = config_value.value
            
            # Create backup of existing file
            if config_file.exists():
                backup_file = config_file.with_suffix(f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                shutil.copy2(config_file, backup_file)
                self.logger.debug(f"Created backup: {backup_file}")
            
            # Save configuration
            ensure_directory(config_file.parent)
            
            with open(config_file, 'w') as f:
                if format == ConfigFormat.YAML:
                    yaml.dump(config_data, f, default_flow_style=False, sort_keys=True)
                elif format == ConfigFormat.JSON:
                    json.dump(config_data, f, indent=2, sort_keys=True)
                else:
                    raise ValueError(f"Unsupported save format: {format}")
            
            self.logger.info(f"Configuration saved to: {config_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False
    
    def reload_configuration(self) -> bool:
        """
        Reload configuration from sources (MANDATORY).
        
        Returns:
            bool: True if reload successful
        """
        try:
            self.logger.info("Reloading configuration...")
            
            # Clear current values (keep schemas)
            with self._lock:
                self.config_values.clear()
            
            # Reload from all sources
            return self.load_configuration()
            
        except Exception as e:
            self.logger.error(f"Configuration reload failed: {e}")
            return False
    
    def validate_value(self, key: str, value: Any) -> Tuple[bool, List[str]]:
        """
        Validate a specific configuration value (MANDATORY).
        
        Args:
            key: Configuration key
            value: Value to validate
            
        Returns:
            tuple: (is_valid, error_messages)
        """
        schema = self.config_schemas.get(key)
        if not schema:
            return True, []  # No schema = valid
        
        return schema.validate_value(value)
    
    def get_config_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a configuration key (MANDATORY).
        
        Args:
            key: Configuration key
            
        Returns:
            dict: Configuration information or None
        """
        config_value = self.config_values.get(key)
        if not config_value:
            return None
        
        info = {
            "key": key,
            "value": config_value.value if not config_value.is_secret else "***HIDDEN***",
            "source_type": config_value.source.source_type,
            "source_path": config_value.source.source_path,
            "last_modified": config_value.last_modified.isoformat() if config_value.last_modified else None,
            "is_secret": config_value.is_secret,
            "is_readonly": config_value.is_readonly,
            "is_valid": config_value.is_valid()
        }
        
        # Add schema information
        if config_value.schema:
            info["schema"] = {
                "type": config_value.schema.field_type.__name__,
                "required": config_value.schema.required,
                "default_value": config_value.schema.default_value,
                "description": config_value.schema.description,
                "enterprise_only": config_value.schema.enterprise_only,
                "validation_rules": config_value.schema.validation_rules
            }
        
        # Add validation errors if any
        validation_errors = config_value.get_validation_errors()
        if validation_errors:
            info["validation_errors"] = validation_errors
        
        return info
    
    def export_configuration(self, output_file: Path, 
                           include_secrets: bool = False,
                           include_defaults: bool = False) -> bool:
        """
        Export configuration to file with options (MANDATORY).
        
        Args:
            output_file: Output file path
            include_secrets: Whether to include secrets
            include_defaults: Whether to include default values
            
        Returns:
            bool: True if export successful
        """
        try:
            export_data = {
                "metadata": {
                    "export_time": datetime.now().isoformat(),
                    "framework_version": "1.0.0",
                    "advanced_mode": self.advanced_mode.enabled,
                    "total_keys": len(self.config_values)
                },
                "configuration": {}
            }
            
            # Export configuration values
            with self._lock:
                for key, config_value in self.config_values.items():
                    # Skip secrets unless requested
                    if config_value.is_secret and not include_secrets:
                        continue
                    
                    # Skip defaults unless requested
                    if (not include_defaults and 
                        config_value.schema and
                        config_value.schema.default_value == config_value.value and
                        config_value.source.source_type == "default"):
                        continue
                    
                    value_data = {
                        "value": config_value.value,
                        "source": config_value.source.source_type,
                        "last_modified": config_value.last_modified.isoformat() if config_value.last_modified else None
                    }
                    
                    if config_value.schema:
                        value_data["description"] = config_value.schema.description
                        value_data["required"] = config_value.schema.required
                        value_data["type"] = config_value.schema.field_type.__name__
                    
                    export_data["configuration"][key] = value_data
            
            # Write export file
            ensure_directory(output_file.parent)
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2, sort_keys=True)
            
            self.logger.info(f"Configuration exported to: {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration export failed: {e}")
            return False
    
    # ========================================================================
    # CHANGE TRACKING (ADVANCED MODE ONLY)
    # ========================================================================
    
    def _track_config_change(self, key: str, old_value: Any, new_value: Any, source: str):
        """Track configuration changes (advanced mode only)"""
        if not self.advanced_mode.enabled:
            return
        
        change_record = {
            "timestamp": datetime.now().isoformat(),
            "key": key,
            "old_value": old_value,
            "new_value": new_value,
            "source": source,
            "change_id": len(self.change_history)
        }
        
        self.change_history.append(change_record)
        
        # Limit history size
        max_history = 1000
        if len(self.change_history) > max_history:
            self.change_history = self.change_history[-max_history:]
    
    def _notify_change_listeners(self, key: str, value: Any):
        """Notify registered change listeners (advanced mode only)"""
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES):
            return
        
        for listener in self.change_listeners:
            try:
                listener(key, value)
            except Exception as e:
                self.logger.warning(f"Change listener error: {e}")
 # ========================================================================
    # ADVANCED FEATURES (OPTIONAL - ONLY ENABLED WITH FEATURE FLAGS)
    # ========================================================================
    
    def add_change_listener(self, listener: Callable[[str, Any], None]):
        """
        Add configuration change listener (OPTIONAL - requires DYNAMIC_UPDATES).
        
        Args:
            listener: Callback function for changes
        """
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES):
            self.logger.warning("Dynamic updates not enabled - change listener not added")
            return
        
        self.change_listeners.append(listener)
        self.logger.debug("Configuration change listener added")
    
    def remove_change_listener(self, listener: Callable[[str, Any], None]):
        """Remove configuration change listener (OPTIONAL)"""
        if listener in self.change_listeners:
            self.change_listeners.remove(listener)
            self.logger.debug("Configuration change listener removed")
    
    def get_change_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get configuration change history (OPTIONAL - requires advanced mode).
        
        Args:
            limit: Maximum number of changes to return
            
        Returns:
            List[dict]: Change history
        """
        if not self.advanced_mode.enabled:
            return []
        
        return self.change_history[-limit:] if self.change_history else []
    
    # ========================================================================
    # SECRETS MANAGEMENT (OPTIONAL - REQUIRES SECRETS_MANAGEMENT FEATURE)
    # ========================================================================
    
    def set_secret(self, key: str, value: str, encrypt: bool = True) -> bool:
        """
        Set a secret configuration value (OPTIONAL - requires SECRETS_MANAGEMENT).
        
        Args:
            key: Secret key
            value: Secret value
            encrypt: Whether to encrypt the value
            
        Returns:
            bool: True if set successful
        """
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.SECRETS_MANAGEMENT):
            self.logger.warning("Secrets management not enabled")
            return False
        
        try:
            # Encrypt value if requested
            if encrypt:
                encrypted_value = self._encrypt_secret(value)
            else:
                encrypted_value = value
            
            # Create secret source
            secret_source = ConfigSource(
                source_type="secret",
                loaded_at=datetime.now(),
                priority=25  # Higher than environment, lower than override
            )
            
            # Create secret config value
            config_value = ConfigValue(
                key=key,
                value=encrypted_value,
                source=secret_source,
                is_secret=True,
                last_modified=datetime.now()
            )
            
            with self._lock:
                self.config_values[key] = config_value
                
                # Track change
                self._track_config_change(key, None, "***SECRET***", "secret")
            
            # Save to secure storage
            self._save_secret_to_storage(key, encrypted_value)
            
            self.logger.info(f"Secret set: {key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set secret {key}: {e}")
            return False
    
    def get_secret(self, key: str, decrypt: bool = True) -> Optional[str]:
        """
        Get a secret configuration value (OPTIONAL - requires SECRETS_MANAGEMENT).
        
        Args:
            key: Secret key
            decrypt: Whether to decrypt the value
            
        Returns:
            str: Secret value or None
        """
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.SECRETS_MANAGEMENT):
            return None
        
        config_value = self.config_values.get(key)
        if not config_value or not config_value.is_secret:
            return None
        
        try:
            if decrypt and config_value.value:
                return self._decrypt_secret(config_value.value)
            else:
                return config_value.value
                
        except Exception as e:
            self.logger.error(f"Failed to get secret {key}: {e}")
            return None
    
    def list_secrets(self) -> List[str]:
        """List all secret keys (OPTIONAL)"""
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.SECRETS_MANAGEMENT):
            return []
        
        return [key for key, value in self.config_values.items() if value.is_secret]
    
    def _encrypt_secret(self, value: str) -> str:
        """Encrypt secret value (simplified implementation)"""
        try:
            # Simple base64 encoding (in production, use proper encryption)
            import base64
            return base64.b64encode(value.encode()).decode()
        except Exception:
            return value  # Fallback to plain text
    
    def _decrypt_secret(self, encrypted_value: str) -> str:
        """Decrypt secret value (simplified implementation)"""
        try:
            import base64
            return base64.b64decode(encrypted_value.encode()).decode()
        except Exception:
            return encrypted_value  # Fallback if decryption fails
    
    def _save_secret_to_storage(self, key: str, encrypted_value: str):
        """Save secret to secure storage"""
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.SECRETS_MANAGEMENT):
            return
        
        secrets_dir = self.config_dir / "secrets"
        ensure_directory(secrets_dir)
        
        secrets_file = secrets_dir / "secrets.json"
        
        # Load existing secrets
        secrets_data = {}
        if secrets_file.exists():
            try:
                with open(secrets_file, 'r') as f:
                    secrets_data = json.load(f)
            except Exception:
                pass
        
        # Update secrets
        secrets_data[key] = {
            "value": encrypted_value,
            "created_at": datetime.now().isoformat(),
            "encrypted": True
        }
        
        # Save secrets
        try:
            with open(secrets_file, 'w') as f:
                json.dump(secrets_data, f, indent=2)
            
            # Set restrictive permissions (Unix/Linux)
            if hasattr(os, 'chmod'):
                os.chmod(secrets_file, 0o600)  # Owner read/write only
                
        except Exception as e:
            self.logger.error(f"Failed to save secret to storage: {e}")
    
    def _load_secrets_from_storage(self):
        """Load secrets from secure storage"""
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.SECRETS_MANAGEMENT):
            return
        
        secrets_file = self.config_dir / "secrets" / "secrets.json"
        if not secrets_file.exists():
            return
        
        try:
            with open(secrets_file, 'r') as f:
                secrets_data = json.load(f)
            
            secret_source = ConfigSource(
                source_type="secret_storage",
                source_path=str(secrets_file),
                loaded_at=datetime.now(),
                priority=25
            )
            
            for key, secret_info in secrets_data.items():
                config_value = ConfigValue(
                    key=key,
                    value=secret_info["value"],
                    source=secret_source,
                    is_secret=True,
                    last_modified=datetime.now()
                )
                
                with self._lock:
                    self.config_values[key] = config_value
            
            self.logger.debug(f"Loaded {len(secrets_data)} secrets from storage")
            
        except Exception as e:
            self.logger.error(f"Failed to load secrets from storage: {e}")
    
    # ========================================================================
    # CONFIGURATION TEMPLATES (OPTIONAL - REQUIRES TEMPLATES FEATURE)
    # ========================================================================
    
    def load_template(self, template_name: str) -> bool:
        """
        Load configuration template (OPTIONAL - requires TEMPLATES).
        
        Args:
            template_name: Template name
            
        Returns:
            bool: True if template loaded successfully
        """
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.TEMPLATES):
            self.logger.warning("Configuration templates not enabled")
            return False
        
        template_file = self.config_dir / "templates" / f"{template_name}.yml"
        if not template_file.exists():
            self.logger.error(f"Template not found: {template_name}")
            return False
        
        try:
            with open(template_file, 'r') as f:
                template_data = yaml.safe_load(f)
            
            # Apply template values
            template_source = ConfigSource(
                source_type="template",
                source_path=str(template_file),
                loaded_at=datetime.now(),
                priority=5  # Lower than files, higher than defaults
            )
            
            self._load_config_data(template_data, template_source)
            
            self.logger.info(f"Template loaded: {template_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load template {template_name}: {e}")
            return False
    
    def save_as_template(self, template_name: str, description: str = "") -> bool:
        """
        Save current configuration as template (OPTIONAL).
        
        Args:
            template_name: Template name
            description: Template description
            
        Returns:
            bool: True if template saved successfully
        """
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.TEMPLATES):
            self.logger.warning("Configuration templates not enabled")
            return False
        
        try:
            template_data = {
                "metadata": {
                    "name": template_name,
                    "description": description,
                    "created_at": datetime.now().isoformat(),
                    "framework_version": "1.0.0"
                },
                "configuration": {}
            }
            
            # Export non-secret, non-default values
            with self._lock:
                for key, config_value in self.config_values.items():
                    # Skip secrets
                    if config_value.is_secret:
                        continue
                    
                    # Skip default values
                    if (config_value.schema and 
                        config_value.schema.default_value == config_value.value and
                        config_value.source.source_type == "default"):
                        continue
                    
                    template_data["configuration"][key] = config_value.value
            
            # Save template
            template_file = self.config_dir / "templates" / f"{template_name}.yml"
            ensure_directory(template_file.parent)
            
            with open(template_file, 'w') as f:
                yaml.dump(template_data, f, default_flow_style=False)
            
            self.logger.info(f"Template saved: {template_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save template {template_name}: {e}")
            return False
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """List available configuration templates (OPTIONAL)"""
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.TEMPLATES):
            return []
        
        templates = []
        templates_dir = self.config_dir / "templates"
        
        if not templates_dir.exists():
            return []
        
        for template_file in templates_dir.glob("*.yml"):
            try:
                with open(template_file, 'r') as f:
                    template_data = yaml.safe_load(f)
                
                metadata = template_data.get("metadata", {})
                template_info = {
                    "name": template_file.stem,
                    "description": metadata.get("description", ""),
                    "created_at": metadata.get("created_at"),
                    "file_path": str(template_file)
                }
                
                templates.append(template_info)
                
            except Exception as e:
                self.logger.warning(f"Failed to read template {template_file}: {e}")
        
        return sorted(templates, key=lambda x: x["name"])
    
    # ========================================================================
    # ENVIRONMENT MANAGEMENT (OPTIONAL - REQUIRES ENVIRONMENTS FEATURE)
    # ========================================================================
    
    def load_environment(self, environment: str) -> bool:
        """
        Load environment-specific configuration (OPTIONAL - requires ENVIRONMENTS).
        
        Args:
            environment: Environment name (dev, staging, prod, etc.)
            
        Returns:
            bool: True if environment loaded successfully
        """
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.ENVIRONMENTS):
            self.logger.warning("Environment management not enabled")
            return False
        
        env_file = self.config_dir / "environments" / f"{environment}.yml"
        if not env_file.exists():
            self.logger.error(f"Environment configuration not found: {environment}")
            return False
        
        try:
            with open(env_file, 'r') as f:
                env_data = yaml.safe_load(f)
            
            # Apply environment values
            env_source = ConfigSource(
                source_type="environment_config",
                source_path=str(env_file),
                loaded_at=datetime.now(),
                priority=15  # Between files and environment variables
            )
            
            self._load_config_data(env_data, env_source)
            
            # Set current environment marker
            self.set("current_environment", environment, "environment_config")
            
            self.logger.info(f"Environment loaded: {environment}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load environment {environment}: {e}")
            return False
    
    def create_environment(self, environment: str, description: str = "") -> bool:
        """Create new environment configuration (OPTIONAL)"""
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.ENVIRONMENTS):
            return False
        
        try:
            env_data = {
                "metadata": {
                    "environment": environment,
                    "description": description,
                    "created_at": datetime.now().isoformat()
                },
                "configuration": {
                    # Environment-specific defaults
                    "log_level": "INFO" if environment == "prod" else "DEBUG",
                    "auto_cleanup": environment == "prod",
                    "api_enabled": environment != "dev"
                }
            }
            
            env_file = self.config_dir / "environments" / f"{environment}.yml"
            ensure_directory(env_file.parent)
            
            with open(env_file, 'w') as f:
                yaml.dump(env_data, f, default_flow_style=False)
            
            self.logger.info(f"Environment created: {environment}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create environment {environment}: {e}")
            return False
    
    # ========================================================================
    # CONFIGURATION MIGRATION (OPTIONAL - REQUIRES MIGRATION FEATURE)
    # ========================================================================
    
    def migrate_configuration(self, from_version: str, to_version: str) -> bool:
        """
        Migrate configuration between versions (OPTIONAL - requires MIGRATION).
        
        Args:
            from_version: Source version
            to_version: Target version
            
        Returns:
            bool: True if migration successful
        """
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.MIGRATION):
            self.logger.warning("Configuration migration not enabled")
            return False
        
        try:
            self.logger.info(f"Migrating configuration from {from_version} to {to_version}")
            
            # Create backup before migration
            backup_file = self.config_dir / "backups" / f"pre_migration_{from_version}_to_{to_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yml"
            self.save_configuration(backup_file)
            
            # Apply version-specific migrations
            migration_applied = False
            
            # Example migrations (extend as needed)
            if from_version == "1.0" and to_version == "1.1":
                migration_applied = self._migrate_1_0_to_1_1()
            elif from_version == "1.1" and to_version == "1.2":
                migration_applied = self._migrate_1_1_to_1_2()
            
            if migration_applied:
                # Update version marker
                self.set("config_version", to_version, "migration")
                self.save_configuration()
                
                self.logger.info(f"Configuration migration completed: {from_version} → {to_version}")
                return True
            else:
                self.logger.warning(f"No migration path found: {from_version} → {to_version}")
                return False
                
        except Exception as e:
            self.logger.error(f"Configuration migration failed: {e}")
            return False
    
    def _migrate_1_0_to_1_1(self) -> bool:
        """Example migration from version 1.0 to 1.1"""
        try:
            # Example: Rename old config key
            if self.has("old_setting_name"):
                old_value = self.get("old_setting_name")
                self.set("new_setting_name", old_value, "migration")
                self.delete("old_setting_name")
                self.logger.info("Migrated: old_setting_name → new_setting_name")
            
            # Example: Add new required settings with defaults
            if not self.has("new_required_setting"):
                self.set("new_required_setting", "default_value", "migration")
                self.logger.info("Added new required setting with default value")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Migration 1.0→1.1 failed: {e}")
            return False
    
    def _migrate_1_1_to_1_2(self) -> bool:
        """Example migration from version 1.1 to 1.2"""
        try:
            # Example: Convert setting format
            if self.has("some_setting"):
                old_value = self.get("some_setting")
                if isinstance(old_value, str):
                    # Convert string to list
                    new_value = [item.strip() for item in old_value.split(",")]
                    self.set("some_setting", new_value, "migration")
                    self.logger.info("Converted some_setting from string to list")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Migration 1.1→1.2 failed: {e}")
            return False
    
    def get_migration_info(self) -> Dict[str, Any]:
        """Get configuration migration information (OPTIONAL)"""
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.MIGRATION):
            return {}
        
        current_version = self.get("config_version", "1.0")
        available_migrations = ["1.0→1.1", "1.1→1.2"]  # Example
        
        return {
            "current_version": current_version,
            "target_version": "1.2",  # Latest
            "available_migrations": available_migrations,
            "migration_needed": current_version != "1.2",
            "backup_files": self._list_backup_files()
        }
    
    def _list_backup_files(self) -> List[str]:
        """List available backup files"""
        backups_dir = self.config_dir / "backups"
        if not backups_dir.exists():
            return []
        
        backup_files = []
        for backup_file in backups_dir.glob("*.yml"):
            backup_files.append(str(backup_file))
        
        return sorted(backup_files, reverse=True)  # Most recent first
# ========================================================================
    # PUBLIC APIS AND UTILITIES (MANDATORY)
    # ========================================================================
    
    def reset_to_defaults(self) -> bool:
        """
        Reset all configuration to default values (MANDATORY).
        
        Returns:
            bool: True if reset successful
        """
        try:
            self.logger.info("Resetting configuration to defaults...")
            
            # Create backup before reset
            backup_file = self.config_dir / "backups" / f"before_reset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yml"
            self.save_configuration(backup_file)
            
            with self._lock:
                # Clear current values
                self.config_values.clear()
                
                # Reload only defaults
                self._load_default_configuration()
            
            # Track change (for advanced mode)
            if self.advanced_mode.enabled:
                self._track_config_change("__ALL__", "custom_values", "defaults", "reset")
            
            self.logger.info("Configuration reset to defaults completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration reset failed: {e}")
            return False
    
    def merge_configuration(self, other_config: Dict[str, Any], 
                           overwrite: bool = False) -> bool:
        """
        Merge external configuration into current config (MANDATORY).
        
        Args:
            other_config: Configuration dictionary to merge
            overwrite: Whether to overwrite existing values
            
        Returns:
            bool: True if merge successful
        """
        try:
            merge_source = ConfigSource(
                source_type="merge",
                loaded_at=datetime.now(),
                priority=35  # Very high priority
            )
            
            merged_count = 0
            
            with self._lock:
                for key, value in other_config.items():
                    # Skip if key exists and overwrite is False
                    if not overwrite and key in self.config_values:
                        self.logger.debug(f"Skipping existing key: {key} (overwrite=False)")
                        continue
                    
                    # Validate value if schema exists
                    schema = self.config_schemas.get(key)
                    if schema:
                        valid, errors = schema.validate_value(value)
                        if not valid:
                            self.logger.warning(f"Merge validation failed for {key}: {'; '.join(errors)}")
                            continue
                    
                    # Create config value
                    config_value = ConfigValue(
                        key=key,
                        value=value,
                        source=merge_source,
                        schema=schema,
                        last_modified=datetime.now()
                    )
                    
                    old_value = self.config_values.get(key)
                    self.config_values[key] = config_value
                    merged_count += 1
                    
                    # Track change (for advanced mode)
                    if self.advanced_mode.enabled:
                        self._track_config_change(
                            key, 
                            old_value.value if old_value else None, 
                            value, 
                            "merge"
                        )
            
            self.logger.info(f"Configuration merge completed: {merged_count} values merged")
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration merge failed: {e}")
            return False
    
    def compare_configurations(self, other_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare current configuration with another configuration (MANDATORY).
        
        Args:
            other_config: Configuration to compare against
            
        Returns:
            dict: Comparison results
        """
        comparison = {
            "identical": True,
            "differences": [],
            "missing_in_current": [],
            "missing_in_other": [],
            "value_differences": []
        }
        
        try:
            current_config = self.get_all(include_secrets=False)
            
            # Check for missing keys
            current_keys = set(current_config.keys())
            other_keys = set(other_config.keys())
            
            comparison["missing_in_current"] = list(other_keys - current_keys)
            comparison["missing_in_other"] = list(current_keys - other_keys)
            
            # Check for value differences
            common_keys = current_keys & other_keys
            for key in common_keys:
                current_value = current_config[key]
                other_value = other_config[key]
                
                if current_value != other_value:
                    comparison["value_differences"].append({
                        "key": key,
                        "current_value": current_value,
                        "other_value": other_value
                    })
            
            # Calculate overall differences
            comparison["differences"] = (
                comparison["missing_in_current"] + 
                comparison["missing_in_other"] + 
                [diff["key"] for diff in comparison["value_differences"]]
            )
            
            comparison["identical"] = len(comparison["differences"]) == 0
            
            self.logger.debug(f"Configuration comparison: {len(comparison['differences'])} differences found")
            return comparison
            
        except Exception as e:
            self.logger.error(f"Configuration comparison failed: {e}")
            return {"error": str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get configuration statistics (MANDATORY).
        
        Returns:
            dict: Configuration statistics
        """
        stats = {
            "total_keys": 0,
            "by_source": {},
            "by_type": {},
            "validation_status": {
                "valid": 0,
                "invalid": 0,
                "errors": []
            },
            "advanced_mode": self.advanced_mode.enabled,
            "feature_usage": {}
        }
        
        try:
            with self._lock:
                stats["total_keys"] = len(self.config_values)
                
                # Count by source
                for config_value in self.config_values.values():
                    source_type = config_value.source.source_type
                    stats["by_source"][source_type] = stats["by_source"].get(source_type, 0) + 1
                    
                    # Count by type
                    if config_value.schema:
                        type_name = config_value.schema.field_type.__name__
                        stats["by_type"][type_name] = stats["by_type"].get(type_name, 0) + 1
                    
                    # Validation status
                    if config_value.is_valid():
                        stats["validation_status"]["valid"] += 1
                    else:
                        stats["validation_status"]["invalid"] += 1
                        errors = config_value.get_validation_errors()
                        stats["validation_status"]["errors"].extend(errors)
                
                # Advanced mode feature usage
                if self.advanced_mode.enabled:
                    stats["feature_usage"] = {
                        "secrets_management": self.advanced_mode.is_feature_enabled(AdvancedFeature.SECRETS_MANAGEMENT),
                        "dynamic_updates": self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES),
                        "templates": self.advanced_mode.is_feature_enabled(AdvancedFeature.TEMPLATES),
                        "migration": self.advanced_mode.is_feature_enabled(AdvancedFeature.MIGRATION),
                        "environments": self.advanced_mode.is_feature_enabled(AdvancedFeature.ENVIRONMENTS),
                        "compliance": self.advanced_mode.is_feature_enabled(AdvancedFeature.COMPLIANCE)
                    }
                    
                    stats["change_history_count"] = len(self.change_history)
                    stats["change_listeners_count"] = len(self.change_listeners)
            
            self.logger.debug("Configuration statistics calculated")
            return stats
            
        except Exception as e:
            self.logger.error(f"Configuration statistics failed: {e}")
            return {"error": str(e)}
    
    def cleanup(self):
        """
        Cleanup configuration manager resources (MANDATORY).
        
        Should be called when shutting down the framework.
        """
        try:
            self.logger.info("Cleaning up Configuration Manager...")
            
            # Clear change listeners
            if self.change_listeners:
                self.change_listeners.clear()
                self.logger.debug("Change listeners cleared")
            
            # Save current configuration if changes exist
            if self.config_values:
                try:
                    self.save_configuration()
                    self.logger.debug("Configuration saved during cleanup")
                except Exception as e:
                    self.logger.warning(f"Failed to save configuration during cleanup: {e}")
            
            # Clear sensitive data (secrets)
            if self.advanced_mode.is_feature_enabled(AdvancedFeature.SECRETS_MANAGEMENT):
                secret_keys = [key for key, value in self.config_values.items() if value.is_secret]
                for key in secret_keys:
                    # Don't delete from storage, just clear from memory
                    if key in self.config_values:
                        self.config_values[key].value = None
                
                if secret_keys:
                    self.logger.debug(f"Cleared {len(secret_keys)} secrets from memory")
            
            # Final cleanup
            with self._lock:
                pass  # Lock cleanup is automatic
            
            self.logger.info("Configuration Manager cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Configuration cleanup failed: {e}")
    
    # ========================================================================
    # UTILITY METHODS (MANDATORY)
    # ========================================================================
    
    def is_advanced_mode_enabled(self) -> bool:
        """Check if advanced mode is enabled (MANDATORY)"""
        return self.advanced_mode.enabled
    
    def get_config_directory(self) -> Path:
        """Get configuration directory path (MANDATORY)"""
        return self.config_dir
    
    def get_supported_formats(self) -> List[str]:
        """Get supported configuration formats (MANDATORY)"""
        return [format.value for format in ConfigFormat]
    
    def get_available_schemas(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all available configuration schemas (MANDATORY).
        
        Returns:
            dict: Schema definitions
        """
        schemas = {}
        
        for schema_name, schema in self.config_schemas.items():
            # Skip enterprise-only schemas if advanced mode disabled
            if schema.enterprise_only and not self.advanced_mode.enabled:
                continue
            
            schemas[schema_name] = {
                "type": schema.field_type.__name__,
                "required": schema.required,
                "default_value": schema.default_value,
                "description": schema.description,
                "validation_rules": schema.validation_rules,
                "enterprise_only": schema.enterprise_only
            }
        
        return schemas
    
    def test_configuration(self) -> Dict[str, Any]:
        """
        Test current configuration for issues (MANDATORY).
        
        Returns:
            dict: Test results
        """
        test_results = {
            "passed": True,
            "errors": [],
            "warnings": [],
            "test_count": 0
        }
        
        try:
            # Test 1: Validate all values
            test_results["test_count"] += 1
            for key, config_value in self.config_values.items():
                if not config_value.is_valid():
                    errors = config_value.get_validation_errors()
                    test_results["errors"].extend([f"{key}: {error}" for error in errors])
                    test_results["passed"] = False
            
            # Test 2: Check required keys
            test_results["test_count"] += 1
            for schema_name, schema in self.config_schemas.items():
                if schema.required and schema_name not in self.config_values:
                    test_results["errors"].append(f"Required configuration missing: {schema_name}")
                    test_results["passed"] = False
            
            # Test 3: Check directory access
            test_results["test_count"] += 1
            required_dirs = [
                self.get("targets_dir", "targets"),
                self.get("models_dir", "models"),
                self.get("output_dir", "output"),
                self.get("cache_dir", "cache"),
                self.get("logs_dir", "logs")
            ]
            
            for dir_name in required_dirs:
                try:
                    dir_path = Path(dir_name)
                    if not dir_path.exists():
                        test_results["warnings"].append(f"Directory does not exist: {dir_path}")
                    elif not os.access(dir_path, os.R_OK | os.W_OK):
                        test_results["errors"].append(f"Directory not accessible: {dir_path}")
                        test_results["passed"] = False
                except Exception as e:
                    test_results["errors"].append(f"Directory test failed for {dir_name}: {e}")
                    test_results["passed"] = False
            
            # Test 4: Advanced feature consistency
            if self.advanced_mode.enabled:
                test_results["test_count"] += 1
                
                # Check if secrets directory exists when secrets are enabled
                if self.advanced_mode.is_feature_enabled(AdvancedFeature.SECRETS_MANAGEMENT):
                    secrets_dir = self.config_dir / "secrets"
                    if not secrets_dir.exists():
                        test_results["warnings"].append("Secrets management enabled but secrets directory missing")
            
            self.logger.debug(f"Configuration test completed: {test_results['test_count']} tests")
            return test_results
            
        except Exception as e:
            test_results["errors"].append(f"Configuration test failed: {e}")
            test_results["passed"] = False
            return test_results
    
    def __str__(self) -> str:
        """String representation (MANDATORY)"""
        stats = self.get_statistics()
        return (f"ConfigManager(keys={stats['total_keys']}, "
                f"advanced_mode={stats['advanced_mode']}, "
                f"config_dir={self.config_dir})")
    
    def __repr__(self) -> str:
        """Developer representation (MANDATORY)"""
        return (f"ConfigManager(config_dir='{self.config_dir}', "
                f"advanced_mode={self.advanced_mode.enabled}, "
                f"loaded_keys={len(self.config_values)})")


# ============================================================================
# EXCEPTION CLASSES (MANDATORY)
# ============================================================================

class ConfigurationError(Exception):
    """Base exception for configuration errors"""
    pass


class ConfigurationValidationError(ConfigurationError):
    """Configuration validation failed"""
    pass


class ConfigurationLoadError(ConfigurationError):
    """Configuration loading failed"""
    pass


class ConfigurationSaveError(ConfigurationError):
    """Configuration saving failed"""
    pass


class SecretManagementError(ConfigurationError):
    """Secret management operation failed"""
    pass


class AdvancedFeatureDisabledError(ConfigurationError):
    """Advanced feature is disabled but required"""
    pass


# ============================================================================
# UTILITY FUNCTIONS (MANDATORY)
# ============================================================================

def create_config_manager(advanced_mode: bool = False, 
                         config_dir: Optional[Path] = None,
                         **kwargs) -> ConfigManager:
    """
    Factory function for creating ConfigManager instances (MANDATORY).
    
    Args:
        advanced_mode: Enable advanced features
        config_dir: Configuration directory
        **kwargs: Additional options for advanced mode
        
    Returns:
        ConfigManager: Configured instance
    """
    try:
        config_manager = ConfigManager(
            config_dir=config_dir,
            advanced_mode=advanced_mode,
            **kwargs
        )
        
        # Load configuration
        if not config_manager.load_configuration():
            raise ConfigurationLoadError("Failed to load initial configuration")
        
        return config_manager
        
    except Exception as e:
        raise ConfigurationError(f"Failed to create ConfigManager: {e}")


def validate_config_file(config_file: Path) -> Tuple[bool, List[str]]:
    """
    Validate configuration file without loading (MANDATORY).
    
    Args:
        config_file: Configuration file to validate
        
    Returns:
        tuple: (is_valid, error_messages)
    """
    errors = []
    
    try:
        if not config_file.exists():
            errors.append(f"Configuration file not found: {config_file}")
            return False, errors
        
        # Try to parse file
        with open(config_file, 'r') as f:
            if config_file.suffix.lower() in ['.yml', '.yaml']:
                yaml.safe_load(f)
            elif config_file.suffix.lower() == '.json':
                json.load(f)
            else:
                errors.append(f"Unsupported file format: {config_file.suffix}")
                return False, errors
        
        return True, []
        
    except yaml.YAMLError as e:
        errors.append(f"YAML parsing error: {e}")
    except json.JSONDecodeError as e:
        errors.append(f"JSON parsing error: {e}")
    except Exception as e:
        errors.append(f"File validation error: {e}")
    
    return False, errors


def get_default_config_template() -> Dict[str, Any]:
    """
    Get default configuration template (MANDATORY).
    
    Returns:
        dict: Default configuration template
    """
    return {
        # Framework directories
        "targets_dir": "targets",
        "models_dir": "models", 
        "output_dir": "output",
        "cache_dir": "cache",
        "logs_dir": "logs",
        
        # Logging
        "log_level": "INFO",
        
        # Build settings
        "max_concurrent_builds": 2,
        "build_timeout": 3600,
        "auto_cleanup": True,
        
        # Docker settings
        "docker_registry": "ghcr.io",
        "docker_namespace": "llm-framework",
        
        # GUI settings
        "gui_theme": "dark",
        "gui_auto_refresh": True,
        "gui_refresh_interval": 30,
        
        # API settings
        "api_enabled": False,
        "api_port": 8000,
        "api_host": "127.0.0.1"
    }


def migrate_legacy_config(legacy_config_file: Path, 
                         output_file: Optional[Path] = None) -> bool:
    """
    Migrate legacy configuration format (MANDATORY).
    
    Args:
        legacy_config_file: Legacy configuration file
        output_file: Output file (auto-generate if None)
        
    Returns:
        bool: True if migration successful
    """
    try:
        # This is a placeholder for legacy migration
        # Implement specific migration logic based on legacy format
        
        if not legacy_config_file.exists():
            return False
        
        # Load legacy config (implement based on legacy format)
        with open(legacy_config_file, 'r') as f:
            legacy_data = yaml.safe_load(f)
        
        # Convert to new format
        new_config = get_default_config_template()
        
        # Apply legacy values (implement mapping logic)
        # This is framework-specific and would need to be customized
        
        # Save new format
        if not output_file:
            output_file = legacy_config_file.with_suffix('.migrated.yml')
        
        with open(output_file, 'w') as f:
            yaml.dump(new_config, f, default_flow_style=False)
        
        return True
        
    except Exception:
        return False


# ============================================================================
# MODULE INITIALIZATION AND VALIDATION
# ============================================================================

def validate_config_manager_installation() -> Dict[str, Any]:
    """
    Validate ConfigManager installation and dependencies (MANDATORY).
    
    Returns:
        dict: Validation results
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "dependencies": {}
    }
    
    try:
        # Check required dependencies
        dependencies = {
            "yaml": "PyYAML for YAML configuration support",
            "pathlib": "pathlib for path handling",
            "datetime": "datetime for timestamps",
            "threading": "threading for thread safety",
            "json": "json for JSON configuration support"
        }
        
        for dep_name, description in dependencies.items():
            try:
                __import__(dep_name)
                result["dependencies"][dep_name] = {"available": True, "description": description}
            except ImportError:
                result["dependencies"][dep_name] = {"available": False, "description": description}
                result["errors"].append(f"Missing dependency: {dep_name} ({description})")
                result["valid"] = False
        
        # Check file system permissions
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                tmp.write(b"test")
                tmp.flush()
        except Exception as e:
            result["errors"].append(f"File system write test failed: {e}")
            result["valid"] = False
        
        if result["valid"]:
            result["message"] = "ConfigManager installation validation passed"
        else:
            result["message"] = f"ConfigManager installation validation failed ({len(result['errors'])} errors)"
        
        return result
        
    except Exception as e:
        result["valid"] = False
        result["errors"].append(f"Installation validation error: {e}")
        result["message"] = "ConfigManager installation validation failed"
        return result


# Initialize module
if __name__ == "__main__":
    # Run validation when module is executed directly
    validation_result = validate_config_manager_installation()
    print(f"ConfigManager Validation: {validation_result['message']}")
    
    if not validation_result["valid"]:
        for error in validation_result["errors"]:
            print(f"ERROR: {error}")
    
    if validation_result["warnings"]:
        for warning in validation_result["warnings"]:
            print(f"WARNING: {warning}")        