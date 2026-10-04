from dataclasses import dataclass

from tunarag import (
    AdapterError,
    ErrorCode,
    MissingOptionalDependencyError,
    Secret,
    SyncInAsyncContextError,
)
from tunarag.errors import redact


@dataclass
class Diagnostic:
    model: str
    token: Secret


def test_structured_error_redacts_details_and_preserves_metadata() -> None:
    error = AdapterError(
        "adapter request failed",
        stage="adapter.run",
        retryable=True,
        details={
            "authorization": "Bearer raw-secret",
            "nested": Diagnostic("small", Secret("wrapped-secret")),
            "attempt": 2,
        },
    )

    diagnostic = error.as_dict()

    assert diagnostic["code"] == ErrorCode.ADAPTER.value
    assert diagnostic["retryable"] is True
    assert diagnostic["details"]["authorization"] == "***redacted***"
    assert diagnostic["details"]["nested"]["token"] == "***redacted***"
    assert "raw-secret" not in repr(diagnostic)
    assert "wrapped-secret" not in repr(diagnostic)


def test_specialized_errors_provide_actionable_messages() -> None:
    dependency = MissingOptionalDependencyError("RAGAS evaluation", "ragas")
    sync = SyncInAsyncContextError()

    assert dependency.code is ErrorCode.OPTIONAL_DEPENDENCY
    assert dependency.details == {"feature": "RAGAS evaluation", "extra": "ragas"}
    assert "use the async API" in str(sync)


def test_redaction_does_not_call_unknown_object_repr() -> None:
    class UnsafeRepresentation:
        def __repr__(self) -> str:
            raise AssertionError("repr must not be called")

    assert redact(UnsafeRepresentation()) == "<UnsafeRepresentation>"
    assert redact({"input_tokens": 12, "access_token": "secret"}) == {
        "input_tokens": 12,
        "access_token": "***redacted***",
    }
