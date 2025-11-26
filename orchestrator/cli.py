#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Command Line Interface
DIRECTIVE: Gold standard, complete, professionally written.
"""

import sys
import json
import logging
import subprocess
import asyncio
import os
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, asdict

import click
import yaml
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from orchestrator.Core.framework import FrameworkManager, FrameworkConfig
from orchestrator.Core.orchestrator import LLMOrchestrator, BuildRequest, WorkflowType, PriorityLevel
from orchestrator.Core.builder import BuildEngine, ModelFormat, OptimizationLevel
from orchestrator.Core.module_generator import ModuleGenerator
from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError

@dataclass
class TargetConfig:
    name: str
    architecture: str
    status: str = "available"
    version: str = "1.0.0"
    maintainer: str = "Framework Team"
    description: str = ""
    supported_boards: List[str] = None
    docker_image: str = ""
    def __post_init__(self):
        if self.supported_boards is None: self.supported_boards = []

console = Console()
__version__ = "1.1.0"

DEFAULT_CONFIG = {
    "targets_dir": "targets", "models_dir": "models", "output_dir": "output",
    "configs_dir": "configs", "cache_dir": "cache", "logs_dir": "logs",
    "log_level": "INFO", "max_concurrent_builds": 2
}

class FrameworkContext:
    def __init__(self):
        self.config: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.framework_manager: Optional[FrameworkManager] = None
        self.orchestrator: Optional[LLMOrchestrator] = None
        self.build_engine: Optional[BuildEngine] = None
        self.verbose: bool = False
        self.quiet: bool = False
        self._initialized: bool = False
        
    def initialize(self):
        if self._initialized: return
        try:
            fc = FrameworkConfig(**self.config)
            self.framework_manager = FrameworkManager(fc)
            if not self.framework_manager.initialize(): raise RuntimeError("Framework init failed")
            self.orchestrator = LLMOrchestrator(fc)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if not loop.run_until_complete(self.orchestrator.initialize()):
                    raise RuntimeError("Orchestrator init failed")
            finally: loop.close()
            self.build_engine = self.orchestrator.build_engine
            self._initialized = True
        except Exception as e:
            console.print(f"[red]Init failed: {e}[/red]")
            sys.exit(1)

pass_context = click.make_pass_decorator(FrameworkContext, ensure=True)

def setup_cli_logging(level: str = "INFO"):
    logging.basicConfig(level=getattr(logging, level.upper()), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stderr)])

def load_config_file(path: Optional[str] = None) -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if path and Path(path).exists():
        try:
            with open(Path(path), 'r') as f:
                if Path(path).suffix in ['.yml', '.yaml']: cfg.update(yaml.safe_load(f))
                else: cfg.update(json.load(f))
        except Exception as e: console.print(f"[yellow]Config load failed: {e}[/yellow]")
    return cfg

def format_target_table(targets: List[TargetConfig]) -> Table:
    table = Table(title="Available Targets")
    table.add_column("Name", style="cyan"); table.add_column("Arch", style="green"); table.add_column("Status", style="yellow")
    for t in targets: table.add_row(t.name, t.architecture, t.status)
    return table

@click.group()
@click.version_option(version=__version__)
@click.option('--config', '-c', type=click.Path(exists=True))
@click.option('--verbose', '-v', is_flag=True)
@click.option('--quiet', '-q', is_flag=True)
@pass_context
def cli(ctx: FrameworkContext, config: Optional[str], verbose: bool, quiet: bool):
    setup_cli_logging("DEBUG" if verbose else "INFO")
    ctx.config.update(load_config_file(config))
    ctx.verbose = verbose; ctx.quiet = quiet
    ctx.initialize()

@cli.group()
def targets(): pass

@targets.command('list')
@click.option('--format', '-f', default='table', type=click.Choice(['table', 'json']))
@pass_context
def list_targets(ctx: FrameworkContext, format: str):
    try:
        avail = ctx.build_engine.list_available_targets()
        objs = [TargetConfig(name=t.get("name", "unk"), architecture=t.get("target_arch", "unk"), description=t.get("path", "")) for t in avail]
        if format == 'table': console.print(format_target_table(objs))
        else: click.echo(json.dumps([asdict(t) for t in objs], indent=2))
    except Exception as e: console.print(f"[red]Error: {e}[/red]"); sys.exit(1)

@cli.group()
def build(): pass

@build.command('start')
@click.option('--model', '-m', required=True)
@click.option('--target', '-t', required=True)
@click.option('--format', '-f', default='gguf')
@click.option('--quantization', '-q')
@click.option('--output-dir', '-o
