"""RAG ingestion pipeline: chunks.json -> embeddings -> persistent ChromaDB.

This script performs INGESTION ONLY (no retrieval, no LLM answer generation).

Workflow
--------
1. Read pre-chunked documents from ``chunks.json``.
2. Validate each record and extract (source, chunk_id, text) + metadata.
3. Derive a stable, deterministic ID per chunk: ``<source>::<chunk_id>``.
4. Compute a SHA-256 ``text_hash`` per chunk (used as a content cache key).
5. Open a persistent ChromaDB database and the ``rag_chunks`` collection.
6. Compare each chunk's current ``text_hash`` against the stored hash:
     - unchanged  -> skip (no re-embedding)
     - new/changed -> embed with the default local EF, then upsert
7. Upsert (insert-or-update by ID) in batches -> idempotent re-runs.

Embedding model
---------------
ChromaDB's default embedding function, ``DefaultEmbeddingFunction``, uses
``all-MiniLM-L6-v2`` running locally via ONNX Runtime (no paid API).
Expected output dimensionality: 384.
The SAME embedding function must be used for document ingestion and future
query embedding; otherwise query vectors live in a different space and
similarity search returns garbage.

This implementation precomputes embeddings (``ef(texts)``) and passes them
explicitly to ``collection.upsert(embeddings=...)`` rather than letting
ChromaDB embed implicitly. Reasons:
  * full control over batching and per-batch error reporting;
  * the content-hash cache can skip embedding entirely for unchanged chunks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Disable ChromaDB's anonymized telemetry BEFORE importing chromadb. The
# installed posthog version is incompatible with chromadb's capture call
# signature, which produces noisy non-fatal errors. Setting the env var early
# is the reliable way to suppress it.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CHUNKS_FILE = PROJECT_ROOT / "chunks" / "chunks.json"
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "chroma_db"
DEFAULT_COLLECTION_NAME = "rag_chunks"
BATCH_SIZE = 64
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

log = logging.getLogger("rag.ingest")


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # ChromaDB 0.6.3 ships a telemetry path that is incompatible with the
    # installed posthog version (capture() signature changed). It catches the
    # exception and logs a noisy non-fatal ERROR. We want telemetry off anyway,
    # so silence that specific logger. The exception is harmless and caught.
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)


# ---------------------------------------------------------------------------
# Loading + validation
# ---------------------------------------------------------------------------

def load_chunks(path: Path) -> list[dict]:
    """Read and JSON-parse the chunks file. Raises on missing/invalid JSON."""
    if not path.exists():
        raise SystemExit(f"Chunks file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Chunks file is not valid JSON: {exc}")
    if not isinstance(data, list):
        raise SystemExit(
            f"Expected a JSON list at top level, got {type(data).__name__}."
        )
    return data


def validate_record(rec: Any, index: int) -> tuple[dict | None, str | None]:
    """Validate a single raw record.

    Returns (normalized_chunk, None) if valid, else (None, reason).
    The normalized chunk keeps the original field names plus derived fields.
    """
    if not isinstance(rec, dict):
        return None, f"record {index}: not a JSON object"

    source = rec.get("source")
    chunk_id = rec.get("chunk_id")
    text = rec.get("text")

    if not isinstance(source, str) or not source.strip():
        return None, f"record {index}: missing/empty 'source'"
    if not isinstance(chunk_id, int) or isinstance(chunk_id, bool):
        return None, f"record {index}: 'chunk_id' must be an integer (got {type(chunk_id).__name__})"
    if not isinstance(text, str) or not text.strip():
        return None, f"record {index}: missing/empty 'text'"

    return {
        "source": source,
        "chunk_id": chunk_id,
        "text": text,
    }, None


def make_uid(source: str, chunk_id: int) -> str:
    """Deterministic, globally-unique Chroma ID for a chunk.

    chunk_id is per-source (transcript_1 has chunk_id 0 AND transcript_2 has
    chunk_id 0), so (source, chunk_id) is the true unique key. We join with '::'
    which is safe for filenames and unambiguous."""
    return f"{source}::{chunk_id}"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Chroma helpers
# ---------------------------------------------------------------------------

def get_existing_hashes(collection: chromadb.Collection, ids: list[str]) -> dict[str, str]:
    """Return {id: text_hash} for IDs already present in the collection.

    Used to detect unchanged chunks so we skip re-embedding them. Bounded in
    batches to stay safe for large datasets.
    """
    if not ids:
        return {}
    found: dict[str, str] = {}
    for i in range(0, len(ids), 1000):
        batch = ids[i:i + 1000]
        got = collection.get(ids=batch, include=["metadatas"])
        for uid, meta in zip(got.get("ids", []), got.get("metadatas", [])):
            if meta and isinstance(meta.get("text_hash"), str):
                found[uid] = meta["text_hash"]
    return found


def existing_embedding_dim(collection: chromadb.Collection) -> int | None:
    """Dimensionality of embeddings already in the collection (None if empty).

    ChromaDB returns embeddings as a numpy 2D array, so we must avoid boolean
    truth-tests on it (those raise 'ambiguous truth value').
    """
    peek = collection.get(limit=1, include=["embeddings"])
    embs = peek.get("embeddings")
    if embs is None:
        return None
    # Normalise numpy array / list-of-lists into a plain list of rows.
    rows = list(embs)
    if not rows:
        return None
    return len(list(rows[0]))


def get_expected_dim(ef: Any) -> int:
    """Embed a tiny probe to learn the EF's output dimension (and warm the model)."""
    vec = ef(["dimension probe"])
    return len(vec[0])


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest chunks.json into ChromaDB.")
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_FILE,
                        help="Path to chunks.json")
    parser.add_argument("--db", type=Path, default=DEFAULT_CHROMA_DIR,
                        help="Persistent ChromaDB directory")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION_NAME,
                        help="Collection name")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help="Embed/upsert batch size")
    parser.add_argument("--force", action="store_true",
                        help="Re-embed and upsert every chunk (ignore the content-hash cache)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure_logging(args.verbose)
    log.info("=== RAG ingestion ===")
    log.info("Chunks file : %s", args.chunks)
    log.info("ChromaDB dir: %s", args.db)
    log.info("Collection  : %s", args.collection)
    log.info("Batch size  : %d", args.batch_size)

    # 1. Load + validate -----------------------------------------------------
    raw = load_chunks(args.chunks)
    log.info("Total chunks discovered in file: %d", len(raw))

    valid: list[dict] = []
    skipped: list[str] = []
    for i, rec in enumerate(raw):
        norm, reason = validate_record(rec, i)
        if norm is None:
            skipped.append(reason)
            continue
        valid.append(norm)

    log.info("Valid chunks  : %d", len(valid))
    log.info("Skipped chunks: %d", len(skipped))
    for r in skipped:
        log.warning("  skipped: %s", r)

    if not valid:
        log.error("No valid chunks to ingest. Exiting.")
        return 1

    # Attach derived fields needed for storage.
    for c in valid:
        c["uid"] = make_uid(c["source"], c["chunk_id"])
        c["hash"] = text_hash(c["text"])
        c["text_length"] = len(c["text"])

    # 2. Set up Chroma + embedding function ----------------------------------
    args.db.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(args.db),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    ef = DefaultEmbeddingFunction()

    # Pre-warm the model and learn its output dimension.
    expected_dim = get_expected_dim(ef)
    log.info("Embedding model: %s (DefaultEmbeddingFunction -> ONNXMiniLM_L6_V2)",
             EMBEDDING_MODEL_NAME)
    log.info("Expected vector dimensionality: %d", expected_dim)

    # Create or open the collection. We use cosine space, which is the standard
    # metric for normalized sentence embeddings and gives interpretable
    # distances (0 = identical). get_or_create keeps any pre-existing collection
    # intact (it never deletes data).
    collection = client.get_or_create_collection(
        name=args.collection,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # 3. Dimension-mismatch guard --------------------------------------------
    # If the collection already holds embeddings from a DIFFERENT model, mixing
    # in our vectors would corrupt similarity search. We detect this and abort
    # WITHOUT deleting anything (per project policy). The user must explicitly
    # decide how to migrate.
    stored_dim = existing_embedding_dim(collection)
    if stored_dim is not None and stored_dim != expected_dim:
        log.error("DIMENSION MISMATCH: collection '%s' already contains vectors of "
                  "dimension %d, but %s produces %d.", args.collection, stored_dim,
                  EMBEDDING_MODEL_NAME, expected_dim)
        log.error("Refusing to mix incompatible embeddings. No data was changed.")
        log.error("Safe migration options:")
        log.error("  1) Use a NEW collection name (e.g. --collection rag_chunks_v2).")
        log.error("  2) Explicitly delete the existing collection and re-ingest "
                  "(only with your permission).")
        return 2

    # 4. Decide what needs (re)embedding via the content-hash cache ----------
    uids = [c["uid"] for c in valid]
    if args.force:
        log.info("--force set: ignoring content-hash cache; will re-embed all chunks.")
        existing_hashes: dict[str, str] = {}
    else:
        existing_hashes = get_existing_hashes(collection, uids)

    to_embed: list[dict] = []
    unchanged = 0
    for c in valid:
        if existing_hashes.get(c["uid"]) == c["hash"]:
            unchanged += 1
        else:
            to_embed.append(c)

    log.info("Unchanged (cached, skipping embed): %d", unchanged)
    log.info("To embed/upsert (new + changed)   : %d", len(to_embed))

    # 5. Embed + upsert in batches ------------------------------------------
    inserted_or_updated = 0
    batch_failures = 0
    for i in range(0, len(to_embed), args.batch_size):
        batch = to_embed[i:i + args.batch_size]
        batch_ids = [c["uid"] for c in batch]
        batch_texts = [c["text"] for c in batch]
        batch_metas = [
            {
                "source": c["source"],
                "chunk_index": c["chunk_id"],
                "text_hash": c["hash"],
                "text_length": c["text_length"],
            }
            for c in batch
        ]
        try:
            embeddings = ef(batch_texts)  # list[list[float]]
            collection.upsert(
                ids=batch_ids,
                documents=batch_texts,
                embeddings=embeddings,
                metadatas=batch_metas,
            )
            inserted_or_updated += len(batch)
            log.info("  batch %d/%d upserted %d records (total so far %d)",
                     i // args.batch_size + 1,
                     (len(to_embed) + args.batch_size - 1) // args.batch_size,
                     len(batch), inserted_or_updated)
        except Exception as exc:
            batch_failures += 1
            log.error("  batch %d FAILED: %s",
                      i // args.batch_size + 1, exc)
            log.error("    ids in failed batch: %s", batch_ids[:5])

    # 6. Final report --------------------------------------------------------
    final_count = collection.count()
    log.info("=== Ingestion summary ===")
    log.info("Discovered in file       : %d", len(raw))
    log.info("Valid                    : %d", len(valid))
    log.info("Skipped (invalid)        : %d", len(skipped))
    log.info("Unchanged (cached, skip) : %d", unchanged)
    log.info("Embedded + upserted      : %d", inserted_or_updated)
    log.info("Batch failures           : %d", batch_failures)
    log.info("Records now in collection: %d", final_count)
    log.info("Embedding model          : %s (dim %d)", EMBEDDING_MODEL_NAME, expected_dim)
    log.info("DB dir / collection      : %s / %s", args.db, args.collection)

    if batch_failures:
        log.error("Ingestion completed WITH %d batch failures. Review logs above.", batch_failures)
        return 3

    # If everything new was upserted and nothing was lost, the collection count
    # should equal the number of valid chunks (idempotent upsert).
    if final_count < len(valid):
        log.warning("Collection count (%d) < valid chunks (%d). Some records may be missing.",
                    final_count, len(valid))
    else:
        log.info("OK: collection count >= valid chunk count (idempotent upsert confirmed).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
