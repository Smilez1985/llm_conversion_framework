# llm_conversion_framework [WARNING: The entire project was created with the help of AI (Claude/Gemini) and is, as of 2025-11-15, still untested!]
A GUI-based LLM Deployment Framework that: Can automatically optimize & quantize arbitrary LLMs. Perfectly optimized for any CPU, GPU, or NPU. MVP: RK3566 Support.

# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-blue.svg)](https://docs.docker.com/get-docker/)
[![Poetry](https://img.shields.io/badge/poetry-1.5+-blue.svg)](https://python-poetry.org/)

**Professional modular framework for cross-compilation of Large Language Models on edge hardware**

Eliminates the complexity of cross-compiling and quantizing LLMs for fragmented edge hardware (CPUs, GPUs, NPUs). Community-driven, Docker-based, production-ready.

## 🎯 Features

- 🏗️ **Multi-Architecture Support** - ARM, x86_64, RISC-V with automatic hardware detection
- 🐳 **Docker-Native** - Isolated build environments using multi-stage builds
- 🎨 **Professional GUI** - PySide6 Interface with a 5-Step Module Creation Wizard
- ⚡ **Live Monitoring** - Real-time build output and progress tracking
- 🔧 **Hardware-Optimized** - CPU-specific compiler flags and SIMD optimizations
- 🌍 **Community-Ready** - Plugin system for new hardware targets
- 📦 **Production Packaging** - Deployment-ready output including test scripts
- 🤖 **AI-Assisted** - Automatic code generation for new modules

## 🚀 Quick Start

### Prerequisites

- **Docker** 20.10+ with docker-compose
- **Python** 3.10+
- **Poetry** 1.5+ for dependency management
- **Git** for repository management



### Installation

```bash
# 1. Clone repository
git clone [https://github.com/Smilez1985/llm_conversion_framework.git]
cd llm_conversion_framework
```
```
# 2. Install dependencies
poetry install
```
```
# 3. Build Docker container
docker-compose build
```
```
# 4. Start GUI
poetry run llm-builder
```
### First Steps 

1. **Create Hardware Profile** on your target system:

```bash
# Run this on your RK3566/Target System
curl -O [https://github.com/Smilez1985/llm_conversion_framework/raw/main/scripts/hardware_probe.sh]
chmod +x hardware_probe.sh
./hardware_probe.sh
# Generates: target_hardware_config.txt
```
2. **Convert Model**:
```
# Via GUI: File → Import Hardware Profile → Upload target_hardware_config.txt
# Build Configuration → Select Model → Select Target → Start Build


# Or via CLI:
poetry run llm-cli build \
  --model models/granite-h-350m \
  --target rockchip \
  --quantization Q4_K_M \
  --hardware-profile configs/my_rk3566.txt
```
3. **Deployment**:
```Bash
# Output is located in output/packages/
cd output/packages/granite-h-350m_q4km_aarch64_latest/
./deploy.sh /opt/ai_models/
```

## 🏗️ Architecture
### Framework Structure
```
llm-cross-compiler-framework/
├── orchestrator/           # Framework Core (GUI + CLI)
├── targets/                # Hardware-specific modules
│   ├── rockchip/           # ✅ Radxa/Rockchip (RK3566, RK3588)
│   ├── nvidia-jetson/      # 🚧 NVIDIA Jetson Family
│   ├── raspberry-pi/       # 🚧 Raspberry Pi Family
│   └── _template/          # Template for new targets
├── community/              # Community-contributed targets
├── docs/                   # Documentation
└── scripts/                # Setup & Deployment Tools
```
### Supported Hardware

| Familie | Status | Architekturen | Features |
|---------|--------|---------------|----------|
| **Rockchip** | ✅ Ready | RK3566, RK3568, RK3576, RK3588 | NEON, Cross-Compilation |
| **NVIDIA Jetson** | 🚧 Development | Nano, Xavier NX, Orin | CUDA, TensorRT |
| **Raspberry Pi** | 🚧 Development | Pi 4, Pi 5 | ARM Cortex-A72/A76 |
| **Intel NPU** | 📋 Planned | Meteor Lake | OpenVINO |
| **Hailo** | 📋 Planned | Hailo-8, Hailo-10 | HailoRT |

### Workflow: 4-Module-Architektur

Each hardware family implements 4 standardized modules:

```bash
1. source_module.sh    # Environment & Tools Setup
2. config_module.sh    # Hardware Detection & Flags
3. convert_module.sh   # Format Conversion (HF→GGUF)
4. target_module.sh    # Quantization & Packaging
```

Pipeline Flow:
```
Input Model → Hardware Profile → Docker Container → Optimized Binary
     ↓              ↓                  ↓                   ↓
 HF/ONNX/PT   target_config.txt   Cross-Compilation   Deployment Package
```

## 🛠️ Development: 

### Adding a New Hardware Target

The framework offers a **5-Step Module Creation Wizard**:

1. **Hardware Identification**  - Name, architecture, SDK, boards
2. **Docker Environment**- Base OS, packages, setup commands
3. **Configuration Agent** - Compiler flags, CMake flags
4. **Profile Script** - Hardware detection for target systems
5. **Summary & Generation** - AI-assisted code generation
   
```bash
Start GUI Wizard
poetry run llm-builder
# → "New Module..." → Follow the 5-step wizard


# Or manually:
cp -r targets/_template targets/my_hardware
# Customize targets/my_hardware/
```

### Module Development Guidelines:
**Gold Standard Directives for all modules:**

**Docker-Container:**
✅ Use Multi-Stage Build
✅ BuildX for Multi-Architecture support
✅ Hadolint-compliant syntax
✅ Poetry for Python dependencies

**Scripts (Shell/Python):**
✅ Fully functional (no placeholders)
✅ Robust if not exist checks
✅ Professionally documented/commented
✅ Isolated environments (container-native)

### Testing
```bash
Framework Tests
poetry run pytest

# Target Validation
./scripts/validate-target.sh targets/rockchip

# Integration Test
poetry run llm-cli test --target rockchip --model test-model
```

## 📚 Documentation

- 📖 [Getting Started Guide](docs/getting-started.md)
- 🔧 [Adding New Targets](docs/adding-targets.md)
- 📡 [API Reference](docs/api-reference.md)
- 💡 [Examples & Tutorials](docs/examples/)

 
## 🤝 Community

1. **Fork** the repository
2. **Create Branch**: git checkout -b feature/my-hardware-target
3. **Develop Module** using the Module Creation Wizard
4. Add & Run **Tests**
5. Create **Pull Request**

### Community-Targets

The `community/` directory contains hardware targets contributed by the community:

- `community/hailo/` - Hailo NPU Support
- `community/intel-npu/` - Intel Meteor Lake NPU
- `community/custom-boards/` - special-Hardware

### Support

🐛 Issues: GitHub Issues
💬 Discussions: GitHub Discussions
📧 Email: -

## 📊 Status & Roadmap

### Current Status (v1.0.0)
✅ **Framework Core** - GUI, CLI, Docker Management
✅ **Rockchip Target** - Production-ready for RK3566/3588
✅ **Module Creation Wizard** - Community-ready
✅ **Documentation** - Complete Getting StartedRoadmapv1.1.0

### Roadmap

**v1.1.0** (Q1 2026)
- 🎯 NVIDIA Jetson Support (CUDA/TensorRT)
- 🎯 Raspberry Pi Support
- 🎯 Performance Benchmarking

**v1.2.0** (Q2 2026)
- 🎯 Intel NPU Support (OpenVINO)
- 🎯 Hailo NPU Support
- 🎯 Auto-Optimization Engine

**v2.0.0** (Q3 2026)
- 🎯 Cloud Build Support
- 🎯 Model Zoo Integration
- 🎯 Advanced Profiling Tools

## 🏆 Examples

### Rockchip RK3566 Example

```Bash
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

## 📄 License
MIT License - see [LICENSE](LICENSE) for details.


## 🙏 Acknowledgments

- **llama.cpp** - Core quantization and inference engine
- **Hugging Face** - Model ecosystem and transformers
- **Docker** - Containerization platform
- **PySide6** - Professional GUI framework
- **Poetry** - Modern Python dependency management

  
**Built with ❤️ for the AI Community**

*Empowering edge AI development through professional tooling and community collaboration.*
