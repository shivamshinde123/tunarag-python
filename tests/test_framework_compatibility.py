import asyncio
from typing import TypedDict

import pytest

from tunarag import Candidate, EvaluationExample, LangChainAdapter, LangGraphAdapter

try:
    from langchain_core.runnables import RunnableConfig, RunnableLambda
    from langgraph.graph import END, START, StateGraph
except ImportError:
    pytest.skip("optional framework packages are not installed", allow_module_level=True)


@pytest.mark.frameworks
def test_langchain_runnable_lambda_compatibility() -> None:
    async def answer(payload: dict[str, str], config: RunnableConfig) -> dict[str, str]:
        prefix = config["configurable"]["prefix"]
        return {"answer": f"{prefix}: {payload['question']}"}

    chain = RunnableLambda(answer)
    adapter = LangChainAdapter(chain, output_mapper=lambda output: output["answer"])

    output, usage = asyncio.run(
        adapter.run(
            Candidate({"prefix": "optimized"}),
            EvaluationExample(id="lc-1", query="What is TunaRAG?"),
        )
    )

    assert output == "optimized: What is TunaRAG?"
    assert usage[-1].component == "langchain.runnable"


class GraphState(TypedDict, total=False):
    question: str
    answer: str


@pytest.mark.frameworks
def test_compiled_langgraph_compatibility() -> None:
    async def answer(state: GraphState, config: RunnableConfig) -> GraphState:
        prefix = config["configurable"]["prefix"]
        return {"answer": f"{prefix}: {state['question']}"}

    builder = StateGraph(GraphState)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    graph = builder.compile()
    adapter = LangGraphAdapter(graph, output_mapper=lambda output: output["answer"])

    output, usage = asyncio.run(
        adapter.run(
            Candidate({"prefix": "optimized"}),
            EvaluationExample(id="lg-1", query="What is TunaRAG?"),
        )
    )

    assert output == "optimized: What is TunaRAG?"
    assert usage[-1].component == "langgraph.runnable"
