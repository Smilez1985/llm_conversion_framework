#!/bin/bash
# rknn_module.sh - NPU Model Conversion Module
# Part of LLM Cross-Compiler Framework
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Konvertiert ONNX-Modelle (Piper-TTS, Vosk, Vision) in das RKNN-Format
#        für die RK3566/RK3588 NPU. Nutzt die Container-interne Python-Umgebung.

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

readonly SCRIPT_NAME="rknn_module.sh"
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
readonly SCRIPT_DIR="/app/scripts"  # Pfad im Docker-Container
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Default NPU Platform (wird ggf. überschrieben)
TARGET_PLATFORM="rk3566"
QUANT_TYPE="i8" # i8 (Int8) ist Standard für maximale NPU-Leistung

# ============================================================================
# LOGGING
# ============================================================================

log_info() { echo "ℹ️  [$(date '+%H:%M:%S')] [RKNN] $1"; }
log_success() { echo "✅ [$(date '+%H:%M:%S')] [RKNN] $1"; }
log_warn() { echo "⚠️  [$(date '+%H:%M:%S')] [RKNN] $1"; }
log_error() { echo "❌ [$(date '+%H:%M:%S')] [RKNN] $1" >&2; }

die() {
    log_error "$1"
    exit "${2:-1}"
}

# ============================================================================
# MAIN LOGIC
# ============================================================================

main() {
    local input_onnx=""
    local model_name=""
    
    # Parse Arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --input) input_onnx="$2"; shift 2;;
            --target) TARGET_PLATFORM="$2"; shift 2;;
            --quant) QUANT_TYPE="$2"; shift 2;;
            --model-name) model_name="$2"; shift 2;;
            *) die "Unbekannter Parameter: $1";;
        esac
    done
    
    # Validation
    if [[ -z "$input_onnx" ]]; then die "Input ONNX file required (--input)"; fi
    if [[ ! -f "$input_onnx" ]]; then die "ONNX file not found: $input_onnx"; fi
    if [[ -z "$model_name" ]]; then model_name=$(basename "$input_onnx" .onnx); fi
    
    # Setup Output Paths
    mkdir -p "$OUTPUT_DIR/rknn"
    local output_rknn="$OUTPUT_DIR/rknn/${model_name}_${TARGET_PLATFORM}_${QUANT_TYPE}.rknn"
    
    log_info "🚀 Starte RKNN Konvertierung..."
    log_info "Model: $model_name"
    log_info "Input: $input_onnx"
    log_info "Target Platform: $TARGET_PLATFORM"
    log_info "Quantization: $QUANT_TYPE"
    
    # Check Python Converter Script
    if [[ ! -f "$SCRIPT_DIR/rknn_converter.py" ]]; then
        die "Helper script missing: $SCRIPT_DIR/rknn_converter.py"
    fi
    
    # Execute Python Conversion
    # Wir nutzen 'python3' direkt, da die Umgebung im Dockerfile (rknn-toolkit2) bereits steht.
    
    local start_time=$SECONDS
    
    if python3 "$SCRIPT_DIR/rknn_converter.py" \
        --model "$input_onnx" \
        --output "$output_rknn" \
        --target "$TARGET_PLATFORM" \
        --dtype "$QUANT_TYPE"; then
        
        local duration=$((SECONDS - start_time))
        
        # Validate Output
        if [[ -f "$output_rknn" ]]; then
             local size_mb=$(du -m "$output_rknn" | cut -f1)
             log_success "Konvertierung erfolgreich in ${duration}s!"
             log_success "RKNN Model: $output_rknn ($size_mb MB)"
             
             # Create Metadata for Orchestrator
             echo "rknn_model_path=$output_rknn" > "$OUTPUT_DIR/rknn_build_info.txt"
             echo "target_platform=$TARGET_PLATFORM" >> "$OUTPUT_DIR/rknn_build_info.txt"
        else
             die "Output file missing despite success message."
        fi
        
    else
        log_error "Python conversion script failed."
        log_warn "Tipp: Prüfen Sie, ob das rknn-toolkit2 korrekt im Docker installiert ist."
        exit 1
    fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
