#!/bin/bash
# source_module.sh
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# 
# ZWECK: Environment & Tools Setup für LLM-Konvertierung
# Dieses Modul richtet die komplette Build-Umgebung ein:
# - System-Dependencies
# - VENV-Management 
# - llama.cpp Repository & Build
# - Python-Dependencies (inkl. PyTorch ARM)
#
# PARAMETER:
# --work-dir: Arbeitsverzeichnis für Build-Artefakte
# --venv-dir: VENV-Basis-Verzeichnis  
# --clean: Bereinige vorherige Builds
# --debug: Ausführlicher Debug-Output

set -euo pipefail

# --- GLOBALE VARIABLEN ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${WORK_DIR:-/tmp/llm_converter_work}"
VENV_BASE_DIR="${VENV_BASE_DIR:-${WORK_DIR}/venvs}"
LLAMA_CPP_DIR="${WORK_DIR}/repos/llama.cpp"
LLAMA_CPP_REPO="https://github.com/ggerganov/llama.cpp.git"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"
DEBUG="${DEBUG:-0}"

# VENV-Tracking
CURRENT_VENV=""
LLAMA_CPP_VENV="${VENV_BASE_DIR}/llama_cpp"

# --- LOGGING SYSTEM ---
log_info() { echo "ℹ️  [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_success() { echo "✅ [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_warning() { echo "⚠️  [$(date '+%H:%M:%S')] [SOURCE] $1"; }
log_error() { echo "❌ [$(date '+%H:%M:%S')] [SOURCE] $1" >&2; }
log_debug() { [ "$DEBUG" = "1" ] && echo "🔍 [$(date '+%H:%M:%S')] [SOURCE] $1"; }

# --- PROFESSIONAL ERROR HANDLING ---
cleanup_on_error() {
    local exit_code=$?
    log_error "Source-Modul fehlgeschlagen (Exit Code: $exit_code). Cleanup..."
    
    # Deaktiviere aktive VENV
    deactivate_current_venv 2>/dev/null || true
    
    # Cleanup temporäre Dateien
    if [ -n "${TEMP_FILES:-}" ]; then
        rm -f $TEMP_FILES 2>/dev/null || true
    fi
    
    log_error "Source-Modul Cleanup abgeschlossen"
    exit $exit_code
}
trap cleanup_on_error ERR

# --- ARGUMENT PARSING ---
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --work-dir)
                WORK_DIR="$2"
                shift 2
                ;;
            --venv-dir)
                VENV_BASE_DIR="$2"
                LLAMA_CPP_VENV="${VENV_BASE_DIR}/llama_cpp"
                shift 2
                ;;
            --clean)
                CLEAN_BUILD=1
                shift
                ;;
            --debug)
                DEBUG=1
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unbekannter Parameter: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

show_usage() {
    cat << EOF
VERWENDUNG: $0 [OPTIONEN]

OPTIONEN:
    --work-dir DIR      Arbeitsverzeichnis für Build-Artefakte (default: /tmp/llm_converter_work)
    --venv-dir DIR      VENV-Basis-Verzeichnis (default: \$WORK_DIR/venvs)
    --clean             Bereinige vorherige Builds
    --debug             Ausführlicher Debug-Output
    --help              Zeige diese Hilfe

BEISPIELE:
    $0                                  # Standard-Setup
    $0 --work-dir /build --debug       # Custom work-dir mit Debug
    $0 --clean                          # Clean Build
EOF
}

# --- PROFESSIONAL VENV MANAGEMENT ---
activate_venv() {
    local venv_path="$1"
    local venv_name=$(basename "$venv_path")
    
    if [ ! -d "$venv_path" ]; then
        log_error "VENV nicht gefunden: $venv_path"
        return 1
    fi
    
    # Deaktiviere vorherige VENV falls aktiv
    deactivate_current_venv
    
    log_debug "Aktiviere VENV: $venv_name"
    source "$venv_path/bin/activate"
    CURRENT_VENV="$venv_path"
    
    # Robuste Verifikation
    if [ -z "${VIRTUAL_ENV:-}" ] || [ "$VIRTUAL_ENV" != "$venv_path" ]; then
        log_error "VENV-Aktivierung fehlgeschlagen: $venv_path"
        return 1
    fi
    
    # Test pip in VENV
    if ! which pip | grep -q "$venv_path"; then
        log_error "pip nicht aus VENV: $(which pip)"
        return 1
    fi
    
    log_debug "VENV erfolgreich aktiv: $(basename "$VIRTUAL_ENV")"
    return 0
}

