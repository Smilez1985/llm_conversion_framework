#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Command Line Interface
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Professional CLI for automation, CI/CD integration, and power users.
Supports all framework operations including Source Management and Module Generation.
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
from rich import print as rprint

# Import Core Components
from orchestrator.Core.framework import FrameworkManager, FrameworkConfig
from orchestrator.Core.orchestrator import LLMOrchestrator, BuildRequest, WorkflowType, PriorityLevel
from orchestrator.Core.builder import BuildEngine, TargetArch, ModelFormat, OptimizationLevel
from orchestrator.Core.module_generator import ModuleGenerator
from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError

# ============================================================================
# DATENKLASSEN
# ============================================================================

@dataclass
class TargetConfig:
    """Target configuration for CLI display"""
    name: str
    architecture: str
    status: str = "available"
    version: str = "1.0.0"
    maintainer: str = "Framework Team"
    description: str = ""
    supported_boards: List[str] = None
    docker_image: str = ""
    
    def __post_init__(self):
        if self.supported_boards is None:
            self.supported_boards = []


# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

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


# ============================================================================
# CLICK CONTEXT UND MANAGER INITIALISIERUNG
# ============================================================================

class FrameworkContext:
    """Shared context for CLI commands, hält Instanzen der Core-Manager"""
    
    def __init__(self):
        self.config: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.framework_manager: Optional[FrameworkManager] = None
        self.orchestrator: Optional[LLMOrchestrator] = None
        self.build_engine: Optional[BuildEngine] = None
        self.verbose: bool = False
        self.quiet: bool = False
        self._initialized: bool = False
        
    def initialize(self):
        """Initialisiert FrameworkManager und Orchestrator."""
        if self._initialized:
            return
            
        try:
            # Framework Manager initialisieren
            framework_config = FrameworkConfig(**self.config)
            self.framework_manager = FrameworkManager(framework_config)
            
            if not self.framework_manager.initialize():
                raise RuntimeError("Framework Manager initialization failed")
            
            # Orchestrator initialisieren  
            self.orchestrator = LLMOrchestrator(framework_config)
            
            # Synchrone Initialisierung für CLI
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                success = loop.run_until_complete(self.orchestrator.initialize())
                if not success:
                    raise RuntimeError("Orchestrator initialization failed")
            finally:
                loop.close()
            
            # Build Engine ist über Orchestrator verfügbar
            self.build_engine = self.orchestrator.build_engine
            
            self._initialized = True
            
        except Exception as e:
            console.print(f"[red]Failed to initialize framework: {e}[/red]")
            sys.exit(1)


pass_context = click.make_pass_decorator(FrameworkContext, ensure=True)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def setup_cli_logging(level: str = "INFO"):
    """Setup logging for CLI operations"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )


def load_config_file(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from file"""
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


def format_target_table(targets: List[TargetConfig]) -> Table:
    """Format targets as a Rich table"""
    table = Table(title="Available Targets")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Architecture", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Boards", style="magenta")
    
    for target in targets:
        status = "✅ Ready" if target.status == "available" else "❌ Not Ready"
        boards = ", ".join(target.supported_boards[:2]) if target.supported_boards else "None"
        if target.supported_boards and len(target.supported_boards) > 2:
            boards += f" (+{len(target.supported_boards) - 2} more)"
            
        table.add_row(target.name, target.architecture, status, boards)
    
    return table


def target_arch_from_string(arch_str: str) -> TargetArch:
    """Convert string to TargetArch enum"""
    try:
        return TargetArch[arch_str.upper()]
    except KeyError:
        try:
            return TargetArch(arch_str.lower())
        except ValueError:
            # Fallback or error
            return TargetArch.ARM64


def model_format_from_string(format_str: str) -> ModelFormat:
    """Convert string to ModelFormat enum"""
    try:
        return ModelFormat[format_str.upper()]
    except KeyError:
        try:
            return ModelFormat(format_str.lower())
        except ValueError:
            return ModelFormat.HUGGINGFACE


# ============================================================================
# MAIN CLI GROUP
# ============================================================================

