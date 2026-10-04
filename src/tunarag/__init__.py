"""Public package for typed RAG configuration optimization."""

from .domain import Candidate, MetricValue, Secret, UsageRecord, ValueStatus
from .objective import Objective, ObjectiveDirection, ObjectiveResult, ObjectiveTerm
from .stopping import CostBudget, MaxTrials, StopContext
from .store import SQLiteStore, StudyRecord, TrialRecord, TrialStatus

__all__ = [
    "Candidate",
    "CostBudget",
    "MaxTrials",
    "MetricValue",
    "Objective",
    "ObjectiveDirection",
    "ObjectiveResult",
    "ObjectiveTerm",
    "Secret",
    "StopContext",
    "SQLiteStore",
    "StudyRecord",
    "TrialRecord",
    "TrialStatus",
    "UsageRecord",
    "ValueStatus",
    "__version__",
]

__version__ = "0.1.0.dev0"
