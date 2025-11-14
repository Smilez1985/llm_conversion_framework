#!/bin/bash
# target_module.sh - Quantization & Final Packaging Module
# Part of LLM Cross-Compiler Framework
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Cross-kompiliert llama.cpp Binaries (llama-cli, llama-quantize), 
#        quantisiert GGUF FP16, und erstellt ein Deployment-Paket.

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

readonly SCRIPT_NAME="target_module.sh"
readonly SCRIPT_VERSION="1.0.0"

# Environment variables with defaults
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/llama.cpp}"
readonly OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
readonly TEMP_DIR="${OUTPUT_DIR}/temp"
readonly FINAL_PACKAGE_DIR="${OUTPUT_DIR}/packages"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"
DEBUG="${DEBUG:-0}"

# Load build configuration (setzt CMAKE_TOOLCHAIN_FILE, CFLAGS, CXXFLAGS, BUILD_JOBS etc.)
if [[ ! -f "${BUILD_CACHE_DIR}/build_config.sh" ]]; then
    echo "❌ [TARGET] Kritischer Fehler: build_config.sh nicht gefunden. Führen Sie config_module.sh zuerst aus." >&2
    exit 1
fi
source "${BUILD_CACHE_DIR}/build_config.sh"

# Target configuration
declare -A TARGET_CONFIG
declare -A QUANTIZATION_STATS
declare -A BUILD_STATS

# Tools (Pfade zu den ZIEL-Binaries)
LLAMA_CPP_QUANTIZE="$LLAMA_CPP_PATH/build_target/bin/llama-quantize"
LLAMA_CPP_CLI="$LLAMA_CPP_PATH/build_target/bin/llama-cli"
LLAMA_CPP_SERVER="$LLAMA_CPP_PATH/build_target/bin/llama-server"

# ============================================================================
# LOGGING & ERROR HANDLING
# ============================================================================

log_info() { echo "ℹ️  [$(date '+%H:%M:%S')] [TARGET] $1"; }
log_success() { echo "✅ [$(date '+%H:%M:%S')] [TARGET] $1"; }
log_warn() { echo "⚠️  [$(date '+%H:%M:%S')] [TARGET] $1"; }
log_error() { echo "❌ [$(date '+%H:%M:%S')] [TARGET] $1" >&2; }
log_debug() { [ "$DEBUG" = "1" ] && echo "🔍 [$(date '+%H:%M:%S')] [TARGET] $1"; }

die() {
    log_error "$1"
    exit "${2:-1}"
}

cleanup_on_error() {
    local exit_code=$?
    log_error "Target module failed with exit code: $exit_code"
    
    if [[ -n "${BUILD_DIR:-}" && -d "${BUILD_DIR:-}" ]]; then
        log_info "Cleaning up build directory: $BUILD_DIR"
        rm -rf "$BUILD_DIR" 2>/dev/null || true
    fi
    
    log_error "Cleanup completed"
    exit $exit_code
}

trap cleanup_on_error ERR

# ============================================================================
# INPUT VALIDATION
# ============================================================================

validate_inputs() {
    local input_gguf="$1"
    local quant_method="$2"
    local model_name="$3"
    
    log_info "Validating target module inputs"
    
    if [[ ! -f "$input_gguf" ]]; then die "Input GGUF file not found: $input_gguf"; fi
    
    local file_size; file_size=$(stat -c%s "$input_gguf" 2>/dev/null || echo "0")
    if [[ "$file_size" -lt 1048576 ]]; then die "Input GGUF file suspiciously small"; fi
    
    if [[ -z "$quant_method" ]]; then die "Quantization method required"; fi
    if [[ -z "$model_name" ]]; then die "Model name required"; fi
    
    TARGET_CONFIG[INPUT_GGUF]="$input_gguf"
    TARGET_CONFIG[QUANT_METHOD]="$quant_method"
    TARGET_CONFIG[MODEL_NAME]="$model_name"
    TARGET_CONFIG[INPUT_SIZE_BYTES]="$file_size"
    TARGET_CONFIG[INPUT_SIZE_MB]="$((file_size / 1024 / 1024))"
    
    log_success "Input validation completed"
}