@click.group()
@click.version_option(version=__version__)
@click.option('--config', '-c', type=click.Path(exists=True), help='Configuration file path')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.option('--quiet', '-q', is_flag=True, help='Quiet output')
@click.option('--log-level', default='INFO', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']))
@pass_context
def cli(ctx: FrameworkContext, config: Optional[str], verbose: bool, quiet: bool, log_level: str):
    """
    🚀 LLM Cross-Compiler Framework CLI
    
    Professional command-line interface for cross-compiling Large Language Models
    for edge hardware. Supports automation, CI/CD integration, and power users.
    """
    # Setup logging
    setup_cli_logging("DEBUG" if verbose else log_level)
    
    # Load configuration
    ctx.config.update(load_config_file(config))
    ctx.verbose = verbose
    ctx.quiet = quiet
    
    # Initialisiere Framework und Orchestrator
    ctx.initialize()
    
    if not quiet:
        console.print(Panel(
            f"[bold cyan]LLM Cross-Compiler Framework CLI v{__version__}[/bold cyan]\n"
            f"Professional cross-compilation for edge AI",
            title="🚀 Framework CLI"
        ))


# ============================================================================
# TARGET MANAGEMENT COMMANDS
# ============================================================================

@cli.group()
def targets():
    """Manage hardware targets and architectures"""
    pass


@targets.command('list')
@click.option('--format', '-f', default='table', type=click.Choice(['table', 'json', 'yaml']))
@pass_context
def list_targets(ctx: FrameworkContext, format: str):
    """List available hardware targets"""
    
    try:
        if not ctx.build_engine:
            console.print("[red]Build engine not available[/red]")
            sys.exit(1)
        
        available_targets = ctx.build_engine.list_available_targets()
        
        targets_config_objects = []
        for target_info in available_targets:
            target_config = TargetConfig(
                name=target_info.get("target_arch", "unknown"),
                architecture=target_info.get("target_arch", "unknown"),
                status="available" if target_info.get("available", False) else "unavailable",
                version="1.0.0",
                maintainer="Framework Team",
                description=f"Target for {target_info.get('target_arch', 'unknown')} architecture",
                supported_boards=target_info.get("modules", []),
                docker_image="llm-framework/builder"
            )
            targets_config_objects.append(target_config)
        
        if format == 'table':
            if targets_config_objects:
                table = format_target_table(targets_config_objects)
                console.print(table)
            else:
                console.print("[yellow]No targets found matching criteria[/yellow]")
        elif format == 'json':
            click.echo(json.dumps([asdict(t) for t in targets_config_objects], indent=2))
        elif format == 'yaml':
            click.echo(yaml.dump([asdict(t) for t in targets_config_objects], default_flow_style=False))
            
    except Exception as e:
        console.print(f"[red]Error listing targets: {e}[/red]")
        sys.exit(1)


@targets.command('validate')
@click.argument('target_name')
@pass_context
def validate_target(ctx: FrameworkContext, target_name: str):
    """Validate a target configuration"""
    try:
        result = ctx.framework_manager.validate_target(target_name)
        if result.get("valid", False):
            console.print(f"[green]✅ Target '{target_name}' is valid[/green]")
            if ctx.verbose:
                console.print(f"[blue]Target path: {result.get('target_path', 'Unknown')}[/blue]")
        else:
            console.print(f"[red]❌ Target '{target_name}' validation failed[/red]")
            for error in result.get("errors", []):
                console.print(f"  [red]• {error}[/red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error validating target: {e}[/red]")
        sys.exit(1)


# ============================================================================
# MODULE MANAGEMENT COMMANDS (WIZARD VIA CLI)
# ============================================================================

@cli.group()
def module():
    """Manage hardware target modules"""
    pass

@module.command('create')
@click.option('--name', prompt='Module Name', help='Name of the new target')
@click.option('--arch', prompt='Architecture', type=click.Choice(['aarch64', 'x86_64', 'armv7l', 'riscv64']), help='CPU Architecture')
@click.option('--sdk', prompt='SDK/Backend', default='None', help='Special SDK (e.g. CUDA, RKNN)')
@pass_context
def module_create(ctx: FrameworkContext, name: str, arch: str, sdk: str):
    """Create a new hardware target module interactively"""
    
    console.print(f"\n[bold cyan]Creating new target module: {name}[/bold cyan]")
    
    # Interaktive Abfrage weiterer Details (CLI Wizard Style)
    base_os = click.prompt("Base Docker Image", default="debian:bookworm-slim")
    description = click.prompt("Description", default=f"Target for {name}")
    
    console.print("Enter required system packages (comma separated):")
    packages_input = click.prompt("Packages", default="build-essential, cmake, git")
    packages = [p.strip() for p in packages_input.split(',')]
    
    cpu_flags = click.prompt("Default CPU Flags", default="")
    
    module_data = {
        "module_name": name,
        "architecture": arch,
        "sdk": sdk,
        "description": description,
        "base_os": base_os,
        "packages": packages,
        "cpu_flags": cpu_flags,
        "supported_boards": [], 
        "setup_commands": "",
        "cmake_flags": "",
        "detection_commands": "lscpu"
    }
    
    try:
        targets_dir = Path(ctx.config.get('targets_dir', 'targets'))
        generator = ModuleGenerator(targets_dir)
        
        output_path = generator.generate_module(module_data)
        
        console.print(f"\n[bold green]✅ Module successfully created![/bold green]")
        console.print(f"Location: {output_path}")
        console.print("\nNext steps:")
        console.print(f"1. Edit {output_path}/target.yml to add supported boards")
        console.print(f"2. Customize {output_path}/modules/config_module.sh")
        
    except Exception as e:
        console.print(f"[bold red]Error creating module: {e}[/bold red]")
        sys.exit(1)


# ============================================================================
# BUILD COMMANDS
# ============================================================================

@cli.group()
def build():
    """Build and cross-compile models"""
    pass


@build.command('start')
@click.option('--model', '-m', required=True, help='Model name (HuggingFace) or local path')
@click.option('--target', '-t', required=True, help='Target hardware architecture')
@click.option('--format', '-f', default='gguf', help='Target format (gguf, onnx, tflite)')
@click.option('--quantization', '-q', help='Quantization method (q4_0, q8_0, etc.)')
@click.option('--output-dir', '-o', help='Custom output directory')
@click.option('--optimization', default='balanced', 
              type=click.Choice(['fast', 'balanced', 'size', 'speed', 'aggressive']),
              help='Optimization level')
@click.option('--priority', default='normal',
              type=click.Choice(['low', 'normal', 'high', 'urgent', 'critical']),
              help='Build priority')
@click.option('--parallel', is_flag=True, default=True, help='Enable parallel builds')
@click.option('--follow', '-F', is_flag=True, help='Follow build output in real-time')
@pass_context
def start_build(ctx: FrameworkContext, model: str, target: str, format: str, 
                quantization: Optional[str], output_dir: Optional[str], 
                optimization: str, priority: str, parallel: bool, follow: bool):
    """Start a new build job"""
    
    try:
        target_arch = target_arch_from_string(target)
        target_format = model_format_from_string(format)
        
        opt_mapping = {
            'fast': OptimizationLevel.FAST,
            'balanced': OptimizationLevel.BALANCED,
            'size': OptimizationLevel.SIZE,
            'speed': OptimizationLevel.SPEED,
            'aggressive': OptimizationLevel.AGGRESSIVE
        }
        optimization_level = opt_mapping[optimization]
        
        priority_mapping = {
            'low': PriorityLevel.LOW,
            'normal': PriorityLevel.NORMAL,
            'high': PriorityLevel.HIGH,
            'urgent': PriorityLevel.URGENT,
            'critical': PriorityLevel.CRITICAL
        }
        priority_level = priority_mapping[priority]
        
        if not output_dir:
            output_dir = str(Path(ctx.config["output_dir"]) / f"build_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        build_request = BuildRequest(
            request_id="",
            workflow_type=WorkflowType.SIMPLE_CONVERSION,
            priority=priority_level,
            models=[model],
            targets=[target_arch],
            target_formats=[target_format],
            optimization_level=optimization_level,
            quantization_options=[quantization] if quantization else [],
            parallel_builds=parallel,
            output_base_dir=output_dir,
            description=f"CLI build: {model} -> {target} ({format})"
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            request_id = loop.run_until_complete(ctx.orchestrator.submit_build_request(build_request))
            
            if not ctx.quiet:
                console.print(Panel(
                    f"[bold]Model:[/bold] {model}\n"
                    f"[bold]Target:[/bold] {target}\n"
                    f"[bold]Format:[/bold] {format}\n"
                    f"[bold]Quantization:[/bold] {quantization or 'None'}\n"
                    f"[bold]Output:[/bold] {output_dir}",
                    title=f"🚀 Starting Build: {request_id}"
                ))
            
            if follow:
                console.print("[blue]Following build progress (Ctrl+C to stop following)...[/blue]")
                try:
                    while True:
                        workflow_status = loop.run_until_complete(ctx.orchestrator.get_workflow_status(request_id))
                        if workflow_status:
                            console.print(f"[yellow]Status: {workflow_status.status.value} - {workflow_status.current_stage}[/yellow]")
                            console.print(f"[cyan]Progress: {workflow_status.progress_percent}% ({workflow_status.completed_builds}/{workflow_status.total_builds} builds)[/cyan]")
                            
                            if workflow_status.status.value in ["ready", "error"]:
                                break
                        
                        import time
                        time.sleep(5)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Stopped following build (build continues in background)[/yellow]")
            else:
                console.print(f"[green]Build started with ID: {request_id}[/green]")
                console.print(f"Use 'llm-cli build status {request_id}' to check progress")
                
        finally:
            loop.close()
            
    except Exception as e:
        console.print(f"[red]Build failed: {e}[/red]")
        sys.exit(1)


@build.command('status')
@click.argument('request_id', required=False)
@click.option('--all', '-a', is_flag=True, help='Show all builds')
@pass_context
def build_status(ctx: FrameworkContext, request_id: Optional[str], all: bool):
    """Check build status"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if all or not request_id:
                workflows = loop.run_until_complete(ctx.orchestrator.list_workflows())
                if not workflows:
                    console.print("[yellow]No builds found[/yellow]")
                    return
                
                table = Table(title="Build Status")
                table.add_column("Request ID", style="cyan", no_wrap=True)
                table.add_column("Status", style="yellow")
                table.add_column("Progress", style="blue")
                
                for workflow in workflows:
                    table.add_row(
                        workflow.request_id[:12] + "...",
                        workflow.status.value,
                        f"{workflow.progress_percent}%"
                    )
                console.print(table)
            else:
                workflow_status = loop.run_until_complete(ctx.orchestrator.get_workflow_status(request_id))
                if not workflow_status:
                    console.print(f"[red]Build '{request_id}' not found[/red]")
                    sys.exit(1)
                
                console.print(f"[bold]ID:[/bold] {workflow_status.request_id}")
                console.print(f"[bold]Status:[/bold] {workflow_status.status.value}")
                console.print(f"[bold]Progress:[/bold] {workflow_status.progress_percent}%")
                
        finally:
            loop.close()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

# ============================================================================
# SYSTEM COMMANDS (INKLUSIVE MONITOR)
# ============================================================================

@cli.group()
def system():
    """System management and diagnostics"""
    pass

@system.command('status')
@pass_context
def system_status(ctx: FrameworkContext):
    """Show framework system status"""
    info = ctx.framework_manager.get_info()
    console.print(f"[bold]Framework Version:[/bold] {info.version}")
    console.print(f"[bold]Docker:[/bold] {'✅ Connected' if info.docker_available else '❌ Disconnected'}")
    console.print(f"[bold]Targets:[/bold] {info.targets_count}")

@system.command('monitor')
def system_monitor():
    """Start interactive ctop monitor"""
    try:
        # Check if ctop container is running
        subprocess.run(["docker", "start", "llm-monitor"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Attach to ctop
        subprocess.run(["docker", "attach", "llm-monitor"])
    except subprocess.CalledProcessError:
        console.print("[yellow]Monitor container not found. Run 'docker-compose up -d' first.[/yellow]")
    except KeyboardInterrupt:
        console.print("\nExiting monitor...")
    except Exception as e:
        console.print(f"[red]Failed to start monitor: {e}[/red]")

@system.command('clean')
@click.option('--all', is_flag=True, help='Clean everything')
@click.option('--force', '-f', is_flag=True, help='Force clean')
@pass_context
def system_clean(ctx: FrameworkContext, all: bool, force: bool):
    """Clean system artifacts"""
    if not force and not click.confirm(f"Clean build cache and logs?"):
        return
    
    try:
        cache_dir = Path(ctx.config["cache_dir"])
        if cache_dir.exists():
            import shutil
            for item in cache_dir.iterdir():
                if item.is_dir(): shutil.rmtree(item)
                else: item.unlink()
            console.print("[green]Cache cleaned[/green]")
    except Exception as e:
        console.print(f"[red]Clean failed: {e}[/red]")

# ============================================================================
# CONFIG COMMANDS (SOURCES MANAGEMENT)
# ============================================================================

@cli.group()
def config():
    """Configuration management"""
    pass

@config.command('show')
@pass_context
def show_config(ctx: FrameworkContext):
    """Show current configuration"""
    click.echo(json.dumps(ctx.config, indent=2, default=str))

@config.command('sources')
@click.option('--list', '-l', is_flag=True, help='List configured sources')
@click.option('--add', '-a', nargs=3, help='Add source: SECTION NAME URL (e.g. core llama_cpp https://...)')
@pass_context
def config_sources(ctx: FrameworkContext, list: bool, add: tuple):
    """Manage source repositories from project_sources.yml"""
    
    sources_file = Path(ctx.config.get('configs_dir', 'configs')) / 'project_sources.yml'
    
    if list:
        if hasattr(ctx.framework_manager.config, 'source_repositories'):
            table = Table(title="Configured Source Repositories")
            table.add_column("Key (Section.Name)", style="cyan")
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
        
        # Load existing yaml
        if sources_file.exists():
            try:
                with open(sources_file, 'r') as f:
                    data = yaml.safe_load(f) or {}
            except Exception as e:
                console.print(f"[red]Error loading sources file: {e}[/red]")
                return
        else:
            data = {}
        
        # Update data
        if section not in data:
            data[section] = {}
        data[section][name] = url
        
        # Write back
        try:
            with open(sources_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)
            console.print(f"[green]Successfully added source: {section}.{name} -> {url}[/green]")
            console.print("[blue]Note: Restart framework/CLI to apply changes.[/blue]")
        except Exception as e:
            console.print(f"[red]Error writing sources file: {e}[/red]")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()
