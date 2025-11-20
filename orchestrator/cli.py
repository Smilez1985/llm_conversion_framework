#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Command Line Interface
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
"""

import sys
import json
import logging
import subprocess
import asyncio
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

# Import Core Components
from orchestrator.Core.framework import FrameworkManager, FrameworkConfig
from orchestrator.Core.orchestrator import LLMOrchestrator, BuildRequest, WorkflowType, PriorityLevel
from orchestrator.Core.builder import BuildEngine, TargetArch, ModelFormat, OptimizationLevel
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
    "targets_dir": "targets",
    "models_dir": "models", 
    "output_dir": "output",
    "configs_dir": "configs",
    "cache_dir": "cache",
    "logs_dir": "logs",
    "log_level": "INFO",
    "max_concurrent_builds": 2
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
            framework_config = FrameworkConfig(**self.config)
            self.framework_manager = FrameworkManager(framework_config)
            if not self.framework_manager.initialize():
                raise RuntimeError("Framework Manager initialization failed")
            
            self.orchestrator = LLMOrchestrator(framework_config)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success = loop.run_until_complete(self.orchestrator.initialize())
                if not success: raise RuntimeError("Orchestrator initialization failed")
            finally:
                loop.close()
            
            self.build_engine = self.orchestrator.build_engine
            self._initialized = True
        except Exception as e:
            console.print(f"[red]Failed to initialize framework: {e}[/red]")
            sys.exit(1)

pass_context = click.make_pass_decorator(FrameworkContext, ensure=True)

def setup_cli_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )

def load_config_file(config_path: Optional[str] = None) -> Dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    if config_path and Path(config_path).exists():
        try:
            with open(Path(config_path), 'r') as f:
                if Path(config_path).suffix in ['.yml', '.yaml']:
                    file_config = yaml.safe_load(f)
                else:
                    file_config = json.load(f)
            config.update(file_config)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load config file: {e}[/yellow]")
    return config

def target_arch_from_string(arch_str: str) -> TargetArch:
    try: return TargetArch[arch_str.upper()]
    except KeyError: return TargetArch.ARM64

def model_format_from_string(format_str: str) -> ModelFormat:
    try: return ModelFormat[format_str.upper()]
    except KeyError: return ModelFormat.HUGGINGFACE

@click.group()
@click.version_option(version=__version__)
@click.option('--config', '-c', type=click.Path(exists=True), help='Configuration file path')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.option('--quiet', '-q', is_flag=True, help='Quiet output')
@pass_context
def cli(ctx: FrameworkContext, config: Optional[str], verbose: bool, quiet: bool):
    """🚀 LLM Cross-Compiler Framework CLI"""
    setup_cli_logging("DEBUG" if verbose else "INFO")
    ctx.config.update(load_config_file(config))
    ctx.verbose = verbose
    ctx.quiet = quiet
    ctx.initialize()

@cli.group()
def config():
    """Configuration management"""
    pass

@config.command('sources')
@click.option('--list', '-l', is_flag=True, help='List configured sources')
@click.option('--add', '-a', nargs=3, help='Add source: SECTION NAME URL')
@pass_context
def config_sources(ctx: FrameworkContext, list: bool, add: tuple):
    """Manage source repositories"""
    sources_file = Path(ctx.config.get('configs_dir', 'configs')) / 'project_sources.yml'
    
    if list:
        if hasattr(ctx.framework_manager.config, 'source_repositories'):
            table = Table(title="Configured Source Repositories")
            table.add_column("Key", style="cyan")
            table.add_column("URL", style="green")
            for key, url in ctx.framework_manager.config.source_repositories.items():
                table.add_row(key, url)
            console.print(table)
        else:
            console.print("[yellow]No sources configured.[/yellow]")
            
    if add:
        if len(add) != 3:
            console.print("[red]Error: Add requires exactly 3 arguments: SECTION NAME URL[/red]")
            return
        section, name, url = add
        if sources_file.exists():
            with open(sources_file, 'r') as f: data = yaml.safe_load(f) or {}
        else: data = {}
        
        if section not in data: data[section] = {}
        data[section][name] = url
        
        with open(sources_file, 'w') as f: yaml.dump(data, f, default_flow_style=False)
        console.print(f"[green]Added source: {section}.{name} -> {url}[/green]")

@cli.group()
def system():
    """System management"""
    pass

@system.command('monitor')
def system_monitor():
    """Start interactive ctop monitor"""
    try:
        subprocess.run(["docker", "start", "llm-monitor"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "attach", "llm-monitor"])
    except subprocess.CalledProcessError:
        console.print("[yellow]Monitor container not found. Run 'docker-compose up -d' first.[/yellow]")
    except KeyboardInterrupt:
        console.print("\nExiting monitor...")
    except Exception as e:
        console.print(f"[red]Failed to start monitor: {e}[/red]")

@cli.group()
def build():
    """Build commands"""
    pass

@build.command('start')
@click.option('--model', '-m', required=True, help='Model name')
@click.option('--target', '-t', required=True, help='Target architecture')
@click.option('--quantization', '-q', default='Q4_K_M', help='Quantization method')
@pass_context
def build_start(ctx: FrameworkContext, model: str, target: str, quantization: str):
    """Start a build"""
    try:
        t_arch = target_arch_from_string(target)
        req = BuildRequest(
            request_id="",
            workflow_type=WorkflowType.SIMPLE_CONVERSION,
            models=[model],
            targets=[t_arch],
            target_formats=[ModelFormat.GGUF],
            quantization_options=[quantization],
            output_base_dir="output"
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        rid = loop.run_until_complete(ctx.orchestrator.submit_build_request(req))
        console.print(f"[green]Build started: {rid}[/green]")
        loop.close()
    except Exception as e:
        console.print(f"[red]Build failed: {e}[/red]")

if __name__ == "__main__":
    main()
