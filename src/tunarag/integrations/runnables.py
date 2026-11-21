"""Adapters for LangChain runnables and compiled LangGraph graphs."""

from __future__ import annotations

import math
import time
import warnings
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from typing import Any

from ..dataset import EvaluationExample
from ..domain import Candidate, UsageRecord, ValueStatus
from ..errors import MissingOptionalDependencyError
from ..serialization import callable_identity, callable_name

RunnableFactory = Callable[[Candidate], Any]
RunnableInputMapper = Callable[[Any, Candidate], Any]
RunnableConfigMapper = Callable[[Candidate], Mapping[str, Any] | None]
RunnableOutputMapper = Callable[[Any], Any]
RunnableUsageMapper = Callable[[Any], Sequence[UsageRecord]]
TokenPrices = Mapping[str, tuple[float, float]]
"""Model name -> (USD per 1M input tokens, USD per 1M output tokens)."""


class _RunnableAdapter:
    def __init__(
        self,
        runnable: Any,
        *,
        factory: RunnableFactory | None,
        input_key: str,
        input_mapper: RunnableInputMapper | None,
        config_mapper: RunnableConfigMapper | None,
        output_mapper: RunnableOutputMapper | None,
        usage_mapper: RunnableUsageMapper | None,
        capture_message_usage: bool,
        token_prices: TokenPrices | None,
        identity: Any,
        framework: str,
    ) -> None:
        if (runnable is None) == (factory is None):
            raise ValueError("provide exactly one of runnable or factory")
        if runnable is not None:
            _require_runnable(runnable, framework)
        if factory is not None and not callable(factory):
            raise TypeError("runnable factory must be callable")
        if not input_key.strip():
            raise ValueError("runnable input key must not be empty")
        for name, mapper in (
            ("input_mapper", input_mapper),
            ("config_mapper", config_mapper),
            ("output_mapper", output_mapper),
            ("usage_mapper", usage_mapper),
        ):
            if mapper is not None and not callable(mapper):
                raise TypeError(f"{name} must be callable")
        if not isinstance(capture_message_usage, bool):
            raise TypeError("capture_message_usage must be a boolean")
        self._runnable = runnable
        self._factory = factory
        self._input_key = input_key
        self._input_mapper = input_mapper
        self._config_mapper = config_mapper
        self._output_mapper = output_mapper
        self._usage_mapper = usage_mapper
        self._capture_message_usage = capture_message_usage
        self._token_prices = validate_token_prices(token_prices)
        self._identity = identity
        self._framework = framework
        warn_missing_identity(self, identity)

    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, tuple[UsageRecord, ...]]:
        """Invoke one framework runnable for a TunaRAG candidate and example."""

        runnable = self._resolve_runnable(candidate)
        runnable_input = self._map_input(example, candidate)
        config = self._map_config(candidate)
        handler = None
        if self._usage_mapper is None and self._capture_message_usage:
            handler = _usage_handler()
            if handler is not None:
                config = _with_callback(config, handler)
        started_at = time.perf_counter()
        raw_output = await runnable.ainvoke(runnable_input, config=config)
        latency = time.perf_counter() - started_at
        output = raw_output if self._output_mapper is None else self._output_mapper(raw_output)
        usage = list(self._map_usage(raw_output, handler))
        usage.append(
            UsageRecord(
                component=f"{self._framework}.runnable",
                latency_seconds=latency,
            )
        )
        return output, tuple(usage)

    def fingerprint(self) -> dict[str, Any]:
        """Return stable, provider-secret-free adapter semantics."""

        # An explicit identity is the user's declaration of the pipeline version and replaces
        # automatic code fingerprinting (which would also see run-varying closure state).
        code = callable_identity if self._identity is None else callable_name
        runnable: Any = None
        if self._runnable is not None:
            runnable = (
                runnable_identity(self._runnable)
                if self._identity is None
                else _type_name(self._runnable)
            )
        return {
            "integration": self._framework,
            "schema_version": 2,
            "runnable": runnable,
            "factory": code(self._factory),
            "input_key": self._input_key,
            "input_mapper": code(self._input_mapper),
            "config_mapper": code(self._config_mapper),
            "output_mapper": code(self._output_mapper),
            "usage_mapper": code(self._usage_mapper),
            "capture_message_usage": self._capture_message_usage,
            "identity": self._identity,
        }

    def _resolve_runnable(self, candidate: Candidate) -> Any:
        if self._runnable is not None:
            return self._runnable
        if self._factory is None:
            raise RuntimeError("runnable adapter is not configured")
        runnable = self._factory(candidate)
        _require_runnable(runnable, self._framework)
        return runnable

    def _map_input(self, example: Any, candidate: Candidate) -> Any:
        if self._input_mapper is not None:
            return self._input_mapper(example, candidate)
        if isinstance(example, EvaluationExample):
            return {self._input_key: example.query}
        return example

    def _map_config(self, candidate: Candidate) -> Mapping[str, Any] | None:
        if self._config_mapper is None:
            return {"configurable": dict(candidate.parameters)}
        config = self._config_mapper(candidate)
        if config is not None and not isinstance(config, Mapping):
            raise TypeError("config_mapper must return a mapping or None")
        return config

    def _map_usage(self, raw_output: Any, handler: Any) -> tuple[UsageRecord, ...]:
        if self._usage_mapper is not None:
            usage = tuple(self._usage_mapper(raw_output))
            if any(not isinstance(item, UsageRecord) for item in usage):
                raise TypeError("usage_mapper must return only UsageRecord values")
            return usage
        if not self._capture_message_usage:
            return ()
        counts: list[tuple[str | None, int | None, int | None]] = []
        if handler is not None:
            # Every chat-model call inside the runnable, even when the output is a string.
            for model, metadata in sorted(dict(handler.usage_metadata).items()):
                counts.append(
                    (
                        str(model) if model else None,
                        _token_count(metadata.get("input_tokens")),
                        _token_count(metadata.get("output_tokens")),
                    )
                )
        if not counts:
            counts = _message_usage(raw_output)
        return tuple(
            priced_usage(
                f"{self._framework}.model", model, input_tokens, output_tokens, self._token_prices
            )
            for model, input_tokens, output_tokens in counts
        )


