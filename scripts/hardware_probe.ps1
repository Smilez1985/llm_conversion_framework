# hardware_probe.ps1 - LLM Framework Hardware Analyzer (Windows)
# DIREKTIVE: Goldstandard. Generiert target_hardware_config.txt
# ZWECK: Liefert Hardware-Infos für den Module Wizard (Ditto)

$ErrorActionPreference = "Stop"
$OutputFile = "target_hardware_config.txt"

function Log-Output {
    param ([string]$Message)
    Write-Host $Message
    Add-Content -Path $OutputFile -Value $Message
}

# Init File
Set-Content -Path $OutputFile -Value "# LLM Framework Hardware Profile (Windows)"
Add-Content -Path $OutputFile -Value "# Generated: $(Get-Date)"
Add-Content -Path $OutputFile -Value "# Hostname: $env:COMPUTERNAME"

# --- CPU DETEKTION ---
Log-Output "[CPU]"
$cpu = Get-CimInstance Win32_Processor
Log-Output "Name=$($cpu.Name)"
Log-Output "Architecture=$($env:PROCESSOR_ARCHITECTURE)"
Log-Output "Cores=$($cpu.NumberOfCores)"

# Feature Detection (Simuliert, da Windows das schwerer macht als Linux /proc/cpuinfo)
# Wir prüfen auf gängige Befehlssätze via Architektur
if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
    Log-Output "SUPPORTS_NEON=ON"
    Log-Output "SUPPORTS_FP16=ON"
} elseif ($env:PROCESSOR_ARCHITECTURE -like "*64*") {
    # Annahme auf modernen x64 CPUs
    Log-Output "SUPPORTS_AVX2=ON"
    # AVX512 ist schwerer zu detektieren ohne externes Tool, wir lassen es erstmal offen oder nutzen Coreinfo wenn vorhanden
}

# --- RAM DETEKTION ---
Log-Output "[MEMORY]"
$mem = Get-CimInstance Win32_ComputerSystem
$memMB = [math]::Round($mem.TotalPhysicalMemory / 1MB)
Log-Output "Total_RAM_MB=$memMB"

# --- GPU DETEKTION (NVIDIA) ---
Log-Output "[ACCELERATORS]"
try {
    if (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue) {
        Log-Output "GPU_VENDOR=NVIDIA"
        $gpuinfo = nvidia-smi --query-gpu=name --format=csv,noheader
        Log-Output "GPU_MODEL=$gpuinfo"
        Log-Output "SUPPORTS_CUDA=ON"
    } else {
        Log-Output "SUPPORTS_CUDA=OFF"
    }
} catch {
    Log-Output "SUPPORTS_CUDA=OFF"
}

# NPU Detection on Windows is tricky, usually requires drivers. 
# We assume if it's Windows, it's likely a dev machine, not the embedded target directly.

Write-Host "`n✅ Probing complete. Data written to $OutputFile"
