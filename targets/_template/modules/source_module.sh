#!/bin/bash
# source_module.sh - Environment & Tools Setup
# Part of LLM Cross-Compiler Framework
# DIREKTIVE: Goldstandard, Reproduzierbar (Pinned Commits).

set -euo pipefail

# --- CONFIGURATION & GLOBALS ---
readonly SCRIPT_NAME="source_module.sh"
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly REPO_DIR="${BUILD_CACHE_DIR}/repos"
# Default Pfad für llama.cpp (Symlink Ziel)
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/llama.cpp}"

# Quellen aus Environment (injiziert durch Orchestrator)
readonly LLAMA_CPP_REPO="${LLAMA_CPP_REPO_OVERRIDE:-https://github.com/ggerganov/llama.cpp.git}"
readonly LLAMA_CPP_COMMIT="${LLAMA_CPP_COMMIT:-b3626}" # Standard-Fallback

# --- LOGGING ---
log_info() { echo "ℹ️  [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_success() { echo "✅ [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_error() { echo "❌ [$(date '+%H:%M:%S')] [SOURCE] $1" >&2; }

ensure_repo() {
    local url="$1"
    local path="$2"
    local commit="${3:-HEAD}"

    log_info "Prüfe Repo: $(basename "$path") @ $commit"

    if [ ! -d "$path/.git" ]; then
        git clone "$url" "$path"
    else
        cd "$path"
        git fetch origin
    fi

    cd "$path"
    # Hard Reset auf den spezifischen Commit für Reproduzierbarkeit
    git checkout -f "$commit"
    git submodule update --init --recursive
}

validate_python_environment() {
    log_info "Validiere Python-Umgebung..."
    # Check critical deps
    python3 -c "import torch; import transformers; import numpy" || {
        log_error "Python Dependencies fehlen!"
        exit 1
    }
}

# --- MAIN EXECUTION ---
main() {
    local start_time=$SECONDS
    log_info "Starte Source Module (Environment Setup)..."
    
    mkdir -p "$REPO_DIR"
    mkdir -p "$BUILD_CACHE_DIR/models"
    mkdir -p "$BUILD_CACHE_DIR/output"
    
    # 1. Setup llama.cpp
    ensure_repo "$LLAMA_CPP_REPO" "$REPO_DIR/llama.cpp" "$LLAMA_CPP_COMMIT"
    
    # Symlink erstellen für Kompatibilität
    mkdir -p "$(dirname "$LLAMA_CPP_PATH")"
    ln -sf "$REPO_DIR/llama.cpp" "$LLAMA_CPP_PATH"
    
    # 2. Validate Env
    validate_python_environment
    
    local duration=$((SECONDS - start_time))
    log_success "Source Module abgeschlossen in ${duration}s"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
