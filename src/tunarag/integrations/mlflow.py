"""Optional post-commit MLflow tracking mirror."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

from ..errors import MissingOptionalDependencyError, redact
from ..store import SQLiteStore, StudyEvent, TrialStatus


class MLflowClient(Protocol):
    """Subset of the low-level MLflow client used by the mirror."""

    def create_run(self, experiment_id: str, *, tags: Mapping[str, str]) -> Any: ...

    def log_metric(
        self, run_id: str, key: str, value: float, *, step: int | None = None
    ) -> Any: ...

    def log_param(self, run_id: str, key: str, value: Any) -> Any: ...

    def set_tag(self, run_id: str, key: str, value: Any) -> None: ...

    def set_terminated(self, run_id: str, *, status: str | None = None) -> None: ...


@dataclass(frozen=True, slots=True)
class _TrialMirrorData:
    sequence: int
    status: TrialStatus
    candidate: Mapping[str, Any]
    metrics: Mapping[str, float]


class MLflowCallback:
    """Mirror committed study events into one low-level MLflow run."""

    def __init__(
        self,
        store: SQLiteStore,
        *,
        experiment_id: str = "0",
        tracking_uri: str | None = None,
        tags: Mapping[str, str] | None = None,
        client: MLflowClient | None = None,
    ) -> None:
        if not experiment_id.strip():
            raise ValueError("MLflow experiment id must not be empty")
        self._store = store
        self._experiment_id = experiment_id
        self._tracking_uri = tracking_uri
        safe_tags = redact(tags or {})
        if not isinstance(safe_tags, Mapping):
            raise TypeError("MLflow tags must be a mapping")
        self._tags = {str(key): str(value) for key, value in safe_tags.items()}
        self._client = client
        self._run_ids: dict[str, str] = {}

    async def on_event(self, event: StudyEvent) -> None:
        """Mirror one durable event after gathering committed local state."""

        trial_data = self._trial_data(event)
        await asyncio.to_thread(self._mirror, event, trial_data)

    def _trial_data(self, event: StudyEvent) -> _TrialMirrorData | None:
        if event.type not in {"trial.succeeded", "trial.failed", "trial.cancelled"}:
            return None
        trial_id = event.payload.get("trial_id")
        if not isinstance(trial_id, str):
            return None
        trial = self._store.get_trial(trial_id)
        candidate = json.loads(trial.candidate_json)
        if not isinstance(candidate, Mapping):
            candidate = {}
        safe_candidate = redact(candidate)
        if not isinstance(safe_candidate, Mapping):
            safe_candidate = {}
        metrics = {
            metric.name: float(metric.value)
            for metric in self._store.list_metrics(trial_id)
            if metric.value is not None
        }
        return _TrialMirrorData(trial.sequence, trial.status, safe_candidate, metrics)

    def _mirror(self, event: StudyEvent, trial: _TrialMirrorData | None) -> None:
        client = self._client_or_import()
        run_id = self._run_ids.get(event.study_id)
        if run_id is None:
            tags = {
                **self._tags,
                "tunarag.study_id": event.study_id,
                "tunarag.mirror": "event-callback",
            }
            run = client.create_run(self._experiment_id, tags=tags)
            run_id = str(run.info.run_id)
            self._run_ids[event.study_id] = run_id
        client.set_tag(run_id, "tunarag.last_event", event.type)
        client.set_tag(run_id, "tunarag.last_event_sequence", event.sequence)
        if trial is not None:
            self._mirror_trial(client, run_id, trial)
        terminal_status = {
            "study.completed": "FINISHED",
            "study.failed": "FAILED",
            "study.cancelled": "KILLED",
        }.get(event.type)
        if terminal_status is not None:
            client.set_terminated(run_id, status=terminal_status)

    def _mirror_trial(self, client: MLflowClient, run_id: str, trial: _TrialMirrorData) -> None:
        prefix = f"trial.{trial.sequence}"
        client.set_tag(run_id, f"{prefix}.status", trial.status.value)
        for key, value in sorted(trial.candidate.items()):
            client.log_param(
                run_id, _tracking_key(f"{prefix}.candidate.{key}"), _parameter_value(value)
            )
        for name, value in sorted(trial.metrics.items()):
            client.log_metric(run_id, _tracking_key(name), value, step=trial.sequence)
        client.log_metric(
            run_id,
            "tunarag.trial_failed",
            1.0 if trial.status is TrialStatus.FAILED else 0.0,
            step=trial.sequence,
        )

    def _client_or_import(self) -> MLflowClient:
        if self._client is not None:
            return self._client
        try:
            module = import_module("mlflow")
        except ImportError as error:
            raise MissingOptionalDependencyError("MLflow tracking", "mlflow") from error
        self._client = module.MlflowClient(tracking_uri=self._tracking_uri)
        return self._client


def _parameter_value(value: Any) -> str:
    safe = redact(value)
    if safe is None or isinstance(safe, (bool, int, float, str)):
        return str(safe)
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tracking_key(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.\-/ ]", "_", value)
    if normalized == value and len(normalized) <= 250:
        return normalized
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{normalized[:237]}.{digest}"
