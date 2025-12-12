<#
.SYNOPSIS
    LLM Framework Hardware Analyzer (Enterprise Edition - Windows)
    
.DESCRIPTION
    Detects CPU features (AVX/NEON via Native Bridge), GPU/NPU hardware, and system resources.
    Generates 'target_hardware_config.txt'.
    
    HISTORY:
    v2.1.0: Added MemryX (MX3) and Axelera (Metis) detection logic.
    v2.0.1: Native API Bridge (C#) for accurate CPU feature detection.
    v2.0.0: GPU Driver Version extraction.
    
.NOTES
    File Name       : hardware_probe.ps1
    Author          : LLM Framework Team
    Prerequisite    : Windows PowerShell 5.1 or PowerShell Core 7+
#>

# 1. ADMIN CHECK
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "Script requires Administrator privileges for Hardware Detection."
    Write-Host "Attempting to elevate..." -ForegroundColor Yellow
    try {
        Start-Process PowerShell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        Exit
    } catch {
        Write-Error "Failed to elevate. Please run as Administrator manually."
        Exit 1
    }
}

# 2. SET EXECUTION POLICY
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force -ErrorAction SilentlyContinue

$ErrorActionPreference = "Stop"
$OutputFile = "target_hardware_config.txt"

function Log-Output {
    param ([string]$Message)
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] $Message"
    Add-Content -Path $OutputFile -Value $Message
}

# === INITIALIZATION ===
Write-Host "=== LLM Framework Hardware Probe (v2.1.0) ===" -ForegroundColor Cyan

Set-Content -Path $OutputFile -Value "# LLM Framework Hardware Profile (Windows)"
Add-Content -Path $OutputFile -Value "# Generated: $(Get-Date)"
Add-Content -Path $OutputFile -Value "# Hostname: $env:COMPUTERNAME"
Add-Content -Path $OutputFile -Value "# OS: Windows $([System.Environment]::OSVersion.Version)"

# === 1. NATIVE API BRIDGE (C# Injection) ===
# Innovation preservation: Using kernel32.dll for reliable CPU feature flags
$Kernel32Code = @"
using System;
using System.Runtime.InteropServices;
public class HardwareInfo {
    [DllImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsProcessorFeaturePresent(uint ProcessorFeature);
    public const uint PF_ARM_NEON_INSTRUCTIONS_AVAILABLE = 37;
    public const uint PF_AVX_INSTRUCTIONS_AVAILABLE = 27;
    public const uint PF_AVX2_INSTRUCTIONS_AVAILABLE = 39;
    public const uint PF_AVX512F_INSTRUCTIONS_AVAILABLE = 40;
}
"@
try { Add-Type -TypeDefinition $Kernel32Code -Language CSharp } catch { Log-Output "# Warning: Native Bridge failed." }

# === 2. HARDWARE DETECTION ===

# --- CPU ---
Log-Output "[CPU]"
try {
    $cpu = Get-CimInstance Win32_Processor
    Log-Output "Name=$($cpu.Name.Trim())"
    Log-Output "Architecture=$($env:PROCESSOR_ARCHITECTURE)"
    Log-Output "Cores=$($cpu.NumberOfCores)"
} catch { Log-Output "Name=Unknown" }

# Native Bridge Feature Checks
$hasNeon = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_ARM_NEON_INSTRUCTIONS_AVAILABLE)
$hasAvx = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX_INSTRUCTIONS_AVAILABLE)
$hasAvx2 = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX2_INSTRUCTIONS_AVAILABLE)
$hasAvx512 = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX512F_INSTRUCTIONS_AVAILABLE)
$hasFp16 = $false 

if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64" -and $hasNeon) { $hasFp16 = $true }
if ($hasAvx512) { $hasFp16 = $true }

Log-Output "SUPPORTS_NEON=$($hasNeon.ToString().ToUpper())"
Log-Output "SUPPORTS_AVX=$($hasAvx.ToString().ToUpper())"
Log-Output "SUPPORTS_AVX2=$($hasAvx2.ToString().ToUpper())"
Log-Output "SUPPORTS_AVX512=$($hasAvx512.ToString().ToUpper())"
Log-Output "SUPPORTS_FP16=$($hasFp16.ToString().ToUpper())"

# --- MEMORY ---
Log-Output "[MEMORY]"
try {
    $mem = Get-CimInstance Win32_ComputerSystem
    $memMB = [math]::Round($mem.TotalPhysicalMemory / 1MB)
    Log-Output "Total_RAM_MB=$memMB"
} catch { Log-Output "Total_RAM_MB=Unknown" }

# --- ACCELERATORS ---
Log-Output "[ACCELERATORS]"

# 1. NVIDIA GPU
if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
    try {
        $gpuinfo = nvidia-smi --query-gpu=name --format=csv,noheader
        if ($gpuinfo -is [array]) { $gpuinfo = $gpuinfo[0] }
        
        # v2.0.0: Driver Version Extraction
        $driverVer = nvidia-smi --query-gpu=driver_version --format=csv,noheader
        if ($driverVer -is [array]) { $driverVer = $driverVer[0] }
        
        Log-Output "GPU_VENDOR=NVIDIA"
        Log-Output "GPU_MODEL=$gpuinfo"
        Log-Output "GPU_DRIVER_VERSION=$driverVer"
        Log-Output "SUPPORTS_CUDA=ON"
    } catch { Log-Output "SUPPORTS_CUDA=OFF" }
} else { Log-Output "SUPPORTS_CUDA=OFF" }

# 2. Intel GPU (Arc / Iris Xe)
$intelGpus = Get-CimInstance Win32_VideoController | Where-Object { $_.PNPDeviceID -like "*VEN_8086*" }
if ($intelGpus) {
    foreach ($gpu in $intelGpus) {
        Log-Output "GPU_VENDOR=Intel"
        Log-Output "GPU_MODEL=$($gpu.Name)"
        
        # Driver Version from WMI
        Log-Output "GPU_DRIVER_VERSION=$($gpu.DriverVersion)"
        
        if ($gpu.Name -match "Arc") { Log-Output "SUPPORTS_INTEL_XPU=ON (Arc)" } 
        elseif ($gpu.Name -match "Iris") { Log-Output "SUPPORTS_INTEL_XPU=ON (Iris)" } 
        else { Log-Output "SUPPORTS_INTEL_XPU=ON (Generic)" }
    }
}

# 3. NPU Detection
$npuFound = $false

# Intel NPU (Core Ultra)
$intelNpu = Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like "*Intel(R) AI Boost*" -or $_.InstanceId -like "*INTC1085*" }
if ($intelNpu) {
    Log-Output "NPU_VENDOR=Intel"
    Log-Output "NPU_MODEL=AI Boost"
    Log-Output "SUPPORTS_INTEL_NPU=ON"
    $npuFound = $true
}

# Hailo NPU
$hailoNpu = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like "*VEN_1E60*" }
if ($hailoNpu) {
    Log-Output "NPU_VENDOR=Hailo"
    Log-Output "NPU_MODEL=Hailo-8"
    Log-Output "SUPPORTS_HAILO=ON"
    $npuFound = $true
}

# Rockchip (USB Mode / Maskrom)
$rkNpu = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like "*VID_2207*" }
if ($rkNpu) {
    Log-Output "NPU_VENDOR=Rockchip"
    Log-Output "NPU_MODEL=Rockchip Device (USB)"
    Log-Output "SUPPORTS_RKNN=ON"
    $npuFound = $true
}

# NEU v2.1.0: MemryX (MX3)
# Suche nach generischem Namen oder bekannter Vendor ID
$memryx = Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like "*MemryX*" }
if ($memryx) {
    Log-Output "NPU_VENDOR=MemryX"
    Log-Output "NPU_MODEL=MX3"
    Log-Output "SUPPORTS_MX3=ON"
    $npuFound = $true
}

# NEU v2.1.0: Axelera (Metis)
# Suche nach generischem Namen oder bekannter Vendor ID
$axelera = Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like "*Axelera*" }
if ($axelera) {
    Log-Output "NPU_VENDOR=Axelera"
    Log-Output "NPU_MODEL=Metis"
    Log-Output "SUPPORTS_METIS=ON"
    $npuFound = $true
}

if (-not $npuFound) { Log-Output "NPU_STATUS=None detected" }

# --- 4. SOFTWARE STACK ---
Log-Output "[SOFTWARE]"

# Check Docker
if (Get-Command docker -ErrorAction SilentlyContinue) {
    $DockerVer = (docker --version) -replace "Docker version ", "" -replace ",", ""
    Log-Output "DOCKER_VERSION=$DockerVer"
} else {
    Log-Output "DOCKER_VERSION=Missing"
}

# Check Python
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PyVer = (python --version) -replace "Python ", ""
    Log-Output "PYTHON_VERSION=$PyVer"
} else {
    Log-Output "PYTHON_VERSION=Missing"
}

Write-Host "`n✅ Probing complete. Config written to $OutputFile" -ForegroundColor Green
Start-Sleep -Seconds 2
