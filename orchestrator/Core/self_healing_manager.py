#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Enterprise Self-Healing Manager (v2.0)
DIREKTIVE: Goldstandard, Autonome Fehlerbehebung & Lernfähigkeit.

Features:
- Analysiert Build-Fehler mit Ditto (AI).
- Führt Reparaturen automatisch aus (Lokal & Remote).
- "Lernendes System": Speichert erfolgreiche Fixes in lokaler Knowledge-Base.
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from datetime import datetime

from orchestrator.utils.logging import get_logger

@dataclass
class HealingProposal:
    """Vorschlag zur Fehlerbehebung."""
    error_summary: str
    root_cause: str
    fix_command: str
    is_remote_fix: bool = False # True = Muss auf Target (SSH) laufen, False = Lokal/Docker
    confidence_score: float = 0.0
    source: str = "AI" # "AI" oder "HISTORY"

class SelfHealingManager:
    """
    The 'Doctor' of the framework.
    Diagnoses errors, prescribes CLI commands, and performs surgery.
    """
    
    def __init__(self, framework_manager):
        self.logger = get_logger("SelfHealing")
        self.framework = framework_manager
        self.ditto = None 
        
        # Knowledge Base für "Known Issues"
        # Wir nutzen das Config-Verzeichnis des Frameworks
        if self.framework and self.framework.config:
            self.kb_file = Path(self.framework.config.configs_dir) / "healing_knowledge_base.json"
        else:
            # Fallback
            self.kb_file = Path("configs") / "healing_knowledge_base.json"
            
        self.known_issues = self._load_knowledge_base()

    def _get_ditto(self):
        """Lazy Init für AI Engine"""
        if not self.ditto:
            if hasattr(self.framework, 'ditto_manager') and self.framework.ditto_manager:
                self.ditto = self.framework.ditto_manager
            else:
                try:
                    from orchestrator.Core.ditto_manager import DittoCoder
                    # Wir versuchen, Ditto zu initialisieren, falls Config vorhanden
                    if self.framework:
                        self.ditto = DittoCoder(config_manager=self.framework.config, framework_manager=self.framework)
                except Exception as e:
                    self.logger.error(f"Could not init Ditto for healing: {e}")
        return self.ditto

    def _load_knowledge_base(self) -> List[Dict]:
        """Lädt historisch erfolgreiche Fixes."""
        if self.kb_file.exists():
            try:
                with open(self.kb_file, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_to_knowledge_base(self, proposal: HealingProposal, original_error_signature: str):
        """Speichert einen erfolgreichen Fix."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "error_signature": original_error_signature,
            "proposal": asdict(proposal)
        }
        self.known_issues.append(entry)
        try:
            # Stelle sicher, dass das Verzeichnis existiert
            self.kb_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.kb_file, "w") as f:
                json.dump(self.known_issues, f, indent=2)
            self.logger.info("Fix added to Knowledge Base.")
        except Exception as e:
            self.logger.warning(f"Could not save Knowledge Base: {e}")

    def _generate_error_signature(self, log: str) -> str:
        """Erstellt einen einfachen Hash/Signatur aus dem Log (z.B. letzte Zeile)."""
        # Vereinfacht: Nehmen wir die letzten nicht-leeren Zeilen als "Fingerabdruck"
        lines = [l.strip() for l in log.strip().split('\n') if l.strip()]
        return lines[-1] if lines else "unknown_error"

    def analyze_error(self, error_log: str, context: str = "") -> Optional[HealingProposal]:
        """
        Analysiert Fehler: Erst Check in DB, dann AI-Anfrage.
        """
        signature = self._generate_error_signature(error_log)
        
        # 1. Check History (Instant Fix)
        for issue in self.known_issues:
            # Sehr einfacher String-Match (könnte durch Vektor-Suche/Qdrant ersetzt werden)
            if issue.get("error_signature") == signature:
                self.logger.info("Known Issue detected! Using cached fix.")
                p_data = issue["proposal"]
                return HealingProposal(
                    p_data["error_summary"], p_data["root_cause"], 
                    p_data["fix_command"], p_data["is_remote_fix"], 
                    1.0, "HISTORY"
                )

        # 2. Ask Ditto (AI Analysis)
        ditto = self._get_ditto()
        if not ditto: 
            self.logger.warning("Ditto AI not available for analysis.")
            return None

        self.logger.info("Consulting AI for diagnosis...")
        log_tail = error_log[-3000:] # Token Save
        
        system_prompt = """
        You are the Self-Healing Module (Auto-Repair) for an Embedded AI Framework.
        Analyze the BUILD/RUNTIME ERROR.
        
        OUTPUT JSON ONLY:
        {
            "summary": "Short explanation",
            "root_cause": "Deep technical reason",
            "fix_command": "Single line bash command to fix it",
            "target": "HOST" (Docker/PC) or "DEVICE" (SSH),
            "confidence": 0.0 to 1.0
        }
        NO MARKDOWN. NO EXPLANATION TEXT.
        """
        
        user_prompt = f"CONTEXT: {context}\n\nERROR LOG:\n{log_tail}"
        
        try:
            # Wir nutzen die LLM-Schnittstelle von Ditto
            # Annahme: DittoCoder hat eine Methode _query_llm oder ähnlich
            response = ditto._query_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ])
            
            # Robust JSON parsing
            clean_json = response.strip()
            if "```" in clean_json:
                # Extrahiere JSON Block falls in Markdown
                match = re.search(r"```(?:json)?(.*?)```", clean_json, re.DOTALL)
                if match:
                    clean_json = match.group(1).strip()
            
            data = json.loads(clean_json)
            
            if not data.get("fix_command"): return None
            
            return HealingProposal(
                error_summary=data.get("summary", "Unknown"),
                root_cause=data.get("root_cause", "Unknown"),
                fix_command=data.get("fix_command", ""),
                is_remote_fix=(str(data.get("target", "HOST")).upper() == "DEVICE"),
                confidence_score=float(data.get("confidence", 0.0)),
                source="AI"
            )
            
        except Exception as e:
            self.logger.error(f"AI Analysis failed: {e}")
            return None

    def apply_fix(self, proposal: HealingProposal, error_log_context: str = "", auto_confirm: bool = False) -> bool:
        """
        Führt den vorgeschlagenen Fix aus.
        """
        self.logger.info(f"Applying Fix ({proposal.source}): {proposal.fix_command}")
        
        if not auto_confirm and proposal.confidence_score < 0.8:
            self.logger.warning(f"Confidence low ({proposal.confidence_score}). Skipping auto-execution.")
            return False

        success = False
        output = ""

        # A. Remote Fix (via DeploymentManager)
        if proposal.is_remote_fix:
            dep_mgr = self.framework.get_component("deployment_manager")
            if not dep_mgr:
                self.logger.error("DeploymentManager not loaded. Cannot execute remote fix.")
                return False
            
            # Hole Credentials aus Config
            # TODO: Hier sollte der SecretsManager verwendet werden!
            target_ip = self.framework.config.get("target_ip", "192.168.1.100")
            user = self.framework.config.get("target_user", "root")
            password = self.framework.config.get("target_password") 
            
            self.logger.info(f"Connecting to {target_ip}...")
            success, output = dep_mgr.execute_command(proposal.fix_command, target_ip, user, password)

        # B. Local Fix (subprocess)
        else:
            try:
                # Shell=True ist hier notwendig für komplexe Commands (Pipes etc.)
                res = subprocess.run(
                    proposal.fix_command, 
                    shell=True, 
                    check=True, 
                    capture_output=True, 
                    text=True
                )
                success = True
                output = res.stdout
            except subprocess.CalledProcessError as e:
                success = False
                output = e.stderr
            except Exception as e:
                success = False
                output = str(e)

        # C. Result Evaluation & Learning
        if success:
            self.logger.info("✅ Fix applied successfully.")
            
            # LERNEN: Wenn es ein AI-Fix war und erfolgreich, speichere ihn für die Zukunft
            if proposal.source == "AI" and error_log_context:
                signature = self._generate_error_signature(error_log_context)
                self._save_to_knowledge_base(proposal, signature)
                
            return True
        else:
            self.logger.error(f"❌ Fix failed: {output}")
            return False
