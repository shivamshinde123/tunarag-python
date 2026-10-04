# TunaRAG API Specification

## Status

This is the living V0.1 Python API contract. The companion
`01_API_Specification.docx` contains the full design narrative. Implemented and planned APIs
are separated below so design commitments are not mistaken for runtime behavior.

## Implemented surface

`tunarag` exports `Candidate`, `MetricValue`, `UsageRecord`, `Secret`, `ValueStatus`, objective
types, `MaxTrials`, `CostBudget`, `RetryPolicy`, `SQLiteStore`, study/trial records, and the
cache types `CacheKey`, `CacheEntry`, `CacheLookup`, `CacheLookupStatus`, `CachePrivacy`, and
`SQLiteCache`, search-space types, `RandomSearch`, `LLMSearch`, `LLMSuggestionRequest`, and
`LLMSearchProvider`. Extension protocols also live in `tunarag.contracts`.
The evaluator surface includes `MetricEvaluator`, `MetricScorer`, `RagasEvaluator`, and
`RagasSampleMapper`.

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

## Search strategies

`SearchSpace.validate(parameters)` requires exact keys and validates integer, float, and
categorical bounds. `SearchSpace.describe()` produces structured provider input rather than a
package-owned natural-language prompt. `RandomSearch` remains seeded and isolated.

`LLMSearch(space, provider, max_suggestion_attempts=3, fallback_seed=0, fallback=True)` calls an
injected async `LLMSearchProvider.suggest(LLMSuggestionRequest)`. Each provider result is treated
as untrusted data and validated against the search space. Provider exceptions and invalid
outputs consume a bounded attempt without exposing exception messages. Exhaustion either samples
a deterministic fallback keyed by suggestion number or raises redacted `SearchSpaceError` when
fallback is disabled. Requests include provider-safe prior observations; sensitive keys and
`Secret` values are redacted recursively. Replay advances suggestion numbering and restores
observation context. The strategy fingerprint includes search space, provider type and optional
provider fingerprint, limits, fallback seed, and fallback policy.

Provider-call token/cost accounting is not yet part of the `SearchStrategy.suggest` return
contract; providers should retain their own usage until the planned strategy-usage extension is
implemented. This limitation is explicit rather than reporting unknown search cost as zero.

## Evaluators

`MetricEvaluator(name, scorer, status=ValueStatus.EXACT)` adapts one synchronous or asynchronous
numeric callable to the evaluator protocol. A finite numeric result becomes one metric. `None`,
NaN, and infinity become an unavailable metric with zero coverage. Booleans and nonnumeric
values raise `EvaluationError`. The reserved `tunarag.objective` metric name is rejected.

`RagasEvaluator(metrics, sample_mapper, metric_prefix="ragas.", llm=None, embeddings=None,
raise_exceptions=False)` is available without importing RAGAS at package import time. The caller
must explicitly map `(output, example)` to keyword fields accepted by RAGAS `SingleTurnSample`;
this mapping is the privacy boundary controlling which application data reaches evaluator
providers. Each call builds a one-row `EvaluationDataset`, invokes async `ragas.aevaluate` with
progress disabled, and converts the one-row score mapping into `MetricValue` observations.
Missing/nonfinite scores are unavailable with zero coverage. Provider exception messages are not
included in public errors. Install with `pip install 'tunarag-python[ragas]'`. The supported V0.1
integration range is RAGAS `>=0.4,<0.5`; TunaRAG does not configure provider credentials.

Both built-ins implement semantic fingerprints. Callable identity uses module and qualified name;
users should avoid anonymous lambdas for persisted studies that must remain compatible across
code moves. RAGAS metric, LLM, and embedding objects can implement `Fingerprintable` to include
behavioral configuration without exposing secrets.

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

`callbacks=[...]` accepts objects implementing async
`on_event(event: StudyEvent) -> None`. Events are delivered only after their database
transaction commits and in durable sequence order. New studies deliver their full live event
stream; resume starts after the existing event tail and does not replay historical callback
notifications. Retry scheduling is delivered before backoff. A callback exception never changes
the trial/study result: TunaRAG appends a redacted `callback.failed` event with callback identity,
source sequence, and exception type, then continues other callbacks. Diagnostic callback events
are not recursively dispatched.

`aoptimize` is authoritative. The implemented slice runs bounded trial batches, aggregates each
metric by arithmetic mean across samples, preserves coverage and confidence, computes a
benefit-oriented objective, isolates adapter/evaluator/objective failures, persists partial
usage on failure, and observes committed successful trials. Each retry creates a new durable
attempt and appends usage from failed attempts before sleeping. Adapter and evaluator calls use
the sample timeout; the complete candidate execution uses the trial timeout. Duplicate
candidates are rejected; a bounded run of duplicates stops as search exhaustion. `optimize`
owns an event loop only when none is active and otherwise raises
`SyncInAsyncContextError`.

The optimizer schedules up to `Settings.concurrency` trials per batch and executes up to
`Settings.sample_concurrency` samples within each trial. Trial outcomes and strategy
observations are applied in durable sequence order after a batch, regardless of completion
timing. `MaxTrials` is a hard reservation cap; snapshot-based cost or time stop conditions can
overshoot by work already in the active batch. Evaluation examples are currently materialized
once per trial before bounded sample tasks start, so callers should keep V0.1 evaluation splits
finite and memory-appropriate.

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
came from cache. `InMemoryDataset` provides a repeatable versioned dataset. Study forking,
streaming sample windows, and mandatory custom-component fingerprints remain planned V0.1 work.

## Versioning

The distribution is `tunarag-python`; the import package is `tunarag`. Public APIs follow
semantic versioning. SQLite schemas and cache formats have independent versions and explicit
migration or invalidation rules.
