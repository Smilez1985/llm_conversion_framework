#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Helper Utilities
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Comprehensive helper utilities for file operations, system validation,
network operations, and cross-platform compatibility. Container-native
with Poetry+VENV, robust error recovery.

Key Responsibilities:
- File and directory operations with if-not-exist checks
- System command validation and execution
- Safe JSON/YAML processing with error recovery
- Network connectivity and download utilities
- Cross-platform compatibility helpers
- Resource monitoring and disk space management
- String and data manipulation utilities
- Retry mechanisms and timeout handling
"""

import os
import sys
import json
import shutil
import subprocess
import platform
import tempfile
import hashlib
import urllib.request
import urllib.parse
import socket
import time
import psutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple, Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
import queue
import re
import gzip
import tarfile
import zipfile

import yaml
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class OSType(Enum):
    """Operating system types"""
    WINDOWS = "windows"
    LINUX = "linux" 
    MACOS = "macos"
    UNKNOWN = "unknown"


class ArchiveFormat(Enum):
    """Supported archive formats"""
    ZIP = "zip"
    TAR = "tar"
    TAR_GZ = "tar.gz"
    TAR_BZ2 = "tar.bz2"
    GZ = "gz"


class RetryStrategy(Enum):
    """Retry strategies for operations"""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"
    NO_RETRY = "no_retry"


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class SystemInfo:
    """System information container"""
    os_type: OSType
    os_version: str
    architecture: str
    cpu_count: int
    memory_gb: float
    python_version: str
    
    # Disk information
    disk_total_gb: float
    disk_free_gb: float
    disk_used_gb: float
    
    # Network information
    has_internet: bool
    network_interfaces: List[str] = field(default_factory=list)
    
    # Container information
    is_container: bool = False
    container_runtime: Optional[str] = None


@dataclass
class DownloadProgress:
    """Download progress tracking"""
    url: str
    total_size: int = 0
    downloaded: int = 0
    speed_mbps: float = 0.0
    eta_seconds: Optional[int] = None
    start_time: datetime = field(default_factory=datetime.now)
    
    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage"""
        if self.total_size > 0:
            return (self.downloaded / self.total_size) * 100
        return 0.0
    
    @property
    def elapsed_time(self) -> timedelta:
        """Calculate elapsed time"""
        return datetime.now() - self.start_time


@dataclass
class RetryConfig:
    """Configuration for retry operations"""
    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    exceptions: Tuple[type, ...] = (Exception,)


# ============================================================================
# FILE AND DIRECTORY OPERATIONS
# ============================================================================

def ensure_directory(path: Union[str, Path], mode: int = 0o755) -> Path:
    """
    Ensure directory exists with proper error handling and permissions.
    
    Args:
        path: Directory path to create
        mode: Directory permissions (Unix-style)
        
    Returns:
        Path: Created directory path
        
    Raises:
        OSError: If directory cannot be created
    """
    dir_path = Path(path)
    
    if not dir_path.exists():
        try:
            dir_path.mkdir(parents=True, exist_ok=True, mode=mode)
        except PermissionError:
            raise OSError(f"Permission denied: Cannot create directory {dir_path}")
        except Exception as e:
            raise OSError(f"Failed to create directory {dir_path}: {e}")
    
    elif not dir_path.is_dir():
        raise OSError(f"Path exists but is not a directory: {dir_path}")
    
    # Verify write permissions
    if not os.access(dir_path, os.W_OK):
        raise OSError(f"Directory not writable: {dir_path}")
    
    return dir_path


def safe_remove_directory(path: Union[str, Path], force: bool = False) -> bool:
    """
    Safely remove directory with contents.
    
    Args:
        path: Directory path to remove
        force: Force removal even if directory is not empty
        
    Returns:
        bool: True if successful
    """
    dir_path = Path(path)
    
    if not dir_path.exists():
        return True
    
    if not dir_path.is_dir():
        return False
    
    try:
        if force:
            shutil.rmtree(dir_path)
        else:
            # Only remove if empty
            dir_path.rmdir()
        return True
    except Exception:
        return False


