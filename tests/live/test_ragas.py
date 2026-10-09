import asyncio
from types import SimpleNamespace

import pytest

from tunarag import EvaluationExample, RagasEvaluator

pytestmark = pytest.mark.live


def test_real_ragas_exact_match_without_provider():
    from ragas.metrics import ExactMatch

    evaluator = RagasEvaluator(
        [ExactMatch()],
        lambda output, example: {"response": output, "reference": example.reference_answer},
        raise_exceptions=True,
    )
    example = EvaluationExample("q", "What stores experiments?", reference_answer="SQLite")

    async def evaluate():
        correct = await evaluator.evaluate("SQLite", example)
        incorrect = await evaluator.evaluate("Redis", example)
        return correct, incorrect

    correct, incorrect = asyncio.run(evaluate())
    assert correct[0].value == 1
    assert incorrect[0].value == 0


def test_real_provider_and_judge_construction_without_requests(monkeypatch):
    from .conftest import provider
    from .test_provider import faithfulness

    monkeypatch.setenv("OPENROUTER_API_KEY", "placeholder-not-a-real-key")
    config = SimpleNamespace(getoption=lambda name: 1 if name == "--live-request-limit" else None)
    generator = provider.__wrapped__(config)
    clients = next(generator)
    try:
        assert isinstance(faithfulness(clients), RagasEvaluator)
        assert clients["budget"].used == 0
    finally:
        next(generator, None)


@pytest.mark.parametrize("failure_status", [429, 503, 200])
def test_real_sdk_http_failures_are_isolated(failure_status, tmp_path):
    import json

    import httpx
    from langchain_core.runnables import RunnableLambda
    from langchain_openai import ChatOpenAI

    from tunarag import (
        EvaluationDataset,
        IntegerRange,
        LangChainAdapter,
        MetricEvaluator,
        Objective,
        ObjectiveTerm,
        Optimizer,
        RandomSearch,
        RetryPolicy,
        SearchSpace,
        Settings,
        SQLiteStore,
    )

    requests = []

    def respond(request):
        model = json.loads(request.content)["model"]
        requests.append(model)
        if model == "failing":
            if failure_status == 200:
                return httpx.Response(
                    200, content=b"not-json", headers={"content-type": "application/json"}
                )
            return httpx.Response(failure_status, json={"error": {"message": "injected failure"}})
        return httpx.Response(
            200,
            json={
                "id": "mock-response",
                "object": "chat.completion",
                "model": model,
                "created": 0,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    sync_client = httpx.Client(transport=httpx.MockTransport(respond))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    def factory(candidate):
        chat = ChatOpenAI(
            model="failing" if candidate.parameters["value"] == 2 else "working",
            api_key="placeholder-not-a-real-key",
            base_url="https://openrouter.ai/api/v1",
            http_client=sync_client,
            http_async_client=async_client,
            max_retries=0,
        )
        return RunnableLambda(lambda payload: payload["question"]) | chat

    store = SQLiteStore(tmp_path / "failures.db")
    runner = Optimizer(
        adapter=LangChainAdapter(factory=factory),
        strategy=RandomSearch(SearchSpace({"value": IntegerRange(1, 2)}), seed=0),
        evaluators=(
            MetricEvaluator("quality", lambda output, example: float(output.content == "ok")),
        ),
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=Settings.resolve(overrides={"max_trials": 2, "concurrency": 1}, environ={}),
        retry_policy=RetryPolicy(max_retries=0, sample_timeout_seconds=5, trial_timeout_seconds=10),
    )
    try:
        result = runner.optimize(
            EvaluationDataset.from_records([{"id": "q", "query": "question"}]),
            study_name="sdk-failure-isolation",
        )
        assert len(result.failed_trials) == len(result.successful_trials) == 1
        assert result.best_candidate.parameters["value"] == 1
        assert requests == ["failing", "working"]
        assert all(trial.attempts == 1 for trial in result.trials)
        assert "injected failure" not in result.failed_trials[0].error
    finally:
        runner.close()
        store.close()
        sync_client.close()
        asyncio.run(async_client.aclose())
