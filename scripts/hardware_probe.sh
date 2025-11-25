#!/bin/bash
# hardware_probe.sh
# 
# VERSION: 2.1 (Unified: Rockchip RK35xx + RPi 5 16GB + Hailo-8)
# DIREKTIVE: Goldstandard, robust, modular.
#
# Dieses Skript analysiert das Host-System, um eine optimale Build-Strategie
# für LLMs zu entwickeln. Es unterstützt x86, Rockchip und Raspberry Pi 5.

# --- 1. Vorbereitung und Variablen ---
PROBE_OUTPUT_FILE="target_hardware_config.txt"
LOG_FILE="/tmp/hardware_probe_log.txt"

# Bereinigen alter Läufe
> "$PROBE_OUTPUT_FILE"
> "$LOG_FILE"

echo "Hardware-Probing gestartet..."
echo "Ergebnisse werden gespeichert in: $PROBE_OUTPUT_FILE"

# Hilfsfunktion zur Protokollierung von Fehlern
log_error() {
    echo "[FEHLER] $1" >> "$LOG_FILE"
}

# Funktion zum Ausführen eines Befehls und Speichern des Ergebnisses
run_probe() {
    local key="$1"
    local command="$2"
    
    # Pre-Check: Existiert das Tool überhaupt? (Vermeidet 'command not found' logs)
    local tool=$(echo "$command" | awk '{print $1}')
    if ! command -v "$tool" &> /dev/null; then
        # Ausnahme: Manche Infos kommen aus cat /proc/..., das ist kein "Tool" im klassischen Sinne
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
        # Optional: Nur loggen, aber nicht in die Output-Datei schreiben, um sie sauber zu halten
        # Oder explizit UNKNOWN setzen:
        echo "${key}=UNKNOWN" >> "$PROBE_OUTPUT_FILE"
        log_error "Probe failed for $key"
    fi
}

# --- 2. Basis-System & Board-Identifikation ---
echo "# Allgemeine Systeminformationen" >> "$PROBE_OUTPUT_FILE"
run_probe "OS_DISTRO" "cat /etc/os-release | grep ^NAME= | cut -d'=' -f2 | tr -d '\"'"
run_probe "OS_VERSION_ID" "cat /etc/os-release | grep ^VERSION_ID= | cut -d'=' -f2 | tr -d '\"'"
run_probe "KERNEL_VERSION" "uname -r"
run_probe "ARCHITECTURE_FULL" "uname -m"

# Spezifische Board-Erkennung (Wichtig für Pi 5 vs. Rockchip)
# Liest das Device Tree Model aus (Standard auf ARM SBCs)
run_probe "BOARD_MODEL" "cat /sys/firmware/devicetree/base/model 2>/dev/null | tr -d '\0'"

# --- 3. RAM Analyse & Tiering (Kritisch für Modell-Auswahl) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# Memory Status & Tier Class" >> "$PROBE_OUTPUT_FILE"

# Rohe RAM-Werte in MB ermitteln
if command -v free &> /dev/null; then
    TOTAL_RAM_MB=$(free -m | grep Mem: | awk '{print $2}')
    AVAILABLE_RAM_MB=$(free -m | grep Mem: | awk '{print $7}')
else
    TOTAL_RAM_MB="0"
    AVAILABLE_RAM_MB="0"
fi

run_probe "SYSTEM_RAM_MB" "echo $TOTAL_RAM_MB"
run_probe "SYSTEM_RAM_AVAILABLE_MB" "echo $AVAILABLE_RAM_MB"

# Automatische Klassifizierung für den Builder
if [ "$TOTAL_RAM_MB" -gt 15000 ]; then
    # 16 GB+ Klasse (Dein Pi 5 Modell 2025)
    echo "MEMORY_TIER=ULTRA" >> "$PROBE_OUTPUT_FILE"
    echo "MAX_MODEL_SIZE_SUGGESTION=14B_Q4_OR_8B_Q8" >> "$PROBE_OUTPUT_FILE"
elif [ "$TOTAL_RAM_MB" -gt 7000 ]; then
    # 8 GB Standard
    echo "MEMORY_TIER=HIGH" >> "$PROBE_OUTPUT_FILE"
    echo "MAX_MODEL_SIZE_SUGGESTION=8B_Q4_KM" >> "$PROBE_OUTPUT_FILE"
elif [ "$TOTAL_RAM_MB" -gt 3500 ]; then
    # 4 GB Klasse
    echo "MEMORY_TIER=MID" >> "$PROBE_OUTPUT_FILE"
    echo "MAX_MODEL_SIZE_SUGGESTION=3B_Q4_KM" >> "$PROBE_OUTPUT_FILE"
