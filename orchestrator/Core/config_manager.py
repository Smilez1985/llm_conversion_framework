#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Configuration Manager
DIRECTIVE: Gold standard, complete, professionally written.
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
import re
import yaml

from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory, safe_json_load

class ConfigFormat(Enum):
    YAML = "yaml"
    JSON = "json"
    ENV = "env"
    TOML = "toml"

class ConfigScope(Enum):
    GLOBAL = "global"
    USER = "user"
    PROJECT = "project"
    ENVIRONMENT = "environment"
    RUNTIME = "runtime"

class AdvancedFeature(Enum):
    SECRETS_MANAGEMENT = "secrets_management"
    DYNAMIC_UPDATES = "dynamic_updates"
    TEMPLATES = "templates"
    MIGRATION = "migration"
    ENVIRONMENTS = "environments"
    COMPLIANCE = "compliance"

@dataclass
class ConfigSchema:
    field_name: str
    field_type: type
    required: bool = False
    default_value: Any = None
    description: str = ""
    validation_rules: List[str] = field(default_factory=list)
    enterprise_only: bool = False
    
    def validate_value(self, value: Any) -> Tuple[bool, List[str]]:
        errors = []
        if value is not None and not isinstance(value, self.field_type):
            try:
                if self.field_type == int: value = int(value)
                elif self.field_type == float: value = float(value)
                elif self.field_type == bool: value = str(value).lower() in ('true', '1', 'yes', 'on')
                elif self.field_type == str: value = str(value)
            except Exception: errors.append(f"Invalid type for {self.field_name}")
        return len(errors) == 0, errors

@dataclass
class ConfigSource:
    source_type: str
    source_path: Optional[str] = None
    loaded_at: Optional[datetime] = None
    priority: int = 0

@dataclass
class ConfigValue:
    key: str
    value: Any
    source: ConfigSource
    schema: Optional[ConfigSchema] = None
    is_secret: bool = False
    is_readonly: bool = False
    last_modified: Optional[datetime] = None
    def is_valid(self) -> bool:
        if not self.schema: return True
        valid, _ = self.schema.validate_value(self.value)
        return valid
    def get_validation_errors(self) -> List[str]:
        if not self.schema: return []
        _, errors = self.schema.validate_value(self.value)
        return errors

@dataclass
class AdvancedModeConfig:
    enabled: bool = False
    enabled_features: Set[AdvancedFeature] = field(default_factory=set)
    show_advanced_options: bool = False
    show_expert_warnings: bool = True
    require_confirmation: bool = True
    audit_changes: bool = False
    require_validation: bool = True
    enforce_compliance: bool = False
    def is_feature_enabled(self, feature: AdvancedFeature) -> bool:
        return self.enabled and feature in self.enabled_features
    def enable_feature(self, feature: AdvancedFeature):
        if self.enabled: self.enabled_features.add(feature)

