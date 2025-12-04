#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Core Framework Manager
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Updates v2.0.0:
- Version Bump to 2.0.0 (The Brain Update).
- Initialization of Guardian Layers (Consistency, Self-Healing, Telemetry).
- Integration of Deployment and Model Managers.
- Enhanced Configuration Model.
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
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

# --- COMPONENT IMPORTS (Lazy/Optional) ---
try:
    from orchestrator.Core.dataset_manager import DatasetManager
except ImportError: DatasetManager = None

try:
    from orchestrator.Core.rag_manager import RAGManager
except ImportError: RAGManager = None

try:
    from orchestrator.Core.crawler_manager import CrawlerManager
except ImportError: CrawlerManager = None

try:
    from orchestrator.Core.deployment_manager import DeploymentManager
except ImportError: DeploymentManager = None

try:
    from orchestrator.Core.model_manager import ModelManager
except ImportError: ModelManager = None

# v2.0 Guardian Layers
try:
    from orchestrator.Core.consistency_manager import ConsistencyManager
except ImportError: ConsistencyManager = None

try:
    from orchestrator.Core.self_healing_manager import SelfHealingManager
except ImportError: SelfHealingManager = None

try:
    from orchestrator.utils.telemetry import TelemetryManager
except ImportError: TelemetryManager = None


@dataclass
class FrameworkInfo:
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
    min_python_version: str = "3.10"
    min_docker_version: str = "20.10"
    min_memory_gb: int = 8
    min_disk_gb: int = 20
    required_commands: List[str] = None
    def __post_init__(self):
        if self.required_commands is None: self.required_commands = ["docker", "git"]

@dataclass
class FrameworkConfig:
    targets_dir: str = "targets"
    models_dir: str = "models"
    output_dir: str = "output"
    configs_dir: str = "configs"
    cache_dir: str = "cache"
    logs_dir: str = "logs"
    log_level: str = "INFO"
    max_concurrent_builds: int = 2
    build_timeout: int = 3600
    auto_cleanup: bool = True
    docker_registry: str = "ghcr.io"
    docker_namespace: str = "llm-framework"
    default_build_args: Dict[str, str] = None
    gui_theme: str = "dark"
    gui_auto_refresh: bool = True
    gui_refresh_interval: int = 30
    api_enabled: bool = False
    api_port: int = 8000
    api_host: str = "127.0.0.1"
    source_repositories: Dict[str, str] = field(default_factory=dict)
    
    # v1.5+ Features
    enable_rag_knowledge: bool = False
    
    # v1.6+ Crawler Settings
    crawler_respect_robots: bool = True
    crawler_max_depth: int = 2
    crawler_max_pages: int = 50
    input_history: List[str] = field(default_factory=list)
    
    # v2.0+ Brain Settings
    chat_context_limit: int = 4096
    enable_telemetry: bool = False
    offline_mode: bool = False
    preferred_tiny_model: str = "tinyllama_1b"

    def __post_init__(self):
        if self.default_build_args is None: self.default_build_args = {"BUILD_JOBS": "4", "PYTHON_VERSION": "3.11"}

