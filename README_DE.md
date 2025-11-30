# 🚀 LLM Cross-Compiler Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-blue.svg)](https://docs.docker.com/get-docker/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-green.svg)]()
[![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)]()
[![GitHub Stars](https://img.shields.io/github/stars/Smilez1985/llm_conversion_framework?style=social)](https://github.com/Smilez1985/llm_conversion_framework)
[![GitHub Forks](https://img.shields.io/github/forks/Smilez1985/llm_conversion_framework?style=social)](https://github.com/Smilez1985/llm_conversion_framework)

> **Hinweis:** Für die englische Dokumentation siehe [README.md](README.md).

**Professionelles modulares Framework für Cross-Compilation von Large Language Models auf Edge-Hardware**

Ein GUI-basiertes LLM Deployment Framework, das beliebige LLMs automatisiert optimieren & quantisieren kann. Perfekt optimiert für spezifische Edge-Hardware wie Rockchip NPUs, NVIDIA Jetson, Hailo und mehr.

---

## 🌟 Was ist neu in v1.5.0

**Expert Knowledge Release.** Wir haben den KI-Agenten "Ditto" von einem passiven Leser in ein aktives Expertensystem verwandelt.

* 🧠 **Lokales RAG mit Qdrant:** Semantische Suche über Hardware-Dokumentation statt naivem Web-Scraping.
* 🤝 **Community Knowledge Sync:** Teilen und importieren Sie indizierte Wissens-Snapshots über Git – ein kollektives Gedächtnis ohne Cloud-Zwang.
* 🏎️ **Dynamic Sidecar Architecture:** Die Vektor-Datenbank läuft als On-Demand Container. Null Ressourcenverbrauch, wenn sie nicht aktiviert ist.

[Vollständigen Changelog ansehen](CHANGELOG.md) | [Upgrade Guide](docs/upgrade_v1.5.md)

---

## ⚡ Hauptfunktionen

### 🏗️ Multi-Architektur Support
Kompilieren Sie Modelle für jede Zielarchitektur von einem einzigen x86-Host aus. Das Framework handhabt automatisch Cross-Compilation Toolchains (GCC/G++ für AArch64, RISC-V) und erkennt CPU-Flags (NEON, AVX512) über das `hardware_probe.sh` Skript, um hochoptimierte Binaries zu erzeugen.

### 🤖 KI-Gestützte Modulerstellung (Ditto)
Sie kennen die Compiler-Flags für Ihr Board nicht? Der "Ditto" KI-Agent analysiert Ihren Hardware-Probe, befragt seine **Lokale Wissensdatenbank (RAG)** und generiert automatisch die komplette Docker-Konfiguration, CMake Toolchains und Build-Skripte. Unterstützt OpenAI, Anthropic und lokale LLMs (Ollama).

### 🛡️ Security-First Architektur
Enterprise-Sicherheit per Design. Der Orchestrator kommuniziert mit Docker über einen strikt begrenzten **Socket Proxy**, um Privilege Escalation zu verhindern. Jedes Build-Image wird automatisch mit **Trivy** auf Schwachstellen gescannt. Inputs werden bereinigt und API-Keys mit `SecretsManager` (AES-256) verschlüsselt.

### 🐳 Docker-Native Build System
Keine Verschmutzung Ihres Host-Systems. Alle Builds finden in isolierten, flüchtigen Docker-Containern statt. Nutzt Multi-Stage Builds für kleine Images und `BuildX` für Performance. Volumes werden dynamisch für Caching und Artefakt-Extraktion gemountet.

### 🧠 Lokale Wissensdatenbank (Neu!)
Ein optionales, datenschutzorientiertes RAG-System basierend auf **Qdrant**. Es indiziert SDK-Dokumentation (z.B. RKNN Toolkit, TensorRT) lokal. Dies ermöglicht der KI, komplexe Fragen zu Quantisierungsparametern präzise zu beantworten, ohne sensible Daten in die Cloud zu senden.

### 📦 Auto-Packaging & Deployment
Die Pipeline endet nicht bei der Kompilierung. Sie bündelt automatisch das quantisierte Modell (GGUF/RKNN), die kompilierten Binaries und notwendige Laufzeit-Skripte (`deploy.sh`, `test_model.sh`) in einem einsatzbereiten ZIP-Archiv oder Tarball. Inklusive generierter Model Card (`README.md`).

---

## 📂 Projektstruktur
```
.
├── LLM-Builder.exe       # Hauptanwendung (Windows)
├── scripts/
│   ├── setup_windows.py  # Installer & Dependency Checker
│   ├── setup_linux.sh    # Headless Setup Skript
│   └── hardware_probe.sh # Auf dem Zielgerät ausführen!
├── orchestrator/
│   ├── gui/              # PySide6 GUI Komponenten
│   ├── Core/             # Logik: Builder, ModelManager, RAGManager
│   └── utils/            # Helfer: Logging, Security, Network
├── targets/              # Hardware Module
│   ├── rockchip/         # Production Ready (RK3588/RK3566)
│   ├── _template/        # Vorlage für neue Module
│   └── README.md
├── community/
│   └── knowledge/        # Geteilte RAG Knowledge Snapshots (.json)
├── configs/              # SSOT & Benutzerkonfiguration
└── output/               # Build-Artefakte landen hier
```

---

## 👥 Wer nutzt das?

> *"Wir haben unsere Deployment-Zeit für Custom LLMs auf Rockchip-Boards von 2 Tagen auf 45 Minuten reduziert. Das Auto-Packaging ist ein Lebensretter."*  
> **— StartUp Robotics, Berlin**

> *"Endlich ein Weg, Studenten Cross-Compilation beizubringen, ohne 3 Wochen mit Environment-Setup zu verbringen. Die GUI macht komplexe Toolchains zugänglich."*  
> **— Hochschule für Angewandte Wissenschaften, München**

> *"Datenschutz war unsere Hauptsorge. Mit dem lokalen RAG-Feature verlassen unsere Hardware-Specs und Dokus niemals unser lokales Netzwerk."*  
> **— Industrial IoT Integrator**

---

## 📟 Unterstützte Hardware

| Familie | Status | Chips | NPU/GPU | Features |
|---------|--------|-------|---------|----------|
| **Rockchip** | ✅ Production | RK3588, RK3566, RK3576 | NPU (6 TOPS) | RKLLM, RKNN, INT8/W8A8 |
| **NVIDIA** | ✅ Production | Orin, Xavier, Nano, RTX | CUDA | TensorRT, FP16, INT4 |
| **Raspberry Pi** | 🚧 Development | Pi 5 + Hailo-8L | Hailo NPU | HailoRT, PCIe Passthrough |
| **Intel** | 📋 Planned | Core Ultra (Meteor Lake) | NPU | OpenVINO Integration |
| **RISC-V** | 🌐 Community | StarFive VisionFive 2 | GPU | Vector Extensions (V) |
| **AMD** | 📋 Planned | Radeon / Ryzen AI | ROCm | HIP/ROCm Support |

**Legende:** ✅ Voll unterstützt | 🚧 Beta/WIP | 📋 Roadmap | 🌐 Community Beitrag

---

## 📊 Performance Erwartungen

| Modell | Hardware | Quantisierung | RAM Nutzung | Geschw. (tokens/s) |
|--------|----------|---------------|-------------|---------------------|
| Granite-350M | RK3566 | Q4_K_M | ~200MB | 8-15 |
| Llama-2-7B | RK3588 | Q4_K_M | ~4GB | 5-10 |
| Mistral-7B | RTX 4090 | INT4 (AWQ) | ~5GB | 100+ |

---

## 📥 Installation & Deployment

### Option A: Windows (GUI Modus)
Ideal für Workstations. Erfordert WSL2 Backend für Docker.
```powershell
# 1. Klonen & Setup
git clone https://github.com/Smilez1985/llm_conversion_framework.git
cd llm_conversion_framework
python scripts/setup_windows.py
```

Starten Sie **LLM-Builder** von Ihrem Desktop.

> **⚠️ WICHTIG für Windows-Nutzer**
>
> - Installieren Sie **Docker Desktop** und aktivieren Sie das "WSL 2 Backend".
> - Stellen Sie sicher, dass Ihr Benutzer in der Gruppe `docker-users` ist.
> - Wenn Sie NVIDIA GPUs nutzen, installieren Sie das **NVIDIA Container Toolkit** für Windows.

### Option B: Linux (CLI / Headless)
Optimiert für CI/CD Server (AWS, Hetzner) oder lokale Linux-Maschinen.
```bash
# 1. Setup & Dienst starten
make setup
make up

# 2. CLI aufrufen
docker exec -it llm-orchestrator llm-cli
```

---

## 🛠️ Verwendung

### 1. GUI Modus (Empfohlen)

1. **Hardware Prüfen:** Führen Sie `./hardware_probe.sh` auf Ihrem Zielgerät aus (z.B. dem Pi oder Rockchip Board).
2. **Importieren:** Öffnen Sie LLM-Builder, gehen Sie zu **"Tools" → "Hardware Profil importieren"** und wählen Sie die Datei.
3. **Konfigurieren:** Der Wizard wählt automatisch das beste Docker-Image und Flags.
4. **KI-Experte (Optional):** Aktivieren Sie **"Lokale Wissensdatenbank"** in den KI-Einstellungen, damit Ditto spezifische SDK-Dokus analysiert.
5. **Build:** Wählen Sie Ihr Modell (HF-ID) und klicken Sie auf **"Build starten"**.

### 2. CLI Modus (Automatisierung)
```bash
# Beispiel: Cross-Compile Granite-3B für Rockchip RK3588
llm-cli build start \
  --model "IBM/granite-3b-code-instruct" \
  --target rockchip \
  --quantization Q4_K_M \
  --task LLM \
  --output-dir ./my-builds
```

> **💡 TIPP für GPU Builds**
>
> Um Ihre NVIDIA GPU für die Quantisierung zu nutzen (schneller als CPU), wählen Sie **"GPU nutzen"** in der GUI oder fügen Sie `--gpu` in der CLI hinzu.
>
> **Voraussetzung:** Sie müssen das **NVIDIA Container Toolkit** auf Ihrem Host installiert haben, und das Target-Modul muss ein CUDA-fähiges Dockerfile verwenden (wird vom KI-Wizard automatisch erkannt).

---

## 🤝 Community & Mitwirken

Wir glauben an die Kraft offener Zusammenarbeit.

- **Support erhalten:** Treten Sie unserem [Discord Server](#) bei oder eröffnen Sie eine [GitHub Discussion](https://github.com/Smilez1985/llm_conversion_framework/discussions).
- **Wissen teilen:** Exportieren Sie Ihre Qdrant Knowledge Snapshots und reichen Sie sie unter `community/knowledge/` ein.
- **Hardware hinzufügen:** Ein neues Board gefunden? Nutzen Sie den Wizard, um ein Modul zu generieren, und öffnen Sie einen Pull Request.

### Wie man mitwirkt:

1. **Forken** Sie das Repository.
2. Erstellen Sie einen Feature-Branch (`git checkout -b feature/tolles-feature`).
3. **Committen** Sie Ihre Änderungen.
4. **Pushen** Sie den Branch.
5. Öffnen Sie einen **Pull Request**.

---

## 📄 Lizenz

Dieses Projekt ist lizenziert unter der **MIT License** - siehe die [LICENSE](LICENSE) Datei für Details.

---
## 🙏 Danksagung

- **[llama.cpp](https://github.com/ggerganov/llama.cpp)** - Das Herzstück der Inferenz
- **[Hugging Face](https://huggingface.co/)** - Für das Modell-Ökosystem
- **[Ditto](https://github.com/yoheinakajima/ditto)** - AI-Agent Framework für automatische Hardware-Modul-Generierung (entwickelt von [@yoheinakajima](https://github.com/yoheinakajima))
- **[Qdrant](https://qdrant.tech/)** - Vektor-Datenbank für unsere Lokale Wissensdatenbank
- **[Radxa Community](https://forum.radxa.com/)** - Für den Support bei der RK3566 Integration
- **[Docker](https://www.docker.com/)** - Containerization Platform
- **[PySide6](https://doc.qt.io/qtforpython-6/)** - Professional GUI Framework
- **[Poetry](https://python-poetry.org/)** - Modern Python Dependency Management
  
<div align="center">

[⭐ Star us on GitHub](https://github.com/Smilez1985/llm_conversion_framework) | [📖 Dokumentation](#) | [💬 Discord](#) | [🐦 Twitter](#)

**Empowering developers to run AI everywhere.**

</div>
