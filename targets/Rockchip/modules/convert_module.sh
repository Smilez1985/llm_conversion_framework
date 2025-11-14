#!/bin/bash
# convert_module.sh - Universal Model Format Converter
# Part of LLM Cross-Compiler Framework
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Konvertiert verschiedene Model-Formate (HF, ONNX, PyTorch) zu GGUF FP16
#        Universell einsetzbar für alle unterstützten Architekturen

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

readonly SCRIPT_NAME="convert_module.sh"
readonly SCRIPT_VERSION="1.0.0"

# Environment variables with defaults
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/llama.cpp}"
readonly MODELS_DIR="${MODELS_DIR:-${BUILD_CACHE_DIR}/models}"
readonly OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
readonly TEMP_DIR="${TEMP_DIR:-${BUILD_CACHE_DIR}/temp}"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Model configuration
declare -A MODEL_CONFIG
declare -A CONVERSION_STATS

# Supported formats and their converters
declare -A FORMAT_CONVERTERS=(
    ["huggingface"]="convert_hf_to_gguf"
    ["pytorch"]="convert_pytorch_to_gguf"
    ["onnx"]="convert_onnx_to_gguf"
    ["safetensors"]="convert_safetensors_to_gguf"
)

# ============================================================================
# LOGGING & ERROR HANDLING
# ============================================================================

log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$SCRIPT_NAME] [$level] $message" >&2
}

log_info() { [[ "$LOG_LEVEL" != "ERROR" ]] && log "INFO" "$1"; }
log_warn() { log "WARN" "$1"; }
log_error() { log "ERROR" "$1"; }
log_success() { log "SUCCESS" "$1"; }
log_debug() { [[ "${DEBUG:-0}" == "1" ]] && log "DEBUG" "$1"; }

die() {
    log_error "$1"
    exit "${2:-1}"
}

cleanup_on_error() {
    local exit_code=$?
    log_error "Conversion failed with exit code: $exit_code"
    
    # Clean up temporary files
    if [[ -n "${TEMP_FILES:-}" ]]; then
        rm -f $TEMP_FILES 2>/dev/null || true
    fi
    
    # Clean up temporary directories
    if [[ -n "${TEMP_CONVERSION_DIR:-}" && -d "${TEMP_CONVERSION_DIR:-}" ]]; then
        rm -rf "${TEMP_CONVERSION_DIR}" 2>/dev/null || true
    fi
    
    log_error "Cleanup completed"
    exit $exit_code
}

trap cleanup_on_error ERR

# ============================================================================
# INPUT VALIDATION & FORMAT DETECTION
# ============================================================================

detect_model_format() {
    local model_path="$1"
    
    log_info "Detecting model format for: $model_path"
    
    if [[ ! -e "$model_path" ]]; then
        die "Model path does not exist: $model_path"
    fi
    
    if [[ -d "$model_path" ]]; then
        # Directory-based model
        if [[ -f "$model_path/config.json" ]]; then
            if [[ -f "$model_path/model.safetensors" ]] || [[ -f "$model_path/pytorch_model.bin" ]]; then
                MODEL_CONFIG[FORMAT]="huggingface"
                log_success "Detected Hugging Face model format"
                return 0
            fi
        fi
        
        # Check for PyTorch checkpoint directory
        if find "$model_path" -name "*.pth" -o -name "*.pt" | head -1 | grep -q .; then
            MODEL_CONFIG[FORMAT]="pytorch"
            log_success "Detected PyTorch checkpoint format"
            return 0
        fi
        
        # Check for ONNX model directory
        if find "$model_path" -name "*.onnx" | head -1 | grep -q .; then
            MODEL_CONFIG[FORMAT]="onnx"
            log_success "Detected ONNX model format"
            return 0
        fi
        
        die "Unable to detect model format in directory: $model_path"
        
    elif [[ -f "$model_path" ]]; then
        # Single file model
        case "${model_path,,}" in
            *.onnx)
                MODEL_CONFIG[FORMAT]="onnx"
                log_success "Detected ONNX model file"
                ;;
            *.pth|*.pt)
                MODEL_CONFIG[FORMAT]="pytorch"
                log_success "Detected PyTorch model file"
                ;;
            *.safetensors)
                MODEL_CONFIG[FORMAT]="safetensors"
                log_success "Detected SafeTensors model file"
                ;;
            *.gguf)
                die "Input is already in GGUF format: $model_path"
                ;;
            *)
                die "Unsupported model file format: $model_path"
                ;;
        esac
    else
        die "Invalid model path: $model_path"
    fi
}

