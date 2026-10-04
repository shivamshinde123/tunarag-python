import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tunarag import (
    AttemptStatus,
    Candidate,
    MetricValue,
    SQLiteStore,
    StoreError,
    StudyStatus,
    TrialStatus,
    UsageRecord,
    ValueStatus,
)


def test_study_and_trial_lifecycle_survives_store_reopen(tmp_path) -> None:
    path = tmp_path / "study.sqlite"
    store = SQLiteStore(path)
    study = store.create_study("demo", {"seed": 7})
    store.transition_study(study.id, StudyStatus.RUNNING)
    trial = store.create_trial(study.id, 0, Candidate({"top_k": 3}))
    store.transition_trial(trial.id, TrialStatus.RUNNING)
    store.transition_trial(trial.id, TrialStatus.FAILED, error="provider unavailable")
    store.close()

    reopened = SQLiteStore(path)
    persisted = reopened.get_trial(trial.id)

    assert persisted.status is TrialStatus.FAILED
    assert persisted.error == "provider unavailable"
    assert persisted.candidate_json == '{"top_k":3}'
    reopened.close()


def test_trial_sequence_is_unique_per_study() -> None:
    store = SQLiteStore()
    study = store.create_study("demo", {})
    store.transition_study(study.id, StudyStatus.RUNNING)
    store.create_trial(study.id, 1, Candidate({"value": "a"}))

    with pytest.raises(sqlite3.IntegrityError):
        store.create_trial(study.id, 1, Candidate({"value": "b"}))

    store.close()


def test_store_guards_lifecycle_and_candidate_uniqueness() -> None:
    store = SQLiteStore()
    study = store.create_study("demo", {})

    with pytest.raises(ValueError, match="must be running"):
        store.reserve_trial(study.id, Candidate({"top_k": 3}))

    running = store.transition_study(study.id, StudyStatus.RUNNING)
    first = store.reserve_trial(running.id, Candidate({"top_k": 3}))
    second = store.reserve_trial(running.id, Candidate({"top_k": 4}))

    assert first.sequence == 0
    assert second.sequence == 1
    with pytest.raises(sqlite3.IntegrityError):
        store.reserve_trial(running.id, Candidate({"top_k": 3}))

    store.transition_trial(first.id, TrialStatus.RUNNING)
    with pytest.raises(ValueError, match="trials are active"):
        store.transition_study(study.id, StudyStatus.COMPLETED)
    terminal = store.transition_trial(first.id, TrialStatus.SUCCEEDED)
    assert terminal.status is TrialStatus.SUCCEEDED
    with pytest.raises(ValueError, match="invalid trial transition"):
        store.transition_trial(first.id, TrialStatus.RUNNING)
    store.transition_trial(second.id, TrialStatus.CANCELLED)
    completed = store.transition_study(study.id, StudyStatus.COMPLETED)
    assert completed.status is StudyStatus.COMPLETED
    store.close()


def test_attempt_leases_are_recoverable_without_reusing_attempt_numbers() -> None:
    now = 10.0
    store = SQLiteStore(clock=lambda: now)
    study = store.create_study("recovery", {})
    store.transition_study(study.id, StudyStatus.RUNNING)
    trial = store.reserve_trial(study.id, Candidate({"model": "small"}))
    first = store.start_attempt(trial.id, lease_seconds=5.0)

    assert first.number == 0
    assert store.abandon_expired_attempts(now=14.0) == []

    abandoned = store.abandon_expired_attempts(now=16.0)
    assert abandoned[0].status is AttemptStatus.ABANDONED
    assert abandoned[0].error == "lease expired"
    assert store.list_recoverable_trials(study.id) == [store.get_trial(trial.id)]

    now = 20.0
    second = store.start_attempt(trial.id, lease_seconds=5.0)
    assert second.number == 1
    assert [attempt.number for attempt in store.list_attempts(trial.id)] == [0, 1]
    store.close()


