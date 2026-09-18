import sqlite3

import pytest

from tunarag.domain import Candidate
from tunarag.store import SQLiteStore, TrialStatus


def test_study_and_trial_lifecycle_survives_store_reopen(tmp_path) -> None:
    path = tmp_path / "study.sqlite"
    store = SQLiteStore(path)
    study = store.create_study("demo", {"seed": 7})
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
    store.create_trial(study.id, 1, Candidate({"value": "a"}))

    with pytest.raises(sqlite3.IntegrityError):
        store.create_trial(study.id, 1, Candidate({"value": "b"}))

    store.close()