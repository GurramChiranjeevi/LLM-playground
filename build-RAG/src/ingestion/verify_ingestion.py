"""Verify a RAG ChromaDB ingestion.

Reopens the persistent ChromaDB database from disk in a FRESH process, checks
that the expected records were stored, validates that the embeddings are sane
(numbers, finite, consistent dimension), and runs a sample semantic similarity
search using the SAME embedding function used for ingestion.

This is intentionally a separate script from ``ingest.py``: verification must
prove that data was actually persisted to disk and is retrievable on its own,
not just that the in-memory write call returned successfully.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from pathlib import Path
from typing import Any

# Disable ChromaDB's anonymized telemetry BEFORE importing chromadb (see
# ingest.py for rationale).
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CHUNKS_FILE = PROJECT_ROOT / "chunks" / "chunks.json"
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "chroma_db"
DEFAULT_COLLECTION_NAME = "rag_chunks"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

log = logging.getLogger("rag.verify")


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # See ingest.py: silence chromadb's noisy (non-fatal) telemetry logger.
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)


def make_uid(source: str, chunk_index: int) -> str:
    return f"{source}::{chunk_index}"


def expected_valid_ids(chunks_path: Path) -> set[str]:
    """Recompute the set of valid chunk IDs straight from chunks.json.

    Re-runs the same lightweight validation as ingest.py so the comparison
    accounts for any records deliberately skipped during ingestion.
    """
    with chunks_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    ids: set[str] = set()
    for rec in data:
        if not isinstance(rec, dict):
            continue
        source, chunk_id, text = rec.get("source"), rec.get("chunk_id"), rec.get("text")
        if (isinstance(source, str) and source.strip()
                and isinstance(chunk_id, int) and not isinstance(chunk_id, bool)
                and isinstance(text, str) and text.strip()):
            ids.add(make_uid(source, chunk_id))
    return ids


def preview_vector(vec: list[float], n: int = 6) -> str:
    """Short human-readable preview of a vector (avoids dumping 384 floats)."""
    head = ", ".join(f"{x:.6f}" for x in vec[:n])
    return f"[{head}, ... ]"


def check_embeddings(collection: chromadb.Collection, sample: int) -> dict[str, Any]:
    """Fetch a sample of stored records and validate their embeddings.

    ChromaDB returns embeddings as a numpy 2D array; we convert rows to plain
    Python lists to avoid numpy 'ambiguous truth value' errors downstream.
    """
    got = collection.get(limit=sample, include=["documents", "metadatas", "embeddings"])
    ids = list(got.get("ids", []))
    docs = list(got.get("documents", []))
    metas = list(got.get("metadatas", []))
    embs_raw = got.get("embeddings")
    embs = [list(v) for v in embs_raw] if embs_raw is not None else []

    dims: set[int] = set()
    non_finite = 0
    empty = 0
    for vec in embs:
        if len(vec) == 0:
            empty += 1
            continue
        dims.add(len(vec))
        for x in vec:
            if not math.isfinite(float(x)):
                non_finite += 1
                break

    log.info("Sample size        : %d", len(ids))
    log.info("Embedding dims seen: %s", sorted(dims) or "n/a")
    log.info("Empty embeddings   : %d", empty)
    log.info("Non-finite values  : %d", non_finite)

    for i, (uid, doc, meta, vec) in enumerate(zip(ids, docs, metas, embs)):
        log.info("--- record %d ---", i + 1)
        log.info("  id        : %s", uid)
        log.info("  metadata  : %s", meta)
        log.info("  text[:120]: %s", (doc or "")[:120].replace("\n", " "))
        if vec:
            log.info("  vec dim   : %d", len(vec))
            log.info("  vec head  : %s", preview_vector(list(vec)))
        else:
            log.info("  vec       : MISSING")

    return {
        "count": len(ids),
        "dims": sorted(dims),
        "empty": empty,
        "non_finite": non_finite,
    }


def run_semantic_search(collection: chromadb.Collection, query: str, n: int) -> None:
    """Run a sample query using the collection's own embedding function."""
    log.info("=== Sample semantic search ===")
    log.info("Query: %r", query)
    log.info("Top-N: %d", n)
    # Passing query_texts lets ChromaDB embed the query with the SAME
    # embedding_function the collection was created with -> compatible space.
    res = collection.query(query_texts=[query], n_results=n)
    q_ids = res.get("ids", [[]])[0]
    q_docs = res.get("documents", [[]])[0]
    q_metas = res.get("metadatas", [[]])[0]
    q_dists = res.get("distances", [[]])[0]

    log.info("Results returned: %d", len(q_ids))
    for rank, (uid, doc, meta, dist) in enumerate(zip(q_ids, q_docs, q_metas, q_dists), 1):
        sim = 1.0 - float(dist)  # cosine distance -> cosine similarity
        log.info("  #%d dist=%.4f sim=%.4f id=%s", rank, dist, sim, uid)
        log.info("      source=%s chunk_index=%s", meta.get("source"), meta.get("chunk_index"))
        log.info("      text[:200]: %s", (doc or "")[:200].replace("\n", " "))

    log.info(
        "Interpretation: with cosine SPACE, 'dist' is cosine distance "
        "(0=identical, 2=opposite). sim=1-dist; higher sim = more relevant."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify RAG ingestion in ChromaDB.")
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_FILE)
    parser.add_argument("--db", type=Path, default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION_NAME)
    parser.add_argument("--sample", type=int, default=3,
                        help="Number of stored records to display in detail.")
    parser.add_argument("--query", default="how should I think about savings and compounding?",
                        help="Natural-language query for the sample semantic search.")
    parser.add_argument("--n", type=int, default=3, help="Top-N results for the query.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure_logging(args.verbose)
    log.info("=== RAG ingestion verification ===")
    log.info("ChromaDB dir: %s", args.db)
    log.info("Collection  : %s", args.collection)

    ok = True

    # 1. Reopen DB from disk in a fresh client/process ------------------------
    if not args.db.exists():
        log.error("ChromaDB directory not found: %s", args.db)
        log.error("Run ingest.py first.")
        return 1

    client = chromadb.PersistentClient(
        path=str(args.db),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    try:
        collection = client.get_collection(name=args.collection)
    except Exception as exc:
        log.error("Could not open collection '%s': %s", args.collection, exc)
        return 1

    # Use the same embedding function for the sample query.
    ef = DefaultEmbeddingFunction()

    # 2. Collection-level counts ---------------------------------------------
    stored = collection.count()
    log.info("Records in collection: %d", stored)

    # 3. Compare expected valid IDs vs stored unique IDs ----------------------
    try:
        expected = expected_valid_ids(args.chunks)
        log.info("Expected valid chunks (from chunks.json): %d", len(expected))
    except Exception as exc:
        log.warning("Could not read chunks.json to compute expected count: %s", exc)
        expected = set()

    if expected:
        all_ids = collection.get(include=[]).get("ids", [])
        stored_unique = set(all_ids)
        log.info("Stored unique IDs  : %d", len(stored_unique))
        missing = expected - stored_unique
        extra = stored_unique - expected
        if missing:
            log.warning("Missing from DB (%d): %s", len(missing), sorted(missing)[:5])
            ok = False
        else:
            log.info("All expected IDs present in the collection.")
        if extra:
            log.info("Extra IDs in DB (%d) [ok, e.g. older runs]: %s",
                     len(extra), sorted(extra)[:5])

    # 4. Validate embeddings on a sample -------------------------------------
    log.info("=== Sample record inspection ===")
    emb_info = check_embeddings(collection, sample=args.sample)
    if not emb_info["count"]:
        log.error("No records retrieved for inspection. Ingestion likely failed.")
        return 1
    if emb_info["empty"]:
        log.error("Some records have empty embeddings.")
        ok = False
    if emb_info["non_finite"]:
        log.error("Some embeddings contain non-finite (NaN/inf) values.")
        ok = False
    if len(emb_info["dims"]) == 1:
        log.info("Observed vector dimensionality: %d (consistent across sample)",
                 emb_info["dims"][0])
    elif emb_info["dims"]:
        log.error("Inconsistent embedding dimensions: %s", emb_info["dims"])
        ok = False

    # 5. Sample semantic search ----------------------------------------------
    run_semantic_search(collection, args.query, args.n)

    # 6. Verdict --------------------------------------------------------------
    log.info("=== Verification %s ===", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


