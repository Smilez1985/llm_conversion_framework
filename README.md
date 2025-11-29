# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-blue.svg)](https://docs.docker.com/get-docker/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-green.svg)]()
[![Version](https://img.shields.io/badge/version-1.3.0-blue.svg)]()

> **Note:** For documentation in German, see [README-de.md](README-de.md).

**Professional Modular Framework for Cross-Compiling Large Language Models on Edge Hardware**

A GUI-based LLM Deployment Framework capable of automating the optimization & quantization of any LLM. Perfectly optimized for any CPU, GPU, or NPU (Rockchip, NVIDIA, etc.).

---

## 🌟 Status: Production Ready (v1.3.0)

The framework has undergone a comprehensive security and architectural audit. It meets enterprise standards regarding modularity, security (Trivy scanning, socket proxy), and stability.

* **Security:** Containers are isolated (Socket Proxy), Docker socket is protected, inputs are sanitized.
* **Modularity:** Clean separation between Orchestrator (Management), Builder (Execution), and Target Modules.
* **AI-Integration:** Optional "Ditto" agent (v1.2) for fully automated generation of new hardware modules.
* **I18n:** Full support for English and German interfaces.

---

## 🗺️ Roadmap

**v1.3.0** (Current)
- ✅ AI Wizard (Ditto Integration) with Auto-Discovery
- ✅ Security Hardening (Socket Proxy, Trivy Scanner)
- ✅ Multi-Provider AI Support (Ollama, OpenAI, Anthropic)
- ✅ NVIDIA GPU Passthrough Support
- ✅ Internationalization (DE/EN)

**v1.4.0** (Q2 2026)
- 🎯 Intel NPU Support (OpenVINO) Full Integration
- 🎯 Hailo NPU Support Full Integration
- 🎯 Auto-Optimization Engine (Grid Search for Quantization)

**v2.0.0** (Q3 2026)
- 🎯 Cloud Build Support (AWS/Azure integration)
- 🎯 Model Zoo Integration (One-Click Deploy)

---

## 📊 Performance Expectations

| Model        | Hardware | Quantization | RAM Usage | Speed (tokens/s) |
| :---         | :---     | :---         | :---      | :---             |
| Granite-350M | RK3566   | Q4_K_M       | ~200MB    | 8-15             |
| Llama-2-7B   | RK3588   | Q4_K_M       | ~4GB      | 5-10             |
| Mistral-7B   | RTX 4090 | INT4 (AWQ)   | ~5GB      | 100+             |

---

## 📥 Installation & Deployment

The framework supports two primary operating modes:

### A. Windows (Workstation / Laptop)
Ideal for development, GUI usage, and testing.

* **Requirements:** Docker Desktop, WSL2.
* **Setup:**
    ```powershell
    # Starts the automated installer (handles dependencies, creates shortcuts)
    python scripts/setup_windows.py
    ```
* Simply launch the created desktop shortcut `LLM-Builder`.

### B. Linux (Server / Headless / Cloud)
Optimized for CI/CD pipelines, build servers (AWS, Hetzner), or local Linux machines. Runs efficiently without a GUI.

* **Requirements:** Docker Engine (`docker-ce`). **No** Docker Desktop required!
* **Setup & Start:**
    ```bash
    # Checks requirements, installs Docker if needed, fixes permissions
    make setup
    
    # Starts the Orchestrator in background (Headless Mode)
    make up
    ```
* Use the CLI afterwards: `docker exec -it llm-orchestrator llm-cli`

---

## ⚙️ Hardware Usage & Performance

The framework intelligently manages available resources based on your target selection.

### Standard: CPU & RAM (Cross-Compilation)
For targets like **Rockchip (RK3588/RK3566)**, the standard container primarily utilizes **CPU and RAM**.

* **Why?** We explicitly install the PyTorch CPU version to keep the Docker image small (~2GB instead of >8GB).
* **Bottleneck:** During quantization (e.g., `llama-quantize`), memory bandwidth is usually the limiting factor, not raw GPU compute. A strong CPU is often more efficient here than the overhead of large GPU containers.

### Option: GPU Acceleration (NVIDIA Jetson / RTX)
The framework core is **GPU-Ready**.

* **The "Hidden Gem":** The Builder (`orchestrator/Core/builder.py`) can pass GPU resources via `DeviceRequest` directly to the build container.
* **How to activate:**
    1.  Select **"Use GPU"** in the GUI Wizard or CLI.
    2.  Ensure the target module uses a GPU-capable base image (e.g., `nvidia/cuda:12.2...`).
    3.  *Tip:* Use the **AI Wizard (Ditto)** – it detects NVIDIA hardware in the probe log and automatically suggests the correct CUDA image.

---

## 🛠️ Features

* **Smart Wizard:** Create new hardware targets in 5 steps.
* **AI Auto-Discovery:** Upload `hardware_probe.sh` output, and the AI configures the module for you (Flags, SDKs, Docker Image).
* **Multi-Target:** Supports Rockchip (NPU), NVIDIA (CUDA), Intel (OpenVINO), and more.
* **Security First:** Integrated Trivy scanner checks every image after build.

## 🏆 Examples

### Rockchip RK3566 Example

```bash
# 1. Create Hardware Profile (on the board)
./hardware_probe.sh
```
```
# 2. Build via CLI (on the host)
llm-cli build start \
  --model "IBM/granite-3b-code-instruct" \
  --target rockchip \
  --quantization Q4_K_M \
  --task LLM
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
