#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Command Line Interface
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Professional CLI for automation, CI/CD integration, and power users.
Supports all framework operations without requiring GUI.
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
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Import der Kernkomponenten (KORRIGIERT)
from orchestrator.Core.framework import FrameworkManager, FrameworkConfig
from orchestrator.Core.orchestrator import LLMOrchestrator, BuildRequest, WorkflowType, PriorityLevel
from orchestrator.Core.builder import BuildEngine, TargetArch, ModelFormat, OptimizationLevel
from orchestrator.utils.logging import get_logger
from orchestrator.utils.validation import ValidationError


# ============================================================================
# DATENKLASSEN (KORRIGIERT - Fehlende Klassen hinzugefügt)
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

# Rich console für schöne Ausgabe
console = Console()

# Framework Version
__version__ = "1.0.0"

# Default configuration (für CLI)
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
# CLICK CONTEXT UND MANAGER INITIALISIERUNG (KORRIGIERT)
# ============================================================================

class FrameworkContext:
    """Shared context for CLI commands, hält Instanzen der Core-Manager"""
    
    def __init__(self):
        self.config: Dict[str, Any] = DEFAULT_CONFIG.copy()
        # Verwende unsere existierenden Manager
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
# UTILITY FUNCTIONS (KORRIGIERT)
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
    table.add_column("Version", style="blue")
    table.add_column("Boards", style="magenta")
    
    for target in targets:
        status = "✅ Ready" if target.status == "available" else "❌ Not Ready"
        boards = ", ".join(target.supported_boards[:2]) if target.supported_boards else "None"
        if target.supported_boards and len(target.supported_boards) > 2:
            boards += f" (+{len(target.supported_boards) - 2} more)"
            
        table.add_row(
            target.name,
            target.architecture,
            status,
            target.version,
            boards
        )
    
    return table


def format_build_status(build_info: Dict[str, Any]) -> Panel:
    """Format build status as a Rich panel"""
    status_color = {
        "building": "yellow",
        "completed": "green", 
        "failed": "red",
        "queued": "blue",
        "ready": "green"
    }.get(build_info.get("status", "unknown"), "white")
    
    content = f"""
[bold]ID:[/bold] {build_info.get('request_id', 'Unknown')}
[bold]Type:[/bold] {build_info.get('workflow_type', 'Unknown')}
[bold]Status:[/bold] [{status_color}]{build_info.get('status', 'Unknown')}[/{status_color}]
[bold]Progress:[/bold] {build_info.get('progress_percent', 0)}%
[bold]Total Builds:[/bold] {build_info.get('total_builds', 0)}
[bold]Completed:[/bold] {build_info.get('completed_builds', 0)}
[bold]Failed:[/bold] {build_info.get('failed_builds', 0)}
"""
    
    if build_info.get('start_time'):
        start_time = build_info['start_time']
        if isinstance(start_time, str):
            start_time = start_time.split('T')[0]
        content += f"[bold]Started:[/bold] {start_time}\n"
    
    return Panel(content.strip(), title=f"Workflow {build_info.get('request_id', 'Unknown')}")


def target_arch_from_string(arch_str: str) -> TargetArch:
    """Convert string to TargetArch enum"""
    arch_mapping = {
        "arm64": TargetArch.ARM64,
        "armv7": TargetArch.ARMV7,
        "x86_64": TargetArch.X86_64,
        "rk3566": TargetArch.RK3566,
        "rk3588": TargetArch.RK3588,
        "raspberry_pi": TargetArch.RASPBERRY_PI
    }
    
    arch_lower = arch_str.lower()
    if arch_lower not in arch_mapping:
        available = ", ".join(arch_mapping.keys())
        raise click.BadParameter(f"Invalid architecture '{arch_str}'. Available: {available}")
    
    return arch_mapping[arch_lower]


def model_format_from_string(format_str: str) -> ModelFormat:
    """Convert string to ModelFormat enum"""
    format_mapping = {
        "hf": ModelFormat.HUGGINGFACE,
        "huggingface": ModelFormat.HUGGINGFACE,
        "gguf": ModelFormat.GGUF,
        "onnx": ModelFormat.ONNX,
        "tflite": ModelFormat.TENSORFLOW_LITE,
        "pytorch": ModelFormat.PYTORCH_MOBILE
    }
    
    format_lower = format_str.lower()
    if format_lower not in format_mapping:
        available = ", ".join(format_mapping.keys())
        raise click.BadParameter(f"Invalid format '{format_str}'. Available: {available}")
    
    return format_mapping[format_lower]


# ============================================================================
# MAIN CLI GROUP (KORRIGIERT)
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
    setup_cli_logging(log_level)
    
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
# TARGET MANAGEMENT COMMANDS (KORRIGIERT)
# ============================================================================

@cli.group()
def targets():
    """Manage hardware targets and architectures"""
    pass


@targets.command('list')
@click.option('--format', '-f', default='table', type=click.Choice(['table', 'json', 'yaml']))
@click.option('--architecture', '-a', help='Filter by architecture')
@click.option('--status', '-s', help='Filter by status')
@pass_context
def list_targets(ctx: FrameworkContext, format: str, architecture: Optional[str], status: Optional[str]):
    """List available hardware targets"""
    
    try:
        # Nutze BuildEngine für verfügbare Targets
        if not ctx.build_engine:
            console.print("[red]Build engine not available[/red]")
            sys.exit(1)
        
        available_targets = ctx.build_engine.list_available_targets()
        
        # Konvertiere zu TargetConfig-Objekten
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
        
        # Apply filters
        if architecture:
            targets_config_objects = [t for t in targets_config_objects if architecture.lower() in t.architecture.lower()]
        if status:
            targets_config_objects = [t for t in targets_config_objects if t.status == status]
        
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


