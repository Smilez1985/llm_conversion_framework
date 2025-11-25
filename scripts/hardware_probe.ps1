<#
.SYNOPSIS
    hardware_probe.ps1 - Windows Version
    Version: 1.0 (RTX + Hailo Support)
    
.DESCRIPTION
    Analysiert Windows-Host-Hardware (CPU, RAM, GPU, NPU) für das LLM Framework.
    Erzeugt eine key=value Konfigurationsdatei, die kompatibel zum Linux-Skript ist.
#>

$OutputFile = "target_hardware_config.txt"
$LogFile = "$env:TEMP\hardware_probe_log.txt"

# --- Hilfsfunktionen ---
function Write-Config {
    param([string]$Key, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { $Value = "UNKNOWN" }
    Add-Content -Path $OutputFile -Value "$Key=$Value" -Encoding UTF8
}

function Log-Message {
    param([string]$Message)
    Add-Content -Path $LogFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
}

# Init Files
"" | Set-Content -Path $OutputFile -Encoding UTF8
"" | Set-Content -Path $LogFile

Write-Host "Starte Windows Hardware Probe..."
Log-Message "Started probing on Windows"

# --- 1. OS & System ---
Write-Host "- Sammle OS Informationen..."
Write-Config "OS_DISTRO" "Windows"
Write-Config "OS_VERSION_ID" (Get-CimInstance Win32_OperatingSystem).Version
Write-Config "KERNEL_VERSION" ([System.Environment]::OSVersion.Version.ToString())
Write-Config "ARCHITECTURE_FULL" $env:PROCESSOR_ARCHITECTURE

# --- 2. CPU Details ---
Write-Host "- Sammle CPU Informationen..."
$cpu = Get-CimInstance Win32_Processor
Write-Config "CPU_MODEL_NAME" $cpu.Name.Trim()
Write-Config "CPU_CORES" $cpu.NumberOfLogicalProcessors
Write-Config "CPU_VENDOR_ID" $cpu.Manufacturer

# --- 3. RAM Analyse & Tiering (Identisch zur Linux Logik) ---
Write-Host "- Analysiere RAM..."
$compInfo = Get-CimInstance Win32_ComputerSystem
$totalRamMB = [math]::Round($compInfo.TotalPhysicalMemory / 1MB)
$osInfo = Get-CimInstance Win32_OperatingSystem
$freeRamMB = [math]::Round($osInfo.FreePhysicalMemory / 1024) # FreePhysicalMemory is in KB

Write-Config "SYSTEM_RAM_MB" $totalRamMB
Write-Config "SYSTEM_RAM_AVAILABLE_MB" $freeRamMB

# Tiering Logik
if ($totalRamMB -gt 15000) {
    Write-Config "MEMORY_TIER" "ULTRA"
    Write-Config "MAX_MODEL_SIZE_SUGGESTION" "14B_Q4_OR_8B_Q8"
} elseif ($totalRamMB -gt 7000) {
    Write-Config "MEMORY_TIER" "HIGH"
    Write-Config "MAX_MODEL_SIZE_SUGGESTION" "8B_Q4_KM"
} elseif ($totalRamMB -gt 3500) {
    Write-Config "MEMORY_TIER" "MID"
    Write-Config "MAX_MODEL_SIZE_SUGGESTION" "3B_Q4_KM"
} else {
    Write-Config "MEMORY_TIER" "LOW"
    Write-Config "MAX_MODEL_SIZE_SUGGESTION" "TINY_MODELS_ONLY"
}

# --- 4. GPU Detection (Fokus auf NVIDIA RTX) ---
Write-Host "- Suche nach GPUs..."
$gpus = Get-CimInstance Win32_VideoController
$nvidiaFound = $false

foreach ($gpu in $gpus) {
    if ($gpu.Name -match "NVIDIA") {
        $nvidiaFound = $true
        Write-Config "GPU_TYPE" "NVIDIA"
        Write-Config "GPU_MODEL" ($gpu.Name -replace " ", "_")
        
        # Versuche nvidia-smi zu nutzen für exakte VRAM Daten
        if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
            try {
                $driverVer = nvidia-smi --query-gpu=driver_version --format=csv,noheader
                Write-Config "GPU_DRIVER_VERSION" $driverVer
                
                # CUDA Version Check
                $cudaVer = nvidia-smi | Select-String "CUDA Version: ([0-9.]+)"
                if ($cudaVer -match "CUDA Version: ([0-9.]+)") {
                     Write-Config "CUDA_TOOLKIT_VERSION" $matches[1]
                }
            } catch {
                Log-Message "nvidia-smi found but failed to run"
            }
        } else {
             Write-Config "CUDA_TOOLKIT_VERSION" "DRIVER_INSTALLED_BUT_SMI_MISSING"
        }
        break # Erste NVIDIA GPU reicht fürs Erste
    }
}

if (-not $nvidiaFound) {
    # Check auf AMD oder Intel
    if ($gpus.Name -match "AMD" -or $gpus.Name -match "Radeon") {
        Write-Config "GPU_TYPE" "AMD"
    } elseif ($gpus.Name -match "Intel") {
        Write-Config "GPU_TYPE" "INTEL_IGPU"
    } else {
        Write-Config "GPU_TYPE" "GENERIC"
    }
}

# --- 5. NPU Detection (Hailo / PCIe Scan) ---
Write-Host "- Suche nach NPU (PCIe)..."
# In Powershell suchen wir nach der Vendor ID 1E60 (Hailo) in den PnP Devices
$hailoDev = Get-PnpDevice | Where-Object { $_.HardwareID -match "VEN_1E60" }

if ($hailoDev) {
    Write-Config "NPU_TYPE" "HAILO_8"
    Write-Config "NPU_CONNECTION" "PCIE"
    Write-Config "NPU_DETECTED" "TRUE"
} else {
    Write-Config "NPU_PCIE_CARD" "NONE"
}

# Hailo Software Stack Check
if (Get-Command "hailort-cli" -ErrorAction SilentlyContinue) {
    $hailoVer = hailort-cli --version
    Write-Config "HAILO_RT_VERSION" $hailoVer
} else {
    Write-Config "HAILO_SOFTWARE" "NOT_INSTALLED"
}

# --- 6. Abschluss ---
Write-Host "Hardware Probe abgeschlossen."
Write-Config "PROBE_TIMESTAMP" (Get-Date -Format "yyyy-MM-dd_HH:mm:ss")

Write-Host "Datei erstellt: $OutputFile" -ForegroundColor Green
