#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Telemetry & Support
DIREKTIVE: Goldstandard, Privacy First (Opt-In), Sanitization.

Zweck:
Erstellt anonymisierte Fehlerberichte als GitHub Issue Links.
Sammelt keine Daten im Hintergrund, sondern bereitet sie für den User vor.
Entfernt sensible Pfade und Secrets (Sanitization).
"""

import sys
import platform
import urllib.parse
import re
import os
from typing import Optional, Dict, Any
from datetime import datetime

from orchestrator.utils.logging import get_logger

GITHUB_REPO_URL = "https://github.com/Smilez1985/llm_conversion_framework/issues/new"

class TelemetryManager:
    """
    Verwaltet Fehlerberichterstattung und Anonymisierung.
    """
    
    def __init__(self, framework_manager):
        self.logger = get_logger(__name__)
        self.config = framework_manager.config
        self.enabled = self.config.get("enable_telemetry", False) # Standard: False (Opt-In)

    def generate_issue_link(self, error: Exception, context: str = "", logs: str = "") -> str:
        """
        Generiert einen mailto-artigen Link für ein neues GitHub Issue.
        """
        if not self.enabled:
            self.logger.debug("Telemetry disabled. Skipping report generation.")
            return ""

        try:
            # 1. System Info sammeln
            sys_info = self._get_system_info()
            
            # 2. Report Body bauen
            body = f"""
**Describe the bug**
A clear description of what happened.

**Context**
{context}

**Error Message**
