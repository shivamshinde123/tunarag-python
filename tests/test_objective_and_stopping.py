import pytest

from tunarag.domain import MetricValue, ValueStatus
from tunarag.objective import Objective, ObjectiveDirection, ObjectiveTerm
from tunarag.stopping import (
    CostBudget,
    MaxFailures,
    MaxTrials,
    NoImprovement,
    StopContext,
    TargetScore,
    TimeBudget,
)


def test_objective_normalizes_and_respects_metric_direction() -> None:
    objective = Objective(
        (
            ObjectiveTerm("quality", weight=2, minimum=0, maximum=1),
            ObjectiveTerm(
                "latency", weight=1, direction=ObjectiveDirection.MINIMIZE, minimum=0, maximum=100
            ),
        )
    )

    result = objective.evaluate((MetricValue("quality", 0.8), MetricValue("latency", 25)))

    assert result.score == pytest.approx(2 * 0.8 + 0.75)
    assert result.status is ValueStatus.EXACT


def test_objective_propagates_estimated_and_unavailable_values() -> None:
    objective = Objective((ObjectiveTerm("cost", direction=ObjectiveDirection.MINIMIZE),))

    estimated = objective.evaluate((MetricValue("cost", 2, ValueStatus.ESTIMATED),))
    unavailable = objective.evaluate(())

    assert estimated.status is ValueStatus.ESTIMATED
    assert unavailable.score is None
    assert unavailable.status is ValueStatus.UNAVAILABLE


def test_stop_conditions_apply_declared_budget_policy() -> None:
    context = StopContext(completed_trials=3, exact_cost=0.8, estimated_cost=0.4)

    assert MaxTrials(3).should_stop(context)
    assert CostBudget(1.0).should_stop(context)
    assert not CostBudget(1.0, count_estimated=False).should_stop(context)

    with pytest.raises(ValueError, match="at least one"):
        MaxTrials(0)


def test_score_time_and_failure_stop_conditions() -> None:
    context = StopContext(
        completed_trials=4,
        elapsed_seconds=12.0,
        successful_trials=2,
        failed_trials=2,
        objective_scores=(0.4, None, 0.8, None),
    )

    assert TargetScore(0.75).should_stop(context)
    assert not TargetScore(0.9).should_stop(context)
    assert TimeBudget(10).should_stop(context)
    assert MaxFailures(2).should_stop(context)
    assert not MaxFailures(2, consecutive=True).should_stop(context)
    assert MaxFailures(1, consecutive=True).should_stop(context)


def test_no_improvement_counts_failures_and_respects_delta_and_warmup() -> None:
    context = StopContext(
        completed_trials=5,
        successful_trials=4,
        failed_trials=1,
        objective_scores=(0.5, 0.55, None, 0.56, 0.56),
    )

    assert NoImprovement(3, min_delta=0.1).should_stop(context)
    assert not NoImprovement(5, min_delta=0.1).should_stop(context)
    assert not NoImprovement(1, warmup_trials=6).should_stop(context)


def test_stop_context_and_condition_validation() -> None:
    with pytest.raises(ValueError, match="history"):
        StopContext(2, objective_scores=(1.0,))
    with pytest.raises(ValueError, match="finite"):
        StopContext(0, elapsed_seconds=float("inf"))
    with pytest.raises(ValueError, match="positive integer"):
        MaxFailures(True)
    with pytest.raises(ValueError, match="positive integer"):
        NoImprovement(0)
    with pytest.raises(ValueError, match="finite"):
        TargetScore(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        CostBudget(float("inf"))
    with pytest.raises(ValueError, match="at least one"):
        MaxTrials(True)
