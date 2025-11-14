#!/bin/bash
# source_module.sh - Environment & Tools Setup
# Part of LLM Cross-Compiler Framework
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Stellt sicher, dass llama.cpp geklont und die Python-Umgebung (für Konvertierung)
#        im Docker-Container eingerichtet ist.

set -euo pipefail

# --- CONFIGURATION & GLOBALS ---
readonly SCRIPT_NAME="source_module.sh"
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/llama.cpp}"
readonly LLAMA_CPP_REPO="https://github.com/ggerganov/llama.cpp.git"
readonly LLAMA_CPP_COMMIT="${LLAMA_CPP_COMMIT:-b3626}" # Referenz aus docker-compose.yml
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"
DEBUG="${DEBUG:-0}"

# --- LOGGING ---
log_info() { echo "ℹ️  [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_success() { echo "✅ [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_warn() { echo "⚠️  [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_error() { echo "❌ [$(date '+%H:%M:%S')] [SOURCE] $1" >&2; }
log_debug() { [ "$DEBUG" = "1" ] && echo "🔍 [$(date '+%H:%M:%S')] [SOURCE] $1"; }

# --- ERROR HANDLING ---
cleanup_on_error() {
    log_error "Source-Modul fehlgeschlagen. Cleanup..."
    exit 1
}
trap cleanup_on_error ERR

# --- MAIN FUNCTIONS ---
setup_directories() {
    log_info "Erstelle Arbeitsverzeichnisse (falls nicht vorhanden)..."
    mkdir -p "$LLAMA_CPP_PATH"
    mkdir -p "$BUILD_CACHE_DIR/models"
    mkdir -p "$BUILD_CACHE_DIR/output"
}

setup_llama_cpp() {
    log_info "Richte llama.cpp Repository ein..."
    
    if [ ! -d "$LLAMA_CPP_PATH/.git" ]; then
        log_info "Klone llama.cpp (Commit: $LLAMA_CPP_COMMIT)..."
        if ! git clone "$LLAMA_CPP_REPO" "$LLAMA_CPP_PATH"; then
            log_error "llama.cpp Clone fehlgeschlagen"
            return 1
        fi
        cd "$LLAMA_CPP_PATH"
        git checkout "$LLAMA_CPP_COMMIT"
    else
        log_info "Update llama.cpp Repository..."
        cd "$LLAMA_CPP_PATH"
        git fetch
        git checkout "$LLAMA_CPP_COMMIT" || git pull origin "$LLAMA_CPP_COMMIT"
    fi
    
    git submodule update --init --recursive
    log_success "llama.cpp Repository bereit"
    return 0
}

validate_python_environment() {
    log_info "Validiere Python-Umgebung (Container-nativ)..."
    
    # Im Container-Kontext (Dockerfile) sollten diese bereits installiert sein
    local required_modules=("torch" "transformers" "numpy" "sentencepiece")
    
    for module in "${required_modules[@]}"; do
        if ! python3 -c "import $module" 2>/dev/null; then
            log_error "Fehlendes Python-Modul: $module"
            log_error "Stellen Sie sicher, dass das Docker-Image korrekt gebaut wurde."
            return 1
        fi
    done
    
    log_success "Python-Umgebung für Konvertierung validiert"
    return 0
}

# --- MAIN EXECUTION ---
main() {
    local start_time=$SECONDS
    log_info "Starte Source Module (Environment Setup)..."
    
    setup_directories
    setup_llama_cpp
    validate_python_environment
    
    local duration=$((SECONDS - start_time))
    log_success "Source Module abgeschlossen in ${duration}s"
    log_info "Nächstes Modul: config_module.sh"
}

# Nur ausführen, wenn direkt aufgerufen
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi