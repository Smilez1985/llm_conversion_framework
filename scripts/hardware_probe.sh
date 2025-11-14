Hardware Probing Skript (Universell)

------------------------

#!/bin/bash
# hardware_probe.sh
# 
# DIREKTIVE: Goldstandard, robust, professionell geschrieben.
# Dieses Skript wird auf JEDEM Linux-Zielsystem ausgeführt, um alle
# relevanten Hardware- und OS-Metadaten für die Cross-Compilation oder 
# die native Kompilierung zu sammeln (vergleichbar mit CPU-Z/GPU-Z).

# --- 1. Vorbereitung und Variablen ---
PROBE_OUTPUT_FILE="target_hardware_config.txt"
LOG_FILE="/tmp/hardware_probe_log.txt"
# Bereinigen alter Läufe
> "$PROBE_OUTPUT_FILE"
> "$LOG_FILE"

echo "Hardware-Probing gestartet. Ergebnisse werden in '$PROBE_OUTPUT_FILE' gespeichert."

# Funktion zur Protokollierung von Fehlern
log_error() {
    echo "[FEHLER] $1" | tee -a "$LOG_FILE"
}

# Funktion zum Ausführen eines Befehls und Speichern des Ergebnisses
run_probe() {
    local key="$1"
    local command="$2"
    
    # Sicherstellen, dass der Befehl existiert, bevor er ausgeführt wird
    if ! command -v $(echo "$command" | awk '{print $1}') &> /dev/null && [[ "$key" != "CPU_MODEL_NAME" ]]; then
        echo "${key}=TOOL_NOT_FOUND" >> "$PROBE_OUTPUT_FILE"
        return
    fi

    # Führt den Befehl aus und speichert das Ergebnis im Key=Value-Format
    local result=$($command 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$result" ]; then
        # Ergebnis bereinigen (Leerzeichen am Anfang/Ende entfernen) und speichern
        echo "${key}=$(echo $result | xargs)" >> "$PROBE_OUTPUT_FILE"
    else
        log_error "Befehl für Schlüssel '$key' fehlgeschlagen oder leer. Befehl: '$command'"
        echo "${key}=UNKNOWN" >> "$PROBE_OUTPUT_FILE"
    fi
}

# --- 2. System- und OS-Informationen ---
echo "# Allgemeine Systeminformationen" >> "$PROBE_OUTPUT_FILE"
run_probe "OS_DISTRO" "cat /etc/os-release 2>/dev/null | grep ^NAME= | cut -d'=' -f2 | tr -d '\"'"
run_probe "OS_VERSION_ID" "cat /etc/os-release 2>/dev/null | grep ^VERSION_ID= | cut -d'=' -f2 | tr -d '\"'"
run_probe "KERNEL_VERSION" "uname -r"
run_probe "ARCHITECTURE_FULL" "uname -m"

# --- 3. CPU-Details und Optimierungs-Features ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# CPU- und Compiler-Optimierungs-Details" >> "$PROBE_OUTPUT_FILE"

# CPU-Modellname (häufig in /proc/cpuinfo oder lscpu)
run_probe "CPU_MODEL_NAME" "lscpu 2>/dev/null | grep 'Model name' | awk -F: '{print \$2}' | xargs"
if [ ! -s "$PROBE_OUTPUT_FILE" ] || ! grep -q "CPU_MODEL_NAME" "$PROBE_OUTPUT_FILE"; then
    run_probe "CPU_MODEL_NAME" "cat /proc/cpuinfo 2>/dev/null | grep 'model name' | head -n 1 | awk -F: '{print \$2}' | xargs"
fi

run_probe "CPU_CORES" "nproc"
run_probe "CPU_L2_CACHE_KB" "lscpu 2>/dev/null | grep 'L2 cache' | awk '{print \$3}' | tr -d 'K'"
run_probe "CPU_VENDOR_ID" "lscpu 2>/dev/null | grep 'Vendor ID' | awk '{print \$3}'"

# --- 4. Wichtige SIMD/Compiler-Features (Basis für llama.cpp Flags) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# SIMD / Vektorisierungs-Features (Wichtig für llama.cpp / GGML)" >> "$PROBE_OUTPUT_FILE"
CPU_FLAGS=$(cat /proc/cpuinfo 2>/dev/null | grep flags | head -n 1)
CPU_FEATURES=$(cat /proc/cpuinfo 2>/dev/null | grep Features | head -n 1)

# ARM-Features (aarch64)
if echo "$CPU_FEATURES" | grep -q neon; then
    run_probe "SUPPORTS_NEON" "ON"
else
    run_probe "SUPPORTS_NEON" "OFF"
fi

# X86-Features (x86_64)
# Die Flags werden gesammelt, um die besten Kompilierungs-Optionen zu wählen (z.B. AVX2, AVX512)
if echo "$CPU_FLAGS" | grep -q avx512f; then
    run_probe "SUPPORTS_AVX512" "ON"
elif echo "$CPU_FLAGS" | grep -q avx2; then
    run_probe "SUPPORTS_AVX2" "ON"
elif echo "$CPU_FLAGS" | grep -q avx; then
    run_probe "SUPPORTS_AVX" "ON"
else
    run_probe "SUPPORTS_X86_SIMD" "NONE"
fi

# --- 5. GPU- und Beschleuniger-Erkennung (TensorRT/Vulkan/etc.) ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# Beschleuniger-Erkennung (NVIDIA/AMD/Vulkan/OpenCL)" >> "$PROBE_OUTPUT_FILE"

# Prüfe auf NVIDIA CUDA (RTX/Tensor-Fähigkeit)
if command -v nvidia-smi &> /dev/null; then
    run_probe "GPU_DRIVER_VERSION" "nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1"
    run_probe "GPU_MODEL" "nvidia-smi --query-gpu=gpu_name --format=csv,noheader | head -n 1 | sed 's/ /_/g'"
    # Prüfung auf CUDA Toolkit (wichtig für TensorRT/Entwickler-Builds)
    if command -v nvcc &> /dev/null; then
        run_probe "CUDA_TOOLKIT_VERSION" "nvcc --version | grep 'release' | awk '{print \$6}' | cut -d',' -f1"
    else
        run_probe "CUDA_TOOLKIT_VERSION" "NOT_INSTALLED"
    fi
else
    run_probe "GPU_NVIDIA" "NOT_FOUND"
fi

# Prüfe auf Vulkan-Support (DX12-Äquivalent für Linux)
if command -v vulkaninfo &> /dev/null; then
    # Versuche, die höchste unterstützte Vulkan-Version zu erfassen
    run_probe "VULKAN_SUPPORT" "vulkaninfo --summary | grep 'Vulkan Instance Version' | awk '{print \$4}'"
else
    run_probe "VULKAN_SUPPORT" "TOOL_NOT_INSTALLED"
fi

# Prüfe auf OpenCL (generische Beschleuniger, z.B. Mali, Rockchip NPU/GPU)
if command -v clinfo &> /dev/null; then
    run_probe "OPENCL_PLATFORM" "clinfo | grep 'Platform Name' | head -n 1 | awk -F: '{print \$2}' | xargs"
else
    run_probe "OPENCL_PLATFORM" "TOOL_NOT_INSTALLED"
fi

# --- 6. Abschluss ---
echo "" >> "$PROBE_OUTPUT_FILE"
echo "# Probing abgeschlossen am $(date +%Y-%m-%d_%H:%M:%S)" >> "$PROBE_OUTPUT_FILE"

echo "Probing erfolgreich. Konfigurationsdatei wurde erstellt: $PROBE_OUTPUT_FILE"
echo "Bitte laden Sie diese Datei in den Orchestrator hoch."

