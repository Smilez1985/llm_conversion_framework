#!/bin/bash
# hardware_probe.sh
# 
# VERSION: 2.0 (Pi 5 + Hailo-8 Enhanced)
# DIREKTIVE: Goldstandard, robust, modular.
#
# Dieses Skript analysiert das Host-System, um eine optimale Build-Strategie
# für LLMs zu entwickeln. Es unterstützt x86, Rockchip und Raspberry Pi 5.

# --- 1. Vorbereitung und Variablen ---
PROBE_OUTPUT_FILE="target_hardware_config.txt"
LOG_FILE="/tmp/hardware_probe_log.txt"

# Bereinigen
> "$PROBE_OUTPUT_FILE"
> "$LOG_FILE"

echo "Hardware-Probing gestartet..."
echo "Ziel-Datei: $PROBE_OUTPUT_FILE"

# Hilfsfunktion: Führt Befehl aus, schreibt in Datei, fängt Fehler ab.
run_probe() {
    local key="$1"
    local command="$2"
    
    # Pre-Check: Existiert das Tool überhaupt? (Vermeidet hässliche 'command not found' logs)
    local tool=$(echo "$command" | awk '{print $1}')
    if ! command -v "$tool" &> /dev/null; then
        # Ausnahme: Manche Infos kommen aus cat /proc/..., das ist kein "Tool"
        if [[ "$tool" != "cat" && "$tool" != "grep" ]]; then
            echo "${key}=TOOL_NOT_FOUND" >> "$PROBE_OUTPUT_FILE"
            return
        fi
    fi

    # Ausführung
    local result=$(eval "$command" 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$result" ]; then
        # Trim Whitespace
        result=$(echo "$result" | xargs)
        echo "${key}=${result}" >> "$PROBE_OUTPUT_FILE"
    else
        echo "${key}=UNKNOWN" >> "$PROBE_OUTPUT_FILE"
        echo "[WARN] Probe failed for $key" >> "$LOG_FILE"
    fi
}

# --- 2. Basis-System & Board-Identifikation ---
echo "# System Basics" >> "$PROBE_OUTPUT_FILE"
run_probe "OS_DISTRO" "cat /etc/os-release | grep ^NAME= | cut -d'=' -f2 | tr -d '\"'"
run_probe "KERNEL_VERSION" "uname -r"
run_probe "ARCHITECTURE_FULL" "uname -m"

# Spezifische Board-Erkennung (Wichtig für Pi 5 vs. Rockchip)
# Versuche Device-Tree Model auszulesen (Standard auf ARM SBCs)
run_probe "BOARD_MODEL" "cat /sys/firmware/devicetree/base/model 2>/dev/null | tr -d '\0'"

# --- 3. RAM Analyse (Kritisch für Modell-Auswahl) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# Memory Status (Crucial for Quantization Level)" >> "$PROBE_OUTPUT_FILE"
# RAM in MB
run_probe "SYSTEM_RAM_MB" "free -m | grep Mem: | awk '{print \$2}'"
# Verfügbarer RAM (wichtig falls System schon voll ist)
run_probe "SYSTEM_RAM_AVAILABLE_MB" "free -m | grep Mem: | awk '{print \$7}'"

# --- 4. CPU-Details (Architektur & Kerne) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# CPU Architecture" >> "$PROBE_OUTPUT_FILE"

run_probe "CPU_CORES" "nproc"
# Versuch, den genauen Core-Typ zu finden (Cortex-A76 vs A55)
# Auf Pi 5 und Rockchip oft im dmesg oder kompatiblen Strings versteckt
run_probe "CPU_IMPLEMENTER" "grep 'CPU implementer' /proc/cpuinfo | head -n 1 | awk -F: '{print \$2}'"
run_probe "CPU_PART" "grep 'CPU part' /proc/cpuinfo | head -n 1 | awk -F: '{print \$2}'"

# --- 5. Advanced SIMD / Compiler Flags (Performance!) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# SIMD Capabilities (LLM Inference Speedup)" >> "$PROBE_OUTPUT_FILE"

CPU_INFO=$(cat /proc/cpuinfo 2>/dev/null)

# -- ARM (Aarch64) Spezifische Checks --
if echo "$CPU_INFO" | grep -q "asimd"; then run_probe "HAS_ASIMD" "ON"; else run_probe "HAS_ASIMD" "OFF"; fi
if echo "$CPU_INFO" | grep -q "neon"; then run_probe "HAS_NEON" "ON"; else run_probe "HAS_NEON" "OFF"; fi
if echo "$CPU_INFO" | grep -q "fp16"; then run_probe "HAS_FP16" "ON"; else run_probe "HAS_FP16" "OFF"; fi
# WICHTIG für Pi 5 (Dot Product Instructions beschleunigen Q4/Q8 Inferenz massiv)
if echo "$CPU_INFO" | grep -q "atomics"; then run_probe "HAS_ATOMICS" "ON"; else run_probe "HAS_ATOMICS" "OFF"; fi
if echo "$CPU_INFO" | grep -q "crc32"; then run_probe "HAS_CRC32" "ON"; else run_probe "HAS_CRC32" "OFF"; fi
# Check für DotProduct (manchmal 'asimddp' oder 'dotprod')
if echo "$CPU_INFO" | grep -E -q "asimddp|dotprod"; then 
    run_probe "HAS_DOTPROD" "ON" 
else 
    run_probe "HAS_DOTPROD" "OFF" 
fi

# -- x86 Spezifische Checks (Fallback) --
if echo "$CPU_INFO" | grep -q "avx512"; then run_probe "HAS_AVX512" "ON"; fi
if echo "$CPU_INFO" | grep -q "avx2"; then run_probe "HAS_AVX2" "ON"; fi

# --- 6. NPU & AI Beschleuniger (Hailo / Rockchip) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# AI Accelerator Detection" >> "$PROBE_OUTPUT_FILE"

# A. PCI Scan (Findet Hailo am PCIe Bus)
if command -v lspci &> /dev/null; then
    # Hailo Technologies Vendor ID ist 1e60
    HAILO_PCI=$(lspci -d 1e60: 2>/dev/null)
    if [ -n "$HAILO_PCI" ]; then
        echo "NPU_TYPE=HAILO_8" >> "$PROBE_OUTPUT_FILE"
        echo "NPU_CONNECTION=PCIE" >> "$PROBE_OUTPUT_FILE"
    else
        echo "NPU_PCIE_CARD=NONE" >> "$PROBE_OUTPUT_FILE"
    fi
else
    echo "LSPCI_TOOL=MISSING" >> "$PROBE_OUTPUT_FILE"
fi

# B. Hailo Software Stack Check
if command -v hailort-cli &> /dev/null; then
    run_probe "HAILO_RT_VERSION" "hailort-cli --version"
    # Prüfen ob Chip aktiv antwortet
    run_probe "HAILO_DEVICE_STATUS" "hailort-cli fw-control identify 2>&1 | grep 'Device Identity' | head -n 1"
else
    run_probe "HAILO_SOFTWARE" "NOT_INSTALLED"
fi

# C. Rockchip NPU (Fallback/Alternative)
if [ -e "/dev/rknpu" ] || [ -e "/proc/device-tree/rknpu" ]; then
    echo "NPU_TYPE=ROCKCHIP_NPU" >> "$PROBE_OUTPUT_FILE"
fi

# --- 7. GPU (Standard) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# GPU Status" >> "$PROBE_OUTPUT_FILE"
if command -v nvidia-smi &> /dev/null; then
    run_probe "GPU_TYPE" "NVIDIA"
elif [ -e "/dev/mali0" ]; then
    run_probe "GPU_TYPE" "ARM_MALI"
else
    run_probe "GPU_TYPE" "GENERIC_OR_NONE"
fi

echo "------------------------------------------------"
echo "Probing Complete."
echo "Detected Board Model: $(grep BOARD_MODEL $PROBE_OUTPUT_FILE | cut -d'=' -f2)"
echo "Detected NPU:         $(grep NPU_TYPE $PROBE_OUTPUT_FILE | cut -d'=' -f2)"
echo "------------------------------------------------"
