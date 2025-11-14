#!/bin/bash
# convert_module.sh - Universal Model Format Converter
# Part of LLM Cross-Compiler Framework
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Konvertiert HuggingFace-Modelle zu GGUF FP16
#        (Container-nativ, nutzt Python-Umgebung aus Dockerfile)

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

readonly SCRIPT_NAME="convert_module.sh"
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/llama.cpp}"
readonly OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"
DEBUG="${DEBUG:-0}"

# --- LOGGING ---
log_info() { echo "ℹ️  [$(date '+%H:%M:%S')] [CONVERT] $1"; }
log_success() { echo "✅ [$(date '+%H:%M:%S')] [CONVERT] $1"; }
log_warn() { echo "⚠️  [$(date '+%H:%M:%S')] [CONVERT] $1"; }
log_error() { echo "❌ [$(date '+%H:%M:%S')] [CONVERT] $1" >&2; }
log_debug() { [ "$DEBUG" = "1" ] && echo "🔍 [$(date '+%H:%M:%S')] [CONVERT] $1"; }

# --- ERROR HANDLING ---
die() {
    log_error "$1"
    exit "${2:-1}"
}
trap "die 'Convert Module fehlgeschlagen'" ERR

# ============================================================================
# CONVERSION
# ============================================================================

validate_inputs() {
    if [[ -z "${MODEL_CONFIG[INPUT_PATH]}" ]]; then die "INPUT_PATH nicht gesetzt"; fi
    if [[ -z "${MODEL_CONFIG[OUTPUT_PATH]}" ]]; then die "OUTPUT_PATH nicht gesetzt"; fi
    
    if [[ ! -d "${MODEL_CONFIG[INPUT_PATH]}" ]]; then die "Input-Verzeichnis nicht gefunden: ${MODEL_CONFIG[INPUT_PATH]}"; fi
    
    if [[ ! -f "$LLAMA_CPP_PATH/convert_hf_to_gguf.py" ]]; then die "convert_hf_to_gguf.py nicht gefunden"; fi
}

run_conversion() {
    local input_path="${MODEL_CONFIG[INPUT_PATH]}"
    local output_path="${MODEL_CONFIG[OUTPUT_PATH]}"
    local model_name="${MODEL_CONFIG[MODEL_NAME]}"
    
    log_info "Starte Konvertierung: $model_name (HF -> GGUF FP16)"
    
    # Backup
    if [[ -f "$output_path" ]]; then
        mv "$output_path" "${output_path}.backup.$(date +%s)"
        log_info "Backup erstellt"
    fi
    
    cd "$LLAMA_CPP_PATH"
    
    # Starte Konvertierung
    if ! python3 convert_hf_to_gguf.py \
        "$input_path" \
        --outfile "$output_path" \
        --outtype f16 \
        --vocab-type spm \
        --verbose; then
        die "HF zu GGUF Konvertierung fehlgeschlagen"
    fi
    
    if [[ ! -f "$output_path" ]]; then die "GGUF-Datei nicht erstellt: $output_path"; fi
    
    local file_size_mb=$(du -m "$output_path" | cut -f1)
    log_success "Konvertierung erfolgreich (${file_size_mb}MB)"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================
main() {
    local start_time=$SECONDS
    log_info "Starte Convert Module (HF -> GGUF FP16)..."
    
    declare -A MODEL_CONFIG
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --input)
                MODEL_CONFIG[INPUT_PATH]="$2"
                shift 2
                ;;
            --output)
                MODEL_CONFIG[OUTPUT_PATH]="$2"
                shift 2
                ;;
            --model-name)
                MODEL_CONFIG[MODEL_NAME]="$2"
                shift 2
                ;;
            *)
                die "Unbekannter Parameter: $1"
                ;;
        esac
    done
    
    # Auto-detect defaults
    if [[ -z "${MODEL_CONFIG[INPUT_PATH]:-}" ]]; then die "Input-Pfad fehlt (--input)"; fi
    if [[ -z "${MODEL_CONFIG[MODEL_NAME]:-}" ]]; then MODEL_CONFIG[MODEL_NAME]=$(basename "${MODEL_CONFIG[INPUT_PATH]}"); fi
    if [[ -z "${MODEL_CONFIG[OUTPUT_PATH]:-}" ]]; then MODEL_CONFIG[OUTPUT_PATH]="$OUTPUT_DIR/${MODEL_CONFIG[MODEL_NAME]}.fp16.gguf"; fi
    
    validate_inputs
    run_conversion
    
    local duration=$((SECONDS - start_time))
    log_success "Convert Module abgeschlossen in ${duration}s"
    log_info "Nächstes Modul: target_module.sh"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi