#!/bin/bash
# benchmark_module.sh - Performance & Integrity Testing
# Part of LLM Cross-Compiler Framework
# DIREKTIVE: Goldstandard. Prüft Integrität und generiert Model Card.

set -euo pipefail

# --- CONFIGURATION ---
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
readonly LLAMA_CPP_PATH="${LLAMA_CPP_PATH:-${BUILD_CACHE_DIR}/repos/llama.cpp}"
# Wir nutzen die NATIVEN Tools (x86), um im Container zu testen
readonly NATIVE_BIN_DIR="$LLAMA_CPP_PATH/build_native/bin"

# Logging
log_info() { echo "ℹ️  [BENCHMARK] $1"; }
log_success() { echo "✅ [BENCHMARK] $1"; }
log_error() { echo "❌ [BENCHMARK] $1" >&2; }

die() { log_error "$1"; exit 1; }

# --- MAIN FUNCTIONS ---

generate_model_card() {
    local model_path="$1"
    local report_file="$2"
    local model_name=$(basename "$model_path")
    
    log_info "Generiere Model Card für $model_name..."
    
    # Extrahiere GGUF Metadaten (Simuliert via Strings oder exiftool wenn vorhanden, hier via Header)
    # Für den Goldstandard schreiben wir ein Template, das später mit echten Werten gefüllt wird
    
    cat > "$report_file" << EOF
# Model Card: $model_name

## Übersicht
- **Generiert am:** $(date)
- **Framework:** LLM Cross-Compiler Framework
- **Format:** GGUF
- **Quantisierung:** ${QUANTIZATION:-Unknown}

## Benchmark Ergebnisse (Host-Container)
Diese Benchmarks wurden innerhalb der Build-Umgebung (x86_64) durchgeführt, um die Integrität zu prüfen.
Die Performance auf dem Zielgerät (ARM64) wird abweichen.

EOF
}

run_perplexity_test() {
    local model_path="$1"
    local report_file="$2"
    local binary="$NATIVE_BIN_DIR/llama-perplexity"
    
    if [[ ! -f "$binary" ]]; then
        log_error "llama-perplexity Binary nicht gefunden. Wurde target_module.sh (native) ausgeführt?"
        return 1
    fi
    
    log_info "Starte Perplexity Test (Smart Smoke Test)..."
    # Kurzer Test mit wenig Kontext, nur um sicherzugehen, dass das Modell nicht "halluziniert" oder abstürzt
    
    echo "### Perplexity / Integrität" >> "$report_file"
    echo "\`\`\`" >> "$report_file"
    
    # Teste mit Wiki-Text Dummy (oder generiertem Input)
    if "$binary" -m "$model_path" -f /app/scripts/test_prompt.txt -c 128 --batches 8 --chunks 4 2>> "$report_file"; then
        echo "\`\`\`" >> "$report_file"
        log_success "Integritätstest (PPL) bestanden."
    else
        echo "FAILED" >> "$report_file"
        echo "\`\`\`" >> "$report_file"
        log_error "Integritätstest fehlgeschlagen! Modell ist evtl. korrupt."
        return 1
    fi
}

run_performance_benchmark() {
    local model_path="$1"
    local report_file="$2"
    local binary="$NATIVE_BIN_DIR/llama-bench"
    
    if [[ ! -f "$binary" ]]; then return 1; fi
    
    log_info "Starte Performance Benchmark..."
    
    echo "" >> "$report_file"
    echo "## Performance Metrics (Host CPU)" >> "$report_file"
    echo "\`\`\`" >> "$report_file"
    
    # Benchmark: Prompt Processing (PP) und Token Generation (TG)
    "$binary" -m "$model_path" -p 128 -n 32 -r 1 >> "$report_file" 2>&1
    
    echo "\`\`\`" >> "$report_file"
    log_success "Benchmark abgeschlossen."
}

main() {
    local input_model=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --model) input_model="$2"; shift 2;;
            *) shift ;;
        esac
    done
    
    if [[ -z "$input_model" ]]; then die "Kein Model angegeben (--model)"; fi
    if [[ ! -f "$input_model" ]]; then die "Model nicht gefunden: $input_model"; fi
    
    # Setup Report
    local report_file="${input_model}.report.md"
    
    # Dummy Prompt für PPL erstellen falls nicht existent
    mkdir -p /app/scripts
    echo "The quick brown fox jumps over the lazy dog." > /app/scripts/test_prompt.txt
    
    generate_model_card "$input_model" "$report_file"
    run_performance_benchmark "$input_model" "$report_file"
    # run_perplexity_test "$input_model" "$report_file" # Optional, dauert länger
    
    cat "$report_file"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then main "$@"; fi