@targets.command('info')
@click.argument('target_name')
@click.option('--format', '-f', default='panel', type=click.Choice(['panel', 'json', 'yaml']))
@pass_context
def target_info(ctx: FrameworkContext, target_name: str, format: str):
    """Show detailed information about a target"""
    
    try:
        # Konvertiere Target-Name zu TargetArch
        target_arch = target_arch_from_string(target_name)
        
        # Hole Target-Info vom BuildEngine
        target_data = ctx.build_engine.get_target_info(target_arch)
        
        if not target_data or not target_data.get("available", False):
            console.print(f"[red]Target '{target_name}' not found or not available[/red]")
            sys.exit(1)
        
        if format == 'panel':
            # Erstelle TargetConfig für Anzeige
            target = TargetConfig(
                name=target_arch.value,
                architecture=target_arch.value,
                status="available" if target_data.get("available", False) else "unavailable",
                version="1.0.0",
                maintainer="Framework Team",
                description=f"Cross-compilation target for {target_arch.value}",
                supported_boards=target_data.get("modules", []),
                docker_image="llm-framework/builder"
            )
            
            content = f"""
[bold]Architecture:[/bold] {target.architecture}
[bold]Version:[/bold] {target.version}
[bold]Maintainer:[/bold] {target.maintainer}
[bold]Description:[/bold] {target.description}

[bold]Available Modules:[/bold]
{chr(10).join(f"  • {module}" for module in target.supported_boards)}

[bold]Docker Image:[/bold] {target.docker_image}
[bold]Status:[/bold] {target.status}
[bold]Target Path:[/bold] {target_data.get('target_path', 'Unknown')}
"""
            panel = Panel(content.strip(), title=f"Target: {target_name}")
            console.print(panel)
            
        elif format == 'json':
            click.echo(json.dumps(target_data, indent=2))
        elif format == 'yaml':
            click.echo(yaml.dump(target_data, default_flow_style=False))
            
    except click.BadParameter as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error getting target info: {e}[/red]")
        sys.exit(1)


@targets.command('validate')
@click.argument('target_name')
@pass_context
def validate_target(ctx: FrameworkContext, target_name: str):
    """Validate a target configuration"""
    
    try:
        # Verwende FrameworkManager für Target-Validierung
        result = ctx.framework_manager.validate_target(target_name)
        
        if result.get("valid", False):
            console.print(f"[green]✅ Target '{target_name}' is valid[/green]")
            
            # Zeige zusätzliche Informationen
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
# BUILD COMMANDS (KORRIGIERT - Nutzt LLMOrchestrator)
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
        # Validiere und konvertiere Parameter
        target_arch = target_arch_from_string(target)
        target_format = model_format_from_string(format)
        
        # Optimization Level
        opt_mapping = {
            'fast': OptimizationLevel.FAST,
            'balanced': OptimizationLevel.BALANCED,
            'size': OptimizationLevel.SIZE,
            'speed': OptimizationLevel.SPEED,
            'aggressive': OptimizationLevel.AGGRESSIVE
        }
        optimization_level = opt_mapping[optimization]
        
        # Priority Level
        priority_mapping = {
            'low': PriorityLevel.LOW,
            'normal': PriorityLevel.NORMAL,
            'high': PriorityLevel.HIGH,
            'urgent': PriorityLevel.URGENT,
            'critical': PriorityLevel.CRITICAL
        }
        priority_level = priority_mapping[priority]
        
        # Output Directory
        if not output_dir:
            output_dir = str(Path(ctx.config["output_dir"]) / f"build_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        # Erstelle Build Request
        build_request = BuildRequest(
            request_id="",  # Wird automatisch generiert
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
        
        # Starte Build über Orchestrator
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
                    f"[bold]Optimization:[/bold] {optimization}\n"
                    f"[bold]Priority:[/bold] {priority}\n"
                    f"[bold]Output:[/bold] {output_dir}",
                    title=f"🚀 Starting Build: {request_id}"
                ))
            
            if follow:
                # Follow build progress
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
            
    except click.BadParameter as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Build failed: {e}[/red]")
        sys.exit(1)


