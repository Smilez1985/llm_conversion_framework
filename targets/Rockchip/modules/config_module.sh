#!/bin/bash
# config_module.sh - Hardware Config & CMake Toolchain Generator
# Part of LLM Cross-Compiler Framework
# 
# DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.
# ZWECK: Liest target_hardware_config.txt und generiert optimierte Build-Konfiguration
#        Variable Substitution für hardware-spezifische Compiler-Flags

set -euo pipefail

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================

readonly SCRIPT_NAME="config_module.sh"
readonly SCRIPT_VERSION="1.0.0"

# Environment variables with defaults
readonly BUILD_CACHE_DIR="${BUILD_CACHE_DIR:-/build-cache}"
readonly HARDWARE_CONFIG_FILE="${HARDWARE_CONFIG_FILE:-${BUILD_CACHE_DIR}/target_hardware_config.txt}"
readonly OUTPUT_TOOLCHAIN_FILE="${OUTPUT_TOOLCHAIN_FILE:-${BUILD_CACHE_DIR}/cross_compile_toolchain.cmake}"
readonly OUTPUT_CONFIG_FILE="${OUTPUT_CONFIG_FILE:-${BUILD_CACHE_DIR}/build_config.sh}"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Hardware configuration storage
declare -A HW_CONFIG
declare -A COMPILER_CONFIG
declare -A CMAKE_FLAGS

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

die() {
    log_error "$1"
    exit "${2:-1}"
}

# ============================================================================
# HARDWARE CONFIG PARSING
# ============================================================================

load_hardware_config() {
    log_info "Loading hardware configuration from: $HARDWARE_CONFIG_FILE"
    
    if [[ ! -f "$HARDWARE_CONFIG_FILE" ]]; then
        die "Hardware config file not found: $HARDWARE_CONFIG_FILE"
    fi
    
    # Parse key=value pairs, skip comments and empty lines
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        
        # Clean key and value
        key=$(echo "$key" | tr -d ' \t')
        value=$(echo "$value" | tr -d ' \t' | sed 's/^"//;s/"$//')
        
        # Store in associative array
        HW_CONFIG["$key"]="$value"
        
    done < <(grep -E '^[^#]*=' "$HARDWARE_CONFIG_FILE")
    
    log_info "Loaded ${#HW_CONFIG[@]} hardware configuration parameters"
}

display_hardware_summary() {
    log_info "Hardware Configuration Summary:"
    echo "=================================="
    echo "CPU Model: ${HW_CONFIG[CPU_MODEL_NAME]:-Unknown}"
    echo "Architecture: ${HW_CONFIG[ARCHITECTURE_FULL]:-Unknown}"
    echo "CPU Cores: ${HW_CONFIG[CPU_CORES]:-Unknown}"
    echo "NEON Support: ${HW_CONFIG[SUPPORTS_NEON]:-Unknown}"
    echo "AVX2 Support: ${HW_CONFIG[SUPPORTS_AVX2]:-Unknown}"
    echo "AVX512 Support: ${HW_CONFIG[SUPPORTS_AVX512]:-Unknown}"
    echo "GPU Model: ${HW_CONFIG[GPU_MODEL]:-Not Detected}"
    echo "OS: ${HW_CONFIG[OS_DISTRO]:-Unknown} ${HW_CONFIG[OS_VERSION_ID]:-}"
    echo "=================================="
}

# ============================================================================
# ARCHITECTURE DETECTION & COMPILER FLAGS
# ============================================================================

detect_target_architecture() {
    local arch="${HW_CONFIG[ARCHITECTURE_FULL]:-unknown}"
    local cpu_model="${HW_CONFIG[CPU_MODEL_NAME]:-unknown}"
    
    log_info "Detecting target architecture: $arch"
    
    case "$arch" in
        "aarch64"|"arm64")
            COMPILER_CONFIG[TARGET_ARCH]="aarch64"
            COMPILER_CONFIG[CROSS_PREFIX]="aarch64-linux-gnu"
            detect_arm_cpu_specific_flags
            setup_arm_compiler_flags
            ;;
        "x86_64"|"amd64")
            COMPILER_CONFIG[TARGET_ARCH]="x86_64"
            COMPILER_CONFIG[CROSS_PREFIX]=""  # Native compilation
            detect_x86_cpu_specific_flags
            setup_x86_compiler_flags
            ;;
        "armv7l")
            COMPILER_CONFIG[TARGET_ARCH]="armv7l"
            COMPILER_CONFIG[CROSS_PREFIX]="arm-linux-gnueabihf"
            setup_armv7_compiler_flags
            ;;
        *)
            die "Unsupported target architecture: $arch"
            ;;
    esac
    
    log_success "Target architecture configured: ${COMPILER_CONFIG[TARGET_ARCH]}"
}

