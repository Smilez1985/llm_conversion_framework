#!/bin/bash
# rkllm_module.sh - RKLLM Toolkit Execution Module (Template)
# Part of LLM Cross-Compiler Framework
#
# DIREKTIVE: Goldstandard, Enterprise-Grade Error Handling.
# ZWECK: Wrapper-Skript, das die Python-Logik zur RKLLM-Konvertierung aufruft.
#        Wird vom ModuleGenerator in neue Targets kopiert.

set -euo pipefail

# ============================================================================
# CONFIGURATION & ENVIRONMENT
# ============================================================================

# Diese Variablen werden vom Orchestrator/Builder in den Container injiziert
# $MODEL_SOURCE    : Pfad zum Input-Modell (HuggingFace Repo oder lokaler Ordner)
# $QUANTIZATION    : Gewünschte Quantisierung (z.B. INT8, INT4, W8A8, W4A16)
# $OUTPUT_DIR      : Zielordner für Artefakte
# $SCRIPT_DIR      : Ort, an dem die Python-Helper liegen (default: /app/scripts)

# Defaults setzen, falls nicht injiziert (für lokale Tests)
BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
OUTPUT_DIR="${OUTPUT_DIR:-${BUILD_CACHE_DIR}/output}"
SCRIPT_DIR="${SCRIPT_DIR:-/app/scripts}"
RKLLM_DIR="/app/rknn-llm"

# Logging Helper
log_info() { echo ">> [RKLLM-Module] $(date '+%H:%M:%S') INFO: $1"; }
log_error() { echo ">> [RKLLM-Module] $(date '+%H:%M:%S') ERROR: $1" >&2; }
die() { log_error "$1"; exit 1; }

# ============================================================================
# MAIN LOGIC
# ============================================================================

main() {
    log_info "Initializing RKLLM Conversion Pipeline..."
    
    # 1. Validierung der Eingaben
    if [[ -z "${MODEL_SOURCE:-}" ]]; then
        die "Environment variable MODEL_SOURCE is missing."
    fi

    log_info "Model Source: $MODEL_SOURCE"
    log_info "Quantization Input: ${QUANTIZATION:-None}"

    # 2. Mapping der Quantisierung (Framework -> RKLLM SDK Sprech)
    # Das RKLLM-Toolkit versteht 'w8a8' und 'w4a16'. Wir mappen User-Eingaben darauf.
    case "${QUANTIZATION:-w8a8}" in
        "w8a8"|"W8A8"|"INT8"|"Q8_0"|"i8")
            Q_TYPE="w8a8"
            ;;
        "w4a16"|"W4A16"|"INT4"|"Q4_K_M"|"i4")
            Q_TYPE="w4a16"
            ;;
        *)
            log_info "Unknown quantization format '$QUANTIZATION'. Defaulting to 'w8a8'."
            Q_TYPE="w8a8"
            ;;
    esac

    log_info "Mapped Quantization Type: $Q_TYPE"

    # 3. Prüfen auf das Python-Konvertierungs-Skript
    # Das Skript 'export_rkllm.py' muss vom ModuleGenerator nach /app/scripts kopiert worden sein.
    CONVERTER_SCRIPT="$SCRIPT_DIR/export_rkllm.py"

    if [ ! -f "$CONVERTER_SCRIPT" ]; then
        die "Critical: Python converter script not found at $CONVERTER_SCRIPT. Check ModuleGenerator logic."
    fi

    # 4. Toolkit Setup (Optional, falls nicht im Dockerfile enthalten)
    # In der Regel ist das Toolkit im Image 'built-in', aber wir prüfen auf Updates via SSOT
    if [ -n "${RKLLM_TOOLKIT_REPO_OVERRIDE:-}" ] && [ ! -d "$RKLLM_DIR" ]; then
        log_info "Cloning RKLLM Toolkit from $RKLLM_TOOLKIT_REPO_OVERRIDE..."
        git clone "$RKLLM_TOOLKIT_REPO_OVERRIDE" "$RKLLM_DIR" || die "Git clone failed."
    fi

    # 5. Ausführung der Konvertierung
    log_info "Launching Python conversion process..."
    
    # Wir rufen python3 auf und übergeben die Parameter explizit
    # Das verhindert Injection-Angriffe, da wir keine Shell-Expansion nutzen
    set +e # Wir wollen den Exit-Code selbst behandeln
    python3 "$CONVERTER_SCRIPT" \
        --model "$MODEL_SOURCE" \
        --output "$OUTPUT_DIR/model-${Q_TYPE}.rkllm" \
        --quant "$Q_TYPE" \
        --target "rk3588" 
    
    EXIT_CODE=$?
    set -e

    if [ $EXIT_CODE -eq 0 ]; then
        log_info "Conversion completed successfully."
        
        # 6. Verifikation des Artefakts
        RESULT_FILE="$OUTPUT_DIR/model-${Q_TYPE}.rkllm"
        if [ -f "$RESULT_FILE" ]; then
            FILE_SIZE=$(du -h "$RESULT_FILE" | cut -f1)
            log_info "Generated Artifact: $RESULT_FILE (Size: $FILE_SIZE)"
        else
            die "Python script reported success, but output file '$RESULT_FILE' is missing."
        fi
    else
        die "Python conversion script failed with exit code $EXIT_CODE."
    fi
}

# Script Entrypoint
main "$@"
