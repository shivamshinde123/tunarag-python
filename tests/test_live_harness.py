from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from live.support import RequestBudget, load_corpus
from live.test_provider import rag_pipeline
from live.test_provider import test_live_rag_optimization_and_completed_resume as run_tuning


def test_live_request_budget_rejects_extra_requests_and_other_hosts():
    budget = RequestBudget(1)
    request = SimpleNamespace(url=SimpleNamespace(scheme="https", host="openrouter.ai"))
    budget.before_request(request)
    with pytest.raises(RuntimeError, match="exhausted"):
        budget.before_request(request)
    assert budget.used == 1
    with pytest.raises(RuntimeError, match="only contact"):
        RequestBudget(1).before_request(
            SimpleNamespace(url=SimpleNamespace(scheme="https", host="example.com"))
        )
    with pytest.raises(ValueError):
        RequestBudget(0)


def test_live_corpus_rejects_unknown_document_reference(tmp_path):
    documents = Path(__file__).with_name("live") / "documents.json"
    records = tmp_path / "records.json"
    records.write_text(
        '[{"id":"q","query":"question","reference_answer":"answer",'
        '"relevant_document_ids":["unknown"]}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="reference supplied"):
        load_corpus(documents, records)


def test_live_optimization_harness_offline(tmp_path):
    directory = Path(__file__).with_name("live")
    corpus = load_corpus(directory / "documents.json", directory / "dataset.json")
    provider = {
        "chat": FakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="SQLite",
                    usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                )
            ]
        ),
        "embeddings": DeterministicFakeEmbedding(size=32),
        "budget": RequestBudget(1),
    }
    pipeline = rag_pipeline.__wrapped__(provider, corpus)
    run_tuning("retrieval_recall", pipeline, provider, tmp_path)
