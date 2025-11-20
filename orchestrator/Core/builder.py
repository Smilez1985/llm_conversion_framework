def _generate_dockerfile_content(self, config: BuildConfiguration, target_config: Dict) -> str:
        """
        Generate Multi-Stage Dockerfile content.
        """
        # Architecture mapping
        arch_mapping = {
            TargetArch.ARM64: "linux/arm64",
            TargetArch.ARMV7: "linux/arm/v7", 
            TargetArch.X86_64: "linux/amd64",
            TargetArch.RK3566: "linux/arm64",
            TargetArch.RK3588: "linux/arm64"
        }
        
        platform = arch_mapping.get(config.target_arch, "linux/amd64")
        
        dockerfile_lines = [
            "# hadolint ignore=DL3007",
            "# Multi-Stage Build for LLM Cross-Compilation",
            "# DIREKTIVE: BuildX + Hadolint + Poetry + VENV Support",
            "",
            "# =============================================================================",
            "# STAGE 1: Base Builder Environment", 
            "# =============================================================================",
            f"FROM --platform={platform} {config.base_image} AS builder",
            "",
            "# Install base build dependencies",
            "RUN apt-get update && apt-get install -y --no-install-recommends \\",
            "    build-essential cmake git curl wget python3 python3-pip python3-dev pkg-config \\",
            "    && apt-get clean && rm -rf /var/lib/apt/lists/*",
            "",
            "# Install Poetry",
            "ENV POETRY_VERSION=" + (config.poetry_version if config.poetry_version != "latest" else "1.7.1"),
            "ENV POETRY_HOME=/opt/poetry",
            "ENV POETRY_VENV_IN_PROJECT=true",
            "ENV PATH=\"/opt/poetry/bin:$PATH\"",
            "RUN curl -sSL https://install.python-poetry.org | python3 -",
            "",
            "# =============================================================================", 
            "# STAGE 2: Dependencies Installation (VENV)",
            "# =============================================================================",
            "FROM builder AS dependencies",
            "WORKDIR /workspace",
            "",
            "COPY pyproject.toml poetry.lock* ./",
            "",
            "# Install dependencies into .venv",
            "RUN poetry config virtualenvs.create true \\",
            "    && poetry install --no-dev --no-interaction --no-ansi",
            "",
        ]
        
        # RK3566 specifics
        if config.target_arch == TargetArch.RK3566:
            dockerfile_lines.extend([
                "RUN apt-get update && apt-get install -y --no-install-recommends gcc-aarch64-linux-gnu g++-aarch64-linux-gnu crossbuild-essential-arm64 && apt-get clean && rm -rf /var/lib/apt/lists/*",
                "ENV CC=aarch64-linux-gnu-gcc",
                "ENV CXX=aarch64-linux-gnu-g++", 
                "ENV AR=aarch64-linux-gnu-ar",
                "ENV STRIP=aarch64-linux-gnu-strip",
                "ENV CMAKE_TOOLCHAIN_FILE=/workspace/cmake/rk3566-toolchain.cmake",
            ])
        
        # Stage 3: Tools
        dockerfile_lines.extend([
            "FROM dependencies AS build-tools",
            "RUN mkdir -p /workspace/modules /workspace/cache /workspace/output /workspace/cmake",
            "COPY modules/ /workspace/modules/",
            "RUN chmod +x /workspace/modules/*.sh",
            "COPY build_config.json target.yml* /workspace/",
            # VENV Activation for Shell Scripts
            "ENV PATH=\"/workspace/.venv/bin:$PATH\"",
            "ENV VIRTUAL_ENV=\"/workspace/.venv\"",
            "",
        ])
        
        # ... (Custom Build Args loop - identisch)
        for key, value in config.build_args.items():
            dockerfile_lines.append(f"ENV {key}={value}")
            
        # Execution Stage
        dockerfile_lines.extend([
            "FROM build-tools AS build-execution",
            "WORKDIR /workspace",
            # Modules use the VENV implicitly via PATH
            "RUN /workspace/modules/source_module.sh",
            "RUN /workspace/modules/config_module.sh",
            "RUN /workspace/modules/convert_module.sh",
            "RUN /workspace/modules/target_module.sh",
            "",
            "# =============================================================================",
            "# STAGE 5: Final Output",
            "# =============================================================================",
            "FROM scratch AS output",
            "COPY --from=build-execution /workspace/output/ /output/",
            f'LABEL build.id="{config.build_id}"',
        ])
        
        return "\n".join(dockerfile_lines)