def safe_copy_file(src: Union[str, Path], dst: Union[str, Path], 
                  preserve_metadata: bool = True, create_dirs: bool = True) -> bool:
    """
    Safely copy file with error handling.
    
    Args:
        src: Source file path
        dst: Destination file path
        preserve_metadata: Whether to preserve metadata
        create_dirs: Whether to create destination directories
        
    Returns:
        bool: True if successful
    """
    src_path = Path(src)
    dst_path = Path(dst)
    
    if not src_path.exists() or not src_path.is_file():
        return False
    
    try:
        if create_dirs:
            ensure_directory(dst_path.parent)
        
        if preserve_metadata:
            shutil.copy2(src_path, dst_path)
        else:
            shutil.copy(src_path, dst_path)
        
        return True
    except Exception:
        return False


def calculate_file_checksum(file_path: Union[str, Path], algorithm: str = "sha256") -> Optional[str]:
    """
    Calculate file checksum.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (md5, sha1, sha256, sha512)
        
    Returns:
        str: Hex digest of checksum or None if failed
    """
    path = Path(file_path)
    
    if not path.exists() or not path.is_file():
        return None
    
    try:
        hasher = hashlib.new(algorithm)
        
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    except Exception:
        return None


def get_file_size(file_path: Union[str, Path]) -> int:
    """
    Get file size in bytes.
    
    Args:
        file_path: Path to file
        
    Returns:
        int: File size in bytes, 0 if file doesn't exist
    """
    path = Path(file_path)
    
    try:
        return path.stat().st_size if path.exists() else 0
    except Exception:
        return 0


def get_directory_size(directory: Union[str, Path]) -> int:
    """
    Calculate total size of directory and its contents.
    
    Args:
        directory: Directory path
        
    Returns:
        int: Total size in bytes
    """
    dir_path = Path(directory)
    
    if not dir_path.exists() or not dir_path.is_dir():
        return 0
    
    total_size = 0
    try:
        for item in dir_path.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size
    except Exception:
        pass
    
    return total_size


def find_files(directory: Union[str, Path], pattern: str = "*", 
              recursive: bool = True, case_sensitive: bool = True) -> List[Path]:
    """
    Find files matching pattern.
    
    Args:
        directory: Directory to search
        pattern: File pattern (glob style)
        recursive: Whether to search recursively
        case_sensitive: Whether pattern matching is case sensitive
        
    Returns:
        List[Path]: List of matching file paths
    """
    dir_path = Path(directory)
    
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    
    try:
        if recursive:
            files = list(dir_path.rglob(pattern))
        else:
            files = list(dir_path.glob(pattern))
        
        # Filter to files only
        files = [f for f in files if f.is_file()]
        
        # Case insensitive filtering if needed
        if not case_sensitive:
            pattern_lower = pattern.lower()
            files = [f for f in files if pattern_lower in f.name.lower()]
        
        return sorted(files)
    except Exception:
        return []


# ============================================================================
# SYSTEM COMMAND OPERATIONS
# ============================================================================