def test_terminal_commit_is_atomic_and_replayable(tmp_path) -> None:
    path = tmp_path / "study.sqlite"
    store = SQLiteStore(path, clock=lambda: 100.0)
    study = store.create_study("result", {})
    store.transition_study(study.id, StudyStatus.RUNNING)
    trial = store.reserve_trial(study.id, Candidate({"top_k": 5}))
    attempt = store.start_attempt(trial.id, lease_seconds=30.0)

    with pytest.raises(ValueError, match="active attempt"):
        store.transition_trial(trial.id, TrialStatus.SUCCEEDED)

    result = store.commit_trial_result(
        trial.id,
        status=TrialStatus.SUCCEEDED,
        attempt_id=attempt.id,
        metrics=[MetricValue("quality", 0.9)],
        usage=[
            UsageRecord(
                "generator",
                input_tokens=10,
                output_tokens=4,
                cost=0.0125,
                status=ValueStatus.ESTIMATED,
                pricing_version="2026-10",
            )
        ],
    )

    assert result.status is TrialStatus.SUCCEEDED
    assert store.get_attempt(attempt.id).status is AttemptStatus.SUCCEEDED
    assert store.list_metrics(trial.id) == [MetricValue("quality", 0.9)]
    persisted_usage = store.list_usage(trial.id)
    assert persisted_usage[0].usage.cost == 0.0125
    assert persisted_usage[0].usage.status is ValueStatus.ESTIMATED
    events = store.list_events(study.id)
    assert [event.sequence for event in events] == list(range(len(events)))
    assert events[-1].type == "trial.succeeded"
    redacted = store.append_event(
        study.id, "diagnostic", {"access_token": "do-not-store", "input_tokens": 10}
    )
    assert redacted.payload == {"access_token": "***redacted***", "input_tokens": 10}
    store.close()

    reopened = SQLiteStore(path)
    assert reopened.get_trial(trial.id).status is TrialStatus.SUCCEEDED
    assert reopened.list_metrics(trial.id) == [MetricValue("quality", 0.9)]
    assert reopened.list_usage(trial.id)[0].usage.pricing_version == "2026-10"
    reopened.close()


def test_terminal_commit_rolls_back_when_attempt_belongs_to_another_trial() -> None:
    store = SQLiteStore()
    study = store.create_study("atomic", {})
    store.transition_study(study.id, StudyStatus.RUNNING)
    first = store.reserve_trial(study.id, Candidate({"value": "first"}))
    second = store.reserve_trial(study.id, Candidate({"value": "second"}))
    store.start_attempt(first.id, lease_seconds=10.0)
    second_attempt = store.start_attempt(second.id, lease_seconds=10.0)

    with pytest.raises(ValueError, match="does not belong"):
        store.commit_trial_result(
            first.id,
            status=TrialStatus.SUCCEEDED,
            attempt_id=second_attempt.id,
            metrics=[MetricValue("quality", 1.0)],
            usage=[UsageRecord("generator", input_tokens=1)],
        )

    assert store.get_trial(first.id).status is TrialStatus.RUNNING
    assert store.list_metrics(first.id) == []
    assert store.list_usage(first.id) == []
    store.close()


def test_version_one_database_migrates_without_losing_records(tmp_path) -> None:
    path = tmp_path / "version-one.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
        INSERT INTO schema_version(version) VALUES (1);
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
        INSERT INTO studies(id, name, config_hash) VALUES ('study-1', 'legacy', 'hash');
        INSERT INTO trials(
            id, study_id, sequence, candidate_hash, candidate_json, status
        ) VALUES ('trial-1', 'study-1', 0, 'candidate', '{"top_k":3}', 'pending');
        """
    )
    connection.close()

    store = SQLiteStore(path)

    assert store.get_study("study-1").status is StudyStatus.CREATED
    assert store.get_trial("trial-1").status is TrialStatus.PENDING
    store.close()


def test_store_rejects_unknown_schema_version(tmp_path) -> None:
    path = tmp_path / "future.sqlite"
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO schema_version(version) VALUES (99)")
    connection.close()

    with pytest.raises(StoreError, match="unsupported experiment schema"):
        SQLiteStore(path)


def test_concurrent_connections_allocate_unique_trial_and_event_sequences(tmp_path) -> None:
    path = tmp_path / "concurrent.sqlite"
    store = SQLiteStore(path)
    study = store.create_study("concurrent", {})
    store.transition_study(study.id, StudyStatus.RUNNING)

    def reserve(index: int) -> int:
        connection = SQLiteStore(path)
        try:
            return connection.reserve_trial(study.id, Candidate({"worker": index})).sequence
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        sequences = list(executor.map(reserve, range(8)))

    assert sorted(sequences) == list(range(8))
    events = store.list_events(study.id)
    assert [event.sequence for event in events] == list(range(len(events)))
    store.close()