@build.command('status')
@click.argument('request_id', required=False)
@click.option('--all', '-a', is_flag=True, help='Show all builds')
@click.option('--format', '-f', default='panel', type=click.Choice(['panel', 'table', 'json']))
@pass_context
def build_status(ctx: FrameworkContext, request_id: Optional[str], all: bool, format: str):
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
                
                if format == 'table':
                    table = Table(title="Build Status")
                    table.add_column("Request ID", style="cyan", no_wrap=True)
                    table.add_column("Type", style="green")
                    table.add_column("Status", style="yellow")
                    table.add_column("Progress", style="blue")
                    table.add_column("Builds", style="magenta")
                    
                    for workflow in workflows:
                        table.add_row(
                            workflow.request_id[:12] + "...",
                            workflow.workflow_type.value,
                            workflow.status.value,
                            f"{workflow.progress_percent}%",
                            f"{workflow.completed_builds}/{workflow.total_builds}"
                        )
                    
                    console.print(table)
                elif format == 'json':
                    workflows_data = []
                    for workflow in workflows:
                        workflows_data.append({
                            "request_id": workflow.request_id,
                            "workflow_type": workflow.workflow_type.value,
                            "status": workflow.status.value,
                            "progress_percent": workflow.progress_percent,
                            "total_builds": workflow.total_builds,
                            "completed_builds": workflow.completed_builds,
                            "failed_builds": workflow.failed_builds,
                            "start_time": workflow.start_time.isoformat() if workflow.start_time else None
                        })
                    click.echo(json.dumps(workflows_data, indent=2))
                else:
                    for workflow in workflows:
                        workflow_dict = {
                            "request_id": workflow.request_id,
                            "workflow_type": workflow.workflow_type.value,
                            "status": workflow.status.value,
                            "progress_percent": workflow.progress_percent,
                            "total_builds": workflow.total_builds,
                            "completed_builds": workflow.completed_builds,
                            "failed_builds": workflow.failed_builds,
                            "start_time": workflow.start_time
                        }
                        panel = format_build_status(workflow_dict)
                        console.print(panel)
            else:
                workflow_status = loop.run_until_complete(ctx.orchestrator.get_workflow_status(request_id))
                if not workflow_status:
                    console.print(f"[red]Build '{request_id}' not found[/red]")
                    sys.exit(1)
                
                if format == 'json':
                    workflow_dict = {
                        "request_id": workflow_status.request_id,
                        "workflow_type": workflow_status.workflow_type.value,
                        "status": workflow_status.status.value,
                        "progress_percent": workflow_status.progress_percent,
                        "total_builds": workflow_status.total_builds,
                        "completed_builds": workflow_status.completed_builds,
                        "failed_builds": workflow_status.failed_builds,
                        "start_time": workflow_status.start_time
                    }
                    click.echo(json.dumps(workflow_dict, indent=2, default=str))
                else:
                    workflow_dict = {
                        "request_id": workflow_status.request_id,
                        "workflow_type": workflow_status.workflow_type.value,
                        "status": workflow_status.status.value,
                        "progress_percent": workflow_status.progress_percent,
                        "total_builds": workflow_status.total_builds,
                        "completed_builds": workflow_status.completed_builds,
                        "failed_builds": workflow_status.failed_builds,
                        "start_time": workflow_status.start_time
                    }
                    panel = format_build_status(workflow_dict)
                    console.print(panel)
                    
                    # Zeige Logs wenn verbose
                    if ctx.verbose and workflow_status.logs:
                        console.print("\n[bold]Recent Logs:[/bold]")
                        for log_entry in workflow_status.logs[-10:]:  # Last 10 entries
                            console.print(f"  {log_entry}")
                            
        finally:
            loop.close()
            
    except Exception as e:
        console.print(f"[red]Error getting build status: {e}[/red]")
        sys.exit(1)


@build.command('cancel')
@click.argument('request_id')
@click.option('--force', '-f', is_flag=True, help='Force cancel without confirmation')
@pass_context
def cancel_build(ctx: FrameworkContext, request_id: str, force: bool):
    """Cancel a running build"""
    
    try:
        if not force and not click.confirm(f"Cancel build '{request_id}'?"):
            console.print("[blue]Build cancellation cancelled[/blue]")
            return
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            success = loop.run_until_complete(ctx.orchestrator.cancel_workflow(request_id))
            
            if success:
                console.print(f"[yellow]Build '{request_id}' cancelled[/yellow]")
            else:
                console.print(f"[red]Failed to cancel build '{request_id}' (not found or already completed)[/red]")
                sys.exit(1)
                
        finally:
            loop.close()
            
    except Exception as e:
        console.print(f"[red]Error cancelling build: {e}[/red]")
        sys.exit(1)
# ============================================================================
# SYSTEM COMMANDS (KORRIGIERT - Nutzt Framework Manager + Orchestrator)
# ============================================================================

@cli.group()
def system():
    """System management and diagnostics"""
    pass


@system.command('status')
@click.option('--format', '-f', default='panel', type=click.Choice(['panel', 'json', 'yaml']))
@pass_context
def system_status(ctx: FrameworkContext, format: str):
    """Show framework system status"""
    
    try:
        # Framework Info
        framework_info = ctx.framework_manager.get_info()
        
        # Orchestrator Status  
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            orchestrator_status = ctx.orchestrator.get_system_status()
        finally:
            loop.close()
        
        status_data = {
            "framework": {
                "version": framework_info.version,
                "build_date": framework_info.build_date.split('T')[0] if 'T' in framework_info.build_date else framework_info.build_date,
                "installation_path": framework_info.installation_path,
                "config_path": framework_info.config_path,
                "docker_available": framework_info.docker_available,
                "targets_count": framework_info.targets_count,
                "active_builds": framework_info.active_builds
            },
            "orchestrator": orchestrator_status.get("orchestrator", {}),
            "workflows": orchestrator_status.get("workflows", {}),
            "resources": orchestrator_status.get("resources", {}),
            "components": orchestrator_status.get("components", {}),
            "metrics": orchestrator_status.get("metrics", {})
        }
        
        if format == 'json':
            click.echo(json.dumps(status_data, indent=2, default=str))
        elif format == 'yaml':
            click.echo(yaml.dump(status_data, default_flow_style=False))
        else:
            # Panel format
            framework_data = status_data["framework"]
            orchestrator_data = status_data["orchestrator"]
            resources_data = status_data["resources"]
            
            content = f"""
[bold]Framework Version:[/bold] {framework_data['version']}
[bold]Docker Status:[/bold] {"✅ Connected" if framework_data['docker_available'] else "❌ Disconnected"}
[bold]Installation Path:[/bold] {framework_data['installation_path']}
[bold]Available Targets:[/bold] {framework_data['targets_count']}

[bold]Orchestrator:[/bold] {"✅ Ready" if orchestrator_data.get('ready', False) else "❌ Not Ready"}
[bold]Active Workflows:[/bold] {status_data['workflows'].get('active', 0)}
[bold]Total Workflows:[/bold] {status_data['workflows'].get('total', 0)}

[bold]System Resources:[/bold]
  • CPU: {resources_data.get('cpu_percent', 0):.1f}%
  • Memory: {resources_data.get('memory_percent', 0):.1f}%
  • Disk: {resources_data.get('disk_usage_gb', 0):.1f} GB
  • Active Builds: {resources_data.get('active_builds', 0)}
  • Can Start Build: {"✅ Yes" if resources_data.get('can_start_build', False) else "❌ No"}

[bold]Build Date:[/bold] {framework_data['build_date']}
"""
            
            panel = Panel(content.strip(), title="🔧 System Status")
            console.print(panel)
            
    except Exception as e:
        console.print(f"[red]Error getting system status: {e}[/red]")
        sys.exit(1)


