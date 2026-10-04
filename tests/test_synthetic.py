import asyncio
from typing import Any

import pytest

from tunarag import (
    DatasetError,
    SourceDocument,
    SourceSpan,
    SyntheticDatasetBuilder,
    SyntheticGenerationRequest,
    SyntheticGenerationResponse,
    SyntheticQA,
    UsageRecord,
)


class Provider:
    def __init__(self) -> None:
        self.requests: list[SyntheticGenerationRequest] = []

    async def generate(self, request: SyntheticGenerationRequest) -> SyntheticGenerationResponse:
        self.requests.append(request)
        items = tuple(
            SyntheticQA(
                query=f"Question {index}?",
                answer="TunaRAG",
                source_spans=(SourceSpan(0, 7),),
                confidence=0.9,
            )
            for index in range(request.count)
        )
        return SyntheticGenerationResponse(items, (UsageRecord("synthetic", input_tokens=10),))

    def fingerprint(self) -> Any:
        return {"model": "test-generator"}


def test_builder_generates_deterministic_provenance_and_usage() -> None:
    provider = Provider()
    documents = (SourceDocument("doc-1", "TunaRAG documentation."),)
    builder = SyntheticDatasetBuilder(
        provider, samples_per_document=2, seed=7, generator_version="prompt-v2"
    )

    first = asyncio.run(builder.generate(documents))
    second = asyncio.run(builder.generate(documents))

    assert first.dataset.version == second.dataset.version
    assert len(first.dataset.examples) == 2
    assert len(first.usage) == 1
    example = first.dataset.examples[0]
    assert example.synthetic is True
    assert example.reference_contexts == ("TunaRAG",)
    assert example.relevant_document_ids == ("doc-1",)
    assert example.metadata["generator_version"] == "prompt-v2"
    assert example.metadata["generator"]["fingerprint"] == {"model": "test-generator"}
    assert provider.requests[0].seed == provider.requests[1].seed


def test_builder_redacts_provider_exception_messages() -> None:
    class FailingProvider:
        async def generate(
            self, request: SyntheticGenerationRequest
        ) -> SyntheticGenerationResponse:
            raise RuntimeError(f"private text: {request.document.text}")

    builder = SyntheticDatasetBuilder(FailingProvider(), samples_per_document=1)
    with pytest.raises(DatasetError) as raised:
        asyncio.run(builder.generate((SourceDocument("doc", "private source"),)))

    assert "private source" not in str(raised.value)
    assert raised.value.details["cause"] == "RuntimeError"


def test_builder_validates_counts_spans_and_inputs() -> None:
    class BadProvider:
        async def generate(
            self, request: SyntheticGenerationRequest
        ) -> SyntheticGenerationResponse:
            return SyntheticGenerationResponse(
                (SyntheticQA("Q?", "A", (SourceSpan(0, len(request.document.text) + 1),)),)
            )

    builder = SyntheticDatasetBuilder(BadProvider(), samples_per_document=1)
    with pytest.raises(DatasetError, match="span"):
        asyncio.run(builder.generate((SourceDocument("doc", "short"),)))
    with pytest.raises(DatasetError, match="source documents"):
        asyncio.run(builder.generate(()))
    with pytest.raises(ValueError, match="positive integer"):
        SyntheticDatasetBuilder(BadProvider(), concurrency=0)
