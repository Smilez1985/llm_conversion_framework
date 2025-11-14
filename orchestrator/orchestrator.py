#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Orchestrator
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Central orchestration engine coordinating all framework components.
Manages high-level build workflows, resource allocation, and error recovery.
Container-native with Poetry+VENV, RK3566 MVP support.

Key Responsibilities:
- Coordinate FrameworkManager, BuildEngine, TargetManager, ModelManager
- High-level build workflow orchestration
- Build queue management and resource allocation
- Event system for status updates and monitoring
- Error recovery and retry mechanisms
- Cross-component state synchronization
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
from orchestrator.Core.builder import BuildEngine, BuildConfiguration, BuildProgress, BuildStatus, TargetArch, ModelFormat, OptimizationLevel
from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError, validate_path, validate_config
from orchestrator.utils.helpers import ensure_directory, check_command_exists, safe_json_load


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class OrchestrationStatus(Enum):
    """Orchestrator status enumeration"""
    INITIALIZING = "initializing"
    READY = "ready"
    BUILDING = "building"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"
    ERROR = "error"


class WorkflowType(Enum):
    """Build workflow types"""
    SIMPLE_CONVERSION = "simple_conversion"      # Single model, single target
    BATCH_CONVERSION = "batch_conversion"        # Multiple models, single target
    MULTI_TARGET = "multi_target"                # Single model, multiple targets
    FULL_MATRIX = "full_matrix"                  # Multiple models, multiple targets
    CUSTOM_PIPELINE = "custom_pipeline"          # User-defined workflow


class PriorityLevel(Enum):
    """Build priority levels"""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20
    CRITICAL = 50


class ResourceType(Enum):
    """System resource types"""
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
    """High-level build request"""
    request_id: str
    workflow_type: WorkflowType
    priority: PriorityLevel = PriorityLevel.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    
    # Source configuration
    models: List[str] = field(default_factory=list)  # Model sources
    model_branch: str = "main"
    
    # Target configuration  
    targets: List[TargetArch] = field(default_factory=list)
    target_formats: List[ModelFormat] = field(default_factory=list)
    
    # Build parameters
    optimization_level: OptimizationLevel = OptimizationLevel.BALANCED
    quantization_options: List[str] = field(default_factory=list)
    parallel_builds: bool = True
    max_concurrent: int = 2
    
    # Output configuration
    output_base_dir: str = ""
    output_naming: str = "default"  # default, model_target, custom
    
    # Advanced options
    retry_count: int = 2
    timeout: int = 3600
    cleanup_on_success: bool = True
    cleanup_on_failure: bool = False
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    description: str = ""
    user_id: Optional[str] = None


