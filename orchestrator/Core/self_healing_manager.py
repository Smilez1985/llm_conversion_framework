#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Self-Healing Manager
DIREKTIVE: Goldstandard, Autonome Fehlerbehebung.

Zweck:
Analysiert Build-Fehler und Hardware-Inkompatibilitäten.
Nutzt Ditto (AI), um Lösungen (Shell-Commands) zu generieren.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from orchestrator.utils.logging import get_logger

@dataclass
class HealingProposal:
    """Vorschlag zur Fehlerbehebung."""
    error_summary: str
    root_cause: str
    fix_command: str
    is_remote_fix: bool = False # True = Muss auf Target (SSH) laufen, False = Lokal/Docker
    confidence_score: float = 0.0

class SelfHealingManager:
    """
    The 'Doctor' of the framework.
    Diagnoses errors and prescribes CLI commands.
    """
    
    def __init__(self, framework_manager):
        self.logger = get_logger(__name__)
        self.framework = framework_manager
        self.ditto = None # Lazy init

    def _get_ditto(self):
        if not self.ditto:
            # Versuche Ditto aus dem Framework zu holen (falls instanziiert)
            # Sonst temporär erstellen (für Offline-Analyse)
            if hasattr(self.framework, 'ditto_manager') and self.framework.ditto_manager:
                self.ditto = self.framework.ditto_manager
            else:
                # Fallback: Versuche Import
                try:
                    from orchestrator.Core.ditto_manager import DittoCoder
                    self.ditto = DittoCoder(config_manager=self.framework.config, framework_manager=self.framework)
                except Exception as e:
                    self.logger.error(f"Could not init Ditto for healing: {e}")
        return self.ditto

    def analyze_error(self, error_log: str, context: str = "") -> Optional[HealingProposal]:
        """
        Analysiert einen Fehlertext und generiert einen Heilungsvorschlag.
        """
        ditto = self._get_ditto()
        if not ditto:
            return None

        self.logger.info("Starting AI Error Analysis (Self-Healing)...")
        
        # Kürze Log auf die letzten relevanten Zeilen (Token Limit)
        log_tail = error_log[-4000:] if len(error_log) > 4000 else error_log
        
        # Prompt Construction
        system_prompt = """
        You are the Self-Healing Module of an Embedded AI Build System.
        Analyze the provided BUILD ERROR LOG.
        
        TASK:
        1. Identify the root cause (e.g. missing library, wrong driver version, permission denied).
        2. Generate a precise SHELL COMMAND to fix it.
        3. Determine if the fix must run on the HOST (Docker/Linux) or the TARGET DEVICE (Edge).
        
        OUTPUT FORMAT (JSON ONLY):
        {
            "summary": "Short error description",
            "root_cause": "Technical explanation",
            "fix_command": "sudo apt-get install x / pip install y",
            "target": "HOST" or "DEVICE",
            "confidence": 0.95
        }
        
        RULES:
        - If you cannot determine a fix, return null for fix_command.
        - Be conservative. High confidence only for known issues.
        """
        
        user_prompt = f"""
        CONTEXT: {context}
        
        ERROR LOG:
        {log_tail}
        """
        
        try:
            # Wir nutzen Dittos interne LLM-Schnittstelle (Cloud oder Offline)
            # Da DittoManager.ask_ditto für Chat optimiert ist (String return),
            # nutzen wir hier die interne _query_llm Methode oder bauen eine neue Hilfsmethode.
            # Um Code-Duplizierung zu vermeiden und die Abstraktion zu wahren,
            # nutzen wir hier einen direkten Call via Ditto's _query_llm (protected, aber wir sind im Core).
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Zugriff auf Ditto's LLM Engine
            response_text = ditto._query_llm(messages)
            
            # JSON Parsing (Robust)
            if "```" in response_text:
                match = re.search(r"```(?:json)?(.*?)```", response_text, re.DOTALL)
                if match: response_text = match.group(1).strip()
            
            data = json.loads(response_text)
            
            # Validierung
            if not data.get("fix_command"):
                self.logger.warning("AI could not find a fix command.")
                return None
                
            return HealingProposal(
                error_summary=data.get("summary", "Unknown Error"),
                root_cause=data.get("root_cause", "Check logs"),
                fix_command=data.get("fix_command", ""),
                is_remote_fix=(data.get("target", "HOST").upper() == "DEVICE"),
                confidence_score=float(data.get("confidence", 0.0))
            )

        except Exception as e:
            self.logger.error(f"Self-Healing Analysis failed: {e}")
            return None