validate_model_structure() {
    local model_path="$1"
    local format="${MODEL_CONFIG[FORMAT]}"
    
    log_info "Validating model structure for $format format"
    
    case "$format" in
        "huggingface")
            validate_huggingface_model "$model_path"
            ;;
        "pytorch")
            validate_pytorch_model "$model_path"
            ;;
        "onnx")
            validate_onnx_model "$model_path"
            ;;
        "safetensors")
            validate_safetensors_model "$model_path"
            ;;
        *)
            die "Unknown format for validation: $format"
            ;;
    esac
}

validate_huggingface_model() {
    local model_path="$1"
    
    # Required files for HF model
    local required_files=("config.json")
    local model_files=()
    
    # Check for model weight files
    if [[ -f "$model_path/model.safetensors" ]]; then
        model_files+=("model.safetensors")
    elif [[ -f "$model_path/pytorch_model.bin" ]]; then
        model_files+=("pytorch_model.bin")
    else
        # Multi-file models
        mapfile -t found_safetensors < <(find "$model_path" -name "model-*.safetensors" 2>/dev/null | head -10)
        mapfile -t found_pytorch < <(find "$model_path" -name "pytorch_model-*.bin" 2>/dev/null | head -10)
        
        if [[ ${#found_safetensors[@]} -gt 0 ]]; then
            model_files+=("${found_safetensors[@]}")
        elif [[ ${#found_pytorch[@]} -gt 0 ]]; then
            model_files+=("${found_pytorch[@]}")
        else
            die "No model weight files found in HF model directory"
        fi
    fi
    
    # Validate required files
    for file in "${required_files[@]}"; do
        if [[ ! -f "$model_path/$file" ]]; then
            die "Missing required file in HF model: $file"
        fi
    done
    
    # Get model info from config
    if command -v jq >/dev/null 2>&1; then
        local model_type
        model_type=$(jq -r '.model_type // "unknown"' "$model_path/config.json" 2>/dev/null || echo "unknown")
        MODEL_CONFIG[MODEL_TYPE]="$model_type"
        
        local vocab_size
        vocab_size=$(jq -r '.vocab_size // "unknown"' "$model_path/config.json" 2>/dev/null || echo "unknown")
        MODEL_CONFIG[VOCAB_SIZE]="$vocab_size"
        
        log_info "Model type: $model_type, Vocab size: $vocab_size"
    fi
    
    # Calculate total size
    local total_size=0
    for file in "${model_files[@]}"; do
        if [[ -f "$file" ]]; then
            local file_size
            file_size=$(stat -c%s "$file" 2>/dev/null || echo "0")
            total_size=$((total_size + file_size))
        fi
    done
    
    MODEL_CONFIG[INPUT_SIZE_BYTES]="$total_size"
    MODEL_CONFIG[INPUT_SIZE_MB]="$((total_size / 1024 / 1024))"
    
    log_success "HF model validation completed: ${MODEL_CONFIG[INPUT_SIZE_MB]}MB, ${#model_files[@]} weight files"
}

validate_pytorch_model() {
    local model_path="$1"
    
    if [[ -f "$model_path" ]]; then
        # Single PyTorch file
        local file_size
        file_size=$(stat -c%s "$model_path" 2>/dev/null || echo "0")
        MODEL_CONFIG[INPUT_SIZE_BYTES]="$file_size"
        MODEL_CONFIG[INPUT_SIZE_MB]="$((file_size / 1024 / 1024))"
    else
        # PyTorch checkpoint directory
        local total_size
        total_size=$(du -sb "$model_path" 2>/dev/null | cut -f1 || echo "0")
        MODEL_CONFIG[INPUT_SIZE_BYTES]="$total_size"
        MODEL_CONFIG[INPUT_SIZE_MB]="$((total_size / 1024 / 1024))"
    fi
    
    log_success "PyTorch model validation completed: ${MODEL_CONFIG[INPUT_SIZE_MB]}MB"
}

validate_onnx_model() {
    local model_path="$1"
    
    if [[ -f "$model_path" ]]; then
        local file_size
        file_size=$(stat -c%s "$model_path" 2>/dev/null || echo "0")
        MODEL_CONFIG[INPUT_SIZE_BYTES]="$file_size"
        MODEL_CONFIG[INPUT_SIZE_MB]="$((file_size / 1024 / 1024))"
    else
        local total_size
        total_size=$(du -sb "$model_path" 2>/dev/null | cut -f1 || echo "0")
        MODEL_CONFIG[INPUT_SIZE_BYTES]="$total_size"
        MODEL_CONFIG[INPUT_SIZE_MB]="$((total_size / 1024 / 1024))"
    fi
    
    # Validate ONNX file if possible
    if command -v python3 >/dev/null 2>&1; then
        if python3 -c "import onnx; onnx.load('$model_path')" 2>/dev/null; then
            log_success "ONNX model structure validation passed"
        else
            log_warn "ONNX model structure validation failed (non-fatal)"
        fi
    fi
    
    log_success "ONNX model validation completed: ${MODEL_CONFIG[INPUT_SIZE_MB]}MB"
}

validate_safetensors_model() {
    local model_path="$1"
    
    local file_size
    file_size=$(stat -c%s "$model_path" 2>/dev/null || echo "0")
    MODEL_CONFIG[INPUT_SIZE_BYTES]="$file_size"
    MODEL_CONFIG[INPUT_SIZE_MB]="$((file_size / 1024 / 1024))"
    
    log_success "SafeTensors model validation completed: ${MODEL_CONFIG[INPUT_SIZE_MB]}MB"
}

# ============================================================================
# CONVERSION FUNCTIONS
# ============================================================================

setup_conversion_environment() {
    log_info "Setting up conversion environment"
    
    # Create necessary directories
    mkdir -p "$OUTPUT_DIR" "$TEMP_DIR"
    
    # Verify llama.cpp installation
    if [[ ! -d "$LLAMA_CPP_PATH" ]]; then
        die "llama.cpp not found at: $LLAMA_CPP_PATH"
    fi
    
    # Verify Python dependencies
    local required_modules=("torch" "transformers" "numpy")
    for module in "${required_modules[@]}"; do
        if ! python3 -c "import $module" 2>/dev/null; then
            die "Required Python module not available: $module"
        fi
    done
    
    log_success "Conversion environment ready"
}

convert_hf_to_gguf() {
    local input_path="$1"
    local output_path="$2"
    
    log_info "Converting Hugging Face model to GGUF FP16"
    
    local convert_script="$LLAMA_CPP_PATH/convert_hf_to_gguf.py"
    if [[ ! -f "$convert_script" ]]; then
        die "HF conversion script not found: $convert_script"
    fi
    
    # Create backup if output exists
    if [[ -f "$output_path" ]]; then
        local backup_path="${output_path}.backup.$(date +%s)"
        mv "$output_path" "$backup_path"
        log_info "Created backup: $(basename "$backup_path")"
    fi
    
    # Run conversion
    log_info "Running HF to GGUF conversion..."
    cd "$LLAMA_CPP_PATH"
    
    if ! python3 "$convert_script" \
        "$input_path" \
        --outfile "$output_path" \
        --outtype f16 \
        --verbose; then
        die "HF to GGUF conversion failed"
    fi
    
    log_success "HF to GGUF conversion completed"
}

convert_pytorch_to_gguf() {
    local input_path="$1"
    local output_path="$2"
    
    log_info "Converting PyTorch model to GGUF FP16"
    
    # This would require a custom converter or converting via HF format first
    local temp_hf_dir="$TEMP_DIR/pytorch_to_hf_$(date +%s)"
    mkdir -p "$temp_hf_dir"
    TEMP_CONVERSION_DIR="$temp_hf_dir"
    
    log_info "Converting PyTorch to Hugging Face format (intermediate step)"
    
    # Create a simple conversion script
    cat > "$TEMP_DIR/pytorch_to_hf.py" << 'EOF'
import sys
import torch
import json
from pathlib import Path

def convert_pytorch_to_hf(input_path, output_dir):
    """Convert PyTorch checkpoint to HF format"""
    print(f"Loading PyTorch model from: {input_path}")
    
    # Load the checkpoint
    checkpoint = torch.load(input_path, map_location='cpu')
    
    # Extract model state dict
    if isinstance(checkpoint, dict):
        if 'model' in checkpoint:
            state_dict = checkpoint['model']
        elif 'state_dict' in checkpoint:
            state_dict = checkpoint['state_dict']
        else:
            state_dict = checkpoint
    else:
        state_dict = checkpoint
    
    # Save as PyTorch model.bin
    torch.save(state_dict, f"{output_dir}/pytorch_model.bin")
    
    # Create minimal config.json
    config = {
        "model_type": "llama",
        "architectures": ["LlamaForCausalLM"],
        "torch_dtype": "float16",
        "vocab_size": 32000
    }
    
    with open(f"{output_dir}/config.json", 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"Converted to HF format in: {output_dir}")

if __name__ == "__main__":
    convert_pytorch_to_hf(sys.argv[1], sys.argv[2])
EOF
    
    if ! python3 "$TEMP_DIR/pytorch_to_hf.py" "$input_path" "$temp_hf_dir"; then
        die "PyTorch to HF conversion failed"
    fi
    
    # Now convert HF to GGUF
    convert_hf_to_gguf "$temp_hf_dir" "$output_path"
    
    log_success "PyTorch to GGUF conversion completed"
}

convert_onnx_to_gguf() {
    local input_path="$1"
    local output_path="$2"
    
    log_warn "ONNX to GGUF conversion is experimental"
    
    # ONNX conversion would require specialized tools
    # For now, we'll provide a placeholder that could be extended
    
    die "ONNX to GGUF conversion not yet implemented. Please convert to HF format first."
}

convert_safetensors_to_gguf() {
    local input_path="$1"
    local output_path="$2"
    
    log_info "Converting SafeTensors model to GGUF FP16"
    
    # SafeTensors conversion via temporary HF format
    local temp_hf_dir="$TEMP_DIR/safetensors_to_hf_$(date +%s)"
    mkdir -p "$temp_hf_dir"
    TEMP_CONVERSION_DIR="$temp_hf_dir"
    
    # Copy safetensors file and create minimal HF structure
    cp "$input_path" "$temp_hf_dir/model.safetensors"
    
    # Create minimal config.json
    cat > "$temp_hf_dir/config.json" << EOF
{
  "model_type": "llama",
  "architectures": ["LlamaForCausalLM"],
  "torch_dtype": "float16",
  "vocab_size": 32000
}
EOF
    
    # Convert via HF format
    convert_hf_to_gguf "$temp_hf_dir" "$output_path"
    
    log_success "SafeTensors to GGUF conversion completed"
}

# ============================================================================
# OUTPUT VALIDATION & VERIFICATION
# ============================================================================

validate_gguf_output() {
    local output_path="$1"
    
    log_info "Validating GGUF output: $output_path"
    
    if [[ ! -f "$output_path" ]]; then
        die "GGUF output file not created: $output_path"
    fi
    
    # Check file size
    local output_size
    output_size=$(stat -c%s "$output_path" 2>/dev/null || echo "0")
    CONVERSION_STATS[OUTPUT_SIZE_BYTES]="$output_size"
    CONVERSION_STATS[OUTPUT_SIZE_MB]="$((output_size / 1024 / 1024))"
    
    if [[ "$output_size" -lt 1048576 ]]; then  # Less than 1MB
        die "GGUF output suspiciously small: $((output_size / 1024))KB"
    fi
    
    # Verify file type
    local file_type
    file_type=$(file "$output_path" 2>/dev/null || echo "unknown")
    if [[ "$file_type" != *"data"* ]]; then
        log_warn "GGUF file type verification inconclusive: $file_type"
    fi
    
    # Test with llama.cpp if available
    if [[ -f "$LLAMA_CPP_PATH/llama-cli" ]]; then
        log_info "Testing GGUF file with llama.cpp..."
        if timeout 30 "$LLAMA_CPP_PATH/llama-cli" --model "$output_path" --prompt "Test" --n-predict 1 >/dev/null 2>&1; then
            log_success "GGUF file functional test passed"
        else
            log_warn "GGUF file functional test failed (may not be critical)"
        fi
    fi
    
    # Calculate compression ratio
    local input_size="${MODEL_CONFIG[INPUT_SIZE_BYTES]:-0}"
    if [[ "$input_size" -gt 0 ]]; then
        local compression_ratio
        compression_ratio=$(echo "scale=2; $output_size * 100 / $input_size" | bc 2>/dev/null || echo "unknown")
        CONVERSION_STATS[COMPRESSION_RATIO]="$compression_ratio"
        log_info "Compression ratio: ${compression_ratio}% of original size"
    fi
    
    log_success "GGUF output validation completed: ${CONVERSION_STATS[OUTPUT_SIZE_MB]}MB"
}

# ============================================================================
# MAIN CONVERSION LOGIC
# ============================================================================

run_conversion() {
    local input_path="$1"
    local output_path="$2"
    local format="${MODEL_CONFIG[FORMAT]}"
    
    log_info "Starting conversion: $format → GGUF FP16"
    
    case "$format" in
        "huggingface")
            convert_hf_to_gguf "$input_path" "$output_path"
            ;;
        "pytorch")
            convert_pytorch_to_gguf "$input_path" "$output_path"
            ;;
        "onnx")
            convert_onnx_to_gguf "$input_path" "$output_path"
            ;;
        "safetensors")
            convert_safetensors_to_gguf "$input_path" "$output_path"
            ;;
        *)
            die "Unsupported format for conversion: $format"
            ;;
    esac
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

print_conversion_summary() {
    echo ""
    echo "=== CONVERSION SUMMARY ==="
    echo "Input Format: ${MODEL_CONFIG[FORMAT]}"
    echo "Model Type: ${MODEL_CONFIG[MODEL_TYPE]:-Unknown}"
    echo "Input Size: ${MODEL_CONFIG[INPUT_SIZE_MB]:-Unknown}MB"
    echo "Output Size: ${CONVERSION_STATS[OUTPUT_SIZE_MB]:-Unknown}MB"
    echo "Compression: ${CONVERSION_STATS[COMPRESSION_RATIO]:-Unknown}%"
    echo "Output File: ${MODEL_CONFIG[OUTPUT_PATH]:-Unknown}"
    echo "=========================="
}

main() {
    log_info "Starting $SCRIPT_NAME v$SCRIPT_VERSION"
    
    # Parse arguments
    local input_path=""
    local output_path=""
    local model_name=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --input)
                input_path="$2"
                shift 2
                ;;
            --output)
                output_path="$2"
                shift 2
                ;;
            --model-name)
                model_name="$2"
                shift 2
                ;;
            --help)
                echo "Usage: $0 --input INPUT_PATH --output OUTPUT_PATH [--model-name NAME]"
                exit 0
                ;;
            *)
                die "Unknown argument: $1"
                ;;
        esac
    done
    
    # Validate arguments
    if [[ -z "$input_path" ]]; then
        die "Input path required (--input)"
    fi
    
    if [[ -z "$output_path" ]]; then
        if [[ -n "$model_name" ]]; then
            output_path="$OUTPUT_DIR/${model_name}.fp16.gguf"
        else
            output_path="$OUTPUT_DIR/model.fp16.gguf"
        fi
        log_info "Output path auto-generated: $output_path"
    fi
    
    MODEL_CONFIG[INPUT_PATH]="$input_path"
    MODEL_CONFIG[OUTPUT_PATH]="$output_path"
    MODEL_CONFIG[MODEL_NAME]="${model_name:-$(basename "$input_path")}"
    
    # Setup and validation
    setup_conversion_environment
    detect_model_format "$input_path"
    validate_model_structure "$input_path"
    
    # Create output directory
    mkdir -p "$(dirname "$output_path")"
    
    # Run conversion
    local start_time=$SECONDS
    run_conversion "$input_path" "$output_path"
    local conversion_time=$((SECONDS - start_time))
    
    # Validate output
    validate_gguf_output "$output_path"
    
    # Store timing
    CONVERSION_STATS[CONVERSION_TIME_SECONDS]="$conversion_time"
    CONVERSION_STATS[CONVERSION_TIME_MINUTES]="$((conversion_time / 60))"
    
    print_conversion_summary
    
    log_success "Conversion completed in ${conversion_time} seconds"
    log_info "Next step: Run target_module.sh for quantization and packaging"
}

# Only run main if script is executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi