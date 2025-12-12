#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Community Manager (v2.1 Enterprise)
DIREKTIVE: Goldstandard, Safe-Copy logic, Swarm Memory Integration.

Verwaltet Community-Module und den 'Swarm Memory' (Shared RAG).
Stellt sicher, dass User-Targets geschützt bleiben.

UPDATES v2.1:
- SwarmCipher: 'Fake-Encryption' (Obfuscation) für Knowledge-Uploads (Wingdings/XOR-Bluff).
- Git Integration: Push/Pull auf 'Edge-LLM-Knowledge-Base'.
"""

import shutil
import logging
import yaml
import zipfile
import json
import re
import os
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from orchestrator.utils.logging import get_logger
from orchestrator.utils.helpers import ensure_directory

# --- SWARM CIPHER (The "Bluff" Security) ---
class SwarmCipher:
    """
    Implements 'Security by Obscurity' for the Swarm Memory.
    Technique: XOR with static key -> Mapped to Unicode Symbols (Pseudo-Wingdings).
    
    This makes the content unreadable to bots, AI scrapers, and script kiddies,
    while remaining easily decodable by the Framework.
    """
    KEY = "DITTO_SWARM_KEY_v1_EDGE_CORE"
    # Mapping bytes 0-255 to Unicode Mathematical Operators (looks like Alien/Wingdings)
    # Start at U+2200 (∀)
    OFFSET = 0x2200 

    @staticmethod
    def encrypt(text: str) -> str:
        """Text -> XOR Bytes -> Symbol String"""
        # 1. To Bytes
        data = text.encode('utf-8')
        # 2. XOR with Key
        key_bytes = SwarmCipher.KEY.encode('utf-8')
        xored = bytearray()
        for i, b in enumerate(data):
            xored.append(b ^ key_bytes[i % len(key_bytes)])
        
        # 3. Map to Symbols (Wingdings-style visual obfuscation)
        return "".join([chr(b + SwarmCipher.OFFSET) for b in xored])

    @staticmethod
    def decrypt(symbols: str) -> str:
        """Symbol String -> Bytes -> XOR Reverse -> Text"""
        try:
            # 1. Map symbols back to bytes
            xored = bytearray()
            for char in symbols:
                val = ord(char) - SwarmCipher.OFFSET
                if val < 0 or val > 255: 
                    # Fallback or error if non-swarm char found
                    raise ValueError("Invalid Swarm Character detected")
                xored.append(val)
            
            # 2. XOR Reverse
            key_bytes = SwarmCipher.KEY.encode('utf-8')
            decrypted = bytearray()
            for i, b in enumerate(xored):
                decrypted.append(b ^ key_bytes[i % len(key_bytes)])
                
            return decrypted.decode('utf-8')
        except Exception as e:
            return f"[Decryption Failed: {e}]"

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
    # Das offizielle Schwarm-Gedächtnis Repo
    SWARM_REPO_URL = "https://github.com/Smilez1985/Edge-LLM-Knowledge-Base.git"

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

    # --- MODULE MANAGEMENT (Original Logic Preserved) ---

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
    # KNOWLEDGE BASE SYNC (Updated for Swarm Encryption)
    # ============================================================================

    def sync_knowledge_base(self) -> int:
        """
        Scannt community/knowledge/*.json und importiert neue Snapshots in Qdrant.
        Entschlüsselt dabei 'swarm_encrypted' Dateien automatisch.
        """
        rag_manager = self.framework.get_component("rag_manager")
        if not rag_manager:
            self.logger.warning("RAG Manager not available. Skipping Knowledge Sync.")
            return 0

        imported_count = 0
        
        for json_file in self.knowledge_dir.glob("*.json"):
            try:
                marker = json_file.with_suffix(".imported")
                if marker.exists(): continue

                self.logger.info(f"Syncing knowledge from {json_file.name}...")
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # --- SWARM DECRYPTION ---
                if isinstance(data, dict) and data.get("swarm_encrypted", False):
                    self.logger.info(f"Decrypting Swarm Packet: {json_file.name}")
                    try:
                        raw_payload = SwarmCipher.decrypt(data["payload"])
                        data = json.loads(raw_payload)
                    except Exception as e:
                        self.logger.error(f"Decryption failed for {json_file.name}: {e}")
                        continue
                # ------------------------

                if isinstance(data, list):
                    for entry in data:
                        src = entry.get("source", "community_unknown")
                        content = entry.get("content", "")
                        meta = entry.get("metadata", {})
                        meta["origin_pack"] = json_file.name
                        
                        if rag_manager.ingest_document(src, content, meta):
                            imported_count += 1
                
                with open(marker, 'w') as f: f.write(datetime.now().isoformat())
                    
            except Exception as e:
                self.logger.error(f"Failed to sync {json_file.name}: {e}")

        if imported_count > 0:
            self.logger.info(f"Knowledge Sync complete. Imported {imported_count} documents.")
        return imported_count

    def export_knowledge_base(self, output_name_prefix: str = "knowledge_export") -> Optional[str]:
        """Exportiert lokales Wissen (Qdrant) in ein JSON File."""
        rag_manager = self.framework.get_component("rag_manager")
        if not rag_manager or not rag_manager._connect(): return None

        self.logger.info("Scanning Knowledge Base for export...")
        
        all_points = []
        next_offset = None
        
        try:
            while True:
                records, next_offset = rag_manager.client.scroll(
                    collection_name="framework_knowledge",
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False
                )
                all_points.extend(records)
                if next_offset is None: break
        except Exception as e:
            self.logger.error(f"Qdrant scroll failed: {e}")
            return None

        if not all_points: return None

        export_data = []
        for point in all_points:
            payload = point.payload or {}
            content = self._sanitize_content(payload.get("content", ""))
            source = self._sanitize_content(payload.get("source", "unknown"))
            if content:
                clean_meta = {k: v for k, v in payload.items() if k not in ["content", "source", "chunk_index"]}
                export_data.append({"source": source, "content": content, "metadata": clean_meta})

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_name_prefix}_{ts}.json"
        export_path = self.knowledge_dir / filename
        
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            return str(export_path)
        except Exception as e:
            self.logger.error(f"Failed to write export file: {e}")
            return None

    # ============================================================================
    # SWARM UPLOAD (NEU: Git Integration + Obfuscation)
    # ============================================================================

    def upload_knowledge_to_swarm(self, export_file: str, github_token: str, username: str = "CommunityUser") -> bool:
        """
        1. Liest den Export.
        2. Verschlüsselt ihn mit SwarmCipher.
        3. Pusht ihn in das GitHub Repo.
        """
        file_path = Path(export_file)
        if not file_path.exists():
            self.logger.error(f"File not found: {export_file}")
            return False

        # A. Verschleierung (The Bluff)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_json = f.read()
            
            encrypted_payload = SwarmCipher.encrypt(raw_json)
            
            swarm_packet = {
                "swarm_encrypted": True,
                "version": "v1.0",
                "timestamp": datetime.now().isoformat(),
                "contributor": username,
                "payload": encrypted_payload # Hier liegt der Wingdings-Salat
            }
            
            enc_filename = f"swarm_{file_path.name}"
        except Exception as e:
            self.logger.error(f"Encryption failed: {e}")
            return False

        # B. Git Operation (Push to Hive)
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "swarm_repo"
            
            # Auth-URL bauen (Token-basiert)
            auth_url = self.SWARM_REPO_URL.replace("https://", f"https://{username}:{github_token}@")
            
            try:
                self.logger.info("Cloning Swarm Repo...")
                # Depth 1 für Speed
                subprocess.run(["git", "clone", "--depth", "1", auth_url, str(repo_dir)], check=True, capture_output=True)
                
                # Datei ablegen
                contributions_dir = repo_dir / "contributions"
                ensure_directory(contributions_dir)
                dest_file = contributions_dir / enc_filename
                
                with open(dest_file, 'w', encoding='utf-8') as f:
                    json.dump(swarm_packet, f, indent=2)
                
                # Commit & Push
                self.logger.info("Committing to Swarm...")
                # Git Config für diesen Run setzen
                subprocess.run(["git", "config", "user.email", "ditto@framework.local"], cwd=repo_dir, check=True)
                subprocess.run(["git", "config", "user.name", username], cwd=repo_dir, check=True)
                
                subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
                msg = f"feat(knowledge): Contribution from {username} ({datetime.now().strftime('%Y-%m-%d')})"
                subprocess.run(["git", "commit", "-m", msg], cwd=repo_dir, check=True)
                
                self.logger.info("Pushing to Swarm...")
                subprocess.run(["git", "push"], cwd=repo_dir, check=True)
                
                self.logger.info("✅ Upload successful! You are now part of the Swarm.")
                return True
                
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Git operation failed: {e}")
                if e.stderr: self.logger.error(f"Git Error: {e.stderr.decode()}")
                return False
            except Exception as e:
                self.logger.error(f"Upload failed: {e}")
                return False

    def _sanitize_content(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r'(sk-[a-zA-Z0-9]{20,})', 'sk-REDACTED', text)
        text = re.sub(r'(hf_[a-zA-Z0-9]{20,})', 'hf_REDACTED', text)
        text = re.sub(r'/home/[a-zA-Z0-9_-]+/', '/home/user/', text)
        text = re.sub(r'C:\\Users\\[a-zA-Z0-9_-]+\\', r'C:\\Users\\User\\', text)
        return text
