#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Community Manager
DIREKTIVE: Goldstandard, Safe-Copy, Contribution-Workflow.

Verwaltet die Interaktion zwischen dem 'community/'-Repository-Ordner
und dem lokalen 'targets/'-Ordner. Stellt sicher, dass User-Modifikationen
niemals überschrieben werden.
"""

import os
import shutil
import logging
import yaml
import zipfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from orchestrator.utils.logging import get_logger
from orchestrator.utils.helpers import ensure_directory

@dataclass
class CommunityModule:
    """Repräsentiert ein Modul aus dem Community-Ordner"""
    id: str              # Ordnername
    name: str            # Aus target.yml
    description: str
    architecture: str
    author: str
    version: str
    path: Path
    is_installed: bool = False
    tags: List[str] = None

class CommunityManager:
    def __init__(self, framework_manager):
        self.logger = get_logger(__name__)
        self.config = framework_manager.config
        self.app_root = Path(framework_manager.info.installation_path)
        
        # Pfade
        self.community_dir = self.app_root / "community"
        self.targets_dir = self.app_root / "targets"
        self.contribution_dir = self.app_root / "contributions"  # Output für exportierte Module
        
        ensure_directory(self.community_dir)
        ensure_directory(self.contribution_dir)

    def refresh_repo(self) -> bool:
        """Führt ein Git Pull nur für den Community-Ordner durch (via Sparse Checkout simuliert oder Full Pull)"""
        # Da wir im Main-Update schon pullen, scannen wir hier primär neu.
        # Ein expliziter Pull könnte hier ergänzt werden.
        return True

    def scan_modules(self) -> List[CommunityModule]:
        """Scannt community/ und targets/ um verfügbare Module zu finden."""
        modules = []
        
        if not self.community_dir.exists():
            self.logger.warning(f"Community directory not found: {self.community_dir}")
            return []

        installed_targets = {p.name for p in self.targets_dir.iterdir() if p.is_dir()}

        for item in self.community_dir.iterdir():
            if item.is_dir() and (item / "target.yml").exists():
                try:
                    # Parse Metadata
                    with open(item / "target.yml", 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                        meta = data.get('metadata', {})
                    
                    mod = CommunityModule(
                        id=item.name,
                        name=meta.get('name', item.name),
                        description=meta.get('description', 'No description'),
                        architecture=meta.get('architecture_family', 'unknown'),
                        author=meta.get('maintainer', 'Community'),
                        version=meta.get('version', '1.0.0'),
                        path=item,
                        is_installed=(item.name in installed_targets),
                        tags=[meta.get('category', 'general'), meta.get('vendor', 'generic')]
                    )
                    modules.append(mod)
                except Exception as e:
                    self.logger.error(f"Error parsing community module {item.name}: {e}")
        
        return sorted(modules, key=lambda x: x.name)

    def install_module(self, module_id: str) -> bool:
        """
        Installiert ein Modul von community/ nach targets/.
        SICHERHEIT: Überschreibt NIEMALS existierende Ordner.
        """
        source = self.community_dir / module_id
        dest = self.targets_dir / module_id
        
        if dest.exists():
            self.logger.warning(f"Installation aborted: Target '{module_id}' already exists locally.")
            return False
        
        try:
            self.logger.info(f"Installing community module: {module_id}")
            shutil.copytree(source, dest)
            return True
        except Exception as e:
            self.logger.error(f"Installation failed for {module_id}: {e}")
            # Cleanup partial install
            if dest.exists():
                shutil.rmtree(dest)
            raise e

    def prepare_contribution(self, target_path: str, author_name: str) -> str:
        """
        Packt ein lokales Target als Contribution-ZIP für Pull Requests.
        Führt vorher Validierung durch.
        """
        src_path = Path(target_path)
        if not src_path.exists():
            raise FileNotFoundError("Target path does not exist")
            
        # 1. Validierung (Minimal)
        required = ["target.yml", "Dockerfile", "modules/config_module.sh"]
        for f in required:
            if not (src_path / f).exists():
                raise ValueError(f"Invalid module structure: missing {f}")

        # 2. Packaging
        timestamp = datetime.now().strftime("%Y%m%d")
        zip_name = f"contrib_{src_path.name}_{author_name}_{timestamp}.zip"
        zip_path = self.contribution_dir / zip_name
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(src_path):
                for file in files:
                    # Skip hidden files and temp artifacts
                    if file.startswith('.') or file.endswith('.pyc') or '__pycache__' in root:
                        continue
                        
                    file_p = Path(root) / file
                    arcname = file_p.relative_to(src_path.parent) # Behalte Ordnernamen
                    zipf.write(file_p, arcname)
                    
        self.logger.info(f"Contribution package created: {zip_path}")
        return str(zip_path)
