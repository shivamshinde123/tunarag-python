import asyncio

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from live.campaign import (
    ChatSuggestionProvider,
    PipelineBuilder,
    page_recall,
    question_sets,
    search_space,
    term_coverage,
)

from tunarag import Candidate
from tunarag.search import LLMSuggestionRequest


def test_campaign_suggestion_uses_schema_and_rejects_duplicate_choices():
    chat = FakeMessagesListChatModel(responses=[AIMessage(content='{"candidate_index":0}')])
    provider = ChatSuggestionProvider(chat)
    request = LLMSuggestionRequest(search_space().describe(), (), 0, 0)
    assert asyncio.run(provider.suggest(request)) == provider.choices[0]
    assert provider.valid == 1
    with pytest.raises(ValueError, match="available"):
        asyncio.run(provider.suggest(request))
    assert provider.valid == 1


def test_campaign_splits_and_metric_bounds():
    development, held_out = question_sets()
    assert len(development.examples) == 10 and len(held_out.examples) == 20
    example = development.examples[0]
    assert term_coverage({"answer": "Eight heads with dimension 64"}, example) == 1
    assert term_coverage({"answer": "Unknown"}, example) == 0
    assert page_recall({"pages": ["5", "5"]}, example) == 1
    assert page_recall({"pages": []}, example) == 0
    assert len(search_space().describe()) == 5


def test_campaign_synthetic_export_handles_frozen_metadata(tmp_path):
    import json

    from live.test_campaign import test_live_synthetic_qa_provenance as run_synthetic

    chat = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content=json.dumps(
                    {"items": [{"query": "Q1?", "answer": "A1"}, {"query": "Q2?", "answer": "A2"}]}
                ),
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )
        ]
    )
    run_synthetic({"chat": chat}, tmp_path)
    rows = json.loads((tmp_path / "synthetic.json").read_text())
    assert len(rows) == 2 and all(row["synthetic"] for row in rows)


@pytest.mark.parametrize("framework", ["langchain", "langgraph"])
def test_campaign_uses_framework_pipeline_and_applies_parameters(framework, tmp_path):
    provider = {
        "chat": FakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="Eight heads, 64 dimensions.",
                    usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                )
            ]
        ),
        "embeddings": DeterministicFakeEmbedding(size=32),
    }
    documents = [
        Document(
            page_content="Attention uses eight heads, each with dimension 64. " * 30,
            metadata={"page": index},
        )
        for index in range(3)
    ]
    builder = PipelineBuilder(documents, provider, framework, tmp_path)
    candidate = Candidate(
        {
            "top_k": 3,
            "chunk_size": 500,
            "overlap": 80,
            "search_type": "mmr",
            "prompt_style": "structured",
        }
    )
    example = question_sets()[0].examples[0]
    output, usage = asyncio.run(builder.adapter().run(candidate, example))
    assert len(output["contexts"]) == 3
    assert len(builder.stores) == 1
    assert builder.built == [dict(candidate.parameters)]
    assert output["latency_seconds"] >= 0
    assert output["generation_cost_estimate"] == pytest.approx(0.000012)
    assert usage[0].input_tokens == 10
    independent = asyncio.run(builder.independent_run(candidate, example))
    assert independent["answer"] == output["answer"]
