#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Orchestrator
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
"""

import os
import sys
import json
import logging
import asyncio
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
import queue
import signal

import yaml
from packaging import version

from orchestrator.Core.framework import FrameworkManager, FrameworkConfig, FrameworkError
from orchestrator.Core.builder import BuildEngine, BuildConfiguration, BuildProgress, BuildStatus, ModelFormat, OptimizationLevel
from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory, check_command_exists, safe_json_load


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class OrchestrationStatus(Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    BUILDING = "building"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"
    ERROR = "error"

class WorkflowType(Enum):
    SIMPLE_CONVERSION = "simple_conversion"
    BATCH_CONVERSION = "batch_conversion"
    MULTI_TARGET = "multi_target"
    FULL_MATRIX = "full_matrix"
    CUSTOM_PIPELINE = "custom_pipeline"

class PriorityLevel(Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20
    CRITICAL = 50

class ResourceType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    DOCKER = "docker"
    NETWORK = "network"

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class BuildRequest:
    request_id: str
    workflow_type: WorkflowType
    priority: PriorityLevel = PriorityLevel.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    models: List[str] = field(default_factory=list)
    model_branch: str = "main"
    targets: List[str] = field(default_factory=list) # MODULAR: List of strings
    target_formats: List[ModelFormat] = field(default_factory=list)
    optimization_level: OptimizationLevel = OptimizationLevel.BALANCED
    quantization_options: List[str] = field(default_factory=list)
    parallel_builds: bool = True
    max_concurrent: int = 2
    output_base_dir: str = ""
    output_naming: str = "default"
    retry_count: int = 2
    timeout: int = 3600
    cleanup_on_success: bool = True
    cleanup_on_failure: bool = False
    tags: List[str] = field(default_factory=list)
    description: str = ""
    user_id: Optional[str] = None

@dataclass 
class WorkflowProgress:
    request_id: str
    workflow_type: WorkflowType
    status: OrchestrationStatus
    current_stage: str = ""
    total_builds: int = 0
    completed_builds: int = 0
    failed_builds: int = 0
    skipped_builds: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    build_ids: List[str] = field(default_factory=list)
    active_builds: Set[str] = field(default_factory=set)
    completed_builds_detail: List[Dict[str, Any]] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def progress_percent(self) -> int:
        if self.total_builds == 0: return 0
        return int((self.completed_builds + self.failed_builds) / self.total_builds * 100)
    
    @property
    def success_rate(self) -> float:
        if self.completed_builds + self.failed_builds == 0: return 0.0
        return self.completed_builds / (self.completed_builds + self.failed_builds) * 100
    
    def add_log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{timestamp}] [{level}] {message}")
    
    def add_error(self, error: str):
        self.errors.append(error); self.add_log(f"ERROR: {error}", "ERROR")
    
    def add_warning(self, warning: str):
        self.warnings.append(warning); self.add_log(f"WARNING: {warning}", "WARNING")

@dataclass
class ResourceUsage:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_usage_gb: float = 0.0
    docker_containers: int = 0
    active_builds: int = 0
    max_cpu_percent: float = 80.0
    max_memory_percent: float = 80.0
    max_disk_usage_gb: float = 100.0
    max_containers: int = 10
    max_builds: int = 4
    
    def is_resource_available(self, resource_type: ResourceType) -> bool:
        if resource_type == ResourceType.CPU: return self.cpu_percent < self.max_cpu_percent
        elif resource_type == ResourceType.MEMORY: return self.memory_percent < self.max_memory_percent
        elif resource_type == ResourceType.DISK: return self.disk_usage_gb < self.max_disk_usage_gb
        elif resource_type == ResourceType.DOCKER: return self.docker_containers < self.max_containers
        return True
    
    def can_start_build(self) -> bool:
        return (self.active_builds < self.max_builds and self.is_resource_available(ResourceType.CPU) and self.is_resource_available(ResourceType.MEMORY))

@dataclass
class EventMessage:
    event_type: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

class LLMOrchestrator:
    def __init__(self, config: Optional[FrameworkConfig] = None):
        self.logger = get_logger(__name__)
        self.config = config or FrameworkConfig()
        self.framework_manager = None
        self.build_engine = None
        self.target_manager = None
        self.model_manager = None
        self._lock = threading.RLock()
        self._status = OrchestrationStatus.INITIALIZING
        self._shutdown_event = threading.Event()
        self._workflows: Dict[str, WorkflowProgress] = {}
        self._build_queue = asyncio.Queue()
        self._active_requests: Dict[str, BuildRequest] = {}
        self._resource_usage = ResourceUsage()
        self._resource_monitor_thread = None
        self._event_listeners: Dict[str, List[Callable]] = {}
        self._event_queue = queue.Queue()
        self._event_processor_thread = None
        self._workflow_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="workflow")
        self._monitoring_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="monitor")
        self._metrics = {"total_requests": 0, "successful_workflows": 0, "failed_workflows": 0, "total_builds": 0, "successful_builds": 0, "failed_builds": 0, "average_build_time": 0.0, "uptime_start": datetime.now()}
        self.logger.info("LLM Orchestrator initialized")
    
    async def initialize(self) -> bool:
        try:
            self.logger.info("Initializing LLM Orchestrator...")
            with self._lock: self._status = OrchestrationStatus.INITIALIZING
            self.framework_manager = FrameworkManager(self.config)
            if not self.framework_manager.initialize(): raise Exception("Framework Manager init failed")
            self.build_engine = BuildEngine(self.framework_manager, self.config.max_concurrent_builds)
            # Start services
            self._start_monitoring()
            with self._lock: self._status = OrchestrationStatus.READY
            return True
        except Exception as e:
            self._status = OrchestrationStatus.ERROR
            self.logger.error(f"Orchestrator initialization failed: {e}")
            return False
    
    def _start_monitoring(self):
        pass # Monitoring logic placeholder

    async def submit_build_request(self, request: BuildRequest) -> str:
        if not self._status == OrchestrationStatus.READY: raise Exception("Orchestrator not ready")
        if not request.request_id: request.request_id = f"req_{uuid.uuid4().hex[:8]}"
        
        workflow = WorkflowProgress(request.request_id, request.workflow_type, OrchestrationStatus.BUILDING, start_time=datetime.now())
        workflow.total_builds = len(request.models) * len(request.targets)
        
        with self._lock:
            self._active_requests[request.request_id] = request
            self._workflows[request.request_id] = workflow
            
        self._workflow_executor.submit(self._execute_workflow, request)
        return request.request_id

    def _execute_workflow(self, request: BuildRequest):
        wf = self._workflows[request.request_id]
        try:
            configs = []
            for m in request.models:
                for t in request.targets: # t is String now!
                    cfg = BuildConfiguration(
                        build_id=f"bld_{uuid.uuid4().hex[:6]}",
                        timestamp=datetime.now().isoformat(),
                        model_source=m,
                        target_arch=t, # Pass string
                        target_format=request.target_formats[0],
                        output_dir=request.output_base_dir,
                        quantization=request.quantization_options[0] if request.quantization_options else None
                    )
                    configs.append(cfg)
            
            for c in configs:
                self.build_engine.build_model(c)
                wf.completed_builds += 1
            
            wf.status = OrchestrationStatus.READY
            
        except Exception as e:
            wf.status = OrchestrationStatus.ERROR
            wf.add_error(str(e))

    async def get_workflow_status(self, rid: str): return self._workflows.get(rid)
    async def list_workflows(self): return list(self._workflows.values())
