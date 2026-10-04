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
from .dataset import InMemoryDataset
from .domain import Candidate, MetricValue, Secret, UsageRecord, ValueStatus
from .engine import Optimizer
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
from .result import OptimizationResult, TrialSummary, UsageSummary
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
    "InMemoryDataset",
    "MaxTrials",
    "MetricValue",
    "MissingOptionalDependencyError",
    "Objective",
    "ObjectiveDirection",
    "ObjectiveResult",
    "ObjectiveTerm",
    "OptimizationResult",
    "Optimizer",
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
    "TrialSummary",
    "TrialStatus",
    "TunaRAGError",
    "UsageRecord",
    "UsageSummary",
    "ValueStatus",
    "__version__",
]

__version__ = "0.1.0.dev0"
