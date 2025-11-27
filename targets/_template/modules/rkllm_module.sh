#!/bin/bash
# rkllm_module.sh - RKLLM Toolkit Execution Module
# Optimized for RK3588/RK3576 NPU LLM Acceleration
# Part of LLM Cross-Compiler Framework

set -euo pipefail

# Environment Variables
# $MODEL_SOURCE: Path to HuggingFace model directory (safetensors)
# $QUANTIZATION: Target quantization (w8a8, w4a16)
# $RKLLM_TOOLKIT_REPO_OVERRIDE: URL from SSOT
# $OUTPUT_DIR: Final artifact destination

# Defaults
RKLLM_DIR="/app/rknn-llm"
BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"

log() { echo ">> [RKLLM] $1"; }

main() {
    log "Starting RKLLM Pipeline..."
    
    # 1. Check & Setup Toolkit
    if [ ! -d "$RKLLM_DIR" ]; then
        log "Cloning RKLLM Toolkit..."
        git clone "${RKLLM_TOOLKIT_REPO_OVERRIDE:-https://github.com/airockchip/rknn-llm.git}" "$RKLLM_DIR"
    else
        log "Using existing RKLLM Toolkit at $RKLLM_DIR"
    fi

    # 2. Determine Conversion Type
    # Mapped from Framework Quantization types to RKLLM types
    case "${QUANTIZATION:-w8a8}" in
        "w8a8"|"W8A8"|"INT8"|"Q8_0")
            Q_TYPE="w8a8"
            ;;
        "w4a16"|"W4A16"|"INT4"|"Q4_K_M")
            Q_TYPE="w4a16"
            ;;
        *)
            log "Warning: Unknown quantization '$QUANTIZATION'. Defaulting to w8a8."
            Q_TYPE="w8a8"
            ;;
    esac

    log "Target Platform: rk3588 (Hardcoded for RKLLM Module)"
    log "Quantization:    $Q_TYPE"
    log "Model Source:    $MODEL_SOURCE"

    # 3. Execution
    # NOTE: RKLLM structure changes often. This assumes the standard python export script structure.
    # We use a wrapper python script or call the module directly if available.
    
    # Create a temporary conversion script to handle the python API
    cat <<EOF > convert_rkllm.py
import sys
from rkllm.api import RKLLM

model_path = "$MODEL_SOURCE"
save_path = "$OUTPUT_DIR/model-$Q_TYPE.rkllm"
q_type = "$Q_TYPE"
target = "rk3588"

print(f"Loading model from {model_path}...")
llm = RKLLM()

ret = llm.load_huggingface(model=model_path)
if ret != 0:
    print("Load failed!")
    sys.exit(1)

print(f"Building for {target} with {q_type}...")
ret = llm.build(
    do_quantization=True,
    optimization_level=1,
    quantized_dtype=q_type,
    target_platform=target
)
if ret != 0:
    print("Build failed!")
    sys.exit(1)

print(f"Exporting to {save_path}...")
ret = llm.export_rkllm(save_path)
if ret != 0:
    print("Export failed!")
    sys.exit(1)
    
print("RKLLM Conversion Success!")
EOF

    # Run the python script
    python3 convert_rkllm.py
    
    # Cleanup
    rm convert_rkllm.py
    
    log "RKLLM Pipeline Finished."
}

main "$@"