def check_command_exists(command: str) -> bool:
    """
    Check if a system command exists and is executable.
    
    Args:
        command: Command name to check
        
    Returns:
        bool: True if command exists and is executable
    """
    try:
        # Use 'which' on Unix-like systems, 'where' on Windows
        if platform.system().lower() == "windows":
            result = subprocess.run(
                ["where", command], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
        else:
            result = subprocess.run(
                ["which", command], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
        
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def execute_command(command: Union[str, List[str]], 
                   cwd: Optional[Union[str, Path]] = None,
                   timeout: Optional[int] = None,
                   capture_output: bool = True,
                   env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    """
    Execute system command with proper error handling.
    
    Args:
        command: Command to execute (string or list)
        cwd: Working directory
        timeout: Command timeout in seconds
        capture_output: Whether to capture stdout/stderr
        env: Environment variables
        
    Returns:
        Tuple[int, str, str]: (return_code, stdout, stderr)
    """
    if isinstance(command, str):
        # Split string command properly
        import shlex
        command = shlex.split(command)
    
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
            env=env
        )
        
        return result.returncode, result.stdout or "", result.stderr or ""
    
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds"
    except FileNotFoundError:
        return -1, "", f"Command not found: {command[0] if command else 'unknown'}"
    except Exception as e:
        return -1, "", f"Command execution failed: {str(e)}"


def execute_command_with_progress(command: Union[str, List[str]], 
                                 progress_callback: Optional[Callable[[str], None]] = None,
                                 **kwargs) -> Tuple[int, List[str], List[str]]:
    """
    Execute command with real-time output streaming.
    
    Args:
        command: Command to execute
        progress_callback: Callback for output lines
        **kwargs: Additional arguments for subprocess
        
    Returns:
        Tuple[int, List[str], List[str]]: (return_code, stdout_lines, stderr_lines)
    """
    if isinstance(command, str):
        import shlex
        command = shlex.split(command)
    
    stdout_lines = []
    stderr_lines = []
    
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **kwargs
        )
        
        # Read output in real-time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                stdout_lines.append(line)
                if progress_callback:
                    progress_callback(line)
        
        # Get any remaining stderr
        stderr_output = process.stderr.read()
        if stderr_output:
            stderr_lines.extend(stderr_output.strip().split('\n'))
        
        return process.returncode, stdout_lines, stderr_lines
    
    except Exception as e:
        return -1, [], [f"Command execution failed: {str(e)}"]


def get_command_output(command: Union[str, List[str]], **kwargs) -> Optional[str]:
    """
    Get command output as string, None if failed.
    
    Args:
        command: Command to execute
        **kwargs: Additional arguments for execute_command
        
    Returns:
        str: Command output or None if failed
    """
    return_code, stdout, stderr = execute_command(command, **kwargs)
    
    if return_code == 0:
        return stdout.strip()
    return None


# ============================================================================
# JSON/YAML PROCESSING
# ============================================================================

def safe_json_load(file_path: Union[str, Path], default: Any = None) -> Any:
    """
    Safely load JSON file with error handling.
    
    Args:
        file_path: Path to JSON file
        default: Default value if loading fails
        
    Returns:
        Any: Loaded JSON data or default value
    """
    path = Path(file_path)
    
    if not path.exists() or not path.is_file():
        return default
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def safe_json_save(data: Any, file_path: Union[str, Path], 
                  indent: int = 2, ensure_ascii: bool = False) -> bool:
    """
    Safely save data to JSON file.
    
    Args:
        data: Data to save
        file_path: Path to JSON file
        indent: JSON indentation
        ensure_ascii: Whether to ensure ASCII encoding
        
    Returns:
        bool: True if successful
    """
    path = Path(file_path)
    
    try:
        ensure_directory(path.parent)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii, default=str)
        
        return True
    except Exception:
        return False


def safe_yaml_load(file_path: Union[str, Path], default: Any = None) -> Any:
    """
    Safely load YAML file with error handling.
    
    Args:
        file_path: Path to YAML file
        default: Default value if loading fails
        
    Returns:
        Any: Loaded YAML data or default value
    """
    path = Path(file_path)
    
    if not path.exists() or not path.is_file():
        return default
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return default


def safe_yaml_save(data: Any, file_path: Union[str, Path], 
                  default_flow_style: bool = False) -> bool:
    """
    Safely save data to YAML file.
    
    Args:
        data: Data to save
        file_path: Path to YAML file
        default_flow_style: YAML flow style
        
    Returns:
        bool: True if successful
    """
    path = Path(file_path)
    
    try:
        ensure_directory(path.parent)
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=default_flow_style, 
                     allow_unicode=True, sort_keys=True)
        
        return True
    except Exception:
        return False


