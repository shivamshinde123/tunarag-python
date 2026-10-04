"""Public package for typed RAG configuration optimization."""

from .cache import (
    CacheEntry,
    CacheKey,
    CacheLookup,
    CacheLookupStatus,
    CachePrivacy,
    SQLiteCache,
)
from .config import CachePolicy, Settings
from .domain import Candidate, MetricValue, Secret, UsageRecord, ValueStatus
from .errors import (
    AdapterError,
    BudgetError,
    ConfigurationError,
    ErrorCode,
    EvaluationError,
    MissingOptionalDependencyError,
    ResumeError,
    SearchSpaceError,
    StoreError,
    SyncInAsyncContextError,
    TunaRAGError,
)
from .objective import Objective, ObjectiveDirection, ObjectiveResult, ObjectiveTerm
from .stopping import CostBudget, MaxTrials, StopContext
from .store import SQLiteStore, StudyRecord, TrialRecord, TrialStatus

__all__ = [
    "AdapterError",
    "BudgetError",
    "CacheEntry",
    "CacheKey",
    "CacheLookup",
    "CacheLookupStatus",
    "CachePolicy",
    "CachePrivacy",
    "Candidate",
    "ConfigurationError",
    "CostBudget",
    "ErrorCode",
    "EvaluationError",
    "MaxTrials",
    "MetricValue",
    "MissingOptionalDependencyError",
    "Objective",
    "ObjectiveDirection",
    "ObjectiveResult",
    "ObjectiveTerm",
    "ResumeError",
    "Secret",
    "SearchSpaceError",
    "Settings",
    "SQLiteCache",
    "SQLiteStore",
    "StopContext",
    "StoreError",
    "SyncInAsyncContextError",
    "StudyRecord",
    "TrialRecord",
    "TrialStatus",
    "TunaRAGError",
    "UsageRecord",
    "ValueStatus",
    "__version__",
]

__version__ = "0.1.0.dev0"