@system.command('info')
@click.option('--format', '-f', default='panel', type=click.Choice(['panel', 'json', 'yaml']))
@pass_context
def system_info(ctx: FrameworkContext, format: str):
    """Show detailed system information"""
    
    try:
        # Sammle Systeminformationen
        framework_info = ctx.framework_manager.get_info()
        framework_config = ctx.framework_manager.get_config()
        
        info_data = {
            "framework": {
                "version": framework_info.version,
                "git_commit": framework_info.git_commit,
                "build_date": framework_info.build_date,
                "installation_path": framework_info.installation_path,
                "config_path": framework_info.config_path
            },
            "configuration": {
                "targets_dir": framework_config.targets_dir,
                "models_dir": framework_config.models_dir,
                "output_dir": framework_config.output_dir,
                "cache_dir": framework_config.cache_dir,
                "logs_dir": framework_config.logs_dir,
                "log_level": framework_config.log_level,
                "max_concurrent_builds": framework_config.max_concurrent_builds,
                "docker_registry": framework_config.docker_registry,
                "docker_namespace": framework_config.docker_namespace
            },
            "system": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": sys.platform,
                "executable": sys.executable
            }
        }
        
        if format == 'json':
            click.echo(json.dumps(info_data, indent=2, default=str))
        elif format == 'yaml':
            click.echo(yaml.dump(info_data, default_flow_style=False))
        else:
            content = f"""
[bold cyan]Framework Information[/bold cyan]
[bold]Version:[/bold] {info_data['framework']['version']}
[bold]Build Date:[/bold] {info_data['framework']['build_date']}
[bold]Installation:[/bold] {info_data['framework']['installation_path']}
[bold]Git Commit:[/bold] {info_data['framework']['git_commit'] or 'Unknown'}

[bold cyan]Configuration[/bold cyan]
[bold]Targets Directory:[/bold] {info_data['configuration']['targets_dir']}
[bold]Models Directory:[/bold] {info_data['configuration']['models_dir']}
[bold]Output Directory:[/bold] {info_data['configuration']['output_dir']}
[bold]Cache Directory:[/bold] {info_data['configuration']['cache_dir']}
[bold]Log Level:[/bold] {info_data['configuration']['log_level']}
[bold]Max Concurrent Builds:[/bold] {info_data['configuration']['max_concurrent_builds']}

[bold cyan]System Environment[/bold cyan]
[bold]Python Version:[/bold] {info_data['system']['python_version']}
[bold]Platform:[/bold] {info_data['system']['platform']}
[bold]Python Executable:[/bold] {info_data['system']['executable']}
"""
            
            panel = Panel(content.strip(), title="ℹ️ System Information")
            console.print(panel)
            
    except Exception as e:
        console.print(f"[red]Error getting system info: {e}[/red]")
        sys.exit(1)


@system.command('clean')
@click.option('--cache', is_flag=True, help='Clean build cache')
@click.option('--logs', is_flag=True, help='Clean log files')
@click.option('--builds', is_flag=True, help='Clean completed builds')
@click.option('--all', is_flag=True, help='Clean everything')
@click.option('--force', '-f', is_flag=True, help='Force clean without confirmation')
@pass_context
def system_clean(ctx: FrameworkContext, cache: bool, logs: bool, builds: bool, all: bool, force: bool):
    """Clean system artifacts"""
    
    if all:
        cache = logs = builds = True
    
    if not (cache or logs or builds):
        console.print("[yellow]No cleanup options specified. Use --cache, --logs, --builds, or --all[/yellow]")
        return
    
    cleanup_items = []
    if cache:
        cleanup_items.append("build cache")
    if logs:
        cleanup_items.append("log files")
    if builds:
        cleanup_items.append("completed builds")
    
    cleanup_text = ", ".join(cleanup_items)
    
    if not force and not click.confirm(f"Clean {cleanup_text}?"):
        console.print("[blue]Cleanup cancelled[/blue]")
        return
    
    try:
        cleaned_count = 0
        
        if cache:
            cache_dir = Path(ctx.config["cache_dir"])
            if cache_dir.exists():
                import shutil
                for item in cache_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                        cleaned_count += 1
                    elif item.is_file():
                        item.unlink()
                        cleaned_count += 1
                console.print(f"[green]✅ Cache cleaned ({cleaned_count} items)[/green]")
        
        if logs:
            logs_dir = Path(ctx.config["logs_dir"])
            if logs_dir.exists():
                for log_file in logs_dir.glob("*.log"):
                    log_file.unlink()
                    cleaned_count += 1
                console.print(f"[green]✅ Log files cleaned[/green]")
        
        if builds:
            # Cleanup old workflows (älter als 24 Stunden)
            if hasattr(ctx.orchestrator, 'cleanup_completed_workflows'):
                ctx.orchestrator.cleanup_completed_workflows(max_age_hours=24)
                console.print(f"[green]✅ Old workflows cleaned[/green]")
        
        console.print(f"[green]System cleanup completed[/green]")
        
    except Exception as e:
        console.print(f"[red]Error during cleanup: {e}[/red]")
        sys.exit(1)


