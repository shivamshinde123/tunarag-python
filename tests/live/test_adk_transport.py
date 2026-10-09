import asyncio

import pytest

from tunarag import AdapterError, Candidate, EvaluationExample, GoogleADKAdapter

from .support import RequestBudget
from .test_google_adk import adk_model

pytestmark = pytest.mark.live


@pytest.mark.parametrize("mode", ["success", "upstream_failure", "exhausted_budget"])
def test_adk_uses_guarded_openrouter_client(mode, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "true")
    import httpx
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from langchain_openai import ChatOpenAI

    budget = RequestBudget(1)
    sent = []
    guarded = []
    if mode == "exhausted_budget":
        budget.used = 1

    async def guard(request):
        guarded.append(str(request.url))
        await budget.before_async_request(request)

    def respond(request):
        import json

        payload = json.loads(request.content)
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert payload["model"] == "openai/gpt-4.1-mini"
        assert payload["max_tokens"] == 512
        assert not payload.get("tools") and not payload.get("stream")
        sent.append(payload)
        if mode == "upstream_failure":
            return httpx.Response(503, json={"error": {"message": "test unavailable"}})
        return httpx.Response(
            200,
            json={
                "id": "offline-adk",
                "object": "chat.completion",
                "created": 1,
                "model": "openai/gpt-4.1-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Verified"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            },
        )

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            event_hooks={"request": [guard]},
        ) as client:
            chat = ChatOpenAI(
                api_key="offline-test-key",
                base_url="https://openrouter.ai/api/v1",
                model="openai/gpt-4.1-mini",
                http_async_client=client,
                max_retries=0,
            )
            runner = InMemoryRunner(agent=Agent(name="transport", model=adk_model(chat)))
            adapter = GoogleADKAdapter(runner)
            try:
                if mode == "success":
                    output, usage = await adapter.run(
                        Candidate({"top_k": 1}), EvaluationExample("q", "test")
                    )
                    assert output["answer"] == "Verified"
                    assert any(
                        item.input_tokens == 10 and item.output_tokens == 2 for item in usage
                    )
                else:
                    with pytest.raises(AdapterError, match="runner returned an error event"):
                        await adapter.run(Candidate({"top_k": 1}), EvaluationExample("q", "test"))
                sessions = await runner.session_service.list_sessions(
                    app_name=runner.app_name, user_id="tunarag-evaluation"
                )
                assert sessions.sessions == []
                assert len(sent) == (0 if mode == "exhausted_budget" else 1)
                assert len(guarded) == 1
                assert budget.used == 1
            finally:
                await runner.close()

    asyncio.run(exercise())
