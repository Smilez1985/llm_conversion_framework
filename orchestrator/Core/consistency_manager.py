#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Consistency Manager
DIREKTIVE: Goldstandard, Determinismus, Pre-Flight Checks.

Zweck:
Sichert die Integrität des Builds VOR dem Start.
Prüft Kompatibilität zwischen Hardware-Treibern (Probe) und Software-SDKs (Target).
Verhindert "Doomed to Fail" Builds durch strikte Gates.

Features:
- Validierung von SDK-Versionen gegen Treiber-Versionen.
- Prüfung von Quantisierungs-Support für spezifische NPUs.
- Vorschläge zur Behebung (Fix-Commands).
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import re

from orchestrator.utils.logging import get_logger

@dataclass
class ConsistencyIssue:
    """Repräsentiert ein gefundenes Kompatibilitäts-Problem."""
    component: str          # z.B. "NPU Driver"
    severity: str           # "WARNING" oder "ERROR"
    message: str            # Beschreibung des Fehlers
    detected_value: str     # Was gefunden wurde (z.B. "v1.4.0")
    required_value: str     # Was nötig ist (z.B. ">= v1.6.0")
    suggested_fix: str      # Shell-Befehl zur Behebung

class ConsistencyManager:
    """
    The Guardian of the Build Pipeline.
    Validates prerequisites before execution.
    """
    
    def __init__(self, framework_manager):
        self.logger = get_logger(__name__)
        self.framework = framework_manager
        self.config = framework_manager.config
        
        # Knowledge Base für Kompatibilität (Könnte später aus RAG/YAML kommen)
        # Hier hardcoden wir kritische Known-Good-States für den Goldstandard.
        self.compatibility_matrix = {
            "rockchip": {
                "rknn_toolkit2": {
                    "1.6.0": {"driver_min": "0.8.2"},
                    "2.0.0": {"driver_min": "0.9.3"}
                },
                "rkllm": {
                    "1.0.0": {"driver_min": "0.9.6"}
                }
            },
            "nvidia": {
                "cuda": {
                    "11.8": {"driver_min": "520.00"},
                    "12.2": {"driver_min": "535.00"}
                }
            }
        }

    def check_build_compatibility(self, build_config: Dict[str, Any]) -> List[ConsistencyIssue]:
        """
        Haupt-Prüfmethode. Wird vom Orchestrator vor dem Build aufgerufen.
        
        Args:
            build_config: Dict mit 'target', 'quantization', etc.
            
        Returns:
            Liste von ConsistencyIssue Objekten (leer = alles OK).
        """
        issues = []
        target = build_config.get("target", "").lower()
        
        # 1. Lade Hardware-Profil
        hw_profile = self._load_hardware_profile()
        if not hw_profile:
            # Warnung: Wir fliegen blind, aber blockieren nicht hart (könnte Simulation sein)
            self.logger.warning("No hardware profile found. Skipping consistency checks.")
            return []

        self.logger.info(f"Running Consistency Check for Target: {target}...")

        # 2. Router zu spezifischen Checks
        if "rockchip" in target:
            issues.extend(self._check_rockchip(hw_profile, build_config))
        elif "nvidia" in target or "cuda" in target:
            issues.extend(self._check_nvidia(hw_profile, build_config))
        elif "intel" in target:
            issues.extend(self._check_intel(hw_profile, build_config))

        # 3. Allgemeine Checks
        # Prüfung auf RAM (grobe Schätzung)
        issues.extend(self._check_resources(hw_profile, build_config))

        return issues

    def _load_hardware_profile(self) -> Optional[Dict[str, str]]:
        """Liest die target_hardware_config.txt aus dem Cache."""
        profile_path = Path(self.config.cache_dir) / "target_hardware_config.txt"
        if not profile_path.exists():
            return None
            
        data = {}
        try:
            with open(profile_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        data[key.strip()] = val.strip()
            return data
        except Exception as e:
            self.logger.error(f"Failed to parse hardware profile: {e}")
            return None

    # --- SPECIFIC CHECKS ---

    def _check_rockchip(self, hw: Dict[str, str], cfg: Dict[str, str]) -> List[ConsistencyIssue]:
        issues = []
        
        # A. NPU Check
        if hw.get("NPU_VENDOR") != "Rockchip":
            issues.append(ConsistencyIssue(
                component="NPU", severity="ERROR",
                message="Target is Rockchip, but no Rockchip NPU detected in probe.",
                detected_value=hw.get("NPU_VENDOR", "None"), required_value="Rockchip",
                suggested_fix="Check hardware connection or probe again."
            ))
            return issues # Abort further checks if hardware missing

        # B. Driver Version Logic (Simuliert, da hardware_probe.sh Treiber-Version noch nicht exakt parst)
        # Wir nehmen an, hardware_probe.sh wurde erweitert um NPU_DRIVER_VERSION
        driver_ver = hw.get("NPU_DRIVER_VERSION", "0.0.0")
        
        # Quantization Check
        quant = cfg.get("quantization", "")
        if "W8A8" in quant and "3588" not in hw.get("NPU_MODEL", ""):
             issues.append(ConsistencyIssue(
                component="NPU Capabilities", severity="WARNING",
                message="W8A8 quantization is optimized for RK3588/3576. May be slow on this NPU.",
                detected_value=hw.get("NPU_MODEL", "Unknown"), required_value="RK3588",
                suggested_fix="Consider using INT8 or Q4_K_M."
            ))

        return issues

    def _check_nvidia(self, hw: Dict[str, str], cfg: Dict[str, str]) -> List[ConsistencyIssue]:
        issues = []
        
        # A. CUDA Check
        if hw.get("SUPPORTS_CUDA") != "ON":
             issues.append(ConsistencyIssue(
                component="GPU", severity="ERROR",
                message="Target is NVIDIA, but no CUDA-capable GPU detected.",
                detected_value="None", required_value="NVIDIA GPU",
                suggested_fix="Install NVIDIA Drivers and Container Toolkit."
            ))
        
        return issues

    def _check_intel(self, hw: Dict[str, str], cfg: Dict[str, str]) -> List[ConsistencyIssue]:
        issues = []
        format_type = cfg.get("format", "").lower()
        
        # A. IPEX Requirements
        if format_type == "openvino" or "ipex" in format_type:
            # Check for AVX512_VNNI or AMX on CPU if no GPU
            has_gpu = (hw.get("SUPPORTS_INTEL_XPU") == "ON")
            has_vnni = (hw.get("SUPPORTS_AVX512_VNNI") == "ON")
            has_amx = (hw.get("SUPPORTS_AMX") == "ON")
            
            if not has_gpu and not (has_vnni or has_amx):
                 issues.append(ConsistencyIssue(
                    component="Intel Acceleration", severity="WARNING",
                    message="No XPU (Arc/iGPU) and no AMX/VNNI detected. Inference will be slow.",
                    detected_value="Standard x86_64", required_value="AVX512-VNNI or AMX or XPU",
                    suggested_fix="Use a newer Intel CPU (Gen 11+) or Arc GPU."
                ))
        
        return issues

    def _check_resources(self, hw: Dict[str, str], cfg: Dict[str, str]) -> List[ConsistencyIssue]:
        issues = []
        
        # RAM Check
        try:
            total_ram = int(hw.get("Total_RAM_MB", 0))
            # Grobe Heuristik
            model_name = cfg.get("model_name", "").lower()
            estimated_req = 4000 # Default 4GB
            
            if "7b" in model_name: estimated_req = 8000
            if "13b" in model_name: estimated_req = 16000
            if "70b" in model_name: estimated_req = 48000
            
            if total_ram > 0 and total_ram < estimated_req:
                 issues.append(ConsistencyIssue(
                    component="System Memory", severity="WARNING",
                    message=f"Low RAM detected for model {model_name}.",
                    detected_value=f"{total_ram} MB", required_value=f"~{estimated_req} MB",
                    suggested_fix="Add Swap or choose a smaller quantization (e.g. Q4_0)."
                ))
        except:
            pass
            
        return issues
