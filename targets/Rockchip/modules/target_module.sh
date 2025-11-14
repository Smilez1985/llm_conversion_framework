#!/bin/bash
# target_module.sh - Quantization & Final Packaging Module
# Part of LLM Cross-Compiler Framework
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Quantisiert GGUF FP16 → gewünschtes Format, cross-kompiliert llama.cpp,
#        erstellt deployment-ready Package mit Dokumentation und Tests

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

readonly SCRIPT_NAME="target_module.sh"
readonly SCRIPT_VERSION="1.0.0"

# Environment variables with defaults
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/llama.cpp}" # Geklont in source_module.sh
readonly OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
readonly TEMP_DIR="${OUTPUT_DIR}/temp"
readonly FINAL_PACKAGE_DIR="${OUTPUT_DIR}/packages"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Lade Build-Konfiguration, generiert von config_module.sh
# Setzt: TARGET_ARCH, CMAKE_TOOLCHAIN_FILE, CFLAGS, CXXFLAGS, BUILD_JOBS etc.
if [[ -f "${BUILD_CACHE_DIR}/build_config.sh" ]]; then
    source "${BUILD_CACHE_DIR}/build_config.sh"
fi

# Target configuration
declare -A TARGET_CONFIG
declare -A QUANTIZATION_STATS
declare -A BUILD_STATS

# Tools (Verweist auf den Build-Ordner von llama.cpp)
LLAMA_CPP_QUANTIZE="$LLAMA_CPP_PATH/build/bin/llama-quantize"
LLAMA_CPP_CLI="$LLAMA_CPP_PATH/build/bin/llama-cli"
LLAMA_CPP_SERVER="$LLAMA_CPP_PATH/build/bin/llama-server"

# Supported quantization methods (für Manifest)
declare -A QUANT_METHODS=(
    ["Q4_K_M"]="4-bit k-quantization (medium, recommended)"
    ["Q8_0"]="8-bit integer quantization (high quality)"
)

# ============================================================================
# LOGGING & ERROR HANDLING
# ============================================================================

log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$SCRIPT_NAME] [$level] $message" >&2
}

log_info() { [[ "$LOG_LEVEL" != "ERROR" ]] && log "INFO" "$1"; }
log_warn() { log "WARN" "$1"; }
log_error() { log "ERROR" "$1"; }
log_success() { log "SUCCESS" "$1"; }
log_debug() { [[ "${DEBUG:-0}" == "1" ]] && log "DEBUG" "$1"; }

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
# INPUT VALIDATION & CONFIGURATION
# ============================================================================

validate_inputs() {
    local input_gguf="$1"
    local quant_method="$2"
    local model_name="$3"
    
    log_info "Validating target module inputs"
    
    if [[ ! -f "$input_gguf" ]]; then die "Input GGUF file not found: $input_gguf"; fi
    
    local file_size; file_size=$(stat -c%s "$input_gguf" 2>/dev/null || echo "0")
    if [[ "$file_size" -lt 1048576 ]]; then die "Input GGUF file suspiciously small"; fi
    
    if [[ -z "${QUANT_METHODS[$quant_method]:-}" ]]; then die "Unsupported quantization method: $quant_method"; fi
    if [[ -z "$model_name" ]] || [[ "$model_name" =~ [^a-zA-Z0-9_-] ]]; then die "Invalid model name"; fi
    
    TARGET_CONFIG[INPUT_GGUF]="$input_gguf"
    TARGET_CONFIG[QUANT_METHOD]="$quant_method"
    TARGET_CONFIG[MODEL_NAME]="$model_name"
    TARGET_CONFIG[INPUT_SIZE_BYTES]="$file_size"
    TARGET_CONFIG[INPUT_SIZE_MB]="$((file_size / 1024 / 1024))"
    
    log_success "Input validation completed: ${TARGET_CONFIG[INPUT_SIZE_MB]}MB GGUF, $quant_method quantization"
}

setup_target_environment() {
    log_info "Setting up target build environment"
    
    # Create necessary directories
    mkdir -p "$OUTPUT_DIR" "$TEMP_DIR" "$FINAL_PACKAGE_DIR"
    
    # Verify llama.cpp installation
    if [[ ! -d "$LLAMA_CPP_PATH" ]]; then die "llama.cpp not found at: $LLAMA_CPP_PATH"; fi
    
    # Check for build toolchain variables set by config_module.sh
    if [[ -z "${CMAKE_TOOLCHAIN_FILE:-}" ]] || [[ ! -f "${CMAKE_TOOLCHAIN_FILE:-}" ]]; then
        log_error "CMAKE_TOOLCHAIN_FILE nicht gefunden. config_module.sh muss zuerst erfolgreich ausgeführt werden."
        exit 1
    fi

    TARGET_CONFIG[CROSS_COMPILE]="true"
    log_success "Target environment ready"
}

# ============================================================================
# CROSS-COMPILATION DER BINARIES
# ============================================================================

cross_compile_llama_cpp() {
    log_info "Schritt 1/4: Cross-Kompilierung von llama.cpp Binaries für ${TARGET_ARCH}"
    
    local build_dir="$LLAMA_CPP_PATH/build_target"
    local build_type="${CMAKE_BUILD_TYPE:-Release}"
    BUILD_DIR="$build_dir"  # Für Cleanup
    
    rm -rf "$build_dir"
    mkdir -p "$build_dir"
    cd "$build_dir"
    
    local cmake_args=()
    cmake_args+=("-DCMAKE_BUILD_TYPE=$build_type")
    cmake_args+=("-DBUILD_SHARED_LIBS=OFF")
    cmake_args+=("-DLLAMA_CURL=OFF")
    cmake_args+=("-DGGML_CUDA=OFF")
    cmake_args+=("-DGGML_SYCL=OFF")
    cmake_args+=("-DLLAMA_BLAS=OFF")
    cmake_args+=("-DCMAKE_TOOLCHAIN_FILE=${CMAKE_TOOLCHAIN_FILE}")

    # CFLAGS und CXXFLAGS werden aus build_config.sh (Source) geladen
    cmake_args+=("-DCMAKE_C_FLAGS='$CFLAGS'")
    cmake_args+=("-DCMAKE_CXX_FLAGS='$CXXFLAGS'")
    
    # Run CMake configuration
    log_info "Configuring llama.cpp build..."
    if ! cmake "$LLAMA_CPP_PATH" "${cmake_args[@]}"; then
        die "CMake configuration failed"
    fi
    
    # Build binaries (llama-cli, llama-server, llama-quantize)
    local build_jobs="${BUILD_JOBS:-4}"
    log_info "Building llama.cpp binaries (${build_jobs} jobs)..."
    
    local start_time=$SECONDS
    # Kompiliere alle notwendigen Binaries
    if ! make -j"$build_jobs" llama-quantize llama-cli llama-server; then 
        die "llama.cpp Binär-Kompilierung fehlgeschlagen. Überprüfen Sie den Toolchain-Output."
    fi
    local build_time=$((SECONDS - start_time))
    
    # Validiere Binaries (sie liegen in build_target/bin/)
    local binaries=("bin/llama-cli" "bin/llama-server" "bin/llama-quantize")
    for binary in "${binaries[@]}"; do
        if [[ ! -f "$binary" ]]; then
            die "Erforderliches Binary nicht gebaut: $binary"
        fi
    done
    
    # Store build statistics
    BUILD_STATS[BUILD_TIME]="$build_time"
    BUILD_STATS[BUILD_JOBS]="$build_jobs"
    
    # Store binary paths for packaging (Absolute Pfade)
    TARGET_CONFIG[LLAMA_CLI_BINARY]="$build_dir/bin/llama-cli"
    TARGET_CONFIG[LLAMA_SERVER_BINARY]="$build_dir/bin/llama-server"
    
    log_success "Cross-Kompilierung abgeschlossen in ${build_time}s. Binaries erstellt."
}

# ============================================================================
# QUANTIZATION
# ============================================================================

