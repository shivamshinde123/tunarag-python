import asyncio
import json

import pytest

from tunarag import Candidate, EvaluationExample

pytestmark = pytest.mark.live


def test_framework_tool_round_trip(monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "true")
    import httpx
    from langchain_core.documents import Document
    from langchain_core.embeddings import DeterministicFakeEmbedding
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_openai import ChatOpenAI

    from .adk_tools import ToolPipeline
    from .paid_payload import validate_paid_payload

    sent = []

    def respond(request):
        body = json.loads(request.content)
        validate_paid_payload(body, {"openai/gpt-4.1-mini"}, allow_tools=True)
        sent.append(body)
        tool_call = len(sent) == 1
        message = {"role": "assistant", "content": None if tool_call else "Eight heads."}
        if tool_call:
            message["tool_calls"] = [
                {
                    "id": "call1",
                    "type": "function",
                    "function": {"name": "search_paper", "arguments": '{"query":"heads"}'},
                }
            ]
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 1,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if tool_call else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            chat = ChatOpenAI(
                api_key="offline",
                model="openai/gpt-4.1-mini",
                http_async_client=client,
                base_url="https://openrouter.ai/api/v1",
                max_retries=0,
            )
            vectors = InMemoryVectorStore.from_documents(
                [Document(page_content="Eight heads.")], DeterministicFakeEmbedding(size=16)
            )
            pipeline = ToolPipeline(vectors, chat)
            try:
                output, usage = await pipeline.adapter().run(
                    Candidate({"top_k": 1, "prompt_style": "brief"}),
                    EvaluationExample("q", "How many heads?"),
                )
                assert output["answer"] == "Eight heads."
                assert output["contexts"] == ["Eight heads."]
                assert len(pipeline.calls) == 1
                assert sum(item.component == "google_adk.model" for item in usage) == 2
                assert len(sent) == 2
                assert sent[0]["tool_choice"] != "none"
                assert sent[1]["tool_choice"] == "none"
            finally:
                await pipeline.close()

    asyncio.run(exercise())
