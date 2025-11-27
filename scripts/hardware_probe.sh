#!/bin/bash
# hardware_probe.sh - LLM Framework Hardware Analyzer
# DIREKTIVE: Goldstandard. Generiert target_hardware_config.txt
# FIX: Variable Naming Consistency (HAS_ -> SUPPORTS_)

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
    # ARM Specifics
    if [ -f /proc/cpuinfo ]; then
        IMPL=$(grep "CPU implementer" /proc/cpuinfo | head -n1 | awk '{print $3}')
        PART=$(grep "CPU part" /proc/cpuinfo | head -n1 | awk '{print $3}')
        log "CPU_Implementer=$IMPL"
        log "CPU_Part=$PART"
        
        # Features detection (Case Insensitive grep)
        FEATURES=$(grep "Features" /proc/cpuinfo | head -n1)
        
        # FIX: Naming match with config_module.sh (SUPPORTS_*)
        if echo "$FEATURES" | grep -iq "neon" || echo "$FEATURES" | grep -iq "asimd"; then
            log "SUPPORTS_NEON=ON" 
        else
            log "SUPPORTS_NEON=OFF"
        fi
        
        if echo "$FEATURES" | grep -iq "fp16" || echo "$FEATURES" | grep -iq "fphp"; then
            log "SUPPORTS_FP16=ON"
        else
            log "SUPPORTS_FP16=OFF"
        fi
        
        if echo "$FEATURES" | grep -iq "v8"; then
            log "ARM_VERSION=v8"
        fi
    fi
elif [ "$CPU_ARCH" = "x86_64" ]; then
    # x86 Specifics
    FLAGS=$(grep "flags" /proc/cpuinfo | head -n1)
    
    # FIX: Naming match with config_module.sh
    if echo "$FLAGS" | grep -iq "avx2"; then
        log "SUPPORTS_AVX2=ON"
    else
        log "SUPPORTS_AVX2=OFF"
    fi
    
    if echo "$FLAGS" | grep -iq "avx512"; then
        log "SUPPORTS_AVX512=ON"
    else
        log "SUPPORTS_AVX512=OFF"
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

# --- GPU/NPU DETEKTION ---
log "[ACCELERATORS]"

# Rockchip NPU
if [ -d "/sys/kernel/debug/rknpu" ] || dmesg | grep -iq "rknpu"; then
    log "NPU_VENDOR=Rockchip"
    # Try to detect version
    if dmesg | grep -iq "rk3588"; then
        log "NPU_MODEL=RK3588"
        log "SUPPORTS_RKLLM=ON"
    elif dmesg | grep -iq "rk3566" || dmesg | grep -iq "rk3568"; then
        log "NPU_MODEL=RK3566_68"
        log "SUPPORTS_RKLLM=OFF"
    fi
fi

# NVIDIA GPU
if command -v nvidia-smi >/dev/null; then
    log "GPU_VENDOR=NVIDIA"
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)
    log "GPU_MODEL=$GPU_NAME"
    log "SUPPORTS_CUDA=ON"
else
    log "SUPPORTS_CUDA=OFF"
fi

# Hailo
if lspci | grep -iq "Hailo"; then
    log "NPU_VENDOR=Hailo"
    log "SUPPORTS_HAILO=ON"
fi

echo "Probing complete. See $OUTPUT_FILE"
