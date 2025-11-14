#!/bin/bash
# entrypoint.sh - LLM Cross-Compiler Framework Container Entry Point
# DIREKTIVE: Goldstandard, robust, professionell geschrieben

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

readonly SCRIPT_NAME="entrypoint.sh"
readonly SCRIPT_VERSION="1.0.0"
readonly FRAMEWORK_VERSION="1.0.0"

# Environment defaults
export BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
export LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-/usr/src/llama.cpp}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export DEBUG="${DEBUG:-0}"

# ============================================================================
# LOGGING
# ============================================================================

log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [ENTRYPOINT] [$level] $message" >&2
}

log_info() { [[ "$LOG_LEVEL" != "ERROR" ]] && log "INFO" "$1"; }
log_warn() { log "WARN" "$1"; }
log_error() { log "ERROR" "$1"; }
log_success() { log "SUCCESS" "$1"; }

# ============================================================================
# CONTAINER INITIALIZATION
# ============================================================================

print_banner() {
    cat << 'EOF'
╔══════════════════════════════════════════════════════════════╗
║               LLM Cross-Compiler Framework                   ║
║                   Rockchip Container                         ║
╠══════════════════════════════════════════════════════════════╣
║  Target: RK3566, RK3568, RK3576, RK3588                     ║
║  Modules: source → config → convert → target                 ║
║  Architecture: AArch64 Cross-Compilation                     ║
╚══════════════════════════════════════════════════════════════╝
EOF
}

initialize_container() {
    log_info "Initializing LLM Cross-Compiler Framework Container"
    log_info "Framework Version: $FRAMEWORK_VERSION"
    log_info "Container User: $(whoami)"
    log_info "Working Directory: $(pwd)"
    log_info "Build Cache: $BUILD_CACHE_DIR"
    
    # Verify container environment
    verify_environment
    
    # Setup build cache permissions
    setup_build_cache
    
    # Validate framework modules
    validate_framework_modules
    
    log_success "Container initialization completed"
}

verify_environment() {
    log_info "Verifying container environment"
    
    # Check Python installation
    if ! python3 --version >/dev/null 2>&1; then
        log_error "Python3 not available"
        exit 1
    fi
    
    # Check critical Python modules
    local required_modules=("torch" "transformers" "numpy")
    for module in "${required_modules[@]}"; do
        if ! python3 -c "import $module" 2>/dev/null; then
            log_error "Required Python module not available: $module"
            exit 1
        fi
    done
    
    # Check cross-compilation toolchain
    if ! aarch64-linux-gnu-gcc --version >/dev/null 2>&1; then
        log_error "AArch64 cross-compiler not available"
        exit 1
    fi
    
    # Check llama.cpp installation
    if [[ ! -d "$LLAMA_CPP_PATH" ]]; then
        log_error "llama.cpp not found at: $LLAMA_CPP_PATH"
        exit 1
    fi
    
    # Check llama.cpp tools
    local llama_tools=("llama-quantize" "llama-cli")
    for tool in "${llama_tools[@]}"; do
        if [[ ! -f "$LLAMA_CPP_PATH/$tool" ]]; then
            log_error "llama.cpp tool not found: $tool"
            exit 1
        fi
    done
    
    log_success "Environment verification completed"
}

setup_build_cache() {
    log_info "Setting up build cache directory"
    
    # Create subdirectories if they don't exist
    local cache_dirs=(
        "$BUILD_CACHE_DIR/models"
        "$BUILD_CACHE_DIR/temp"
        "$BUILD_CACHE_DIR/output"
        "$BUILD_CACHE_DIR/logs"
        "$BUILD_CACHE_DIR/toolchains"
        "$BUILD_CACHE_DIR/packages"
    )
    
    for dir in "${cache_dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            log_info "Created cache directory: $(basename "$dir")"
        fi
    done
    
    # Verify write permissions
    local test_file="$BUILD_CACHE_DIR/.write_test"
    if ! touch "$test_file" 2>/dev/null; then
        log_error "No write permission for build cache: $BUILD_CACHE_DIR"
        exit 1
    fi
    rm -f "$test_file"
    
    log_success "Build cache setup completed"
}

validate_framework_modules() {
    log_info "Validating framework modules"
    
    local modules=("source_module.sh" "config_module.sh" "convert_module.sh" "target_module.sh")
    local modules_dir="/app/modules"
    
    for module in "${modules[@]}"; do
        local module_path="$modules_dir/$module"
        if [[ ! -f "$module_path" ]]; then
            log_error "Framework module not found: $module"
            exit 1
        fi
        
        if [[ ! -x "$module_path" ]]; then
            log_error "Framework module not executable: $module"
            exit 1
        fi
    done
    
    log_success "Framework modules validated"
}

# ============================================================================
# RUNTIME MODES
# ============================================================================

run_pipeline() {
    local input_path="$1"
    local model_name="$2"
    local quant_method="${3:-Q4_K_M}"
    local hardware_config="${4:-}"
    
    log_info "Starting LLM cross-compilation pipeline"
    log_info "Input: $input_path"
    log_info "Model: $model_name"
    log_info "Quantization: $quant_method"
    
    # Set up environment for modules
    export MODEL_NAME="$model_name"
    export QUANT_METHOD="$quant_method"
    export INPUT_PATH="$input_path"
    
    if [[ -n "$hardware_config" ]] && [[ -f "$hardware_config" ]]; then
        export HARDWARE_CONFIG_FILE="$hardware_config"
    fi
    
    local start_time=$SECONDS
    
    # Execute the 4-module pipeline
    log_info "Stage 1/4: Environment Setup"
    /app/modules/source_module.sh
    
    log_info "Stage 2/4: Hardware Configuration"
    /app/modules/config_module.sh
    
    log_info "Stage 3/4: Model Conversion"
    /app/modules/convert_module.sh --input "$input_path" --model-name "$model_name"
    
    log_info "Stage 4/4: Quantization & Packaging"
    local gguf_file="$BUILD_CACHE_DIR/output/${model_name}.fp16.gguf"
    /app/modules/target_module.sh --input "$gguf_file" --quantization "$quant_method" --model-name "$model_name"
    
    local total_time=$((SECONDS - start_time))
    
    log_success "Pipeline completed in ${total_time} seconds"
    log_info "Output available in: $BUILD_CACHE_DIR/output/packages"
}