deactivate_current_venv() {
    if [ -n "$CURRENT_VENV" ] && [ -n "${VIRTUAL_ENV:-}" ]; then
        log_debug "Deaktiviere VENV: $(basename "$VIRTUAL_ENV")"
        deactivate 2>/dev/null || true
        CURRENT_VENV=""
    fi
}

create_venv() {
    local venv_path="$1"
    local venv_name=$(basename "$venv_path")
    
    if [ -d "$venv_path" ] && [ "${CLEAN_BUILD:-0}" != "1" ]; then
        log_info "VENV bereits vorhanden: $venv_name"
        return 0
    fi
    
    log_info "Erstelle VENV: $venv_name"
    rm -rf "$venv_path" 2>/dev/null || true
    mkdir -p "$(dirname "$venv_path")"
    
    if ! python3 -m venv "$venv_path"; then
        log_error "VENV-Erstellung fehlgeschlagen: $venv_path"
        return 1
    fi
    
    # Upgrade pip in new VENV
    activate_venv "$venv_path"
    pip install --upgrade pip setuptools wheel
    deactivate_current_venv
    
    log_success "VENV erstellt: $venv_name"
    return 0
}

# --- SYSTEM DEPENDENCIES MANAGEMENT ---
check_command() {
    local cmd="$1"
    if ! command -v "$cmd" &>/dev/null; then
        return 1
    fi
    return 0
}

request_sudo_if_needed() {
    if ! command -v sudo &>/dev/null; then
        log_warning "sudo nicht verfügbar"
        return 1
    fi
    
    if sudo -n true 2>/dev/null; then
        log_debug "sudo bereits verfügbar"
        return 0
    fi
    
    log_info "Sudo-Berechtigung erforderlich für Paketinstallation..."
    if sudo -v; then
        log_success "Sudo-Berechtigung erhalten"
        return 0
    else
        log_error "Sudo-Berechtigung verweigert"
        return 1
    fi
}

check_system_dependencies() {
    log_info "Prüfe System-Abhängigkeiten..."
    
    local missing_deps=()
    local required_deps=(
        "python3:python3-full"
        "python3-pip:python3-pip" 
        "python3-venv:python3-venv"
        "git:git"
        "gcc:build-essential"
        "g++:build-essential"
        "make:build-essential"
        "cmake:cmake"
        "curl:curl"
        "pkg-config:pkg-config"
        "libffi-dev:libffi-dev"
        "libssl-dev:libssl-dev"
        "libbz2-dev:libbz2-dev"
        "libreadline-dev:libreadline-dev"
        "libsqlite3-dev:libsqlite3-dev"
    )
    
    # Prüfe Commands
    for dep_spec in "${required_deps[@]}"; do
        local cmd="${dep_spec%%:*}"
        local pkg="${dep_spec##*:}"
        
        if ! check_command "$cmd"; then
            if [[ ! " ${missing_deps[@]} " =~ " $pkg " ]]; then
                missing_deps+=("$pkg")
            fi
        fi
    done
    
    # Prüfe Python-Module
    if ! python3 -c "import venv, ssl, sqlite3" 2>/dev/null; then
        missing_deps+=("python3-full" "python3-venv" "libssl-dev" "libsqlite3-dev")
    fi
    
    # Prüfe python3-full speziell
    if ! dpkg -l python3-full >/dev/null 2>&1; then
        missing_deps+=("python3-full")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_warning "Installiere fehlende System-Pakete: ${missing_deps[*]}"
        
        if ! request_sudo_if_needed; then
            log_error "Sudo-Berechtigung erforderlich für: ${missing_deps[*]}"
            return 1
        fi
        
        if ! sudo apt update; then
            log_error "apt update fehlgeschlagen"
            return 1
        fi
        
        if ! sudo apt install -y "${missing_deps[@]}"; then
            log_error "Installation der System-Pakete fehlgeschlagen"
            return 1
        fi
    fi
    
    log_success "System-Abhängigkeiten verfügbar"
    return 0
}

