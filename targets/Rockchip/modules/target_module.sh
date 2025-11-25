#!/bin/bash
# target_module.sh - Quantization & Final Packaging
# DIREKTIVE: Goldstandard. Behebt "Quantisierungs-Falle" durch Native Build.

set -euo pipefail

# Globals
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/repos/llama.cpp}"
readonly OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
readonly FINAL_PACKAGE_DIR="${OUTPUT_DIR}/packages"

# Load Config
if [[ -f "${BUILD_CACHE_DIR}/build_config.sh" ]]; then
    source "${BUILD_CACHE_DIR}/build_config.sh"
fi

declare -A TARGET_CONFIG

# Logging
log_info() { echo "ℹ️  [$(date '+%H:%M:%S')] [TARGET] $1"; }
log_success() { echo "✅ [$(date '+%H:%M:%S')] [TARGET] $1"; }
log_error() { echo "❌ [$(date '+%H:%M:%S')] [TARGET] $1" >&2; }
die() { log_error "$1"; exit 1; }

# ============================================================================
# 1. NATIVE BUILD (Für Quantisierungswerkzeuge)
# ============================================================================
build_native_tools() {
    log_info "Schritt 1A: Baue NATIVE Tools (x86) für schnelle Quantisierung..."
    
    local build_dir="$LLAMA_CPP_PATH/build_native"
    rm -rf "$build_dir" && mkdir -p "$build_dir"
    cd "$build_dir"

    # Native Kompilierung (nutzt GCC des Containers, nicht den Cross-Compiler)
    cmake "$LLAMA_CPP_PATH" \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=OFF \
        -DLLAMA_BUILD_SERVER=OFF \
        -DGGML_NATIVE=ON 

    make -j$(nproc) llama-quantize
    
    # Setze den Pfad zum Quantize-Tool auf dieses NATIVE Binary
    LLAMA_CPP_QUANTIZE="$build_dir/bin/llama-quantize"
    
    log_success "Native Tools gebaut: $LLAMA_CPP_QUANTIZE"
}

# ============================================================================
# 2. CROSS BUILD (Für Ziel-Hardware)
# ============================================================================
cross_compile_target() {
    log_info "Schritt 1B: Cross-Kompilierung für Target (${TARGET_ARCH})..."
    
    local build_dir="$LLAMA_CPP_PATH/build_target"
    rm -rf "$build_dir" && mkdir -p "$build_dir"
    cd "$build_dir"
    
    # Hier nutzen wir das Toolchain-File von config_module.sh
    cmake "$LLAMA_CPP_PATH" \
        -DCMAKE_TOOLCHAIN_FILE="${CMAKE_TOOLCHAIN_FILE}" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_FLAGS="${CFLAGS:-}" \
        -DCMAKE_CXX_FLAGS="${CXXFLAGS:-}"

    make -j$(nproc) llama-cli llama-server

    # Pfade für das Packaging setzen
    TARGET_CONFIG[LLAMA_CLI_BINARY]="$build_dir/bin/llama-cli"
    TARGET_CONFIG[LLAMA_SERVER_BINARY]="$build_dir/bin/llama-server"
    
    log_success "Target Binaries gebaut."
}

# ============================================================================
# 3. QUANTISIERUNG (Nutzt NATIVE Tools)
# ============================================================================
quantize_model() {
    local input_gguf="${TARGET_CONFIG[INPUT_GGUF]}"
    local quant_method="${TARGET_CONFIG[QUANT_METHOD]}"
    local model_name="${TARGET_CONFIG[MODEL_NAME]}"
    local output_gguf="$OUTPUT_DIR/${model_name}.${quant_method,,}.gguf"
    
    log_info "Schritt 2: Quantisiere Model (Native Speed)..."
    
    if ! "$LLAMA_CPP_QUANTIZE" "$input_gguf" "$output_gguf" "$quant_method"; then
        die "Quantisierung fehlgeschlagen"
    fi
    
    TARGET_CONFIG[QUANTIZED_GGUF]="$output_gguf"
    log_success "Quantisierung abgeschlossen."
}

# ============================================================================
# 4. PACKAGING
# ============================================================================
create_package() {
    local pkg_name="${TARGET_CONFIG[MODEL_NAME]}_${TARGET_CONFIG[QUANT_METHOD]}_${TARGET_ARCH}"
    local pkg_dir="$FINAL_PACKAGE_DIR/$pkg_name"
    
    mkdir -p "$pkg_dir"
    cp "${TARGET_CONFIG[QUANTIZED_GGUF]}" "$pkg_dir/"
    cp "${TARGET_CONFIG[LLAMA_CLI_BINARY]}" "$pkg_dir/"
    cp "${TARGET_CONFIG[LLAMA_SERVER_BINARY]}" "$pkg_dir/"
    
    log_success "Paket erstellt: $pkg_dir"
}

main() {
    local input_gguf=""
    local quant_method="Q4_K_M"
    local model_name=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --input) input_gguf="$2"; shift 2;;
            --quantization) quant_method="$2"; shift 2;;
            --model-name) model_name="$2"; shift 2;;
            *) shift;;
        esac
    done
    
    TARGET_CONFIG[INPUT_GGUF]="$input_gguf"
    TARGET_CONFIG[QUANT_METHOD]="$quant_method"
    TARGET_CONFIG[MODEL_NAME]="$model_name"
    
    build_native_tools
    quantize_model
    cross_compile_target
    create_package
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
