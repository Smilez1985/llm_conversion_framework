#!/bin/bash
# hardware_probe.sh - LLM Framework Hardware Analyzer (Linux Enterprise)
# DIREKTIVE: Goldstandard Detection.
#
# HISTORY:
# v2.1.0: Added MemryX (MX3) and Axelera (Metis) detection via lspci/lsusb.
# v2.0.0: Added Driver Version extraction and Docker/Python checks.
# v1.0.0: Initial CPU/RAM probe.

set -u

OUTPUT_FILE="target_hardware_config.txt"

# Header schreiben
{
    echo "# LLM Framework Hardware Profile"
    echo "# Generated: $(date)"
    echo "# Hostname: $(hostname)"
    echo "# Kernel: $(uname -r)"
    echo "PLATFORM=Linux"
} > "$OUTPUT_FILE"

# Konsistente Logging-Funktion
log() {
    echo "$1" | tee -a "$OUTPUT_FILE"
}

# Helper: Check dependency
check_cmd() {
    command -v "$1" >/dev/null 2>&1
}

echo "--- Starting Hardware Probe v2.1 ---"

# --- 1. CPU DETEKTION ---
# (Original Logic Preserved & Enhanced)
log "[CPU]"
CPU_ARCH=$(uname -m)
log "Architecture=$CPU_ARCH"

if [ "$CPU_ARCH" = "aarch64" ] || [ "$CPU_ARCH" = "arm64" ]; then
    if [ -f /proc/cpuinfo ]; then
        IMPL=$(grep "CPU implementer" /proc/cpuinfo | head -n1 | awk '{print $3}')
        PART=$(grep "CPU part" /proc/cpuinfo | head -n1 | awk '{print $3}')
        log "CPU_Implementer=$IMPL"
        log "CPU_Part=$PART"
        
        FEATURES=$(grep "Features" /proc/cpuinfo | head -n1)
        if echo "$FEATURES" | grep -iqE "neon|asimd"; then log "SUPPORTS_NEON=ON"; else log "SUPPORTS_NEON=OFF"; fi
        if echo "$FEATURES" | grep -iqE "fp16|fphp"; then log "SUPPORTS_FP16=ON"; else log "SUPPORTS_FP16=OFF"; fi
    fi
elif [ "$CPU_ARCH" = "x86_64" ]; then
    FLAGS=$(grep "flags" /proc/cpuinfo | head -n1)
    if echo "$FLAGS" | grep -iq "avx2"; then log "SUPPORTS_AVX2=ON"; else log "SUPPORTS_AVX2=OFF"; fi
    if echo "$FLAGS" | grep -iq "avx512f"; then log "SUPPORTS_AVX512=ON"; else log "SUPPORTS_AVX512=OFF"; fi
    if echo "$FLAGS" | grep -iq "avx512_vnni"; then log "SUPPORTS_AVX512_VNNI=ON"; else log "SUPPORTS_AVX512_VNNI=OFF"; fi
fi

# --- 2. RAM DETEKTION ---
log "[MEMORY]"
if check_cmd free; then
    MEM_TOTAL_KB=$(free | grep Mem | awk '{print $2}')
    MEM_TOTAL_MB=$((MEM_TOTAL_KB / 1024))
    log "Total_RAM_MB=$MEM_TOTAL_MB"
else
    log "Total_RAM_MB=Unknown"
fi

# --- 3. ACCELERATORS (GPU/NPU) ---
log "[ACCELERATORS]"

NPU_FOUND="FALSE"

# A. Rockchip NPU
if [ -d "/sys/kernel/debug/rknpu" ] || dmesg | grep -iq "rknpu"; then
    log "NPU_VENDOR=Rockchip"
    NPU_FOUND="TRUE"
    if dmesg | grep -iq "rk3588"; then
        log "NPU_MODEL=RK3588"
        log "SUPPORTS_RKLLM=ON"
    elif dmesg | grep -iqE "rk3566|rk3568"; then
        log "NPU_MODEL=RK3566_68"
        log "SUPPORTS_RKLLM=OFF"
    fi
fi

# B. NVIDIA GPU
if check_cmd nvidia-smi; then
    log "GPU_VENDOR=NVIDIA"
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)
    GPU_DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1)
    CUDA_VER=$(nvidia-smi --query-gpu=cuda_version --format=csv,noheader | head -n1)
    
    log "GPU_MODEL=$GPU_NAME"
    log "GPU_DRIVER_VERSION=$GPU_DRIVER"
    log "HOST_CUDA_VERSION=$CUDA_VER"
    log "SUPPORTS_CUDA=ON"
else
    log "SUPPORTS_CUDA=OFF"
fi

# C. Hailo NPU (PCIe)
if check_cmd lspci; then
    if lspci -d 1e60: 2>/dev/null | grep -iq "Hailo"; then
        log "NPU_VENDOR=Hailo"
        log "SUPPORTS_HAILO=ON"
        NPU_FOUND="TRUE"
    fi
fi

# D. MemryX MX3 (USB/PCIe) - NEU v2.1
# Check USB
if check_cmd lsusb; then
    # MemryX often appears with Vendor ID 1d6b (Linux Foundation) as prototype or specific ID
    # Searching by name is safer if descriptors are set
    if lsusb | grep -i "MemryX" > /dev/null; then
        log "NPU_VENDOR=MemryX"
        log "NPU_MODEL=MX3"
        log "SUPPORTS_MX3=ON"
        log "MX3_INTERFACE=USB"
        NPU_FOUND="TRUE"
    fi
fi
# Check PCIe
if check_cmd lspci; then
    if lspci | grep -i "MemryX" > /dev/null; then
        log "NPU_VENDOR=MemryX"
        log "NPU_MODEL=MX3"
        log "SUPPORTS_MX3=ON"
        log "MX3_INTERFACE=PCIe"
        NPU_FOUND="TRUE"
    fi
fi

# E. Axelera AI (Metis) - NEU v2.1
if check_cmd lspci; then
    # Search for Axelera in PCI devices
    if lspci | grep -i "Axelera" > /dev/null; then
        log "NPU_VENDOR=Axelera"
        log "NPU_MODEL=Metis"
        log "SUPPORTS_METIS=ON"
        NPU_FOUND="TRUE"
    fi
fi

# F. Intel GPU (Arc/iGPU)
if check_cmd lspci; then
    if lspci -d 8086: 2>/dev/null | grep -iE "VGA|Display|3D"; then
        GPU_INFO=$(lspci -d 8086: | grep -iE "VGA|Display|3D" | head -n1)
        # Simple heuristic
        if echo "$GPU_INFO" | grep -iq "Arc"; then
            log "GPU_VENDOR=Intel"
            log "GPU_MODEL=Intel_Arc"
            log "SUPPORTS_INTEL_XPU=ON"
        fi
    fi
fi

if [ "$NPU_FOUND" = "FALSE" ] && [ "$SUPPORTS_CUDA" = "OFF" ]; then
    log "NPU_STATUS=None detected"
fi

# --- 4. SOFTWARE STACK ---
log "[SOFTWARE]"

# Docker Check
if check_cmd docker; then
    DOCKER_VER=$(docker --version | awk '{print $3}' | tr -d ',')
    log "DOCKER_VERSION=$DOCKER_VER"
else
    log "DOCKER_VERSION=Missing"
fi

# Python Check
if check_cmd python3; then
    PY_VER=$(python3 --version | awk '{print $2}')
    log "PYTHON_VERSION=$PY_VER"
else
    log "PYTHON_VERSION=Missing"
fi

echo "Probe complete. Config written to $OUTPUT_FILE"
