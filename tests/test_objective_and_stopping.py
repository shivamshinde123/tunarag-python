import pytest

from tunarag.domain import MetricValue, ValueStatus
from tunarag.objective import Objective, ObjectiveDirection, ObjectiveTerm
from tunarag.stopping import CostBudget, MaxTrials, StopContext


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
