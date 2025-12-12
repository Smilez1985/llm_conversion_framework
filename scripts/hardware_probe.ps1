<#
.SYNOPSIS
    LLM Framework Hardware Analyzer (Enterprise Edition - Windows v2.4)
    
.DESCRIPTION
    Performs a deep scan of system hardware (CPU Caches, RAM Speed/Timings, Accelerators).
    Generates 'target_hardware_config.txt'.
    
    HISTORY:
    v2.4.0: Added Deep RAM Scan (Speed per DIMM), L2/L3 Cache Info.
    v2.3.0: Strict VID/PID extraction.
#>

# 1. ADMIN CHECK
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "Deep Scan requires Administrator privileges."
    try { Start-Process PowerShell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""; Exit }
    catch { Write-Error "Failed to elevate."; Exit 1 }
}

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
    if ($InstanceId -match "$Type`_([0-9A-F]{4})") { return $Matches[1] }
    return "Unknown"
}

# === INITIALIZATION ===
Write-Host "=== LLM Framework Hardware Probe v2.4 (Deep Scan) ===" -ForegroundColor Cyan
New-Item -Path $OutputFile -ItemType File -Force | Out-Null
Log-Output "GENERATED_AT" "$(Get-Date)"
Log-Output "PLATFORM" "Windows"
Log-Output "HOSTNAME" $env:COMPUTERNAME
Log-Output "OS_VERSION" "$([System.Environment]::OSVersion.Version)"

# === 1. NATIVE API BRIDGE (C#) ===
# (Preserved Original Logic)
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

# === 2. SYSTEM DEEP DIVE ===

# --- CPU (Caches & ID) ---
Write-Host "Analyzing CPU..." -ForegroundColor Green
try {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    Log-Output "CPU_MODEL" $cpu.Name.Trim()
    Log-Output "CPU_CORES_LOGICAL" $cpu.NumberOfLogicalProcessors
    Log-Output "CPU_CORES_PHYSICAL" $cpu.NumberOfCores
    Log-Output "CPU_DEVICE_ID" "$($cpu.ProcessorId)_REV$($cpu.Revision)"
    
    # Caches (KB)
    Log-Output "CPU_L2_CACHE_SIZE_KB" $cpu.L2CacheSize
    Log-Output "CPU_L3_CACHE_SIZE_KB" $cpu.L3CacheSize
} catch { Log-Output "CPU_INFO" "Partial/Error" }

# Instruction Sets
$hasAvx2 = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX2_INSTRUCTIONS_AVAILABLE)
$hasAvx512 = [HardwareInfo]::IsProcessorFeaturePresent([HardwareInfo]::PF_AVX512F_INSTRUCTIONS_AVAILABLE)
Log-Output "SUPPORTS_AVX2" $hasAvx2.ToString().ToUpper()
Log-Output "SUPPORTS_AVX512" $hasAvx512.ToString().ToUpper()

# --- MEMORY (Speed & Modules) ---
Write-Host "Analyzing Memory..." -ForegroundColor Green
try {
    $mems = Get-CimInstance Win32_PhysicalMemory
    $totalMem = 0
    $speeds = @()
    $types = @()
    
    foreach ($m in $mems) {
        $totalMem += $m.Capacity
        if ($m.Speed) { $speeds += $m.Speed }
        # MemoryType is often 0 (Unknown) on DDR4/5 in CIM, use SMBIOSMemoryType if possible, or fallback
        # Just logging configured clock speed is most important for bandwidth
    }
    
    Log-Output "RAM_TOTAL_MB" ([math]::Round($totalMem / 1MB))
    if ($speeds.Count -gt 0) {
        $maxSpeed = ($speeds | Measure-Object -Maximum).Maximum
        Log-Output "RAM_SPEED_MTS" $maxSpeed
    } else {
        Log-Output "RAM_SPEED_MTS" "Unknown"
    }
    Log-Output "RAM_MODULES_COUNT" $mems.Count
} catch { Log-Output "RAM_DETAILS" "Error reading CIM" }

# === 3. ACCELERATOR DETECTION (Strict ID) ===
Write-Host "Scanning Accelerators..." -ForegroundColor Green
$npuFound = $false

# A. NVIDIA
$nvidia = Get-PnpDevice -PresentOnly -Class Display | Where-Object { $_.InstanceId -match "VEN_10DE" }
if ($nvidia) {
    $devId = Get-DeviceIdPart $nvidia.InstanceId "DEV"
    $venId = Get-DeviceIdPart $nvidia.InstanceId "VEN"
    Log-Output "GPU_VENDOR" "NVIDIA"
    Log-Output "GPU_VENDOR_ID" "0x$venId"
    Log-Output "GPU_DEVICE_ID" "0x$devId"
    Log-Output "SUPPORTS_CUDA" "ON"
    
    if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
        $vram = nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits
        Log-Output "GPU_VRAM_MB" $vram
        Log-Output "GPU_DRIVER_VERSION" (nvidia-smi --query-gpu=driver_version --format=csv,noheader)
    }
} else { Log-Output "SUPPORTS_CUDA" "OFF" }

# B. Rockchip (USB)
$rkDev = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match "VID_2207" }
if ($rkDev) {
    $pid = Get-DeviceIdPart $rkDev.InstanceId "PID"
    Log-Output "NPU_VENDOR" "Rockchip"
    Log-Output "NPU_DEVICE_ID" "0x$pid"
    switch ($pid) {
        "350A" { Log-Output "NPU_MODE" "Maskrom (RK3588)" }
        "350B" { Log-Output "NPU_MODE" "Loader (RK3588)" }
        "0006" { Log-Output "NPU_MODE" "ADB/MTP" }
        "0019" { Log-Output "NPU_MODE" "ADB" }
        Default { Log-Output "NPU_MODE" "Unknown" }
    }
    Log-Output "SUPPORTS_RKNN" "ON"
    $npuFound = $true
}

# C. MemryX / Axelera / Hailo
function Check-Device ($Name, $VidSearch, $Flag) {
    $dev = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match $VidSearch -or $_.FriendlyName -like "*$Name*" }
    if ($dev) {
        # Try extract VID/PID if standard format
        if ($dev.InstanceId -match "VID_([0-9A-F]{4})&PID_([0-9A-F]{4})") {
            Log-Output "NPU_VENDOR_ID" "0x$($Matches[1])"
            Log-Output "NPU_DEVICE_ID" "0x$($Matches[2])"
        } elseif ($dev.InstanceId -match "VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})") {
            Log-Output "NPU_VENDOR_ID" "0x$($Matches[1])"
            Log-Output "NPU_DEVICE_ID" "0x$($Matches[2])"
        }
        Log-Output "NPU_VENDOR" $Name
        Log-Output $Flag "ON"
        return $true
    }
    return $false
}

if (Check-Device "MemryX" "VID_1D6B" "SUPPORTS_MX3") { $npuFound = $true }
if (Check-Device "Axelera" "VEN_1F4B" "SUPPORTS_METIS") { $npuFound = $true }
if (Check-Device "Hailo" "VEN_1E60" "SUPPORTS_HAILO") { $npuFound = $true }

if (-not $npuFound) { Log-Output "NPU_STATUS" "None" }

# --- 4. SOFTWARE ---
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Log-Output "DOCKER_VERSION" ((docker --version) -replace "Docker version ", "" -replace ",", "")
} else { Log-Output "DOCKER_VERSION" "Missing" }

Write-Host "✅ Deep Scan complete." -ForegroundColor Green
