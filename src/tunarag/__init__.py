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
from .store import (
    AttemptRecord,
    AttemptStatus,
    PersistedUsageRecord,
    SQLiteStore,
    StudyEvent,
    StudyRecord,
    StudyStatus,
    TrialRecord,
    TrialStatus,
)

__all__ = [
    "AdapterError",
    "AttemptRecord",
    "AttemptStatus",
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
    "PersistedUsageRecord",
    "ResumeError",
    "Secret",
    "SearchSpaceError",
    "Settings",
    "SQLiteCache",
    "SQLiteStore",
    "StopContext",
    "StoreError",
    "StudyEvent",
    "SyncInAsyncContextError",
    "StudyRecord",
    "StudyStatus",
    "TrialRecord",
    "TrialStatus",
    "TunaRAGError",
    "UsageRecord",
    "ValueStatus",
    "__version__",
]

__version__ = "0.1.0.dev0"