@system.command('validate')
@pass_context
def system_validate(ctx: FrameworkContext):
    """Validate system requirements and installation"""
    
    try:
        # Verwende Orchestrator Validation
        from orchestrator.Core.orchestrator import validate_orchestrator_requirements
        
        validation_result = validate_orchestrator_requirements()
        
        console.print("[bold]System Validation Results:[/bold]\n")
        
        # Python Version
        if validation_result["python_version"]:
            console.print("[green]✅ Python version: OK[/green]")
        else:
            console.print("[red]❌ Python version: FAILED[/red]")
        
        # Dependencies
        console.print("\n[bold]Dependencies:[/bold]")
        for dep, available in validation_result["dependencies"].items():
            status = "✅ OK" if available else "❌ MISSING"
            color = "green" if available else "red"
            console.print(f"[{color}]{status} {dep}[/{color}]")
        
        # System Resources
        if validation_result.get("system_resources"):
            console.print("\n[bold]System Resources:[/bold]")
            resources = validation_result["system_resources"]
            
            if "memory_gb" in resources:
                memory_gb = resources["memory_gb"]
                memory_status = "✅ OK" if memory_gb >= 8 else "⚠️ LIMITED"
                memory_color = "green" if memory_gb >= 8 else "yellow"
                console.print(f"[{memory_color}]{memory_status} Memory: {memory_gb:.1f} GB[/{memory_color}]")
            
            if "disk_free_gb" in resources:
                disk_gb = resources["disk_free_gb"]
                disk_status = "✅ OK" if disk_gb >= 20 else "⚠️ LIMITED"
                disk_color = "green" if disk_gb >= 20 else "yellow"
                console.print(f"[{disk_color}]{disk_status} Disk Space: {disk_gb:.1f} GB free[/{disk_color}]")
            
            if "cpu_count" in resources:
                cpu_count = resources["cpu_count"]
                console.print(f"[blue]ℹ️ CPU Cores: {cpu_count}[/blue]")
        
        # Errors
        if validation_result["errors"]:
            console.print("\n[bold red]Errors:[/bold red]")
            for error in validation_result["errors"]:
                console.print(f"[red]❌ {error}[/red]")
        
        # Warnings
        if validation_result["warnings"]:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in validation_result["warnings"]:
                console.print(f"[yellow]⚠️ {warning}[/yellow]")
        
        # Overall Status
        has_errors = bool(validation_result["errors"])
        if not has_errors:
            console.print("\n[bold green]✅ System validation passed![/bold green]")
        else:
            console.print("\n[bold red]❌ System validation failed![/bold red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Error during system validation: {e}[/red]")
        sys.exit(1)


# ============================================================================
# CONFIG COMMANDS (KORRIGIERT)
# ============================================================================

@cli.group()
def config():
    """Configuration management"""
    pass


@config.command('show')
@click.option('--format', '-f', default='yaml', type=click.Choice(['yaml', 'json', 'table']))
@click.option('--key', '-k', help='Show specific configuration key')
@pass_context
def show_config(ctx: FrameworkContext, format: str, key: Optional[str]):
    """Show current configuration"""
    
    try:
        framework_config = ctx.framework_manager.get_config()
        
        # Konvertiere zu Dict für Anzeige
        config_dict = {
            "targets_dir": framework_config.targets_dir,
            "models_dir": framework_config.models_dir,
            "output_dir": framework_config.output_dir,
            "configs_dir": framework_config.configs_dir,
            "cache_dir": framework_config.cache_dir,
            "logs_dir": framework_config.logs_dir,
            "log_level": framework_config.log_level,
            "max_concurrent_builds": framework_config.max_concurrent_builds,
            "build_timeout": framework_config.build_timeout,
            "auto_cleanup": framework_config.auto_cleanup,
            "docker_registry": framework_config.docker_registry,
            "docker_namespace": framework_config.docker_namespace,
            "gui_theme": framework_config.gui_theme,
            "api_enabled": framework_config.api_enabled,
            "api_port": framework_config.api_port
        }
        
        if key:
            if key in config_dict:
                console.print(f"{key}: {config_dict[key]}")
            else:
                console.print(f"[red]Configuration key '{key}' not found[/red]")
                available_keys = ", ".join(config_dict.keys())
                console.print(f"Available keys: {available_keys}")
                sys.exit(1)
        else:
            if format == 'json':
                click.echo(json.dumps(config_dict, indent=2))
            elif format == 'table':
                table = Table(title="Configuration")
                table.add_column("Key", style="cyan", no_wrap=True)
                table.add_column("Value", style="green")
                
                for k, v in config_dict.items():
                    table.add_row(k, str(v))
                
                console.print(table)
            else:  # yaml
                click.echo(yaml.dump(config_dict, default_flow_style=False))
                
    except Exception as e:
        console.print(f"[red]Error showing configuration: {e}[/red]")
        sys.exit(1)