# ============================================================================
# NETWORK OPERATIONS
# ============================================================================

def check_internet_connectivity(urls: List[str] = None, timeout: int = 5) -> bool:
    """
    Check internet connectivity by testing multiple URLs.
    
    Args:
        urls: List of URLs to test (uses defaults if None)
        timeout: Request timeout in seconds
        
    Returns:
        bool: True if internet is accessible
    """
    if urls is None:
        urls = [
            "https://www.google.com",
            "https://www.github.com", 
            "https://www.cloudflare.com"
        ]
    
    for url in urls:
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return True
        except Exception:
            continue
    
    return False


def download_file(url: str, destination: Union[str, Path], 
                 progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
                 chunk_size: int = 8192, timeout: int = 30) -> bool:
    """
    Download file with progress tracking and resume support.
    
    Args:
        url: URL to download
        destination: Destination file path
        progress_callback: Progress callback function
        chunk_size: Download chunk size in bytes
        timeout: Request timeout in seconds
        
    Returns:
        bool: True if download successful
    """
    dest_path = Path(destination)
    ensure_directory(dest_path.parent)
    
    # Setup retry strategy
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    try:
        # Check if partial file exists for resume
        resume_header = {}
        downloaded = 0
        
        if dest_path.exists():
            downloaded = dest_path.stat().st_size
            resume_header = {'Range': f'bytes={downloaded}-'}
        
        # Start download
        response = session.get(url, headers=resume_header, stream=True, timeout=timeout)
        response.raise_for_status()
        
        # Get total size
        total_size = downloaded
        if 'content-length' in response.headers:
            total_size += int(response.headers['content-length'])
        elif 'content-range' in response.headers:
            # Parse content-range header
            range_info = response.headers['content-range']
            total_size = int(range_info.split('/')[-1])
        
        # Setup progress tracking
        progress = DownloadProgress(url=url, total_size=total_size, downloaded=downloaded)
        
        # Download file
        mode = 'ab' if downloaded > 0 else 'wb'
        with open(dest_path, mode) as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    progress.downloaded += len(chunk)
                    
                    # Update progress
                    if progress_callback:
                        # Calculate speed
                        elapsed = progress.elapsed_time.total_seconds()
                        if elapsed > 0:
                            progress.speed_mbps = (progress.downloaded * 8) / (elapsed * 1024 * 1024)
                            
                            # Calculate ETA
                            if progress.total_size > 0:
                                remaining = progress.total_size - progress.downloaded
                                if progress.speed_mbps > 0:
                                    progress.eta_seconds = int(remaining * 8 / (progress.speed_mbps * 1024 * 1024))
                        
                        progress_callback(progress)
        
        return True
    
    except Exception:
        # Clean up partial file on failure
        if dest_path.exists() and downloaded == 0:
            dest_path.unlink()
        return False


