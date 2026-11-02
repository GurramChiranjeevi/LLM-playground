"""ChromaDB retrieval using the existing ingested collection.

This module deliberately reuses the same embedding configuration as
``src/ingestion/ingest.py``: Chroma's ``DefaultEmbeddingFunction`` (all-MiniLM-L6-v2,
384-dim). It never re-chunks or re-embeds the source documents — it only
embeds the user's question and queries the persistent collection.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

log = logging.getLogger("rag.retriever")


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    text: str
    source: str | None
    chunk_index: int | None
    distance: float | None
    similarity: float | None
    metadata: dict[str, Any]


class Retriever:
    def __init__(
        self,
        chroma_dir: Path,
        collection_name: str,
        top_k: int = 5,
        max_distance: float | None = None,
        embedding_function: Any | None = None,
    ):
        self.chroma_dir = Path(chroma_dir)
        self.collection_name = collection_name
        self.top_k = int(top_k)
        self.max_distance = max_distance
        # Use the same EF as ingestion; instantiating it warms the ONNX model lazily.
        self.embedding_function = embedding_function if embedding_function is not None else DefaultEmbeddingFunction()

        if not self.chroma_dir.exists():
            raise FileNotFoundError(
                f"ChromaDB directory not found: {self.chroma_dir}. "
                "Run ingestion first or set RAG_CHROMA_DIR to the correct path."
            )

        try:
            self.client = chromadb.PersistentClient(
                path=str(self.chroma_dir),
                settings=chromadb.Settings(anonymized_telemetry=False),
            )
        except Exception as exc:
            raise ConnectionError(f"Failed to open ChromaDB at {self.chroma_dir}: {exc}") from exc

        try:
            self.collection = self.client.get_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
            )
        except Exception as exc:
            raise ValueError(
                f"Collection '{self.collection_name}' not found in {self.chroma_dir}: {exc} "
                "Check the collection name (ingest uses 'rag_chunks')."
            ) from exc

    @property
    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        k = int(top_k) if top_k is not None else self.top_k
        if not query or not query.strip():
            return []

        try:
            res = self.collection.query(
                query_texts=[query],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise RuntimeError(f"ChromaDB retrieval failed: {exc}") from exc

        ids_list = (res.get("ids") or [[]])[0]
        docs_list = (res.get("documents") or [[]])[0]
        metas_list = (res.get("metadatas") or [[]])[0]
        dists_list = (res.get("distances") or [[]])[0]

        chunks: list[RetrievedChunk] = []
        for uid, doc, meta, dist in zip(ids_list, docs_list, metas_list, dists_list):
            dist_f = float(dist) if dist is not None else None
            sim = (1.0 - dist_f) if dist_f is not None else None
            meta = meta or {}
            if self.max_distance is not None and dist_f is not None and dist_f > self.max_distance:
                continue
            chunks.append(
                RetrievedChunk(
                    id=uid,
                    text=doc or "",
                    source=meta.get("source") if isinstance(meta, dict) else None,
                    chunk_index=meta.get("chunk_index") if isinstance(meta, dict) else None,
                    distance=dist_f,
                    similarity=sim,
                    metadata=meta if isinstance(meta, dict) else {},
                )
            )
        return chunks

    def format_debug(self, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "[RETRIEVAL DEBUG] No chunks retrieved."
        lines = ["", "[RETRIEVAL DEBUG]", f"Retrieved {len(chunks)} chunks:", ""]
        for idx, c in enumerate(chunks, 1):
            lines.append(f"{idx}. Source: {c.source or 'unknown'}  id: {c.id}")
            if c.distance is not None:
                lines.append(f"   Distance: {c.distance:.6f}  Similarity: {(c.similarity or 0):.6f}")
            if c.chunk_index is not None:
                lines.append(f"   Chunk index: {c.chunk_index}")
            if c.metadata:
                # Show compact metadata (avoid dumping huge hashes unless useful)
                meta_show = dict(c.metadata)
                lines.append(f"   Metadata: {json.dumps(meta_show, ensure_ascii=False)}")
            preview = (c.text or "").replace("\n", " ")
            if len(preview) > 300:
                preview = preview[:297] + "..."
            lines.append(f"   Content: {preview}")
            lines.append("")
        return "\n".join(lines)