class LangChainAdapter(_RunnableAdapter):
    """Expose a LangChain runnable through TunaRAG's standard adapter contract."""

    def __init__(
        self,
        runnable: Any = None,
        *,
        factory: RunnableFactory | None = None,
        input_key: str = "question",
        input_mapper: RunnableInputMapper | None = None,
        config_mapper: RunnableConfigMapper | None = None,
        output_mapper: RunnableOutputMapper | None = None,
        usage_mapper: RunnableUsageMapper | None = None,
        capture_message_usage: bool = True,
        token_prices: TokenPrices | None = None,
        identity: Any = None,
    ) -> None:
        super().__init__(
            runnable,
            factory=factory,
            input_key=input_key,
            input_mapper=input_mapper,
            config_mapper=config_mapper,
            output_mapper=output_mapper,
            usage_mapper=usage_mapper,
            capture_message_usage=capture_message_usage,
            token_prices=token_prices,
            identity=identity,
            framework="langchain",
        )


class LangGraphAdapter(_RunnableAdapter):
    """Expose a compiled LangGraph graph through TunaRAG's adapter contract."""

    def __init__(
        self,
        graph: Any = None,
        *,
        factory: RunnableFactory | None = None,
        input_key: str = "question",
        input_mapper: RunnableInputMapper | None = None,
        config_mapper: RunnableConfigMapper | None = None,
        output_mapper: RunnableOutputMapper | None = None,
        usage_mapper: RunnableUsageMapper | None = None,
        capture_message_usage: bool = True,
        token_prices: TokenPrices | None = None,
        identity: Any = None,
    ) -> None:
        super().__init__(
            graph,
            factory=factory,
            input_key=input_key,
            input_mapper=input_mapper,
            config_mapper=config_mapper,
            output_mapper=output_mapper,
            usage_mapper=usage_mapper,
            capture_message_usage=capture_message_usage,
            token_prices=token_prices,
            identity=identity,
            framework="langgraph",
        )


def validate_token_prices(prices: TokenPrices | None) -> dict[str, tuple[float, float]] | None:
    """Check a model -> (input, output) USD-per-million-token price table."""

    if prices is None:
        return None
    if not isinstance(prices, Mapping):
        raise TypeError("token_prices must map model names to (input, output) prices")
    checked: dict[str, tuple[float, float]] = {}
    for model, pair in prices.items():
        if not isinstance(model, str) or not model.strip():
            raise ValueError("token_prices keys must be model names")
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("token_prices values must be (input_per_million, output_per_million)")
        values = tuple(float(value) for value in pair)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("token prices must be finite and not negative")
        checked[model] = (values[0], values[1])
    return checked


def priced_usage(
    component: str,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    prices: Mapping[str, tuple[float, float]] | None,
) -> UsageRecord:
    """Build a model-call usage record, estimating cost when the model has a price."""

    name = component if model is None else f"{component}:{model}"
    price = None if prices is None or model is None else prices.get(model)
    if price is None:
        return UsageRecord(name, input_tokens=input_tokens, output_tokens=output_tokens)
    cost = ((input_tokens or 0) * price[0] + (output_tokens or 0) * price[1]) / 1_000_000
    return UsageRecord(
        name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        status=ValueStatus.ESTIMATED,
        pricing_version="token_prices",
    )


def warn_missing_identity(adapter: object, identity: Any) -> None:
    if identity is None:
        warnings.warn(
            f"{type(adapter).__name__} has no identity=...; cached results and resumed "
            "studies can only distinguish pipelines by code structure. Pass identity with "
            "your corpus, index, model, and prompt revisions.",
            UserWarning,
            stacklevel=4,
        )


def runnable_identity(runnable: Any, *, _depth: int = 0) -> Any:
    """Best-effort structural identity: type, wrapped functions, graph nodes, chain steps."""

    identity: dict[str, Any] = {"type": _type_name(runnable)}
    if _depth > 6:
        return identity
    function = getattr(runnable, "func", None) or getattr(runnable, "afunc", None)
    if callable(function):
        identity["function"] = callable_identity(function)
    nodes = getattr(getattr(runnable, "builder", None), "nodes", None)
    if isinstance(nodes, Mapping):
        identity["nodes"] = {
            str(name): runnable_identity(getattr(spec, "runnable", spec), _depth=_depth + 1)
            for name, spec in sorted(nodes.items(), key=lambda item: str(item[0]))
        }
    steps = getattr(runnable, "steps", None)
    if isinstance(steps, list):
        identity["steps"] = [runnable_identity(step, _depth=_depth + 1) for step in steps]
    return identity


def _usage_handler() -> Any:
    try:
        return import_module("langchain_core.callbacks").UsageMetadataCallbackHandler()
    except (ImportError, AttributeError):
        return None


def _with_callback(config: Mapping[str, Any] | None, handler: Any) -> dict[str, Any]:
    merged = {} if config is None else dict(config)
    callbacks = merged.get("callbacks")
    if callbacks is None:
        merged["callbacks"] = [handler]
    elif isinstance(callbacks, (list, tuple)):
        merged["callbacks"] = [*callbacks, handler]
    elif hasattr(callbacks, "copy") and hasattr(callbacks, "add_handler"):
        manager = callbacks.copy()
        manager.add_handler(handler, inherit=True)
        merged["callbacks"] = manager
    return merged


def _message_usage(output: Any) -> list[tuple[str | None, int | None, int | None]]:
    records: list[tuple[str | None, int | None, int | None]] = []
    visited: set[int] = set()

    def collect(value: Any) -> None:
        if value is None or isinstance(value, (str, bytes, bytearray, bool, int, float)):
            return
        value_id = id(value)
        if value_id in visited:
            return
        visited.add(value_id)
        metadata = (
            value.get("usage_metadata")
            if isinstance(value, Mapping)
            else getattr(value, "usage_metadata", None)
        )
        if isinstance(metadata, Mapping):
            input_tokens = _token_count(metadata.get("input_tokens"))
            output_tokens = _token_count(metadata.get("output_tokens"))
            if input_tokens is not None or output_tokens is not None:
                response = getattr(value, "response_metadata", None)
                model = response.get("model_name") if isinstance(response, Mapping) else None
                model_name = model if isinstance(model, str) else None
                records.append((model_name, input_tokens, output_tokens))
        if isinstance(value, Mapping):
            for item in value.values():
                collect(item)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                collect(item)

    collect(output)
    return records


def _token_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _require_runnable(value: Any, framework: str) -> None:
    module, name = (
        ("langchain_core.runnables", "Runnable")
        if framework == "langchain"
        else ("langgraph.graph.state", "CompiledStateGraph")
    )
    try:
        framework_type = getattr(import_module(module), name)
    except ImportError as error:
        raise MissingOptionalDependencyError(framework, framework) from error
    if not isinstance(value, framework_type):
        raise TypeError(
            f"{framework} integration requires a real {name}, not a custom ainvoke object"
        )


def _type_name(value: Any) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"
