import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda

from tunarag import Candidate, EvaluationExample, LangChainAdapter, UsageRecord


@dataclass
class Message:
    content: str
    usage_metadata: dict[str, int]


class FakeRunnable(RunnableLambda):
    def __init__(self, output: Any) -> None:
        super().__init__(lambda value: output)
        self.output = output
        self.calls: list[tuple[Any, Any]] = []

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        del kwargs
        self.calls.append((input, config))
        return self.output


def example() -> EvaluationExample:
    return EvaluationExample(id="example-1", query="What is TunaRAG?")


def test_langchain_adapter_has_minimal_runnable_defaults() -> None:
    message = Message(
        "TunaRAG optimizes RAG systems.",
        {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9},
    )
    runnable = FakeRunnable({"answer": message})
    adapter = LangChainAdapter(runnable)
    candidate = Candidate({"top_k": 3})

    output, usage = asyncio.run(adapter.run(candidate, example()))

    assert output == {"answer": message}
    assert runnable.calls == [
        (
            {"question": "What is TunaRAG?"},
            {"configurable": {"top_k": 3}},
        )
    ]
    assert usage[0] == UsageRecord(
        component="langchain.message",
        input_tokens=4,
        output_tokens=5,
    )
    assert usage[1].component == "langchain.runnable"
    assert usage[1].latency_seconds is not None
    assert usage[1].latency_seconds >= 0


def test_langgraph_adapter_supports_state_and_output_mapping() -> None:
    graph = FakeRunnable({"question": "q", "answer": "optimized"})
    adapter = LangChainAdapter(
        graph,
        input_mapper=lambda sample, candidate: {
            "question": sample.query,
            "top_k": candidate.parameters["top_k"],
        },
        config_mapper=lambda candidate: {
            "configurable": {"thread_id": "evaluation"},
            "tags": [f"top-k-{candidate.parameters['top_k']}"],
        },
        output_mapper=lambda output: output["answer"],
        capture_message_usage=False,
    )

    output, usage = asyncio.run(adapter.run(Candidate({"top_k": 2}), example()))

    assert output == "optimized"
    assert graph.calls == [
        (
            {"question": "What is TunaRAG?", "top_k": 2},
            {
                "configurable": {"thread_id": "evaluation"},
                "tags": ["top-k-2"],
            },
        )
    ]
    assert [item.component for item in usage] == ["langchain.runnable"]


def test_runnable_factory_builds_per_candidate_and_customizes_usage() -> None:
    built: list[Candidate] = []

    def factory(candidate: Candidate) -> FakeRunnable:
        built.append(candidate)
        return FakeRunnable({"answer": "ok"})

    adapter = LangChainAdapter(
        factory=factory,
        usage_mapper=lambda output: (UsageRecord("provider", output_tokens=len(output)),),
        identity={"pipeline": "support-rag-v2"},
    )
    candidate = Candidate({"model": "small"})

    _, usage = asyncio.run(adapter.run(candidate, example()))

    assert built == [candidate]
    assert usage[0] == UsageRecord("provider", output_tokens=1)
    assert adapter.fingerprint()["identity"] == {"pipeline": "support-rag-v2"}
    assert adapter.fingerprint()["factory"].endswith("factory")


def test_noncanonical_examples_pass_through_by_default() -> None:
    runnable = FakeRunnable("ok")
    adapter = LangChainAdapter(runnable)
    custom_example = {"messages": ["hello"]}

    asyncio.run(adapter.run(Candidate({"temperature": 0.1}), custom_example))

    assert runnable.calls[0][0] is custom_example


@pytest.mark.parametrize("adapter_type", [LangChainAdapter])
def test_runnable_adapter_rejects_invalid_construction(adapter_type: Any) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        adapter_type()
    with pytest.raises(ValueError, match="exactly one"):
        adapter_type(FakeRunnable("ok"), factory=lambda candidate: FakeRunnable(candidate))
    with pytest.raises(TypeError, match="ainvoke"):
        adapter_type(object())
    with pytest.raises(ValueError, match="input key"):
        adapter_type(FakeRunnable("ok"), input_key=" ")


def test_factory_result_and_mapper_usage_are_validated() -> None:
    invalid_factory = LangChainAdapter(factory=lambda candidate: object())
    invalid_config = LangChainAdapter(
        FakeRunnable("ok"),
        config_mapper=lambda candidate: "invalid",  # type: ignore[arg-type,return-value]
    )
    invalid_usage = LangChainAdapter(
        FakeRunnable("ok"),
        usage_mapper=lambda output: ("invalid",),  # type: ignore[arg-type,return-value]
    )

    with pytest.raises(TypeError, match="ainvoke"):
        asyncio.run(invalid_factory.run(Candidate({"value": 1}), example()))
    with pytest.raises(TypeError, match="mapping"):
        asyncio.run(invalid_config.run(Candidate({"value": 1}), example()))
    with pytest.raises(TypeError, match="UsageRecord"):
        asyncio.run(invalid_usage.run(Candidate({"value": 1}), example()))