def get_url_info(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Get information about URL without downloading.
    
    Args:
        url: URL to check
        timeout: Request timeout
        
    Returns:
        dict: URL information
    """
    info = {
        "url": url,
        "accessible": False,
        "size_bytes": 0,
        "content_type": "",
        "last_modified": None,
        "supports_resume": False
    }
    
    try:
        response = requests.head(url, timeout=timeout)
        response.raise_for_status()
        
        info["accessible"] = True
        
        if 'content-length' in response.headers:
            info["size_bytes"] = int(response.headers['content-length'])
        
        if 'content-type' in response.headers:
            info["content_type"] = response.headers['content-type']
        
        if 'last-modified' in response.headers:
            info["last_modified"] = response.headers['last-modified']
        
        if 'accept-ranges' in response.headers:
            info["supports_resume"] = response.headers['accept-ranges'] == 'bytes'
    
    except Exception:
        pass
    
    return info


# ============================================================================
# SYSTEM INFORMATION
# ============================================================================

def get_system_info() -> SystemInfo:
    """
    Get comprehensive system information.
    
    Returns:
        SystemInfo: System information container
    """
    # Detect OS type
    system = platform.system().lower()
    if system == "windows":
        os_type = OSType.WINDOWS
    elif system == "linux":
        os_type = OSType.LINUX
    elif system == "darwin":
        os_type = OSType.MACOS
    else:
        os_type = OSType.UNKNOWN
    
    # Get memory info
    memory_bytes = psutil.virtual_memory().total
    memory_gb = memory_bytes / (1024 ** 3)
    
    # Get disk info
    disk_usage = psutil.disk_usage('/')
    disk_total_gb = disk_usage.total / (1024 ** 3)
    disk_free_gb = disk_usage.free / (1024 ** 3)
    disk_used_gb = (disk_usage.total - disk_usage.free) / (1024 ** 3)
    
    # Get network interfaces
    network_interfaces = list(psutil.net_if_addrs().keys())
    
    # Check internet connectivity
    has_internet = check_internet_connectivity()
    
    # Check if running in container
    is_container = (
        os.path.exists('/.dockerenv') or 
        os.environ.get('container') is not None or
        os.environ.get('KUBERNETES_SERVICE_HOST') is not None
    )
    
    # Detect container runtime
    container_runtime = None
    if is_container:
        if os.path.exists('/.dockerenv'):
            container_runtime = "docker"
        elif os.environ.get('KUBERNETES_SERVICE_HOST'):
            container_runtime = "kubernetes"
        else:
            container_runtime = "unknown"
    
    return SystemInfo(
        os_type=os_type,
        os_version=platform.platform(),
        architecture=platform.machine(),
        cpu_count=psutil.cpu_count(),
        memory_gb=memory_gb,
        python_version=platform.python_version(),
        disk_total_gb=disk_total_gb,
        disk_free_gb=disk_free_gb,
        disk_used_gb=disk_used_gb,
        has_internet=has_internet,
        network_interfaces=network_interfaces,
        is_container=is_container,
        container_runtime=container_runtime
    )


def get_available_disk_space(path: Union[str, Path] = ".") -> int:
    """
    Get available disk space in bytes.
    
    Args:
        path: Path to check (defaults to current directory)
        
    Returns:
        int: Available disk space in bytes
    """
    try:
        return psutil.disk_usage(str(path)).free
    except Exception:
        return 0


def check_disk_space(path: Union[str, Path], required_gb: float) -> bool:
    """
    Check if sufficient disk space is available.
    
    Args:
        path: Path to check
        required_gb: Required space in GB
        
    Returns:
        bool: True if sufficient space available
    """
    available_bytes = get_available_disk_space(path)
    required_bytes = required_gb * (1024 ** 3)
    
    return available_bytes >= required_bytes


def get_cpu_info() -> Dict[str, Any]:
    """
    Get CPU information.
    
    Returns:
        dict: CPU information
    """
    return {
        "count": psutil.cpu_count(),
        "logical_count": psutil.cpu_count(logical=True),
        "frequency_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
        "usage_percent": psutil.cpu_percent(interval=1),
        "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
    }


def get_memory_info() -> Dict[str, Any]:
    """
    Get memory information.
    
    Returns:
        dict: Memory information
    """
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    
    return {
        "total_gb": memory.total / (1024 ** 3),
        "available_gb": memory.available / (1024 ** 3),
        "used_gb": memory.used / (1024 ** 3),
        "free_gb": memory.free / (1024 ** 3),
        "percent_used": memory.percent,
        "swap_total_gb": swap.total / (1024 ** 3),
        "swap_used_gb": swap.used / (1024 ** 3),
        "swap_percent": swap.percent
    }


# ============================================================================
# RETRY MECHANISMS
# ============================================================================

def retry_operation(func: Callable, config: RetryConfig = None, *args, **kwargs) -> Any:
    """
    Retry operation with configurable strategy.
    
    Args:
        func: Function to retry
        config: Retry configuration
        *args: Function arguments
        **kwargs: Function keyword arguments
        
    Returns:
        Any: Function result
        
    Raises:
        Exception: Last exception if all retries failed
    """
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            return func(*args, **kwargs)
        except config.exceptions as e:
            last_exception = e
            
            if attempt < config.max_attempts - 1:
                # Calculate delay
                if config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
                    delay = min(config.base_delay * (config.backoff_factor ** attempt), config.max_delay)
                elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
                    delay = min(config.base_delay * (attempt + 1), config.max_delay)
                elif config.strategy == RetryStrategy.FIXED_DELAY:
                    delay = config.base_delay
                else:
                    delay = 0
                
                if delay > 0:
                    time.sleep(delay)
    
    # All retries failed
    if last_exception:
        raise last_exception
    else:
        raise RuntimeError("All retry attempts failed")


# ============================================================================
# ARCHIVE OPERATIONS
# ============================================================================

def extract_archive(archive_path: Union[str, Path], destination: Union[str, Path],
                   format: Optional[ArchiveFormat] = None) -> bool:
    """
    Extract archive file.
    
    Args:
        archive_path: Path to archive file
        destination: Extraction destination
        format: Archive format (auto-detected if None)
        
    Returns:
        bool: True if successful
    """
    archive_file = Path(archive_path)
    dest_dir = Path(destination)
    
    if not archive_file.exists():
        return False
    
    ensure_directory(dest_dir)
    
    # Auto-detect format if not specified
    if format is None:
        format = _detect_archive_format(archive_file)
    
    try:
        if format == ArchiveFormat.ZIP:
            with zipfile.ZipFile(archive_file, 'r') as zip_ref:
                zip_ref.extractall(dest_dir)
        
        elif format in [ArchiveFormat.TAR, ArchiveFormat.TAR_GZ, ArchiveFormat.TAR_BZ2]:
            mode = 'r'
            if format == ArchiveFormat.TAR_GZ:
                mode = 'r:gz'
            elif format == ArchiveFormat.TAR_BZ2:
                mode = 'r:bz2'
            
            with tarfile.open(archive_file, mode) as tar_ref:
                tar_ref.extractall(dest_dir)
        
        elif format == ArchiveFormat.GZ:
            with gzip.open(archive_file, 'rb') as gz_ref:
                output_file = dest_dir / archive_file.stem
                with open(output_file, 'wb') as out_ref:
                    shutil.copyfileobj(gz_ref, out_ref)
        
        else:
            return False
        
        return True
    
    except Exception:
        return False


def create_archive(source_path: Union[str, Path], archive_path: Union[str, Path],
                  format: ArchiveFormat = ArchiveFormat.TAR_GZ) -> bool:
    """
    Create archive from source path.
    
    Args:
        source_path: Source file or directory
        archive_path: Archive file path
        format: Archive format
        
    Returns:
        bool: True if successful
    """
    source = Path(source_path)
    archive = Path(archive_path)
    
    if not source.exists():
        return False
    
    ensure_directory(archive.parent)
    
    try:
        if format == ArchiveFormat.ZIP:
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                if source.is_file():
                    zip_ref.write(source, source.name)
                else:
                    for file_path in source.rglob("*"):
                        if file_path.is_file():
                            zip_ref.write(file_path, file_path.relative_to(source.parent))
        
        elif format in [ArchiveFormat.TAR, ArchiveFormat.TAR_GZ, ArchiveFormat.TAR_BZ2]:
            mode = 'w'
            if format == ArchiveFormat.TAR_GZ:
                mode = 'w:gz'
            elif format == ArchiveFormat.TAR_BZ2:
                mode = 'w:bz2'
            
            with tarfile.open(archive, mode) as tar_ref:
                tar_ref.add(source, arcname=source.name)
        
        else:
            return False
        
        return True
    
    except Exception:
        return False


def _detect_archive_format(archive_path: Path) -> ArchiveFormat:
    """Detect archive format from file extension"""
    suffix = archive_path.suffix.lower()
    
    if suffix == '.zip':
        return ArchiveFormat.ZIP
    elif suffix == '.gz':
        if archive_path.name.endswith('.tar.gz'):
            return ArchiveFormat.TAR_GZ
        else:
            return ArchiveFormat.GZ
    elif suffix == '.bz2':
        return ArchiveFormat.TAR_BZ2
    elif suffix == '.tar':
        return ArchiveFormat.TAR
    else:
        return ArchiveFormat.TAR_GZ  # Default


# ============================================================================
# STRING AND DATA UTILITIES
# ============================================================================

def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """
    Sanitize filename for cross-platform compatibility.
    
    Args:
        filename: Original filename
        replacement: Replacement character for invalid chars
        
    Returns:
        str: Sanitized filename
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, replacement)
    
    # Remove leading/trailing whitespace and dots
    filename = filename.strip(' .')
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        max_name_len = 255 - len(ext)
        filename = name[:max_name_len] + ext
    
    # Ensure not empty
    if not filename:
        filename = "unnamed"
    
    return filename


