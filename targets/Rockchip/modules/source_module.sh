#!/bin/bash
# source_module.sh - Environment & Tools Setup
# Part of LLM Cross-Compiler Framework
# 
# ZWECK: Zentrale Verwaltung aller Quellcodes und Repositories.
#        Nutzt injizierte Umgebungsvariablen vom Orchestrator.

set -euo pipefail

# --- CONFIGURATION & GLOBALS ---
readonly SCRIPT_NAME="source_module.sh"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Pfade
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly REPO_DIR="${BUILD_CACHE_DIR}/repos"
readonly TOOLS_DIR="${BUILD_CACHE_DIR}/tools"

# Repository URLs (Mit Injektions-Logik!)
# Wenn *_OVERRIDE gesetzt ist (durch Orchestrator/DockerManager), wird dies genutzt.
# Andernfalls Fallback auf Standard-URLs.

readonly LLAMA_CPP_REPO="${LLAMA_CPP_REPO_OVERRIDE:-https://github.com/ggerganov/llama.cpp.git}"
readonly LLAMA_CPP_COMMIT="${LLAMA_CPP_COMMIT:-b3626}"

readonly RKNN_TOOLKIT2_REPO="${RKNN_TOOLKIT2_REPO_OVERRIDE:-https://github.com/airockchip/rknn-toolkit2.git}"
readonly RKNN_MODEL_ZOO_REPO="${RKNN_MODEL_ZOO_REPO_OVERRIDE:-https://github.com/airockchip/rknn_model_zoo.git}"

# Voice Pipeline Sources
readonly VOSK_API_REPO="${VOSK_API_REPO_OVERRIDE:-https://github.com/alphacep/vosk-api.git}"
readonly PIPER_PHONEMIZE_REPO="${PIPER_PHONEMIZE_REPO_OVERRIDE:-https://github.com/rhasspy/piper-phonemize.git}"


# --- LOGGING ---
log_info() { echo "ℹ️  [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_success() { echo "✅ [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_error() { echo "❌ [$(date '+%H:%M:%S')] [SOURCE] $1" >&2; }

# --- MAIN FUNCTIONS ---

setup_directories() {
    log_info "Erstelle Verzeichnisstruktur..."
    mkdir -p "$REPO_DIR"
    mkdir -p "$TOOLS_DIR"
    mkdir -p "$BUILD_CACHE_DIR/models/onnx"
    mkdir -p "$BUILD_CACHE_DIR/output"
}

setup_llama_cpp() {
    local target_dir="$REPO_DIR/llama.cpp"
    log_info "Prüfe llama.cpp Repository..."
    log_info "URL: $LLAMA_CPP_REPO"
    
    if [ ! -d "$target_dir/.git" ]; then
        log_info "Klone llama.cpp..."
        git clone "$LLAMA_CPP_REPO" "$target_dir"
        cd "$target_dir"
        git checkout "$LLAMA_CPP_COMMIT"
    else
        log_info "Update llama.cpp..."
        cd "$target_dir"
        # Falls sich die URL geändert hat (durch Config-Wechsel), müssen wir ggf. neu aufsetzen
        # Einfachheitshalber pullen wir hier nur.
        git fetch origin
        git checkout "$LLAMA_CPP_COMMIT" || git pull origin master
    fi
    
    git submodule update --init --recursive
    log_success "llama.cpp bereit."
}

setup_rknn_toolkit() {
    local target_dir="$REPO_DIR/rknn-toolkit2"
    log_info "Prüfe RKNN-Toolkit2..."
    log_info "URL: $RKNN_TOOLKIT2_REPO"
    
    if [ ! -d "$target_dir/.git" ]; then
        git clone --depth 1 "$RKNN_TOOLKIT2_REPO" "$target_dir"
    fi
    
    # Kopiere Wheels für Deployment
    local lite_dir="$target_dir/rknn-toolkit-lite2/packages"
    if [ -d "$lite_dir" ]; then
        mkdir -p "$BUILD_CACHE_DIR/output/drivers"
        cp "$lite_dir"/*.whl "$BUILD_CACHE_DIR/output/drivers/" 2>/dev/null || true
    fi
    log_success "RKNN-Toolkit2 bereit."
}

setup_voice_dependencies() {
    local vosk_dir="$REPO_DIR/vosk-api"
    local piper_dir="$REPO_DIR/piper-phonemize"
    
    if [ ! -d "$vosk_dir/.git" ]; then
        git clone --depth 1 "$VOSK_API_REPO" "$vosk_dir"
    fi
    
    if [ ! -d "$piper_dir/.git" ]; then
        git clone --depth 1 "$PIPER_PHONEMIZE_REPO" "$piper_dir"
    fi
    log_success "Voice Dependencies bereit."
}

# --- MAIN EXECUTION ---
main() {
    local start_time=$SECONDS
    log_info "Starte Source Module..."
    
    setup_directories
    setup_llama_cpp
    setup_rknn_toolkit
    setup_voice_dependencies
    
    local duration=$((SECONDS - start_time))
    log_success "Source Module fertig in ${duration}s."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
