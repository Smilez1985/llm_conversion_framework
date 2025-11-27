#!/bin/bash
# rkllm_module.sh - RKLLM Toolkit Execution Module
# Optimized for RK3588/RK3576 NPU LLM Acceleration
# Part of LLM Cross-Compiler Framework

set -euo pipefail

# Environment
# $MODEL_SOURCE: Path to HuggingFace model
# $QUANTIZATION: w8a8, w4a16
# $RKLLM_TOOLKIT_REPO_OVERRIDE: URL from SSOT

RKLLM_DIR="/app/rknn-llm"
BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"

log() { echo ">> [RKLLM] $1"; }
die() { echo "❌ [RKLLM] $1" >&2; exit 1; }

main() {
    log "Starting RKLLM Pipeline..."
    
    # 1. Setup
    if [ ! -d "$RKLLM_DIR" ]; then
        log "Cloning RKLLM Toolkit..."
        REPO="${RKLLM_TOOLKIT_REPO_OVERRIDE:-https://github.com/airockchip/rknn-llm.git}"
        git clone "$REPO" "$RKLLM_DIR" || die "Clone failed"
    fi

    # 2. Quant Type
    case "${QUANTIZATION:-w8a8}" in
        "w8a8"|"W8A8"|"INT8") Q_TYPE="w8a8";;
        "w4a16"|"W4A16"|"INT4") Q_TYPE="w4a16";;
        *) log "Warning: Unknown quant '$QUANTIZATION', defaulting w8a8"; Q_TYPE="w8a8";;
    esac

    TARGET="rk3588"
    RKLLM_OUT="$OUTPUT_DIR/model-${TARGET}-${Q_TYPE}.rkllm"

    # 3. Python Script Generation
    CONVERT_SCRIPT="$BUILD_CACHE_DIR/convert_rkllm.py"
    
    cat <<EOF > "$CONVERT_SCRIPT"
import sys
from rkllm.api import RKLLM

llm = RKLLM()

print(f"Loading HF Model: $MODEL_SOURCE")
ret = llm.load_huggingface(model='$MODEL_SOURCE')
if ret != 0: sys.exit(1)

print(f"Building for $TARGET with $Q_TYPE...")
ret = llm.build(
    do_quantization=True,
    optimization_level=1,
    quantized_dtype='$Q_TYPE',
    target_platform='$TARGET'
)
if ret != 0: sys.exit(1)

print(f"Exporting to $RKLLM_OUT...")
ret = llm.export_rkllm('$RKLLM_OUT')
if ret != 0: sys.exit(1)
EOF

    # 4. Run
    log "Running conversion..."
    python3 "$CONVERT_SCRIPT" || die "Conversion failed"
    
    rm -f "$CONVERT_SCRIPT"
    
    if [ -f "$RKLLM_OUT" ]; then
        log "Success: $RKLLM_OUT"
    else
        die "Output missing"
    fi
}

main "$@"
