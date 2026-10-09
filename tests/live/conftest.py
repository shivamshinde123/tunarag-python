from __future__ import annotations

import os
from pathlib import Path

import pytest

from .support import RequestBudget, load_corpus
from .test_tracking import tracking_server as _tracking_server

tracking_server = _tracking_server


def pytest_addoption(parser):
    group = parser.getgroup("live integrations")
    group.addoption("--live", action="store_true", help="Enable real optional integration tests")
    group.addoption(
        "--live-paid", action="store_true", help="Authorize bounded OpenRouter requests"
    )
    group.addoption("--live-env", help="Explicit dotenv path; no automatic dotenv loading")
    group.addoption("--live-request-limit", type=int, default=40)
    group.addoption("--live-campaign", action="store_true", help="Enable extended PDF campaigns")
    group.addoption("--live-pdf", help="Local text-selectable PDF for the extended campaign")
    group.addoption("--live-held-out-report", help="Existing campaign held-out answers to score")
    group.addoption("--live-documents", default=str(Path(__file__).with_name("documents.json")))
    group.addoption("--live-dataset", default=str(Path(__file__).with_name("dataset.json")))


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "campaign" in item.keywords and not config.getoption("--live-campaign"):
            item.add_marker(pytest.mark.skip(reason="requires --live-campaign"))
        elif "live" in item.keywords and not config.getoption("--live"):
            item.add_marker(pytest.mark.skip(reason="requires --live"))
        elif "paid" in item.keywords and not config.getoption("--live-paid"):
            item.add_marker(pytest.mark.skip(reason="requires --live-paid"))


@pytest.fixture(scope="session")
def provider(pytestconfig):
    import httpx
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    env_path = pytestconfig.getoption("--live-env")
    if env_path:
        from dotenv import load_dotenv

        if not Path(env_path).is_file():
            pytest.fail("--live-env must name an existing file", pytrace=False)
        load_dotenv(env_path, override=False)
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        pytest.fail("Set OPENROUTER_API_KEY in the explicit dotenv file", pytrace=False)
    budget = RequestBudget(pytestconfig.getoption("--live-request-limit"))
    sync_client = httpx.Client(event_hooks={"request": [budget.before_request]}, timeout=45)
    async_client = httpx.AsyncClient(
        event_hooks={"request": [budget.before_async_request]},
        timeout=45,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    options = {
        "api_key": key,
        "base_url": "https://openrouter.ai/api/v1",
        "http_client": sync_client,
        "http_async_client": async_client,
        "max_retries": 0,
        "timeout": 45,
    }

    def chat(variable):
        return ChatOpenAI(
            **options,
            model=os.getenv(variable, "openai/gpt-4.1-mini"),
            temperature=0,
            max_tokens=512,
        )

    yield {
        "chat": chat("TUNARAG_LIVE_CHAT_MODEL"),
        "judge": chat("TUNARAG_LIVE_JUDGE_MODEL"),
        "embeddings": OpenAIEmbeddings(
            **options,
            model=os.getenv("TUNARAG_LIVE_EMBEDDING_MODEL", "openai/text-embedding-3-small"),
            check_embedding_ctx_length=False,
        ),
        "budget": budget,
    }
    sync_client.close()
    import asyncio

    asyncio.run(async_client.aclose())


@pytest.fixture(autouse=True)
def disable_live_telemetry(monkeypatch):
    monkeypatch.setenv("RAGAS_DO_NOT_TRACK", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")


@pytest.fixture(scope="session")
def corpus(pytestconfig):
    return load_corpus(
        Path(pytestconfig.getoption("--live-documents")),
        Path(pytestconfig.getoption("--live-dataset")),
    )