quantize_model() {
    local input_gguf="${TARGET_CONFIG[INPUT_GGUF]}"
    local quant_method="${TARGET_CONFIG[QUANT_METHOD]}"
    local model_name="${TARGET_CONFIG[MODEL_NAME]}"
    
    local quantized_output="$OUTPUT_DIR/${model_name}.${quant_method,,}.gguf"
    
    log_info "Schritt 2/4: Starte Model-Quantisierung: FP16 → $quant_method"
    
    # Verify quantize tool exists (MUSS VORHER KOMPILIERT WORDEN SEIN)
    if [[ ! -f "$LLAMA_CPP_QUANTIZE" ]]; then
        die "llama-quantize tool nicht gefunden (Build fehlgeschlagen): $LLAMA_CPP_QUANTIZE"
    fi

    # Backup existing quantized model if present
    if [[ -f "$quantized_output" ]]; then
        local backup_file="${quantized_output}.backup.$(date +%s)"
        mv "$quantized_output" "$backup_file"
        log_info "Created backup: $(basename "$backup_file")"
    fi
    
    # Run quantization (Host-Ausführung, da es ein LLAMA.CPP Python-Tool ist)
    local start_time=$SECONDS
    
    # Führe die Binärdatei direkt aus dem Build-Pfad aus (Cross-Kompilierung läuft auf Host)
    if ! "$LLAMA_CPP_QUANTIZE" "$input_gguf" "$quantized_output" "$quant_method"; then
        die "Model quantization failed"
    fi
    
    local quant_time=$((SECONDS - start_time))
    
    # Validate quantized output
    if [[ ! -f "$quantized_output" ]]; then
        die "Quantized model not created: $quantized_output"
    fi
    
    local output_size
    output_size=$(stat -c%s "$quantized_output" 2>/dev/null || echo "0")
    
    # Store statistics
    QUANTIZATION_STATS[OUTPUT_FILE]="$quantized_output"
    QUANTIZATION_STATS[OUTPUT_SIZE_BYTES]="$output_size"
    QUANTIZATION_STATS[OUTPUT_SIZE_MB]="$((output_size / 1024 / 1024))"
    QUANTIZATION_STATS[QUANTIZATION_TIME]="$quant_time"
    QUANTIZATION_STATS[COMPRESSION_RATIO]=$(echo "scale=2; $output_size * 100 / ${TARGET_CONFIG[INPUT_SIZE_BYTES]}" | bc 2>/dev/null || echo "unknown")
    
    TARGET_CONFIG[QUANTIZED_GGUF]="$quantized_output"
    
    log_success "Quantization completed in ${quant_time}s: ${QUANTIZATION_STATS[OUTPUT_SIZE_MB]}MB (${QUANTIZATION_STATS[COMPRESSION_RATIO]}% of original)"
}

# ============================================================================
# MODEL VALIDATION & TESTING
# ============================================================================

validate_quantized_model() {
    local quantized_gguf="${TARGET_CONFIG[QUANTIZED_GGUF]}"
    local llama_cli="${TARGET_CONFIG[LLAMA_CLI_BINARY]}"
    
    log_info "Schritt 3/4: Validiere Model-Größe und Integrität"
    
    local min_size=$((50 * 1024 * 1024))  # 50MB minimum
    local actual_size="${QUANTIZATION_STATS[OUTPUT_SIZE_BYTES]}"
    
    if [[ "$actual_size" -lt "$min_size" ]]; then
        die "Quantized model suspiciously small: $((actual_size / 1024 / 1024))MB"
    fi
    
    # Functional test WIRD HIER NICHT AUSGEFÜHRT (Cross-Compile-Limit)
    log_warn "Überspringe Funktionstest: Cross-kompilierte Binaries können auf dem Host nicht ausgeführt werden."
    
    log_success "Model validation completed"
}

# ============================================================================
# PACKAGE CREATION
# ============================================================================

create_deployment_package() {
    local model_name="${TARGET_CONFIG[MODEL_NAME]}"
    local quant_method="${TARGET_CONFIG[QUANT_METHOD]}"
    local target_arch="${TARGET_ARCH:-unknown}"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local package_name="${model_name}_${quant_method,,}_${target_arch}_${timestamp}"
    local package_dir="$FINAL_PACKAGE_DIR/$package_name"
    
    log_info "Schritt 4/4: Erstelle Deployment-Paket: $package_name"
    
    rm -rf "$package_dir"
    mkdir -p "$package_dir"
    
    # Copy quantized model
    cp "${TARGET_CONFIG[QUANTIZED_GGUF]}" "$package_dir/${model_name}.${quant_method,,}.gguf"
    
    # Copy binaries (Cross-kompilierte Binaries)
    if [[ -f "${TARGET_CONFIG[LLAMA_CLI_BINARY]}" ]]; then
        cp "${TARGET_CONFIG[LLAMA_CLI_BINARY]}" "$package_dir/llama-cli"
        chmod +x "$package_dir/llama-cli"
    fi
    
    if [[ -f "${TARGET_CONFIG[LLAMA_SERVER_BINARY]}" ]]; then
        cp "${TARGET_CONFIG[LLAMA_SERVER_BINARY]}" "$package_dir/llama-server"
        chmod +x "$package_dir/llama-server"
    fi
    
    # Copy build configuration files
    if [[ -f "${CMAKE_TOOLCHAIN_FILE:-}" ]]; then
        cp "$CMAKE_TOOLCHAIN_FILE" "$package_dir/cmake_toolchain.cmake"
    fi
    
    if [[ -f "${BUILD_CACHE_DIR}/target_hardware_config.txt" ]]; then
        cp "${BUILD_CACHE_DIR}/target_hardware_config.txt" "$package_dir/"
    fi
    
    # Store package info
    TARGET_CONFIG[PACKAGE_DIR]="$package_dir"
    TARGET_CONFIG[PACKAGE_NAME]="$package_name"
    
    # Create package manifest
    create_package_manifest "$package_dir"
    
    # Create documentation
    create_package_documentation "$package_dir"
    
    # Create helper scripts
    create_helper_scripts "$package_dir"
    
    # Create latest symlink
    local latest_link="$FINAL_PACKAGE_DIR/${model_name}_${quant_method,,}_${target_arch}_latest"
    rm -f "$latest_link"
    ln -s "$package_name" "$latest_link"
    
    log_success "Deployment package created: $package_dir"
}

create_package_manifest() {
    local package_dir="$1"
    
    log_info "Creating package manifest"
    
    cat > "$package_dir/MANIFEST.json" << EOF
{
  "package_info": {
    "name": "${TARGET_CONFIG[PACKAGE_NAME]}",
    "model_name": "${TARGET_CONFIG[MODEL_NAME]}",
    "quantization": "${TARGET_CONFIG[QUANT_METHOD]}",
    "target_architecture": "${TARGET_ARCH:-unknown}",
    "created": "$(date -Iseconds)",
    "creator": "$SCRIPT_NAME v$SCRIPT_VERSION"
  },
  "model_info": {
    "original_size_mb": ${TARGET_CONFIG[INPUT_SIZE_MB]:-0},
    "quantized_size_mb": ${QUANTIZATION_STATS[OUTPUT_SIZE_MB]:-0},
    "compression_ratio": "${QUANTIZATION_STATS[COMPRESSION_RATIO]:-0}%",
    "quantization_method": "${TARGET_CONFIG[QUANT_METHOD]}",
    "quantization_description": "${QUANT_METHODS[${TARGET_CONFIG[QUANT_METHOD]}]}"
  },
  "hardware_target": {
    "architecture": "${TARGET_CONFIG[HW_ARCHITECTURE_FULL]:-unknown}",
    "cpu_model": "${TARGET_CONFIG[HW_CPU_MODEL_NAME]:-unknown}",
    "cpu_cores": "${TARGET_CONFIG[HW_CPU_CORES]:-unknown}",
    "neon_support": "${TARGET_CONFIG[HW_SUPPORTS_NEON]:-unknown}",
    "gpu_model": "${TARGET_CONFIG[HW_GPU_MODEL]:-unknown}"
  },
  "build_info": {
    "cross_compile": "${TARGET_CONFIG[CROSS_COMPILE]}",
    "build_time_seconds": ${BUILD_STATS[BUILD_TIME]:-0},
    "quantization_time_seconds": ${QUANTIZATION_STATS[QUANTIZATION_TIME]:-0},
    "build_jobs": ${BUILD_STATS[BUILD_JOBS]:-4},
    "cmake_toolchain": "${CMAKE_TOOLCHAIN_FILE:-none}"
  },
  "files": {
    "model": "${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf",
    "cli_binary": "llama-cli",
    "server_binary": "llama-server",
    "documentation": "README.md",
    "test_script": "test_model.sh",
    "deploy_script": "deploy.sh"
  }
}
EOF
}