class FrameworkManager:
    def __init__(self, config: Optional[Union[Dict[str, Any], FrameworkConfig]] = None):
        self.logger = get_logger(__name__)
        self._lock = threading.Lock()
        self._initialized = False
        self._shutdown_event = threading.Event()
        
        if isinstance(config, dict):
            known = FrameworkConfig.__annotations__.keys()
            # Safe filtering of unknown keys
            valid_config = {k:v for k,v in config.items() if k in known}
            self.config = FrameworkConfig(**valid_config)
        elif isinstance(config, FrameworkConfig): 
            self.config = config
        else: 
            self.config = FrameworkConfig()
        
        # UPDATE: Version 2.0.0 (The Brain Update)
        self.info = FrameworkInfo("2.0.0", datetime.now().isoformat(), installation_path=str(Path(__file__).parent.parent.parent))
        
        # Components Registry
        self._components = {}
        
        # Manager References (Properties)
        self.dataset_manager = None
        self.rag_manager = None
        self.crawler_manager = None
        self.deployment_manager = None
        self.model_manager = None
        self.consistency_manager = None
        self.healing_manager = None
        self.telemetry_manager = None
        self.config_manager = None # Reference usually passed externally or init here if needed
        
        self._event_queue = queue.Queue()
        self._build_counter = 0
        self._active_builds = {}
        
        self.logger.info(f"Framework Manager initialized (v{self.info.version})")

    def initialize(self) -> bool:
        with self._lock:
            if self._initialized: return True
            try:
                self.logger.info("Initializing...")
                self._validate_system_requirements()
                self._setup_directories()
                self._load_extended_configuration()
                self._initialize_docker()
                self._initialize_core_components()
                
                self._initialized = True
                return True
            except Exception as e:
                self.logger.error(f"Init failed: {e}")
                return False

    def _validate_system_requirements(self):
        req = SystemRequirements()
        if version.parse(f"{sys.version_info.major}.{sys.version_info.minor}") < version.parse(req.min_python_version):
            raise Exception(f"Python {req.min_python_version}+ required")
        for cmd in req.required_commands:
            if not check_command_exists(cmd): 
                # Don't fail hard on windows if git is missing in path but installed, just warn
                self.logger.warning(f"Command might be missing: {cmd}")

    def _setup_directories(self):
        for d in [self.config.targets_dir, self.config.models_dir, self.config.output_dir, self.config.configs_dir, self.config.cache_dir, self.config.logs_dir]:
            ensure_directory(Path(d))

    def _load_extended_configuration(self):
        src_file = Path(self.config.configs_dir) / "project_sources.yml"
        if src_file.exists():
            try:
                with open(src_file, 'r') as f:
                    data = yaml.safe_load(f)
                    if data:
                        self.config.source_repositories = data
            except Exception as e: self.logger.warning(f"Sources load failed: {e}")

    def _initialize_docker(self):
        try:
            c = docker.from_env()
            c.ping()
            self.register_component("docker_client", c)
            self.info.docker_available = True
        except Exception as e:
            self.logger.error(f"Docker init failed: {e}")
            self.info.docker_available = False

    def _initialize_core_components(self):
        """Initializes and registers all internal manager components."""
        
        # 1. Telemetry (First, to catch errors in others)
        if TelemetryManager:
            try:
                self.telemetry_manager = TelemetryManager(self)
                self.register_component("telemetry_manager", self.telemetry_manager)
            except Exception as e: self.logger.error(f"Telemetry init failed: {e}")

        # 2. Dataset Manager
        if DatasetManager:
            try:
                self.dataset_manager = DatasetManager(self)
                self.register_component("dataset_manager", self.dataset_manager)
            except Exception as e: self.logger.error(f"DatasetManager init failed: {e}")

        # 3. Model Manager (Needs to be before RAG/Ditto for offline models)
        if ModelManager:
            try:
                self.model_manager = ModelManager(self)
                self.model_manager.initialize()
                self.register_component("model_manager", self.model_manager)
            except Exception as e: self.logger.error(f"ModelManager init failed: {e}")

        # 4. RAG Manager (Optional)
        if RAGManager:
            if self.config.enable_rag_knowledge:
                try:
                    self.rag_manager = RAGManager(self)
                    self.register_component("rag_manager", self.rag_manager)
                    self.logger.info("RAGManager initialized (Knowledge Base Active)")
                except Exception as e: self.logger.error(f"RAGManager init failed: {e}")
            else:
                self.logger.info("RAGManager disabled via config.")

        # 5. Crawler Manager (Optional)
        if CrawlerManager:
            try:
                self.crawler_manager = CrawlerManager(self)
                self.register_component("crawler_manager", self.crawler_manager)
            except Exception as e: self.logger.error(f"CrawlerManager init failed: {e}")

        # 6. Deployment Manager (v1.7)
        if DeploymentManager:
            try:
                self.deployment_manager = DeploymentManager(self)
                self.register_component("deployment_manager", self.deployment_manager)
            except Exception as e: self.logger.error(f"DeploymentManager init failed: {e}")

        # 7. Consistency Manager (v2.0 Guardian)
        if ConsistencyManager:
            try:
                self.consistency_manager = ConsistencyManager(self)
                self.register_component("consistency_manager", self.consistency_manager)
                self.logger.info("Consistency Manager activated")
            except Exception as e: self.logger.error(f"ConsistencyManager init failed: {e}")

        # 8. Self-Healing Manager (v2.0 Guardian)
        if SelfHealingManager:
            try:
                self.healing_manager = SelfHealingManager(self)
                self.register_component("healing_manager", self.healing_manager)
                self.logger.info("Self-Healing Manager activated")
            except Exception as e: self.logger.error(f"SelfHealingManager init failed: {e}")

    def register_component(self, n, c):
        with self._lock: self._components[n] = c

    def get_component(self, n): return self._components.get(n)

    def validate_target(self, name):
        p = Path(self.config.targets_dir) / name
        if not p.exists(): return {"valid": False, "errors": ["Not found"]}
        return {"valid": True, "target_path": str(p)}

    def create_build_id(self):
        with self._lock: self._build_counter += 1; return f"build_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._build_counter:04d}"

    def register_build(self, bid, data):
        with self._lock: self._active_builds[bid] = data

    def update_build_status(self, bid, stat, prog=None):
        with self._lock:
            if bid in self._active_builds:
                j = self._active_builds[bid]
                if hasattr(j, 'status'): j.status = stat; j.progress = prog or j.progress
                else: j['status'] = stat; j['progress'] = prog or j['progress']

    def get_next_queued_build_status(self):
        with self._lock:
            for j in self._active_builds.values():
                s = getattr(j, 'status', None) or j.get('status')
                if s == "queued": return asdict(j) if hasattr(j, 'id') else j
        return None

    def get_info(self):
        try:
            targets = list(Path(self.config.targets_dir).glob("*"))
            self.info.targets_count = len([t for t in targets if t.is_dir() and not t.name.startswith('_')])
        except: pass
        self.info.active_builds = len(self._active_builds)
        return self.info

    def shutdown(self): self._initialized = False
