"""Coordinates retrieval and generation for the terminal RAG app."""

from __future__ import annotations

from collections.abc import Iterator

from src.config import Settings
from src.generation.llm import OllamaClient, StreamEvent, build_messages
from src.retrieval.retriever import Retriever, RetrievedChunk


class EmptyQuestionError(ValueError):
    pass


class RAGPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.retriever = Retriever(
            chroma_dir=settings.chroma_dir,
            collection_name=settings.collection_name,
            top_k=settings.top_k,
            max_distance=settings.max_distance,
        )
        self.llm = OllamaClient(
            host=settings.ollama_host,
            model=settings.ollama_model,
            num_ctx=settings.num_ctx,
            temperature=settings.temperature,
            think=settings.think,
            timeout=settings.timeout,
        )

    def startup_checks(self) -> None:
        """Verify both backends before entering the interactive loop."""
        _ = self.retriever.count
        self.llm.ensure_available()

    def retrieve(self, question: str) -> list[RetrievedChunk]:
        if not question or not question.strip():
            raise EmptyQuestionError("Please enter a non-empty question.")
        return self.retriever.retrieve(question, top_k=self.settings.top_k)

    def stream_answer(
        self, question: str, chunks: list[RetrievedChunk]
    ) -> Iterator[StreamEvent]:
        messages = build_messages(question, chunks)
        yield from self.llm.stream_chat(messages)
