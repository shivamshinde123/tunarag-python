import json
import os
import subprocess
import sys
from pathlib import Path

import tunarag
from tunarag import SQLiteStore


def test_abrupt_process_death_recovers_only_unfinished_trial(tmp_path):
    worker = Path(__file__).with_name("process_recovery_worker.py")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(tunarag.__file__).resolve().parents[1])
    options = {
        "env": environment,
        "capture_output": True,
        "text": True,
        "timeout": 45,
        "creationflags": subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    }
    crashed = subprocess.run([sys.executable, str(worker), str(tmp_path), "crash"], **options)
    assert crashed.returncode == 23, crashed.stderr
    resumed = subprocess.run([sys.executable, str(worker), str(tmp_path), "resume"], **options)
    assert resumed.returncode == 0, resumed.stderr
    calls = [
        json.loads(line)["top_k"] for line in (tmp_path / "calls.jsonl").read_text().splitlines()
    ]
    assert calls == [2, 1, 1]
    reloaded = subprocess.run([sys.executable, str(worker), str(tmp_path), "reload"], **options)
    assert reloaded.returncode == 0, reloaded.stderr
    assert (tmp_path / "calls.jsonl").read_text().count("\n") == 3
    store = SQLiteStore(tmp_path / "study.db")
    try:
        study_id = (tmp_path / "study-id.txt").read_text()
        trials = store.list_trials(study_id)
        assert len(trials) == 2
        assert [item.status.value for item in store.list_attempts(trials[1].id)] == [
            "abandoned",
            "succeeded",
        ]
    finally:
        store.close()
