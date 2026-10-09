import asyncio
import json
import time
import tracemalloc

import pytest

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

pytestmark = pytest.mark.live


@pytest.mark.parametrize("fault", [429, 503, "timeout", "connection"])
@pytest.mark.parametrize("recover", [True, False])
def test_sdk_fault_isolation(fault, recover, tmp_path):
    import httpx
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    calls = []

    def transport(request):
        calls.append(json.loads(request.content))
        if len(calls) <= (1 if recover else 2):
            if fault == "timeout":
                raise httpx.ReadTimeout("injected timeout", request=request)
            if fault == "connection":
                raise httpx.ConnectError("injected connection loss", request=request)
            return httpx.Response(
                fault,
                headers={"retry-after": "0.01"},
                json={"error": {"message": "injected failure"}},
            )
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 1,
                "model": "offline",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Supported answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            },
        )

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            chat = ChatOpenAI(
                api_key="offline",
                model="offline",
                http_async_client=client,
                base_url="https://openrouter.ai/api/v1",
                max_retries=1,
            )
            chain = ChatPromptTemplate.from_template("{input}") | chat
            store = SQLiteStore(tmp_path / "fault.db")
            runner = Optimizer(
                adapter=LangChainAdapter(chain, input_key="input"),
                strategy=RandomSearch(SearchSpace({"marker": IntegerRange(1, 2)}), seed=0),
                evaluators=(MetricEvaluator("quality", lambda output, example: 1.0),),
                objective=Objective((ObjectiveTerm("quality"),)),
                store=store,
                settings=Settings.resolve(
                    overrides={"max_trials": 2, "concurrency": 1, "sample_concurrency": 1},
                    environ={},
                ),
                retry_policy=RetryPolicy(max_retries=0),
            )
            try:
                result = await runner.aoptimize(
                    EvaluationDataset.from_records([{"id": "q", "query": "Question"}]),
                    study_name="fault",
                )
                result.write_json(tmp_path / "fault-result.json")
                assert len(calls) == 3
                assert len(result.successful_trials) == (2 if recover else 1)
                assert len(result.failed_trials) == (0 if recover else 1)
                assert all(len(store.list_attempts(trial.id)) == 1 for trial in result.trials)
            finally:
                runner.close()
                store.close()

    asyncio.run(exercise())


def test_bounded_framework_stress(tmp_path):
    from langchain_classic.chains import create_retrieval_chain
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.documents import Document
    from langchain_core.embeddings import DeterministicFakeEmbedding
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda
    from langchain_core.vectorstores import InMemoryVectorStore

    vectors = InMemoryVectorStore.from_documents(
        [
            Document(page_content=f"Topic {index}: the verified answer is supported.")
            for index in range(256)
        ],
        DeterministicFakeEmbedding(size=16),
    )
    chat = FakeListChatModel(responses=["Supported answer"], sleep=0.002)
    prompt = ChatPromptTemplate.from_messages(
        [("system", "Answer from {context}"), ("human", "{input}")]
    )
    data = EvaluationDataset.from_records(
        [{"id": f"q{index}", "query": f"What is topic {index}?"} for index in range(8)]
    )
    rows = []

    async def exercise():
        for limit in (1, 4, 16):
            active = 0
            peak = 0

            async def enter(value):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.002)
                return value

            async def leave(value):
                nonlocal active
                active -= 1
                return value

            def factory(candidate):
                chain = create_retrieval_chain(
                    vectors.as_retriever(search_kwargs={"k": candidate.parameters["top_k"]}),
                    create_stuff_documents_chain(chat, prompt),
                )
                return RunnableLambda(enter) | chain | RunnableLambda(leave)

            store = SQLiteStore(tmp_path / f"load-{limit}.db")
            runner = Optimizer(
                adapter=LangChainAdapter(factory=factory, input_key="input"),
                strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 25)}), seed=7),
                evaluators=(
                    MetricEvaluator(
                        "quality", lambda output, example: float(bool(output["answer"]))
                    ),
                ),
                objective=Objective((ObjectiveTerm("quality"),)),
                store=store,
                settings=Settings.resolve(
                    overrides={
                        "max_trials": 25,
                        "concurrency": 1 if limit == 1 else 4,
                        "sample_concurrency": 4 if limit == 16 else 1,
                    },
                    environ={},
                ),
                retry_policy=RetryPolicy(max_retries=0),
            )
            tracemalloc.start()
            started = time.monotonic()
            try:
                result = await runner.aoptimize(data, study_name=f"stress-{limit}")
                assert len(result.successful_trials) == 25 and not result.failed_trials
                assert peak == limit and active == 0
                rows.append(
                    {
                        "limit": limit,
                        "peak": peak,
                        "trials": 25,
                        "samples": 200,
                        "seconds": time.monotonic() - started,
                        "peak_traced_bytes": tracemalloc.get_traced_memory()[1],
                    }
                )
            finally:
                tracemalloc.stop()
                runner.close()
                store.close()
        (tmp_path / "stress.json").write_text(json.dumps(rows, indent=2))

    asyncio.run(asyncio.wait_for(exercise(), timeout=240))