# ============================================================================
# CROSS-COMPILATION (Schritt 1)
# ============================================================================

cross_compile_llama_cpp() {
    log_info "Schritt 1/4: Cross-Kompilierung von llama.cpp Binaries für ${TARGET_ARCH}"
    
    local build_dir="$LLAMA_CPP_PATH/build_target" # Separater Build-Ordner
    BUILD_DIR="$build_dir"  # Für Cleanup
    
    rm -rf "$build_dir"
    mkdir -p "$build_dir"
    cd "$build_dir"
    
    local cmake_args=()
    cmake_args+=("-DCMAKE_BUILD_TYPE=Release")
    cmake_args+=("-DBUILD_SHARED_LIBS=OFF")
    cmake_args+=("-DLLAMA_CURL=OFF")
    cmake_args+=("-DGGML_CUDA=OFF")
    cmake_args+=("-DGGML_SYCL=OFF")
    cmake_args+=("-DLLAMA_BLAS=OFF")

    # WICHTIG: Setze die Toolchain und Optimierungs-Flags
    cmake_args+=("-DCMAKE_TOOLCHAIN_FILE=${CMAKE_TOOLCHAIN_FILE}")
    
    # Lade CFLAGS/CXXFLAGS aus der build_config.sh
    cmake_args+=("-DCMAKE_C_FLAGS='$CFLAGS'")
    cmake_args+=("-DCMAKE_CXX_FLAGS='$CXXFLAGS'")
    
    # 5. ERSETZEN: Fügen Sie hier Ihre SDK-spezifischen CMake-Flags hinzu
    # z.B.: cmake_args+=("-DGGML_CUDA=ON")
    # z.B.: cmake_args+=("-DGGML_OPENCL=ON")
    
    log_info "Configuring llama.cpp build..."
    if ! cmake "$LLAMA_CPP_PATH" "${cmake_args[@]}"; then
        die "CMake configuration failed"
    fi
    
    local build_jobs="${BUILD_JOBS:-4}"
    log_info "Building llama.cpp binaries (${build_jobs} jobs)..."
    
    local start_time=$SECONDS
    # Kompiliere alle notwendigen Binaries
    if ! make -j"$build_jobs" llama-quantize llama-cli llama-server; then 
        die "llama.cpp Binär-Kompilierung fehlgeschlagen."
    fi
    local build_time=$((SECONDS - start_time))
    
    # Validiere Binaries
    local binaries=("$LLAMA_CPP_QUANTIZE" "$LLAMA_CPP_CLI" "$LLAMA_CPP_SERVER")
    for binary in "${binaries[@]}"; do
        if [[ ! -f "$binary" ]]; then
            die "Erforderliches Binary nicht gebaut: $binary"
        fi
    done
    
    BUILD_STATS[BUILD_TIME]="$build_time"
    BUILD_STATS[BUILD_JOBS]="$build_jobs"
    
    log_success "Cross-Kompilierung abgeschlossen in ${build_time}s."
}

# ============================================================================
# QUANTIZATION (Schritt 2)
# ============================================================================

