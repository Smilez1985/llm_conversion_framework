# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2025-11-29
### Added
- **Internationalization (I18n):** Complete support for English and German user interfaces.
- **LocalizationManager:** Centralized service for dynamic language switching (`orchestrator/utils/localization.py`).
- **GUI Enhancements:**
    - New Dropdowns for **Task** (LLM, Voice, VLM) and **Quantization** (INT8, INT4, FP16).
    - Added **"Use GPU"** checkbox for NVIDIA Passthrough.
    - Integrated Language Selection Dialog on first start.
- **Dataset Detection:** GUI now auto-detects `dataset.txt` for INT8 quantization or asks the user.

### Changed
- **Refactoring:** Updated all GUI components (`main_window.py`, `wizards.py`, `dialogs.py`) to use dynamic translation keys.
- **Dependencies:** Added `litellm`, `rich`, and `psutil` to `pyproject.toml`.

## [1.2.0] - 2025-11-29
### Added
- **AI Wizard (Ditto):** Integration of AI-powered hardware discovery.
    - `ditto_manager.py`: Analyzes `hardware_probe` output and fetches SDK documentation from SSOT.
    - Generates build logic dynamically (Bash `case` statements).
- **Smart Dispatcher:** New `build.sh` template that dispatches tasks based on Hardware (RK3588 vs RK3566) and Task Type (LLM vs Voice).
- **Templates:** Added `rkllm_module.sh` and `rknn_module.sh` templates for automated module generation.

### Security
- **Socket Proxy:** Replaced direct Docker Socket mount with `tecnativa/docker-socket-proxy` to isolate the Orchestrator.
- **Trivy Scanner:** Integrated `trivy-infra-scanner` service for automated vulnerability checks.
- **Input Validation:** Hardened `hardware_probe.ps1` with C# Native API injection for safe CPU flag detection.

## [1.1.0] - 2025-11-28
### Changed
- **Architecture:** Decoupled Builder from specific target logic. Removed hardcoded `TargetArch` enums.
- **Clean Code:** Removed "Spaghetti Code" (Python inside Bash heredocs).
    - Extracted `export_rkllm.py` and `rknn_converter.py` as standalone scripts.
    - Updated `module_generator.py` to copy physical scripts instead of generating them.
- **Docker:** Removed static `rockchip-builder` service from `docker-compose.yml`. Builders are now spawned dynamically.

### Fixed
- Fixed `setup_windows.py` crashing on list/set operations.
- Fixed missing Cross-Compilers (`gcc-aarch64-linux-gnu`) in Dockerfile templates.

## [1.0.0] - 2025-11-20
### Added
- Initial Release.
- Core Framework structure (Orchestrator, Builder, Docker Manager).
- Basic support for Rockchip RK3588/RK3566 cross-compilation.
- CLI (`llm-cli`) and GUI (`llm-gui`) entry points.
- Hardware Probe scripts for Linux and Windows.
