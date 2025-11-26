# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-0db7ed.svg)](https://docs.docker.com/get-docker/)
[![Poetry](https://img.shields.io/badge/poetry-1.5+-60A5FA.svg)](https://python-poetry.org/)
[![Platform](https://img.shields.io/badge/platform-win%20%7C%20linux%20%7C%20mac-lightgrey)]()
[![Status](https://img.shields.io/badge/status-production-green)]()

**Professionelles modulares Framework für die Cross-Compilation von Large Language Models auf Edge-Hardware**

Eliminiert die Komplexität der Cross-Kompilierung und Quantisierung von LLMs für fragmentierte Edge-Hardware (CPUs, GPUs, NPUs). Community-driven, Docker-basiert, production-ready.

---

## 📖 Über das Projekt

Wir lösen ein Problem, das jeder kennt, aber niemand angeht: Die saubere, reproduzierbare Kompilierung von LLMs und NPU-Tools für unterschiedliche Hardware-Architekturen.

Das **LLM Cross-Compiler Framework** ist keine einfache "Installations-Anleitung", sondern eine Docker-basierte Fertigungsstraße. Es verwandelt Source-Code (HuggingFace, llama.cpp, Vosk) vollautomatisch in optimierte Binaries für dein Zielsystem.

### ✨ Was es leistet (V 1.1.0)

* ✅ Vollständige Cross-Compilation für **Rockchip RK3566/RK3588** (inkl. NPU-Support via RKNN)
* ✅ **Windows-Installer & GUI** für einfache Bedienung ohne Kommandozeilen-Frust
* ✅ **Single-Source-of-Truth** Architektur für reproduzierbare Builds
* ✅ **Auto-Update** & **Smart-Sync** Technologie für nahtlose Updates

---

## 🎯 Features

| Feature | Beschreibung |
|---------|--------------|
| 🏗️ **Multi-Arch Support** | ARM, x86_64, RISC-V mit automatischer Hardware-Erkennung |
| 🐳 **Docker-Native** | Isolierte Build-Umgebungen mit Multi-Stage Builds (Keine Dependency-Hölle auf dem Host) |
| 🎨 **Profi-GUI** | PySide6 Interface mit integriertem **5-Schritt Module Creation Wizard** |
| ⚡ **Live Monitoring** | Echtzeit-Anzeige von Build-Logs und Fortschritt |
| 🔧 **Hardware-Optimiert** | Setzt automatisch CPU-spezifische Flags (NEON, AVX, NPU) für maximale Performance |
| 🌍 **Community Hub** | Integrierter "App Store" zum Herunterladen neuer Hardware-Targets |
| 📦 **Auto-Packaging** | Erstellt fertige Deployment-Pakete inkl. Test-Skripten für das Zielgerät |

---

## 🚀 Quick Start

### Voraussetzungen

- **Docker Desktop** (20.10+)
- **Python** (3.10+)
- **Poetry** (1.5+)
- **Git**

> **⚠️ WICHTIG: Docker Desktop & WSL2 unter Windows**
>
> Das Framework nutzt Docker Desktop mit WSL2 für alle Build-Prozesse. Dies ist eine **zwingende Voraussetzung**.
>
> 1. Aktiviere **WSL2** (Windows Subsystem for Linux 2) über die PowerShell
> 2. Installiere das [WSL2 Linux-Kernel-Update-Paket](https://wslstore.blob.core.windows.net/wslupdate/wsl_update_x64.msi)
> 3. Installiere [Docker Desktop für Windows](https://docs.docker.com/desktop/install/windows-install/)
> 4. Stelle in den Docker-Einstellungen sicher, dass die **WSL2-Integration** aktiviert ist
>
> Das Framework prüft automatisch, ob Docker läuft, bevor die Installation fortgesetzt wird.

### Installation (Windows - Empfohlen)
1. Lade den neuesten [Installer (setup.exe)](Platzhalter-Link-zur-exe) herunter.
2. Führe die Installation aus.
3. Starte "LLM-Builder" vom Desktop.

### Installation (Entwickler / Linux)
```bash
# 1. Repository klonen
git clone https://github.com/Smilez1985/llm_conversion_framework.git
cd llm_conversion_framework

# 2. Dependencies installieren (via Poetry)
poetry install

# 3. Docker-Container bauen (Initial)
docker-compose build

# 4. GUI starten
poetry run llm-builder
```

---

## 🛠️ Verwendung

### Schritt 1: Hardware-Profil erstellen

Führe dieses Skript auf deinem Zielsystem (z.B. dem Rockchip Board) aus, um die Hardware-Fähigkeiten exakt zu erfassen.
```bash
# Auf deinem RK3566/Zielsystem ausführen
curl -O https://raw.githubusercontent.com/Smilez1985/llm_conversion_framework/main/scripts/hardware_probe.sh
chmod +x hardware_probe.sh
./hardware_probe.sh
# -> Erzeugt: target_hardware_config.txt
```

### Schritt 2: Modell konvertieren & bauen

**Via GUI** (empfohlen):

1. `File` → `Import Hardware Profile` → Wähle deine `target_hardware_config.txt`
2. Wähle im Tab **"Build & Monitor"** dein Modell (z.B. via `Browse HF` Button)
3. Wähle das Ziel (z.B. `rockchip`) und die Quantisierung (`Q4_K_M`)
4. Klicke `Start Build`

**Oder via CLI:**
```bash
poetry run llm-cli build \
  --model models/granite-h-350m \
  --target rockchip \
  --quantization Q4_K_M \
  --hardware-profile configs/my_rk3566.txt
```

### Schritt 3: Deployment

Das fertige Paket findest du im `output` Ordner.
```bash
cd output/packages/granite-h-350m_q4km_aarch64_latest/

# Kopiere diesen Ordner auf dein Gerät und führe aus:
./deploy.sh /opt/ai_models/
```

---

## 🏗️ Architektur

### Framework-Struktur
```
llm-cross-compiler-framework/
├── orchestrator/           # Python Core (GUI, CLI, Manager)
│   ├── gui/                # GUI Fenster & Dialoge
│   ├── Core/               # Geschäftslogik
│   └── utils/              # Helper & Updater
├── targets/                # Hardware-Module
│   ├── rockchip/           # ✅ Production-Ready (RK3566/88)
│   ├── _template/          # 📋 Vorlage für neue Targets
│   └── ...
├── community/              # Community-Contributed Targets
├── configs/                # Globale Konfigurationen
└── scripts/                # Setup, Build & CI Tools
```

### Pipeline-Ablauf
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

### Unterstützte Hardware

| Familie | Status | Architekturen | Features |
|---------|--------|---------------|----------|
| **Rockchip** | ✅ Ready | RK3566, RK3568, RK3576, RK3588 | NEON, Cross-Compilation |
| **NVIDIA Jetson** | 🚧 Development | Nano, Xavier NX, Orin | CUDA, TensorRT |
| **Raspberry Pi** | 🚧 Development | Pi 4, Pi 5 | ARM Cortex-A72/A76 |
| **Intel NPU** | 📋 Planned | Meteor Lake | OpenVINO |
| **Hailo** | 📋 Planned | Hailo-8, Hailo-10 | HailoRT |

---

## 🤝 Community & Beitragen

Wir brauchen **DICH**, um Unterstützung für weitere Hardware hinzuzufügen!

### Neues Target hinzufügen

Das Framework besitzt einen integrierten **5-Schritt Module Creation Wizard**:

1. Starte die GUI: `poetry run llm-builder`
2. Menü: `Tools` → `Create New Module...`
3. Folge den **5 Schritten** (Hardware Info, Docker Setup, Flags, etc.)
4. Das Framework generiert automatisch alle notwendigen Skripte (`config_module.sh`, `Dockerfile`, etc.)

**Oder manuell:**
```bash
cp -r targets/_template targets/my_hardware
# targets/my_hardware/ anpassen
```

### Pull Requests

1. **Fork** das Repository
2. **Branch** erstellen: `git checkout -b feature/my-new-target`
3. **Module entwickeln** mit dem Wizard
4. **Tests** hinzufügen und ausführen
5. **Pull Request** erstellen

### Community-Targets

Die `community/` Directory enthält von der Community beigesteuerte Hardware-Targets:

- `community/hailo/` - Hailo NPU Support
- `community/intel-npu/` - Intel Meteor Lake NPU
- `community/custom-boards/` - Spezial-Hardware

---

## 📊 Status & Roadmap

### Current Status (v1.1.0)

- ✅ **Framework Core** - GUI, CLI, Docker-Management
- ✅ **Rockchip Target** - Production-ready für RK3566/3588
- ✅ **Module Creation Wizard** - 5-Schritt Assistent
- ✅ **Auto-Update System** - Smart-Sync Technologie

### Roadmap

| Meilenstein | Status | Geplant |
|-------------|--------|---------|
| v1.0.0 (MVP) | ✅ | Rockchip RK3566/88 Support, GUI, Docker-Core |
| v1.1.0 | ✅ | Auto-Updater, Community Hub, Smart Sync |
| v1.2.0 | 📋 | Intel NPU & Hailo Support |
| v2.0.0 | 📋 | Cloud Build Integration & Auto-Optimization |

---

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
# Framework-Tests
poetry run pytest

# Target-Validation
./scripts/validate-target.sh targets/rockchip

# Integration-Test
poetry run llm-cli test --target rockchip --model test-model
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

---

## 📄 Lizenz

Dieses Projekt ist lizenziert unter der **MIT License** - siehe die [LICENSE](LICENSE) Datei für Details.

---

## 🙏 Danksagung

- **[llama.cpp](https://github.com/ggerganov/llama.cpp)** - Das Herzstück der Inferenz
- **[Hugging Face](https://huggingface.co/)** - Für das Modell-Ökosystem
- **[Radxa Community](https://forum.radxa.com/)** - Für den Support bei der RK3566 Integration
- **[Docker](https://www.docker.com/)** - Containerization Platform
- **[PySide6](https://doc.qt.io/qtforpython-6/)** - Professional GUI Framework
- **[Poetry](https://python-poetry.org/)** - Modern Python Dependency Management

---

<div align="center">

**Built with ❤️ for the Edge AI Community**

*Empowering developers to run AI everywhere.*

</div>
