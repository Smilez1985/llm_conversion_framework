# Dockerfile für [Hardware-Familie]
# LLM Cross-Compiler Framework - Template
# DIREKTIVE: Goldstandard, Multi-stage, Hadolint-konform

# ============================================================================
# STAGE 1: Build Environment Setup
# ============================================================================
# Verwenden Sie ein stabiles Basis-Image, z.B. debian:bookworm oder ubuntu:22.04
FROM debian:bookworm-slim AS builder

# Metadaten
LABEL maintainer="[Ihr Name]"
LABEL description="[Hardware-Familie] Cross-Compilation Container"
LABEL version="1.0.0"

# Build-Argumente
ARG BUILD_JOBS=4
ARG PYTHON_VERSION=3.11

# Umgebungsvariablen
ENV DEBIAN_FRONTEND=noninteractive
ENV LLAMA_CPP_PATH=/usr/src/llama.cpp
ENV BUILD_CACHE_DIR=/build-cache
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ============================================================================
# SYSTEM DEPENDENCIES & TOOLCHAIN
# ============================================================================

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Build essentials
        build-essential \
        cmake \
        make \
        git \
        curl \
        wget \
        ca-certificates \
        \
        # 1. ERSETZEN: Cross-compilation toolchain für [IHRE_ARCHITEKTUR]
        # Beispiel für AArch64 (Rockchip/Jetson/R-Pi):
        # crossbuild-essential-arm64 \
        # gcc-aarch64-linux-gnu \
        # g++-aarch64-linux-gnu \
        
        # Beispiel für x86_64 (Native, Intel NPU):
        # (Keine Cross-Compiler nötig, nur build-essential)
        
        # Python
        python3=${PYTHON_VERSION}* \
        python3-pip \
        python3-dev \
        python3-venv \
        \
        # Utilities
        pkg-config \
        libffi-dev \
        libssl-dev \
        jq \
        bc \
        file \
        time \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ============================================================================
# 2. ERSETZEN: Proprietäre SDKs (falls erforderlich)
# ============================================================================
# Beispiel für NVIDIA CUDA (auskommentiert):
# RUN wget ...
# RUN ./cuda_installer.run --silent ...

# Beispiel für Intel OpenVINO (auskommentiert):
# RUN wget ...
# RUN /opt/intel/openvino/install_dependencies.sh

# ============================================================================
# PYTHON ENVIRONMENT & DEPENDENCIES
# ============================================================================

RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Installiere PyTorch (notwendig für Konvertierung)
RUN python3 -m pip install --no-cache-dir \
        torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cpu

# Installiere ML-Abhängigkeiten
RUN python3 -m pip install --no-cache-dir \
        transformers tokenizers safetensors sentencepiece protobuf \
        huggingface-hub datasets numpy scipy onnx onnxruntime \
        tqdm psutil pyyaml requests

# ============================================================================
# LLAMA.CPP SETUP (Wird von source_module.sh ausgeführt)
# ============================================================================
# Das Klonen und Bauen von llama.cpp erfolgt durch die Module,
# um Flexibilität zu gewährleisten.

# ============================================================================
# STAGE 2: Runtime Environment
# ============================================================================
FROM debian:bookworm-slim AS runtime

LABEL stage="runtime"
LABEL framework="llm-cross-compiler"
LABEL target="[Hardware-Familie]"

ENV DEBIAN_FRONTEND=noninteractive
ENV LLAMA_CPP_PATH=/usr/src/llama.cpp
ENV BUILD_CACHE_DIR=/build-cache
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/app/modules:/app/scripts:${PATH}"

# Installiere minimale Runtime-Abhängigkeiten
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # 3. ERSETZEN: Runtime-Bibliotheken (z.B. Cross-Compiler Runtime)
        # Beispiel für AArch64:
        # crossbuild-essential-arm64 \
        
        # Python Runtime
        python3 \
        # Build tools (benötigt für config_module/target_module)
        cmake \
        make \
        git \
        # Utilities
        bc \
        jq \
        file \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Kopiere Python-Umgebung
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Kopiere llama.cpp (falls in Stufe 1 gebaut)
# Normalerweise wird dies durch source_module.sh im Volume erledigt

# Kopiere Framework-Module und Skripte
WORKDIR /app
COPY modules/ ./modules/
COPY scripts/ ./scripts/
RUN chmod +x modules/*.sh scripts/*.sh

# ============================================================================
# RUNTIME CONFIGURATION
# ============================================================================

# Erstelle Cache-Verzeichnis und Non-Root-User
RUN mkdir -p ${BUILD_CACHE_DIR} \
    && mkdir -p ${BUILD_CACHE_DIR}/{models,temp,output,logs,toolchains} \
    && groupadd -r llmbuilder \
    && useradd -r -g llmbuilder -d /app -s /bin/bash llmbuilder \
    && chown -R llmbuilder:llmbuilder /app ${BUILD_CACHE_DIR}

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import torch, transformers; print('OK')" || exit 1

# Setze Workdir und User
WORKDIR ${BUILD_CACHE_DIR}
USER llmbuilder

# Volumes
VOLUME ["${BUILD_CACHE_DIR}"]

# Entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["interactive"]