quantize_model() {
    local input_gguf="${TARGET_CONFIG[INPUT_GGUF]}"
    local quant_method="${TARGET_CONFIG[QUANT_METHOD]}"
    local model_name="${TARGET_CONFIG[MODEL_NAME]}"
    
    local quantized_output="$OUTPUT_DIR/${model_name}.${quant_method,,}.gguf"
    
    log_info "Schritt 2/4: Starte Model-Quantisierung: FP16 → $quant_method"
    
    # Verify quantize tool exists
    if [[ ! -f "$LLAMA_CPP_QUANTIZE" ]]; then
        die "llama-quantize tool nicht gefunden: $LLAMA_CPP_QUANTIZE"
    fi

    if [[ -f "$quantized_output" ]]; then
        mv "$quantized_output" "${quantized_output}.backup.$(date +%s)"
        log_info "Backup erstellt"
    fi
    
    local start_time=$SECONDS
    
    # Führe die kompilierte Binärdatei aus
    if ! "$LLAMA_CPP_QUANTIZE" "$input_gguf" "$quantized_output" "$quant_method"; then
        die "Model quantization failed"
    fi
    
    local quant_time=$((SECONDS - start_time))
    
    if [[ ! -f "$quantized_output" ]]; then die "Quantized model not created"; fi
    
    local output_size; output_size=$(stat -c%s "$quantized_output" 2>/dev/null || echo "0")
    
    QUANTIZATION_STATS[OUTPUT_FILE]="$quantized_output"
    QUANTIZATION_STATS[OUTPUT_SIZE_BYTES]="$output_size"
    QUANTIZATION_STATS[OUTPUT_SIZE_MB]="$((output_size / 1024 / 1024))"
    QUANTIZATION_STATS[QUANTIZATION_TIME]="$quant_time"
    QUANTIZATION_STATS[COMPRESSION_RATIO]=$(echo "scale=2; $output_size * 100 / ${TARGET_CONFIG[INPUT_SIZE_BYTES]}" | bc 2>/dev/null || echo "unknown")
    TARGET_CONFIG[QUANTIZED_GGUF]="$quantized_output"
    
    log_success "Quantization completed in ${quant_time}s: ${QUANTIZATION_STATS[OUTPUT_SIZE_MB]}MB"
}

# ============================================================================
# MODEL VALIDATION (Schritt 3)
# ============================================================================

validate_quantized_model() {
    local quantized_gguf="${TARGET_CONFIG[QUANTIZED_GGUF]}"
    local llama_cli="${TARGET_CONFIG[LLAMA_CLI_BINARY]}"
    
    log_info "Schritt 3/4: Validiere Model-Größe und Integrität"
    
    local min_size=$((50 * 1024 * 1024))  # 50MB
    local actual_size="${QUANTIZATION_STATS[OUTPUT_SIZE_BYTES]}"
    
    if [[ "$actual_size" -lt "$min_size" ]]; then
        die "Quantized model suspiciously small: $((actual_size / 1024 / 1024))MB"
    fi
    
    # Cross-Compile Check: Wir können die Binaries hier nicht ausführen.
    log_warn "Überspringe Funktionstest: Cross-kompilierte Binaries können auf dem Host nicht ausgeführt werden."
    
    log_success "Model validation (Größe) completed"
}

# ============================================================================
# PACKAGE CREATION (Schritt 4)
# ============================================================================

create_deployment_package() {
    local model_name="${TARGET_CONFIG[MODEL_NAME]}"
    local quant_method="${TARGET_CONFIG[QUANT_METHOD]}"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local package_name="${model_name}_${quant_method,,}_${TARGET_ARCH}_${timestamp}"
    local package_dir="$FINAL_PACKAGE_DIR/$package_name"
    
    log_info "Schritt 4/4: Erstelle Deployment-Paket: $package_name"
    
    rm -rf "$package_dir"
    mkdir -p "$package_dir"
    
    # Kopiere Model
    cp "${TARGET_CONFIG[QUANTIZED_GGUF]}" "$package_dir/${model_name}.${quant_method,,}.gguf"
    
    # Kopiere Binaries
    cp "${TARGET_CONFIG[LLAMA_CLI_BINARY]}" "$package_dir/llama-cli"
    cp "${TARGET_CONFIG[LLAMA_SERVER_BINARY]}" "$package_dir/llama-server"
    
    # Kopiere Configs
    cp "${CMAKE_TOOLCHAIN_FILE}" "$package_dir/cmake_toolchain.cmake"
    cp "${BUILD_CACHE_DIR}/target_hardware_config.txt" "$package_dir/"
    
    TARGET_CONFIG[PACKAGE_DIR]="$package_dir"
    TARGET_CONFIG[PACKAGE_NAME]="$package_name"
    
    # Erstelle Manifest, README und Helper-Scripts
    create_package_manifest "$package_dir"
    create_package_documentation "$package_dir"
    create_helper_scripts "$package_dir"
    
    # Erstelle 'latest' Symlink
    local latest_link="$FINAL_PACKAGE_DIR/${model_name}_${quant_method,,}_${TARGET_ARCH}_latest"
    rm -f "$latest_link"
    ln -s "$package_name" "$latest_link"
    
    log_success "Deployment package created: $package_dir"
}

