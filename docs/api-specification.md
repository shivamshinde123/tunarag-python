# TunaRAG API Specification

## Status

This is the living V0.1 Python API contract. The companion
`01_API_Specification.docx` contains the full design narrative. Implemented and planned APIs
are separated below so design commitments are not mistaken for runtime behavior.

## Implemented surface

`tunarag` exports `Candidate`, `MetricValue`, `UsageRecord`, `Secret`, `ValueStatus`, objective
types, `MaxTrials`, `CostBudget`, `RetryPolicy`, `SQLiteStore`, study/trial records, and the
cache types `CacheKey`, `CacheEntry`, `CacheLookup`, `CacheLookupStatus`, `CachePrivacy`, and
`SQLiteCache`. Search-space types and `RandomSearch` are currently imported from
`tunarag.search`; extension protocols live in `tunarag.contracts`.

`Candidate` requires a nonempty parameter mapping. Metrics and usage retain `exact`,
`estimated`, or `unavailable` provenance. `Objective.evaluate` combines configured terms.
`SQLiteStore` initializes or migrates experiment schema version 2. It creates and transitions
studies; atomically reserves unique ordered trials; starts, finishes, and recovers leased
attempts; atomically commits terminal metrics, usage, attempt state, trial state, and event;
lists replayable trials, attempt history, metrics, usage, recoverable work, and ordered events;
and closes its connection. Only running studies reserve trials. Terminal states are immutable. Unknown IDs
raise `KeyError`; invalid transitions raise `ValueError`.

`CacheKey.from_parts(namespace, *parts, format_version=1)` creates secret-safe canonical
identity. `SQLiteCache.put` atomically stores bytes with privacy and optional positive TTL.
`SQLiteCache.get` returns explicit hit, miss, expired, corrupt, or quarantined status; only a
verified hit contains payload bytes. `delete` removes one key, while `prune` removes expired
entries and optionally quarantined entries. Cache metadata and payloads survive reopen.

`Settings.resolve` applies defaults, an explicitly selected `[tunarag]` TOML table, known
`TUNARAG_` variables, and explicit overrides in ascending precedence. It never loads `.env`,
reads provider credentials, or creates directories. `Settings.as_dict` is safe to persist.

`RetryPolicy(max_retries=2, sample_timeout_seconds=60.0,
trial_timeout_seconds=300.0, base_delay_seconds=0.5,
max_delay_seconds=30.0)` validates bounded attempts and deterministic capped exponential
backoff. `None` disables an individual timeout when constructing the policy directly. Known
retryable failures are structured `TunaRAGError` values marked `retryable`, `TimeoutError`, and
`ConnectionError`; arbitrary exceptions are nonretryable.

Public package errors derive from `TunaRAGError` and expose stable `ErrorCode`, message, stage,
retryability, and recursively redacted structured details. Implemented subclasses cover
configuration, search space, adapter, evaluation, store, resume, budget, optional dependency,
and sync-in-async failures. Low-level domain values still raise `ValueError` or `TypeError`;
unknown trial IDs raise `KeyError`; database constraints raise `sqlite3.IntegrityError` until
their package-boundary translations are implemented.

## Optimizer entry point

```python
optimizer = Optimizer(
    adapter=adapter,
    strategy=RandomSearch(search_space, seed=42),
    evaluators=evaluators,
    objective=objective,
    store=store,
    cache=cache,
    settings=settings,
    retry_policy=RetryPolicy(max_retries=2),
)
result = await optimizer.aoptimize(dataset, study_name="support-rag")
```

`aoptimize` is authoritative. The implemented slice runs sequential trials, aggregates each
metric by arithmetic mean across samples, preserves coverage and confidence, computes a
benefit-oriented objective, isolates adapter/evaluator/objective failures, persists partial
usage on failure, and observes committed successful trials. Each retry creates a new durable
attempt and appends usage from failed attempts before sleeping. Adapter and evaluator calls use
the sample timeout; the complete candidate execution uses the trial timeout. Duplicate
candidates are rejected; a bounded run of duplicates stops as search exhaustion. `optimize`
owns an event loop only when none is active and otherwise raises
`SyncInAsyncContextError`.

When a cache is supplied, `CachePolicy` controls reads and writes. Evaluation cache keys include
the payload format, dataset version, canonical candidate, and adapter/evaluator identities.
Components implementing `Fingerprintable.fingerprint()` contribute semantic configuration;
other custom components are identified by type only.
Hits restore aggregate metrics, recompute the current objective, incur no current-run usage,
and set `TrialSummary.cached=True`. Only successful uncached metrics are written, after the
trial commit. Cache I/O or semantic-decoding failures produce durable diagnostic events and
fall back to execution; they do not fail the trial. Custom components should implement a stable,
secret-safe fingerprint when behavior can change without changing the Python type.

`await optimizer.aresume(dataset, study_id=...)` is the authoritative resume entry point;
`optimizer.resume(...)` is its sync wrapper and rejects an active event loop. Resume requires a
matching configuration hash, abandons expired attempts only in the selected study, rejects live
leases with retryable `ResumeError`, reconstructs all terminal summaries and usage, replays
successful trials into the strategy, and continues pending/recoverable work. Compatible
completed studies load without adapter/evaluator execution. Failed and cancelled studies are
terminal. The optional `ReplayableSearchStrategy.replay` contract lets a strategy distinguish
state restoration from live observation. Replay-aware strategies receive every durably reserved
candidate, including failed or unfinished trials; ordinary strategies receive only successful
observations. `RandomSearch` uses replay to verify candidates and advance its seeded generator.

`OptimizationResult` exposes study and stop status, all terminal trial summaries, best trial
and candidate, successful/failed subsets, aggregate usage with exact-versus-estimated cost,
and a valid no-success outcome. Each `TrialSummary` reports attempt count and whether metrics
came from cache. `InMemoryDataset` provides a repeatable versioned dataset. Callback dispatch,
concurrency, study forking, and mandatory custom-component fingerprints remain planned V0.1
work.

## Versioning

The distribution is `tunarag-python`; the import package is `tunarag`. Public APIs follow
semantic versioning. SQLite schemas and cache formats have independent versions and explicit
migration or invalidation rules.
