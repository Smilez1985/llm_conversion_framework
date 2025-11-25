# Dockerfile für [Hardware-Familie]
# LLM Cross-Compiler Framework - Template
# DIREKTIVE: Goldstandard, Multi-stage, Hadolint-konform, Secured

# ============================================================================
# STAGE 1: Build Environment Setup
# ============================================================================
FROM debian:bookworm-slim AS builder

# Metadaten
LABEL maintainer="[Ihr Name]"
LABEL description="[Hardware-Familie] Cross-Compilation Container"
LABEL version="1.0.0"

# Build-Argumente (Standard-Werte, werden durch docker-compose überschrieben)
ARG BUILD_JOBS=4
ARG PYTHON_VERSION=3.11
ARG POETRY_URL="https://install.python-poetry.org"
ARG POETRY_SHA256="3b5842cd6318176812455429c6c109909d21b184579720f154506f6734828455"

# Umgebungsvariablen
ENV DEBIAN_FRONTEND=noninteractive
ENV LLAMA_CPP_PATH=/usr/src/llama.cpp
ENV BUILD_CACHE_DIR=/build-cache
ENV CCACHE_DIR=/build-cache/ccache
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/root/.local/bin:$PATH"

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
        
        # Python
        python3=${PYTHON_VERSION}* \
        python3-pip \
        python3-dev \
        python3-venv \
        \
        # Utilities & Security
        pkg-config \
        libffi-dev \
        libssl-dev \
        jq \
        bc \
        file \
        time \
        ccache \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ============================================================================
# SECURE POETRY INSTALLATION
# ============================================================================
RUN curl -sSL -o poetry_installer.py "${POETRY_URL}" \
    && echo "${POETRY_SHA256}  poetry_installer.py" | sha256sum -c - \
    && python3 poetry_installer.py \
    && rm poetry_installer.py

# Configure Poetry
ENV PATH="/root/.local/bin:$PATH"
RUN poetry config virtualenvs.create false

# ============================================================================
# 2. ERSETZEN: Proprietäre SDKs (falls erforderlich)
# ============================================================================
# Beispiel: RUN wget ... && ./cuda_installer.run --silent ...

# ============================================================================
# PYTHON ENVIRONMENT & DEPENDENCIES
# ============================================================================

RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Installiere Core ML Dependencies (Pinned versions recommended)
RUN python3 -m pip install --no-cache-dir \
        torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu \
        transformers tokenizers safetensors sentencepiece protobuf \
        huggingface-hub datasets numpy scipy onnx onnxruntime \
        tqdm psutil pyyaml requests

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
        # crossbuild-essential-arm64 \
        python3 \
        python3-pip \
        cmake \
        make \
        git \
        bc \
        jq \
        file \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Kopiere Python-Umgebung
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

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
    && chmod -R 755 ${BUILD_CACHE_DIR}

RUN groupadd -r llmbuilder && \
    useradd -r -g llmbuilder -d /app -s /bin/bash llmbuilder \
    && chown -R llmbuilder:llmbuilder /app ${BUILD_CACHE_DIR}

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import torch; print('OK')" || exit 1

# Setze Workdir und User
WORKDIR ${BUILD_CACHE_DIR}
USER llmbuilder

# Volumes
VOLUME ["${BUILD_CACHE_DIR}"]

# Entrypoint (Pfad korrigiert!)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["interactive"]