create_package_manifest() {
    local package_dir="$1"
    log_debug "Creating package manifest"
    
    cat > "$package_dir/MANIFEST.json" << EOF
{
  "package_info": {
    "name": "${TARGET_CONFIG[PACKAGE_NAME]}",
    "model_name": "${TARGET_CONFIG[MODEL_NAME]}",
    "quantization": "${TARGET_CONFIG[QUANT_METHOD]}",
    "target_architecture": "${TARGET_ARCH:-unknown}",
    "created": "$(date -Iseconds)"
  },
  "model_info": {
    "original_size_mb": ${TARGET_CONFIG[INPUT_SIZE_MB]:-0},
    "quantized_size_mb": ${QUANTIZATION_STATS[OUTPUT_SIZE_MB]:-0},
    "compression_ratio": "${QUANTIZATION_STATS[COMPRESSION_RATIO]:-0}%"
  },
  "hardware_target": {
    "architecture": "${TARGET_CONFIG[HW_ARCHITECTURE_FULL]:-unknown}",
    "cpu_model": "${TARGET_CONFIG[HW_CPU_MODEL_NAME]:-unknown}",
    "cpu_cores": "${TARGET_CONFIG[HW_CPU_CORES]:-unknown}",
    "neon_support": "${TARGET_CONFIG[HW_SUPPORTS_NEON]:-unknown}"
  },
  "build_info": {
    "cross_compile": "${TARGET_CONFIG[CROSS_COMPILE]}",
    "build_time_seconds": ${BUILD_STATS[BUILD_TIME]:-0},
    "quantization_time_seconds": ${QUANTIZATION_STATS[QUANTIZATION_TIME]:-0},
    "build_jobs": ${BUILD_STATS[BUILD_JOBS]:-4},
    "cflags": "$CFLAGS"
  },
  "files": [
    "${model_name}.${quant_method,,}.gguf",
    "llama-cli",
    "llama-server",
    "README.md",
    "test_model.sh",
    "deploy.sh",
    "target_hardware_config.txt",
    "cmake_toolchain.cmake"
  ]
}
EOF
}