# --- DIRECTORY SETUP ---
setup_directories() {
    log_info "Erstelle Arbeitsverzeichnisse..."
    
    local dirs=(
        "$WORK_DIR"
        "$(dirname "$LLAMA_CPP_DIR")"
        "$VENV_BASE_DIR"
    )
    
    for dir in "${dirs[@]}"; do
        if ! mkdir -p "$dir"; then
            log_error "Verzeichnis-Erstellung fehlgeschlagen: $dir"
            return 1
        fi
    done
    
    log_success "Arbeitsverzeichnisse erstellt"
    return 0
}

# --- LLAMA.CPP REPOSITORY MANAGEMENT ---
setup_llama_cpp_repository() {
    log_info "Richte llama.cpp Repository ein..."
    
    if [ ! -d "$LLAMA_CPP_DIR" ]; then
        log_info "Klone llama.cpp Repository..."
        if ! git clone "$LLAMA_CPP_REPO" "$LLAMA_CPP_DIR"; then
            log_error "llama.cpp Clone fehlgeschlagen"
            return 1
        fi
    else
        if [ "${CLEAN_BUILD:-0}" = "1" ]; then
            log_info "Clean Build: Entferne vorheriges llama.cpp..."
            rm -rf "$LLAMA_CPP_DIR"
            if ! git clone "$LLAMA_CPP_REPO" "$LLAMA_CPP_DIR"; then
                log_error "llama.cpp Clone fehlgeschlagen"
                return 1
            fi
        else
            log_info "Update llama.cpp Repository..."
            cd "$LLAMA_CPP_DIR"
            git pull || log_warning "llama.cpp Update fehlgeschlagen (nicht kritisch)"
        fi
    fi
    
    cd "$LLAMA_CPP_DIR"
    git submodule update --init --recursive
    
    log_success "llama.cpp Repository bereit"
    return 0
}

# --- PYTORCH ARM INSTALLATION ---
install_pytorch_arm() {
    log_info "Installiere PyTorch für ARM..."
    
    # VENV muss bereits aktiv sein
    if [ -z "${VIRTUAL_ENV:-}" ]; then
        log_error "VENV nicht aktiv für PyTorch Installation"
        return 1
    fi
    
    # Strategie 1: PyTorch ARM Index
    log_info "Versuche PyTorch ARM Wheels..."
    if pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu; then
        log_success "PyTorch ARM Wheels installiert"
        return 0
    fi
    
    # Strategie 2: Standard PyPI (kann lange dauern)
    log_warning "Fallback: Standard PyPI (kann 30+ Minuten dauern)..."
    log_info "Installiere PyTorch via Standard PyPI..."
    
    # ARM-Build-Optimierungen
    export MAX_JOBS=$BUILD_JOBS
    
    if pip install torch --no-cache-dir --verbose; then
        log_success "PyTorch via PyPI installiert"
        return 0
    fi
    
    # Strategie 3: Conda (falls verfügbar)
    if check_command conda; then
        log_warning "Versuche Conda PyTorch..."
        if conda install pytorch cpuonly -c pytorch -y; then
            log_success "PyTorch via Conda installiert"
            return 0
        fi
    fi
    
    log_error "PyTorch-Installation fehlgeschlagen!"
    log_error "Mögliche Lösungen:"
    log_error "1. Installieren Sie Miniforge: https://github.com/conda-forge/miniforge"
    log_error "2. Verwenden Sie vorkompilierte PyTorch ARM Wheels"
    log_error "3. Kompilieren Sie PyTorch manuell"
    
    return 1
}

