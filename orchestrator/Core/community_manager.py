#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Community Manager
DIREKTIVE: Goldstandard, Safe-Copy logic.
Verwaltet Community-Module und stellt sicher, dass User-Targets geschützt bleiben.
"""

import shutil
import logging
import yaml
import zipfile
import os
from pathlib import Path
from datetime import datetime
from typing import List
from dataclasses import dataclass

from orchestrator.utils.logging import get_logger
from orchestrator.utils.helpers import ensure_directory

@dataclass
class CommunityModule:
    id: str
    name: str
    description: str
    architecture: str
    author: str
    version: str
    path: Path
    is_installed: bool = False

class CommunityManager:
    def __init__(self, framework_manager):
        self.logger = get_logger(__name__)
        self.config = framework_manager.config
        self.app_root = Path(framework_manager.info.installation_path)
        
        self.community_dir = self.app_root / "community"
        self.targets_dir = self.app_root / "targets"
        self.contribution_dir = self.app_root / "contributions"
        
        ensure_directory(self.community_dir)
        ensure_directory(self.contribution_dir)

    def scan_modules(self) -> List[CommunityModule]:
        """Scannt community/ Ordner nach verfügbaren Targets."""
        modules = []
        if not self.community_dir.exists():
            return []

        installed_targets = {p.name for p in self.targets_dir.iterdir() if p.is_dir()}

        for item in self.community_dir.iterdir():
            if item.is_dir() and (item / "target.yml").exists():
                try:
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
                        is_installed=(item.name in installed_targets)
                    )
                    modules.append(mod)
                except Exception as e:
                    self.logger.error(f"Error loading module {item.name}: {e}")
        
        return sorted(modules, key=lambda x: x.name)

    def install_module(self, module_id: str) -> bool:
        """Kopiert Modul von community/ nach targets/ (SICHER: Kein Überschreiben)."""
        source = self.community_dir / module_id
        dest = self.targets_dir / module_id
        
        if dest.exists():
            self.logger.warning(f"Target '{module_id}' existiert bereits. Überspringe Installation.")
            return False
        
        try:
            shutil.copytree(source, dest)
            self.logger.info(f"Installed: {module_id}")
            return True
        except Exception as e:
            self.logger.error(f"Install failed: {e}")
            if dest.exists(): shutil.rmtree(dest)
            raise e

    def prepare_contribution(self, target_path: str, author: str) -> str:
        """Packt ein Target als ZIP für Contribution."""
        src = Path(target_path)
        ts = datetime.now().strftime("%Y%m%d")
        zip_path = self.contribution_dir / f"contrib_{src.name}_{author}_{ts}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(src):
                for file in files:
                    if file.startswith('.') or file.endswith('.pyc'): continue
                    fp = Path(root) / file
                    zf.write(fp, fp.relative_to(src.parent))
                    
        return str(zip_path)
