# llm_conversion_framework 

Ein GUI-basiertes LLM Deployment Framework, das beliebige LLMs automatisiert optimieren & quantisieren kann. Für jede CPU, GPU oder NPU perfekt optimiert. **MVP: RK3566 Support.**

# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-blue.svg)](https://docs.docker.com/get-docker/)
[![Poetry](https://img.shields.io/badge/poetry-1.5+-blue.svg)](https://python-poetry.org/)

**Professionelles modulares Framework für Cross-Compilation von Large Language Models auf Edge-Hardware**

Eliminiert die Komplexität der Cross-Kompilierung und Quantisierung von LLMs für fragmentierte Edge-Hardware (CPUs, GPUs, NPUs). Community-driven, Docker-basiert, production-ready.

---

**🛠️ Schluss mit Dependency-Hölle: Ein universelles Cross-Compiling Framework für ALLE KI-Hardware.**

Wir haben ein Problem gelöst, das jeder kennt, aber niemand angeht: Die saubere Kompilierung von LLMs und NPU-Tools für unterschiedliche Hardware-Architekturen.

Ich stelle vor: Das **LLM Cross-Compiler Framework**. Es ist keine einfache "Installations-Anleitung", sondern eine Docker-basierte Fertigungsstraße, die Source-Code (HuggingFace, llama.cpp, Vosk) vollautomatisch in optimierte Binaries für dein Zielsystem verwandelt.

### 🚀 Was es kann (MVP):

* Vollständige Cross-Compilation für **Rockchip RK3566/RK3588** (inkl. NPU-Support via RKNN).
* Windows-Installer & GUI für einfache Bedienung.
* Zentrale "Single-Source-of-Truth" Architektur für Repositories.

### 🌍 Wo das Potential liegt (Und wo ich DICH brauche):
Die Architektur ist hardware-agnostisch. Das Framework ist so gebaut, dass es alles kompilieren kann – von kleinen Edge-NPUs bis zu massiven Server-Farmen. Ich besitze nur Rockchip-Hardware, aber das Framework ist bereit für mehr:

* NVIDIA Jetson / Desktop GPUs?
* Intel NPUs / ARCs?
* RISC-V Boards?
* AMD ROCm?

### 🤝 Der Aufruf:
Das Gerüst steht. Die Logik ist solide. Jetzt braucht es die Community, um die Module für eure Hardware zu schreiben. Das System ist modular: Ein neues Target ist nur ein Ordner und ein Dockerfile entfernt.

**Lasst uns den Goldstandard für KI-Deployment bauen. Zusammen.**

👉 **Fork it, build it, push it:** [GitHub Repository](https://github.com/Smilez1985/llm_conversion_framework)

> **⚠️ HINWEIS:** Dieses Projekt ist ein experimenteller Proof-of-Concept (Stand 20.11.2025) und wurde KI-gestützt entwickelt. Tests stehen noch aus.

> **⚠️ HINWEIS:**
> ### Installation von Docker Desktop (Wichtig!)
>
> Das Framework nutzt Docker Desktop mit WSL2 für alle Build-Prozesse. Dies ist eine **zwingende Voraussetzung** und kann nicht vom Framework selbst installiert werden.
>
> 1.  **Aktivieren Sie WSL2** (Windows Subsystem for Linux 2) über die PowerShell.
> 2.  Installieren Sie das [WSL2 Linux-Kernel-Update-Paket](https://wslstore.blob.core.windows.net/wslupdate/wsl_update_x64.msi).
> 3.  Laden Sie [Docker Desktop für Windows](https://docs.docker.com/desktop/install/windows-install/) herunter und installieren Sie es.
> 4.  Stellen Sie in den Docker-Einstellungen sicher, dass die **WSL2-Integration** aktiviert ist.
>
> Das Framework prüft automatisch, ob Docker läuft, bevor die Installation fortgesetzt wird.


---

## 🎯 Features

- 🏗️ **Multi-Architecture Support** - ARM, x86_64, RISC-V mit automatischer Hardware-Erkennung
- 🐳 **Docker-Native** - Isolierte Build-Umgebungen mit Multi-Stage Builds
- 🎨 **Professional GUI** - PySide6 Interface mit 5-Schritt Module Creation Wizard
- ⚡ **Live Monitoring** - Real-time Build Output und Progress Tracking
- 🔧 **Hardware-Optimized** - CPU-spezifische Compiler-Flags und SIMD-Optimierungen
- 🌍 **Community-Ready** - Plugin-System für neue Hardware-Targets
- 📦 **Production Packaging** - Deployment-ready Output mit Test-Scripts
- 🤖 **AI-Assisted** - Automatische Code-Generierung für neue Module

## 🚀 Quick Start

### Prerequisites

- **Docker** 20.10+ mit docker-compose
- **Python** 3.10+
- **Poetry** 1.5+ für Dependency Management
- **Git** für Repository-Verwaltung

### Installation

```bash
# 1. Repository klonen
git clone https://github.com/Smilez1985/llm_conversion_framework.git
cd llm_conversion_framework

# 2. Dependencies installieren
poetry install

# 3. Docker-Container bauen
docker-compose build

# 4. GUI starten
poetry run llm-builder
```

### Erste Schritte

1. **Hardware-Profil erstellen**  auf Ihrem Zielsystem:

```Bash
# Auf Ihrem RK3566/Zielsystem ausführen
curl -O https://raw.githubusercontent.com/Smilez1985/llm_conversion_framework/main/scripts/hardware_probe.sh
chmod +x hardware_probe.sh
./hardware_probe.sh
# Erzeugt: target_hardware_config.txt
```

2. **Modell konvertieren:**
``` Bash
# Via GUI: File → Import Hardware Profile → target_hardware_config.txt hochladen
# Build Configuration → Modell wählen → Target wählen → Build starten

# Oder via CLI:
poetry run llm-cli build \
  --model models/granite-h-350m \
  --target rockchip \
  --quantization Q4_K_M \
  --hardware-profile configs/my_rk3566.txt
```

3. **Deployment:**

```Bash
# Output findet sich in output/packages/
cd output/packages/granite-h-350m_q4km_aarch64_latest/
./deploy.sh /opt/ai_models/
```

## 🏗️ Architektur

### Framework-Struktur
```
llm-cross-compiler-framework/
├── orchestrator/           # Framework Core (GUI + CLI)
├── targets/                # Hardware-spezifische Module
│   ├── rockchip/           # ✅ Radxa/Rockchip (RK3566, RK3588)
│   ├── nvidia-jetson/      # 🚧 NVIDIA Jetson Familie
│   ├── raspberry-pi/       # 🚧 Raspberry Pi Familie
│   └── _template/          # Template für neue Targets
├── community/              # Community-contributed Targets
├── docs/                   # Dokumentation
└── scripts/                # Setup & Deployment Tools
```

### Unterstützte Hardware

| Familie | Status | Architekturen | Features |
|---------|--------|---------------|----------|
| **Rockchip** | ✅ Ready | RK3566, RK3568, RK3576, RK3588 | NEON, Cross-Compilation |
| **NVIDIA Jetson** | 🚧 Development | Nano, Xavier NX, Orin | CUDA, TensorRT |
| **Raspberry Pi** | 🚧 Development | Pi 4, Pi 5 | ARM Cortex-A72/A76 |
| **Intel NPU** | 📋 Planned | Meteor Lake | OpenVINO |
| **Hailo** | 📋 Planned | Hailo-8, Hailo-10 | HailoRT |


Jede Hardware-Familie implementiert 4 standardisierte Module:

```bash
1. source_module.sh    # Environment & Tools Setup
2. config_module.sh    # Hardware Detection & Flags
3. convert_module.sh   # Format Conversion (HF→GGUF)
4. target_module.sh    # Quantization & Packaging
```

**Pipeline-Ablauf:**
```
Input Model → Hardware Profile → Docker Container → Optimized Binary
     ↓              ↓                    ↓                  ↓
  HF/ONNX/PT   target_config.txt   Cross-Compilation   Deployment Package
```

## 🛠️ Development

### Neues Hardware-Target hinzufügen

Das Framework bietet einen **5-Schritt Module Creation Wizard**:

1. **Hardware Identification** - Name, Architektur, SDK, Boards
2. **Docker Environment** - Base OS, Packages, Setup Commands  
3. **Configuration Agent** - Compiler Flags, CMake Flags
4. **Profile Script** - Hardware Detection für Target-Systeme
5. **Summary & Generation** - AI-assisted Code Generation

```bash
# GUI-Wizard starten
poetry run llm-builder
# → "New Module..." → 5-Schritt-Wizard folgen

# Oder manuell:
cp -r targets/_template targets/my_hardware
# targets/my_hardware/ anpassen
```

### Module-Entwicklung Guidelines

**Goldstandard-Direktiven für alle Module:**

**Docker-Container:**
- ✅ Multi-Stage Build verwenden
- ✅ BuildX für Multi-Architektur
- ✅ Hadolint-konforme Syntax
- ✅ Poetry für Python-Dependencies

**Scripts (Shell/Python):**
- ✅ Vollständig funktionsfähig (keine Platzhalter)
- ✅ Robuste `if not exist` Abfragen
- ✅ Professional dokumentiert/kommentiert
- ✅ Isolierte Umgebungen (Container-native)

### Testing

```bash
# Framework-Tests
poetry run pytest

# Target-Validation
./scripts/validate-target.sh targets/rockchip

# Integration-Test
poetry run llm-cli test --target rockchip --model test-model
```

## 📚 Documentation

- 📖 [Getting Started Guide](docs/getting-started.md)
- 🔧 [Adding New Targets](docs/adding-targets.md)
- 📡 [API Reference](docs/api-reference.md)
- 💡 [Examples & Tutorials](docs/examples/)

## 🤝 Community

### Beitragen

1. **Fork** das Repository
2. **Branch** erstellen: `git checkout -b feature/my-hardware-target`
3. **Module entwickeln** mit dem Module Creation Wizard
4. **Tests** hinzufügen und ausführen
5. **Pull Request** erstellen

### Community-Targets

Die `community/` Directory enthält von der Community beigesteuerte Hardware-Targets:

- `community/hailo/` - Hailo NPU Support
- `community/intel-npu/` - Intel Meteor Lake NPU
- `community/custom-boards/` - Spezial-Hardware

### Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/Smilez1985/llm_conversion_framework/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/Smilez1985/llm_conversion_framework/discussions)
- 📧 **Email**: -

## 📊 Status & Roadmap

### Current Status (v1.0.0)
- ✅ **Framework Core** - GUI, CLI, Docker-Management
- ✅ **Rockchip Target** - Production-ready für RK3566/3588
- ✅ **Module Creation Wizard** - Community-ready ??
- ✅ **Documentation** - Complete Getting Started

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

```bash
# Hardware-Profil erstellen (auf RK3566)
./hardware_probe.sh

# Build via CLI
poetry run llm-cli build \
  --model models/granite-h-350m \
  --target rockchip \
  --quantization Q4_K_M \
  --hardware-profile configs/rk3566_profile.txt

# Output: granite-h-350m_q4km_aarch64.zip
# Enthält: Quantisiertes Model + AArch64 Binary + Test Scripts
```

### Performance Expectations

| Model | Hardware | Quantization | RAM Usage | Speed (tokens/s) |
|-------|----------|-------------|-----------|------------------|
| Granite-350M | RK3566 | Q4_K_M | ~200MB | 8-15 |
| Llama-2-7B | RK3588 | Q4_K_M | ~4GB | 5-10 |
| Phi-2-2.7B | Pi 5 | Q5_K_M | ~2GB | 3-8 |

## 📄 License

MIT License - siehe [LICENSE](LICENSE) für Details.

## 🙏 Acknowledgments

- **llama.cpp** - Core quantization and inference engine
- **Hugging Face** - Model ecosystem and transformers
- **Docker** - Containerization platform
- **PySide6** - Professional GUI framework
- **Poetry** - Modern Python dependency management

---

**Built with ❤️ for the AI Community**

*Empowering edge AI development through professional tooling and community collaboration.*