else
    # < 4 GB
    echo "MEMORY_TIER=LOW" >> "$PROBE_OUTPUT_FILE"
    echo "MAX_MODEL_SIZE_SUGGESTION=TINY_MODELS_ONLY" >> "$PROBE_OUTPUT_FILE"
fi

# --- 4. CPU-Details (Architektur & Kerne) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# CPU Architecture & Details" >> "$PROBE_OUTPUT_FILE"

run_probe "CPU_CORES" "nproc"
# Versuch, den genauen Core-Typ zu finden (Cortex-A76 vs A55)
run_probe "CPU_MODEL_NAME" "lscpu 2>/dev/null | grep 'Model name' | awk -F: '{print \$2}' | xargs"
run_probe "CPU_IMPLEMENTER" "grep 'CPU implementer' /proc/cpuinfo | head -n 1 | awk -F: '{print \$2}' | xargs"
run_probe "CPU_PART" "grep 'CPU part' /proc/cpuinfo | head -n 1 | awk -F: '{print \$2}' | xargs"

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

# Check für DotProduct (manchmal 'asimddp', 'dotprod' oder gar nicht explizit gelistet, aber via CPU Part impliziert)
if echo "$CPU_INFO" | grep -E -q "asimddp|dotprod"; then 
    run_probe "HAS_DOTPROD" "ON" 
else 
    run_probe "HAS_DOTPROD" "OFF" 
fi

# -- x86 Spezifische Checks (Fallback für Desktop/Server) --
if echo "$CPU_INFO" | grep -q "avx512"; then run_probe "HAS_AVX512" "ON"; fi
if echo "$CPU_INFO" | grep -q "avx2"; then run_probe "HAS_AVX2" "ON"; fi

# --- 6. NPU & AI Beschleuniger (Hailo / Rockchip) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# AI Accelerator Detection" >> "$PROBE_OUTPUT_FILE"

# A. PCI Scan (Findet Hailo am PCIe Bus - Wichtig für Pi 5 HAT)
if command -v lspci &> /dev/null; then
    # Hailo Technologies Vendor ID ist 1e60
    HAILO_PCI=$(lspci -d 1e60: 2>/dev/null)
    if [ -n "$HAILO_PCI" ]; then
        echo "NPU_TYPE=HAILO_8" >> "$PROBE_OUTPUT_FILE"
        echo "NPU_CONNECTION=PCIE" >> "$PROBE_OUTPUT_FILE"
        echo "NPU_DETECTED=TRUE" >> "$PROBE_OUTPUT_FILE"
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
    HAILO_STATUS=$(hailort-cli fw-control identify 2>&1 | grep 'Device Identity' | head -n 1)
    if [ -n "$HAILO_STATUS" ]; then
        run_probe "HAILO_DEVICE_STATUS" "echo OK"
    else
        run_probe "HAILO_DEVICE_STATUS" "echo ERROR_OR_SLEEP"
    fi
else
    run_probe "HAILO_SOFTWARE" "NOT_INSTALLED"
fi

# C. Rockchip NPU (Fallback für RK3566/RK3588)
if [ -e "/dev/rknpu" ] || [ -e "/proc/device-tree/rknpu" ]; then
    echo "NPU_TYPE=ROCKCHIP_NPU" >> "$PROBE_OUTPUT_FILE"
    echo "NPU_DETECTED=TRUE" >> "$PROBE_OUTPUT_FILE"
fi

# --- 7. GPU (Standard) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# GPU Status" >> "$PROBE_OUTPUT_FILE"

if command -v nvidia-smi &> /dev/null; then
    run_probe "GPU_TYPE" "NVIDIA"
    run_probe "GPU_MODEL" "nvidia-smi --query-gpu=gpu_name --format=csv,noheader | head -n 1 | sed 's/ /_/g'"
elif [ -e "/dev/mali0" ]; then
    run_probe "GPU_TYPE" "ARM_MALI"
else
    run_probe "GPU_TYPE" "GENERIC_OR_NONE"
fi

# --- Abschluss ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# Probing abgeschlossen am $(date +%Y-%m-%d_%H:%M:%S)" >> "$PROBE_OUTPUT_FILE"

echo "------------------------------------------------"
echo "Probing erfolgreich beendet."
echo "Datei erstellt: $PROBE_OUTPUT_FILE"
echo "------------------------------------------------"
echo "Erkanntes Board: $(grep BOARD_MODEL $PROBE_OUTPUT_FILE | cut -d'=' -f2)"
echo "Erkannte NPU:    $(grep NPU_TYPE $PROBE_OUTPUT_FILE | cut -d'=' -f2)"
echo "Memory Tier:     $(grep MEMORY_TIER $PROBE_OUTPUT_FILE | cut -d'=' -f2)"
echo "------------------------------------------------"
