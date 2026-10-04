"""Small deterministic RAG implementation used by the quickstart example."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from tunarag import Candidate, EvaluationExample, MetricValue, UsageRecord, ValueStatus

_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class RetrievedAnswer:
    """Answer text and document identifiers returned by the reference RAG."""

    text: str
    document_ids: tuple[str, ...]


class ReferenceRAGAdapter:
    """Retrieve documents by token overlap and concatenate their text as an answer."""

    def __init__(self, documents: dict[str, str]) -> None:
        if not documents:
            raise ValueError("reference RAG requires at least one document")
        self._documents = dict(documents)

    async def run(
        self, candidate: Candidate, example: EvaluationExample
    ) -> tuple[RetrievedAnswer, tuple[UsageRecord, ...]]:
        """Run one deterministic retrieval and answer-generation sample."""

        started_at = time.perf_counter()
        top_k = candidate.parameters.get("top_k")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")

        query_tokens = _tokens(example.query)
        ranked = sorted(
            self._documents.items(),
            key=lambda item: (-len(query_tokens & _tokens(item[1])), item[0]),
        )
        selected = ranked[:top_k]
        answer = RetrievedAnswer(
            text=" ".join(text for _, text in selected),
            document_ids=tuple(document_id for document_id, _ in selected),
        )
        usage = UsageRecord(
            component="reference_rag",
            input_tokens=len(query_tokens),
            output_tokens=len(_tokens(answer.text)),
            cost=0.0,
            latency_seconds=time.perf_counter() - started_at,
        )
        return answer, (usage,)

    def fingerprint(self) -> dict[str, object]:
        """Identify the deterministic corpus without exposing mutable state."""

        return {
            "documents": tuple(sorted(self._documents.items())),
            "algorithm": "token-overlap-v1",
        }


class ReferenceQualityEvaluator:
    """Measure reference-answer token recall in the generated answer."""

    async def evaluate(
        self, output: RetrievedAnswer, example: EvaluationExample
    ) -> tuple[MetricValue, ...]:
        """Return a normalized answer-recall observation."""

        if example.reference_answer is None:
            return (
                MetricValue(
                    "answer_recall",
                    None,
                    status=ValueStatus.UNAVAILABLE,
                    coverage=0.0,
                ),
            )
        expected = _tokens(example.reference_answer)
        if not expected:
            return (
                MetricValue(
                    "answer_recall",
                    None,
                    status=ValueStatus.UNAVAILABLE,
                    coverage=0.0,
                ),
            )
        score = len(expected & _tokens(output.text)) / len(expected)
        return (MetricValue("answer_recall", score),)

    def fingerprint(self) -> dict[str, str]:
        """Return stable evaluator semantics for resume compatibility."""

        return {"metric": "answer_recall", "algorithm": "token-recall-v1"}


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.casefold()))
