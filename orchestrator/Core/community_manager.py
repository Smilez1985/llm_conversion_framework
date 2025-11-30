#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Community Manager
DIREKTIVE: Goldstandard, Safe-Copy logic.
Verwaltet Community-Module und stellt sicher, dass User-Targets geschützt bleiben.

UPDATES v1.5.0:
- Knowledge Sync: Importiert Community-Wissen (JSON Snapshots) in Qdrant.
- Knowledge Export: Erstellt bereinigte Snapshots via Qdrant Scroll API.
"""

import shutil
import logging
import yaml
import zipfile
import json
import re
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
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
        self.framework = framework_manager
        self.config = framework_manager.config
        self.app_root = Path(framework_manager.info.installation_path)
        
        self.community_dir = self.app_root / "community"
        self.knowledge_dir = self.community_dir / "knowledge"
        self.targets_dir = self.app_root / "targets"
        self.contribution_dir = self.app_root / "contributions"
        
        ensure_directory(self.community_dir)
        ensure_directory(self.knowledge_dir)
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

    # ============================================================================
    # KNOWLEDGE BASE SYNC (v1.5.0)
    # ============================================================================

    def sync_knowledge_base(self) -> int:
        """
        Scannt community/knowledge/*.json und importiert neue Snapshots in Qdrant.
        Gibt die Anzahl der importierten Dokumente zurück.
        """
        rag_manager = self.framework.get_component("rag_manager")
        if not rag_manager:
            self.logger.warning("RAG Manager not available. Skipping Knowledge Sync.")
            return 0

        imported_count = 0
        
        # Iteriere über alle JSON Snapshots
        for json_file in self.knowledge_dir.glob("*.json"):
            try:
                # Prüfen, ob wir dieses File schon importiert haben (Marker-Datei)
                marker = json_file.with_suffix(".imported")
                if marker.exists():
                    continue

                self.logger.info(f"Syncing knowledge from {json_file.name}...")
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Format: List of dicts { "source": str, "content": str, "metadata": dict }
                if isinstance(data, list):
                    for entry in data:
                        src = entry.get("source", "community_unknown")
                        content = entry.get("content", "")
                        meta = entry.get("metadata", {})
                        
                        # Add tag to metadata
                        meta["origin_pack"] = json_file.name
                        
                        if rag_manager.ingest_document(src, content, meta):
                            imported_count += 1
                
                # Mark as imported
                with open(marker, 'w') as f:
                    f.write(datetime.now().isoformat())
                    
            except Exception as e:
                self.logger.error(f"Failed to sync {json_file.name}: {e}")

        if imported_count > 0:
            self.logger.info(f"Knowledge Sync complete. Imported {imported_count} documents.")
        return imported_count

    def export_knowledge_base(self, output_name_prefix: str = "knowledge_export") -> Optional[str]:
        """
        Exportiert lokales Wissen (Qdrant) in ein JSON File für die Community.
        Nutzt die Qdrant Scroll API, um über alle Vektoren zu iterieren.
        Wendet strikte Sanitization an, um Secrets zu entfernen.
        """
        rag_manager = self.framework.get_component("rag_manager")
        if not rag_manager:
            self.logger.error("RAG Manager not initialized. Cannot export.")
            return None
            
        # Verbindung prüfen (Startet Container bei Bedarf via DockerManager Logik im Framework init)
        if not rag_manager._connect():
            self.logger.error("Could not connect to Qdrant for export.")
            return None

        self.logger.info("Starting Knowledge Base Export (Scanning all vectors)...")
        
        all_points = []
        next_offset = None
        collection_name = "framework_knowledge" # Muss mit RAGManager übereinstimmen
        
        try:
            # Scroll Loop: Iteriert durch die gesamte Collection
            while True:
                # Qdrant Client Scroll API: Returns (points, next_page_offset)
                records, next_offset = rag_manager.client.scroll(
                    collection_name=collection_name,
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False # Wir exportieren keine Vektoren, nur Payload (Text)
                )
                all_points.extend(records)
                
                if next_offset is None:
                    break
        except Exception as e:
            self.logger.error(f"Failed to scroll Qdrant collection: {e}")
            return None

        if not all_points:
            self.logger.warning("Knowledge base is empty. Nothing to export.")
            return None

        export_data = []
        processed_count = 0
        
        for point in all_points:
            payload = point.payload or {}
            content = payload.get("content", "")
            source = payload.get("source", "unknown")
            
            # Sanitization Step
            safe_content = self._sanitize_content(content)
            safe_source = self._sanitize_content(source)
            
            # Nur exportieren, wenn Inhalt vorhanden ist
            if safe_content:
                # Metadaten bereinigen (interne IDs entfernen)
                clean_meta = {k: v for k, v in payload.items() if k not in ["content", "source", "chunk_index"]}
                
                entry = {
                    "source": safe_source,
                    "content": safe_content,
                    "metadata": clean_meta
                }
                export_data.append(entry)
                processed_count += 1

        # Datei speichern
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_name_prefix}_{ts}.json"
        export_path = self.knowledge_dir / filename
        
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Export successful: {processed_count} documents saved to {export_path}")
            return str(export_path)
        except Exception as e:
            self.logger.error(f"Failed to write export file: {e}")
            return None

    def _sanitize_content(self, text: str) -> str:
        """
        Entfernt sensible Daten aus Texten bevor sie exportiert werden.
        Regex-Filter für API-Keys und Pfade.
        """
        if not text: return ""
        
        # 1. API Keys (OpenAI, HuggingFace, Generic High-Entropy)
        # sk- followed by 20+ chars
        text = re.sub(r'(sk-[a-zA-Z0-9]{20,})', 'sk-REDACTED', text)
        # hf_ followed by 20+ chars
        text = re.sub(r'(hf_[a-zA-Z0-9]{20,})', 'hf_REDACTED', text)
        
        # 2. Local Paths (Unix/Windows)
        # Ersetzt /home/username/... mit /home/user/...
        text = re.sub(r'/home/[a-zA-Z0-9_-]+/', '/home/user/', text)
        text = re.sub(r'/Users/[a-zA-Z0-9_-]+/', '/Users/user/', text)
        # Windows C:\Users\Name
        text = re.sub(r'C:\\Users\\[a-zA-Z0-9_-]+\\', r'C:\\Users\\User\\', text)
        
        return text
