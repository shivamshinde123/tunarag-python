"""Google ADK 2.x runner integration with isolated evaluation sessions."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from typing import Any
from uuid import uuid4

from ..domain import Candidate, UsageRecord
from ..errors import AdapterError, MissingOptionalDependencyError
from ..serialization import callable_identity, callable_name
from .runnables import (
    TokenPrices,
    _token_count,
    _type_name,
    priced_usage,
    validate_token_prices,
    warn_missing_identity,
)

_ERROR_MESSAGE_LIMIT = 300
_LOGGER = logging.getLogger("tunarag.google_adk")


class GoogleADKAdapter:
    """Evaluate a Google ADK runner in a fresh session for every sample and retry.

    Candidate parameters become initial session state. Use a factory when changing
    an agent's model, tools, or graph requires constructing a new framework runner.
    By default the output is ``{"answer": final_text, "tool_responses": [...]}`` so tool
    results (for example retrieved passages) are available to evaluators and RAGAS.
    """

    def __init__(
        self,
        runner: Any = None,
        *,
        factory: Callable[[Candidate], Any] | None = None,
        state_mapper: Callable[[Candidate], Mapping[str, Any]] | None = None,
        output_mapper: Callable[[Any], Any] | None = None,
        events_mapper: Callable[[Sequence[Any]], Any] | None = None,
        token_prices: TokenPrices | None = None,
        identity: Any = None,
    ) -> None:
        if (runner is None) == (factory is None):
            raise ValueError("provide exactly one of runner or factory")
        if output_mapper is not None and events_mapper is not None:
            raise ValueError("provide at most one of output_mapper or events_mapper")
        for name, callback in (
            ("factory", factory),
            ("state_mapper", state_mapper),
            ("output_mapper", output_mapper),
            ("events_mapper", events_mapper),
        ):
            if callback is not None and not callable(callback):
                raise TypeError(f"{name} must be callable")
        if runner is not None:
            _require_runner(runner)
        self._runner = runner
        self._factory = factory
        self._state_mapper = state_mapper
        self._output_mapper = output_mapper
        self._events_mapper = events_mapper
        self._token_prices = validate_token_prices(token_prices)
        self._identity = identity
        warn_missing_identity(self, identity)

    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, tuple[UsageRecord, ...]]:
        """Consume runner events, capture usage, and remove the temporary session."""
        runner = self._runner if self._factory is None else self._factory(candidate)
        _require_runner(runner)
        types = import_module("google.genai.types")
        query = getattr(example, "query", example)
        if not isinstance(query, str) or not query.strip():
            raise TypeError("Google ADK evaluation input must contain a nonempty query")
        state = (
            dict(candidate.parameters)
            if self._state_mapper is None
            else self._state_mapper(candidate)
        )
        if not isinstance(state, Mapping):
            raise TypeError("state_mapper must return a mapping")
        session_id = uuid4().hex
        user_id = "tunarag-evaluation"
        session = await runner.session_service.create_session(
            app_name=runner.app_name,
            user_id=user_id,
            session_id=session_id,
            state=dict(state),
        )
        usage: list[UsageRecord] = []
        events: list[Any] = []
        final_event = None
        started_at = time.perf_counter()
        stream = runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=query)]),
        )
        try:
            async for event in stream:
                events.append(event)
                if event.error_code:
                    # The code is persisted with the trial; the provider's free-text message
                    # may echo user data, so it only goes to the console log.
                    _LOGGER.warning(
                        "Google ADK error event %s: %s",
                        event.error_code,
                        (event.error_message or "")[:_ERROR_MESSAGE_LIMIT],
                    )
                    raise AdapterError(
                        f"Google ADK runner returned an error event ({event.error_code})",
                        stage="adapter",
                        details={"error_code": str(event.error_code)},
                    )
                metadata = event.usage_metadata
                if metadata is not None:
                    usage.append(
                        priced_usage(
                            "google_adk.model",
                            getattr(event, "model_version", None),
                            _token_count(metadata.prompt_token_count),
                            _token_count(metadata.candidates_token_count),
                            self._token_prices,
                        )
                    )
                if event.is_final_response():
                    final_event = event
            if final_event is None:
                raise AdapterError("Google ADK runner produced no final response", stage="adapter")
            if self._events_mapper is not None:
                output = self._events_mapper(tuple(events))
            elif self._output_mapper is not None:
                output = self._output_mapper(final_event)
            else:
                if final_event.content is None:
                    raise AdapterError(
                        "ADK final event has no text; provide output_mapper or events_mapper",
                        stage="adapter",
                    )
                output = {
                    "answer": "".join(
                        part.text or ""
                        for part in final_event.content.parts or ()
                        if not part.thought
                    ),
                    "tool_responses": _tool_responses(events),
                }
            usage.append(
                UsageRecord("google_adk.runner", latency_seconds=time.perf_counter() - started_at)
            )
            return output, tuple(usage)
        finally:
            try:
                await stream.aclose()
            finally:
                await runner.session_service.delete_session(
                    app_name=runner.app_name, user_id=user_id, session_id=session.id
                )

    def fingerprint(self) -> dict[str, Any]:
        """Describe integration semantics without sessions or provider credentials."""
        # An explicit identity replaces automatic code/agent fingerprinting.
        code = callable_identity if self._identity is None else callable_name
        runner: Any = None
        if self._runner is not None:
            runner = (
                _runner_identity(self._runner)
                if self._identity is None
                else _type_name(self._runner)
            )
        return {
            "integration": "google_adk",
            "schema_version": 2,
            "runner": runner,
            "factory": code(self._factory),
            "state_mapper": code(self._state_mapper),
            "output_mapper": code(self._output_mapper),
            "events_mapper": code(self._events_mapper),
            "identity": self._identity,
        }


def _tool_responses(events: Sequence[Any]) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for event in events:
        for response in event.get_function_responses() or ():
            responses.append({"name": response.name, "response": response.response})
    return responses


def _runner_identity(runner: Any) -> dict[str, Any]:
    identity: dict[str, Any] = {"type": _type_name(runner)}
    agent = getattr(runner, "agent", None)
    if agent is not None:
        identity["agent"] = _agent_identity(agent, depth=0)
    return identity


def _agent_identity(agent: Any, *, depth: int) -> dict[str, Any]:
    model = getattr(agent, "model", None)
    model_name = model if isinstance(model, str) else getattr(model, "model", None)
    instruction = getattr(agent, "instruction", None)
    identity: dict[str, Any] = {
        "type": _type_name(agent),
        "name": getattr(agent, "name", None),
        "model": model_name if isinstance(model_name, str) else _type_name(model),
        "instruction": (
            instruction if isinstance(instruction, str) else callable_identity(instruction)
        ),
        "tools": [
            callable_identity(tool) if callable(tool) else getattr(tool, "name", _type_name(tool))
            for tool in getattr(agent, "tools", None) or ()
        ],
    }
    if depth < 4:
        identity["sub_agents"] = [
            _agent_identity(sub_agent, depth=depth + 1)
            for sub_agent in getattr(agent, "sub_agents", None) or ()
        ]
    return identity


def _require_runner(value: Any) -> None:
    try:
        runner_type = import_module("google.adk.runners").Runner
    except ImportError as error:
        raise MissingOptionalDependencyError("Google ADK", "google-adk") from error
    if not isinstance(value, runner_type):
        raise TypeError("GoogleADKAdapter requires a real Google ADK Runner")
