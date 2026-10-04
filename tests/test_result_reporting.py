import csv
import json

from tunarag import (
    Candidate,
    MetricValue,
    ObjectiveDirection,
    ObjectiveResult,
    OptimizationResult,
    Secret,
    TrialSummary,
    UsageRecord,
    UsageSummary,
    ValueStatus,
)
from tunarag.store import StudyStatus, TrialStatus


def _result() -> OptimizationResult:
    trials = (
        TrialSummary(
            id="trial-1",
            sequence=1,
            candidate=Candidate({"model": "small", "api_key": Secret("private")}),
            status=TrialStatus.SUCCEEDED,
            metrics=(MetricValue("quality", 0.8), MetricValue("latency", 2.0)),
            usage=(UsageRecord("generator", 10, 5, 0.1, 2.0),),
            objective=ObjectiveResult(0.8, ValueStatus.EXACT),
            attempts=1,
        ),
        TrialSummary(
            id="trial-2",
            sequence=2,
            candidate=Candidate({"model": "large"}),
            status=TrialStatus.SUCCEEDED,
            metrics=(MetricValue("quality", 0.9), MetricValue("latency", 4.0)),
            usage=(UsageRecord("generator", 20, 10, 0.2, 4.0, ValueStatus.ESTIMATED, "v1"),),
            objective=ObjectiveResult(0.9, ValueStatus.ESTIMATED),
            attempts=2,
            cached=True,
        ),
        TrialSummary(
            id="trial-3",
            sequence=3,
            candidate=Candidate({"model": "broken"}),
            status=TrialStatus.FAILED,
            metrics=(),
            usage=(),
            objective=None,
            attempts=1,
            error="adapter failed: RuntimeError",
        ),
    )
    return OptimizationResult(
        study_id="study-1",
        study_status=StudyStatus.COMPLETED,
        stop_reason="MaxTrials",
        trials=trials,
        best_trial=trials[1],
        usage=UsageSummary(30, 15, 0.1, 0.2, 6.0, ValueStatus.ESTIMATED),
    )


def test_result_ranking_metric_lookup_and_leaders() -> None:
    result = _result()

    assert [trial.id for trial in result.ranked_trials] == ["trial-2", "trial-1"]
    assert result.metric_names == ("latency", "quality")
    assert result.trials[0].metric("quality") == MetricValue("quality", 0.8)
    assert result.trials[2].metric("quality") is None
    assert [
        trial.id
        for trial in result.metric_leaders("latency", direction=ObjectiveDirection.MINIMIZE)
    ] == ["trial-1", "trial-2"]


def test_json_report_is_deterministic_and_redacted(tmp_path) -> None:
    result = _result()

    first = result.to_json()
    second = result.to_json()
    document = json.loads(first)

    assert first == second
    assert "private" not in first
    assert document["trials"][0]["candidate"]["api_key"] == "***redacted***"
    assert document["counts"] == {"failed": 1, "successful": 2, "trials": 3}
    path = result.write_json(tmp_path / "result.json")
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_csv_report_flattens_trials_metrics_and_usage(tmp_path) -> None:
    result = _result()

    path = result.write_csv(tmp_path / "result.csv")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 3
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["usage_status"] == "exact"
    assert rows[0]["metric.quality.value"] == "0.8"
    assert rows[0]["exact_cost"] == "0.1"
    assert rows[1]["estimated_cost"] == "0.2"
    assert rows[2]["metric.quality.value"] == ""
    assert "private" not in path.read_text(encoding="utf-8")
