"""SQLite-backed study, trial, attempt, observation, and event persistence."""

import json
import math
import sqlite3
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from .domain import Candidate, MetricValue, UsageRecord, ValueStatus
from .errors import StoreError, redact
from .serialization import canonical_json, content_hash


class StudyStatus(str, Enum):
    """Durable lifecycle states for a study."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrialStatus(str, Enum):
    """Durable lifecycle states for a trial."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"


class AttemptStatus(str, Enum):
    """Durable lifecycle states for a trial attempt."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"


_STUDY_TRANSITIONS = {
    StudyStatus.CREATED: {StudyStatus.RUNNING, StudyStatus.FAILED, StudyStatus.CANCELLED},
    StudyStatus.RUNNING: {StudyStatus.COMPLETED, StudyStatus.FAILED, StudyStatus.CANCELLED},
    StudyStatus.COMPLETED: set(),
    StudyStatus.FAILED: set(),
    StudyStatus.CANCELLED: set(),
}
_TRIAL_TRANSITIONS = {
    TrialStatus.PENDING: {
        TrialStatus.RUNNING,
        TrialStatus.ABANDONED,
        TrialStatus.CANCELLED,
    },
    TrialStatus.RUNNING: {
        TrialStatus.SUCCEEDED,
        TrialStatus.FAILED,
        TrialStatus.ABANDONED,
        TrialStatus.CANCELLED,
    },
    TrialStatus.SUCCEEDED: set(),
    TrialStatus.FAILED: set(),
    TrialStatus.ABANDONED: set(),
    TrialStatus.CANCELLED: set(),
}
_TERMINAL_TRIAL_STATUSES = {
    TrialStatus.SUCCEEDED,
    TrialStatus.FAILED,
    TrialStatus.ABANDONED,
    TrialStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class StudyRecord:
    """Persisted study identity and lifecycle state."""

    id: str
    name: str
    config_hash: str
    status: StudyStatus
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class TrialRecord:
    """Persisted trial identity and lifecycle state."""

    id: str
    study_id: str
    sequence: int
    candidate_hash: str
    candidate_json: str
    status: TrialStatus
    error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """Persisted execution attempt with a recovery lease."""

    id: str
    trial_id: str
    number: int
    status: AttemptStatus
    started_at: float
    lease_expires_at: float
    finished_at: float | None
    error: str | None


@dataclass(frozen=True, slots=True)
class PersistedUsageRecord:
    """Append-only usage observation associated with a trial and optional attempt."""

    id: str
    trial_id: str
    attempt_id: str | None
    usage: UsageRecord
    created_at: str


@dataclass(frozen=True, slots=True)
class StudyEvent:
    """Ordered durable event for replay and observability."""

    study_id: str
    sequence: int
    type: str
    payload: Mapping[str, Any]
    created_at: str


class SQLiteStore:
    """Transactional SQLite authority for optimization lifecycle state."""

    schema_version = 2

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._connection = sqlite3.connect(str(path), timeout=30.0)
        self._connection.row_factory = sqlite3.Row
        self._clock = clock
        self.initialize()

    def initialize(self) -> None:
        """Create or migrate the experiment schema to the supported version."""

        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        self._connection.commit()
        versions = self._schema_versions()
        if not versions:
            self._create_schema_version_1()
            versions = [1]
        if versions == [1]:
            self._migrate_version_1_to_2()
            versions = [1, 2]
        if versions != [1, 2]:
            self._connection.close()
            raise StoreError(
                "unsupported experiment schema versions",
                stage="store.initialize",
                details={"versions": versions, "supported": self.schema_version},
            )

    def create_study(self, name: str, configuration: object) -> StudyRecord:
        """Create a study in the created state."""

        if not name.strip():
            raise ValueError("study name must not be empty")
        study_id = str(uuid.uuid4())
        config_hash = content_hash(configuration, namespace="study:v1")
        with self._connection:
            self._connection.execute(
                """INSERT INTO studies(id, name, config_hash, status, updated_at)
                VALUES (?, ?, ?, 'created', CURRENT_TIMESTAMP)""",
                (study_id, name, config_hash),
            )
            self._append_event_locked(study_id, "study.created", {"name": name})
        return self.get_study(study_id)

    def get_study(self, study_id: str) -> StudyRecord:
        """Load one study or raise `KeyError`."""

        row = self._connection.execute(
            """SELECT id, name, config_hash, status, created_at, updated_at
            FROM studies WHERE id = ?""",
            (study_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown study: {study_id}")
        return _study_from_row(cast(sqlite3.Row, row))

    def transition_study(self, study_id: str, status: StudyStatus) -> StudyRecord:
        """Apply a guarded study lifecycle transition."""

        self._begin_immediate()
        try:
            current = self._get_study_status_locked(study_id)
            if status not in _STUDY_TRANSITIONS[current]:
                raise ValueError(f"invalid study transition: {current.value} -> {status.value}")
            if status is StudyStatus.COMPLETED:
                active = self._connection.execute(
                    """SELECT 1 FROM trials
                    WHERE study_id = ? AND status IN ('pending', 'running') LIMIT 1""",
                    (study_id,),
                ).fetchone()
                if active is not None:
                    raise ValueError("study cannot complete while trials are active")
            self._connection.execute(
                """UPDATE studies SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                (status.value, study_id),
            )
            self._append_event_locked(
                study_id, f"study.{status.value}", {"previous_status": current.value}
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return self.get_study(study_id)

    def create_trial(self, study_id: str, sequence: int, candidate: Candidate) -> TrialRecord:
        """Create a trial with an explicit nonnegative sequence."""

        if sequence < 0:
            raise ValueError("trial sequence must not be negative")
        self._begin_immediate()
        try:
            self._require_running_study_locked(study_id)
            record = self._insert_trial_locked(study_id, sequence, candidate)
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return record

    def reserve_trial(self, study_id: str, candidate: Candidate) -> TrialRecord:
        """Atomically allocate the next sequence and reserve a unique candidate."""

        self._begin_immediate()
        try:
            self._require_running_study_locked(study_id)
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM trials WHERE study_id = ?",
                (study_id,),
            ).fetchone()
            sequence = int(cast(sqlite3.Row, row)[0])
            record = self._insert_trial_locked(study_id, sequence, candidate)
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return record

    def get_trial(self, trial_id: str) -> TrialRecord:
        """Load one trial or raise `KeyError`."""

        row = self._connection.execute(
            """SELECT id, study_id, sequence, candidate_hash, candidate_json, status,
            error, created_at, updated_at FROM trials WHERE id = ?""",
            (trial_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown trial: {trial_id}")
        return _trial_from_row(cast(sqlite3.Row, row))

    def list_trials(self, study_id: str) -> list[TrialRecord]:
        """Return trials in durable sequence order."""

        rows = self._connection.execute(
            """SELECT id, study_id, sequence, candidate_hash, candidate_json, status,
            error, created_at, updated_at FROM trials
            WHERE study_id = ? ORDER BY sequence""",
            (study_id,),
        ).fetchall()
        return [_trial_from_row(row) for row in rows]

    def transition_trial(
        self, trial_id: str, status: TrialStatus, *, error: str | None = None
    ) -> TrialRecord:
        """Apply a guarded trial lifecycle transition."""

        self._begin_immediate()
        try:
            row = self._get_trial_row_locked(trial_id)
            current = TrialStatus(row["status"])
            if status not in _TRIAL_TRANSITIONS[current]:
                raise ValueError(f"invalid trial transition: {current.value} -> {status.value}")
            if status in _TERMINAL_TRIAL_STATUSES:
                active = self._connection.execute(
                    "SELECT 1 FROM trial_attempts WHERE trial_id = ? AND status = 'running'",
                    (trial_id,),
                ).fetchone()
                if active is not None:
                    raise ValueError("active attempt must be completed through commit_trial_result")
            self._connection.execute(
                """UPDATE trials SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                (status.value, error, trial_id),
            )
            self._append_event_locked(
                row["study_id"],
                f"trial.{status.value}",
                {"trial_id": trial_id, "previous_status": current.value},
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return self.get_trial(trial_id)

    def start_attempt(
        self,
        trial_id: str,
        *,
        lease_seconds: float,
        now: float | None = None,
    ) -> AttemptRecord:
        """Start the next attempt and acquire its recovery lease."""

        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("attempt lease must be a positive finite number")
        started_at = self._timestamp(now)
        self._begin_immediate()
        try:
            trial = self._get_trial_row_locked(trial_id)
            trial_status = TrialStatus(trial["status"])
            if trial_status not in {TrialStatus.PENDING, TrialStatus.RUNNING}:
                raise ValueError(f"cannot start attempt for {trial_status.value} trial")
            active = self._connection.execute(
                "SELECT 1 FROM trial_attempts WHERE trial_id = ? AND status = 'running'",
                (trial_id,),
            ).fetchone()
            if active is not None:
                raise ValueError("trial already has a running attempt")
            row = self._connection.execute(
                """SELECT COALESCE(MAX(attempt_number), -1) + 1
                FROM trial_attempts WHERE trial_id = ?""",
                (trial_id,),
            ).fetchone()
            number = int(cast(sqlite3.Row, row)[0])
            attempt_id = str(uuid.uuid4())
            lease_expires_at = started_at + lease_seconds
            self._connection.execute(
                """INSERT INTO trial_attempts(
                    id, trial_id, attempt_number, status, started_at, lease_expires_at
                ) VALUES (?, ?, ?, 'running', ?, ?)""",
                (attempt_id, trial_id, number, started_at, lease_expires_at),
            )
            if trial_status is TrialStatus.PENDING:
                self._connection.execute(
                    """UPDATE trials SET status = 'running', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?""",
                    (trial_id,),
                )
            self._append_event_locked(
                trial["study_id"],
                "trial.attempt.started",
                {"trial_id": trial_id, "attempt_id": attempt_id, "attempt": number},
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return self.get_attempt(attempt_id)

    def get_attempt(self, attempt_id: str) -> AttemptRecord:
        """Load one attempt or raise `KeyError`."""

        row = self._connection.execute(
            """SELECT id, trial_id, attempt_number, status, started_at,
            lease_expires_at, finished_at, error FROM trial_attempts WHERE id = ?""",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown attempt: {attempt_id}")
        return _attempt_from_row(cast(sqlite3.Row, row))

    def list_attempts(self, trial_id: str) -> list[AttemptRecord]:
        """Return attempts in monotonic attempt-number order."""

        rows = self._connection.execute(
            """SELECT id, trial_id, attempt_number, status, started_at,
            lease_expires_at, finished_at, error FROM trial_attempts
            WHERE trial_id = ? ORDER BY attempt_number""",
            (trial_id,),
        ).fetchall()
        return [_attempt_from_row(row) for row in rows]

    def finish_attempt(
        self,
        attempt_id: str,
        status: AttemptStatus,
        *,
        usage: Sequence[UsageRecord] = (),
        error: str | None = None,
        now: float | None = None,
    ) -> AttemptRecord:
        """Finish a running attempt while leaving retryable trial state intact."""

        if status is AttemptStatus.RUNNING:
            raise ValueError("attempt terminal status must not be running")
        finished_at = self._timestamp(now)
        self._begin_immediate()
        try:
            row = self._get_attempt_row_locked(attempt_id)
            if AttemptStatus(row["status"]) is not AttemptStatus.RUNNING:
                raise ValueError("only a running attempt can be finished")
            self._connection.execute(
                """UPDATE trial_attempts SET status = ?, finished_at = ?, error = ?
                WHERE id = ?""",
                (status.value, finished_at, error, attempt_id),
            )
            self._insert_usage_locked(row["trial_id"], attempt_id, usage)
            trial = self._get_trial_row_locked(row["trial_id"])
            self._append_event_locked(
                trial["study_id"],
                f"trial.attempt.{status.value}",
                {"trial_id": row["trial_id"], "attempt_id": attempt_id},
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return self.get_attempt(attempt_id)

    def abandon_expired_attempts(self, *, now: float | None = None) -> list[AttemptRecord]:
        """Persist abandonment for every running attempt with an expired lease."""

        timestamp = self._timestamp(now)
        abandoned_ids: list[str] = []
        self._begin_immediate()
        try:
            rows = self._connection.execute(
                """SELECT id, trial_id FROM trial_attempts
                WHERE status = 'running' AND lease_expires_at <= ?
                ORDER BY started_at, id""",
                (timestamp,),
            ).fetchall()
            for row in rows:
                self._connection.execute(
                    """UPDATE trial_attempts
                    SET status = 'abandoned', finished_at = ?, error = 'lease expired'
                    WHERE id = ?""",
                    (timestamp, row["id"]),
                )
                trial = self._get_trial_row_locked(row["trial_id"])
                self._append_event_locked(
                    trial["study_id"],
                    "trial.attempt.abandoned",
                    {"trial_id": row["trial_id"], "attempt_id": row["id"]},
                )
                abandoned_ids.append(row["id"])
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return [self.get_attempt(attempt_id) for attempt_id in abandoned_ids]

    def list_recoverable_trials(self, study_id: str) -> list[TrialRecord]:
        """Return running trials that have no active attempt."""

        rows = self._connection.execute(
            """SELECT t.id, t.study_id, t.sequence, t.candidate_hash, t.candidate_json,
            t.status, t.error, t.created_at, t.updated_at
            FROM trials AS t
            WHERE t.study_id = ? AND t.status = 'running'
              AND NOT EXISTS (
                  SELECT 1 FROM trial_attempts AS a
                  WHERE a.trial_id = t.id AND a.status = 'running'
              )
            ORDER BY t.sequence""",
            (study_id,),
        ).fetchall()
        return [_trial_from_row(row) for row in rows]

    def commit_trial_result(
        self,
        trial_id: str,
        *,
        status: TrialStatus,
        metrics: Sequence[MetricValue] = (),
        usage: Sequence[UsageRecord] = (),
        attempt_id: str | None = None,
        error: str | None = None,
        now: float | None = None,
    ) -> TrialRecord:
        """Atomically persist observations, attempt completion, and terminal trial state."""

        if status not in _TERMINAL_TRIAL_STATUSES:
            raise ValueError("trial result status must be terminal")
        metric_names = [metric.name for metric in metrics]
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("trial result contains duplicate metric names")
        finished_at = self._timestamp(now)
        self._begin_immediate()
        try:
            trial = self._get_trial_row_locked(trial_id)
            if TrialStatus(trial["status"]) is not TrialStatus.RUNNING:
                raise ValueError("only a running trial can commit a result")
            if attempt_id is not None:
                attempt = self._get_attempt_row_locked(attempt_id)
                if attempt["trial_id"] != trial_id:
                    raise ValueError("attempt does not belong to trial")
                if AttemptStatus(attempt["status"]) is not AttemptStatus.RUNNING:
                    raise ValueError("only a running attempt can commit a trial result")
                attempt_status = _attempt_status_for_trial(status)
                self._connection.execute(
                    """UPDATE trial_attempts SET status = ?, finished_at = ?, error = ?
                    WHERE id = ?""",
                    (attempt_status.value, finished_at, error, attempt_id),
                )
            for metric in metrics:
                self._connection.execute(
                    """INSERT INTO metric_values(
                        trial_id, name, value, status, coverage
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (trial_id, metric.name, metric.value, metric.status.value, metric.coverage),
                )
            self._insert_usage_locked(trial_id, attempt_id, usage)
            self._connection.execute(
                """UPDATE trials SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                (status.value, error, trial_id),
            )
            self._append_event_locked(
                trial["study_id"],
                f"trial.{status.value}",
                {
                    "trial_id": trial_id,
                    "attempt_id": attempt_id,
                    "metric_count": len(metrics),
                    "usage_count": len(usage),
                },
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return self.get_trial(trial_id)

    def list_metrics(self, trial_id: str) -> list[MetricValue]:
        """Return committed metrics ordered by name."""

        rows = self._connection.execute(
            """SELECT name, value, status, coverage FROM metric_values
            WHERE trial_id = ? ORDER BY name""",
            (trial_id,),
        ).fetchall()
        return [
            MetricValue(row["name"], row["value"], ValueStatus(row["status"]), row["coverage"])
            for row in rows
        ]

    def list_usage(self, trial_id: str) -> list[PersistedUsageRecord]:
        """Return append-only usage in insertion order."""

        rows = self._connection.execute(
            """SELECT id, trial_id, attempt_id, component, input_tokens, output_tokens,
            cost_text, latency_seconds, status, pricing_version, created_at
            FROM usage_records WHERE trial_id = ? ORDER BY rowid""",
            (trial_id,),
        ).fetchall()
        records: list[PersistedUsageRecord] = []
        for row in rows:
            cost = None if row["cost_text"] is None else float(row["cost_text"])
            records.append(
                PersistedUsageRecord(
                    id=row["id"],
                    trial_id=row["trial_id"],
                    attempt_id=row["attempt_id"],
                    usage=UsageRecord(
                        component=row["component"],
                        input_tokens=row["input_tokens"],
                        output_tokens=row["output_tokens"],
                        cost=cost,
                        latency_seconds=row["latency_seconds"],
                        status=ValueStatus(row["status"]),
                        pricing_version=row["pricing_version"],
                    ),
                    created_at=row["created_at"],
                )
            )
        return records

    def append_event(
        self, study_id: str, event_type: str, payload: Mapping[str, Any]
    ) -> StudyEvent:
        """Append a canonical event with an atomic per-study sequence."""

        self._validate_event_type(event_type)
        self._begin_immediate()
        try:
            self._get_study_status_locked(study_id)
            event = self._append_event_locked(study_id, event_type, payload)
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        return event

    def list_events(self, study_id: str, *, after_sequence: int = -1) -> list[StudyEvent]:
        """Return durable events after a sequence in replay order."""

        rows = self._connection.execute(
            """SELECT study_id, sequence, type, payload_json, created_at
            FROM study_events WHERE study_id = ? AND sequence > ? ORDER BY sequence""",
            (study_id, after_sequence),
        ).fetchall()
        return [_event_from_row(row) for row in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    def _insert_usage_locked(
        self,
        trial_id: str,
        attempt_id: str | None,
        usage: Sequence[UsageRecord],
    ) -> None:
        for item in usage:
            self._connection.execute(
                """INSERT INTO usage_records(
                    id, trial_id, attempt_id, component, input_tokens, output_tokens,
                    cost_text, latency_seconds, status, pricing_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    trial_id,
                    attempt_id,
                    item.component,
                    item.input_tokens,
                    item.output_tokens,
                    None if item.cost is None else format(item.cost, ".17g"),
                    item.latency_seconds,
                    item.status.value,
                    item.pricing_version,
                ),
            )

    def _insert_trial_locked(
        self, study_id: str, sequence: int, candidate: Candidate
    ) -> TrialRecord:
        candidate_bytes = canonical_json(candidate.parameters)
        trial_id = str(uuid.uuid4())
        self._connection.execute(
            """INSERT INTO trials(
                id, study_id, sequence, candidate_hash, candidate_json, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)""",
            (
                trial_id,
                study_id,
                sequence,
                content_hash(candidate.parameters, namespace="candidate:v1"),
                candidate_bytes.decode("utf-8"),
            ),
        )
        self._append_event_locked(
            study_id, "trial.reserved", {"trial_id": trial_id, "sequence": sequence}
        )
        return self.get_trial(trial_id)

    def _append_event_locked(
        self, study_id: str, event_type: str, payload: Mapping[str, Any]
    ) -> StudyEvent:
        self._validate_event_type(event_type)
        row = self._connection.execute(
            "SELECT COALESCE(MAX(sequence), -1) + 1 FROM study_events WHERE study_id = ?",
            (study_id,),
        ).fetchone()
        sequence = int(cast(sqlite3.Row, row)[0])
        safe_payload = cast(dict[str, Any], redact(payload))
        payload_json = canonical_json(safe_payload).decode("utf-8")
        self._connection.execute(
            """INSERT INTO study_events(study_id, sequence, type, payload_json)
            VALUES (?, ?, ?, ?)""",
            (study_id, sequence, event_type, payload_json),
        )
        row = self._connection.execute(
            """SELECT study_id, sequence, type, payload_json, created_at
            FROM study_events WHERE study_id = ? AND sequence = ?""",
            (study_id, sequence),
        ).fetchone()
        return _event_from_row(cast(sqlite3.Row, row))

    def _get_study_status_locked(self, study_id: str) -> StudyStatus:
        row = self._connection.execute(
            "SELECT status FROM studies WHERE id = ?", (study_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown study: {study_id}")
        return StudyStatus(row["status"])

    def _require_running_study_locked(self, study_id: str) -> None:
        status = self._get_study_status_locked(study_id)
        if status is not StudyStatus.RUNNING:
            raise ValueError(f"study must be running to reserve trials, not {status.value}")

    def _get_trial_row_locked(self, trial_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            """SELECT id, study_id, sequence, candidate_hash, candidate_json, status,
            error, created_at, updated_at FROM trials WHERE id = ?""",
            (trial_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown trial: {trial_id}")
        return cast(sqlite3.Row, row)

    def _get_attempt_row_locked(self, attempt_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            """SELECT id, trial_id, attempt_number, status, started_at,
            lease_expires_at, finished_at, error FROM trial_attempts WHERE id = ?""",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown attempt: {attempt_id}")
        return cast(sqlite3.Row, row)

    def _schema_versions(self) -> list[int]:
        return [
            int(row[0])
            for row in self._connection.execute(
                "SELECT version FROM schema_version ORDER BY version"
            )
        ]

    def _create_schema_version_1(self) -> None:
        try:
            self._connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE studies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE trials (
                    id TEXT PRIMARY KEY,
                    study_id TEXT NOT NULL REFERENCES studies(id),
                    sequence INTEGER NOT NULL,
                    candidate_hash TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(study_id, sequence)
                );
                INSERT INTO schema_version(version) VALUES (1);
                COMMIT;
                """
            )
        except sqlite3.Error as error:
            self._connection.rollback()
            self._connection.close()
            raise StoreError("could not create experiment schema", stage="store.migrate") from error

    def _migrate_version_1_to_2(self) -> None:
        try:
            self._connection.executescript(
                """
                BEGIN IMMEDIATE;
                ALTER TABLE studies ADD COLUMN status TEXT NOT NULL DEFAULT 'created';
                ALTER TABLE studies ADD COLUMN updated_at TEXT;
                UPDATE studies SET updated_at = created_at WHERE updated_at IS NULL;
                ALTER TABLE trials ADD COLUMN updated_at TEXT;
                UPDATE trials SET updated_at = created_at WHERE updated_at IS NULL;
                CREATE UNIQUE INDEX uq_trials_study_candidate
                    ON trials(study_id, candidate_hash);
                CREATE TABLE trial_attempts (
                    id TEXT PRIMARY KEY,
                    trial_id TEXT NOT NULL REFERENCES trials(id),
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    lease_expires_at REAL NOT NULL,
                    finished_at REAL,
                    error TEXT,
                    UNIQUE(trial_id, attempt_number),
                    CHECK(attempt_number >= 0),
                    CHECK(status IN ('running', 'succeeded', 'failed', 'abandoned', 'cancelled'))
                );
                CREATE UNIQUE INDEX uq_trial_attempts_running
                    ON trial_attempts(trial_id) WHERE status = 'running';
                CREATE INDEX idx_trial_attempts_recovery
                    ON trial_attempts(status, lease_expires_at);
                CREATE TABLE metric_values (
                    trial_id TEXT NOT NULL REFERENCES trials(id),
                    name TEXT NOT NULL,
                    value REAL,
                    status TEXT NOT NULL,
                    coverage REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(trial_id, name),
                    CHECK(status IN ('exact', 'estimated', 'unavailable')),
                    CHECK(coverage >= 0.0 AND coverage <= 1.0)
                );
                CREATE TABLE usage_records (
                    id TEXT PRIMARY KEY,
                    trial_id TEXT NOT NULL REFERENCES trials(id),
                    attempt_id TEXT REFERENCES trial_attempts(id),
                    component TEXT NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cost_text TEXT,
                    latency_seconds REAL,
                    status TEXT NOT NULL,
                    pricing_version TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK(status IN ('exact', 'estimated', 'unavailable'))
                );
                CREATE INDEX idx_usage_records_trial ON usage_records(trial_id);
                CREATE TABLE study_events (
                    study_id TEXT NOT NULL REFERENCES studies(id),
                    sequence INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(study_id, sequence)
                );
                INSERT INTO schema_version(version) VALUES (2);
                COMMIT;
                """
            )
        except sqlite3.Error as error:
            self._connection.rollback()
            self._connection.close()
            raise StoreError(
                "could not migrate experiment schema to version 2",
                stage="store.migrate",
                details={"target_version": 2, "cause": type(error).__name__},
            ) from error

    def _begin_immediate(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")

    def _timestamp(self, value: float | None) -> float:
        timestamp = float(self._clock() if value is None else value)
        if not math.isfinite(timestamp):
            raise ValueError("timestamp must be finite")
        return timestamp

    @staticmethod
    def _validate_event_type(event_type: str) -> None:
        if not event_type.strip():
            raise ValueError("event type must not be empty")


def _study_from_row(row: sqlite3.Row) -> StudyRecord:
    return StudyRecord(
        id=row["id"],
        name=row["name"],
        config_hash=row["config_hash"],
        status=StudyStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _trial_from_row(row: sqlite3.Row) -> TrialRecord:
    return TrialRecord(
        id=row["id"],
        study_id=row["study_id"],
        sequence=row["sequence"],
        candidate_hash=row["candidate_hash"],
        candidate_json=row["candidate_json"],
        status=TrialStatus(row["status"]),
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _attempt_from_row(row: sqlite3.Row) -> AttemptRecord:
    return AttemptRecord(
        id=row["id"],
        trial_id=row["trial_id"],
        number=row["attempt_number"],
        status=AttemptStatus(row["status"]),
        started_at=row["started_at"],
        lease_expires_at=row["lease_expires_at"],
        finished_at=row["finished_at"],
        error=row["error"],
    )


def _event_from_row(row: sqlite3.Row) -> StudyEvent:
    payload = json.loads(row["payload_json"])
    if not isinstance(payload, dict):
        raise StoreError("event payload is not an object", stage="store.read")
    return StudyEvent(
        study_id=row["study_id"],
        sequence=row["sequence"],
        type=row["type"],
        payload=cast(dict[str, Any], payload),
        created_at=row["created_at"],
    )


def _attempt_status_for_trial(status: TrialStatus) -> AttemptStatus:
    return {
        TrialStatus.SUCCEEDED: AttemptStatus.SUCCEEDED,
        TrialStatus.FAILED: AttemptStatus.FAILED,
        TrialStatus.ABANDONED: AttemptStatus.ABANDONED,
        TrialStatus.CANCELLED: AttemptStatus.CANCELLED,
    }[status]
