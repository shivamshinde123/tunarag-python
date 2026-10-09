import asyncio

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph

from tunarag import (
    Candidate,
    EvaluationDataset,
    EvaluationExample,
    IntegerRange,
    LangChainAdapter,
    LangGraphAdapter,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    SearchSpace,
    Settings,
)


class CustomPipeline:
    async def ainvoke(self, payload, config=None):
        return payload

    async def run(self, candidate, example):
        return example, ()


@pytest.mark.parametrize("adapter_type", [LangChainAdapter, LangGraphAdapter])
def test_adapters_reject_handwritten_runnables_and_factory_results(adapter_type) -> None:
    with pytest.raises(TypeError, match="real"):
        adapter_type(CustomPipeline())
    adapter = adapter_type(factory=lambda candidate: CustomPipeline())
    with pytest.raises(TypeError, match="real"):
        asyncio.run(adapter.run(Candidate({"top_k": 2}), EvaluationExample("q", "question")))


def test_optimizer_rejects_custom_adapter_before_creating_a_store() -> None:
    with pytest.raises(TypeError, match="custom RAG adapters are unsupported"):
        Optimizer(
            adapter=CustomPipeline(),
            strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)})),
            evaluators=(MetricEvaluator("quality", lambda output, example: 1.0),),
            objective=Objective((ObjectiveTerm("quality"),)),
        )


@pytest.mark.parametrize("framework", ["langchain", "langgraph"])
def test_framework_parameters_change_optimizer_scores(framework: str) -> None:
    async def answer(payload, config):
        return {"answer": str(config["configurable"]["top_k"])}

    if framework == "langchain":
        adapter = LangChainAdapter(RunnableLambda(answer))
    else:
        builder = StateGraph(dict)
        builder.add_node("answer", answer)
        builder.add_edge(START, "answer")
        builder.add_edge("answer", END)
        adapter = LangGraphAdapter(builder.compile())
    optimizer = Optimizer(
        adapter=adapter,
        strategy=RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=0),
        evaluators=(MetricEvaluator("quality", lambda output, example: float(output["answer"])),),
        objective=Objective((ObjectiveTerm("quality"),)),
        settings=Settings.resolve(overrides={"max_trials": 2}, environ={}),
    )
    try:
        result = optimizer.optimize(
            EvaluationDataset.from_records([{"id": "q", "query": "question"}]),
            study_name=f"{framework}-parameters",
        )
        assert result.best_candidate.parameters["top_k"] == 2
        assert result.best_trial.objective.score == 2.0
    finally:
        optimizer.close()
