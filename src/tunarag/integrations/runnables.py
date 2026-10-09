"""Adapters for LangChain runnables and compiled LangGraph graphs."""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from typing import Any

from ..dataset import EvaluationExample
from ..domain import Candidate, UsageRecord
from ..errors import MissingOptionalDependencyError

RunnableFactory = Callable[[Candidate], Any]
RunnableInputMapper = Callable[[Any, Candidate], Any]
RunnableConfigMapper = Callable[[Candidate], Mapping[str, Any] | None]
RunnableOutputMapper = Callable[[Any], Any]
RunnableUsageMapper = Callable[[Any], Sequence[UsageRecord]]


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
        self._identity = identity
        self._framework = framework

    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, tuple[UsageRecord, ...]]:
        """Invoke one framework runnable for a TunaRAG candidate and example."""

        runnable = self._resolve_runnable(candidate)
        runnable_input = self._map_input(example, candidate)
        config = self._map_config(candidate)
        started_at = time.perf_counter()
        raw_output = await runnable.ainvoke(runnable_input, config=config)
        latency = time.perf_counter() - started_at
        output = raw_output if self._output_mapper is None else self._output_mapper(raw_output)
        usage = list(self._map_usage(raw_output))
        usage.append(
            UsageRecord(
                component=f"{self._framework}.runnable",
                latency_seconds=latency,
            )
        )
        return output, tuple(usage)

    def fingerprint(self) -> dict[str, Any]:
        """Return stable, provider-secret-free adapter semantics."""

        runnable_identity = _type_name(self._runnable) if self._runnable is not None else None
        return {
            "integration": self._framework,
            "schema_version": 1,
            "runnable": runnable_identity,
            "factory": _callable_identity(self._factory),
            "input_key": self._input_key,
            "input_mapper": _callable_identity(self._input_mapper),
            "config_mapper": _callable_identity(self._config_mapper),
            "output_mapper": _callable_identity(self._output_mapper),
            "usage_mapper": _callable_identity(self._usage_mapper),
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

    def _map_usage(self, raw_output: Any) -> tuple[UsageRecord, ...]:
        if self._usage_mapper is not None:
            usage = tuple(self._usage_mapper(raw_output))
            if any(not isinstance(item, UsageRecord) for item in usage):
                raise TypeError("usage_mapper must return only UsageRecord values")
            return usage
        if not self._capture_message_usage:
            return ()
        return _message_usage(raw_output, framework=self._framework)


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
            identity=identity,
            framework="langgraph",
        )


def _message_usage(output: Any, *, framework: str) -> tuple[UsageRecord, ...]:
    records: list[UsageRecord] = []
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
                records.append(
                    UsageRecord(
                        component=f"{framework}.message",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                )
        if isinstance(value, Mapping):
            for item in value.values():
                collect(item)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                collect(item)

    collect(output)
    return tuple(records)


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


def _callable_identity(value: Callable[..., Any] | None) -> str | None:
    if value is None:
        return None
    if inspect.ismethod(value) or inspect.isfunction(value):
        return f"{value.__module__}.{value.__qualname__}"
    return _type_name(value)


def _type_name(value: Any) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"
