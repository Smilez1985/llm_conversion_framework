#!/bin/bash
# rkllm_module.sh - RKLLM Toolkit Execution Module (Template)
# Part of LLM Cross-Compiler Framework

set -euo pipefail

# Environment & Defaults
RKLLM_DIR="/app/rknn-llm"
BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
SCRIPT_DIR="/app/scripts" 

log() { echo ">> [RKLLM] $1"; }
die() { echo "❌ [RKLLM] $1" >&2; exit 1; }

main() {
    log "Starting RKLLM Pipeline..."
    
    # 1. Toolkit Check
    if [ ! -d "$RKLLM_DIR" ]; then
        log "Cloning RKLLM Toolkit..."
        REPO_URL="${RKLLM_TOOLKIT_REPO_OVERRIDE:-[https://github.com/airockchip/rknn-llm.git](https://github.com/airockchip/rknn-llm.git)}"
        git clone "$REPO_URL" "$RKLLM_DIR" || die "Failed to clone RKLLM Toolkit"
    fi

    # 2. Parameter Normalization
    case "${QUANTIZATION:-w8a8}" in
        "w8a8"|"W8A8"|"INT8"|"Q8_0") Q_TYPE="w8a8" ;;
        "w4a16"|"W4A16"|"INT4"|"Q4_K_M") Q_TYPE="w4a16" ;;
        *) log "Warning: Unknown quantization. Defaulting to w8a8."; Q_TYPE="w8a8" ;;
    esac

    # In a template, this might need to be adjusted or detected
    TARGET_PLATFORM="rk3588"
    RKLLM_OUTPUT="$OUTPUT_DIR/model-${TARGET_PLATFORM}-${Q_TYPE}.rkllm"
    
    # 3. Execution (Clean Call)
    # Uses the clean python script from templates
    CONVERTER="$SCRIPT_DIR/export_rkllm.py"
    
    if [ ! -f "$CONVERTER" ]; then
        die "Converter script missing at $CONVERTER"
    fi
    
    log "Delegating to Python Exporter..."
    
    python3 "$CONVERTER" \
        --model "$MODEL_SOURCE" \
        --output "$RKLLM_OUTPUT" \
        --quant "$Q_TYPE" \
        --target "$TARGET_PLATFORM" || die "Python conversion failed"

    # 4. Validation
    if [ -f "$RKLLM_OUTPUT" ]; then
        SIZE=$(du -h "$RKLLM_OUTPUT" | cut -f1)
        log "Artifact created: $RKLLM_OUTPUT ($SIZE)"
    else
        die "Output file missing!"
    fi
}

main "$@"
