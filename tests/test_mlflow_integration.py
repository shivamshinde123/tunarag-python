import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from tunarag import (
    Candidate,
    MetricValue,
    MissingOptionalDependencyError,
    SQLiteStore,
    StudyStatus,
    TrialStatus,
)
from tunarag.integrations import MLflowCallback


class FakeClient:
    def __init__(self) -> None:
        self.runs: list[tuple[str, dict[str, str]]] = []
        self.metrics: list[tuple[str, str, float, int | None]] = []
        self.params: list[tuple[str, str, Any]] = []
        self.tags: list[tuple[str, str, Any]] = []
        self.terminated: list[tuple[str, str | None]] = []

    def create_run(self, experiment_id: str, *, tags: dict[str, str]) -> Any:
        self.runs.append((experiment_id, tags))
        return SimpleNamespace(info=SimpleNamespace(run_id="run-1"))

    def log_metric(self, run_id: str, key: str, value: float, *, step: int | None = None) -> None:
        self.metrics.append((run_id, key, value, step))

    def log_param(self, run_id: str, key: str, value: Any) -> None:
        self.params.append((run_id, key, value))

    def set_tag(self, run_id: str, key: str, value: Any) -> None:
        self.tags.append((run_id, key, value))

    def set_terminated(self, run_id: str, *, status: str | None = None) -> None:
        self.terminated.append((run_id, status))


def test_mlflow_callback_mirrors_committed_trial_and_completion(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "mlflow.sqlite")
    study = store.create_study("mirror", {"version": 1})
    store.transition_study(study.id, StudyStatus.RUNNING)
    trial = store.reserve_trial(
        study.id, Candidate({"model": "small", "api_key": "candidate-secret"})
    )
    attempt = store.start_attempt(trial.id, lease_seconds=10)
    store.commit_trial_result(
        trial.id,
        status=TrialStatus.SUCCEEDED,
        attempt_id=attempt.id,
        metrics=[MetricValue("quality", 0.9)],
    )
    store.transition_study(study.id, StudyStatus.COMPLETED)
    events = store.list_events(study.id)
    client = FakeClient()
    callback = MLflowCallback(
        store,
        experiment_id="experiment-1",
        tags={"team": "rag", "api_key": "secret"},
        client=client,
    )

    async def mirror() -> None:
        for event in events:
            await callback.on_event(event)

    asyncio.run(mirror())

    assert len(client.runs) == 1
    assert client.runs[0][0] == "experiment-1"
    assert client.runs[0][1]["api_key"] == "***redacted***"
    assert ("run-1", "trial.0.candidate.model", "small") in client.params
    assert ("run-1", "trial.0.candidate.api_key", "***redacted***") in client.params
    assert ("run-1", "quality", 0.9, 0) in client.metrics
    assert "candidate-secret" not in repr(client.params)
    assert client.terminated == [("run-1", "FINISHED")]
    store.close()


def test_mlflow_callback_requires_optional_extra(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "missing.sqlite")
    study = store.create_study("missing", {})
    event = store.list_events(study.id)[0]
    callback = MLflowCallback(store)

    def missing(_name: str) -> Any:
        raise ImportError("not installed")

    monkeypatch.setattr("tunarag.integrations.mlflow.import_module", missing)
    with pytest.raises(MissingOptionalDependencyError):
        asyncio.run(callback.on_event(event))
    store.close()
