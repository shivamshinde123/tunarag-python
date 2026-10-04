"""Provider-neutral synthetic QA dataset generation."""

from __future__ import annotations

import asyncio
import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .contracts import Fingerprintable
from .dataset import EvaluationDataset, EvaluationExample
from .domain import UsageRecord
from .errors import DatasetError
from .serialization import content_hash


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One source document approved for synthetic generation."""

    id: str
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, "source document id"))
        object.__setattr__(self, "text", _required_text(self.text, "source document text"))


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Half-open source character range supporting a generated QA pair."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (self.start, self.end)
        ):
            raise TypeError("source span offsets must be integers")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("source span must be a nonempty half-open range")


@dataclass(frozen=True, slots=True)
class SyntheticQA:
    """One provider-produced question, answer, and supporting provenance."""

    query: str
    answer: str
    source_spans: tuple[SourceSpan, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _required_text(self.query, "synthetic query"))
        object.__setattr__(self, "answer", _required_text(self.answer, "synthetic answer"))
        if self.confidence is not None:
            if (
                isinstance(self.confidence, bool)
                or not math.isfinite(self.confidence)
                or not 0.0 <= self.confidence <= 1.0
            ):
                raise ValueError("synthetic confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SyntheticGenerationRequest:
    """Structured request sent to a synthetic QA provider."""

    document: SourceDocument
    count: int
    seed: int


@dataclass(frozen=True, slots=True)
class SyntheticGenerationResponse:
    """Provider output with exact or estimated usage records."""

    items: tuple[SyntheticQA, ...]
    usage: tuple[UsageRecord, ...] = ()


class SyntheticQAProvider(Protocol):
    """Generate typed QA pairs for one source document."""

    async def generate(
        self, request: SyntheticGenerationRequest
    ) -> SyntheticGenerationResponse: ...


@dataclass(frozen=True, slots=True)
class SyntheticDatasetResult:
    """Generated evaluation dataset and provider usage."""

    dataset: EvaluationDataset
    usage: tuple[UsageRecord, ...]


class SyntheticDatasetBuilder:
    """Generate a validated dataset with bounded document concurrency."""

    def __init__(
        self,
        provider: SyntheticQAProvider,
        *,
        samples_per_document: int = 3,
        concurrency: int = 4,
        seed: int = 0,
        generator_version: str = "unspecified",
    ) -> None:
        for name, value in (
            ("samples_per_document", samples_per_document),
            ("concurrency", concurrency),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("synthetic generation seed must be an integer")
        self._provider = provider
        self._samples_per_document = samples_per_document
        self._concurrency = concurrency
        self._seed = seed
        self._generator_version = _required_text(generator_version, "generator version")

    async def generate(self, documents: Sequence[SourceDocument]) -> SyntheticDatasetResult:
        """Generate and validate examples in source-document order."""

        if not documents:
            raise DatasetError("synthetic generation requires source documents")
        if len({document.id for document in documents}) != len(documents):
            raise DatasetError("source document ids must be unique")
        semaphore = asyncio.Semaphore(self._concurrency)

        async def bounded(document: SourceDocument) -> SyntheticGenerationResponse:
            async with semaphore:
                request = SyntheticGenerationRequest(
                    document,
                    self._samples_per_document,
                    _document_seed(self._seed, document.id),
                )
                try:
                    response = await self._provider.generate(request)
                except Exception as error:
                    raise DatasetError(
                        "synthetic QA provider failed",
                        details={"document_id": document.id, "cause": type(error).__name__},
                    ) from error
                return _validate_response(response, request)

        responses = await asyncio.gather(*(bounded(document) for document in documents))
        examples: list[EvaluationExample] = []
        usage: list[UsageRecord] = []
        provider_identity = _provider_identity(self._provider)
        for document, response in zip(documents, responses, strict=True):
            request_seed = _document_seed(self._seed, document.id)
            usage.extend(response.usage)
            for index, item in enumerate(response.items):
                contexts = tuple(document.text[span.start : span.end] for span in item.source_spans)
                if not contexts:
                    contexts = (document.text,)
                metadata = {
                    "source_document_id": document.id,
                    "source_document_metadata": document.metadata,
                    "source_spans": [
                        {"start": span.start, "end": span.end} for span in item.source_spans
                    ],
                    "generator": provider_identity,
                    "generator_version": self._generator_version,
                    "seed": request_seed,
                    "confidence": item.confidence,
                    "review_status": "unreviewed",
                }
                example_id = content_hash(
                    {
                        "document_id": document.id,
                        "index": index,
                        "qa": metadata,
                        "query": item.query,
                        "answer": item.answer,
                    },
                    namespace="tunarag:synthetic-example:v1",
                )
                examples.append(
                    EvaluationExample(
                        id=example_id,
                        query=item.query,
                        reference_answer=item.answer,
                        reference_contexts=contexts,
                        relevant_document_ids=(document.id,),
                        tags=("synthetic",),
                        metadata=metadata,
                        synthetic=True,
                    )
                )
        return SyntheticDatasetResult(EvaluationDataset(tuple(examples)), tuple(usage))


def _validate_response(
    response: Any, request: SyntheticGenerationRequest
) -> SyntheticGenerationResponse:
    if not isinstance(response, SyntheticGenerationResponse):
        raise DatasetError(
            "synthetic provider returned an invalid response",
            details={"document_id": request.document.id},
        )
    if len(response.items) != request.count:
        raise DatasetError(
            "synthetic provider returned an unexpected item count",
            details={
                "document_id": request.document.id,
                "expected": request.count,
                "actual": len(response.items),
            },
        )
    if any(not isinstance(item, SyntheticQA) for item in response.items):
        raise DatasetError("synthetic provider returned invalid QA items")
    if any(not isinstance(item, UsageRecord) for item in response.usage):
        raise DatasetError("synthetic provider returned invalid usage records")
    for item in response.items:
        if any(span.end > len(request.document.text) for span in item.source_spans):
            raise DatasetError(
                "synthetic source span exceeds its document",
                details={"document_id": request.document.id},
            )
    return response


def _document_seed(seed: int, document_id: str) -> int:
    digest = content_hash(
        {"seed": seed, "document_id": document_id}, namespace="tunarag:synthetic-seed:v1"
    )
    return int(digest[:16], 16)


def _provider_identity(provider: SyntheticQAProvider) -> Mapping[str, Any]:
    identity: dict[str, Any] = {
        "type": f"{type(provider).__module__}.{type(provider).__qualname__}"
    }
    if isinstance(provider, Fingerprintable):
        identity["fingerprint"] = provider.fingerprint()
    return identity


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = unicodedata.normalize("NFC", value.lstrip("\ufeff"))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if any(unicodedata.category(char) == "Cc" and char not in {"\n", "\t"} for char in normalized):
        raise ValueError(f"{label} contains a disallowed control character")
    return normalized
