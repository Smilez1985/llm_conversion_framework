# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-blue.svg)](https://docs.docker.com/get-docker/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-green.svg)]()
[![Version](https://img.shields.io/badge/version-1.7.0-blue.svg)]()
[![GitHub Stars](https://img.shields.io/github/stars/Smilez1985/llm_conversion_framework?style=social)](https://github.com/Smilez1985/llm_conversion_framework)
[![GitHub Forks](https://img.shields.io/github/forks/Smilez1985/llm_conversion_framework?style=social)](https://github.com/Smilez1985/llm_conversion_framework)

> **Note:** For documentation in German, see [README_DE.md](README_DE.md).

**Professional Modular Framework for Cross-Compiling Large Language Models on Edge Hardware**

A GUI-based LLM Deployment Framework capable of automating the optimization & quantization of any LLM. Perfectly optimized for specific Edge-Hardware like Rockchip NPUs, NVIDIA Jetson, Intel Arc/NPU, and more.

---

## 🌟 What's New in v1.7.0

**Hardware & Deployment Update.** We bridged the gap between "Building" and "Running".

* 🚢 **Zero-Dependency Deployment:** Deploy your optimized models directly to edge devices via SSH/SCP – no Ansible required. Credentials stay in RAM.
* 🏎️ **Intel Ecosystem Support:** Full native support for **Intel IPEX-LLM** and **OpenVINO**. Run LLMs on Intel Arc GPUs, Iris Xe, and Core Ultra NPUs with ease.
* 📊 **Live Resource Monitoring:** Watch CPU and RAM usage of your build containers in real-time directly in the GUI. No external tools needed.
* 📦 **Golden Artifacts:** Every build automatically generates a deployment-ready ZIP package containing the model, runtimes, and a generated Model Card.

[View Full Changelog](CHANGELOG.md) | [Upgrade Guide](docs/upgrade_v1.7.md)

---

## ⚡ Key Features

### 🏗️ Multi-Architecture Support
Compile models for any target architecture from a single x86 host. The framework automatically handles cross-compilation toolchains (GCC/G++ for AArch64, RISC-V) and detects CPU flags (NEON, AVX512, **AVX512-VNNI, AMX**) via the `hardware_probe.sh` (Linux) or `hardware_probe.ps1` (Windows) scripts.

### 🤖 AI-Powered Module Creation (Ditto)
Don't know the compiler flags for your specific board? The "Ditto" AI Agent analyzes your hardware probe, queries its **Local Knowledge Base (RAG)**, and automatically generates the complete Docker configuration.

### 🚀 Zero-Dependency Deployment (New!)
Push your optimized models to the edge with a single click.
* **Secure:** Passwords are never stored on disk (RAM only).
* **Robust:** "Network Guard" technology pauses the transfer if the connection drops and resumes automatically.
* **Simple:** Generates a `deploy.sh` on the target that handles setup and execution.

### 🛡️ Security-First Architecture
Enterprise-grade security by design. The Orchestrator communicates with Docker via a strictly confined **Socket Proxy**. Every build image is scanned for vulnerabilities using **Trivy**. Inputs are sanitized, and API keys are AES-256 encrypted.

### 🐳 Docker-Native Build System
No pollution of your host system. All builds happen in isolated, transient Docker containers. Uses multi-stage builds to keep images small and `BuildX` for performance. Supports **GPU Passthrough** for both NVIDIA (CUDA) and Intel (VAAPI/Level Zero).

### 🧠 Local Knowledge Base (RAG)
An optional, privacy-focused RAG system based on **Qdrant**. It indexes SDK documentation locally. This allows the AI to answer complex questions about quantization parameters accurately without sending data to the cloud.

---

## 📂 Project Structure

```text
.
├── LLM-Builder.exe       # Main Entry Point (Windows)
├── assets/               # UI Resources (Ditto Avatars, Icons)
├── scripts/
│   ├── setup_windows.py  # Installer & Dependency Checker
│   ├── setup_linux.sh    # Headless Setup Script
│   ├── hardware_probe.sh # Probe for Linux Targets
│   └── hardware_probe.ps1# Probe for Windows Targets
├── orchestrator/
│   ├── gui/              # PySide6 GUI Components
│   ├── Core/             # Logic: Builder, DockerManager, RAGManager, DeploymentManager
│   └── utils/            # Helpers: Logging, Security, Network
├── targets/              # Hardware Modules
│   ├── Rockchip/         # Production Ready (RK3588/RK3566)
│   ├── _template/        # Template for new modules
│   └── README.md
├── community/
│   └── knowledge/        # Shared RAG Knowledge Snapshots (.json)
├── configs/              # SSOT & User Configs
└── output/               # Build Artifacts & Golden Packages appear here
```

## 📟 Supported Hardware

| Family | Status | Chips | NPU/GPU | Features |
|--------|--------|-------|---------|----------|
| **Rockchip** | ✅ Production | RK3588, RK3566, RK3576 | NPU (6 TOPS) | RKLLM, RKNN, INT8/W8A8 |
| **NVIDIA** | ✅ Production | Orin, Xavier, Nano, RTX | CUDA | TensorRT, FP16, INT4 |
| **Raspberry Pi** | 🚧 Development | Pi 5 + Hailo-8L | Hailo NPU | HailoRT, PCIe Passthrough |
| **Intel** | 📋 Planned | Core Ultra (Meteor Lake) | NPU | OpenVINO Integration |
| **RISC-V** | 🌐 Community | StarFive VisionFive 2 | GPU | Vector Extensions (V) |
| **AMD** | 📋 Planned | Radeon / Ryzen AI | ROCm | HIP/ROCm Support |

**Legend:** ✅ Fully Supported | 🚧 Beta/WIP | 📋 Roadmap | 🌐 Community Contributed

---

## 📊 Performance Expectations

| Model | Hardware | Quantization | RAM Usage | Speed (tokens/s) |
|-------|----------|--------------|-----------|------------------|
| Granite-350M | RK3566 | Q4_K_M | ~200MB | 8-15 |
| Llama-2-7B | RK3588 | Q4_K_M | ~4GB | 5-10 |
| Mistral-7B | RTX 4090 | INT4 (AWQ) | ~5GB | 100+ |

---

## 📥 Installation & Deployment

### Option A: Windows (GUI Mode)
Ideal for workstations. Requires WSL2 Backend for Docker.
```powershell
# 1. Clone & Setup
git clone https://github.com/Smilez1985/llm_conversion_framework.git
cd llm_conversion_framework
python scripts/setup_windows.py
```

Launch **LLM-Builder** from your Desktop.

> **⚠️ IMPORTANT for Windows Users**
>
> - Install **Docker Desktop** and enable the "WSL 2 Backend".
> - Ensure your user is in the `docker-users` group.
> - If you use NVIDIA GPUs, install the **NVIDIA Container Toolkit** for Windows.

### Option B: Linux (CLI / Headless)
Optimized for CI/CD servers (AWS, Hetzner) or local Linux machines.
```bash
# 1. Setup & Start Service
make setup
make up

# 2. Access CLI
docker exec -it llm-orchestrator llm-cli
```

---

## 🛠️ Usage Guide

### 1. GUI Mode (Recommended)

1. **Probe Hardware:** Run `./hardware_probe.sh` on your target device (e.g., the Pi or Rockchip board).
2. **Import:** Open LLM-Builder, go to **"Tools" → "Import Hardware Profile"** and select the generated file.
3. **Configure:** The Wizard will auto-select the best Docker image and Flags.
4. **AI Expert (Optional):** Enable **"Local Knowledge Base"** in AI Settings to let Ditto analyze specific SDK docs.
5. **Build:** Select your Model (HF-ID) and click **"Start Build"**.

### 2. CLI Mode (Automation)
```bash
# Example: Cross-compile Granite-3B for Rockchip RK3588
llm-cli build start \
  --model "IBM/granite-3b-code-instruct" \
  --target rockchip \
  --quantization Q4_K_M \
  --task LLM \
  --output-dir ./my-builds
```

> **💡 TIP for GPU Builds**
>
> To use your NVIDIA GPU for quantization (faster than CPU), select **"Use GPU"** in the GUI or add `--gpu` in the CLI.
>
> **Requirement:** You must have the **NVIDIA Container Toolkit** installed on your host, and the target module must use a CUDA-enabled Dockerfile (handled automatically by the AI Wizard).

---

## 🤝 Community & Contribution

We believe in the power of open collaboration.

- **Get Support:** Join our [Discord Server](#) or open a [GitHub Discussion](https://github.com/Smilez1985/llm_conversion_framework/discussions).
- **Share Knowledge:** Export your Qdrant Knowledge Snapshots and submit them to `community/knowledge/`.
- **Add Hardware:** Found a new board? Use the Wizard to generate a module and open a Pull Request.

### How to Contribute:

1. **Fork** the repository.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. **Commit** your changes.
4. **Push** to the branch.
5. Open a **Pull Request**.

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---
## 🙏 Acknowledgments

- **[llama.cpp](https://github.com/ggerganov/llama.cpp)** - The heart of inference
- **[Hugging Face](https://huggingface.co/)** - For the model ecosystem
- **[Ditto](https://github.com/yoheinakajima/ditto)** - AI agent framework for automatic hardware module generation (developed by [@yoheinakajima](https://github.com/yoheinakajima))
- **[Qdrant](https://qdrant.tech/)** - Vector database powering our Local Knowledge Base
- **[Radxa Community](https://forum.radxa.com/)** - For support with RK3566 integration
- **[Docker](https://www.docker.com/)** - Containerization platform
- **[PySide6](https://doc.qt.io/qtforpython-6/)** - Professional GUI framework
- **[Poetry](https://python-poetry.org/)** - Modern Python dependency management
- 
<div align="center">

[⭐ Star us on GitHub](https://github.com/Smilez1985/llm_conversion_framework) | [📖 Documentation](#) | [💬 Discord](#) | [🐦 Twitter](#)

**Empowering developers to run AI everywhere.**


</div>
