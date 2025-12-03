#!/bin/bash
# hardware_probe.sh - LLM Framework Hardware Analyzer
# DIREKTIVE: Goldstandard. Generiert target_hardware_config.txt
#
# Updates v1.7.0:
# - Added detailed Intel CPU detection (AVX512_VNNI, AMX) for IPEX-LLM.
# - Added Intel GPU (XPU/Arc) detection via PCI/Kernel.
# - Improved logging consistency.

set -u

OUTPUT_FILE="target_hardware_config.txt"

# Header schreiben
{
    echo "# LLM Framework Hardware Profile"
    echo "# Generated: $(date)"
    echo "# Hostname: $(hostname)"
} > "$OUTPUT_FILE"

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
        
        # Features detection (Case Insensitive grep)
        FEATURES=$(grep "Features" /proc/cpuinfo | head -n1)
        
        if echo "$FEATURES" | grep -iqE "neon|asimd"; then
            log "SUPPORTS_NEON=ON" 
        else
            log "SUPPORTS_NEON=OFF"
        fi
        
        if echo "$FEATURES" | grep -iqE "fp16|fphp"; then
            log "SUPPORTS_FP16=ON"
        else
            log "SUPPORTS_FP16=OFF"
        fi
        
        if echo "$FEATURES" | grep -iq "v8"; then
            log "ARM_VERSION=v8"
        fi
    fi

elif [ "$CPU_ARCH" = "x86_64" ]; then
    # === Intel/AMD x86 Specifics ===
    # Wir lesen /proc/cpuinfo, da lscpu nicht immer verfügbar ist (Docker)
    FLAGS=$(grep "flags" /proc/cpuinfo | head -n1)
    
    # Standard AVX
    if echo "$FLAGS" | grep -iq "avx2"; then
        log "SUPPORTS_AVX2=ON"
    else
        log "SUPPORTS_AVX2=OFF"
    fi
    
    # AVX-512 Foundation
    if echo "$FLAGS" | grep -iq "avx512f"; then
        log "SUPPORTS_AVX512=ON"
    else
        log "SUPPORTS_AVX512=OFF"
    fi
    
    # Intel Deep Learning Boost (VNNI) - Kritisch für IPEX-LLM INT8 Performance
    if echo "$FLAGS" | grep -iq "avx512_vnni"; then
        log "SUPPORTS_AVX512_VNNI=ON"
    else
        log "SUPPORTS_AVX512_VNNI=OFF"
    fi
    
    # Intel AMX (Advanced Matrix Extensions) - Kritisch für Sapphire Rapids+
    if echo "$FLAGS" | grep -iq "amx_tile"; then
        log "SUPPORTS_AMX=ON"
    else
        log "SUPPORTS_AMX=OFF"
    fi
    
    if echo "$FLAGS" | grep -iq "f16c"; then
        log "SUPPORTS_FP16=ON"
    else
        log "SUPPORTS_FP16=OFF"
    fi
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
fi

# 2. NVIDIA GPU
if command -v nvidia-smi >/dev/null; then
    log "GPU_VENDOR=NVIDIA"
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)
    log "GPU_MODEL=$GPU_NAME"
    log "SUPPORTS_CUDA=ON"
else
    log "SUPPORTS_CUDA=OFF"
fi

# 3. Hailo NPU
if lspci -d 1e60: 2>/dev/null | grep -iq "Hailo"; then
    log "NPU_VENDOR=Hailo"
    log "SUPPORTS_HAILO=ON"
fi

# 4. Intel GPU (Arc / iGPU / Data Center)
# Vendor ID 8086 (Intel), Class 03 (Display)
if lspci -d 8086: 2>/dev/null | grep -iE "VGA|Display|3D"; then
    GPU_INFO=$(lspci -d 8086: | grep -iE "VGA|Display|3D" | head -n1)
    log "GPU_VENDOR=Intel"
    log "GPU_Raw_Info=$GPU_INFO"
    
    # Unterscheidung Arc vs. Integrated
    if echo "$GPU_INFO" | grep -iq "Arc"; then
        log "GPU_MODEL=Intel_Arc"
    elif echo "$GPU_INFO" | grep -iq "Iris"; then
        log "GPU_MODEL=Intel_Iris_Xe"
    else
        log "GPU_MODEL=Intel_iGPU"
    fi
    
    # Prüfen auf Compute Runtime (Level Zero / OpenCL)
    if [ -d "/dev/dri" ]; then
        log "SUPPORTS_INTEL_XPU=ON"
    else
        log "SUPPORTS_INTEL_XPU=OFF (Driver missing?)"
    fi
fi

echo "Probing complete. Config written to $OUTPUT_FILE"
