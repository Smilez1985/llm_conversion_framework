#!/bin/bash
# build.sh for Rockchip
# Manually created / Template instantiated
# Handles dispatching between RK3588 (RKLLM), RK3566 (RKNN) and CPU Fallback.

set -euo pipefail

WORK_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${WORK_DIR}/output"
mkdir -p "$OUTPUT_DIR"

TASK="${MODEL_TASK:-LLM}"
BOARD="${TARGET_BOARD:-rk3566}" 
QUANT="${QUANTIZATION:-FP16}"

echo "=== Rockchip Build Dispatcher ==="
echo "Target Board: $BOARD"
echo "Task Type:    $TASK"
echo "Quantization: $QUANT"

# --- DISPATCH LOGIC ---

# 1. CPU Fallback Check (User requested FP16/Original)
if [[ "$QUANT" == "FP16" ]] || [[ "$QUANT" == *"Original"* ]]; then
    echo ">> Strategy: User requested FP16/Original. Skipping NPU quantization."
    echo ">> Fallback to CPU conversion (GGUF F16)."
    
    # Standard GGUF Conversion (Safe Fallback)
    python3 /usr/src/llama.cpp/convert-hf-to-gguf.py "$MODEL_SOURCE" --outfile "$OUTPUT_DIR/model-f16.gguf" --outtype f16
    exit 0
fi

# 2. Hardware Specific Dispatch
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
        # Auto-Quantize to Q8_0 or chosen quant if supported by llama.cpp
        # Map RKNN quants (i8) to GGUF quants (q8_0) if needed
        GGUF_TYPE="q8_0" # Default for CPU inference
        if [[ "$QUANT" == "Q4"* ]]; then GGUF_TYPE="q4_k_m"; fi
        
        python3 /usr/src/llama.cpp/convert-hf-to-gguf.py "$MODEL_SOURCE" --outfile "$OUTPUT_DIR/model.gguf" --outtype "$GGUF_TYPE"
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