def format_bytes(bytes_value: int, decimal_places: int = 2) -> str:
    """
    Format bytes value as human-readable string.
    
    Args:
        bytes_value: Value in bytes
        decimal_places: Number of decimal places
        
    Returns:
        str: Formatted string (e.g., "1.23 GB")
    """
    if bytes_value == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    
    value = float(bytes_value)
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    
    return f"{value:.{decimal_places}f} {units[unit_index]}"


def format_duration(seconds: float, precision: str = "auto") -> str:
    """
    Format duration as human-readable string.
    
    Args:
        seconds: Duration in seconds
        precision: Precision level (auto, seconds, minutes, hours)
        
    Returns:
        str: Formatted duration string
    """
    if seconds < 0:
        return "0s"
    
    # Auto-select precision
    if precision == "auto":
        if seconds < 60:
            precision = "seconds"
        elif seconds < 3600:
            precision = "minutes"
        else:
            precision = "hours"
    
    if precision == "seconds":
        return f"{seconds:.1f}s"
    elif precision == "minutes":
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    elif precision == "hours":
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        # Full format
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        
        return " ".join(parts)


def parse_version(version_string: str) -> Tuple[int, ...]:
    """
    Parse version string into tuple of integers.
    
    Args:
        version_string: Version string (e.g., "1.2.3")
        
    Returns:
        tuple: Version tuple (e.g., (1, 2, 3))
    """
    try:
        # Remove 'v' prefix if present
        if version_string.startswith('v'):
            version_string = version_string[1:]
        
        # Split by dots and convert to integers
        parts = version_string.split('.')
        return tuple(int(part) for part in parts if part.isdigit())
    except Exception:
        return (0,)


