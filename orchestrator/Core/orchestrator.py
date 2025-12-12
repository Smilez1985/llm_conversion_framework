#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Core Orchestrator
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Zweck:
Verwaltet den gesamten Build-Lebenszyklus, von der Anfrage bis zum Artefakt.
Integriert Builder, ModuleGenerator und (neu) Self-Healing.
"""

import os
import sys
import json
import logging
import asyncio
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from orchestrator.utils.logging import get_logger
from orchestrator.Core.builder import BuildEngine, BuildJob, BuildStatus, OptimizationLevel, ModelFormat
from orchestrator.Core.module_generator import ModuleGenerator

# NEU: Self-Healing Integration (Optional Import)
try:
    from orchestrator.Core.self_healing_manager import SelfHealingManager, HealingProposal
except ImportError:
    SelfHealingManager = None
    HealingProposal = None

# ============================================================================
# DATENKLASSEN & ENUMS
# ============================================================================

class WorkflowType(Enum):
    SIMPLE_CONVERSION = "simple_conversion"
    FULL_CROSS_COMPILE = "full_cross_compile"
    RAG_OPTIMIZED = "rag_optimized"
    CUSTOM_PIPELINE = "custom_pipeline"

class PriorityLevel(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3
    CRITICAL = 4

class OrchestrationStatus(Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    BUILDING = "building"
    HEALING = "healing" # NEU: System repariert sich selbst
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

@dataclass
class BuildRequest:
    """Repräsentiert eine Anfrage vom User (CLI/GUI)"""
    request_id: str
    workflow_type: WorkflowType
    priority: PriorityLevel
    models: List[str]
    targets: List[str]
    target_formats: List[ModelFormat]
    optimization_level: OptimizationLevel
    quantization_options: List[str]
    parallel_builds: bool
    output_base_dir: str
    description: str = ""
    use_gpu: bool = False
    
    def __post_init__(self):
        if not self.request_id:
            self.request_id = f"req_{uuid.uuid4().hex[:8]}"

@dataclass
class WorkflowState:
    """Aktueller Zustand eines Workflows"""
    request_id: str
    status: OrchestrationStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    current_stage: str = "init"
    total_builds: int = 0
    completed_builds: int = 0
    failed_builds: int = 0
    artifacts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # NEU: Aktiver Heilungsvorschlag für GUI
    healing_proposal: Optional[Any] = None 

    @property
    def progress_percent(self) -> int:
        if self.total_builds == 0: return 0
        return int((self.completed_builds / self.total_builds) * 100)

# ============================================================================
# ORCHESTRATOR KLASSE
# ============================================================================

class LLMOrchestrator:
    def __init__(self, config_manager):
        self.logger = get_logger(__name__)
        self.config = config_manager
        
        # Sub-Engines
        self.build_engine = BuildEngine(config_manager)
        self.module_generator = ModuleGenerator(Path(config_manager.targets_dir))
        
        # State Management
        self._workflows: Dict[str, WorkflowState] = {}
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        
        # NEU: Self-Healing Referenz (wird injected)
        self.self_healing = None 

    async def initialize(self) -> bool:
        """Asynchrone Initialisierung"""
        self.logger.info("Initializing Orchestrator...")
        # Check Docker connectivity via BuildEngine
        if not self.build_engine.check_docker():
            self.logger.error("Docker not ready. Orchestrator functionality limited.")
            return False
        return True

    # --- PUBLIC API ---

    async def submit_build_request(self, request: BuildRequest) -> str:
        """Nimmt einen neuen Build-Auftrag entgegen"""
        async with self._lock:
            # Workflow State erstellen
            state = WorkflowState(
                request_id=request.request_id,
                status=OrchestrationStatus.QUEUED,
                start_time=datetime.now()
            )
            self._workflows[request.request_id] = state
            
            # In Queue packen (Priorität beachten: Negativ, da PriorityQueue min-heap ist)
            # Tuple: (priority_int, timestamp, request)
            await self._queue.put((-request.priority.value, datetime.now().timestamp(), request))
            
            self.logger.info(f"Request {request.request_id} queued (Priority: {request.priority.name})")
            
            # Worker triggern (falls noch nicht läuft)
            self._ensure_worker_running()
            
            return request.request_id

    async def get_workflow_status(self, request_id: str) -> Optional[WorkflowState]:
        """Gibt den aktuellen Status zurück"""
        return self._workflows.get(request_id)

    async def list_workflows(self) -> List[WorkflowState]:
        """Listet alle bekannten Workflows"""
        return list(self._workflows.values())

    async def cancel_request(self, request_id: str) -> bool:
        """Bricht einen laufenden Request ab"""
        if request_id in self._active_tasks:
            self._active_tasks[request_id].cancel()
            if request_id in self._workflows:
                self._workflows[request_id].status = OrchestrationStatus.CANCELLED
            return True
        return False

    def inject_self_healing(self, manager):
        """Dependency Injection für SelfHealingManager"""
        self.self_healing = manager
        self.logger.info("Self-Healing Manager injected into Orchestrator.")

    # --- INTERNAL WORKER ---

    def _ensure_worker_running(self):
        # Einfache Implementierung: Fire & Forget Task pro Request in _process_queue
        # In einer echten Queue würde hier ein dauerhafter Worker-Pool laufen.
        asyncio.create_task(self._process_next_item())

    async def _process_next_item(self):
        if self._queue.empty(): return
        
        _, _, request = await self._queue.get()
        
        # Task erstellen und tracken
        task = asyncio.create_task(self._run_build_pipeline(request))
        self._active_tasks[request.request_id] = task
        
        try:
            await task
        except asyncio.CancelledError:
            self.logger.warning(f"Task {request.request_id} cancelled")
        except Exception as e:
            self.logger.error(f"Task {request.request_id} failed: {e}", exc_info=True)
            if request.request_id in self._workflows:
                self._workflows[request.request_id].status = OrchestrationStatus.ERROR
                self._workflows[request.request_id].errors.append(str(e))
        finally:
            self._active_tasks.pop(request.request_id, None)
            self._queue.task_done()
            # Nächsten Job holen (Rekursion / Loop)
            self._ensure_worker_running()

    async def _run_build_pipeline(self, req: BuildRequest):
        """Die eigentliche Pipeline-Logik"""
        state = self._workflows[req.request_id]
        state.status = OrchestrationStatus.PREPARING
        state.current_stage = "Initialization"
        
        self.logger.info(f"Starting pipeline for {req.request_id}")
        
        # 1. Expand Build Matrix (Models x Targets x Quantizations)
        build_jobs: List[BuildJob] = []
        
        for model in req.models:
            for target in req.targets:
                # Validierung Target
                if not (Path(self.config.targets_dir) / target).exists():
                    state.warnings.append(f"Target '{target}' not found. Skipping.")
                    continue
                
                # Formate
                formats = req.target_formats if req.target_formats else [ModelFormat.GGUF]
                
                for fmt in formats:
                    # Quantization (wenn leer, dann 'default' / 'fp16')
                    quants = req.quantization_options if req.quantization_options else [None]
                    
                    for q in quants:
                        job_id = f"{req.request_id}_{len(build_jobs)+1:03d}"
                        
                        # Pfad-Logik
                        out_dir = Path(req.output_base_dir) / target / model.split("/")[-1]
                        if q: out_dir = out_dir / q
                        
                        job = BuildJob(
                            job_id=job_id,
                            source_model=model,
                            target_architecture=target,
                            target_format=fmt,
                            optimization=req.optimization_level,
                            quantization=q,
                            output_path=str(out_dir),
                            status=BuildStatus.PENDING
                        )
                        build_jobs.append(job)

        state.total_builds = len(build_jobs)
        state.status = OrchestrationStatus.BUILDING
        
        self.logger.info(f"Generated {len(build_jobs)} build jobs.")
        
        # 2. Execution Loop
        
        for job in build_jobs:
            state.current_stage = f"Building {job.source_model} for {job.target_architecture}"
            
            # --- START BUILD ---
            success = await self.build_engine.run_job(job)
            
            # --- SELF-HEALING LOOP (NEU v2.0) ---
            if not success and self.self_healing:
                self.logger.warning(f"Build failed for {job.job_id}. Activating Self-Healing...")
                
                # Update Status for GUI
                state.status = OrchestrationStatus.HEALING
                
                # 1. Log Analyse
                error_log = job.error_log if hasattr(job, 'error_log') else "Unknown Error"
                context = f"Target: {job.target_architecture}, Model: {job.source_model}"
                
                proposal = self.self_healing.analyze_error(error_log, context)
                
                if proposal:
                    state.healing_proposal = proposal # Expose to GUI
                    self.logger.info(f"Healing Proposal: {proposal.fix_command}")
                    
                    # Hier könnte Auto-Fix Logik greifen
                    # z.B. wenn config.auto_heal == True -> apply_fix -> retry
                
                else:
                    self.logger.error("Self-Healing found no solution.")
                
                # Reset Status to continue or fail
                state.status = OrchestrationStatus.BUILDING

            # --- END BUILD ---

            if success:
                state.completed_builds += 1
                state.artifacts.append(job.output_path)
            else:
                state.failed_builds += 1
                state.errors.append(f"Job {job.job_id} failed.")
                if req.priority == PriorityLevel.CRITICAL:
                    self.logger.error("Critical build failed. Aborting pipeline.")
                    state.status = OrchestrationStatus.ERROR
                    return

        # 3. Finalization
        state.end_time = datetime.now()
        if state.failed_builds == 0:
            state.status = OrchestrationStatus.COMPLETED
            state.current_stage = "Done"
        elif state.completed_builds > 0:
            state.status = OrchestrationStatus.COMPLETED # Partial success
            state.current_stage = "Completed with errors"
        else:
            state.status = OrchestrationStatus.ERROR
            state.current_stage = "Failed"
            
        self.logger.info(f"Pipeline finished. Status: {state.status.name}")
