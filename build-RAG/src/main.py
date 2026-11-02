"""Terminal-based streaming RAG question-answering application.

Run from the project root:
    .venv/bin/python -m src.main [options]
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):
    # Allow `python src/main.py` in addition to `python -m src.main`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_NUM_CTX,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_TOP_K,
    PROJECT_ROOT,
    Settings,
)
from src.generation.llm import OllamaError
from src.rag.pipeline import EmptyQuestionError, RAGPipeline

BANNER = """========================================
       TRANSCRIPT RAG ASSISTANT
========================================

Ask me anything about your transcripts.

Type 'exit' or 'quit' to close the application.
"""

DIM = "\033[2m"
RESET = "\033[0m"


def build_parser(env: Settings) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Terminal streaming RAG over the existing ChromaDB transcripts.",
    )
    p.add_argument("--chroma-dir", type=Path, default=None,
                   help=f"ChromaDB directory (default: {env.chroma_dir})")
    p.add_argument("--collection", default=None,
                   help=f"Collection name (default: {env.collection_name})")
    p.add_argument("--top-k", type=int, default=None,
                   help=f"Number of chunks to retrieve (default: {env.top_k})")
    p.add_argument("--max-distance", type=float, default=None,
                   help="Drop chunks with cosine distance greater than this value.")
    p.add_argument("--host", default=None,
                   help=f"Ollama base URL (default: {env.ollama_host})")
    p.add_argument("--model", default=None,
                   help=f"Ollama model (default: {env.ollama_model})")
    p.add_argument("--num-ctx", type=int, default=None,
                   help=f"Ollama context window (default: {env.num_ctx})")
    p.add_argument("--temperature", type=float, default=None,
                   help="Sampling temperature (default: 0.2)")
    p.add_argument("--timeout", type=float, default=None,
                   help=f"Ollama request timeout in seconds (default: {env.timeout:g})")
    p.add_argument("--think", dest="think", action="store_true", default=None,
                   help="Enable model thinking/reasoning mode (Qwen3).")
    p.add_argument("--no-think", dest="think", action="store_false", default=None,
                   help="Disable model thinking mode (default).")
    p.add_argument("--show-thinking", dest="show_thinking", action="store_true", default=None,
                   help="Render model thinking tokens (dimmed, stderr).")
    p.add_argument("--no-show-thinking", dest="show_thinking", action="store_false", default=None)
    p.add_argument("--debug", action="store_true", default=None,
                   help="Print retrieval details and full tracebacks.")
    return p


def settings_from_args(args: argparse.Namespace) -> Settings:
    env = Settings.from_env()
    return env.override(
        chroma_dir=args.chroma_dir,
        collection_name=args.collection,
        top_k=args.top_k,
        max_distance=args.max_distance,
        ollama_host=args.host,
        ollama_model=args.model,
        num_ctx=args.num_ctx,
        temperature=args.temperature,
        timeout=args.timeout,
        think=args.think,
        show_thinking=args.show_thinking,
        debug=args.debug,
    )


def _print_error(message: str) -> None:
    print(f"\n[ERROR] {message}", file=sys.stderr)


def _maybe_traceback(debug: bool) -> None:
    if debug:
        traceback.print_exc()


def run(settings: Settings) -> int:
    print(BANNER, flush=True)

    try:
        pipeline = RAGPipeline(settings)
    except (FileNotFoundError, ValueError, ConnectionError) as exc:
        _print_error(str(exc))
        _maybe_traceback(settings.debug)
        return 1

    if settings.debug:
        print(f"[debug] ChromaDB : {settings.chroma_dir} / {settings.collection_name}"
              f" ({pipeline.retriever.count} records)")
        print(f"[debug] Ollama   : {settings.ollama_host} / {settings.ollama_model}")

    try:
        pipeline.startup_checks()
    except OllamaError as exc:
        _print_error(str(exc))
        _maybe_traceback(settings.debug)
        return 1

    while True:
        try:
            question = input("\nYou: ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("\nGoodbye.")
            break

        question = question.strip()
        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if not question:
            print("Please enter a non-empty question (or 'exit').")
            continue

        try:
            chunks = pipeline.retrieve(question)
        except EmptyQuestionError as exc:
            print(str(exc))
            continue
        except RuntimeError as exc:
            _print_error(str(exc))
            _maybe_traceback(settings.debug)
            continue

        if settings.debug:
            print(pipeline.retriever.format_debug(chunks))

        if not chunks:
            print(
                "\nAssistant:\n\n"
                "I could not find any transcript content relevant to that question. "
                "Try rephrasing it or asking about a topic covered in the sessions."
            )
            if settings.max_distance is not None:
                print(f"(All results exceeded --max-distance={settings.max_distance}.)")
            continue

        print("\nAssistant:\n")
        try:
            for event in pipeline.stream_answer(question, chunks):
                if event.kind == "content":
                    sys.stdout.write(event.text)
                    sys.stdout.flush()
                elif event.kind == "thinking" and settings.show_thinking:
                    sys.stderr.write(f"{DIM}{event.text}{RESET}")
                    sys.stderr.flush()
            print()
        except KeyboardInterrupt:
            print("\n[interrupted]")
            continue
        except OllamaError as exc:
            print()
            _print_error(str(exc))
            _maybe_traceback(settings.debug)
            continue

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(Settings.from_env())
    args = parser.parse_args(argv)

    if args.top_k is not None and args.top_k < 1:
        parser.error("--top-k must be >= 1")

    settings = settings_from_args(args)
    try:
        return run(settings)
    except KeyboardInterrupt:
        print("\nGoodbye.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