run_module() {
    local module_name="$1"
    shift
    local module_args=("$@")
    
    log_info "Running individual module: $module_name"
    
    local module_path="/app/modules/${module_name}_module.sh"
    if [[ ! -f "$module_path" ]]; then
        log_error "Module not found: $module_name"
        exit 1
    fi
    
    "$module_path" "${module_args[@]}"
}

run_interactive() {
    log_info "Starting interactive mode"
    
    cat << 'EOF'

🚀 LLM Cross-Compiler Framework - Interactive Mode

Available commands:
  pipeline <input> <model-name> [quantization] [hardware-config] - Run full pipeline
  source [args]                                                  - Run source module
  config [args]                                                  - Run config module  
  convert [args]                                                 - Run convert module
  target [args]                                                  - Run target module
  test                                                           - Run system tests
  status                                                         - Show system status
  help                                                           - Show this help
  exit                                                           - Exit container

EOF
    
    while true; do
        echo -n "llm-framework> "
        read -r command args
        
        case "$command" in
            "pipeline")
                IFS=' ' read -ra ADDR <<< "$args"
                if [[ ${#ADDR[@]} -ge 2 ]]; then
                    run_pipeline "${ADDR[@]}"
                else
                    echo "Usage: pipeline <input> <model-name> [quantization] [hardware-config]"
                fi
                ;;
            "source"|"config"|"convert"|"target")
                IFS=' ' read -ra ADDR <<< "$args"
                run_module "$command" "${ADDR[@]}"
                ;;
            "test")
                run_system_tests
                ;;
            "status")
                show_system_status
                ;;
            "help")
                echo "Available commands: pipeline, source, config, convert, target, test, status, help, exit"
                ;;
            "exit")
                log_info "Exiting interactive mode"
                break
                ;;
            "")
                continue
                ;;
            *)
                echo "Unknown command: $command (type 'help' for available commands)"
                ;;
        esac
    done
}

run_system_tests() {
    log_info "Running system tests"
    
    # Test Python environment
    log_info "Testing Python environment..."
    python3 -c "import torch, transformers, numpy; print('✅ Python environment OK')"
    
    # Test cross-compiler
    log_info "Testing cross-compiler..."
    echo 'int main(){return 0;}' | aarch64-linux-gnu-gcc -x c - -o /tmp/test_cross
    if [[ -f /tmp/test_cross ]]; then
        echo "✅ Cross-compiler OK"
        rm -f /tmp/test_cross
    fi
    
    # Test llama.cpp tools
    log_info "Testing llama.cpp tools..."
    if "$LLAMA_CPP_PATH/llama-quantize" --help >/dev/null 2>&1; then
        echo "✅ llama-quantize OK"
    fi
    
    if "$LLAMA_CPP_PATH/llama-cli" --help >/dev/null 2>&1; then
        echo "✅ llama-cli OK"
    fi
    
    if python3 "$LLAMA_CPP_PATH/convert_hf_to_gguf.py" --help >/dev/null 2>&1; then
        echo "✅ convert script OK"
    fi
    
    log_success "System tests completed"
}

show_system_status() {
    echo "=== SYSTEM STATUS ==="
    echo "Framework Version: $FRAMEWORK_VERSION"
    echo "Python Version: $(python3 --version)"
    echo "PyTorch Version: $(python3 -c 'import torch; print(torch.__version__)')"
    echo "Transformers Version: $(python3 -c 'import transformers; print(transformers.__version__)')"
    echo "Cross-Compiler: $(aarch64-linux-gnu-gcc --version | head -1)"
    echo "Build Cache: $BUILD_CACHE_DIR"
    echo "Available Space: $(df -h $BUILD_CACHE_DIR | tail -1 | awk '{print $4}')"
    echo "====================="
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    # Show banner
    print_banner
    
    # Initialize container
    initialize_container
    
    # Parse command line arguments
    case "${1:-interactive}" in
        "pipeline")
            shift
            if [[ $# -ge 2 ]]; then
                run_pipeline "$@"
            else
                log_error "Usage: pipeline <input> <model-name> [quantization] [hardware-config]"
                exit 1
            fi
            ;;
        "source"|"config"|"convert"|"target")
            local module="$1"
            shift
            run_module "$module" "$@"
            ;;
        "test")
            run_system_tests
            ;;
        "status")
            show_system_status
            ;;
        "interactive"|"bash")
            if [[ "${1:-}" == "bash" ]]; then
                exec bash
            else
                run_interactive
            fi
            ;;
        "help"|"--help")
            cat << EOF
LLM Cross-Compiler Framework - Container Entry Point

Usage:
  $0 pipeline <input> <model-name> [quantization] [hardware-config]
  $0 <module> [args]    - Run individual module (source, config, convert, target)
  $0 test               - Run system tests
  $0 status             - Show system status
  $0 interactive        - Start interactive mode (default)
  $0 bash               - Start bash shell
  $0 help               - Show this help

Examples:
  $0 pipeline /models/granite-h-350m granite-h-350m Q4_K_M
  $0 convert --input /models/granite-h-350m --model-name granite
  $0 test
EOF
            ;;
        *)
            log_error "Unknown command: $1"
            log_error "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main