detect_arm_cpu_specific_flags() {
    local cpu_model="${HW_CONFIG[CPU_MODEL_NAME]:-unknown}"
    local cpu_flags=""
    
    log_info "Detecting ARM CPU specific optimizations for: $cpu_model"
    
    # Rockchip family detection
    if [[ "$cpu_model" =~ [Cc]ortex-[Aa]55 ]] || [[ "$cpu_model" =~ RK3566 ]]; then
        cpu_flags="-mcpu=cortex-a55"
        COMPILER_CONFIG[CPU_TARGET]="cortex-a55"
        COMPILER_CONFIG[SOC_FAMILY]="rockchip"
        log_info "Detected Rockchip RK3566/RK3568 (Cortex-A55)"
    elif [[ "$cpu_model" =~ [Cc]ortex-[Aa]76 ]] || [[ "$cpu_model" =~ RK3588 ]]; then
        cpu_flags="-mcpu=cortex-a76"
        COMPILER_CONFIG[CPU_TARGET]="cortex-a76"
        COMPILER_CONFIG[SOC_FAMILY]="rockchip"
        log_info "Detected Rockchip RK3588 (Cortex-A76)"
    elif [[ "$cpu_model" =~ [Cc]ortex-[Aa]72 ]]; then
        cpu_flags="-mcpu=cortex-a72"
        COMPILER_CONFIG[CPU_TARGET]="cortex-a72"
        COMPILER_CONFIG[SOC_FAMILY]="broadcom"  # Raspberry Pi 4
        log_info "Detected Raspberry Pi 4 (Cortex-A72)"
    elif [[ "$cpu_model" =~ [Cc]ortex-[Aa]53 ]]; then
        cpu_flags="-mcpu=cortex-a53"
        COMPILER_CONFIG[CPU_TARGET]="cortex-a53"
        COMPILER_CONFIG[SOC_FAMILY]="generic"
        log_info "Detected Generic Cortex-A53"
    else
        # Generic ARM64 fallback
        cpu_flags="-march=armv8-a"
        COMPILER_CONFIG[CPU_TARGET]="generic-armv8-a"
        COMPILER_CONFIG[SOC_FAMILY]="generic"
        log_warn "Unknown ARM CPU, using generic ARMv8-A flags"
    fi
    
    COMPILER_CONFIG[CPU_FLAGS]="$cpu_flags"
}

detect_x86_cpu_specific_flags() {
    local cpu_flags=""
    local simd_flags=""
    
    log_info "Detecting x86_64 CPU specific optimizations"
    
    # SIMD instruction set detection
    if [[ "${HW_CONFIG[SUPPORTS_AVX512]:-OFF}" == "ON" ]]; then
        simd_flags="-mavx512f -mavx512bw -mavx512vl"
        COMPILER_CONFIG[SIMD_LEVEL]="AVX512"
        log_info "Detected AVX512 support"
    elif [[ "${HW_CONFIG[SUPPORTS_AVX2]:-OFF}" == "ON" ]]; then
        simd_flags="-mavx2 -mfma"
        COMPILER_CONFIG[SIMD_LEVEL]="AVX2"
        log_info "Detected AVX2 support"
    elif [[ "${HW_CONFIG[SUPPORTS_AVX]:-OFF}" == "ON" ]]; then
        simd_flags="-mavx"
        COMPILER_CONFIG[SIMD_LEVEL]="AVX"
        log_info "Detected AVX support"
    else
        simd_flags="-msse4.2"
        COMPILER_CONFIG[SIMD_LEVEL]="SSE42"
        log_info "Using SSE4.2 as baseline"
    fi
    
    # Generic x86_64 optimization
    cpu_flags="-march=native -mtune=native"
    COMPILER_CONFIG[CPU_FLAGS]="$cpu_flags $simd_flags"
    COMPILER_CONFIG[CPU_TARGET]="native"
    COMPILER_CONFIG[SOC_FAMILY]="x86_64"
}

setup_armv7_compiler_flags() {
    log_info "Setting up ARMv7 compiler flags"
    
    local cpu_flags="-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard"
    COMPILER_CONFIG[CPU_FLAGS]="$cpu_flags"
    COMPILER_CONFIG[CPU_TARGET]="armv7-a"
    COMPILER_CONFIG[SOC_FAMILY]="armv7"
    COMPILER_CONFIG[SIMD_LEVEL]="NEON"
}

