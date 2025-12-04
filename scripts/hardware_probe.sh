#!/bin/bash
# hardware_probe.sh - LLM Framework Hardware Analyzer
# DIREKTIVE: Goldstandard. Generiert target_hardware_config.txt
#
# HISTORY:
# v2.0.0: EXPLICIT extraction of GPU/NPU Driver Versions (Critical for Consistency Check).
# v1.7.0: Added detailed Intel CPU (AVX512_VNNI, AMX) & GPU (Arc/XPU) detection.
#         Improved logging consistency.

set -u

OUTPUT_FILE="target_hardware_config.txt"

# Header schreiben
{
    echo "# LLM Framework Hardware Profile"
    echo "# Generated: $(date)"
    echo "# Hostname: $(hostname)"
    echo "# Kernel: $(uname -r)"
} > "$OUTPUT_FILE"

# Konsistente Logging-Funktion (Goldstandard)
log() {
    echo "$1" | tee -a "$OUTPUT_FILE"
}

# --- CPU DETEKTION ---
log "[CPU]"
CPU_ARCH=$(uname -m)
log "Architecture=$CPU_ARCH"

if [ "$CPU_ARCH" = "aarch64" ] || [ "$CPU_ARCH" = "arm64" ]; then
    # === ARM Specifics ===
    if [ -f /proc/cpuinfo ]; then
        IMPL=$(grep "CPU implementer" /proc/cpuinfo | head -n1 | awk '{print $3}')
        PART=$(grep "CPU part" /proc/cpuinfo | head -n1 | awk '{print $3}')
        log "CPU_Implementer=$IMPL"
        log "CPU_Part=$PART"
        
        FEATURES=$(grep "Features" /proc/cpuinfo | head -n1)
        
        if echo "$FEATURES" | grep -iqE "neon|asimd"; then log "SUPPORTS_NEON=ON"; else log "SUPPORTS_NEON=OFF"; fi
        if echo "$FEATURES" | grep -iqE "fp16|fphp"; then log "SUPPORTS_FP16=ON"; else log "SUPPORTS_FP16=OFF"; fi
        if echo "$FEATURES" | grep -iq "v8"; then log "ARM_VERSION=v8"; fi
    fi

elif [ "$CPU_ARCH" = "x86_64" ]; then
    # === Intel/AMD x86 Specifics ===
    FLAGS=$(grep "flags" /proc/cpuinfo | head -n1)
    
    if echo "$FLAGS" | grep -iq "avx2"; then log "SUPPORTS_AVX2=ON"; else log "SUPPORTS_AVX2=OFF"; fi
    if echo "$FLAGS" | grep -iq "avx512f"; then log "SUPPORTS_AVX512=ON"; else log "SUPPORTS_AVX512=OFF"; fi
    
    # v1.7.0: Intel Deep Learning Boost (VNNI) & AMX
    if echo "$FLAGS" | grep -iq "avx512_vnni"; then log "SUPPORTS_AVX512_VNNI=ON"; else log "SUPPORTS_AVX512_VNNI=OFF"; fi
    if echo "$FLAGS" | grep -iq "amx_tile"; then log "SUPPORTS_AMX=ON"; else log "SUPPORTS_AMX=OFF"; fi
    
    if echo "$FLAGS" | grep -iq "f16c"; then log "SUPPORTS_FP16=ON"; else log "SUPPORTS_FP16=OFF"; fi
fi

# --- RAM DETEKTION ---
log "[MEMORY]"
if command -v free >/dev/null; then
    MEM_TOTAL_KB=$(free | grep Mem | awk '{print $2}')
    MEM_TOTAL_MB=$((MEM_TOTAL_KB / 1024))
    log "Total_RAM_MB=$MEM_TOTAL_MB"
else
    log "Total_RAM_MB=Unknown"
fi

# --- ACCELERATORS (GPU/NPU) ---
log "[ACCELERATORS]"

# 1. Rockchip NPU
if [ -d "/sys/kernel/debug/rknpu" ] || dmesg | grep -iq "rknpu"; then
    log "NPU_VENDOR=Rockchip"
    
    if dmesg | grep -iq "rk3588"; then
        log "NPU_MODEL=RK3588"
        log "SUPPORTS_RKLLM=ON"
    elif dmesg | grep -iqE "rk3566|rk3568"; then
        log "NPU_MODEL=RK3566_68"
        log "SUPPORTS_RKLLM=OFF"
    fi
    
    # v2.0.0: Driver Version Extraction
    if [ -f "/sys/kernel/debug/rknpu/version" ]; then
        RKNPU_VER=$(cat /sys/kernel/debug/rknpu/version)
        log "NPU_DRIVER_VERSION=$RKNPU_VER"
    else
        RKNPU_VER=$(dmesg | grep -i "rknpu" | grep -i "driver version" | head -n1 | awk -F': ' '{print $2}')
        log "NPU_DRIVER_VERSION=${RKNPU_VER:-Unknown}"
    fi
fi

# 2. NVIDIA GPU
if command -v nvidia-smi >/dev/null; then
    log "GPU_VENDOR=NVIDIA"
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)
    # v2.0.0: Explicit Driver Version
    GPU_DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1)
    CUDA_VER=$(nvidia-smi --query-gpu=cuda_version --format=csv,noheader | head -n1)
    
    log "GPU_MODEL=$GPU_NAME"
    log "GPU_DRIVER_VERSION=$GPU_DRIVER"
    log "HOST_CUDA_VERSION=$CUDA_VER"
    log "SUPPORTS_CUDA=ON"
else
    log "SUPPORTS_CUDA=OFF"
fi

# 3. Hailo NPU
if lspci -d 1e60: 2>/dev/null | grep -iq "Hailo"; then
    log "NPU_VENDOR=Hailo"
    log "SUPPORTS_HAILO=ON"
fi

# 4. Intel GPU (Arc / iGPU) (Added in v1.7.0)
if lspci -d 8086: 2>/dev/null | grep -iE "VGA|Display|3D"; then
    GPU_INFO=$(lspci -d 8086: | grep -iE "VGA|Display|3D" | head -n1)
    log "GPU_VENDOR=Intel"
    log "GPU_Raw_Info=$GPU_INFO"
    
    if echo "$GPU_INFO" | grep -iq "Arc"; then
        log "GPU_MODEL=Intel_Arc"
    elif echo "$GPU_INFO" | grep -iq "Iris"; then
        log "GPU_MODEL=Intel_Iris_Xe"
    else
        log "GPU_MODEL=Intel_iGPU"
    fi
    
    if [ -d "/dev/dri" ]; then
        log "SUPPORTS_INTEL_XPU=ON"
        # v2.0.0: Driver Version via module info
        if command -v modinfo >/dev/null; then
            INTEL_DRV_VER=$(modinfo i915 2>/dev/null | grep "^version:" | awk '{print $2}')
            if [ -z "$INTEL_DRV_VER" ]; then
                 INTEL_DRV_VER=$(modinfo xe 2>/dev/null | grep "^version:" | awk '{print $2}')
            fi
            log "GPU_DRIVER_VERSION=${INTEL_DRV_VER:-Unknown}"
        fi
    else
        log "SUPPORTS_INTEL_XPU=OFF (Driver missing?)"
    fi
fi

echo "Probing complete. Config written to $OUTPUT_FILE"