create_package_documentation() {
    local package_dir="$1"
    
    log_info "Creating package documentation"
    
    cat > "$package_dir/README.md" << EOF
# ${TARGET_CONFIG[MODEL_NAME]} - ${TARGET_CONFIG[QUANT_METHOD]} Quantized

## Package Information
- **Model**: ${TARGET_CONFIG[MODEL_NAME]}
- **Quantization**: ${TARGET_CONFIG[QUANT_METHOD]} (${QUANT_METHODS[${TARGET_CONFIG[QUANT_METHOD]}]})
- **Target Architecture**: ${TARGET_ARCH:-unknown}
- **Package Created**: $(date)
- **Framework**: LLM Cross-Compiler Framework v$SCRIPT_VERSION

## Model Statistics
- **Original Size**: ${TARGET_CONFIG[INPUT_SIZE_MB]:-0}MB (FP16)
- **Quantized Size**: ${QUANTIZATION_STATS[OUTPUT_SIZE_MB]:-0}MB
- **Compression Ratio**: ${QUANTIZATION_STATS[COMPRESSION_RATIO]:-0}%
- **Build Time**: ${BUILD_STATS[BUILD_TIME]:-unknown}s

## Hardware Target
- **Architecture**: ${TARGET_CONFIG[HW_ARCHITECTURE_FULL]:-unknown}
- **CPU**: ${TARGET_CONFIG[HW_CPU_MODEL_NAME]:-unknown}
- **Cores**: ${TARGET_CONFIG[HW_CPU_CORES]:-unknown}
- **NEON Support**: ${TARGET_CONFIG[HW_SUPPORTS_NEON]:-unknown}
- **GPU**: ${TARGET_CONFIG[HW_GPU_MODEL]:-Not detected}

## Quick Start

### Run Interactive Chat
\`\`\`bash
./llama-cli --model ${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf --interactive
\`\`\`

### Run as Server
\`\`\`bash
./llama-server --model ${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf --port 8080
\`\`\`

### Test Model
\`\`\`bash
./test_model.sh
\`\`\`

### Deploy to Production
\`\`\`bash
./deploy.sh /path/to/deployment/directory
\`\`\`

## Files Included
- \`${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf\` - Quantized model
- \`llama-cli\` - Command line interface
- \`llama-server\` - HTTP API server
- \`test_model.sh\` - Model testing script
- \`deploy.sh\` - Deployment helper script
- \`MANIFEST.json\` - Package metadata
- \`target_hardware_config.txt\` - Hardware configuration used for build

## Performance Expectations
Actual performance depends on your specific hardware configuration and system load.

## Cross-Compilation Details
- **Cross-Compile**: ${TARGET_CONFIG[CROSS_COMPILE]}
- **Toolchain**: $(basename "${CMAKE_TOOLCHAIN_FILE:-Native compilation}")
- **Optimizations**: Target-specific compiler flags applied

## Support
This package was generated by the LLM Cross-Compiler Framework.
For issues, please check the framework documentation.

---
Generated by $SCRIPT_NAME v$SCRIPT_VERSION
EOF
}

create_helper_scripts() {
    local package_dir="$1"
    
    log_info "Creating helper scripts"
    
    # Test script
    cat > "$package_dir/test_model.sh" << EOF
#!/bin/bash
# Model Test Script
set -euo pipefail

MODEL_FILE="\$(dirname "\$0")/${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf"
CLI_BINARY="\$(dirname "\$0")/llama-cli"

echo "🧪 Testing ${TARGET_CONFIG[MODEL_NAME]} (${TARGET_CONFIG[QUANT_METHOD]})"
echo "============================================"

# Check files exist
if [[ ! -f "\$MODEL_FILE" ]]; then
    echo "❌ Model file not found: \$MODEL_FILE"
    exit 1
fi

if [[ ! -f "\$CLI_BINARY" ]]; then
    echo "❌ CLI binary not found: \$CLI_BINARY"
    exit 1
fi

# Check model size
MODEL_SIZE=\$(du -h "\$MODEL_FILE" | cut -f1)
echo "📊 Model size: \$MODEL_SIZE"

# Check available memory
AVAILABLE_MEM=\$(free -h | grep Available | awk '{print \$7}' || free -h | grep Mem | awk '{print \$7}')
echo "🧠 Available memory: \$AVAILABLE_MEM"

# Basic functionality test
echo "🚀 Running basic functionality test..."
if timeout 60 "\$CLI_BINARY" --model "\$MODEL_FILE" --prompt "Hello" --n-predict 10 --seed 42; then
    echo "✅ Model test passed!"
else
    echo "❌ Model test failed"
    exit 1
fi

echo "🎉 All tests completed successfully!"
EOF
    chmod +x "$package_dir/test_model.sh"
    
    # Deployment script
    cat > "$package_dir/deploy.sh" << EOF
#!/bin/bash
# Deployment Script
set -euo pipefail

PACKAGE_DIR="\$(dirname "\$0")"
DEPLOY_TARGET="\${1:-/opt/ai_models/${TARGET_CONFIG[MODEL_NAME]}}"

echo "🚀 Deploying ${TARGET_CONFIG[MODEL_NAME]} to \$DEPLOY_TARGET"

# Create target directory
if [[ ! -w "\$(dirname "\$DEPLOY_TARGET")" ]] 2>/dev/null; then
    echo "⚠️  Requires sudo for deployment to: \$DEPLOY_TARGET"
    sudo mkdir -p "\$DEPLOY_TARGET"
    sudo cp "\$PACKAGE_DIR"/* "\$DEPLOY_TARGET/"
    sudo chown -R \$(whoami):\$(whoami) "\$DEPLOY_TARGET"
else
    mkdir -p "\$DEPLOY_TARGET"
    cp "\$PACKAGE_DIR"/* "\$DEPLOY_TARGET/"
fi

echo "✅ Deployment completed: \$DEPLOY_TARGET"
echo "📋 Files deployed:"
ls -la "\$DEPLOY_TARGET"

echo ""
echo "🔧 Nächste Schritte:"
echo "1. Test deployment: \$DEPLOY_TARGET/test_model.sh"
echo "2. Run interactive: \$DEPLOY_TARGET/llama-cli --model \$DEPLOY_TARGET/${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf --interactive"
echo "3. Start server: \$DEPLOY_TARGET/llama-server --model \$DEPLOY_TARGET/${TARGET_CONFIG[MODEL_NAME]}.${TARGET_CONFIG[QUANT_METHOD],,}.gguf --port 8080"
EOF
    chmod +x "$package_dir/deploy.sh"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log_info "Starting $SCRIPT_NAME v$SCRIPT_VERSION"
    
    # Parse arguments
    local input_gguf=""
    local quant_method="Q4_K_M"  # Default
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
    
    # Main processing pipeline
    local start_time=$SECONDS
    
    # 1. Cross-Compilation der Binaries (MUSS VOR Quantisierung laufen)
    log_info "Schritt 1/4: Kompiliere Target-Binaries für Cross-Deployment"
    cross_compile_llama_cpp 
    
    # 2. Quantization (Nutzt die gerade erstellte Binary)
    log_info "Schritt 2/4: Quantisiere Model"
    quantize_model
    
    # 3. Validierung
    log_info "Schritt 3/4: Validiere finales Model"
    validate_quantized_model
    
    # 4. Packaging
    log_info "Schritt 4/4: Erstelle Deployment-Paket"
    create_deployment_package
    
    local total_time=$((SECONDS - start_time))
    
    print_final_summary
    
    log_success "Target module completed in ${total_time} seconds"
    log_info "Framework pipeline completed successfully!"
}

# Only run main if script is executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi