"""Google ADK 2.x runner integration with isolated evaluation sessions."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any
from uuid import uuid4

from ..domain import Candidate, UsageRecord
from ..errors import AdapterError, MissingOptionalDependencyError
from .runnables import _callable_identity, _token_count, _type_name


class GoogleADKAdapter:
    """Evaluate a Google ADK runner in a fresh session for every sample and retry.

    Candidate parameters become initial session state. Use a factory when changing
    an agent's model, tools, or graph requires constructing a new framework runner.
    """

    def __init__(
        self,
        runner: Any = None,
        *,
        factory: Callable[[Candidate], Any] | None = None,
        state_mapper: Callable[[Candidate], Mapping[str, Any]] | None = None,
        output_mapper: Callable[[Any], Any] | None = None,
        identity: Any = None,
    ) -> None:
        if (runner is None) == (factory is None):
            raise ValueError("provide exactly one of runner or factory")
        for name, callback in (
            ("factory", factory),
            ("state_mapper", state_mapper),
            ("output_mapper", output_mapper),
        ):
            if callback is not None and not callable(callback):
                raise TypeError(f"{name} must be callable")
        if runner is not None:
            _require_runner(runner)
        self._runner = runner
        self._factory = factory
        self._state_mapper = state_mapper
        self._output_mapper = output_mapper
        self._identity = identity

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
        final_event = None
        started_at = time.perf_counter()
        events = runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=query)]),
        )
        try:
            async for event in events:
                if event.error_code:
                    raise AdapterError("Google ADK runner returned an error event", stage="adapter")
                metadata = event.usage_metadata
                if metadata is not None:
                    usage.append(
                        UsageRecord(
                            "google_adk.model",
                            input_tokens=_token_count(metadata.prompt_token_count),
                            output_tokens=_token_count(metadata.candidates_token_count),
                        )
                    )
                if event.is_final_response():
                    final_event = event
            if final_event is None:
                raise AdapterError("Google ADK runner produced no final response", stage="adapter")
            if self._output_mapper is None and final_event.content is None:
                raise AdapterError(
                    "ADK final event has no text; provide output_mapper for structured output",
                    stage="adapter",
                )
            output = (
                self._output_mapper(final_event)
                if self._output_mapper is not None
                else {
                    "answer": "".join(
                        part.text or ""
                        for part in final_event.content.parts or ()
                        if not part.thought
                    )
                }
            )
            usage.append(
                UsageRecord("google_adk.runner", latency_seconds=time.perf_counter() - started_at)
            )
            return output, tuple(usage)
        finally:
            try:
                await events.aclose()
            finally:
                await runner.session_service.delete_session(
                    app_name=runner.app_name, user_id=user_id, session_id=session.id
                )

    def fingerprint(self) -> dict[str, Any]:
        """Describe integration semantics without sessions or provider credentials."""
        return {
            "integration": "google_adk",
            "schema_version": 1,
            "runner": _type_name(self._runner) if self._runner is not None else None,
            "factory": _callable_identity(self._factory),
            "state_mapper": _callable_identity(self._state_mapper),
            "output_mapper": _callable_identity(self._output_mapper),
            "identity": self._identity,
        }


def _require_runner(value: Any) -> None:
    try:
        runner_type = import_module("google.adk.runners").Runner
    except ImportError as error:
        raise MissingOptionalDependencyError("Google ADK", "google-adk") from error
    if not isinstance(value, runner_type):
        raise TypeError("GoogleADKAdapter requires a real Google ADK Runner")
