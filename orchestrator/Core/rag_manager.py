#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - RAG Manager (Local Knowledge Base)
DIREKTIVE: Goldstandard, Enterprise RAG, Robustness.

Zweck:
Verwaltet die lokale Vektor-Datenbank (Qdrant).
Zuständig für Ingestion (Doku -> Vektoren) und Retrieval (Suche -> Kontext).
Nutzt 'litellm' für Embeddings, um Provider-Agnostik zu wahren.

Updates v1.6.0:
- Integration des CrawlerManager für "Deep Ingest".
- Neue Methode `ingest_url` für Webseiten und PDFs.
"""

import uuid
import time
import logging
import json
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime

# Third-party imports
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as rest
    from qdrant_client.http.exceptions import UnexpectedResponse
    import litellm
except ImportError:
    QdrantClient = None

from orchestrator.utils.logging import get_logger

# Import Crawler (v1.6.0)
try:
    from orchestrator.Core.crawler_manager import CrawlerManager
except ImportError:
    CrawlerManager = None

# ============================================================================
# CONFIGURATION
# ============================================================================

COLLECTION_NAME = "framework_knowledge"
VECTOR_SIZE = 1536  # Standard für viele Modelle (z.B. OpenAI, Nomic)
# Fallback Embedding Model, falls nichts konfiguriert ist
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small" 

@dataclass
class SearchResult:
    score: float
    content: str
    source: str
    metadata: Dict[str, Any]

class RAGManager:
    """
    Manages the semantic memory of the framework.
    Connects to the local Qdrant container (Dynamic Sidecar).
    """

    def __init__(self, framework_manager):
        self.logger = get_logger(__name__)
        self.framework = framework_manager
        self.config = framework_manager.config
        self.client: Optional[QdrantClient] = None
        self._connected = False
        
        # Check dependencies
        if not QdrantClient:
            self.logger.critical("Module 'qdrant-client' not found. RAG disabled.")
            return

    def _connect(self) -> bool:
        """
        Versucht, eine Verbindung zum Qdrant-Container herzustellen.
        Nutzt Retry-Logik, da der Container evtl. gerade erst startet.
        """
        if self._connected and self.client:
            return True

        # URL aus Docker-Netzwerk (intern) oder Localhost (falls GUI lokal läuft)
        # Wir versuchen beide gängigen Adressen
        potential_urls = ["http://localhost:6333", "http://llm-qdrant:6333"]
        
        for url in potential_urls:
            try:
                client = QdrantClient(url=url, timeout=2.0)
                # Health Check
                client.get_collections()
                self.client = client
                self._connected = True
                self._ensure_collection()
                self.logger.info(f"RAGManager connected to Qdrant at {url}")
                return True
            except Exception:
                continue
        
        self.logger.warning("RAGManager could not connect to Qdrant (Container might be down).")
        return False

    def _ensure_collection(self):
        """Stellt sicher, dass die Vektor-Collection existiert."""
        if not self.client: return

        try:
            collections = self.client.get_collections()
            exists = any(c.name == COLLECTION_NAME for c in collections.collections)

            if not exists:
                self.logger.info(f"Creating new RAG collection: {COLLECTION_NAME}")
                self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=rest.VectorParams(
                        size=VECTOR_SIZE,
                        distance=rest.Distance.COSINE,
                    ),
                )
        except Exception as e:
            self.logger.error(f"Failed to ensure collection: {e}")

    def _get_embedding(self, text: str) -> List[float]:
        """
        Generiert Embeddings mittels litellm.
        Versucht, den konfigurierten Provider zu nutzen oder fällt auf OpenAI zurück.
        """
        model = self.config.get("ai_embedding_model", DEFAULT_EMBEDDING_MODEL)
        api_key = os.environ.get("OPENAI_API_KEY", "sk-dummy") # Fallback für LocalLLM
        
        try:
            # Clean text to avoid newline issues
            text = text.replace("\n", " ")
            response = litellm.embedding(
                model=model,
                input=[text],
                api_key=api_key
            )
            return response.data[0]["embedding"]
        except Exception as e:
            self.logger.error(f"Embedding generation failed ({model}): {e}")
            raise e

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
        """
        Zerlegt Text in überlappende Chunks für besseren Kontext.
        """
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += (chunk_size - overlap)
        
        return chunks

    def ingest_document(self, source_name: str, content: str, metadata: Dict[str, Any] = None) -> bool:
        """
        Indiziert ein Dokument in der Vektor-Datenbank.
        """
        if not self._connect(): return False
        if not content.strip(): return False

        self.logger.info(f"Ingesting document: {source_name}...")
        
        chunks = self._chunk_text(content)
        points = []
        
        base_meta = metadata or {}
        base_meta["source"] = source_name
        base_meta["ingested_at"] = datetime.now().isoformat()

        for i, chunk in enumerate(chunks):
            try:
                vector = self._get_embedding(chunk)
                
                # Payload construction
                payload = base_meta.copy()
                payload["content"] = chunk
                payload["chunk_index"] = i
                
                points.append(rest.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                ))
            except Exception as e:
                self.logger.warning(f"Skipping chunk {i} due to embedding error: {e}")

        if points:
            try:
                self.client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points
                )
                self.logger.info(f"Successfully indexed {len(points)} chunks for {source_name}")
                return True
            except Exception as e:
                self.logger.error(f"Qdrant Upsert failed: {e}")
                return False
        return False

    def ingest_url(self, url: str) -> Dict[str, Any]:
        """
        Startet den 'Deep Ingest' Prozess für eine URL mittels CrawlerManager.
        Speichert Ergebnisse direkt in Qdrant.
        """
        if not CrawlerManager:
            return {"success": False, "message": "Crawler module missing"}
            
        if not self._connect():
            return {"success": False, "message": "Qdrant not connected"}

        try:
            crawler = CrawlerManager(self.framework)
            self.logger.info(f"Invoking Crawler for {url}...")
            
            # 1. Crawl
            documents = crawler.crawl(url)
            
            if not documents:
                return {"success": False, "message": "No documents found", "count": 0}

            # 2. Ingest Loop
            success_count = 0
            for doc in documents:
                # Nutze die Metadaten vom Crawler (Source URL, Content Type)
                meta = doc.metadata or {}
                meta["root_url"] = url # Tagging für späteres Filtern
                
                if self.ingest_document(meta.get("source", url), doc.page_content, meta):
                    success_count += 1
            
            return {
                "success": True, 
                "message": f"Ingested {success_count} documents", 
                "count": success_count
            }

        except Exception as e:
            self.logger.error(f"Deep Ingest failed: {e}")
            return {"success": False, "message": str(e)}

    def search(self, query: str, limit: int = 3, score_threshold: float = 0.7) -> List[SearchResult]:
        """
        Semantische Suche nach Kontext für eine Query.
        """
        if not self._connect(): return []

        try:
            query_vector = self._get_embedding(query)
            
            hits = self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold
            )
            
            results = []
            for hit in hits:
                payload = hit.payload or {}
                results.append(SearchResult(
                    score=hit.score,
                    content=payload.get("content", ""),
                    source=payload.get("source", "unknown"),
                    metadata=payload
                ))
            
            self.logger.debug(f"Search '{query}' returned {len(results)} hits")
            return results

        except Exception as e:
            self.logger.error(f"RAG Search failed: {e}")
            return []

    def clear_knowledge_base(self) -> bool:
        """Löscht alle gespeicherten Vektoren (Reset)."""
        if not self._connect(): return False
        try:
            self.client.delete_collection(COLLECTION_NAME)
            self._ensure_collection()
            self.logger.info("Knowledge Base cleared.")
            return True
        except Exception as e:
            self.logger.error(f"Clear failed: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Liefert Status-Metriken für die GUI."""
        status = {"connected": False, "vector_count": 0}
        if self._connect():
            try:
                info = self.client.get_collection(COLLECTION_NAME)
                status["connected"] = True
                status["vector_count"] = info.points_count
                status["status"] = info.status.name
            except:
                pass
        return status
