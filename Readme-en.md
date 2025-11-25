# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-0db7ed.svg)](https://docs.docker.com/get-docker/)
[![Poetry](https://img.shields.io/badge/poetry-1.5+-60A5FA.svg)](https://python-poetry.org/)
[![Platform](https://img.shields.io/badge/platform-win%20%7C%20linux%20%7C%20mac-lightgrey)]()
[![Status](https://img.shields.io/badge/status-production-green)]()

**Professional modular framework for cross-compilation of Large Language Models on edge hardware**

Eliminates the complexity of cross-compiling and quantizing LLMs for fragmented edge hardware (CPUs, GPUs, NPUs). Community-driven, Docker-based, production-ready.

---

## 📖 About the Project

We're solving a problem everyone knows but nobody tackles: Clean, reproducible compilation of LLMs and NPU tools for different hardware architectures.

The **LLM Cross-Compiler Framework** isn't just a simple "installation guide" - it's a Docker-based production line. It automatically transforms source code (HuggingFace, llama.cpp, Vosk) into optimized binaries for your target system.

### ✨ What it delivers (V 1.1.0)

* ✅ Complete cross-compilation for **Rockchip RK3566/RK3588** (including NPU support via RKNN)
* ✅ **Windows Installer & GUI** for easy operation without command-line frustration
* ✅ **Single-Source-of-Truth** architecture for reproducible builds
* ✅ **Auto-Update** & **Smart-Sync** technology for seamless updates

---

## 🎯 Features

| Feature | Description |
|---------|-------------|
| 🏗️ **Multi-Arch Support** | ARM, x86_64, RISC-V with automatic hardware detection |
| 🐳 **Docker-Native** | Isolated build environments with multi-stage builds (No dependency hell on the host) |
| 🎨 **Professional GUI** | PySide6 interface with integrated **5-step Module Creation Wizard** |
| ⚡ **Live Monitoring** | Real-time display of build logs and progress |
| 🔧 **Hardware-Optimized** | Automatically sets CPU-specific flags (NEON, AVX, NPU) for maximum performance |
| 🌍 **Community Hub** | Integrated "App Store" for downloading new hardware targets |
| 📦 **Auto-Packaging** | Creates ready-to-deploy packages including test scripts for the target device |

---

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** (20.10+)
- **Python** (3.10+)
- **Poetry** (1.5+)
- **Git**

> **⚠️ IMPORTANT: Docker Desktop & WSL2 on Windows**
>
> The framework uses Docker Desktop with WSL2 for all build processes. This is a **mandatory requirement**.
>
> 1. Enable **WSL2** (Windows Subsystem for Linux 2) via PowerShell
> 2. Install the [WSL2 Linux Kernel Update Package](https://wslstore.blob.core.windows.net/wslupdate/wsl_update_x64.msi)
> 3. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
> 4. Ensure that **WSL2 integration** is enabled in Docker settings
>
> The framework automatically checks if Docker is running before proceeding with installation.

### Installation
```bash
# 1. Clone repository
git clone https://github.com/Smilez1985/llm_conversion_framework.git
cd llm_conversion_framework

# 2. Install dependencies (via Poetry)
poetry install

# 3. Build Docker containers (initial)
docker-compose build

# 4. Start GUI
poetry run llm-builder
```

---

## 🛠️ Usage

### Step 1: Create Hardware Profile

Run this script on your target system (e.g., the Rockchip board) to accurately capture hardware capabilities.
```bash
# Run on your RK3566/target system
curl -O https://raw.githubusercontent.com/Smilez1985/llm_conversion_framework/main/scripts/hardware_probe.sh
chmod +x hardware_probe.sh
./hardware_probe.sh
# -> Generates: target_hardware_config.txt
```

### Step 2: Convert & Build Model

**Via GUI** (recommended):

1. `File` → `Import Hardware Profile` → Select your `target_hardware_config.txt`
2. In the **"Build & Monitor"** tab, select your model (e.g., via `Browse HF` button)
3. Choose the target (e.g., `rockchip`) and quantization (`Q4_K_M`)
4. Click `Start Build`

**Or via CLI:**
```bash
poetry run llm-cli build \
  --model models/granite-h-350m \
  --target rockchip \
  --quantization Q4_K_M \
  --hardware-profile configs/my_rk3566.txt
```

### Step 3: Deployment

Find the finished package in the `output` folder.
```bash
cd output/packages/granite-h-350m_q4km_aarch64_latest/

# Copy this folder to your device and run:
./deploy.sh /opt/ai_models/
```

---

## 🏗️ Architecture

### Framework Structure
```
llm-cross-compiler-framework/
├── orchestrator/           # Python Core (GUI, CLI, Manager)
│   ├── gui/                # GUI Windows & Dialogs
│   ├── Core/               # Business Logic
│   └── utils/              # Helpers & Updater
├── targets/                # Hardware Modules
│   ├── rockchip/           # ✅ Production-Ready (RK3566/88)
│   ├── _template/          # 📋 Template for new targets
│   └── ...
├── community/              # Community-Contributed Targets
├── configs/                # Global Configurations
└── scripts/                # Setup, Build & CI Tools
```

### Pipeline Flow
```
Input Model (HF/ONNX)
        ↓
    Format Convert
        ↓
    GGUF FP16
        ↓
Quantize (Native x86) ←──── Hardware Profile
        ↓                           ↓
  Quantized GGUF            Config Module
        ↓                           ↓
        └──────→ Cross-Compile ←────┘
                       ↓
                llama-cli (ARM64)
                       ↓
              Deployment Package
```

### Supported Hardware

| Family | Status | Architectures | Features |
|--------|--------|---------------|----------|
| **Rockchip** | ✅ Ready | RK3566, RK3568, RK3576, RK3588 | NEON, Cross-Compilation |
| **NVIDIA Jetson** | 🚧 Development | Nano, Xavier NX, Orin | CUDA, TensorRT |
| **Raspberry Pi** | 🚧 Development | Pi 4, Pi 5 | ARM Cortex-A72/A76 |
| **Intel NPU** | 📋 Planned | Meteor Lake | OpenVINO |
| **Hailo** | 📋 Planned | Hailo-8, Hailo-10 | HailoRT |

---

## 🤝 Community & Contributing

We need **YOU** to add support for more hardware!

### Adding a New Target

The framework has an integrated **5-step Module Creation Wizard**:

1. Start the GUI: `poetry run llm-builder`
2. Menu: `Tools` → `Create New Module...`
3. Follow the **5 steps** (Hardware Info, Docker Setup, Flags, etc.)
4. The framework automatically generates all necessary scripts (`config_module.sh`, `Dockerfile`, etc.)

**Or manually:**
```bash
cp -r targets/_template targets/my_hardware
# Customize targets/my_hardware/
```

### Pull Requests

1. **Fork** the repository
2. **Create branch**: `git checkout -b feature/my-new-target`
3. **Develop module** with the wizard
4. **Add tests** and run them
5. **Create Pull Request**

### Community Targets

The `community/` directory contains community-contributed hardware targets:

- `community/hailo/` - Hailo NPU Support
- `community/intel-npu/` - Intel Meteor Lake NPU
- `community/custom-boards/` - Special Hardware

---

## 📊 Status & Roadmap

### Current Status (v1.1.0)

- ✅ **Framework Core** - GUI, CLI, Docker Management
- ✅ **Rockchip Target** - Production-ready for RK3566/3588
- ✅ **Module Creation Wizard** - 5-step assistant
- ✅ **Auto-Update System** - Smart-Sync technology

### Roadmap

| Milestone | Status | Planned |
|-----------|--------|---------|
| v1.0.0 (MVP) | ✅ | Rockchip RK3566/88 Support, GUI, Docker Core |
| v1.1.0 | ✅ | Auto-Updater, Community Hub, Smart Sync |
| v1.2.0 | 📋 | Intel NPU & Hailo Support |
| v2.0.0 | 📋 | Cloud Build Integration & Auto-Optimization |

---

## 🏆 Examples

### Rockchip RK3566 Example
```bash
# Create hardware profile (on RK3566)
./hardware_probe.sh

# Build via CLI
poetry run llm-cli build \
  --model models/granite-h-350m \
  --target rockchip \
  --quantization Q4_K_M \
  --hardware-profile configs/rk3566_profile.txt

# Output: granite-h-350m_q4km_aarch64.zip
# Contains: Quantized Model + AArch64 Binary + Test Scripts
```

### Performance Expectations

| Model | Hardware | Quantization | RAM Usage | Speed (tokens/s) |
|-------|----------|-------------|-----------|------------------|
| Granite-350M | RK3566 | Q4_K_M | ~200MB | 8-15 |
| Llama-2-7B | RK3588 | Q4_K_M | ~4GB | 5-10 |
| Phi-2-2.7B | Pi 5 | Q5_K_M | ~2GB | 3-8 |

---

## 📚 Documentation

- 📖 [Getting Started Guide](docs/getting-started.md)
- 🔧 [Adding New Targets](docs/adding-targets.md)
- 📡 [API Reference](docs/api-reference.md)
- 💡 [Examples & Tutorials](docs/examples/)

---

## 🛠️ Development

### Testing
```bash
# Framework tests
poetry run pytest

# Target validation
./scripts/validate-target.sh targets/rockchip

# Integration test
poetry run llm-cli test --target rockchip --model test-model
```

### Module Development Guidelines

**Gold standard directives for all modules:**

**Docker Containers:**
- ✅ Use multi-stage builds
- ✅ BuildX for multi-architecture
- ✅ Hadolint-compliant syntax
- ✅ Poetry for Python dependencies

**Scripts (Shell/Python):**
- ✅ Fully functional (no placeholders)
- ✅ Robust `if not exist` checks
- ✅ Professionally documented/commented
- ✅ Isolated environments (container-native)

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **[llama.cpp](https://github.com/ggerganov/llama.cpp)** - The heart of inference
- **[Hugging Face](https://huggingface.co/)** - For the model ecosystem
- **[Radxa Community](https://forum.radxa.com/)** - For support with RK3566 integration
- **[Docker](https://www.docker.com/)** - Containerization platform
- **[PySide6](https://doc.qt.io/qtforpython-6/)** - Professional GUI framework
- **[Poetry](https://python-poetry.org/)** - Modern Python dependency management

---

<div align="center">

**Built with ❤️ for the Edge AI Community**

*Empowering developers to run AI everywhere.*

</div>