@config.command('set')
@click.argument('key')
@click.argument('value')
@click.option('--type', '-t', default='auto', 
              type=click.Choice(['auto', 'string', 'int', 'bool', 'float']),
              help='Value type')
@pass_context
def set_config(ctx: FrameworkContext, key: str, value: str, type: str):
    """Set a configuration value"""
    
    try:
        # Konvertiere Wert basierend auf Typ
        if type == 'auto':
            # Auto-detection
            if value.lower() in ('true', 'false'):
                converted_value = value.lower() == 'true'
            elif value.isdigit():
                converted_value = int(value)
            elif value.replace('.', '').isdigit():
                converted_value = float(value)
            else:
                converted_value = value
        elif type == 'string':
            converted_value = value
        elif type == 'int':
            converted_value = int(value)
        elif type == 'bool':
            converted_value = value.lower() in ('true', '1', 'yes', 'on')
        elif type == 'float':
            converted_value = float(value)
        
        # Update Configuration
        config_update = {key: converted_value}
        success = ctx.framework_manager.update_config(config_update)
        
        if success:
            console.print(f"[green]✅ Configuration updated: {key} = {converted_value}[/green]")
        else:
            console.print(f"[red]❌ Failed to update configuration key: {key}[/red]")
            sys.exit(1)
            
    except ValueError as e:
        console.print(f"[red]Invalid value type: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error setting configuration: {e}[/red]")
        sys.exit(1)


@config.command('reset')
@click.argument('key', required=False)
@click.option('--all', is_flag=True, help='Reset all configuration to defaults')
@click.option('--force', '-f', is_flag=True, help='Force reset without confirmation')
@pass_context
def reset_config(ctx: FrameworkContext, key: Optional[str], all: bool, force: bool):
    """Reset configuration to defaults"""
    
    if all:
        if not force and not click.confirm("Reset ALL configuration to defaults?"):
            console.print("[blue]Configuration reset cancelled[/blue]")
            return
        
        try:
            # Reset zu Default-Konfiguration
            success = ctx.framework_manager.update_config(DEFAULT_CONFIG)
            
            if success:
                console.print("[green]✅ All configuration reset to defaults[/green]")
            else:
                console.print("[red]❌ Failed to reset configuration[/red]")
                sys.exit(1)
                
        except Exception as e:
            console.print(f"[red]Error resetting configuration: {e}[/red]")
            sys.exit(1)
    
    elif key:
        if key not in DEFAULT_CONFIG:
            console.print(f"[red]Unknown configuration key: {key}[/red]")
            sys.exit(1)
        
        if not force and not click.confirm(f"Reset '{key}' to default value?"):
            console.print("[blue]Configuration reset cancelled[/blue]")
            return
        
        try:
            default_value = DEFAULT_CONFIG[key]
            config_update = {key: default_value}
            success = ctx.framework_manager.update_config(config_update)
            
            if success:
                console.print(f"[green]✅ Configuration reset: {key} = {default_value}[/green]")
            else:
                console.print(f"[red]❌ Failed to reset configuration key: {key}[/red]")
                sys.exit(1)
                
        except Exception as e:
            console.print(f"[red]Error resetting configuration: {e}[/red]")
            sys.exit(1)
    else:
        console.print("[yellow]Specify a key to reset or use --all to reset everything[/yellow]")
# ============================================================================
# ADDITIONAL UTILITY COMMANDS
# ============================================================================

@cli.group()
def models():
    """Model management and information"""
    pass


@models.command('list')
@click.option('--local', is_flag=True, help='List only local models')
@click.option('--format', '-f', default='table', type=click.Choice(['table', 'json', 'yaml']))
@pass_context
def list_models(ctx: FrameworkContext, local: bool, format: str):
    """List available models"""
    
    try:
        models_dir = Path(ctx.config["models_dir"])
        local_models = []
        
        if models_dir.exists():
            for model_path in models_dir.iterdir():
                if model_path.is_dir():
                    # Check for typical model files
                    has_model_files = any(
                        (model_path / f).exists() 
                        for f in ["config.json", "pytorch_model.bin", "model.safetensors"]
                    )
                    
                    if has_model_files:
                        local_models.append({
                            "name": model_path.name,
                            "path": str(model_path),
                            "size_mb": sum(f.stat().st_size for f in model_path.rglob('*') if f.is_file()) / (1024*1024)
                        })
        
        if format == 'table':
            if local_models:
                table = Table(title="Local Models")
                table.add_column("Name", style="cyan", no_wrap=True)
                table.add_column("Path", style="green")
                table.add_column("Size (MB)", style="yellow", justify="right")
                
                for model in local_models:
                    table.add_row(
                        model["name"],
                        model["path"],
                        f"{model['size_mb']:.1f}"
                    )
                
                console.print(table)
            else:
                console.print("[yellow]No local models found[/yellow]")
                console.print(f"[blue]Models directory: {models_dir}[/blue]")
        
        elif format == 'json':
            click.echo(json.dumps(local_models, indent=2))
        
        elif format == 'yaml':
            click.echo(yaml.dump(local_models, default_flow_style=False))
            
    except Exception as e:
        console.print(f"[red]Error listing models: {e}[/red]")
        sys.exit(1)


