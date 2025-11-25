#!/bin/bash
# target_module.sh - Quantization & Final Packaging Module (Template)
# Part of LLM Cross-Compiler Framework
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Cross-kompiliert llama.cpp Binaries, quantisiert GGUF, 
#        erstellt Deployment-Paket.

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

readonly SCRIPT_NAME="target_module.sh"
readonly SCRIPT_VERSION="1.0.0"

# Environment variables with defaults
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/repos/llama.cpp}"
readonly OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
readonly FINAL_PACKAGE_DIR="${OUTPUT_DIR}/packages"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"
DEBUG="${DEBUG:-0}"

# Load build configuration (setzt CMAKE_TOOLCHAIN_FILE, CFLAGS, CXXFLAGS, BUILD_JOBS etc.)
if [[ ! -f "${BUILD_CACHE_DIR}/build_config.sh" ]]; then
    echo "❌ [TARGET] Kritischer Fehler: build_config.sh nicht gefunden. Führen Sie config_module.sh zuerst aus." >&2
    exit 1
fi
source "${BUILD_CACHE_DIR}/build_config.sh"

# Target configuration storage
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
# 1. NATIVE BUILD (Für Quantisierungswerkzeuge)
# ============================================================================

build_native_tools() {
    log_info "Schritt 1A: Baue NATIVE Tools (x86) für schnelle Quantisierung..."
    
    local build_dir="$LLAMA_CPP_PATH/build_native"
    rm -rf "$build_dir" && mkdir -p "$build_dir"
    cd "$build_dir"

    # Native Kompilierung (nutzt GCC des Containers, nicht den Cross-Compiler)
    # Wir deaktivieren alles was wir nicht brauchen, um Zeit zu sparen
    cmake "$LLAMA_CPP_PATH" \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=OFF \
        -DLLAMA_BUILD_SERVER=OFF \
        -DGGML_NATIVE=ON  # Optimiert für den Build-Host

    make -j$(nproc) llama-quantize
    
    # Setze den Pfad zum Quantize-Tool auf dieses NATIVE Binary
    # (Variable wird lokal überschrieben, aber wir nutzen eh den direkten Pfad im Quantize-Schritt)
    LLAMA_CPP_QUANTIZE_NATIVE="$build_dir/bin/llama-quantize"
    
    if [[ ! -f "$LLAMA_CPP_QUANTIZE_NATIVE" ]]; then
        die "Native llama-quantize build failed"
    fi

    log_success "Native Tools gebaut: $LLAMA_CPP_QUANTIZE_NATIVE"
}

# ============================================================================
# 2. CROSS BUILD (Für Ziel-Hardware)
# ============================================================================

cross_compile_target() {
    log_info "Schritt 1B: Cross-Kompilierung für Target (${TARGET_ARCH:-unknown})..."
    
    local build_dir="$LLAMA_CPP_PATH/build_target"
    rm -rf "$build_dir" && mkdir -p "$build_dir"
    cd "$build_dir"
    
    local cmake_args=()
    cmake_args+=("-DCMAKE_BUILD_TYPE=Release")
    cmake_args+=("-DBUILD_SHARED_LIBS=OFF")
    # Deaktiviere Features die wir ggf. nicht brauchen um dependencies zu minimieren
    cmake_args+=("-DLLAMA_CURL=OFF") 

    # WICHTIG: Setze die Toolchain und Optimierungs-Flags aus config_module.sh
    cmake_args+=("-DCMAKE_TOOLCHAIN_FILE=${CMAKE_TOOLCHAIN_FILE}")
    cmake_args+=("-DCMAKE_C_FLAGS='${CFLAGS:-}'")
    cmake_args+=("-DCMAKE_CXX_FLAGS='${CXXFLAGS:-}'")
    
    log_info "Configuring target build..."
    if ! cmake "$LLAMA_CPP_PATH" "${cmake_args[@]}"; then
        die "CMake configuration failed"
    fi
    
    local build_jobs="${BUILD_JOBS:-4}"
    log_info "Building target binaries (${build_jobs} jobs)..."
    
    local start_time=$SECONDS
    # Kompiliere CLI und Server
    if ! make -j"$build_jobs" llama-cli llama-server; then 
        die "Target binary compilation failed."
    fi
    local build_time=$((SECONDS - start_time))
    
    # Pfade prüfen
    if [[ ! -f "$LLAMA_CPP_CLI" ]] || [[ ! -f "$LLAMA_CPP_SERVER" ]]; then
        die "Erforderliche Binaries (cli/server) wurden nicht erstellt."
    fi
    
    TARGET_CONFIG[LLAMA_CLI_BINARY]="$LLAMA_CPP_CLI"
    TARGET_CONFIG[LLAMA_SERVER_BINARY]="$LLAMA_CPP_SERVER"
    
    BUILD_STATS[BUILD_TIME]="$build_time"
    
    log_success "Target-Kompilierung abgeschlossen in ${build_time}s."
}

