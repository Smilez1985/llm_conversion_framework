#!/bin/bash
# build.sh for Rockchip
# Manually created / Template instantiated
#
# Handles dispatching between RK3588 (RKLLM) and RK3566 (CPU/RKNN)

set -euo pipefail

WORK_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${WORK_DIR}/output"
mkdir -p "$OUTPUT_DIR"

TASK="${MODEL_TASK:-LLM}"
# Orchestrator passes TARGET_BOARD often as env var, or we detect it
# For this build container, we might be building FOR a specific board passed in args
# But usually Orchestrator sets TARGET_BOARD env var if selected in GUI.
BOARD="${TARGET_BOARD:-rk3566}" 

echo "=== Rockchip Build Dispatcher ==="
echo "Target Board: $BOARD"
echo "Task Type:    $TASK"

# --- DISPATCH LOGIC ---

if [[ "$BOARD" == *"rk3588"* ]] || [[ "$BOARD" == *"RK3588"* ]]; then
    # === RK3588 (Strong NPU) ===
    if [ "$TASK" == "LLM" ]; then
        echo ">> Strategy: RK3588 detected. Using RKLLM-Toolkit."
        /app/modules/rkllm_module.sh
    else
        echo ">> Strategy: Non-LLM task ($TASK). Using RKNN-Toolkit2."
        /app/modules/rknn_module.sh
    fi

elif [[ "$BOARD" == *"rk3566"* ]] || [[ "$BOARD" == *"RK3566"* ]]; then
    # === RK3566 (Weak NPU) ===
    if [ "$TASK" == "LLM" ]; then
        echo ">> Strategy: RK3566 detected. NPU too weak for RKLLM. Fallback to CPU (llama.cpp/GGUF)."
        
        # Call standard llama.cpp conversion
        # Assuming python script is available or using llama-cpp-python
        echo "Converting to GGUF..."
        python3 /usr/src/llama.cpp/convert-hf-to-gguf.py "$MODEL_SOURCE" --outfile "$OUTPUT_DIR/model.gguf" --outtype q8_0
        
        # Optional: Quantize further if needed
        # /usr/src/llama.cpp/quantize ...
    else
        echo ">> Strategy: Voice/Vision task. Using RKNN-Toolkit2 for NPU acceleration."
        /app/modules/rknn_module.sh
    fi

else
    # === GENERIC / UNKNOWN ===
    echo ">> Unknown Rockchip Board '$BOARD'. Defaulting to CPU/GGUF."
    python3 /usr/src/llama.cpp/convert-hf-to-gguf.py "$MODEL_SOURCE" --outfile "$OUTPUT_DIR/model.gguf"
fi

# --- PACKAGING ---
echo "=== Packaging ==="
cd "$OUTPUT_DIR" && tar -czf "rockchip_deployment.tar.gz" *
echo "Done."