@models.command('info')
@click.argument('model_name')
@pass_context
def model_info(ctx: FrameworkContext, model_name: str):
    """Show information about a model"""
    
    try:
        models_dir = Path(ctx.config["models_dir"])
        model_path = models_dir / model_name
        
        if not model_path.exists():
            console.print(f"[red]Model '{model_name}' not found in {models_dir}[/red]")
            sys.exit(1)
        
        # Collect model information
        model_files = list(model_path.rglob('*'))
        total_size = sum(f.stat().st_size for f in model_files if f.is_file())
        
        config_file = model_path / "config.json"
        model_config = {}
        if config_file.exists():
            with open(config_file, 'r') as f:
                model_config = json.load(f)
        
        content = f"""
[bold]Model Name:[/bold] {model_name}
[bold]Path:[/bold] {model_path}
[bold]Total Size:[/bold] {total_size / (1024*1024*1024):.2f} GB
[bold]Files Count:[/bold] {len([f for f in model_files if f.is_file()])}

[bold]Architecture:[/bold] {model_config.get('architectures', ['Unknown'])[0]}
[bold]Model Type:[/bold] {model_config.get('model_type', 'Unknown')}
[bold]Torch Dtype:[/bold] {model_config.get('torch_dtype', 'Unknown')}
"""
        
        if 'vocab_size' in model_config:
            content += f"[bold]Vocabulary Size:[/bold] {model_config['vocab_size']:,}\n"
        
        if 'hidden_size' in model_config:
            content += f"[bold]Hidden Size:[/bold] {model_config['hidden_size']:,}\n"
        
        if 'num_hidden_layers' in model_config:
            content += f"[bold]Layers:[/bold] {model_config['num_hidden_layers']}\n"
        
        panel = Panel(content.strip(), title=f"Model: {model_name}")
        console.print(panel)
        
    except Exception as e:
        console.print(f"[red]Error getting model info: {e}[/red]")
        sys.exit(1)


# ============================================================================
# WORKFLOW COMMANDS
# ============================================================================

@cli.group()
def workflow():
    """Advanced workflow management"""
    pass


@workflow.command('batch')
@click.option('--models', '-m', multiple=True, required=True, help='Models to convert (can be specified multiple times)')
@click.option('--target', '-t', required=True, help='Target architecture')
@click.option('--format', '-f', default='gguf', help='Target format')
@click.option('--output-dir', '-o', required=True, help='Output directory')
@click.option('--parallel', is_flag=True, default=True, help='Enable parallel processing')
@click.option('--quantization', '-q', multiple=True, help='Quantization methods (can be specified multiple times)')
@pass_context
def batch_workflow(ctx: FrameworkContext, models: tuple, target: str, format: str, 
                   output_dir: str, parallel: bool, quantization: tuple):
    """Run batch conversion workflow"""
    
    try:
        # Validate parameters
        target_arch = target_arch_from_string(target)
        target_format = model_format_from_string(format)
        
        # Create batch build request
        build_request = BuildRequest(
            request_id="",
            workflow_type=WorkflowType.BATCH_CONVERSION,
            priority=PriorityLevel.NORMAL,
            models=list(models),
            targets=[target_arch],
            target_formats=[target_format],
            optimization_level=OptimizationLevel.BALANCED,
            quantization_options=list(quantization) if quantization else [],
            parallel_builds=parallel,
            output_base_dir=output_dir,
            description=f"CLI batch workflow: {len(models)} models -> {target} ({format})"
        )
        
        # Submit workflow
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            request_id = loop.run_until_complete(ctx.orchestrator.submit_build_request(build_request))
            
            console.print(Panel(
                f"[bold]Models:[/bold] {len(models)} models\n"
                f"[bold]Target:[/bold] {target}\n"
                f"[bold]Format:[/bold] {format}\n"
                f"[bold]Output:[/bold] {output_dir}\n"
                f"[bold]Parallel:[/bold] {parallel}\n"
                f"[bold]Quantization:[/bold] {', '.join(quantization) if quantization else 'None'}",
                title=f"🚀 Batch Workflow: {request_id}"
            ))
            
            console.print(f"[green]Batch workflow started with ID: {request_id}[/green]")
            console.print(f"Use 'llm-cli build status {request_id}' to check progress")
            
        finally:
            loop.close()
            
    except click.BadParameter as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Batch workflow failed: {e}[/red]")
        sys.exit(1)


@workflow.command('matrix')
@click.option('--models', '-m', multiple=True, required=True, help='Models to convert')
@click.option('--targets', '-t', multiple=True, required=True, help='Target architectures')  
@click.option('--formats', '-f', multiple=True, required=True, help='Target formats')
@click.option('--output-dir', '-o', required=True, help='Output directory')
@click.option('--max-concurrent', default=2, type=int, help='Maximum concurrent builds')
@pass_context
def matrix_workflow(ctx: FrameworkContext, models: tuple, targets: tuple, formats: tuple,
                    output_dir: str, max_concurrent: int):
    """Run full matrix conversion workflow"""
    
    try:
        # Validate parameters
        target_archs = [target_arch_from_string(t) for t in targets]
        target_formats = [model_format_from_string(f) for f in formats]
        
        total_builds = len(models) * len(target_archs) * len(target_formats)
        
        if total_builds > 20:
            if not click.confirm(f"This will create {total_builds} builds. Continue?"):
                console.print("[blue]Matrix workflow cancelled[/blue]")
                return
        
        # Create matrix build request
        build_request = BuildRequest(
            request_id="",
            workflow_type=WorkflowType.FULL_MATRIX,
            priority=PriorityLevel.NORMAL,
            models=list(models),
            targets=target_archs,
            target_formats=target_formats,
            optimization_level=OptimizationLevel.BALANCED,
            parallel_builds=True,
            max_concurrent=max_concurrent,
            output_base_dir=output_dir,
            description=f"CLI matrix workflow: {len(models)}×{len(targets)}×{len(formats)} = {total_builds} builds"
        )
        
        # Submit workflow
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            request_id = loop.run_until_complete(ctx.orchestrator.submit_build_request(build_request))
            
            console.print(Panel(
                f"[bold]Models:[/bold] {len(models)}\n"
                f"[bold]Targets:[/bold] {len(targets)}\n"
                f"[bold]Formats:[/bold] {len(formats)}\n"
                f"[bold]Total Builds:[/bold] {total_builds}\n"
                f"[bold]Max Concurrent:[/bold] {max_concurrent}\n"
                f"[bold]Output:[/bold] {output_dir}",
                title=f"🚀 Matrix Workflow: {request_id}"
            ))
            
            console.print(f"[green]Matrix workflow started with ID: {request_id}[/green]")
            console.print(f"Use 'llm-cli build status {request_id}' to check progress")
            
        finally:
            loop.close()
            
    except click.BadParameter as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Matrix workflow failed: {e}[/red]")
        sys.exit(1)


