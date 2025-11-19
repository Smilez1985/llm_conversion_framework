# 🚀 Projekt-Quellen: LLM Cross-Compiler Framework

Dies ist die zentrale Referenzdatei für alle externen Repositories, SDKs und Modellquellen, die in diesem Projekt verwendet werden.

---

## 🧠 Core LLM & Inferenz-Engines

### 1. llama.cpp
Das Fundament für CPU-basierte Inferenz (Kompilierung und Quantisierung).
* **Git-Link:** `https://github.com/ggerganov/llama.cpp.git`

### 2. Hugging Face Transformers
Wird für die HF-zu-GGUF-Konvertierung (Python-Skripte) benötigt.
* **Git-Link:** `https://github.com/huggingface/transformers`
* **PyPI:** `pip install transformers`

---

## 🤖 Rockchip NPU Toolkits (RK3566)

Dies sind die entscheidenden, aber schwer zu findenden SDKs für die 1TOPS NPU des RK3566.

### 1. RKLLM-Toolkit (Für LLMs)
Das primäre Toolkit, das Sie für die NPU-Beschleunigung von *Large Language Models* (wie Granite oder Piper-TTS) benötigen.
* **Git-Link:** `https://github.com/airockchip/rknn-llm`
* **Zweck:** Konvertiert GGUF- oder HF-Modelle in das `.rkllm`-Format für die NPU.

### 2. RKNN-Toolkit2 (Für allgemeine AI-Modelle)
Wird für traditionelle KI-Modelle (z.B. Computer Vision, VAD) benötigt.
* **Git-Link:** `https://github.com/airockchip/rknn-toolkit2`
* **Zweck:** Konvertiert Modelle (ONNX, Tflite) in das `.rknn`-Format.

---

## 🔊 Voice & TTS-Komponenten

### 1. Piper-TTS
Die von Ihnen gewählte TTS-Engine für die GLaDOS-Stimme.
* **Git-Link:** `https://github.com/rhasspy/piper`

### 2. GLaDOS-TTS (Referenz)
Das originale GLaDOS-Stimmmodell-Repo, das Sie integrieren.
* **Git-Link:** `https://github.com/dnhkng/GLaDOS`

---

## 📦 Modell-Quellen (MVP)

### 1. IBM Granite (LLM)
Das von Ihnen ausgewählte, optimierte LLM für den Start.
* **HF-Link:** `https://huggingface.co/ibm-granite/granite-4.0-h-350m`