# ============================================================================
# 3. QUANTISIERUNG (Nutzt NATIVE Tools)
# ============================================================================

quantize_model() {
    local input_gguf="${TARGET_CONFIG[INPUT_GGUF]}"
    local quant_method="${TARGET_CONFIG[QUANT_METHOD]}"
    local model_name="${TARGET_CONFIG[MODEL_NAME]}"
    
    # Output filename convention
    local quantized_output="$OUTPUT_DIR/${model_name}.${quant_method,,}.gguf"
    
    log_info "Schritt 2: Quantisiere Model (Native Speed): FP16 → $quant_method"
    
    # Pfad zum nativen Tool (wurde in build_native_tools gesetzt/gebaut)
    local native_quantize_tool="$LLAMA_CPP_PATH/build_native/bin/llama-quantize"
    
    if [[ ! -f "$native_quantize_tool" ]]; then
        die "Native quantize tool not found at: $native_quantize_tool"
    fi

    if [[ -f "$quantized_output" ]]; then
        mv "$quantized_output" "${quantized_output}.backup.$(date +%s)"
        log_info "Backup existierender Datei erstellt"
    fi
    
    local start_time=$SECONDS
    
    # Ausführen
    if ! "$native_quantize_tool" "$input_gguf" "$quantized_output" "$quant_method"; then
        die "Model quantization failed"
    fi
    
    local quant_time=$((SECONDS - start_time))
    
    if [[ ! -f "$quantized_output" ]]; then die "Quantized model not created"; fi
    
    local output_size; output_size=$(stat -c%s "$quantized_output" 2>/dev/null || echo "0")
    
    QUANTIZATION_STATS[OUTPUT_FILE]="$quantized_output"
    QUANTIZATION_STATS[OUTPUT_SIZE_BYTES]="$output_size"
    QUANTIZATION_STATS[OUTPUT_SIZE_MB]="$((output_size / 1024 / 1024))"
    QUANTIZATION_STATS[QUANTIZATION_TIME]="$quant_time"
    
    # Compression Ratio berechnen
    local input_size="${TARGET_CONFIG[INPUT_SIZE_BYTES]:-1}"
    QUANTIZATION_STATS[COMPRESSION_RATIO]=$(echo "scale=2; $output_size * 100 / $input_size" | bc 2>/dev/null || echo "unknown")
    
    TARGET_CONFIG[QUANTIZED_GGUF]="$quantized_output"
    
    log_success "Quantization completed in ${quant_time}s: ${QUANTIZATION_STATS[OUTPUT_SIZE_MB]}MB"
}

# ============================================================================
# 4. PACKAGING & MANIFEST
# ============================================================================

create_deployment_package() {
    local model_name="${TARGET_CONFIG[MODEL_NAME]}"
    local quant_method="${TARGET_CONFIG[QUANT_METHOD]}"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local package_name="${model_name}_${quant_method,,}_${TARGET_ARCH:-unknown}_${timestamp}"
    local package_dir="$FINAL_PACKAGE_DIR/$package_name"
    
    log_info "Schritt 4: Erstelle Deployment-Paket: $package_name"
    
    rm -rf "$package_dir"
    mkdir -p "$package_dir"
    
    # Kopiere Artefakte
    log_info "Kopiere Model..."
    cp "${TARGET_CONFIG[QUANTIZED_GGUF]}" "$package_dir/"
    
    log_info "Kopiere Target-Binaries..."
    cp "${TARGET_CONFIG[LLAMA_CLI_BINARY]}" "$package_dir/llama-cli"
    cp "${TARGET_CONFIG[LLAMA_SERVER_BINARY]}" "$package_dir/llama-server"
    
    # Kopiere Build-Infos
    cp "${CMAKE_TOOLCHAIN_FILE}" "$package_dir/cmake_toolchain.cmake"
    if [[ -f "${BUILD_CACHE_DIR}/target_hardware_config.txt" ]]; then
        cp "${BUILD_CACHE_DIR}/target_hardware_config.txt" "$package_dir/"
    fi
    
    TARGET_CONFIG[PACKAGE_DIR]="$package_dir"
    TARGET_CONFIG[PACKAGE_NAME]="$package_name"
    
    # Generiere Hilfsdateien
    create_package_manifest "$package_dir"
    create_package_documentation "$package_dir"
    create_helper_scripts "$package_dir"
    
    # Latest Symlink
    local latest_link="$FINAL_PACKAGE_DIR/${model_name}_${quant_method,,}_latest"
    rm -f "$latest_link"
    ln -s "$package_name" "$latest_link"
    
    log_success "Deployment package created at: $package_dir"
}