# ============================================================================
# COMPILER FLAGS GENERATION
# ============================================================================

setup_arm_compiler_flags() {
    log_info "Setting up ARM compiler flags"
    
    local base_flags="-O3 -pthread -fPIC"
    local security_flags="-fstack-protector-strong -D_FORTIFY_SOURCE=2"
    local optimization_flags="-funroll-loops -ffast-math"
    
    # NEON support
    local simd_flags=""
    if [[ "${HW_CONFIG[SUPPORTS_NEON]:-OFF}" == "ON" ]]; then
        # NEON is implicit in AArch64, explicit for ARMv7
        if [[ "${COMPILER_CONFIG[TARGET_ARCH]}" == "aarch64" ]]; then
            simd_flags=""  # NEON is default in AArch64
        else
            simd_flags="-mfpu=neon"
        fi
        COMPILER_CONFIG[SIMD_LEVEL]="NEON"
        CMAKE_FLAGS[GGML_NATIVE]="ON"
        log_info "NEON SIMD support enabled"
    else
        CMAKE_FLAGS[GGML_NATIVE]="OFF"
        log_warn "No NEON support detected"
    fi
    
    # Combine all flags
    COMPILER_CONFIG[CFLAGS]="${COMPILER_CONFIG[CPU_FLAGS]} $base_flags $security_flags $optimization_flags $simd_flags"
    COMPILER_CONFIG[CXXFLAGS]="${COMPILER_CONFIG[CFLAGS]} -std=c++17"
    COMPILER_CONFIG[LDFLAGS]="-Wl,-O1 -Wl,--as-needed"
}

setup_x86_compiler_flags() {
    log_info "Setting up x86_64 compiler flags"
    
    local base_flags="-O3 -pthread -fPIC"
    local security_flags="-fstack-protector-strong -D_FORTIFY_SOURCE=2"
    local optimization_flags="-funroll-loops -ffast-math"
    
    # Set GGML optimization flags based on SIMD level
    case "${COMPILER_CONFIG[SIMD_LEVEL]}" in
        "AVX512")
            CMAKE_FLAGS[GGML_AVX512]="ON"
            CMAKE_FLAGS[GGML_AVX2]="ON"
            CMAKE_FLAGS[GGML_AVX]="ON"
            ;;
        "AVX2")
            CMAKE_FLAGS[GGML_AVX512]="OFF"
            CMAKE_FLAGS[GGML_AVX2]="ON"
            CMAKE_FLAGS[GGML_AVX]="ON"
            ;;
        "AVX")
            CMAKE_FLAGS[GGML_AVX512]="OFF"
            CMAKE_FLAGS[GGML_AVX2]="OFF"
            CMAKE_FLAGS[GGML_AVX]="ON"
            ;;
        *)
            CMAKE_FLAGS[GGML_AVX512]="OFF"
            CMAKE_FLAGS[GGML_AVX2]="OFF"
            CMAKE_FLAGS[GGML_AVX]="OFF"
            ;;
    esac
    
    CMAKE_FLAGS[GGML_NATIVE]="ON"
    
    # Combine all flags
    COMPILER_CONFIG[CFLAGS]="${COMPILER_CONFIG[CPU_FLAGS]} $base_flags $security_flags $optimization_flags"
    COMPILER_CONFIG[CXXFLAGS]="${COMPILER_CONFIG[CFLAGS]} -std=c++17"
    COMPILER_CONFIG[LDFLAGS]="-Wl,-O1 -Wl,--as-needed"
}

# ============================================================================
# CMAKE TOOLCHAIN GENERATION
# ============================================================================

