<#
.SYNOPSIS
    LLM Framework Hardware Analyzer (Enterprise Edition)
    
.DESCRIPTION
    Detects CPU features (AVX/NEON), GPU/NPU hardware, and system resources.
    Generates 'target_hardware_config.txt' for the Module Wizard.
    
    Features:
    - Auto-Elevation to Administrator
    - Resilient Networking (Ping Loop)
    - Secure Downloads (SHA256 Verification)
    - Native API Access (Kernel32)
    
.NOTES
    File Name      : hardware_probe.ps1
    Author         : LLM Framework Team
    Prerequisite   : Windows PowerShell 5.1 or PowerShell Core 7+
#>

# 1. ADMIN CHECK & AUTO-ELEVATION
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "Script requires Administrator privileges for Hardware Detection (PnP/Drivers)."
    Write-Host "Attempting to elevate..." -ForegroundColor Yellow
    try {
        Start-Process PowerShell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        Exit
    } catch {
        Write-Error "Failed to elevate. Please run as Administrator manually."
        Exit 1
    }
}

# 2. SET EXECUTION POLICY (Process Scope Only)
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force -ErrorAction SilentlyContinue

$ErrorActionPreference = "Stop"
$OutputFile = "target_hardware_config.txt"

# ============================================================================
# UTILITY FUNCTIONS (GOLD STANDARD)
# ============================================================================

function Log-Output {
    param ([string]$Message)
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] $Message"
    Add-Content -Path $OutputFile -Value $Message
}

function Wait-For-Internet {
    param ([int]$TimeoutSeconds = 300)
    $startTime = Get-Date
    
    while ($true) {
        if ((Get-Date) - $startTime -gt (New-TimeSpan -Seconds $TimeoutSeconds)) {
            throw "Timeout waiting for Internet connection."
        }
        
        try {
            $ping = Test-Connection -ComputerName "8.8.8.8" -Count 1 -Quiet -ErrorAction Stop
            if ($ping) { return }
        } catch {
            # Silent catch
        }
        
        Write-Warning "Internet connection lost. Waiting... (Ctrl+C to cancel)"
        Start-Sleep -Seconds 2
    }
}

function Get-FileHashString {
    param ([string]$Path)
    $hash = Get-FileHash -Path $Path -Algorithm SHA256
    return $hash.Hash.ToLower()
}

function Download-Secure {
    param (
        [Parameter(Mandatory=$true)] [string]$Url,
        [Parameter(Mandatory=$true)] [string]$Destination,
        [string]$ExpectedHash = ""
    )
    
    Write-Host "Downloading $(Split-Path $Destination -Leaf)..." -ForegroundColor Cyan
    
    # 1. Network Check
    Wait-For-Internet
    
    try {
        # Download
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
        
        # 2. Security Check (Hash)
        if ($ExpectedHash -ne "") {
            $actualHash = Get-FileHashString -Path $Destination
            if ($actualHash -ne $ExpectedHash.ToLower()) {
                Remove-Item $Destination -Force
                throw "Security Alert: Hash mismatch for $Destination.`nExpected: $ExpectedHash`nActual:   $actualHash"
            }
            Write-Host "✅ Hash Verified ($actualHash)" -ForegroundColor Green
        }
    } catch {
        Write-Error "Download failed: $_"
        if (Test-Path $Destination) { Remove-Item $Destination -Force }
        throw
    }
}

function Check-Dependency {
    param ([string]$Name, [string]$CommandName)
    
    if (Get-Command $CommandName -ErrorAction SilentlyContinue) {
        Log-Output "DEPENDENCY_$($Name.ToUpper())=INSTALLED"
        return $true
    } else {
        Log-Output "DEPENDENCY_$($Name.ToUpper())=MISSING"
        Write-Warning "Missing Dependency: $Name"
        return $false
    }
}

# ============================================================================
# INITIALIZATION
# ============================================================================

Write-Host "=== LLM Framework Hardware Probe ===" -ForegroundColor Cyan

# Init Output File
Set-Content -Path $OutputFile -Value "# LLM Framework Hardware Profile (Windows)"
Add-Content -Path $OutputFile -Value "# Generated: $(Get-Date)"
Add-Content -Path $OutputFile -Value "# Hostname: $env:COMPUTERNAME"
Add-Content -Path $OutputFile -Value "# User: $env:USERNAME (Admin)"

# ============================================================================
# 1. NATIVE API BRIDGE (C# Injection for CPU Flags)
# ============================================================================
# This allows us to query IsProcessorFeaturePresent directly from Kernel32
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

try {
    Add-Type -TypeDefinition $Kernel32Code -Language CSharp
} catch {
    Log-Output "# Warning: Could not compile Native Bridge. Flags might be inaccurate."
}

# ============================================================================
# 2. HARDWARE DETECTION LOGIC
# ============================================================================

# --- CPU ---
Log-Output "[CPU]"
$cpu = Get-CimInstance Win32_Processor
Log-Output "Name=$($cpu.Name.Trim())"
Log-Output "Architecture=$($env:PROCESSOR_ARCHITECTURE)"
Log-Output "Cores=$($cpu.NumberOfCores)"
Log-Output "LogicalProcessors=$($cpu.NumberOfLogicalProcessors)"

# Feature Flags
$hasNeon = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_ARM_NEON_INSTRUCTIONS_AVAILABLE)
$hasAvx = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX_INSTRUCTIONS_AVAILABLE)
$hasAvx2 = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX2_INSTRUCTIONS_AVAILABLE)
$hasAvx512 = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX512F_INSTRUCTIONS_AVAILABLE)
$hasFp16 = $false 

# Heuristic for FP16 (ARMv8.2+ implies FP16 often, AVX512 implies it on x86)
if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64" -and $hasNeon) { $hasFp16 = $true }
if ($hasAvx512) { $hasFp16 = $true }

Log-Output "SUPPORTS_NEON=$($hasNeon.ToString().ToUpper())"
Log-Output "SUPPORTS_AVX=$($hasAvx.ToString().ToUpper())"
Log-Output "SUPPORTS_AVX2=$($hasAvx2.ToString().ToUpper())"
Log-Output "SUPPORTS_AVX512=$($hasAvx512.ToString().ToUpper())"
Log-Output "SUPPORTS_FP16=$($hasFp16.ToString().ToUpper())"

# --- MEMORY ---
Log-Output "[MEMORY]"
$mem = Get-CimInstance Win32_ComputerSystem
$memMB = [math]::Round($mem.TotalPhysicalMemory / 1MB)
Log-Output "Total_RAM_MB=$memMB"

# --- ACCELERATORS (GPU/NPU) ---
Log-Output "[ACCELERATORS]"

# 1. NVIDIA GPU
if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
    try {
        Log-Output "GPU_VENDOR=NVIDIA"
        # Parse CSV output safe
        $gpuinfo = nvidia-smi --query-gpu=name --format=csv,noheader
        if ($gpuinfo -is [array]) { $gpuinfo = $gpuinfo[0] }
        Log-Output "GPU_MODEL=$gpuinfo"
        Log-Output "SUPPORTS_CUDA=ON"
    } catch {
        Log-Output "SUPPORTS_CUDA=OFF"
    }
} else {
    Log-Output "SUPPORTS_CUDA=OFF"
}

# 2. NPU Detection via PnP
$npuFound = $false

# Intel NPU (Meteor Lake / Core Ultra)
$intelNpu = Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like "*Intel(R) AI Boost*" -or $_.InstanceId -like "*INTC1085*" }
if ($intelNpu) {
    Log-Output "NPU_VENDOR=Intel"
    Log-Output "NPU_MODEL=AI Boost"
    Log-Output "SUPPORTS_INTEL_NPU=ON"
    $npuFound = $true
}

# Hailo NPU (PCIe)
$hailoNpu = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like "*VEN_1E60*" }
if ($hailoNpu) {
    Log-Output "NPU_VENDOR=Hailo"
    Log-Output "NPU_MODEL=Hailo-8"
    Log-Output "SUPPORTS_HAILO=ON"
    $npuFound = $true
}

# Rockchip (USB Maskrom/ADB Mode)
$rkNpu = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like "*VID_2207*" }
if ($rkNpu) {
    Log-Output "NPU_VENDOR=Rockchip"
    Log-Output "NPU_MODEL=Rockchip Device (USB)"
    Log-Output "SUPPORTS_RKNN=ON"
    $npuFound = $true
}

if (-not $npuFound) {
    Log-Output "NPU_STATUS=None detected"
}

# ============================================================================
# 3. DEPENDENCY CHECK
# ============================================================================
Log-Output "[DEPENDENCIES]"
Check-Dependency "Docker" "docker"
Check-Dependency "Git" "git"
Check-Dependency "Python" "python"

Write-Host "`n✅ Probing complete. Config written to $OutputFile" -ForegroundColor Green
Write-Host "You can now import this file in the Module Wizard."
Start-Sleep -Seconds 2
