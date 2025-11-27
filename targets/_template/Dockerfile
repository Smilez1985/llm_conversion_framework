# Dockerfile für [Hardware-Familie]
# LLM Cross-Compiler Framework - Template
# DIREKTIVE: Goldstandard, Multi-stage, Hadolint-konform, Secured, CI-Ready

# ============================================================================
# STAGE 1: Build Environment Setup
# ============================================================================
FROM debian:bookworm-slim AS builder

LABEL maintainer="Community Contributor"
LABEL description="[Hardware-Familie] Cross-Compilation Container"
LABEL version="1.0.0"

# Build-Argumente für CI/CD User-Mapping
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG BUILD_JOBS=4
ARG PYTHON_VERSION=3.11
ARG POETRY_URL="https://install.python-poetry.org"
ARG POETRY_SHA256="3b5842cd6318176812455429c6c109909d21b184579720f154506f6734828455"

ENV DEBIAN_FRONTEND=noninteractive
ENV LLAMA_CPP_PATH=/usr/src/llama.cpp
ENV BUILD_CACHE_DIR=/build-cache
ENV PATH="/root/.local/bin:$PATH"

# System Dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential cmake make git curl wget ca-certificates \
        python3=${PYTHON_VERSION}* python3-pip python3-dev python3-venv \
        pkg-config libffi-dev libssl-dev jq bc file time ccache \
        {packages_str} \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Secure Poetry Installation
RUN curl -sSL -o poetry_installer.py "${POETRY_URL}" \
    && echo "${POETRY_SHA256}  poetry_installer.py" | sha256sum -c - \
    && python3 poetry_installer.py \
    && rm poetry_installer.py

ENV PATH="/root/.local/bin:$PATH"
RUN poetry config virtualenvs.create false

# Python Environment
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel
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

ENV DEBIAN_FRONTEND=noninteractive
ENV BUILD_CACHE_DIR=/build-cache
ENV PATH="/app/modules:/app/scripts:${PATH}"

# Runtime Dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip cmake make git bc jq file curl \
    && rm -rf /var/lib/apt/lists/* && apt-get clean

# Copy Python Env
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Setup Directories & User with correct UID/GID
RUN groupadd -g ${GROUP_ID} llmbuilder && \
    useradd -u ${USER_ID} -g llmbuilder -d /app -s /bin/bash llmbuilder && \
    mkdir -p ${BUILD_CACHE_DIR}/{models,temp,output,logs,toolchains} && \
    chown -R llmbuilder:llmbuilder /app ${BUILD_CACHE_DIR}

WORKDIR /app
COPY modules/ ./modules/
COPY scripts/ ./scripts/
RUN chmod +x modules/*.sh scripts/*.sh

# Setup Entrypoint
COPY --chown=llmbuilder:llmbuilder docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR ${BUILD_CACHE_DIR}
USER llmbuilder

VOLUME ["${BUILD_CACHE_DIR}"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["interactive"]
