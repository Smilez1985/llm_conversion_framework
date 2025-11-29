#!/bin/bash
# rknn_module.sh - RKNN Toolkit Execution Module
# Optimized for RK3566/RK3588 NPU (Vision/Audio/Generic)
# Part of LLM Cross-Compiler Framework
#
# DIREKTIVE: Goldstandard. Entkoppelte Architektur.

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

# Environment Variables (Injected by Orchestrator/Builder)
# $MODEL_SOURCE    : Path to input model (ONNX, PyTorch, etc.)
# $QUANTIZATION    : Target quantization (INT8, FP16)
# $OUTPUT_DIR      : Artifact destination

# Defaults
RKNN_TOOLKIT_DIR="/app/rknn-toolkit2" # Standard Install Path in Docker
BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
SCRIPT_DIR="/app/scripts"

log() { echo ">> [RKNN] [$(date '+%H:%M:%S')] $1"; }
die() { echo "❌ [RKNN] [$(date '+%H:%M:%S')] $1" >&2; exit 1; }

# ============================================================================
# MAIN LOGIC
# ============================================================================

main() {
    log "Starting RKNN Pipeline..."

    # 1. Input Validation
    if [[ -z "${MODEL_SOURCE:-}" ]]; then
        die "Environment variable MODEL_SOURCE is missing."
    fi
    
    if [[ ! -f "$MODEL_SOURCE" && ! -d "$MODEL_SOURCE" ]]; then
        die "Model source not found: $MODEL_SOURCE"
    fi

    # 2. Quantization Mapping
    # RKNN Toolkit 2 nutzt 'i8' für asymmetrische Quantisierung (Standard) oder 'fp16'
    case "${QUANTIZATION:-INT8}" in
        "INT8"|"i8"|"Q8_0")
            Q_TYPE="i8"
            ;;
        "FP16"|"f16")
            Q_TYPE="fp16"
            ;;
        *)
            log "Warning: Unknown quantization '$QUANTIZATION'. Defaulting to i8 (INT8)."
            Q_TYPE="i8"
            ;;
    esac

    # 3. Target Platform Detection (Optional Overrides)
    # Default to rk3566 (common for this module), but allow override via env
    TARGET_PLATFORM="${TARGET_BOARD:-rk3566}"
    
    # Normalize target name (rknn config expects lowercase)
    if [[ "$TARGET_PLATFORM" == *"3588"* ]]; then TARGET_PLATFORM="rk3588"; fi
    if [[ "$TARGET_PLATFORM" == *"3566"* ]]; then TARGET_PLATFORM="rk3566"; fi
    if [[ "$TARGET_PLATFORM" == *"3568"* ]]; then TARGET_PLATFORM="rk3568"; fi

    log "Configuration:"
    log "  - Model:    $MODEL_SOURCE"
    log "  - Target:   $TARGET_PLATFORM"
    log "  - Quant:    $Q_TYPE"
    log "  - Script:   $SCRIPT_DIR/rknn_converter.py"

    # 4. Execute Python Converter
    # Wir rufen das dedizierte Skript auf.
    CONVERTER="$SCRIPT_DIR/rknn_converter.py"
    
    if [ ! -f "$CONVERTER" ]; then
        die "Critical: Converter script missing at $CONVERTER. Check Dockerfile copy instructions."
    fi
    
    # Dateiname für Output generieren
    MODEL_NAME=$(basename "$MODEL_SOURCE")
    # Entferne Extension
    MODEL_NAME="${MODEL_NAME%.*}"
    OUTPUT_FILE="$OUTPUT_DIR/${MODEL_NAME}_${TARGET_PLATFORM}_${Q_TYPE}.rknn"
    
    log "Running conversion..."
    
    # Python Aufruf (Capture Exit Code)
    set +e
    python3 "$CONVERTER" \
        --model "$MODEL_SOURCE" \
        --output "$OUTPUT_FILE" \
        --target "$TARGET_PLATFORM" \
        --dtype "$Q_TYPE"
    
    EXIT_CODE=$?
    set -e
    
    if [ $EXIT_CODE -eq 0 ]; then
        log "Conversion successful."
        
        if [ -f "$OUTPUT_FILE" ]; then
            SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
            log "Artifact created: $OUTPUT_FILE ($SIZE)"
            
            # Metadata schreiben
            echo "framework=rknn" > "$OUTPUT_DIR/model_info.txt"
            echo "platform=$TARGET_PLATFORM" >> "$OUTPUT_DIR/model_info.txt"
            echo "quantization=$Q_TYPE" >> "$OUTPUT_DIR/model_info.txt"
        else
            die "Output file missing despite success code."
        fi
    else
        die "Python conversion failed with code $EXIT_CODE."
    fi
    
    log "RKNN Pipeline Finished."
}

main "$@"