install_python_dependencies() {
    log_info "Installiere Python-Abhängigkeiten..."
    
    # Aktiviere VENV mit Retry-Mechanismus
    local retry_count=0
    while [ $retry_count -lt 3 ]; do
        if activate_venv "$LLAMA_CPP_VENV"; then
            break
        fi
        retry_count=$((retry_count + 1))
        log_warning "VENV-Aktivierung Versuch $retry_count fehlgeschlagen, retry..."
        sleep 1
    done
    
    if [ $retry_count -eq 3 ]; then
        log_error "VENV-Aktivierung endgültig fehlgeschlagen"
        return 1
    fi
    
    # Force VENV pip
    local venv_pip="$LLAMA_CPP_VENV/bin/pip"
    if [ ! -f "$venv_pip" ]; then
        log_error "VENV pip nicht gefunden: $venv_pip"
        deactivate_current_venv
        return 1
    fi
    
    # Basis-Dependencies
    local base_deps=("numpy" "sentencepiece" "protobuf" "safetensors")
    
    log_info "Installiere Basis-Dependencies..."
    if ! "$venv_pip" install "${base_deps[@]}"; then
        log_error "Basis-Dependencies Installation fehlgeschlagen"
        deactivate_current_venv
        return 1
    fi
    
    # PyTorch für HF→GGUF Conversion
    if ! install_pytorch_arm; then
        log_error "PyTorch Installation fehlgeschlagen"
        deactivate_current_venv
        return 1
    fi
    
    # Transformers nach PyTorch
    log_info "Installiere transformers..."
    if ! "$venv_pip" install transformers; then
        log_error "Transformers Installation fehlgeschlagen"
        deactivate_current_venv
        return 1
    fi
    
    # Verifikation
    log_info "Verifiziere Dependencies..."
    if ! "$LLAMA_CPP_VENV/bin/python" -c "import torch, transformers, sentencepiece; print('Dependencies OK')"; then
        log_error "Dependencies Verifikation fehlgeschlagen"
        deactivate_current_venv
        return 1
    fi
    
    log_success "Python-Abhängigkeiten installiert"
    deactivate_current_venv
    return 0
}

# --- MAIN FUNCTIONS ---
validate_environment() {
    log_info "Validiere Build-Umgebung..."
    
    # Prüfe kritische Pfade
    local critical_paths=("$LLAMA_CPP_DIR" "$LLAMA_CPP_VENV")
    
    for path in "${critical_paths[@]}"; do
        if [ ! -d "$path" ]; then
            log_error "Kritischer Pfad fehlt: $path"
            return 1
        fi
    done
    
    # Prüfe llama.cpp Tools
    local llama_tools=("$LLAMA_CPP_DIR/convert_hf_to_gguf.py")
    
    for tool in "${llama_tools[@]}"; do
        if [ ! -f "$tool" ]; then
            log_error "llama.cpp Tool fehlt: $tool"
            return 1
        fi
    done
    
    # Prüfe VENV
    if ! activate_venv "$LLAMA_CPP_VENV"; then
        log_error "VENV-Aktivierung für Validierung fehlgeschlagen"
        return 1
    fi
    
    # Test Python-Imports
    if ! python -c "import torch, transformers" 2>/dev/null; then
        log_error "Python-Dependencies nicht vollständig"
        deactivate_current_venv
        return 1
    fi
    
    deactivate_current_venv
    log_success "Build-Umgebung validiert"
    return 0
}

print_summary() {
    echo ""
    echo "✅ SOURCE-MODUL ERFOLGREICH!"
    echo "============================"
    echo "📁 Arbeitsverzeichnis: $WORK_DIR"
    echo "🐍 Python-VENV: $LLAMA_CPP_VENV"
    echo "🛠️  llama.cpp: $LLAMA_CPP_DIR"
    echo "🔧 Build-Jobs: $BUILD_JOBS"
    echo ""
    echo "🎯 Nächste Schritte:"
    echo "   1. config_module.sh - Hardware-Konfiguration"
    echo "   2. convert_module.sh - Model-Konvertierung"
    echo "   3. target_module.sh - Quantisierung & Packaging"
    echo ""
    echo "🚀 Build-Umgebung bereit für LLM-Konvertierung!"
}

# --- MAIN EXECUTION ---
main() {
    local start_time=$SECONDS
    
    echo ""
    echo "🚀 LLM CONVERTER - SOURCE MODULE"
    echo "================================"
    echo "🎯 Environment & Tools Setup"
    echo ""
    
    # Parse arguments
    parse_arguments "$@"
    
    log_info "🔧 SYSTEM SETUP"
    check_system_dependencies
    setup_directories
    
    log_info "📦 REPOSITORY SETUP"
    setup_llama_cpp_repository
    
    log_info "🐍 PYTHON ENVIRONMENT"
    create_venv "$LLAMA_CPP_VENV"
    install_python_dependencies
    
    log_info "✅ VALIDATION"
    validate_environment
    
    print_summary
    
    local duration=$((SECONDS - start_time))
    log_success "Source-Modul abgeschlossen in ${duration} Sekunden"
    return 0
}

# --- EXECUTION ---
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi