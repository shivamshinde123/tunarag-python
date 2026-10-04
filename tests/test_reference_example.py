import json
from pathlib import Path

from examples.quickstart import run


def test_reference_quickstart_writes_complete_reports(tmp_path: Path) -> None:
    report_path = run(tmp_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["study_status"] == "completed"
    assert report["counts"] == {"trials": 3, "successful": 3, "failed": 0}
    assert report["best_trial_id"] is not None
    assert (tmp_path / "trials.csv").is_file()
    assert (tmp_path / "experiments.db").is_file()
