"""SQLite-backed study and trial lifecycle persistence."""

import sqlite3
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .domain import Candidate
from .serialization import canonical_json, content_hash


class TrialStatus(str, Enum):
    """Durable lifecycle states for a trial."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass(frozen=True, slots=True)
class StudyRecord:
    """Persisted study identity."""

    id: str
    name: str
    config_hash: str


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


class SQLiteStore:
    """Small transactional SQLite store for the study lifecycle."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self._connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );
            INSERT OR IGNORE INTO schema_version(version) VALUES (1);
            CREATE TABLE IF NOT EXISTS studies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS trials (
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
            """
        )
        self._connection.commit()

    def create_study(self, name: str, configuration: object) -> StudyRecord:
        if not name.strip():
            raise ValueError("study name must not be empty")
        record = StudyRecord(
            str(uuid.uuid4()), name, content_hash(configuration, namespace="study:v1")
        )
        with self._connection:
            self._connection.execute(
                "INSERT INTO studies(id, name, config_hash) VALUES (?, ?, ?)",
                (record.id, record.name, record.config_hash),
            )
        return record

    def create_trial(self, study_id: str, sequence: int, candidate: Candidate) -> TrialRecord:
        if sequence < 0:
            raise ValueError("trial sequence must not be negative")
        candidate_bytes = canonical_json(candidate.parameters)
        record = TrialRecord(
            id=str(uuid.uuid4()),
            study_id=study_id,
            sequence=sequence,
            candidate_hash=content_hash(candidate.parameters, namespace="candidate:v1"),
            candidate_json=candidate_bytes.decode("utf-8"),
            status=TrialStatus.PENDING,
            error=None,
        )
        with self._connection:
            self._connection.execute(
                """INSERT INTO trials(
                    id, study_id, sequence, candidate_hash, candidate_json, status
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.study_id,
                    record.sequence,
                    record.candidate_hash,
                    record.candidate_json,
                    record.status.value,
                ),
            )
        return record

    def transition_trial(
        self, trial_id: str, status: TrialStatus, *, error: str | None = None
    ) -> TrialRecord:
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE trials SET status = ?, error = ? WHERE id = ?",
                (status.value, error, trial_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown trial: {trial_id}")
        return self.get_trial(trial_id)

    def get_trial(self, trial_id: str) -> TrialRecord:
        row = self._connection.execute(
            "SELECT id, study_id, sequence, candidate_hash, candidate_json, status, error "
            "FROM trials WHERE id = ?",
            (trial_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown trial: {trial_id}")
        return TrialRecord(
            id=row["id"],
            study_id=row["study_id"],
            sequence=row["sequence"],
            candidate_hash=row["candidate_hash"],
            candidate_json=row["candidate_json"],
            status=TrialStatus(row["status"]),
            error=row["error"],
        )

    def close(self) -> None:
        self._connection.close()
