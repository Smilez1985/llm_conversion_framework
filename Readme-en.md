# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-0db7ed.svg)](https://docs.docker.com/get-docker/)
[![Poetry](https://img.shields.io/badge/poetry-1.5+-60A5FA.svg)](https://python-poetry.org/)
[![Platform](https://img.shields.io/badge/platform-win%20%7C%20linux%20%7C%20mac-lightgrey)]()
[![Status](https://img.shields.io/badge/status-production%20ready-green)]()
[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)]()

**Professional modular framework for cross-compiling Large Language Models to edge hardware**

A GUI-based LLM deployment framework that automatically optimizes & quantizes any LLM. Perfectly optimized for every CPU, GPU, or NPU.

---

## 🌟 Status: Production Ready (v1.2.0)

The framework has undergone a comprehensive **Enterprise-Grade Security and Architecture Audit**:

* ✅ **Security:** Container isolation with Socket Proxy, protected Docker socket, input validation, Trivy scanning
* ✅ **Modularity:** Clear separation between Orchestrator (management), Builder (execution), and Target modules
* ✅ **AI Integration:** "Ditto" agent (v1.2) for fully automatic hardware module generation
* ✅ **Multi-Provider Support:** Ollama, OpenAI, Anthropic, and other AI providers
* ✅ **GPU-Ready:** NVIDIA GPU passthrough for accelerated builds

---

## 📖 About the Project

We're solving a problem everyone knows but nobody addresses: Clean, reproducible compilation of LLMs and NPU tools for diverse hardware architectures.

The **LLM Cross-Compiler Framework** isn't just another "installation guide" – it's a Docker-based assembly line. It automatically transforms source code (HuggingFace, llama.cpp, Vosk) into optimized binaries for your target system.

### ✨ What It Does (v1.2.0)

* ✅ Complete cross-compilation for **Rockchip RK3566/RK3588** (including NPU support via RKNN)
* ✅ **Windows installer & GUI** for easy operation without command-line frustration
* ✅ **Single-Source-of-Truth** architecture for reproducible builds
* ✅ **Auto-Update** & **Smart-Sync** technology for seamless updates
* ✅ **AI-Wizard "Ditto"** automatically detects hardware and generates optimized modules
* ✅ **Security Hardening** with Socket Proxy and automatic image scanning
* ✅ **NVIDIA GPU Support** for accelerated quantization and compilation

---

## 🎯 Features

| Feature | Description |
|---------|-------------|
| 🏗️ **Multi-Arch Support** | ARM, x86_64, RISC-V with automatic hardware detection |
| 🐳 **Docker-Native** | Isolated build environments with multi-stage builds (no dependency hell on the host) |
| 🎨 **Professional GUI** | PySide6 interface with integrated **5-step Module Creation Wizard** |
| 🤖 **AI Auto-Discovery** | "Ditto" agent analyzes hardware profile and automatically configures modules (flags, SDKs, Docker images) |
| ⚡ **Live Monitoring** | Real-time display of build logs and progress |
| 🔧 **Hardware-Optimized** | Automatic CPU/GPU/NPU detection with optimized compiler flags (NEON, AVX, CUDA) |
| 🔒 **Security First** | Socket Proxy Protection + Trivy scanner checks every image after build |
| 🌐 **Multi-Provider AI** | Ollama, OpenAI, Anthropic, Google, Azure for AI wizard |
| 🌍 **Community Hub** | Integrated "app store" for downloading new hardware targets |
| 📦 **Auto-Packaging** | Creates ready-to-deploy packages including test scripts for target devices |

---

## 🚀 Quick Start

### Prerequisites

**Windows:**
- Docker Desktop (20.10+) with WSL2
- Python (3.10+)
- Git

**Linux:**
- Docker Engine (`docker-ce`) - No Docker Desktop required!
- Python (3.10+) or Poetry (1.5+)
- Git

> **⚠️ IMPORTANT for Windows Users: Docker Desktop & WSL2**
>
> The framework uses Docker Desktop with WSL2 for all build processes. This is a **mandatory requirement**.
>
> 1. Enable **WSL2** (Windows Subsystem for Linux 2) via PowerShell
> 2. Install the [WSL2 Linux Kernel Update Package](https://wslstore.blob.core.windows.net/wslupdate/wsl_update_x64.msi)
> 3. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
> 4. Ensure **WSL2 integration** is enabled in Docker settings
>
> The framework automatically checks if Docker is running before proceeding with installation.

---

## 📥 Installation & Deployment

The framework supports two primary operating modes:

### A. Windows (Workstation / Laptop)
**Ideal for:** Development, GUI usage, and testing
```powershell
# Automatic installer (downloads dependencies, creates desktop shortcuts)
python scripts/setup_windows.py
```

After installation:
1. Launch **"LLM-Builder"** from desktop
2. The GUI will guide you through the setup process

---

### B. Linux (Server / Headless / Cloud)
**Optimized for:** CI/CD pipelines, build servers (AWS, Hetzner), or local Linux machines. Runs resource-efficiently without GUI.
```bash
# Clone repository
git clone https://github.com/Smilez1985/llm_conversion_framework.git
cd llm_conversion_framework

# Setup (checks prerequisites, installs Docker if needed)
make setup

# Start orchestrator in background
make up

# Use CLI
docker exec -it llm-orchestrator llm-cli --help
```

**Or with Poetry (Developers):**
```bash
# Install dependencies
poetry install

# Build Docker containers
docker-compose build

# Launch GUI
poetry run llm-builder
```

---

## ⚙️ Hardware Utilization & Performance

The framework works intelligently with available resources.

### 🖥️ Standard: CPU & RAM (Cross-Compilation)

For targets like **Rockchip RK3588/RK3566**, the standard container primarily uses **CPU and RAM**.

**Why?**
- PyTorch CPU version keeps Docker image small (~2GB instead of >8GB)
- During quantization, **RAM bandwidth** is often the bottleneck, not GPU compute power
- Powerful CPUs are more efficient here than the overhead of large GPU containers

### 🎮 Option: GPU Acceleration (NVIDIA Jetson / RTX)

The framework is **GPU-ready** at its core!

**The "Hidden Gem":** The Builder (`orchestrator/Core/builder.py`) can pass GPU resources directly to the build container via `DeviceRequest`.

**Activation:**
1. Select **"Use GPU"** option in GUI wizard or CLI
2. Ensure the target module uses a GPU-capable base image (e.g., `nvidia/cuda:12.2...`)
3. **💡 Tip:** Use the **AI-Wizard (Ditto)** – it detects NVIDIA hardware in the probe log and automatically suggests the appropriate CUDA image!

**Performance Expectations:**

| Model | Hardware | Quantization | RAM Usage | Speed (tokens/s) |
|-------|----------|-------------|-----------|------------------|
| Granite-350M | RK3566 | Q4_K_M | ~200MB | 8-15 |
| Llama-2-7B | RK3588 | Q4_K_M | ~4GB | 5-10 |
| Phi-2-2.7B | Pi 5 | Q5_K_M | ~2GB | 3-8 |

---

## 🛠️ Usage

### Step 1: Create Hardware Profile

Run this script on your target system (e.g., Rockchip board) to capture exact hardware capabilities.
```bash
# Execute on your RK3566/target system
curl -O https://raw.githubusercontent.com/Smilez1985/llm_conversion_framework/main/scripts/hardware_probe.sh
chmod +x hardware_probe.sh
./hardware_probe.sh
# -> Creates: target_hardware_config.txt
```

### Step 2: Convert & Build Model

**Via GUI** (recommended):

1. `File` → `Import Hardware Profile` → Select your `target_hardware_config.txt`
2. **Activate AI-Wizard:** The "Ditto" agent automatically analyzes your hardware profile
3. In the **"Build & Monitor"** tab, select your model (e.g., via `Browse HF` button)
4. Choose target (e.g., `rockchip`) and quantization (`Q4_K_M`)
5. Click `Start Build`

**Or via CLI:**
```bash
llm-cli build start \
  --model "IBM/granite-3b-code-instruct" \
  --target rockchip \
  --quantization Q4_K_M \
  --task LLM
```

### Step 3: Deployment

Find the finished package in the `output` folder.
```bash
cd output/packages/granite-3b_q4km_aarch64_latest/

# Copy this folder to your device and run:
./deploy.sh /opt/ai_models/
```

---

## 🏗️ Architecture

### Framework Structure
```
llm-cross-compiler-framework/
├── orchestrator/           # Python Core (GUI, CLI, Manager)
│   ├── gui/                # GUI windows & dialogs
│   ├── Core/               # Business logic (Builder, Config, Model Manager)
│   └── utils/              # Helpers, Updater, Validation
├── targets/                # Hardware modules
│   ├── rockchip/           # ✅ Production-Ready (RK3566/88)
│   ├── _template/          # 📋 Template for new targets
│   └── ...
├── community/              # Community-contributed targets
├── configs/                # Global configurations
└── scripts/                # Setup, build & CI tools
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
  Quantized GGUF       AI-Wizard (Ditto) analyzes
        ↓                           ↓
        └──────→ Cross-Compile ←────┘
                       ↓
                llama-cli (ARM64)
                       ↓
              Deployment Package
                       ↓
              Trivy Security Scan
```

### Supported Hardware

| Family | Status | Architectures | Features |
|---------|--------|---------------|----------|
| **Rockchip** | ✅ Ready | RK3566, RK3568, RK3576, RK3588 | NEON, NPU (RKNN), Cross-Compilation |
| **NVIDIA Jetson** | 🚧 Development | Nano, Xavier NX, Orin | CUDA, TensorRT |
| **Raspberry Pi** | 🚧 Development | Pi 4, Pi 5 | ARM Cortex-A72/A76 |
| **Intel NPU** | 📋 Planned | Meteor Lake | OpenVINO |
| **Hailo** | 📋 Planned | Hailo-8, Hailo-10 | HailoRT |

---

## 🤝 Community & Contributing

We need **YOU** to add support for more hardware!

### Adding a New Target

The framework has an integrated **5-step Module Creation Wizard** with **AI support**:

1. Launch GUI: `llm-builder` (Windows) or `poetry run llm-builder` (Linux)
2. Menu: `Tools` → `Create New Module...`
3. **AI Mode:** Upload your `hardware_probe.sh` output → "Ditto" automatically configures:
   - Optimal compiler flags (NEON, AVX, CUDA)
   - Appropriate Docker base image
   - SDK versions & dependencies
4. Follow the **5 steps** in the wizard
5. The framework automatically generates all necessary scripts (`config_module.sh`, `Dockerfile`, etc.)

**Or manually:**
```bash
cp -r targets/_template targets/my_hardware
# Customize targets/my_hardware/
```

### Pull Requests

1. **Fork** the repository
2. **Create branch:** `git checkout -b feature/my-new-target`
3. **Develop module** using the AI wizard
4. **Add tests** and run them
5. **Create pull request**

### Community Targets

The `community/` directory contains community-contributed hardware targets:

- `community/hailo/` - Hailo NPU support
- `community/intel-npu/` - Intel Meteor Lake NPU
- `community/custom-boards/` - Special hardware

---

## 📊 Status & Roadmap

### Current Status (v1.2.0)

- ✅ **Framework Core** - GUI, CLI, Docker management
- ✅ **Rockchip Target** - Production-ready for RK3566/3588
- ✅ **AI-Wizard "Ditto"** - Automatic hardware detection & module generation
- ✅ **Security Hardening** - Socket Proxy, Trivy scanner, input validation
- ✅ **Multi-Provider AI** - Ollama, OpenAI, Anthropic, Google, Azure
- ✅ **NVIDIA GPU Passthrough** - GPU-accelerated builds

### Roadmap

| Milestone | Status | Planned | Features |
|-------------|--------|---------|----------|
| v1.0.0 (MVP) | ✅ Completed | - | Rockchip RK3566/88, GUI, Docker Core |
| v1.1.0 | ✅ Completed | - | Auto-Updater, AI-Wizard, Smart Sync |
| v1.2.0 | ✅ Completed | - | Security Hardening, Multi-Provider AI, NVIDIA GPU Support |
| v1.3.0 | 📋 Planned | Q2 2026 | Intel NPU (OpenVINO), Hailo NPU, Auto-Optimization Engine |
| v2.0.0 | 📋 Planned | Q3 2026 | Cloud Build Support (AWS/Azure), Model Zoo Integration |

---

## 🏆 Examples

### Rockchip RK3566 Example
```bash
# 1. Create hardware profile (on RK3566)
./hardware_probe.sh

# 2. Build via CLI (on workstation)
llm-cli build start \
  --model "IBM/granite-3b-code-instruct" \
  --target rockchip \
  --quantization Q4_K_M \
  --task LLM

# 3. Output: granite-3b_q4km_aarch64.zip
# Contains: Quantized model + AArch64 binary + test scripts
```

---

## 📚 Documentation

- 📖 [Getting Started Guide](docs/getting-started.md)
- 🔧 [Adding New Targets](docs/adding-targets.md)
- 🤖 [AI-Wizard "Ditto" Guide](docs/ai-wizard.md)
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
- **[Ditto](https://github.com/yoheinakajima/ditto)** - AI agent framework for automatic hardware module generation (developed by [@yoheinakajima](https://github.com/yoheinakajima))
- **[Radxa Community](https://forum.radxa.com/)** - For support with RK3566 integration
- **[Docker](https://www.docker.com/)** - Containerization platform
- **[PySide6](https://doc.qt.io/qtforpython-6/)** - Professional GUI framework
- **[Poetry](https://python-poetry.org/)** - Modern Python dependency management

---

<div align="center">

**Built with ❤️ for the Edge AI Community**

*Empowering developers to run AI everywhere.*

</div>
