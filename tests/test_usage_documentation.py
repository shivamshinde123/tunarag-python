import ast
import asyncio
import csv
import inspect
import json
import random
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from tunarag import (
    Candidate,
    EvaluationDataset,
    EvaluationExample,
    IntegerRange,
    MetricEvaluator,
    MetricValue,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RandomSearch,
    SearchSpace,
    Settings,
    SQLiteStore,
    TunaRAGError,
    UsageRecord,
)

ROOT = Path(__file__).parents[1]
EXPECTED_EXAMPLE_COUNT = 36


def _usage_blocks() -> list[str]:
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    current: list[str] | None = None
    for line in lines:
        if line == "```python":
            if current is not None:
                raise AssertionError("nested Python fence in README.md")
            current = []
        elif line == "```" and current is not None:
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    assert current is None, "unclosed Python fence in README.md"
    assert len(blocks) == EXPECTED_EXAMPLE_COUNT
    return blocks


BLOCKS = _usage_blocks()


def test_readme_illustrations_are_local_and_present() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    illustration_directory = ROOT / "docs/assets/tunarag-python-readme-illustrations"
    illustrations = sorted(illustration_directory.glob("*.png"))

    assert "raw.githubusercontent.com" not in readme
    assert len(illustrations) == 6
    for illustration in illustrations:
        relative_path = illustration.relative_to(ROOT).as_posix()
        assert f"]({relative_path})" in readme


def _run(index: int, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    scope = {} if namespace is None else namespace
    code = compile(
        BLOCKS[index - 1],
        f"README.md example {index}",
        "exec",
        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
    )
    result = eval(code, scope)
    if inspect.isawaitable(result):
        asyncio.run(result)
    return scope


class _Adapter:
    async def run(
        self, candidate: Candidate, example: EvaluationExample
    ) -> tuple[dict[str, Any], tuple[UsageRecord, ...]]:
        return {
            "answer": example.reference_answer or example.query,
            "contexts": list(example.reference_contexts),
            "document_ids": list(example.relevant_document_ids),
            "candidate": dict(candidate.parameters),
        }, (UsageRecord("fixture", latency_seconds=0.001),)

    def fingerprint(self) -> object:
        return {"fixture": 1}


def _dataset() -> EvaluationDataset:
    return EvaluationDataset.from_records(
        [
            {
                "id": "q1",
                "query": "What is TunaRAG?",
                "reference_answer": "A RAG optimizer",
                "reference_contexts": ["A RAG optimizer"],
                "relevant_document_ids": ["doc-1"],
                "metadata": {"tenant": "demo"},
            }
        ]
    )


def _objective() -> Objective:
    return Objective((ObjectiveTerm("answer_quality"),))


def _evaluators() -> tuple[MetricEvaluator, ...]:
    return (MetricEvaluator("answer_quality", lambda _output, _example: 1.0),)


def _strategy(seed: int = 1) -> RandomSearch:
    return RandomSearch(SearchSpace({"top_k": IntegerRange(1, 2)}), seed=seed)


def _optimizer(**overrides: Any) -> Optimizer:
    arguments: dict[str, Any] = {
        "adapter": _Adapter(),
        "strategy": _strategy(),
        "evaluators": _evaluators(),
        "objective": _objective(),
        "settings": Settings.resolve(
            overrides={"max_trials": 1, "concurrency": 1, "sample_concurrency": 1},
            environ={},
        ),
    }
    arguments.update(overrides)
    return Optimizer(**arguments)


class _Runnable:
    def __init__(self, function: Any) -> None:
        self.function = function

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        del kwargs
        result = self.function(input, config)
        return await result if inspect.isawaitable(result) else result


def _install_framework_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import langchain_core.runnables  # noqa: F401
    except ImportError:
        core = ModuleType("langchain_core")
        runnables = ModuleType("langchain_core.runnables")
        runnables.RunnableLambda = _Runnable  # type: ignore[attr-defined]
        core.runnables = runnables  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "langchain_core", core)
        monkeypatch.setitem(sys.modules, "langchain_core.runnables", runnables)

    try:
        import langgraph.graph  # noqa: F401
    except ImportError:
        graph_package = ModuleType("langgraph")
        graph_module = ModuleType("langgraph.graph")

        class StateGraph:
            def __init__(self, state: Any) -> None:
                del state
                self.node: Any = None

            def add_node(self, name: str, node: Any) -> None:
                del name
                self.node = node

            def add_edge(self, start: str, end: str) -> None:
                del start, end

            def compile(self) -> _Runnable:
                return _Runnable(self.node)

        graph_module.START = "__start__"  # type: ignore[attr-defined]
        graph_module.END = "__end__"  # type: ignore[attr-defined]
        graph_module.StateGraph = StateGraph  # type: ignore[attr-defined]
        graph_package.graph = graph_module  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "langgraph", graph_package)
        monkeypatch.setitem(sys.modules, "langgraph.graph", graph_module)


def test_examples_1_to_3_quickstart_and_custom_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    quickstart = _run(1)
    assert quickstart["result"].best_candidate is not None
    contract = _run(2)
    assert callable(contract["run"])
    adapter_scope = _run(3)

    class Service:
        async def answer(self, **kwargs: Any) -> Any:
            assert kwargs == {"query": "question", "top_k": 2, "model": "small"}
            return SimpleNamespace(
                input_tokens=10,
                output_tokens=4,
                cost=0.01,
                latency_seconds=0.2,
            )

    adapter = adapter_scope["ExistingRAGAdapter"](Service())
    output, usage = asyncio.run(
        adapter.run(
            Candidate({"top_k": 2, "model": "small"}),
            EvaluationExample("q", "question"),
        )
    )
    assert output.output_tokens == 4
    assert usage[0].pricing_version == "provider-2026-10"
    assert adapter.fingerprint()["adapter_version"] == 2


def test_examples_4_to_8_framework_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_framework_stubs(monkeypatch)
    example = EvaluationExample("q", "question")
    candidate = Candidate({"top_k": 2, "model": "small"})

    chain_scope = _run(4)
    output, usage = asyncio.run(chain_scope["adapter"].run(candidate, example))
    assert output == "Used top_k=2 for question"
    assert usage[-1].component == "langchain.runnable"

    class VectorStore:
        def as_retriever(self, *, search_kwargs: Mapping[str, Any]) -> Any:
            return SimpleNamespace(top_k=search_kwargs["k"])

    def create_retrieval_chain(retriever: Any, qa_chain: Any) -> _Runnable:
        return _Runnable(
            lambda inputs, _config: {"answer": f"{inputs['question']}:{retriever.top_k}:{qa_chain}"}
        )

    factory_scope = _run(
        5,
        {
            "vector_store": VectorStore(),
            "create_retrieval_chain": create_retrieval_chain,
            "build_qa_chain": lambda model: model,
            "LangChainAdapter": chain_scope["LangChainAdapter"],
        },
    )
    output, _ = asyncio.run(factory_scope["adapter"].run(candidate, example))
    assert output == "question:2:small"

    async def custom_chain(inputs: Any, config: Any) -> dict[str, Any]:
        assert inputs == {"input": "question", "retrieval_limit": 2}
        assert config["configurable"] == {"model": "small"}
        return {"answer": "mapped", "usage": {"input_tokens": 5, "output_tokens": 2}}

    custom_scope = _run(
        6,
        {
            "LangChainAdapter": chain_scope["LangChainAdapter"],
            "chain": _Runnable(custom_chain),
            "UsageRecord": UsageRecord,
        },
    )
    output, usage = asyncio.run(custom_scope["adapter"].run(candidate, example))
    assert output == "mapped"
    assert usage[0].input_tokens == 5

    graph_scope = _run(7)
    output, usage = asyncio.run(graph_scope["adapter"].run(candidate, example))
    assert output == "answer for question with 2 documents"
    assert usage[-1].component == "langgraph.runnable"
    state_scope = _run(
        8,
        {"LangGraphAdapter": graph_scope["LangGraphAdapter"], "graph": graph_scope["graph"]},
    )
    output, _ = asyncio.run(state_scope["adapter"].run(candidate, example))
    assert output == "answer for question with 2 documents"


def test_examples_9_to_12_dataset_workflows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    example_scope = _run(9)
    assert example_scope["example"].metadata["tenant"] == "demo"

    records = [
        {
            "id": "file-q",
            "query": "Question?",
            "reference_answer": "Answer",
            "metadata": {"tenant": "demo"},
        }
    ]
    Path("evaluation.json").write_text(json.dumps(records), encoding="utf-8")
    Path("evaluation.jsonl").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    with Path("evaluation.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0])
        writer.writeheader()
        writer.writerow({**records[0], "metadata": json.dumps(records[0]["metadata"])})

    dataset_scope = _run(10)
    assert dataset_scope["dataset"].examples[0].metadata["tenant"] == "demo"
    assert dataset_scope["json_dataset"].examples == dataset_scope["jsonl_dataset"].examples
    split_scope = _run(11, {"dataset": dataset_scope["dataset"]})
    assert len(split_scope["optimization_data"].examples) == 1
    memory_scope = _run(12)
    assert memory_scope["dataset"].version == "support-set-v4"


def test_examples_13_to_16_synthetic_and_search() -> None:
    synthetic_scope = _run(13)
    assert len(synthetic_scope["dataset"].examples) == 2
    assert synthetic_scope["generation_usage"][0].output_tokens == 40
    search_scope = _run(14)
    random_scope = _run(15, {"space": search_scope["space"]})
    candidate = asyncio.run(random_scope["strategy"].suggest())
    assert search_scope["space"].validate(candidate.parameters) == candidate

    class Client:
        async def generate_json(self, *, schema: Any, context: Any) -> dict[str, Any]:
            assert schema["top_k"]["type"] == "integer"
            assert context["suggestion_number"] == 0
            return {
                "top_k": 3,
                "temperature": 0.2,
                "model": "small",
                "prompt": "grounded",
            }

    llm_scope = _run(16, {"space": search_scope["space"], "llm_client": Client()})
    suggestion = asyncio.run(llm_scope["strategy"].suggest())
    assert suggestion.parameters["prompt"] == "grounded"


def test_examples_17_to_20_evaluation_objective_and_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluator_scope = _run(17)
    example = EvaluationExample(
        "q",
        "question",
        reference_answer="answer",
        relevant_document_ids=("doc-1",),
    )
    exact = asyncio.run(
        evaluator_scope["exact_match_evaluator"].evaluate({"answer": "answer"}, example)
    )
    assert exact[0].value == 1.0
    retrieval = asyncio.run(
        evaluator_scope["RetrievalEvaluator"]().evaluate({"document_ids": ["doc-1"]}, example)
    )
    assert retrieval[0].value == 1.0

    metrics_module = ModuleType("ragas.metrics")
    metrics_module.AnswerRelevancy = type("AnswerRelevancy", (), {})  # type: ignore[attr-defined]
    metrics_module.Faithfulness = type("Faithfulness", (), {})  # type: ignore[attr-defined]
    ragas_module = ModuleType("ragas")
    ragas_module.metrics = metrics_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ragas", ragas_module)
    monkeypatch.setitem(sys.modules, "ragas.metrics", metrics_module)
    ragas_scope = _run(18, {"evaluation_llm": object(), "evaluation_embeddings": object()})
    assert type(ragas_scope["ragas_evaluator"]).__name__ == "RagasEvaluator"

    objective_scope = _run(19)
    objective_result = objective_scope["objective"].evaluate(
        (
            MetricValue("answer_quality", 0.8),
            MetricValue("cost_usd", 0.01),
            MetricValue("latency_seconds", 1.0),
        )
    )
    assert objective_result.score == pytest.approx(0.8)

    monkeypatch.chdir(tmp_path)
    Path("tunarag.toml").write_text("[tunarag]\nmax_trials = 5\n", encoding="utf-8")
    settings_scope = _run(20)
    assert settings_scope["settings"].max_trials == 50
    assert settings_scope["settings"].concurrency == 4


def test_examples_21_to_24_optimizer_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    async_optimizer = _optimizer()
    async_scope = _run(21, {"optimizer": async_optimizer, "dataset": _dataset()})
    assert async_scope["result"].best_candidate is not None
    async_optimizer.close()

    sync_optimizer = _optimizer()
    sync_scope = _run(22, {"optimizer": sync_optimizer, "dataset": _dataset()})
    assert sync_scope["result"].best_candidate is not None
    sync_optimizer.close()

    class QualityEvaluator:
        async def evaluate(self, output: Any, example: Any) -> tuple[MetricValue, ...]:
            del output, example
            return (
                MetricValue("answer_quality", 1.0),
                MetricValue("cost_usd", 0.01),
                MetricValue("latency_seconds", 0.01),
            )

        def fingerprint(self) -> object:
            return {"quality": 1}

    durable_scope = _run(
        23,
        {
            "adapter": _Adapter(),
            "strategy": _strategy(),
            "quality_evaluator": QualityEvaluator(),
            "retrieval_evaluator": MetricEvaluator("extra", lambda _o, _e: 1.0),
            "objective": _run(19)["objective"],
            "dataset": _dataset(),
        },
    )
    assert durable_scope["result"].best_candidate is not None
    policy_scope = _run(24)
    assert policy_scope["policy"].max_attempts == 4


def test_examples_25_to_30_cache_resume_callbacks_and_mlflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cache_scope = _run(
        25,
        {
            "Optimizer": Optimizer,
            "adapter": _Adapter(),
            "strategy": _strategy(),
            "evaluators": _evaluators(),
            "objective": _objective(),
        },
    )
    assert isinstance(cache_scope["optimizer"], Optimizer)
    cache_scope["cache"].close()
    cache_scope["optimizer"].close()

    direct_cache_scope = _run(26)
    assert direct_cache_scope["payload"] == b'{"answer":"world"}'

    dataset = _dataset()

    def build_optimizer(store: SQLiteStore) -> Optimizer:
        return _optimizer(store=store)

    resume_scope = _run(
        27,
        {"build_optimizer": build_optimizer, "Optimizer": Optimizer, "dataset": dataset},
    )
    assert resume_scope["resumed"].study_id == resume_scope["result"].study_id
    inspect_scope = _run(
        28,
        {"store": resume_scope["store"], "result": resume_scope["result"]},
    )
    assert inspect_scope["trials"]
    assert inspect_scope["events"]
    resume_scope["store"].close()

    callback_scope = _run(
        29,
        {
            "Optimizer": Optimizer,
            "adapter": _Adapter(),
            "strategy": _strategy(),
            "evaluators": _evaluators(),
            "objective": _objective(),
        },
    )
    callback_result = callback_scope["optimizer"].optimize(dataset, study_name="callback")
    assert callback_result.best_candidate is not None
    callback_scope["optimizer"].close()

    store = SQLiteStore(tmp_path / "mlflow.db")
    mlflow_scope = _run(
        30,
        {
            "Optimizer": Optimizer,
            "adapter": _Adapter(),
            "strategy": _strategy(),
            "evaluators": _evaluators(),
            "objective": _objective(),
            "store": store,
        },
    )
    assert type(mlflow_scope["callback"]).__name__ == "MLflowCallback"
    store.close()


def test_examples_31_to_36_results_errors_secrets_and_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    class CompleteEvaluator:
        async def evaluate(self, output: Any, example: Any) -> tuple[MetricValue, ...]:
            del output, example
            return (
                MetricValue("answer_quality", 0.9),
                MetricValue("latency_seconds", 0.1),
            )

    optimizer = Optimizer(
        adapter=_Adapter(),
        strategy=_strategy(),
        evaluators=(CompleteEvaluator(),),
        objective=Objective((ObjectiveTerm("answer_quality"),)),
        settings=Settings.resolve(overrides={"max_trials": 1}, environ={}),
    )
    result = optimizer.optimize(_dataset(), study_name="result")
    optimizer.close()
    result_scope = _run(31, {"result": result})
    assert result_scope["result"].metric_names == ("answer_quality", "latency_seconds")
    leaders_scope = _run(32, {"result": result})
    assert leaders_scope["quality_leaders"][0].id == result.best_trial.id
    report_scope = _run(33, {"result": result})
    assert Path("artifacts/result.json").exists()
    assert Path("artifacts/trials.csv").exists()
    assert report_scope["trial"].metric("answer_quality").value == 0.9

    class FailingOptimizer:
        def optimize(self, dataset: Any, *, study_name: str) -> Any:
            del dataset, study_name
            raise TunaRAGError("expected", stage="example")

    error_scope = _run(34, {"optimizer": FailingOptimizer(), "dataset": _dataset()})
    assert error_scope["diagnostic"]["stage"] == "example"
    secret_scope = _run(35)
    assert str(secret_scope["credential"]) == "***redacted***"
    extension_scope = _run(36)
    parameter = extension_scope["EvenInteger"](2, 8)
    sampled = parameter.sample(random.Random(3))
    assert parameter.accepts(sampled)
    assert not parameter.accepts(3)
    assert parameter.describe()["multiple_of"] == 2
    assert capsys.readouterr().out
