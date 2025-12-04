#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Orchestrator
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Updates v2.0.0:
- Integrated Consistency Manager (Pre-Flight Checks).
- Integrated Self-Healing Manager (Post-Fail Recovery).
- Enhanced Workflow Logic with 'Guardian Layers'.
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

# v2.0: Guardian Layers
try:
    from orchestrator.Core.consistency_manager import ConsistencyManager, ConsistencyIssue
except ImportError:
    ConsistencyManager = None

try:
    from orchestrator.Core.self_healing_manager import SelfHealingManager, HealingProposal
except ImportError:
    SelfHealingManager = None


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class OrchestrationStatus(Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    BUILDING = "building"
    PAUSED = "paused"
    HEALING = "healing"           # v2.0: Analysis in progress
    CONSISTENCY_CHECK = "checking" # v2.0: Pre-flight check
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
    targets: List[str] = field(default_factory=list) 
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
    use_gpu: bool = False

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
    
    # v2.0 Data
    consistency_issues: List[Any] = field(default_factory=list)
    healing_proposal: Optional[Any] = None 
    
    @property
    def progress_percent(self) -> int:
        if self.total_builds == 0: return 0
        return int((self.completed_builds + self.failed_builds + self.skipped_builds) / self.total_builds * 100)
    
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

class LLMOrchestrator:
    def __init__(self, config: Optional[FrameworkConfig] = None):
        self.logger = get_logger(__name__)
        self.config = config or FrameworkConfig()
        self.framework_manager = None
        self.build_engine = None
        
        # Managers
        self.target_manager = None
        self.model_manager = None
        self.consistency_manager = None # v2.0
        self.healing_manager = None     # v2.0
        
        self._lock = threading.RLock()
        self._status = OrchestrationStatus.INITIALIZING
        self._shutdown_event = threading.Event()
        self._workflows: Dict[str, WorkflowProgress] = {}
        self._build_queue = asyncio.Queue()
        self._active_requests: Dict[str, BuildRequest] = {}
        self._resource_usage = ResourceUsage()
        self._resource_monitor_thread = None
        self._event_listeners: Dict[str, List[Callable]] = {}
        self._workflow_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="workflow")
        self._monitoring_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="monitor")
        self._metrics = {"total_requests": 0, "successful_workflows": 0, "failed_workflows": 0, "total_builds": 0, "uptime_start": datetime.now()}
        self.logger.info("LLM Orchestrator initialized")
    
    async def initialize(self) -> bool:
        try:
            self.logger.info("Initializing LLM Orchestrator...")
            with self._lock: self._status = OrchestrationStatus.INITIALIZING
            
            self.framework_manager = FrameworkManager(self.config)
            if not self.framework_manager.initialize(): raise Exception("Framework Manager init failed")
            
            self.build_engine = BuildEngine(self.framework_manager, self.config.max_concurrent_builds)
            
            # v2.0: Guardian Layers Initialization
            if ConsistencyManager:
                self.consistency_manager = ConsistencyManager(self.framework_manager)
                self.logger.info("Consistency Manager (Pre-Flight) activated")
                
            if SelfHealingManager:
                self.healing_manager = SelfHealingManager(self.framework_manager)
                self.logger.info("Self-Healing Manager (Post-Fail) activated")

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
            # Config Generation
            for m in request.models:
                for t in request.targets:
                    cfg = BuildConfiguration(
                        build_id=f"bld_{uuid.uuid4().hex[:6]}",
                        timestamp=datetime.now().isoformat(),
                        model_source=m,
                        target_arch=t,
                        target_format=request.target_formats[0] if request.target_formats else ModelFormat.GGUF,
                        output_dir=request.output_base_dir,
                        quantization=request.quantization_options[0] if request.quantization_options else None,
                        use_gpu=request.use_gpu
                    )
                    configs.append(cfg)
            
            # Sequential or Parallel Execution
            for c in configs:
                # --- 1. CONSISTENCY CHECK (Pre-Flight) ---
                if self.consistency_manager:
                    wf.status = OrchestrationStatus.CONSISTENCY_CHECK
                    
                    # Convert BuildConfig to Dict for Checker
                    check_cfg = {
                        "target": c.target_arch,
                        "quantization": c.quantization,
                        "format": c.target_format.value,
                        "model_name": c.model_source
                    }
                    
                    issues = self.consistency_manager.check_build_compatibility(check_cfg)
                    
                    # If CRITICAL Error found -> Skip Build
                    critical_errors = [i for i in issues if i.severity == "ERROR"]
                    if critical_errors:
                        msg = f"Skipped build for {c.target_arch}: {critical_errors[0].message}"
                        self.logger.error(msg)
                        wf.add_error(msg)
                        wf.consistency_issues.extend(critical_errors)
                        wf.skipped_builds += 1
                        continue # Skip this config
                    
                    # Warnings -> Log but proceed
                    warnings = [i for i in issues if i.severity == "WARNING"]
                    if warnings:
                        for w in warnings:
                            wf.add_warning(f"Consistency Warning: {w.message}")

                # --- 2. BUILD EXECUTION ---
                wf.status = OrchestrationStatus.BUILDING
                try:
                    build_id = self.build_engine.build_model(c)
                    
                    # Wait for completion (Blocking in this thread, async in architecture)
                    success = self._wait_for_build(build_id)
                    
                    if success:
                        wf.completed_builds += 1
                    else:
                        wf.failed_builds += 1
                        
                        # --- 3. SELF HEALING (Post-Fail) ---
                        if self.healing_manager:
                            self.logger.warning(f"Build {build_id} failed. Triggering Self-Healing Diagnosis...")
                            wf.status = OrchestrationStatus.HEALING
                            
                            # Fetch Logs
                            prog = self.build_engine.get_build_status(build_id)
                            error_log = "\n".join(prog.logs[-50:]) if prog else "Unknown Error"
                            
                            # Ask Ditto
                            proposal = self.healing_manager.analyze_error(error_log, f"Build: {c.target_arch} / {c.model_source}")
                            
                            if proposal:
                                wf.healing_proposal = proposal
                                msg = f"Healing Proposal: {proposal.fix_command} ({proposal.error_summary})"
                                wf.add_warning(msg)
                                self.logger.info(f"Self-Healing Proposed: {proposal.fix_command}")
                                # In automated CLI mode, we might just log it. 
                                # In GUI mode, DockerManager handles the signal emission.
                            else:
                                self.logger.warning("Self-Healing: No fix found.")

                except Exception as e:
                    self.logger.error(f"Build Execution Error: {e}")
                    wf.failed_builds += 1
            
            wf.status = OrchestrationStatus.READY
            wf.end_time = datetime.now()
            
        except Exception as e:
            wf.status = OrchestrationStatus.ERROR
            wf.add_error(str(e))

    def _wait_for_build(self, build_id: str, timeout=3600) -> bool:
        """Helper to wait for a build in the thread pool."""
        start = time.time()
        while time.time() - start < timeout:
            status = self.build_engine.get_build_status(build_id)
            if not status: return False
            
            if status.status == BuildStatus.COMPLETED:
                return True
            if status.status in [BuildStatus.FAILED, BuildStatus.CANCELLED]:
                return False
            
            time.sleep(1)
        return False

    async def get_workflow_status(self, rid: str): return self._workflows.get(rid)
    async def list_workflows(self): return list(self._workflows.values())