generate_cmake_toolchain() {
    log_info "Generating CMake toolchain file: $OUTPUT_TOOLCHAIN_FILE"
    
    # Create directory if needed
    mkdir -p "$(dirname "$OUTPUT_TOOLCHAIN_FILE")"
    
    cat > "$OUTPUT_TOOLCHAIN_FILE" << EOF
# CMake Toolchain File
# Generated by $SCRIPT_NAME v$SCRIPT_VERSION
# Target Hardware: ${HW_CONFIG[CPU_MODEL_NAME]:-Unknown}
# Architecture: ${COMPILER_CONFIG[TARGET_ARCH]}
# Generated: $(date -Iseconds)

SET(CMAKE_SYSTEM_NAME Linux)
SET(CMAKE_SYSTEM_PROCESSOR ${COMPILER_CONFIG[TARGET_ARCH]})

# Compiler Configuration
EOF

    # Add cross-compiler settings if needed
    if [[ -n "${COMPILER_CONFIG[CROSS_PREFIX]:-}" ]]; then
        cat >> "$OUTPUT_TOOLCHAIN_FILE" << EOF

# Cross-compilation toolchain
SET(CMAKE_C_COMPILER   /usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-gcc)
SET(CMAKE_CXX_COMPILER /usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-g++)
SET(CMAKE_AR           /usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-ar)
SET(CMAKE_STRIP        /usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-strip)

# Search paths
SET(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
SET(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
SET(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
EOF
    else
        cat >> "$OUTPUT_TOOLCHAIN_FILE" << EOF

# Native compilation
SET(CMAKE_C_COMPILER   /usr/bin/gcc)
SET(CMAKE_CXX_COMPILER /usr/bin/g++)
EOF
    fi

    # Add compiler flags
    cat >> "$OUTPUT_TOOLCHAIN_FILE" << EOF

# Compiler Flags
SET(CMAKE_C_FLAGS   "\${CMAKE_C_FLAGS} ${COMPILER_CONFIG[CFLAGS]}")
SET(CMAKE_CXX_FLAGS "\${CMAKE_CXX_FLAGS} ${COMPILER_CONFIG[CXXFLAGS]}")
SET(CMAKE_EXE_LINKER_FLAGS "\${CMAKE_EXE_LINKER_FLAGS} ${COMPILER_CONFIG[LDFLAGS]}")

# GGML/llama.cpp specific optimizations
EOF

    # Add GGML flags
    for flag in "${!CMAKE_FLAGS[@]}"; do
        echo "SET($flag ${CMAKE_FLAGS[$flag]})" >> "$OUTPUT_TOOLCHAIN_FILE"
    done
    
    # Add target-specific configurations
    cat >> "$OUTPUT_TOOLCHAIN_FILE" << EOF

# Target specific configuration
SET(TARGET_SOC_FAMILY "${COMPILER_CONFIG[SOC_FAMILY]}")
SET(TARGET_CPU "${COMPILER_CONFIG[CPU_TARGET]}")
SET(TARGET_SIMD_LEVEL "${COMPILER_CONFIG[SIMD_LEVEL]}")

# Build configuration
SET(CMAKE_BUILD_TYPE Release)
SET(BUILD_SHARED_LIBS OFF)
EOF

    log_success "CMake toolchain file generated successfully"
}

# ============================================================================
# BUILD CONFIGURATION SCRIPT GENERATION
# ============================================================================

generate_build_config() {
    log_info "Generating build configuration script: $OUTPUT_CONFIG_FILE"
    
    mkdir -p "$(dirname "$OUTPUT_CONFIG_FILE")"
    
    cat > "$OUTPUT_CONFIG_FILE" << EOF
#!/bin/bash
# Build Configuration Script
# Generated by $SCRIPT_NAME v$SCRIPT_VERSION
# Target Hardware: ${HW_CONFIG[CPU_MODEL_NAME]:-Unknown}
# Generated: $(date -Iseconds)

# Hardware Information
export TARGET_ARCH="${COMPILER_CONFIG[TARGET_ARCH]}"
export TARGET_CPU="${COMPILER_CONFIG[CPU_TARGET]}"
export TARGET_SOC_FAMILY="${COMPILER_CONFIG[SOC_FAMILY]}"
export TARGET_SIMD_LEVEL="${COMPILER_CONFIG[SIMD_LEVEL]}"

# Compiler Configuration
export CC="${COMPILER_CONFIG[CROSS_PREFIX]:+/usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-}gcc"
export CXX="${COMPILER_CONFIG[CROSS_PREFIX]:+/usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-}g++"
export AR="${COMPILER_CONFIG[CROSS_PREFIX]:+/usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-}ar"
export STRIP="${COMPILER_CONFIG[CROSS_PREFIX]:+/usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-}strip"

# Compiler Flags
export CFLAGS="${COMPILER_CONFIG[CFLAGS]}"
export CXXFLAGS="${COMPILER_CONFIG[CXXFLAGS]}"
export LDFLAGS="${COMPILER_CONFIG[LDFLAGS]}"

# Build Configuration
export CMAKE_TOOLCHAIN_FILE="$OUTPUT_TOOLCHAIN_FILE"
export BUILD_JOBS="\${BUILD_JOBS:-${HW_CONFIG[CPU_CORES]:-4}}"

# Hardware Capabilities (for runtime decisions)
export HW_SUPPORTS_NEON="${HW_CONFIG[SUPPORTS_NEON]:-OFF}"
export HW_SUPPORTS_AVX2="${HW_CONFIG[SUPPORTS_AVX2]:-OFF}"
export HW_SUPPORTS_AVX512="${HW_CONFIG[SUPPORTS_AVX512]:-OFF}"
export HW_GPU_MODEL="${HW_CONFIG[GPU_MODEL]:-None}"

# Path Configuration
export OUTPUT_DIR="\${OUTPUT_DIR:-\$BUILD_CACHE_DIR/output}"
export TEMP_DIR="\${TEMP_DIR:-\$BUILD_CACHE_DIR/temp}"

echo "Build configuration loaded for ${COMPILER_CONFIG[TARGET_ARCH]} (${COMPILER_CONFIG[CPU_TARGET]})"
EOF

    chmod +x "$OUTPUT_CONFIG_FILE"
    log_success "Build configuration script generated successfully"
}

# ============================================================================
# VALIDATION & VERIFICATION
# ============================================================================

validate_configuration() {
    log_info "Validating generated configuration..."
    
    # Check if cross-compiler exists (if cross-compilation)
    if [[ -n "${COMPILER_CONFIG[CROSS_PREFIX]:-}" ]]; then
        local cross_gcc="/usr/bin/${COMPILER_CONFIG[CROSS_PREFIX]}-gcc"
        if [[ ! -f "$cross_gcc" ]]; then
            die "Cross-compiler not found: $cross_gcc"
        fi
        
        # Test cross-compiler
        if ! "$cross_gcc" --version >/dev/null 2>&1; then
            die "Cross-compiler not functional: $cross_gcc"
        fi
        
        log_success "Cross-compiler validated: $cross_gcc"
    fi
    
    # Validate generated files
    if [[ ! -f "$OUTPUT_TOOLCHAIN_FILE" ]]; then
        die "CMake toolchain file not generated: $OUTPUT_TOOLCHAIN_FILE"
    fi
    
    if [[ ! -f "$OUTPUT_CONFIG_FILE" ]]; then
        die "Build config script not generated: $OUTPUT_CONFIG_FILE"
    fi
    
    # Validate CMake syntax
    if command -v cmake >/dev/null 2>&1; then
        if ! cmake -P "$OUTPUT_TOOLCHAIN_FILE" >/dev/null 2>&1; then
            log_warn "CMake toolchain file syntax validation failed (non-fatal)"
        else
            log_success "CMake toolchain file syntax validated"
        fi
    fi
    
    log_success "Configuration validation completed"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

print_summary() {
    echo ""
    echo "=== CONFIGURATION SUMMARY ==="
    echo "Target Architecture: ${COMPILER_CONFIG[TARGET_ARCH]}"
    echo "CPU Target: ${COMPILER_CONFIG[CPU_TARGET]}"
    echo "SOC Family: ${COMPILER_CONFIG[SOC_FAMILY]}"
    echo "SIMD Level: ${COMPILER_CONFIG[SIMD_LEVEL]}"
    echo "Cross Prefix: ${COMPILER_CONFIG[CROSS_PREFIX]:-Native}"
    echo ""
    echo "Generated Files:"
    echo "  CMake Toolchain: $OUTPUT_TOOLCHAIN_FILE"
    echo "  Build Config: $OUTPUT_CONFIG_FILE"
    echo ""
    echo "Compiler Flags:"
    echo "  CFLAGS: ${COMPILER_CONFIG[CFLAGS]}"
    echo "  CXXFLAGS: ${COMPILER_CONFIG[CXXFLAGS]}"
    echo "=============================="
}

main() {
    log_info "Starting $SCRIPT_NAME v$SCRIPT_VERSION"
    log_info "Hardware config file: $HARDWARE_CONFIG_FILE"
    log_info "Output directory: $BUILD_CACHE_DIR"
    
    # Load and process hardware configuration
    load_hardware_config
    display_hardware_summary
    
    # Generate compiler configuration
    detect_target_architecture
    
    # Generate output files
    generate_cmake_toolchain
    generate_build_config
    
    # Validate everything
    validate_configuration
    
    print_summary
    
    log_success "Configuration module completed successfully!"
    log_info "Next step: Run convert_module.sh to process model files"
}

# ============================================================================
# SCRIPT EXECUTION
# ============================================================================

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --hardware-config)
            HARDWARE_CONFIG_FILE="$2"
            shift 2
            ;;
        --output-toolchain)
            OUTPUT_TOOLCHAIN_FILE="$2"
            shift 2
            ;;
        --output-config)
            OUTPUT_CONFIG_FILE="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--hardware-config FILE] [--output-toolchain FILE] [--output-config FILE]"
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

# Only run main if script is executed directly (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi