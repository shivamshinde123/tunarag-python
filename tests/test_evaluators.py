import asyncio
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from tunarag import (
    EvaluationError,
    MetricEvaluator,
    MissingOptionalDependencyError,
    RagasEvaluator,
    ValueStatus,
)


def test_metric_evaluator_supports_sync_and_async_scorers() -> None:
    sync_evaluator = MetricEvaluator("length", lambda output, _example: len(output))

    async def score(output: Any, example: Any) -> float:
        return float(output == example)

    async_evaluator = MetricEvaluator("match", score, status=ValueStatus.ESTIMATED)

    sync_result = asyncio.run(sync_evaluator.evaluate("tuna", None))
    async_result = asyncio.run(async_evaluator.evaluate("yes", "yes"))

    assert sync_result[0].value == 4.0
    assert async_result[0].value == 1.0
    assert async_result[0].status is ValueStatus.ESTIMATED
    assert sync_evaluator.fingerprint()["name"] == "length"


def test_metric_evaluator_marks_missing_or_nonfinite_scores_unavailable() -> None:
    missing = MetricEvaluator("missing", lambda _output, _example: None)
    nonfinite = MetricEvaluator("nonfinite", lambda _output, _example: float("nan"))

    for evaluator in (missing, nonfinite):
        metric = asyncio.run(evaluator.evaluate(None, None))[0]
        assert metric.value is None
        assert metric.status is ValueStatus.UNAVAILABLE
        assert metric.coverage == 0.0


def test_metric_evaluator_rejects_invalid_scores() -> None:
    evaluator = MetricEvaluator("quality", lambda _output, _example: True)  # type: ignore[arg-type]

    with pytest.raises(EvaluationError, match="numeric"):
        asyncio.run(evaluator.evaluate(None, None))


def test_ragas_evaluator_maps_one_sample_and_normalizes_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    ragas = ModuleType("ragas")
    schema = ModuleType("ragas.dataset_schema")

    class SingleTurnSample:
        def __init__(self, **values: Any) -> None:
            self.values = values

    class EvaluationDataset:
        def __init__(self, *, samples: list[Any]) -> None:
            self.samples = samples

    async def aevaluate(**options: Any) -> Any:
        captured.update(options)
        return SimpleNamespace(scores=[{"faithfulness": 0.75, "context_recall": float("nan")}])

    schema.SingleTurnSample = SingleTurnSample  # type: ignore[attr-defined]
    ragas.EvaluationDataset = EvaluationDataset  # type: ignore[attr-defined]
    ragas.aevaluate = aevaluate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ragas", ragas)
    monkeypatch.setitem(sys.modules, "ragas.dataset_schema", schema)

    evaluator = RagasEvaluator(
        [object()],
        lambda output, example: {
            "user_input": example["question"],
            "response": output["answer"],
            "retrieved_contexts": output["contexts"],
            "reference": example["answer"],
        },
    )
    metrics = asyncio.run(
        evaluator.evaluate(
            {"answer": "Tuna", "contexts": ["Fish"]},
            {"question": "What?", "answer": "Tuna"},
        )
    )

    assert captured["show_progress"] is False
    assert captured["dataset"].samples[0].values["response"] == "Tuna"
    assert metrics[0].name == "ragas.faithfulness"
    assert metrics[0].value == 0.75
    assert metrics[1].status is ValueStatus.UNAVAILABLE
    assert metrics[1].coverage == 0.0


def test_ragas_evaluator_wraps_provider_errors_without_message_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ragas = ModuleType("ragas")
    schema = ModuleType("ragas.dataset_schema")
    schema.SingleTurnSample = lambda **values: values  # type: ignore[attr-defined]
    ragas.EvaluationDataset = lambda *, samples: samples  # type: ignore[attr-defined]

    async def aevaluate(**_options: Any) -> Any:
        raise RuntimeError("secret provider response")

    ragas.aevaluate = aevaluate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ragas", ragas)
    monkeypatch.setitem(sys.modules, "ragas.dataset_schema", schema)
    evaluator = RagasEvaluator([object()], lambda _output, _example: {"response": "ok"})

    with pytest.raises(EvaluationError) as raised:
        asyncio.run(evaluator.evaluate(None, None))

    assert "secret provider response" not in str(raised.value)
    assert raised.value.details == {"cause": "RuntimeError"}


def test_ragas_evaluator_requires_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "ragas", raising=False)
    monkeypatch.delitem(sys.modules, "ragas.dataset_schema", raising=False)
    evaluator = RagasEvaluator([object()], lambda _output, _example: {"response": "ok"})

    with pytest.raises(MissingOptionalDependencyError):
        asyncio.run(evaluator.evaluate(None, None))


def test_ragas_evaluator_redacts_mapper_failure_message() -> None:
    def map_sample(_output: Any, _example: Any) -> dict[str, Any]:
        raise ValueError("private example contents")

    evaluator = RagasEvaluator([object()], map_sample)

    with pytest.raises(EvaluationError) as raised:
        asyncio.run(evaluator.evaluate(None, None))

    assert "private example contents" not in str(raised.value)
    assert raised.value.details == {"cause": "ValueError"}


@pytest.mark.parametrize("score", [True, "high", object()])
def test_ragas_evaluator_rejects_non_numeric_scores(
    score: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ragas = ModuleType("ragas")
    schema = ModuleType("ragas.dataset_schema")
    schema.SingleTurnSample = lambda **values: values  # type: ignore[attr-defined]
    ragas.EvaluationDataset = lambda *, samples: samples  # type: ignore[attr-defined]

    async def aevaluate(**_options: Any) -> Any:
        return SimpleNamespace(scores=[{"quality": score}])

    ragas.aevaluate = aevaluate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ragas", ragas)
    monkeypatch.setitem(sys.modules, "ragas.dataset_schema", schema)
    evaluator = RagasEvaluator([object()], lambda _output, _example: {"response": "ok"})

    with pytest.raises(EvaluationError, match="numeric"):
        asyncio.run(evaluator.evaluate(None, None))
