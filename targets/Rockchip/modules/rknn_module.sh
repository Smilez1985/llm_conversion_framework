#!/bin/bash
# rknn_module.sh - RKNN Toolkit Execution Module
# Optimized for RK3566/RK3588 NPU (Vision/Audio/Generic)

set -euo pipefail

# Environment Variables
# $MODEL_SOURCE, $QUANTIZATION, $OUTPUT_DIR, $DATASET_PATH (Optional)

RKNN_TOOLKIT_DIR="/app/rknn-toolkit2"
BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
SCRIPT_DIR="/app/scripts"
DATASET="${DATASET_PATH:-}" # Empty if not set

log() { echo ">> [RKNN] $1"; }
die() { echo "❌ [RKNN] $1" >&2; exit 1; }

main() {
    log "Starting RKNN Pipeline..."

    if [[ -z "${MODEL_SOURCE:-}" ]]; then die "MODEL_SOURCE missing."; fi
    
    # Quantization Mapping
    case "${QUANTIZATION:-INT8}" in
        "INT8"|"i8"|"Q8_0") Q_TYPE="i8";;
        "FP16"|"f16") Q_TYPE="fp16";;
        *) log "Warning: Unknown quantization. Defaulting to i8."; Q_TYPE="i8";;
    esac

    TARGET_PLATFORM="${TARGET_BOARD:-rk3566}"
    if [[ "$TARGET_PLATFORM" == *"3588"* ]]; then TARGET_PLATFORM="rk3588"; fi
    if [[ "$TARGET_PLATFORM" == *"3566"* ]]; then TARGET_PLATFORM="rk3566"; fi

    log "Config: Target=$TARGET_PLATFORM, Quant=$Q_TYPE"
    if [[ -n "$DATASET" ]]; then log "Dataset: $DATASET"; else log "Dataset: None (Hybrid Mode)"; fi

    CONVERTER="$SCRIPT_DIR/rknn_converter.py"
    if [ ! -f "$CONVERTER" ]; then die "Converter script missing."; fi
    
    MODEL_NAME=$(basename "$MODEL_SOURCE")
    OUTPUT_FILE="$OUTPUT_DIR/${MODEL_NAME%.*}_${TARGET_PLATFORM}_${Q_TYPE}.rknn"
    
    log "Running Python Converter..."
    
    # Build Args
    ARGS=("--model" "$MODEL_SOURCE" "--output" "$OUTPUT_FILE" "--target" "$TARGET_PLATFORM" "--dtype" "$Q_TYPE")
    if [[ -n "$DATASET" ]]; then
        ARGS+=("--dataset" "$DATASET")
    fi
    
    if python3 "$CONVERTER" "${ARGS[@]}"; then
        log "Success: $OUTPUT_FILE"
    else
        die "Python conversion failed."
    fi
}

main "$@"
