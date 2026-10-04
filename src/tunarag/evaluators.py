"""Built-in evaluator helpers and optional third-party integrations."""

from __future__ import annotations

import inspect
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from importlib import import_module
from numbers import Real
from typing import Any

from .contracts import Fingerprintable
from .domain import MetricValue, ValueStatus
from .errors import EvaluationError, MissingOptionalDependencyError

MetricScorer = Callable[[Any, Any], float | None | Awaitable[float | None]]
RagasSampleMapper = Callable[[Any, Any], Mapping[str, Any]]


class MetricEvaluator:
    """Adapt one synchronous or asynchronous numeric scorer to an evaluator."""

    def __init__(
        self,
        name: str,
        scorer: MetricScorer,
        *,
        status: ValueStatus = ValueStatus.EXACT,
    ) -> None:
        if not name.strip():
            raise ValueError("metric name must not be empty")
        if name == "tunarag.objective":
            raise ValueError("metric name is reserved: tunarag.objective")
        if not callable(scorer):
            raise TypeError("metric scorer must be callable")
        self._name = name
        self._scorer = scorer
        self._status = status

    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]:
        """Score one adapter output and evaluation example."""

        result = self._scorer(output, example)
        value = await result if inspect.isawaitable(result) else result
        normalized = _numeric_score(value, metric=self._name)
        if normalized is None:
            return (MetricValue(self._name, None, ValueStatus.UNAVAILABLE, 0.0),)
        return (MetricValue(self._name, normalized, self._status),)

    def fingerprint(self) -> Any:
        """Return stable configuration used by study and cache identity."""

        return {
            "name": self._name,
            "status": self._status.value,
            "scorer": _callable_identity(self._scorer),
        }


class RagasEvaluator:
    """Evaluate one sample with optional RAGAS metrics without hard coupling."""

    def __init__(
        self,
        metrics: Sequence[Any],
        sample_mapper: RagasSampleMapper,
        *,
        metric_prefix: str = "ragas.",
        llm: Any = None,
        embeddings: Any = None,
        raise_exceptions: bool = False,
    ) -> None:
        if not metrics:
            raise ValueError("RAGAS evaluator requires at least one metric")
        if not callable(sample_mapper):
            raise TypeError("RAGAS sample mapper must be callable")
        if metric_prefix == "tunarag.objective" or metric_prefix.startswith("tunarag.objective."):
            raise ValueError("RAGAS metric prefix uses a reserved name")
        self._metrics = tuple(metrics)
        self._sample_mapper = sample_mapper
        self._metric_prefix = metric_prefix
        self._llm = llm
        self._embeddings = embeddings
        self._raise_exceptions = raise_exceptions

    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]:
        """Map and evaluate exactly one sample through RAGAS's async API."""

        try:
            sample_data = self._sample_mapper(output, example)
        except Exception as error:
            raise EvaluationError(
                "RAGAS sample mapping failed",
                stage="evaluation",
                details={"cause": type(error).__name__},
            ) from error
        if not isinstance(sample_data, Mapping):
            raise EvaluationError("RAGAS sample mapper must return a mapping", stage="evaluation")
        ragas, dataset_schema = _load_ragas()
        try:
            sample = dataset_schema.SingleTurnSample(**dict(sample_data))
            dataset = ragas.EvaluationDataset(samples=[sample])
            result = await ragas.aevaluate(
                dataset=dataset,
                metrics=list(self._metrics),
                llm=self._llm,
                embeddings=self._embeddings,
                raise_exceptions=self._raise_exceptions,
                show_progress=False,
            )
            scores = result.scores
        except Exception as error:
            raise EvaluationError(
                "RAGAS evaluation failed",
                stage="evaluation",
                details={"cause": type(error).__name__},
            ) from error
        if not isinstance(scores, Sequence) or len(scores) != 1:
            raise EvaluationError("RAGAS returned an invalid per-sample result", stage="evaluation")
        row = scores[0]
        if not isinstance(row, Mapping) or not row:
            raise EvaluationError("RAGAS returned no metric scores", stage="evaluation")
        observations: list[MetricValue] = []
        names: set[str] = set()
        for raw_name, raw_value in row.items():
            name = f"{self._metric_prefix}{raw_name}"
            if not name.strip() or name == "tunarag.objective":
                raise EvaluationError("RAGAS returned an invalid metric name", stage="evaluation")
            if name in names:
                raise EvaluationError("RAGAS returned duplicate metric names", stage="evaluation")
            names.add(name)
            value = _numeric_score(raw_value, metric=name)
            if value is None:
                observations.append(MetricValue(name, None, ValueStatus.UNAVAILABLE, 0.0))
            else:
                observations.append(MetricValue(name, value))
        return tuple(observations)

    def fingerprint(self) -> Any:
        """Return secret-safe semantic integration configuration."""

        return {
            "metrics": [_component_identity(metric) for metric in self._metrics],
            "sample_mapper": _callable_identity(self._sample_mapper),
            "metric_prefix": self._metric_prefix,
            "llm": _component_identity(self._llm),
            "embeddings": _component_identity(self._embeddings),
            "raise_exceptions": self._raise_exceptions,
        }


def _load_ragas() -> tuple[Any, Any]:
    try:
        return import_module("ragas"), import_module("ragas.dataset_schema")
    except ImportError as error:
        raise MissingOptionalDependencyError("RAGAS evaluation", "ragas") from error


def _numeric_score(value: Any, *, metric: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise EvaluationError(
            "evaluator score must be numeric or None",
            stage="evaluation",
            details={"metric": metric, "value_type": type(value).__name__},
        )
    normalized = float(value)
    return normalized if math.isfinite(normalized) else None


def _callable_identity(function: Callable[..., Any]) -> str:
    module = getattr(function, "__module__", type(function).__module__)
    name = getattr(function, "__qualname__", type(function).__qualname__)
    return f"{module}.{name}"


def _component_identity(component: Any) -> Any:
    if component is None:
        return None
    identity: dict[str, Any] = {
        "type": f"{type(component).__module__}.{type(component).__qualname__}"
    }
    if isinstance(component, Fingerprintable):
        identity["fingerprint"] = component.fingerprint()
    return identity
