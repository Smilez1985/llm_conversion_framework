#!/bin/bash
# rkllm_module.sh - RKLLM Toolkit Execution Module
# Optimized for RK3588/RK3576 NPU LLM Acceleration
# Part of LLM Cross-Compiler Framework
#
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Konvertiert HuggingFace LLMs in das RKLLM-Format für die NPU.

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

# Environment Variables injected by Orchestrator/Builder
# $MODEL_SOURCE: Path to HuggingFace model directory (safetensors)
# $QUANTIZATION: Target quantization (w8a8, w4a16)
# $RKLLM_TOOLKIT_REPO_OVERRIDE: URL from SSOT
# $OUTPUT_DIR: Final artifact destination

# Defaults
RKLLM_DIR="/app/rknn-llm"
BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
# Pfad zum Python-Script innerhalb des Containers (wird dynamisch erstellt)
SCRIPT_DIR="/app/scripts"

log() { echo ">> [RKLLM] [$(date '+%H:%M:%S')] $1"; }
die() { echo "❌ [RKLLM] [$(date '+%H:%M:%S')] $1" >&2; exit 1; }

# ============================================================================
# MAIN LOGIC
# ============================================================================

main() {
    log "Starting RKLLM Pipeline..."
    
    # 1. Check & Setup Toolkit
    # ------------------------------------------------------------------------
    if [ ! -d "$RKLLM_DIR" ]; then
        log "Cloning RKLLM Toolkit..."
        # Default URL falls Variable leer (SSOT Fallback)
        REPO_URL="${RKLLM_TOOLKIT_REPO_OVERRIDE:-https://github.com/airockchip/rknn-llm.git}"
        
        if git clone "$REPO_URL" "$RKLLM_DIR"; then
            log "Clone successful."
        else
            die "Failed to clone RKLLM Toolkit form $REPO_URL"
        fi
    else
        log "Using existing RKLLM Toolkit at $RKLLM_DIR"
    fi

    # 2. Determine Conversion Type & Platform
    # ------------------------------------------------------------------------
    # Mapped from Framework Quantization types to RKLLM types
    # RK3588 supports w8a8 and w4a16 (Weight 4-bit, Activation 16-bit)
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

    TARGET_PLATFORM="rk3588" # RKLLM supports rk3588 and rk3576. Defaulting to 3588.
    
    log "Configuration:"
    log "  - Target Platform: $TARGET_PLATFORM"
    log "  - Quantization:    $Q_TYPE"
    log "  - Model Source:    $MODEL_SOURCE"
    
    if [ ! -d "$MODEL_SOURCE" ]; then
        die "Model directory not found at: $MODEL_SOURCE"
    fi

    # 3. Create Python Conversion Script
    # ------------------------------------------------------------------------
    # Wir erzeugen das Skript on-the-fly, um Versionskonflikte zu vermeiden 
    # und die Parameter direkt sauber zu injizieren.
    
    mkdir -p "$SCRIPT_DIR"
    CONVERT_SCRIPT="$SCRIPT_DIR/convert_rkllm_generated.py"
    RKLLM_OUTPUT="$OUTPUT_DIR/model-${TARGET_PLATFORM}-${Q_TYPE}.rkllm"
    
    log "Generating Python conversion script at $CONVERT_SCRIPT..."

    cat <<EOF > "$CONVERT_SCRIPT"
import sys
import os

# Ensure rknn-llm is in path if installed via pip, otherwise we might need to adjust pythonpath
# Assuming rkllm is installed in the docker container environment (pip install rkllm-toolkit)

try:
    from rkllm.api import RKLLM
except ImportError:
    print("CRITICAL ERROR: rkllm module not found.")
    print("Please ensure rkllm-toolkit is installed in the Docker container.")
    sys.exit(1)

model_path = "$MODEL_SOURCE"
save_path = "$RKLLM_OUTPUT"
q_type = "$Q_TYPE"
target = "$TARGET_PLATFORM"

print(f"Initializing RKLLM for {target}...")
llm = RKLLM()

# 1. Load Model
print(f"Loading HuggingFace model from: {model_path}")
# Note: load_huggingface expects the folder path containing config.json, etc.
ret = llm.load_huggingface(model=model_path)
if ret != 0:
    print("❌ Load failed! Return code: " + str(ret))
    sys.exit(1)

# 2. Build
print(f"Building model with quantization: {q_type}...")
# Optimization level 1 is standard
ret = llm.build(
    do_quantization=True,
    optimization_level=1,
    quantized_dtype=q_type,
    target_platform=target,
    num_npu_core=3 # RK3588 has 3 NPU cores
)
if ret != 0:
    print("❌ Build failed! Return code: " + str(ret))
    sys.exit(1)

# 3. Export
print(f"Exporting RKLLM to: {save_path}")
ret = llm.export_rkllm(save_path)
if ret != 0:
    print("❌ Export failed! Return code: " + str(ret))
    sys.exit(1)
    
print("✅ RKLLM Conversion Success!")
EOF

    # 4. Execute Python Script
    # ------------------------------------------------------------------------
    log "Running conversion process..."
    
    # Capture start time
    start_time=$(date +%s)
    
    if python3 "$CONVERT_SCRIPT"; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        log "Conversion process finished in ${duration}s."
        
        # Verify Output
        if [ -f "$RKLLM_OUTPUT" ]; then
            SIZE=$(du -h "$RKLLM_OUTPUT" | cut -f1)
            log "Artifact created successfully: $RKLLM_OUTPUT ($SIZE)"
            
            # Create Info File for Deployer / User
            INFO_FILE="$OUTPUT_DIR/model_info.json"
            echo "{" > "$INFO_FILE"
            echo "  \"framework\": \"rkllm\"," >> "$INFO_FILE"
            echo "  \"platform\": \"$TARGET_PLATFORM\"," >> "$INFO_FILE"
            echo "  \"quantization\": \"$Q_TYPE\"," >> "$INFO_FILE"
            echo "  \"created_at\": \"$(date)\"," >> "$INFO_FILE"
            echo "  \"file\": \"$(basename "$RKLLM_OUTPUT")\"" >> "$INFO_FILE"
            echo "}" >> "$INFO_FILE"
            
        else
            die "Output file missing despite success message!"
        fi
    else
        die "Python conversion script failed. Check logs above."
    fi
    
    # Cleanup
    # rm -f "$CONVERT_SCRIPT" # Optional: Keep for debugging
    
    log "RKLLM Pipeline Finished."
}

main "$@"