create_package_manifest() {
    local package_dir="$1"
    local manifest_file="$package_dir/MANIFEST.json"
    
    cat > "$manifest_file" << EOF
{
  "package_info": {
    "name": "${TARGET_CONFIG[PACKAGE_NAME]}",
    "created": "$(date -Iseconds)",
    "framework_version": "1.0.0"
  },
  "model": {
    "name": "${TARGET_CONFIG[MODEL_NAME]}",
    "quantization": "${TARGET_CONFIG[QUANT_METHOD]}",
    "original_size_mb": ${TARGET_CONFIG[INPUT_SIZE_MB]:-0},
    "quantized_size_mb": ${QUANTIZATION_STATS[OUTPUT_SIZE_MB]:-0},
    "compression_ratio": "${QUANTIZATION_STATS[COMPRESSION_RATIO]:-0}%"
  },
  "target": {
    "architecture": "${TARGET_ARCH:-unknown}",
    "cpu_model": "${TARGET_CPU:-unknown}",
    "compiler_flags": "${CFLAGS:-}"
  },
  "build_stats": {
    "build_time_sec": ${BUILD_STATS[BUILD_TIME]:-0},
    "quant_time_sec": ${QUANTIZATION_STATS[QUANTIZATION_TIME]:-0}
  }
}
EOF
}

create_package_documentation() {
    local package_dir="$1"
    cat > "$package_dir/README.md" << EOF
# ${TARGET_CONFIG[MODEL_NAME]} (${TARGET_CONFIG[QUANT_METHOD]})
## Target: ${TARGET_ARCH:-Generic}

### Quick Start
1.  Copy this folder to your target device.
2.  Run \`./test_model.sh\` to verify functionality.
3.  Run \`./deploy.sh /usr/local/bin\` to install.

### Contents
- Model: \`.gguf\` file
- Binaries: \`llama-cli\`, \`llama-server\` (Compiled for Target)
- Tools: Test & Deploy scripts
EOF
}

create_helper_scripts() {
    local package_dir="$1"
    
    # Test Script
    cat > "$package_dir/test_model.sh" << 'EOF'
#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
MODEL=$(find "$DIR" -name "*.gguf" | head -n 1)
CLI="$DIR/llama-cli"

if [ ! -x "$CLI" ]; then chmod +x "$CLI"; fi

echo "Testing model: $(basename "$MODEL")"
"$CLI" -m "$MODEL" -p "Hello, world!" -n 10 --threads 4
EOF
    chmod +x "$package_dir/test_model.sh"
    
    # Deploy Script
    cat > "$package_dir/deploy.sh" << 'EOF'
#!/bin/bash
set -e
DEST="${1:-/opt/llm}"
echo "Deploying to $DEST..."
mkdir -p "$DEST"
cp -r * "$DEST/"
echo "Done."
EOF
    chmod +x "$package_dir/deploy.sh"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

print_final_summary() {
    echo ""
    echo "=================================================="
    echo "       BUILD & QUANTIZATION COMPLETED"
    echo "=================================================="
    echo " Model:         ${TARGET_CONFIG[MODEL_NAME]}"
    echo " Quantization:  ${TARGET_CONFIG[QUANT_METHOD]}"
    echo " Target Arch:   ${TARGET_ARCH:-unknown}"
    echo " Package:       ${TARGET_CONFIG[PACKAGE_DIR]}"
    echo "=================================================="
    echo ""
}

main() {
    local start_time=$SECONDS
    log_info "Starte Target Module (Template)..."
    
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
                echo "Usage: $0 --input FILE --quantization METHOD --model-name NAME"
                exit 0
                ;;
            *) die "Unknown argument: $1";;
        esac
    done
    
    if [[ -z "$input_gguf" ]]; then die "Input GGUF file required (--input)"; fi
    if [[ -z "$model_name" ]]; then 
        # Fallback model name extraction
        model_name=$(basename "$input_gguf" .gguf)
        model_name=${model_name%.fp16}
    fi
    
    # Setup
    setup_directories # (Falls nötig, aber meistens durch Docker Mounts schon da)
    
    # Validate
    validate_inputs "$input_gguf" "$quant_method" "$model_name"
    
    # 1. Native Tools bauen (Speedup!)
    build_native_tools
    
    # 2. Quantisieren (mit Native Tools)
    quantize_model
    
    # 3. Cross-Compilen (Target Binaries)
    cross_compile_target
    
    # 4. Packen
    create_deployment_package
    
    print_final_summary
}

setup_directories() {
    mkdir -p "$OUTPUT_DIR"
    mkdir -p "$FINAL_PACKAGE_DIR"
}

# Only run main if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
