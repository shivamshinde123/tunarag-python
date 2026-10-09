import re

import pytest
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake import FakeListLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.vectorstores import InMemoryVectorStore
from test_usage_documentation import _run

from tunarag import (
    Candidate,
    Categorical,
    EvaluationDataset,
    IntegerRange,
    LangChainAdapter,
    MetricEvaluator,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    SearchSpace,
    Settings,
)


def dataset():
    return EvaluationDataset.from_records([{"id": "q", "query": "question"}])


def optimizer(adapter, *, strategy=None):
    return Optimizer(
        adapter=adapter,
        strategy=strategy or RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=0),
        evaluators=(
            MetricEvaluator("quality", lambda output, example: float(re.search(r"\d+", output)[0])),
        ),
        objective=Objective((ObjectiveTerm("quality"),)),
        settings=Settings.resolve(overrides={"max_trials": 2}, environ={}),
    )


@pytest.mark.parametrize("block", [4, 7, 8])
def test_readme_langchain_and_langgraph_tune_applied_parameters(block):
    graph_scope = _run(7)
    scope = (
        _run(
            8, {"graph": graph_scope["graph"], "LangGraphAdapter": graph_scope["LangGraphAdapter"]}
        )
        if block == 8
        else _run(block)
    )
    runner = optimizer(scope["adapter"])
    try:
        result = runner.optimize(dataset(), study_name=f"readme-{block}")
        assert result.best_candidate.parameters["top_k"] == 2
        assert {trial.objective.score for trial in result.successful_trials} == {1.0, 2.0}
    finally:
        runner.close()


def test_readme_factory_tunes_real_retrieval_chain_model_and_k():
    vector_store = InMemoryVectorStore.from_documents(
        [Document(page_content="context one"), Document(page_content="context two")],
        DeterministicFakeEmbedding(size=32),
    )
    scope = _run(
        5,
        {
            "LangChainAdapter": LangChainAdapter,
            "vector_store": vector_store,
            "create_retrieval_chain": create_retrieval_chain,
            "build_qa_chain": lambda model: create_stuff_documents_chain(
                FakeListLLM(responses=[model]),
                ChatPromptTemplate.from_template("{context}\n{input}"),
            ),
        },
    )
    for top_k in (1, 2):
        raw = scope["build_chain"](Candidate({"top_k": top_k, "model": "correct"})).invoke(
            {"input": "question"}
        )
        assert len(raw["context"]) == top_k
    runner = Optimizer(
        adapter=scope["adapter"],
        strategy=RandomSearch(
            SearchSpace({"top_k": IntegerRange(1, 2), "model": Categorical(("wrong", "correct"))}),
            seed=0,
        ),
        evaluators=(
            MetricEvaluator("quality", lambda output, example: float(output == "correct")),
        ),
        objective=Objective((ObjectiveTerm("quality"),)),
        settings=Settings.resolve(overrides={"max_trials": 4}, environ={}),
    )
    try:
        result = runner.optimize(dataset(), study_name="readme-factory")
        assert result.best_candidate.parameters["model"] == "correct"
        assert {trial.objective.score for trial in result.successful_trials} == {0.0, 1.0}
    finally:
        runner.close()


def test_readme_llm_search_tunes_real_framework_pipeline():
    class Client:
        async def generate_json(self, *, schema, context):
            return {
                "top_k": context["suggestion_number"] + 1,
                "temperature": 0.0,
                "model": "small",
                "prompt": "grounded",
            }

    space = _run(14)["space"]
    strategy = _run(16, {"space": space, "llm_client": Client()})["strategy"]
    runner = optimizer(_run(4)["adapter"], strategy=strategy)
    try:
        result = runner.optimize(dataset(), study_name="readme-llm-search")
        assert result.best_candidate.parameters["top_k"] == 2
        assert {trial.objective.score for trial in result.successful_trials} == {1.0, 2.0}
    finally:
        runner.close()


@pytest.mark.parametrize("block", [21, 22])
def test_readme_async_and_sync_entrypoints_select_better_candidate(block):
    runner = optimizer(_run(4)["adapter"])
    try:
        result = _run(block, {"optimizer": runner, "dataset": dataset()})["result"]
        assert result.best_candidate.parameters["top_k"] == 2
        assert {trial.objective.score for trial in result.successful_trials} == {1.0, 2.0}
    finally:
        runner.close()


@pytest.mark.parametrize("block", [25, 29])
def test_readme_cache_and_callbacks_preserve_tuning(block, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scope = _run(
        block,
        {
            "Optimizer": Optimizer,
            "adapter": _run(4)["adapter"],
            "strategy": RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=0),
            "evaluators": (
                MetricEvaluator(
                    "quality", lambda output, example: float(re.search(r"\d+", output)[0])
                ),
            ),
            "objective": Objective((ObjectiveTerm("quality"),)),
        },
    )
    try:
        result = scope["optimizer"].optimize(dataset(), study_name=f"readme-{block}")
        assert result.best_candidate.parameters["top_k"] == 2
        assert {trial.objective.score for trial in result.successful_trials} == {1.0, 2.0}
    finally:
        scope["optimizer"].close()
        if "cache" in scope:
            scope["cache"].close()