# ============================================================================
# MAIN ENTRY POINT (KORRIGIERT)
# ============================================================================

def handle_shutdown(ctx: FrameworkContext):
    """Handle graceful shutdown of framework components"""
    try:
        if ctx.orchestrator:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(ctx.orchestrator.shutdown())
            finally:
                loop.close()
        
        if ctx.framework_manager:
            ctx.framework_manager.shutdown()
            
    except Exception as e:
        console.print(f"[yellow]Warning: Shutdown error: {e}[/yellow]")


def main():
    """Main CLI entry point"""
    framework_context = None
    
    try:
        # CLI wird ausgeführt, Context wird durch Click automatisch erstellt
        cli()
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        
        # Versuche graceful shutdown
        try:
            if 'ctx' in locals() and hasattr(ctx, 'orchestrator'):
                handle_shutdown(ctx)
        except:
            pass
        
        sys.exit(130)
        
    except click.ClickException as e:
        # Click-spezifische Exceptions (z.B. falsche Parameter)
        e.show()
        sys.exit(e.exit_code)
        
    except ValidationError as e:
        console.print(f"[red]Validation Error: {e}[/red]")
        sys.exit(1)
        
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        
        # Zeige Traceback nur bei verbose
        if "--verbose" in sys.argv or "-v" in sys.argv:
            import traceback
            console.print("\n[bold]Traceback:[/bold]")
            console.print(traceback.format_exc())
        else:
            console.print("[blue]Use --verbose for detailed error information[/blue]")
        
        # Versuche graceful shutdown
        try:
            if framework_context:
                handle_shutdown(framework_context)
        except:
            pass
        
        sys.exit(1)


# ============================================================================
# AUTOCOMPLETE SUPPORT (BONUS)
# ============================================================================

def get_available_targets():
    """Get available targets for autocompletion"""
    try:
        return [arch.value for arch in TargetArch]
    except:
        return ["rk3566", "arm64", "x86_64"]


def get_available_formats():
    """Get available formats for autocompletion"""
    try:
        return [fmt.value for fmt in ModelFormat]
    except:
        return ["gguf", "onnx", "tflite"]


def get_local_models():
    """Get local models for autocompletion"""
    try:
        models_dir = Path("models")
        if models_dir.exists():
            return [d.name for d in models_dir.iterdir() if d.is_dir()]
    except:
        pass
    return []


# ============================================================================
# CLI ENHANCEMENTS
# ============================================================================

def print_startup_banner():
    """Print startup banner with system info"""
    console.print(Panel.fit(
        "[bold cyan]LLM Cross-Compiler Framework[/bold cyan]\n"
        "[dim]Professional edge AI cross-compilation[/dim]\n\n"
        f"[bold]Version:[/bold] {__version__}\n"
        f"[bold]Python:[/bold] {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n"
        f"[bold]Platform:[/bold] {sys.platform}",
        title="🚀 Framework CLI",
        border_style="cyan"
    ))


def print_help_footer():
    """Print helpful footer information"""
    console.print("\n[dim]Examples:[/dim]")
    console.print("  [cyan]llm-cli targets list[/cyan]                     # List available targets")
    console.print("  [cyan]llm-cli build start -m llama2 -t rk3566[/cyan]  # Build model for RK3566")
    console.print("  [cyan]llm-cli system status[/cyan]                    # Check system status")
    console.print("  [cyan]llm-cli workflow batch -m model1 -m model2[/cyan] # Batch convert models")


# ============================================================================
# VERSION INFO COMMAND
# ============================================================================

@cli.command('version')
@click.option('--format', '-f', default='human', type=click.Choice(['human', 'json', 'short']))
def version_command(format: str):
    """Show version information"""
    
    version_info = {
        "framework_version": __version__,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
        "executable": sys.executable
    }
    
    if format == 'json':
        click.echo(json.dumps(version_info, indent=2))
    elif format == 'short':
        click.echo(__version__)
    else:
        console.print(Panel(
            f"[bold]Framework Version:[/bold] {version_info['framework_version']}\n"
            f"[bold]Python Version:[/bold] {version_info['python_version']}\n"
            f"[bold]Platform:[/bold] {version_info['platform']}\n"
            f"[bold]Python Executable:[/bold] {version_info['executable']}",
            title="📋 Version Information"
        ))


if __name__ == "__main__":
    main()        