@dataclass 
class WorkflowProgress:
    """Workflow execution progress"""
    request_id: str
    workflow_type: WorkflowType
    status: OrchestrationStatus
    current_stage: str = ""
    
    # Progress tracking
    total_builds: int = 0
    completed_builds: int = 0
    failed_builds: int = 0
    skipped_builds: int = 0
    
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    
    # Build tracking
    build_ids: List[str] = field(default_factory=list)
    active_builds: Set[str] = field(default_factory=set)
    completed_builds_detail: List[Dict[str, Any]] = field(default_factory=list)
    
    # Logs and errors
    logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def progress_percent(self) -> int:
        """Calculate overall progress percentage"""
        if self.total_builds == 0:
            return 0
        return int((self.completed_builds + self.failed_builds) / self.total_builds * 100)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.completed_builds + self.failed_builds == 0:
            return 0.0
        return self.completed_builds / (self.completed_builds + self.failed_builds) * 100
    
    def add_log(self, message: str, level: str = "INFO"):
        """Add log entry with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.logs.append(log_entry)
    
    def add_error(self, error: str):
        """Add error and log entry"""
        self.errors.append(error)
        self.add_log(f"ERROR: {error}", "ERROR")
    
    def add_warning(self, warning: str):
        """Add warning and log entry"""
        self.warnings.append(warning)
        self.add_log(f"WARNING: {warning}", "WARNING")


@dataclass
class ResourceUsage:
    """System resource usage tracking"""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_usage_gb: float = 0.0
    docker_containers: int = 0
    active_builds: int = 0
    
    # Resource limits
    max_cpu_percent: float = 80.0
    max_memory_percent: float = 80.0
    max_disk_usage_gb: float = 100.0
    max_containers: int = 10
    max_builds: int = 4
    
    def is_resource_available(self, resource_type: ResourceType) -> bool:
        """Check if specific resource is available"""
        if resource_type == ResourceType.CPU:
            return self.cpu_percent < self.max_cpu_percent
        elif resource_type == ResourceType.MEMORY:
            return self.memory_percent < self.max_memory_percent
        elif resource_type == ResourceType.DISK:
            return self.disk_usage_gb < self.max_disk_usage_gb
        elif resource_type == ResourceType.DOCKER:
            return self.docker_containers < self.max_containers
        return True
    
    def can_start_build(self) -> bool:
        """Check if resources allow starting a new build"""
        return (self.active_builds < self.max_builds and
                self.is_resource_available(ResourceType.CPU) and
                self.is_resource_available(ResourceType.MEMORY) and
                self.is_resource_available(ResourceType.DOCKER))


@dataclass
class EventMessage:
    """Event system message"""
    event_type: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ============================================================================
# MAIN ORCHESTRATOR CLASS
# ============================================================================

class LLMOrchestrator:
    """
    Main orchestration engine for the LLM Cross-Compiler Framework.
    
    Coordinates all framework components and manages high-level workflows:
    - Build request processing and queue management
    - Resource allocation and monitoring
    - Cross-component coordination
    - Event system for status updates
    - Error recovery and retry mechanisms
    - Performance optimization
    
    Architecture:
    - Container-native with Poetry+VENV
    - 4-Module pipeline (source→config→convert→target)
    - Multi-target support with RK3566 MVP
    - Event-driven with async operations
    """
    
    def __init__(self, config: Optional[FrameworkConfig] = None):
        """
        Initialize the LLM Orchestrator.
        
        Args:
            config: Framework configuration (uses defaults if None)
        """
        self.logger = get_logger(__name__)
        
        # Core configuration
        self.config = config or FrameworkConfig()
        
        # Component initialization
        self.framework_manager = None
        self.build_engine = None
        self.target_manager = None
        self.model_manager = None
        
        # State management
        self._lock = threading.RLock()
        self._status = OrchestrationStatus.INITIALIZING
        self._shutdown_event = threading.Event()
        
        # Workflow management
        self._workflows: Dict[str, WorkflowProgress] = {}
        self._build_queue = asyncio.Queue()
        self._active_requests: Dict[str, BuildRequest] = {}
        
        # Resource monitoring
        self._resource_usage = ResourceUsage()
        self._resource_monitor_thread = None
        
        # Event system
        self._event_listeners: Dict[str, List[Callable]] = {}
        self._event_queue = queue.Queue()
        self._event_processor_thread = None
        
        # Executors for async operations
        self._workflow_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="workflow")
        self._monitoring_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="monitor")
        
        # Performance metrics
        self._metrics = {
            "total_requests": 0,
            "successful_workflows": 0,
            "failed_workflows": 0,
            "total_builds": 0,
            "successful_builds": 0,
            "failed_builds": 0,
            "average_build_time": 0.0,
            "uptime_start": datetime.now()
        }
        
        self.logger.info("LLM Orchestrator initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize the orchestrator and all components.
        
        Returns:
            bool: True if initialization successful
            
        Raises:
            OrchestrationError: If initialization fails
        """
        try:
            self.logger.info("Initializing LLM Orchestrator...")
            
            with self._lock:
                self._status = OrchestrationStatus.INITIALIZING
            
            # Step 1: Initialize Framework Manager
            await self._initialize_framework_manager()
            
            # Step 2: Initialize Build Engine
            await self._initialize_build_engine()
            
            # Step 3: Initialize Target Manager
            await self._initialize_target_manager()
            
            # Step 4: Initialize Model Manager  
            await self._initialize_model_manager()
            
            # Step 5: Start monitoring services
            await self._start_monitoring_services()
            
            # Step 6: Start event processing
            await self._start_event_processing()
            
            # Step 7: Register signal handlers
            self._register_signal_handlers()
            
            # Mark as ready
            with self._lock:
                self._status = OrchestrationStatus.READY
            
            self._emit_event("orchestrator.initialized", {"status": "ready"})
            self.logger.info("LLM Orchestrator initialization completed")
            
            return True
            
        except Exception as e:
            self._status = OrchestrationStatus.ERROR
            self.logger.error(f"Orchestrator initialization failed: {e}")
            raise OrchestrationError(f"Initialization failed: {e}") from e
    
    async def shutdown(self, timeout: int = 30):
        """
        Gracefully shutdown the orchestrator.
        
        Args:
            timeout: Shutdown timeout in seconds
        """
        self.logger.info("Shutting down LLM Orchestrator...")
        
        with self._lock:
            self._status = OrchestrationStatus.SHUTTING_DOWN
        
        # Signal shutdown
        self._shutdown_event.set()
        
        try:
            # Cancel all active workflows
            await self._cancel_all_workflows()
            
            # Stop monitoring services
            await self._stop_monitoring_services()
            
            # Stop event processing
            await self._stop_event_processing()
            
            # Shutdown components
            await self._shutdown_components()
            
            # Shutdown executors
            self._workflow_executor.shutdown(wait=True, timeout=timeout//2)
            self._monitoring_executor.shutdown(wait=True, timeout=timeout//2)
            
            self.logger.info("LLM Orchestrator shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            raise
    
    @property
    def status(self) -> OrchestrationStatus:
        """Get current orchestrator status"""
        return self._status
    
    @property
    def is_ready(self) -> bool:
        """Check if orchestrator is ready for requests"""
        return self._status == OrchestrationStatus.READY
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Get performance metrics"""
        current_metrics = self._metrics.copy()
        current_metrics["uptime_seconds"] = (datetime.now() - current_metrics["uptime_start"]).total_seconds()
        return current_metrics
    async def submit_build_request(self, request: BuildRequest) -> str:
        """
        Submit a new build request for processing.
        
        Args:
            request: Build request to process
            
        Returns:
            str: Request ID for tracking
            
        Raises:
            OrchestrationError: If request cannot be submitted
        """
        if not self.is_ready:
            raise OrchestrationError(f"Orchestrator not ready (status: {self._status.value})")
        
        # Validate request
        await self._validate_build_request(request)
        
        # Generate request ID if not provided
        if not request.request_id:
            request.request_id = f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        self.logger.info(f"Submitting build request: {request.request_id}")
        
        # Create workflow progress tracker
        workflow_progress = WorkflowProgress(
            request_id=request.request_id,
            workflow_type=request.workflow_type,
            status=OrchestrationStatus.BUILDING,
            start_time=datetime.now()
        )
        
        # Calculate total builds
        total_builds = len(request.models) * len(request.targets) * len(request.target_formats)
        if request.quantization_options:
            total_builds *= len(request.quantization_options)
        
        workflow_progress.total_builds = total_builds
        workflow_progress.add_log(f"Workflow created with {total_builds} total builds")
        
        # Store request and workflow
        with self._lock:
            self._active_requests[request.request_id] = request
            self._workflows[request.request_id] = workflow_progress
            self._metrics["total_requests"] += 1
        
        # Submit to workflow executor
        future = self._workflow_executor.submit(self._execute_workflow, request)
        
        # Emit event
        self._emit_event("workflow.submitted", {
            "request_id": request.request_id,
            "workflow_type": request.workflow_type.value,
            "total_builds": total_builds
        })
        
        return request.request_id
    
    async def get_workflow_status(self, request_id: str) -> Optional[WorkflowProgress]:
        """Get workflow status"""
        return self._workflows.get(request_id)
    
    async def list_workflows(self, active_only: bool = False) -> List[WorkflowProgress]:
        """List all workflows"""
        with self._lock:
            workflows = list(self._workflows.values())
        
        if active_only:
            active_statuses = {OrchestrationStatus.BUILDING, OrchestrationStatus.READY}
            workflows = [w for w in workflows if w.status in active_statuses]
        
        return workflows
    
    async def cancel_workflow(self, request_id: str) -> bool:
        """
        Cancel a running workflow.
        
        Args:
            request_id: Request to cancel
            
        Returns:
            bool: True if cancellation initiated
        """
        workflow = self._workflows.get(request_id)
        if not workflow:
            return False
        
        self.logger.info(f"Cancelling workflow: {request_id}")
        
        # Cancel all active builds in this workflow
        for build_id in workflow.active_builds.copy():
            if self.build_engine:
                self.build_engine.cancel_build(build_id)
        
        # Update workflow status
        workflow.status = OrchestrationStatus.PAUSED
        workflow.end_time = datetime.now()
        workflow.add_log("Workflow cancelled by user")
        
        # Emit event
        self._emit_event("workflow.cancelled", {"request_id": request_id})
        
        return True
    
    async def _validate_build_request(self, request: BuildRequest):
        """
        Validate build request.
        
        Args:
            request: Request to validate
            
        Raises:
            ValidationError: If request is invalid
        """
        errors = []
        
        # Basic validation
        if not request.models:
            errors.append("At least one model is required")
        
        if not request.targets:
            errors.append("At least one target is required")
        
        if not request.target_formats:
            errors.append("At least one target format is required")
        
        if not request.output_base_dir:
            errors.append("Output base directory is required")
        
        # Validate models exist (if they're local paths)
        for model in request.models:
            if model.startswith("/") or model.startswith("./"):
                # Local path
                if not Path(model).exists():
                    errors.append(f"Model path does not exist: {model}")
        
        # Validate targets are supported
        if self.target_manager:
            available_targets = await self.target_manager.list_available_targets()
            available_target_names = {t.value for t in available_targets}
            
            for target in request.targets:
                if target.value not in available_target_names:
                    errors.append(f"Target not available: {target.value}")
        
        # Validate output directory
        try:
            output_path = Path(request.output_base_dir)
            if not output_path.parent.exists():
                errors.append(f"Output directory parent does not exist: {output_path.parent}")
        except Exception as e:
            errors.append(f"Invalid output directory: {e}")
        
        # Validate resource requirements
        if not self._resource_usage.can_start_build():
            errors.append("Insufficient system resources for build")
        
        if errors:
            raise ValidationError(f"Build request validation failed: {'; '.join(errors)}")
    
    def _execute_workflow(self, request: BuildRequest):
        """
        Execute a complete workflow.
        
        Args:
            request: Build request to execute
        """
        request_id = request.request_id
        workflow = self._workflows[request_id]
        
        try:
            workflow.add_log("Starting workflow execution")
            
            # Generate individual build configurations
            build_configs = self._generate_build_configurations(request)
            
            if not build_configs:
                raise OrchestrationError("No build configurations generated")
            
            workflow.add_log(f"Generated {len(build_configs)} build configurations")
            
            # Execute builds based on workflow type
            if request.workflow_type == WorkflowType.SIMPLE_CONVERSION:
                self._execute_simple_workflow(request, workflow, build_configs)
            elif request.workflow_type == WorkflowType.BATCH_CONVERSION:
                self._execute_batch_workflow(request, workflow, build_configs)
            elif request.workflow_type == WorkflowType.MULTI_TARGET:
                self._execute_multi_target_workflow(request, workflow, build_configs)
            elif request.workflow_type == WorkflowType.FULL_MATRIX:
                self._execute_full_matrix_workflow(request, workflow, build_configs)
            else:
                raise OrchestrationError(f"Unsupported workflow type: {request.workflow_type}")
            
            # Mark workflow as completed
            workflow.status = OrchestrationStatus.READY
            workflow.end_time = datetime.now()
            workflow.add_log("Workflow completed successfully")
            
            # Update metrics
            with self._lock:
                self._metrics["successful_workflows"] += 1
            
            # Emit completion event
            self._emit_event("workflow.completed", {
                "request_id": request_id,
                "success_rate": workflow.success_rate,
                "total_builds": workflow.total_builds,
                "completed_builds": workflow.completed_builds
            })
            
        except Exception as e:
            workflow.status = OrchestrationStatus.ERROR
            workflow.end_time = datetime.now()
            workflow.add_error(f"Workflow failed: {str(e)}")
            
            with self._lock:
                self._metrics["failed_workflows"] += 1
            
            self.logger.error(f"Workflow failed: {request_id} - {e}")
            
            # Emit failure event
            self._emit_event("workflow.failed", {
                "request_id": request_id,
                "error": str(e)
            })
    
    def _generate_build_configurations(self, request: BuildRequest) -> List[BuildConfiguration]:
        """
        Generate individual build configurations from request.
        
        Args:
            request: Build request
            
        Returns:
            List[BuildConfiguration]: Individual build configurations
        """
        configs = []
        
        for model in request.models:
            for target in request.targets:
                for target_format in request.target_formats:
                    # Base configuration
                    base_config = {
                        "model_source": model,
                        "model_branch": request.model_branch,
                        "target_arch": target,
                        "target_format": target_format,
                        "optimization_level": request.optimization_level,
                        "parallel_jobs": 4,
                        "build_timeout": request.timeout,
                        "cleanup_after_build": request.cleanup_on_success
                    }
                    
                    # Handle quantization options
                    if request.quantization_options:
                        for quant in request.quantization_options:
                            config = base_config.copy()
                            config["quantization"] = quant
                            config["build_id"] = self._generate_build_id(model, target, target_format, quant)
                            config["output_dir"] = self._generate_output_path(request, model, target, target_format, quant)
                            
                            configs.append(BuildConfiguration(**config))
                    else:
                        config = base_config.copy()
                        config["build_id"] = self._generate_build_id(model, target, target_format)
                        config["output_dir"] = self._generate_output_path(request, model, target, target_format)
                        
                        configs.append(BuildConfiguration(**config))
        
        return configs
    
    def _generate_build_id(self, model: str, target: TargetArch, target_format: ModelFormat, quantization: str = None) -> str:
        """Generate unique build ID"""
        model_name = Path(model).name if "/" in model else model.replace("/", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        parts = [model_name, target.value, target_format.value]
        if quantization:
            parts.append(quantization)
        
        build_suffix = "_".join(parts)
        return f"build_{timestamp}_{build_suffix}_{uuid.uuid4().hex[:8]}"
    
    def _generate_output_path(self, request: BuildRequest, model: str, target: TargetArch, 
                            target_format: ModelFormat, quantization: str = None) -> str:
        """Generate output path for build"""
        base_dir = Path(request.output_base_dir)
        
        if request.output_naming == "model_target":
            model_name = Path(model).name if "/" in model else model.replace("/", "_")
            path_parts = [model_name, target.value, target_format.value]
            if quantization:
                path_parts.append(quantization)
            
            output_path = base_dir / "_".join(path_parts)
        else:
            # Default naming
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = base_dir / f"output_{timestamp}"
        
        return str(output_path)
    
    async def _initialize_framework_manager(self):
        """Initialize Framework Manager"""
        self.logger.info("Initializing Framework Manager...")
        
        try:
            self.framework_manager = FrameworkManager(self.config)
            
            if not self.framework_manager.initialize():
                raise OrchestrationError("Framework Manager initialization failed")
            
            self.logger.info("Framework Manager initialized successfully")
            
        except Exception as e:
            raise OrchestrationError(f"Framework Manager initialization failed: {e}")
    
    async def _initialize_build_engine(self):
        """Initialize Build Engine"""
        self.logger.info("Initializing Build Engine...")
        
        try:
            if not self.framework_manager:
                raise OrchestrationError("Framework Manager not initialized")
            
            self.build_engine = BuildEngine(
                framework_manager=self.framework_manager,
                max_concurrent_builds=self.config.max_concurrent_builds,
                default_timeout=3600
            )
            
            self.logger.info("Build Engine initialized successfully")
            
        except Exception as e:
            raise OrchestrationError(f"Build Engine initialization failed: {e}")
    
    async def _initialize_target_manager(self):
        """Initialize Target Manager"""
        self.logger.info("Initializing Target Manager...")
        
        try:
            # Target Manager will be implemented next
            # For now, create a placeholder
            self.target_manager = None  # Will be TargetManager(self.framework_manager)
            
            self.logger.info("Target Manager initialized successfully")
            
        except Exception as e:
            raise OrchestrationError(f"Target Manager initialization failed: {e}")
    
    async def _initialize_model_manager(self):
        """Initialize Model Manager"""
        self.logger.info("Initializing Model Manager...")
        
        try:
            # Model Manager will be implemented next
            # For now, create a placeholder
            self.model_manager = None  # Will be ModelManager(self.framework_manager)
            
            self.logger.info("Model Manager initialized successfully")
            
        except Exception as e:
            raise OrchestrationError(f"Model Manager initialization failed: {e}")
    def _execute_simple_workflow(self, request: BuildRequest, workflow: WorkflowProgress, 
                                 build_configs: List[BuildConfiguration]):
        """Execute simple single-build workflow"""
        workflow.current_stage = "Executing simple conversion"
        workflow.add_log("Starting simple conversion workflow")
        
        if len(build_configs) != 1:
            raise OrchestrationError(f"Simple workflow expects 1 build, got {len(build_configs)}")
        
        config = build_configs[0]
        self._execute_single_build_with_retry(request, workflow, config)
    
    def _execute_batch_workflow(self, request: BuildRequest, workflow: WorkflowProgress,
                               build_configs: List[BuildConfiguration]):
        """Execute batch workflow (multiple models, same target)"""
        workflow.current_stage = "Executing batch conversion"
        workflow.add_log(f"Starting batch conversion workflow with {len(build_configs)} builds")
        
        if request.parallel_builds:
            self._execute_builds_parallel(request, workflow, build_configs)
        else:
            self._execute_builds_sequential(request, workflow, build_configs)
    
    def _execute_multi_target_workflow(self, request: BuildRequest, workflow: WorkflowProgress,
                                      build_configs: List[BuildConfiguration]):
        """Execute multi-target workflow (same model, multiple targets)"""
        workflow.current_stage = "Executing multi-target conversion"
        workflow.add_log(f"Starting multi-target conversion workflow with {len(build_configs)} builds")
        
        # Group by model for better resource utilization
        model_groups = {}
        for config in build_configs:
            model = config.model_source
            if model not in model_groups:
                model_groups[model] = []
            model_groups[model].append(config)
        
        # Execute each model group
        for model, configs in model_groups.items():
            workflow.add_log(f"Processing model: {model}")
            if request.parallel_builds:
                self._execute_builds_parallel(request, workflow, configs)
            else:
                self._execute_builds_sequential(request, workflow, configs)
    
    def _execute_full_matrix_workflow(self, request: BuildRequest, workflow: WorkflowProgress,
                                     build_configs: List[BuildConfiguration]):
        """Execute full matrix workflow (multiple models, multiple targets)"""
        workflow.current_stage = "Executing full matrix conversion"
        workflow.add_log(f"Starting full matrix conversion workflow with {len(build_configs)} builds")
        
        # Batch builds by priority and resource requirements
        priority_batches = self._create_priority_batches(build_configs, request.max_concurrent)
        
        for batch_num, batch in enumerate(priority_batches, 1):
            workflow.add_log(f"Processing batch {batch_num}/{len(priority_batches)} ({len(batch)} builds)")
            
            if len(batch) == 1 or not request.parallel_builds:
                self._execute_builds_sequential(request, workflow, batch)
            else:
                self._execute_builds_parallel(request, workflow, batch)
            
            # Check for cancellation between batches
            if workflow.status != OrchestrationStatus.BUILDING:
                break
    
    def _execute_builds_parallel(self, request: BuildRequest, workflow: WorkflowProgress,
                                build_configs: List[BuildConfiguration]):
        """Execute builds in parallel"""
        max_parallel = min(request.max_concurrent, self.config.max_concurrent_builds)
        
        # Submit builds to thread pool
        futures = []
        for config in build_configs[:max_parallel]:
            future = self._workflow_executor.submit(
                self._execute_single_build_with_retry, request, workflow, config
            )
            futures.append((future, config))
        
        # Process remaining builds as slots become available
        remaining_configs = build_configs[max_parallel:]
        
        while futures or remaining_configs:
            # Wait for at least one build to complete
            if futures:
                completed_futures = []
                for future, config in futures:
                    if future.done():
                        completed_futures.append((future, config))
                
                # Remove completed futures
                for completed_future, config in completed_futures:
                    futures.remove((completed_future, config))
                    
                    try:
                        completed_future.result()  # This will raise if the build failed
                    except Exception as e:
                        workflow.add_error(f"Parallel build failed: {config.build_id} - {e}")
                
                # Start new builds if we have remaining configs and free slots
                while remaining_configs and len(futures) < max_parallel:
                    config = remaining_configs.pop(0)
                    future = self._workflow_executor.submit(
                        self._execute_single_build_with_retry, request, workflow, config
                    )
                    futures.append((future, config))
            
            # Small delay to prevent busy waiting
            time.sleep(0.1)
    
    def _execute_builds_sequential(self, request: BuildRequest, workflow: WorkflowProgress,
                                  build_configs: List[BuildConfiguration]):
        """Execute builds sequentially"""
        for config in build_configs:
            if workflow.status != OrchestrationStatus.BUILDING:
                break
            
            self._execute_single_build_with_retry(request, workflow, config)
    
    def _execute_single_build_with_retry(self, request: BuildRequest, workflow: WorkflowProgress,
                                        config: BuildConfiguration):
        """Execute a single build with retry logic"""
        build_id = config.build_id
        max_retries = request.retry_count
        retry_count = 0
        
        workflow.add_log(f"Starting build: {build_id}")
        workflow.active_builds.add(build_id)
        
        while retry_count <= max_retries:
            try:
                # Wait for resources if needed
                if not self._wait_for_resources(timeout=300):  # 5 minute timeout
                    raise OrchestrationError("Timeout waiting for resources")
                
                # Start the build
                actual_build_id = self.build_engine.build_model(config)
                workflow.build_ids.append(actual_build_id)
                
                # Monitor build progress
                success = self._monitor_build_progress(actual_build_id, workflow, request.timeout)
                
                if success:
                    workflow.completed_builds += 1
                    workflow.add_log(f"Build completed successfully: {build_id}")
                    
                    # Update metrics
                    with self._lock:
                        self._metrics["successful_builds"] += 1
                        self._metrics["total_builds"] += 1
                    
                    break
                else:
                    raise OrchestrationError("Build failed or timed out")
                
            except Exception as e:
                retry_count += 1
                workflow.add_error(f"Build attempt {retry_count} failed: {build_id} - {e}")
                
                if retry_count <= max_retries:
                    delay = min(60 * retry_count, 300)  # Exponential backoff, max 5 minutes
                    workflow.add_log(f"Retrying build in {delay} seconds...")
                    time.sleep(delay)
                else:
                    workflow.failed_builds += 1
                    workflow.add_error(f"Build failed after {max_retries + 1} attempts: {build_id}")
                    
                    # Update metrics
                    with self._lock:
                        self._metrics["failed_builds"] += 1
                        self._metrics["total_builds"] += 1
                    
                    break
        
        workflow.active_builds.discard(build_id)
    
    def _monitor_build_progress(self, build_id: str, workflow: WorkflowProgress, timeout: int) -> bool:
        """
        Monitor individual build progress.
        
        Args:
            build_id: Build to monitor
            workflow: Workflow progress tracker
            timeout: Build timeout in seconds
            
        Returns:
            bool: True if build completed successfully
        """
        start_time = time.time()
        last_status = None
        
        while time.time() - start_time < timeout:
            if self._shutdown_event.is_set():
                return False
            
            build_status = self.build_engine.get_build_status(build_id)
            if not build_status:
                return False
            
            # Log status changes
            if build_status.status != last_status:
                workflow.add_log(f"Build {build_id}: {build_status.status.value} - {build_status.current_stage}")
                last_status = build_status.status
            
            if build_status.status == BuildStatus.COMPLETED:
                return True
            elif build_status.status == BuildStatus.FAILED:
                return False
            elif build_status.status == BuildStatus.CANCELLED:
                return False
            
            time.sleep(5)  # Check every 5 seconds
        
        # Timeout
        workflow.add_error(f"Build {build_id} timed out after {timeout} seconds")
        self.build_engine.cancel_build(build_id)
        return False
    
    def _wait_for_resources(self, timeout: int = 300) -> bool:
        """
        Wait for sufficient resources to start a build.
        
        Args:
            timeout: Maximum wait time in seconds
            
        Returns:
            bool: True if resources are available
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self._shutdown_event.is_set():
                return False
            
            if self._resource_usage.can_start_build():
                return True
            
            time.sleep(10)  # Check every 10 seconds
        
        return False
    
    def _create_priority_batches(self, build_configs: List[BuildConfiguration], 
                                max_parallel: int) -> List[List[BuildConfiguration]]:
        """Create batches of builds optimized for parallel execution"""
        # For now, simple batching by max_parallel
        # Future enhancement: intelligent batching by target architecture, model size, etc.
        batches = []
        
        for i in range(0, len(build_configs), max_parallel):
            batch = build_configs[i:i + max_parallel]
            batches.append(batch)
        
        return batches
    
    # ========================================================================
    # EVENT SYSTEM
    # ========================================================================
    
    def _emit_event(self, event_type: str, data: Dict[str, Any], source: str = "orchestrator"):
        """
        Emit an event to the event system.
        
        Args:
            event_type: Type of event
            data: Event data
            source: Event source
        """
        event = EventMessage(
            event_type=event_type,
            source=source,
            data=data
        )
        
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            self.logger.warning(f"Event queue full, dropping event: {event_type}")
    
    def add_event_listener(self, event_type: str, callback: Callable[[EventMessage], None]):
        """
        Add an event listener.
        
        Args:
            event_type: Event type to listen for
            callback: Callback function
        """
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        
        self._event_listeners[event_type].append(callback)
        self.logger.debug(f"Added event listener for: {event_type}")
    
    def remove_event_listener(self, event_type: str, callback: Callable[[EventMessage], None]):
        """Remove an event listener"""
        if event_type in self._event_listeners:
            try:
                self._event_listeners[event_type].remove(callback)
            except ValueError:
                pass
    
    async def _start_event_processing(self):
        """Start event processing thread"""
        self._event_processor_thread = threading.Thread(
            target=self._process_events,
            name="event-processor",
            daemon=True
        )
        self._event_processor_thread.start()
        self.logger.info("Event processing started")
    
    async def _stop_event_processing(self):
        """Stop event processing"""
        if self._event_processor_thread and self._event_processor_thread.is_alive():
            # Signal thread to stop (it will check _shutdown_event)
            self._event_processor_thread.join(timeout=5)
        
        self.logger.info("Event processing stopped")
    
    def _process_events(self):
        """Process events from the event queue"""
        while not self._shutdown_event.is_set():
            try:
                # Get event with timeout
                event = self._event_queue.get(timeout=1)
                
                # Dispatch to listeners
                listeners = self._event_listeners.get(event.event_type, [])
                for listener in listeners:
                    try:
                        listener(event)
                    except Exception as e:
                        self.logger.error(f"Event listener error: {e}")
                
                # Mark task as done
                self._event_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Event processing error: {e}")
    
    # ========================================================================
    # RESOURCE MONITORING
    # ========================================================================
    
    async def _start_monitoring_services(self):
        """Start resource monitoring services"""
        self._resource_monitor_thread = threading.Thread(
            target=self._monitor_resources,
            name="resource-monitor", 
            daemon=True
        )
        self._resource_monitor_thread.start()
        self.logger.info("Resource monitoring started")
    
    async def _stop_monitoring_services(self):
        """Stop monitoring services"""
        if self._resource_monitor_thread and self._resource_monitor_thread.is_alive():
            self._resource_monitor_thread.join(timeout=5)
        
        self.logger.info("Resource monitoring stopped")
    
    def _monitor_resources(self):
        """Monitor system resources"""
        while not self._shutdown_event.is_set():
            try:
                self._update_resource_usage()
                
                # Check for resource alerts
                self._check_resource_alerts()
                
                time.sleep(30)  # Update every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Resource monitoring error: {e}")
                time.sleep(60)  # Wait longer on error
    
    def _update_resource_usage(self):
        """Update current resource usage"""
        try:
            import psutil
            
            # CPU usage
            self._resource_usage.cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self._resource_usage.memory_percent = memory.percent
            
            # Disk usage (framework directory)
            disk = psutil.disk_usage(str(self.framework_manager.info.installation_path))
            self._resource_usage.disk_usage_gb = (disk.total - disk.free) / (1024**3)
            
            # Docker containers (if available)
            if self.framework_manager and self.framework_manager.get_component("docker_client"):
                docker_client = self.framework_manager.get_component("docker_client")
                containers = docker_client.containers.list()
                self._resource_usage.docker_containers = len(containers)
            
            # Active builds
            self._resource_usage.active_builds = len([
                w for w in self._workflows.values() 
                if w.status == OrchestrationStatus.BUILDING
            ])
            
        except ImportError:
            # psutil not available
            pass
        except Exception as e:
            self.logger.warning(f"Resource usage update failed: {e}")
    
    def _check_resource_alerts(self):
        """Check for resource usage alerts"""
        usage = self._resource_usage
        
        # CPU alert
        if usage.cpu_percent > 90:
            self._emit_event("resource.alert", {
                "resource": "cpu",
                "usage_percent": usage.cpu_percent,
                "threshold": 90
            })
        
        # Memory alert
        if usage.memory_percent > 90:
            self._emit_event("resource.alert", {
                "resource": "memory", 
                "usage_percent": usage.memory_percent,
                "threshold": 90
            })
        
        # Disk alert
        if usage.disk_usage_gb > usage.max_disk_usage_gb * 0.9:
            self._emit_event("resource.alert", {
                "resource": "disk",
                "usage_gb": usage.disk_usage_gb,
                "threshold_gb": usage.max_disk_usage_gb * 0.9
            })
    
    def get_resource_usage(self) -> ResourceUsage:
        """Get current resource usage"""
        return self._resource_usage
    # ========================================================================
    # SHUTDOWN AND CLEANUP
    # ========================================================================
    
    async def _cancel_all_workflows(self):
        """Cancel all active workflows"""
        self.logger.info("Cancelling all active workflows...")
        
        active_workflows = [
            w for w in self._workflows.values() 
            if w.status == OrchestrationStatus.BUILDING
        ]
        
        for workflow in active_workflows:
            try:
                await self.cancel_workflow(workflow.request_id)
                self.logger.debug(f"Cancelled workflow: {workflow.request_id}")
            except Exception as e:
                self.logger.error(f"Failed to cancel workflow {workflow.request_id}: {e}")
        
        # Wait for workflows to finish cancelling
        timeout = 30
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            active_count = len([
                w for w in self._workflows.values() 
                if w.status == OrchestrationStatus.BUILDING
            ])
            
            if active_count == 0:
                break
            
            await asyncio.sleep(1)
        
        self.logger.info(f"Cancelled {len(active_workflows)} workflows")
    
    async def _shutdown_components(self):
        """Shutdown all framework components"""
        self.logger.info("Shutting down framework components...")
        
        # Shutdown Build Engine
        if self.build_engine:
            try:
                self.build_engine.shutdown()
                self.logger.debug("Build Engine shutdown completed")
            except Exception as e:
                self.logger.error(f"Build Engine shutdown error: {e}")
        
        # Shutdown Target Manager
        if self.target_manager:
            try:
                # target_manager.shutdown() when implemented
                self.logger.debug("Target Manager shutdown completed")
            except Exception as e:
                self.logger.error(f"Target Manager shutdown error: {e}")
        
        # Shutdown Model Manager
        if self.model_manager:
            try:
                # model_manager.shutdown() when implemented
                self.logger.debug("Model Manager shutdown completed")
            except Exception as e:
                self.logger.error(f"Model Manager shutdown error: {e}")
        
        # Shutdown Framework Manager
        if self.framework_manager:
            try:
                self.framework_manager.shutdown()
                self.logger.debug("Framework Manager shutdown completed")
            except Exception as e:
                self.logger.error(f"Framework Manager shutdown error: {e}")
        
        self.logger.info("All components shutdown completed")
    
    def _register_signal_handlers(self):
        """Register signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            
            # Create new event loop for shutdown if needed
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Schedule shutdown
            loop.create_task(self.shutdown())
        
        # Register handlers for common signals
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Termination
        
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal_handler)  # Hangup (Unix only)
        
        self.logger.debug("Signal handlers registered")
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_workflow_summary(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive workflow summary.
        
        Args:
            request_id: Request ID
            
        Returns:
            dict: Workflow summary or None if not found
        """
        workflow = self._workflows.get(request_id)
        if not workflow:
            return None
        
        request = self._active_requests.get(request_id)
        
        # Calculate timing information
        duration = None
        if workflow.start_time:
            end_time = workflow.end_time or datetime.now()
            duration = (end_time - workflow.start_time).total_seconds()
        
        # Estimate remaining time
        estimated_remaining = None
        if (workflow.status == OrchestrationStatus.BUILDING and 
            workflow.completed_builds > 0 and duration):
            
            avg_time_per_build = duration / workflow.completed_builds
            remaining_builds = workflow.total_builds - workflow.completed_builds - workflow.failed_builds
            estimated_remaining = avg_time_per_build * remaining_builds
        
        summary = {
            "request_id": request_id,
            "workflow_type": workflow.workflow_type.value,
            "status": workflow.status.value,
            "progress": {
                "total_builds": workflow.total_builds,
                "completed_builds": workflow.completed_builds,
                "failed_builds": workflow.failed_builds,
                "active_builds": len(workflow.active_builds),
                "progress_percent": workflow.progress_percent,
                "success_rate": workflow.success_rate
            },
            "timing": {
                "start_time": workflow.start_time.isoformat() if workflow.start_time else None,
                "end_time": workflow.end_time.isoformat() if workflow.end_time else None,
                "duration_seconds": duration,
                "estimated_remaining_seconds": estimated_remaining
            },
            "statistics": {
                "error_count": len(workflow.errors),
                "warning_count": len(workflow.warnings),
                "log_entries": len(workflow.logs)
            }
        }
        
        # Add request details if available
        if request:
            summary["request"] = {
                "models": request.models,
                "targets": [t.value for t in request.targets],
                "target_formats": [f.value for f in request.target_formats],
                "optimization_level": request.optimization_level.value,
                "quantization_options": request.quantization_options,
                "priority": request.priority.value,
                "tags": request.tags,
                "description": request.description
            }
        
        return summary
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            "orchestrator": {
                "status": self._status.value,
                "uptime_seconds": (datetime.now() - self._metrics["uptime_start"]).total_seconds(),
                "ready": self.is_ready
            },
            "workflows": {
                "total": len(self._workflows),
                "active": len([w for w in self._workflows.values() if w.status == OrchestrationStatus.BUILDING]),
                "completed": len([w for w in self._workflows.values() if w.status == OrchestrationStatus.READY]),
                "failed": len([w for w in self._workflows.values() if w.status == OrchestrationStatus.ERROR])
            },
            "resources": {
                "cpu_percent": self._resource_usage.cpu_percent,
                "memory_percent": self._resource_usage.memory_percent,
                "disk_usage_gb": self._resource_usage.disk_usage_gb,
                "docker_containers": self._resource_usage.docker_containers,
                "active_builds": self._resource_usage.active_builds,
                "can_start_build": self._resource_usage.can_start_build()
            },
            "components": {
                "framework_manager": self.framework_manager is not None,
                "build_engine": self.build_engine is not None,
                "target_manager": self.target_manager is not None,
                "model_manager": self.model_manager is not None
            },
            "metrics": self.metrics
        }
    
    def cleanup_completed_workflows(self, max_age_hours: int = 24):
        """
        Clean up old completed workflows.
        
        Args:
            max_age_hours: Maximum age in hours for completed workflows
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        workflows_to_remove = []
        
        for request_id, workflow in self._workflows.items():
            if (workflow.status in [OrchestrationStatus.READY, OrchestrationStatus.ERROR] and
                workflow.end_time and workflow.end_time < cutoff_time):
                workflows_to_remove.append(request_id)
        
        for request_id in workflows_to_remove:
            del self._workflows[request_id]
            if request_id in self._active_requests:
                del self._active_requests[request_id]
            
            self.logger.debug(f"Cleaned up old workflow: {request_id}")
        
        if workflows_to_remove:
            self.logger.info(f"Cleaned up {len(workflows_to_remove)} old workflows")
    
    def export_workflow_report(self, request_id: str, output_path: str) -> bool:
        """
        Export detailed workflow report.
        
        Args:
            request_id: Workflow to export
            output_path: Output file path
            
        Returns:
            bool: True if export successful
        """
        try:
            summary = self.get_workflow_summary(request_id)
            if not summary:
                return False
            
            workflow = self._workflows[request_id]
            
            # Create detailed report
            report = {
                "metadata": {
                    "export_time": datetime.now().isoformat(),
                    "framework_version": self.framework_manager.info.version if self.framework_manager else "unknown",
                    "report_format_version": "1.0"
                },
                "summary": summary,
                "detailed_logs": workflow.logs,
                "errors": workflow.errors,
                "warnings": workflow.warnings,
                "build_details": workflow.completed_builds_detail
            }
            
            # Write report
            output_file = Path(output_path)
            ensure_directory(output_file.parent)
            
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(f"Workflow report exported: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export workflow report: {e}")
            return False


# ============================================================================
# EXCEPTION CLASSES
# ============================================================================

class OrchestrationError(Exception):
    """Base exception for orchestration errors"""
    pass


class WorkflowError(OrchestrationError):
    """Exception raised for workflow-specific errors"""
    pass


class ResourceError(OrchestrationError):
    """Exception raised for resource-related errors"""
    pass


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_build_request(
    models: Union[str, List[str]],
    targets: Union[TargetArch, List[TargetArch]],
    target_formats: Union[ModelFormat, List[ModelFormat]],
    output_base_dir: str,
    workflow_type: WorkflowType = None,
    **kwargs
) -> BuildRequest:
    """
    Create a build request with sensible defaults.
    
    Args:
        models: Model(s) to convert
        targets: Target architecture(s)
        target_formats: Target format(s)
        output_base_dir: Base output directory
        workflow_type: Workflow type (auto-detected if None)
        **kwargs: Additional request options
        
    Returns:
        BuildRequest: Complete build request
    """
    # Normalize inputs to lists
    if isinstance(models, str):
        models = [models]
    if isinstance(targets, TargetArch):
        targets = [targets]
    if isinstance(target_formats, ModelFormat):
        target_formats = [target_formats]
    
    # Auto-detect workflow type if not specified
    if workflow_type is None:
        if len(models) == 1 and len(targets) == 1 and len(target_formats) == 1:
            workflow_type = WorkflowType.SIMPLE_CONVERSION
        elif len(models) > 1 and len(targets) == 1:
            workflow_type = WorkflowType.BATCH_CONVERSION
        elif len(models) == 1 and (len(targets) > 1 or len(target_formats) > 1):
            workflow_type = WorkflowType.MULTI_TARGET
        else:
            workflow_type = WorkflowType.FULL_MATRIX
    
    # Generate request ID
    request_id = f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    return BuildRequest(
        request_id=request_id,
        workflow_type=workflow_type,
        models=models,
        targets=targets,
        target_formats=target_formats,
        output_base_dir=output_base_dir,
        **kwargs
    )


def validate_orchestrator_requirements() -> Dict[str, Any]:
    """
    Validate system requirements for orchestrator.
    
    Returns:
        dict: Validation results
    """
    requirements = {
        "python_version": False,
        "dependencies": {},
        "system_resources": {},
        "errors": [],
        "warnings": []
    }
    
    # Check Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if version.parse(python_version) >= version.parse("3.10"):
        requirements["python_version"] = True
    else:
        requirements["errors"].append(f"Python 3.10+ required, found {python_version}")
    
    # Check dependencies
    deps_to_check = [
        ("docker", "Docker Python library"),
        ("yaml", "PyYAML library"),
        ("psutil", "psutil library (optional for resource monitoring)")
    ]
    
    for module_name, description in deps_to_check:
        try:
            __import__(module_name)
            requirements["dependencies"][module_name] = True
        except ImportError:
            requirements["dependencies"][module_name] = False
            if module_name == "psutil":
                requirements["warnings"].append(f"{description} not available - resource monitoring disabled")
            else:
                requirements["errors"].append(f"{description} not available")
    
    # Check system resources
    try:
        import psutil
        
        # Memory check
        memory = psutil.virtual_memory()
        requirements["system_resources"]["memory_gb"] = memory.total / (1024**3)
        
        if memory.total < 8 * (1024**3):  # 8GB minimum
            requirements["warnings"].append("Less than 8GB RAM available - performance may be limited")
        
        # Disk space check
        disk = psutil.disk_usage('/')
        requirements["system_resources"]["disk_free_gb"] = disk.free / (1024**3)
        
        if disk.free < 20 * (1024**3):  # 20GB minimum
            requirements["warnings"].append("Less than 20GB free disk space - may limit build capabilities")
        
        # CPU count
        requirements["system_resources"]["cpu_count"] = psutil.cpu_count()
        
    except ImportError:
        requirements["warnings"].append("psutil not available - cannot check system resources")
    
    return requirements


async def create_orchestrator_with_validation(config: Optional[FrameworkConfig] = None) -> LLMOrchestrator:
    """
    Create and initialize orchestrator with full validation.
    
    Args:
        config: Framework configuration
        
    Returns:
        LLMOrchestrator: Initialized orchestrator
        
    Raises:
        OrchestrationError: If validation or initialization fails
    """
    # Validate requirements
    validation_result = validate_orchestrator_requirements()
    
    if validation_result["errors"]:
        raise OrchestrationError(f"Validation failed: {'; '.join(validation_result['errors'])}")
    
    # Create orchestrator
    orchestrator = LLMOrchestrator(config)
    
    # Initialize
    success = await orchestrator.initialize()
    if not success:
        raise OrchestrationError("Orchestrator initialization failed")
    
    return orchestrator