def compare_versions(version1: str, version2: str) -> int:
    """
    Compare two version strings.
    
    Args:
        version1: First version string
        version2: Second version string
        
    Returns:
        int: -1 if version1 < version2, 0 if equal, 1 if version1 > version2
    """
    v1_tuple = parse_version(version1)
    v2_tuple = parse_version(version2)
    
    # Pad shorter version with zeros
    max_len = max(len(v1_tuple), len(v2_tuple))
    v1_padded = v1_tuple + (0,) * (max_len - len(v1_tuple))
    v2_padded = v2_tuple + (0,) * (max_len - len(v2_tuple))
    
    if v1_padded < v2_padded:
        return -1
    elif v1_padded > v2_padded:
        return 1
    else:
        return 0


def generate_unique_id(prefix: str = "", length: int = 8) -> str:
    """
    Generate unique identifier.
    
    Args:
        prefix: Optional prefix
        length: Length of random part
        
    Returns:
        str: Unique identifier
    """
    import uuid
    
    if length <= 0:
        random_part = str(uuid.uuid4()).replace('-', '')
    else:
        random_part = str(uuid.uuid4()).replace('-', '')[:length]
    
    if prefix:
        return f"{prefix}_{random_part}"
    else:
        return random_part


# ============================================================================
# CLEANUP AND UTILITIES
# ============================================================================