create_package_documentation() {
    local package_dir="$1"
    log_debug "Creating package documentation"
    
    cat > "$package_dir/README.md" << EOF
# ${TARGET_CONFIG[MODEL_NAME]} - ${TARGET_CONFIG[QUANT_METHOD]}
## Deployment Package (Target: ${TARGET_ARCH})

Generiert durch das LLM Cross-Compiler Framework.

### Inhalt
- \`${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf\`
- \`llama-cli\` (Cross-kompiliert für ${TARGET_ARCH})
- \`llama-server\` (Cross-kompiliert für ${TARGET_ARCH})
- \`test_model.sh\` (Test-Skript für Ziel-Hardware)
- \`deploy.sh\` (Deployment-Skript)
- \`MANIFEST.json\` (Build-Details)
- \`target_hardware_config.txt\` (Hardware-Profil)

### Verwendung auf ${TARGET_ARCH}
1. Übertragen Sie dieses Verzeichnis auf Ihr ${TARGET_ARCH}-Gerät.
2. Führen Sie den Test aus: \`./test_model.sh\`
3. Führen Sie das Deployment aus: \`./deploy.sh /opt/ai_models\`
EOF
}

create_helper_scripts() {
    local package_dir="$1"
    log_debug "Creating helper scripts"
    
    # Test script (Minimalistisch, da auf Ziel-Hardware ausgeführt)
    cat > "$package_dir/test_model.sh" << EOF
#!/bin/bash
set -euo pipefail
MODEL_FILE="\$(dirname "\$0")/${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf"
CLI_BINARY="\$(dirname "\$0")/llama-cli"

echo "🧪 Testing ${TARGET_CONFIG[MODEL_NAME]} (${TARGET_CONFIG[QUANT_METHOD]})"
if [[ ! -f "\$MODEL_FILE" ]] || [[ ! -f "\$CLI_BINARY" ]]; then
    echo "❌ Fehler: Model oder CLI-Binary fehlt."
    exit 1
fi

echo "🚀 Starte Basis-Funktionstest..."
if timeout 60 "\$CLI_BINARY" --model "\$MODEL_FILE" --prompt "Hello" --n-predict 10 --seed 42; then
    echo "✅ Model-Test erfolgreich!"
else
    echo "❌ Model-Test fehlgeschlagen"
    exit 1
fi
EOF
    chmod +x "$package_dir/test_model.sh"
    
    # Deployment script (Minimalistisch)
    cat > "$package_dir/deploy.sh" << EOF
#!/bin/bash
set -euo pipefail
PACKAGE_DIR="\$(dirname "\$0")"
DEPLOY_TARGET="\${1:-/opt/ai_models/${TARGET_CONFIG[MODEL_NAME]}}"
echo "🚀 Deploying ${TARGET_CONFIG[MODEL_NAME]} to \$DEPLOY_TARGET"
mkdir -p "\$DEPLOY_TARGET"
cp -R "\$PACKAGE_DIR"/* "\$DEPLOY_TARGET/"
echo "✅ Deployment abgeschlossen: \$DEPLOY_TARGET"
echo "🔧 Testen: \${DEPLOY_TARGET}/test_model.sh"
EOF
    chmod +x "$package_dir/deploy.sh"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

print_final_summary() {
    echo ""
    log_success "🎉 Deployment-Paket bereit! 🎉"
    echo "=================================="
    echo "Model: ${TARGET_CONFIG[MODEL_NAME]}"
    echo "Quantisierung: ${TARGET_CONFIG[QUANT_METHOD]}"
    echo "Target Arch: ${TARGET_ARCH:-unknown}"
    echo "Größe (FP16): ${TARGET_CONFIG[INPUT_SIZE_MB]:-0}MB"
    echo "Größe (INT4): ${QUANTIZATION_STATS[OUTPUT_SIZE_MB]:-0}MB"
    echo "Paket: ${TARGET_CONFIG[PACKAGE_DIR]}"
    echo "Latest Link: $(basename "${FINAL_PACKAGE_DIR}")/${TARGET_CONFIG[MODEL_NAME]}_${TARGET_CONFIG[QUANT_METHOD],,}_${TARGET_ARCH}_latest"
    echo "=================================="
}

main() {
    local start_time=$SECONDS
    log_info "Starte Target Module (Quantisierung & Packaging)..."
    
    # Parse arguments
    local input_gguf=""
    local quant_method="Q4_K_M"
    local model_name=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --input) input_gguf="$2"; shift 2;;
            --quantization) quant_method="$2"; shift 2;;
            --model-name) model_name="$2"; shift 2;;
            --help) 
                echo "Usage: $0 --input INPUT_GGUF [--quantization METHOD] [--model-name NAME]"
                echo "Supported quantization methods: ${!QUANT_METHODS[*]}"
                exit 0
                ;;
            *) die "Unknown argument: $1";;
        esac
    done
    
    if [[ -z "$input_gguf" ]]; then die "Input GGUF file required (--input)"; fi
    if [[ -z "$model_name" ]]; then model_name=$(basename "$input_gguf" .gguf | sed 's/\.fp16$//'); fi
    
    # Setup and validation
    setup_target_environment
    validate_inputs "$input_gguf" "$quant_method" "$model_name"
    
    # --- KORRIGIERTE PIPELINE-REIHENFOLGE ---
    
    # 1. Cross-Compilation der Binaries (MUSS VOR Quantisierung laufen)
    cross_compile_llama_cpp 
    
    # 2. Quantization (Nutzt die gerade erstellte Binary)
    quantize_model
    
    # 3. Validierung
    validate_quantized_model
    
    # 4. Packaging
    create_deployment_package
    
    # --- ENDE KORREKTUR ---
    
    local total_time=$((SECONDS - start_time))
    
    print_final_summary
    
    log_success "Target module completed in ${total_time} seconds"
    log_info "Framework pipeline completed successfully!"
}

# Only run main if script is executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi