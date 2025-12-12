<#
.SYNOPSIS
    LLM Framework Hardware Analyzer (Enterprise Edition - Windows)
    
.DESCRIPTION
    Detects CPU features, GPU/NPU hardware via Hardware IDs (VID/PID).
    Generates 'target_hardware_config.txt'.
    
    HISTORY:
    v2.2.0: Added Strict VID/PID parsing for USB/PCI devices.
    v2.1.0: Added MemryX/Axelera detection.
    v2.0.1: Native API Bridge.
    
.NOTES
    File Name       : hardware_probe.ps1
    Author          : LLM Framework Team
#>

# 1. ADMIN CHECK
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "Script requires Administrator privileges."
    try {
        Start-Process PowerShell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        Exit
    } catch {
        Write-Error "Failed to elevate."
        Exit 1
    }
}

# 2. SETUP
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force -ErrorAction SilentlyContinue
$ErrorActionPreference = "Stop"
$OutputFile = "target_hardware_config.txt"

function Log-Output {
    param ([string]$Key, [string]$Value)
    $line = "$Key=$Value"
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] $line"
    Add-Content -Path $OutputFile -Value $line
}

function Get-DeviceIdPart {
    param ([string]$InstanceId, [string]$Type)
    # Extrahiert VID, PID, VEN, DEV aus dem String
    if ($InstanceId -match "$Type`_([0-9A-F]{4})") {
        return $Matches[1]
    }
    return "Unknown"
}

# === INITIALIZATION ===
Write-Host "=== LLM Framework Hardware Probe (v2.2) ===" -ForegroundColor Cyan
New-Item -Path $OutputFile -ItemType File -Force | Out-Null
Log-Output "GENERATED_AT" "$(Get-Date)"
Log-Output "PLATFORM" "Windows"
Log-Output "HOSTNAME" $env:COMPUTERNAME
Log-Output "OS_VERSION" "$([System.Environment]::OSVersion.Version)"

# === 1. NATIVE API BRIDGE (CPU Features) ===
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
try { Add-Type -TypeDefinition $Kernel32Code -Language CSharp } catch { Write-Warning "Native Bridge failed." }

# === 2. SYSTEM RESOURCE DETECTION ===
# --- CPU ---
try {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    Log-Output "CPU_MODEL" $cpu.Name.Trim()
    Log-Output "CPU_CORES" $cpu.NumberOfCores
} catch { Log-Output "CPU_MODEL" "Unknown" }

$hasAvx2 = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX2_INSTRUCTIONS_AVAILABLE)
$hasAvx512 = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX512F_INSTRUCTIONS_AVAILABLE)
Log-Output "SUPPORTS_AVX2" $hasAvx2.ToString().ToUpper()
Log-Output "SUPPORTS_AVX512" $hasAvx512.ToString().ToUpper()

# --- RAM ---
try {
    $mem = Get-CimInstance Win32_ComputerSystem
    $memMB = [math]::Round($mem.TotalPhysicalMemory / 1MB)
    Log-Output "RAM_TOTAL_MB" $memMB
} catch { Log-Output "RAM_TOTAL_MB" "Unknown" }

# === 3. ACCELERATOR DETECTION (STRICT ID CHECK) ===
Write-Host "Scanning for Accelerators..." -ForegroundColor Cyan

$npuFound = $false

# --- NVIDIA GPU (PCIe) ---
# Check via WMI/CIM is safer than nvidia-smi for ID checking
$nvidia = Get-PnpDevice -PresentOnly -Class Display | Where-Object { $_.InstanceId -match "VEN_10DE" } # NVIDIA Vendor ID
if ($nvidia) {
    $devId = Get-DeviceIdPart $nvidia.InstanceId "DEV"
    Log-Output "GPU_VENDOR" "NVIDIA"
    Log-Output "GPU_DEVICE_ID" "0x$devId"
    Log-Output "SUPPORTS_CUDA" "ON"
    
    # Get Details via SMI if avail
    if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
        $drv = nvidia-smi --query-gpu=driver_version --format=csv,noheader
        Log-Output "GPU_DRIVER_VERSION" $drv
    }
} else {
    Log-Output "SUPPORTS_CUDA" "OFF"
}

# --- ROCKCHIP NPU (USB) ---
# Vendor ID: 0x2207
$rkDev = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "VID_2207" }
if ($rkDev) {
    $pid = Get-DeviceIdPart $rkDev.InstanceId "PID"
    Log-Output "NPU_VENDOR" "Rockchip"
    Log-Output "NPU_DEVICE_ID" "0x$pid"
    
    # Mode Detection based on PID
    switch ($pid) {
        "350A" { Log-Output "NPU_MODE" "Maskrom (RK3588)" }
        "350B" { Log-Output "NPU_MODE" "Loader (RK3588)" }
        "0006" { Log-Output "NPU_MODE" "ADB/MTP" }
        "0019" { Log-Output "NPU_MODE" "ADB" }
        Default { Log-Output "NPU_MODE" "Unknown_PID_$pid" }
    }
    Log-Output "SUPPORTS_RKNN" "ON"
    $npuFound = $true
}

# --- MEMRYX MX3 (USB/PCIe) ---
# Vendor ID: 0x3526 (Example) or 0x1D6B (Linux Foundation mapped)
# Wir suchen primär nach VID, Fallback Name
$mx3 = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "VID_3526" -or $_.FriendlyName -like "*MemryX*" }
if ($mx3) {
    $pid = Get-DeviceIdPart $mx3.InstanceId "PID"
    Log-Output "NPU_VENDOR" "MemryX"
    Log-Output "NPU_MODEL" "MX3"
    Log-Output "NPU_DEVICE_ID" "0x$pid"
    Log-Output "SUPPORTS_MX3" "ON"
    $npuFound = $true
}

# --- AXELERA METIS (PCIe) ---
# Vendor ID: 0x1F4B (Axelera)
$metis = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "VEN_1F4B" }
if ($metis) {
    $dev = Get-DeviceIdPart $metis.InstanceId "DEV"
    Log-Output "NPU_VENDOR" "Axelera"
    Log-Output "NPU_MODEL" "Metis"
    Log-Output "NPU_DEVICE_ID" "0x$dev"
    Log-Output "SUPPORTS_METIS" "ON"
    $npuFound = $true
}

# --- HAILO AI (PCIe) ---
# Vendor ID: 0x1E60
$hailo = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "VEN_1E60" }
if ($hailo) {
    Log-Output "NPU_VENDOR" "Hailo"
    Log-Output "SUPPORTS_HAILO" "ON"
    $npuFound = $true
}

if (-not $npuFound) { Log-Output "NPU_STATUS" "None detected" }

# --- 4. SOFTWARE ---
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Log-Output "DOCKER_VERSION" ((docker --version) -replace "Docker version ", "" -replace ",", "")
} else {
    Log-Output "DOCKER_VERSION" "Missing"
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    Log-Output "PYTHON_VERSION" ((python --version) -replace "Python ", "")
}

Write-Host "✅ Probe complete." -ForegroundColor Green