class ConfigManager:
    def __init__(self, config_dir: Optional[Path] = None, advanced_mode: bool = False,
                 enable_secrets: bool = False, enable_templates: bool = False,
                 enable_dynamic_updates: bool = False):
        self.logger = get_logger(__name__)
        self.config_dir = config_dir or self._detect_config_directory()
        self._lock = threading.RLock()
        self.advanced_mode = AdvancedModeConfig(enabled=advanced_mode)
        if advanced_mode:
            if enable_secrets: self.advanced_mode.enable_feature(AdvancedFeature.SECRETS_MANAGEMENT)
            if enable_templates: self.advanced_mode.enable_feature(AdvancedFeature.TEMPLATES)
            if enable_dynamic_updates: self.advanced_mode.enable_feature(AdvancedFeature.DYNAMIC_UPDATES)
        self.config_values: Dict[str, ConfigValue] = {}
        self.config_schemas: Dict[str, ConfigSchema] = {}
        self.change_history: List[Dict[str, Any]] = []
        self.change_listeners: List[Callable] = []
        self._initialize_core_schemas()
        self._ensure_directories()
        self.logger.info(f"Config Manager initialized (advanced: {advanced_mode})")
    
    def _detect_config_directory(self) -> Path:
        candidates = [Path.cwd() / "configs", Path.cwd() / "config", Path.home() / ".llm-framework", Path.cwd()]
        for c in candidates:
            if c.exists() and c.is_dir(): return c
        return Path.cwd() / "configs"
    
    def _ensure_directories(self):
        dirs = [self.config_dir, self.config_dir / "environments", self.config_dir / "templates", self.config_dir / "backups"]
        if self.advanced_mode.enabled:
            dirs.extend([self.config_dir / "secrets", self.config_dir / "compliance", self.config_dir / "audit"])
        for d in dirs: ensure_directory(d)

    def _initialize_core_schemas(self):
        schemas = [
            ConfigSchema("targets_dir", str, True, "targets", "Directory for target definitions"),
            ConfigSchema("models_dir", str, True, "models", "Directory for model storage"),
            ConfigSchema("output_dir", str, True, "output", "Output dir"),
            ConfigSchema("cache_dir", str, True, "cache", "Cache dir"),
            ConfigSchema("logs_dir", str, True, "logs", "Logs dir"),
            ConfigSchema("log_level", str, False, "INFO", "Log level"),
            ConfigSchema("max_concurrent_builds", int, False, 2, "Max builds"),
            ConfigSchema("build_timeout", int, False, 3600, "Timeout seconds"),
            ConfigSchema("auto_cleanup", bool, False, True, "Auto cleanup"),
            ConfigSchema("docker_registry", str, False, "ghcr.io", "Registry URL"),
            ConfigSchema("docker_namespace", str, False, "llm-framework", "Namespace"),
            ConfigSchema("gui_theme", str, False, "dark", "GUI theme"),
            ConfigSchema("gui_auto_refresh", bool, False, True, "Auto refresh"),
            ConfigSchema("gui_refresh_interval", int, False, 30, "Refresh interval"),
            ConfigSchema("api_enabled", bool, False, False, "Enable API"),
            ConfigSchema("api_port", int, False, 8000, "API port"),
            ConfigSchema("api_host", str, False, "127.0.0.1", "API host")
        ]
        for s in schemas: self.config_schemas[s.field_name] = s
    
    def load_configuration(self, config_file: Optional[Path] = None) -> bool:
        try:
            self._load_default_configuration()
            if config_file: self._load_config_file(config_file)
            else: self._load_config_files_auto()
            self._load_environment_variables()
            self._validate_configuration()
            return True
        except Exception as e:
            self.logger.error(f"Config load failed: {e}")
            return False
    
    def _load_default_configuration(self):
        src = ConfigSource("default", loaded_at=datetime.now(), priority=0)
        for name, schema in self.config_schemas.items():
            if schema.default_value is not None:
                with self._lock:
                    self.config_values[name] = ConfigValue(name, schema.default_value, src, schema, last_modified=datetime.now())
    
    def _load_config_files_auto(self):
        candidates = [self.config_dir / "framework.yml", self.config_dir / "config.yml", Path.cwd() / "framework.yml"]
        for f in candidates:
            if f.exists():
                try: self._load_config_file(f)
                except Exception as e: self.logger.warning(f"Failed to load {f}: {e}")
    
    def _load_config_file(self, path: Path):
        if not path.exists(): raise FileNotFoundError(f"Config not found: {path}")
        with open(path, 'r') as f:
            if path.suffix in ['.yml', '.yaml']: data = yaml.safe_load(f)
            elif path.suffix == '.json': data = json.load(f)
            else: data = {}
        if not data: return
        src = ConfigSource("file", str(path), datetime.now(), 10)
        self._load_config_data(data, src)
    
    def _load_config_data(self, data: Dict[str, Any], source: ConfigSource):
        for k, v in data.items():
            schema = self.config_schemas.get(k)
            if schema and schema.enterprise_only and not self.advanced_mode.enabled: continue
            with self._lock:
                existing = self.config_values.get(k)
                if not existing or source.priority >= existing.source.priority:
                    self.config_values[k] = ConfigValue(k, v, source, schema, last_modified=datetime.now())

    def _load_environment_variables(self):
        env_source = ConfigSource("environment", loaded_at=datetime.now(), priority=20)
        prefixes = ["LLM_FRAMEWORK_", "FRAMEWORK_", "LLM_"]
        for k, v in os.environ.items():
            key = None
            for p in prefixes:
                if k.startswith(p):
                    key = k[len(p):].lower()
                    break
            if key:
                schema = self.config_schemas.get(key)
                if schema and schema.enterprise_only and not self.advanced_mode.enabled: continue
                try:
                    val = self._convert_env_value(v, schema)
                    with self._lock:
                        self.config_values[key] = ConfigValue(key, val, env_source, schema, last_modified=datetime.now())
                except Exception: pass

    def _convert_env_value(self, val: str, schema: Optional[ConfigSchema]) -> Any:
        if not schema: return val
        try:
            if schema.field_type == bool: return val.lower() in ('true', '1', 'yes', 'on')
            elif schema.field_type == int: return int(val)
            elif schema.field_type == float: return float(val)
            return val
        except: return val

    def _validate_configuration(self):
        for name, schema in self.config_schemas.items():
            if schema.required and name not in self.config_values:
                self.logger.error(f"Missing required config: {name}")

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            val = self.config_values.get(key)
            return val.value if val else default

    def set(self, key: str, value: Any, source_type: str = "override") -> bool:
        schema = self.config_schemas.get(key)
        if schema and schema.enterprise_only and not self.advanced_mode.enabled: return False
        if schema:
            valid, _ = schema.validate_value(value)
            if not valid: return False
        src = ConfigSource(source_type, loaded_at=datetime.now(), priority=30)
        val = ConfigValue(key, value, src, schema, last_modified=datetime.now())
        with self._lock:
            old = self.config_values.get(key)
            self.config_values[key] = val
            if self.advanced_mode.enabled:
                self._track_config_change(key, old.value if old else None, value, source_type)
            if self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES):
                self._notify_change_listeners(key, value)
        return True

    def _track_config_change(self, key: str, old_value: Any, new_value: Any, source: str):
        self.change_history.append({"ts": datetime.now().isoformat(), "key": key, "old": old_value, "new": new_value, "src": source})

    def _notify_change_listeners(self, key: str, value: Any):
        if not self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES): return
        for l in self.change_listeners:
            try: l(key, value)
            except Exception as e: self.logger.warning(f"Listener error: {e}")

    def add_change_listener(self, listener: Callable[[str, Any], None]):
        if self.advanced_mode.is_feature_enabled(AdvancedFeature.DYNAMIC_UPDATES):
            self.change_listeners.append(listener)
    
    def get_all(self, include_secrets: bool = False) -> Dict[str, Any]:
        result = {}
        with self._lock:
            for key, val in self.config_values.items():
                if val.is_secret and not include_secrets: result[k] = "***HIDDEN***"
                else: result[k] = v.value
        return result

if __name__ == "__main__":
    print("ConfigManager module loaded")
