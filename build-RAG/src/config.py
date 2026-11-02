"""Central configuration for the terminal RAG application.

Every value can be overridden with an environment variable and, where useful,
with a command-line flag (see ``src/main.py``). Defaults point at the existing
ingestion artifacts so nobody has to re-ingest anything.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CHROMA_DIR = PROJECT_ROOT / "chroma_db"
DEFAULT_COLLECTION_NAME = "rag_chunks"

# Must match src/ingestion/ingest.py. Chroma's DefaultEmbeddingFunction runs
# all-MiniLM-L6-v2 locally and produces 384-dimensional vectors.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"

DEFAULT_TOP_K = 5
DEFAULT_NUM_CTX = 8192
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT = 300.0


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    chroma_dir: Path = DEFAULT_CHROMA_DIR
    collection_name: str = DEFAULT_COLLECTION_NAME
    top_k: int = DEFAULT_TOP_K
    max_distance: float | None = None
    ollama_host: str = DEFAULT_OLLAMA_HOST
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    num_ctx: int = DEFAULT_NUM_CTX
    temperature: float = DEFAULT_TEMPERATURE
    think: bool = False
    timeout: float = DEFAULT_TIMEOUT
    debug: bool = False
    show_thinking: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            chroma_dir=Path(os.environ.get("RAG_CHROMA_DIR", str(DEFAULT_CHROMA_DIR))),
            collection_name=os.environ.get("RAG_COLLECTION", DEFAULT_COLLECTION_NAME),
            top_k=_env_int("RAG_TOP_K", DEFAULT_TOP_K),
            max_distance=_env_float("RAG_MAX_DISTANCE", None),
            ollama_host=os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
            ollama_model=os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            num_ctx=_env_int("RAG_NUM_CTX", DEFAULT_NUM_CTX),
            temperature=_env_float("RAG_TEMPERATURE", DEFAULT_TEMPERATURE) or 0.0,
            think=_env_bool("RAG_THINK", False),
            timeout=_env_float("RAG_TIMEOUT", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT,
            debug=_env_bool("RAG_DEBUG", False),
            show_thinking=_env_bool("RAG_SHOW_THINKING", False),
        )

    def override(self, **changes: object) -> "Settings":
        """Return a copy with only the provided (non-None) values replaced."""
        clean = {k: v for k, v in changes.items() if v is not None}
        return replace(self, **clean)
