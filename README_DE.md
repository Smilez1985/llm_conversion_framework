# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-blue.svg)](https://docs.docker.com/get-docker/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-green.svg)]()
[![Version](https://img.shields.io/badge/version-1.3.0-blue.svg)]()

> **Hinweis:** Für die englische Dokumentation siehe [README.md](README.md).

**Professionelles modulares Framework für Cross-Compilation von Large Language Models auf Edge-Hardware**

Ein GUI-basiertes LLM Deployment Framework, das beliebige LLMs automatisiert optimieren & quantisieren kann. Perfekt optimiert für jede CPU, GPU oder NPU (Rockchip, NVIDIA, etc.).

---

## 🌟 Status: Production Ready (v1.3.0)

Das Framework wurde einem umfassenden Sicherheits- und Architektur-Audit unterzogen. Es erfüllt Enterprise-Standards hinsichtlich Modularität, Sicherheit (Trivy Scanning, Socket Proxy) und Stabilität.

* **Sicherheit:** Container sind isoliert (Socket Proxy), Docker-Socket ist geschützt, Inputs werden validiert.
* **Modularität:** Klare Trennung zwischen Orchestrator (Management), Builder (Ausführung) und Target-Modulen.
* **AI-Integration:** Optionaler "Ditto"-Agent (v1.2) zur vollautomatischen Generierung neuer Hardware-Module.
* **I18n:** Vollständige Unterstützung für deutsche und englische Oberflächen.

---

## 🗺️ Roadmap

**v1.3.0** (Aktuell)
- ✅ AI Wizard (Ditto Integration) mit Auto-Discovery
- ✅ Sicherheits-Härtung (Socket Proxy, Trivy Scanner)
- ✅ Multi-Provider AI Support (Ollama, OpenAI, Anthropic)
- ✅ NVIDIA GPU Passthrough Support
- ✅ Internationalisierung (DE/EN)

**v1.4.0** (Q2 2026)
- 🎯 Intel NPU Support (OpenVINO) Vollintegration
- 🎯 Hailo NPU Support Vollintegration
- 🎯 Auto-Optimization Engine (Grid Search für Quantisierung)

**v2.0.0** (Q3 2026)
- 🎯 Cloud Build Support (AWS/Azure Integration)
- 🎯 Model Zoo Integration (One-Click Deploy)

---

## 📊 Performance Erwartungen

| Modell       | Hardware | Quantisierung | RAM Nutzung | Geschw. (tokens/s) |
| :---         | :---     | :---          | :---        | :---               |
| Granite-350M | RK3566   | Q4_K_M        | ~200MB      | 8-15               |
| Llama-2-7B   | RK3588   | Q4_K_M        | ~4GB        | 5-10               |
| Mistral-7B   | RTX 4090 | INT4 (AWQ)    | ~5GB        | 100+               |

---

## 📥 Installation & Deployment

Das Framework unterstützt zwei primäre Betriebsmodi:

### A. Windows (Workstation / Laptop)
Ideal für Entwicklung, GUI-Nutzung und Tests.

* **Voraussetzungen:** Docker Desktop, WSL2.
* **Setup:**
    ```powershell
    # Startet den automatischen Installer (lädt Dependencies, erstellt Shortcuts)
    python scripts/setup_windows.py
    ```
* Starten Sie danach einfach die erstellte Desktop-Verknüpfung `LLM-Builder`.

### B. Linux (Server / Headless / Cloud)
Optimiert für CI/CD-Pipelines, Build-Server (AWS, Hetzner) oder lokale Linux-Maschinen. Läuft effizient ohne GUI.

* **Voraussetzungen:** Docker Engine (`docker-ce`). **Kein** Docker Desktop erforderlich!
* **Setup & Start:**
    ```bash
    # Prüft Voraussetzungen, installiert Docker bei Bedarf und korrigiert Rechte
    make setup
    
    # Startet den Orchestrator im Hintergrund (Headless Mode)
    make up
    ```
* Nutzen Sie danach die CLI: `docker exec -it llm-orchestrator llm-cli`

---

## ⚙️ Hardware-Nutzung & Performance

Das Framework verwaltet verfügbare Ressourcen intelligent basierend auf Ihrer Target-Auswahl.

### Standard: CPU & RAM (Cross-Compilation)
Für Targets wie **Rockchip (RK3588/RK3566)** nutzt der Standard-Container primär **CPU und RAM**.

* **Warum?** Wir installieren explizit die PyTorch-CPU-Version, um das Docker-Image klein zu halten (~2GB statt >8GB).
* **Flaschenhals:** Bei der Quantisierung (z.B. `llama-quantize`) ist meist die Speicherbandbreite der limitierende Faktor, nicht die reine GPU-Rechenleistung. Eine starke CPU ist hier oft effizienter als der Overhead großer GPU-Container.

### Option: GPU-Beschleunigung (NVIDIA Jetson / RTX)
Der Framework-Kern ist **GPU-Ready**.

* **Der "Hidden Gem":** Der Builder (`orchestrator/Core/builder.py`) kann GPU-Ressourcen via `DeviceRequest` direkt an den Build-Container durchreichen.
* **Aktivierung:**
    1.  Wählen Sie **"GPU nutzen"** im GUI-Wizard oder der CLI.
    2.  Stellen Sie sicher, dass das Target-Modul ein GPU-fähiges Basis-Image nutzt (z.B. `nvidia/cuda:12.2...`).
    3.  *Tipp:* Nutzen Sie den **AI-Wizard (Ditto)** – er erkennt NVIDIA-Hardware im Probe-Log und schlägt automatisch das passende CUDA-Image vor.

---

## 🛠️ Features

* **Smart Wizard:** Erstellen Sie neue Hardware-Targets in 5 Schritten.
* **AI Auto-Discovery:** Laden Sie den `hardware_probe.sh` Output hoch, und die KI konfiguriert das Modul für Sie (Flags, SDKs, Docker Image).
* **Multi-Target:** Unterstützt Rockchip (NPU), NVIDIA (CUDA), Intel (OpenVINO) und mehr.
* **Security First:** Integrierter Trivy-Scanner prüft jedes Image nach dem Build.

## 🏆 Beispiele

### Rockchip RK3566 Beispiel

```bash
# 1. Hardware-Profil erstellen (auf dem Board)
./hardware_probe.sh
```
```bash
# 2. Build via CLI (auf dem Host)
llm-cli build start \
  --model "IBM/granite-3b-code-instruct" \
  --target rockchip \
  --quantization Q4_K_M \
  --task LLM
```
```bash
  # 3. Output: granite-3b_q4km_aarch64.zip
# Enthält: Quantisiertes Model + AArch64 Binary + Test Scripts
```



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
# Framework-Tests
poetry run pytest
```
```bash
# Target-Validation
./scripts/validate-target.sh targets/rockchip
```
```bash
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
- **[Ditto](https://github.com/yoheinakajima/ditto)** - AI-Agent Framework für automatische Hardware-Modul-Generierung (entwickelt von [@yoheinakajima](https://github.com/yoheinakajima))
- **[Radxa Community](https://forum.radxa.com/)** - Für den Support bei der RK3566 Integration
- **[Docker](https://www.docker.com/)** - Containerization Platform
- **[PySide6](https://doc.qt.io/qtforpython-6/)** - Professional GUI Framework
- **[Poetry](https://python-poetry.org/)** - Modern Python Dependency Management

---

<div align="center">

**Built with ❤️ for the Edge AI Community**

*Empowering developers to run AI everywhere.*

</div>