def cleanup_temp_files(temp_dir: Optional[Union[str, Path]] = None, 
                      max_age_hours: int = 24) -> int:
    """
    Clean up temporary files older than specified age.
    
    Args:
        temp_dir: Temporary directory (uses system temp if None)
        max_age_hours: Maximum age in hours
        
    Returns:
        int: Number of files cleaned
    """
    if temp_dir is None:
        temp_dir = Path(tempfile.gettempdir())
    else:
        temp_dir = Path(temp_dir)
    
    if not temp_dir.exists():
        return 0
    
    cutoff_time = time.time() - (max_age_hours * 3600)
    cleaned_count = 0
    
    try:
        for item in temp_dir.iterdir():
            try:
                # Check if file is old enough
                if item.stat().st_mtime < cutoff_time:
                    if item.is_file():
                        item.unlink()
                        cleaned_count += 1
                    elif item.is_dir():
                        shutil.rmtree(item)
                        cleaned_count += 1
            except Exception:
                # Skip files that can't be accessed or deleted
                continue
        
        return cleaned_count
    except Exception:
        return 0


def validate_environment() -> Dict[str, Any]:
    """
    Validate framework environment and dependencies.
    
    Returns:
        dict: Validation results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "system_info": {},
        "dependencies": {}
    }
    
    try:
        # Get system information
        system_info = get_system_info()
        results["system_info"] = {
            "os": system_info.os_type.value,
            "architecture": system_info.architecture,
            "memory_gb": system_info.memory_gb,
            "disk_free_gb": system_info.disk_free_gb,
            "python_version": system_info.python_version,
            "is_container": system_info.is_container
        }
        
        # Check minimum requirements
        if system_info.memory_gb < 4:
            results["warnings"].append("Low memory: Less than 4GB RAM available")
        
        if system_info.disk_free_gb < 10:
            results["warnings"].append("Low disk space: Less than 10GB free")
        
        # Check Python version
        python_version = parse_version(system_info.python_version)
        if python_version < (3, 8):
            results["errors"].append("Python 3.8+ required")
            results["valid"] = False
        
        # Check essential commands
        essential_commands = ["docker", "git"]
        for cmd in essential_commands:
            if check_command_exists(cmd):
                results["dependencies"][cmd] = "available"
            else:
                results["dependencies"][cmd] = "missing"
                results["warnings"].append(f"Command not found: {cmd}")
        
        # Check internet connectivity
        if not system_info.has_internet:
            results["warnings"].append("No internet connectivity detected")
        
    except Exception as e:
        results["errors"].append(f"Environment validation failed: {str(e)}")
        results["valid"] = False
    
    return results


# ============================================================================
# MODULE INITIALIZATION
# ============================================================================

def get_helpers_info() -> Dict[str, Any]:
    """
    Get information about helpers module.
    
    Returns:
        dict: Module information
    """
    return {
        "module": "orchestrator.utils.helpers",
        "version": "1.0.0",
        "description": "Helper utilities for LLM Cross-Compiler Framework",
        "functions": [
            "ensure_directory", "safe_copy_file", "calculate_file_checksum",
            "check_command_exists", "execute_command", "safe_json_load",
            "safe_yaml_load", "download_file", "get_system_info",
            "retry_operation", "extract_archive", "format_bytes"
        ],
        "system_info": get_system_info().__dict__
    }


# Initialize module with validation check
try:
    _module_validation = validate_environment()
    if not _module_validation["valid"]:
        print(f"Warning: Environment validation issues detected: {_module_validation['errors']}")
except Exception:
    pass  # Don't break import if validation fails