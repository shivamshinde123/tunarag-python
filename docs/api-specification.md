# TunaRAG API Specification

## Status

This is the living V0.1 Python API contract. The companion
`01_API_Specification.docx` contains the full design narrative. Implemented and planned APIs
are separated below so design commitments are not mistaken for runtime behavior.

## Implemented surface

`tunarag` exports `Candidate`, `MetricValue`, `UsageRecord`, `Secret`, `ValueStatus`, objective
types, built-in stop conditions, `RetryPolicy`, `SQLiteStore`, study/trial records, and the
cache types `CacheKey`, `CacheEntry`, `CacheLookup`, `CacheLookupStatus`, `CachePrivacy`, and
`SQLiteCache`, search-space types, `RandomSearch`, `LLMSearch`, `LLMSuggestionRequest`, and
`LLMSearchProvider`. Extension protocols also live in `tunarag.contracts`.
The evaluator surface includes `MetricEvaluator`, `MetricScorer`, `RagasEvaluator`, and
`RagasSampleMapper`.

## Evaluation datasets

`EvaluationExample` is the canonical immutable sample: ID, query, optional reference answer,
reference contexts, relevant document IDs, tags, JSON metadata, `DatasetSplit`, and a synthetic
flag. Text is normalized to Unicode NFC and LF line endings, with BOM/outer whitespace removed
and unsafe control characters rejected. IDs, queries, list entries, tags, and document IDs must
remain nonempty; tags and document IDs are unique. Metadata is recursively validated as finite
JSON data and deep-frozen.

`EvaluationDataset.from_records`, `.from_json`, `.from_jsonl`, and `.from_csv` normalize data via
`DatasetFieldMap`. Missing IDs are deterministic hashes of normalized semantic content. JSON and
JSONL require objects; CSV collection and metadata cells contain JSON arrays/objects. Duplicate
IDs, malformed values, empty datasets, and I/O failures raise redacted `DatasetError` values with
source location and exception type but no record contents. UTF-8 with an optional BOM is accepted.

The dataset version is a domain-separated SHA-256 hash over schema version, ordered normalized
examples, and split membership; paths and ingestion times are excluded. `with_splits(seed=0,
ratios=SplitRatios(), group_metadata_key=None)` deterministically assigns 80/10/10 optimize,
validation, and test splits by default. A group key keeps all examples sharing a string/integer
metadata value together. `select(split)` returns a nonempty split-specific dataset. The existing
`InMemoryDataset` remains for arbitrary user-defined examples and explicit external versions.

## Synthetic QA generation

`SyntheticDatasetBuilder(provider, samples_per_document=3, concurrency=4, seed=0,
generator_version="unspecified")` generates an `EvaluationDataset` from `SourceDocument` values.
Providers implement async `SyntheticQAProvider.generate(SyntheticGenerationRequest)` and return a
`SyntheticGenerationResponse` containing exactly the requested number of typed `SyntheticQA`
items plus `UsageRecord` values. TunaRAG owns bounded document concurrency and validates response
type, count, usage, confidence, and half-open `SourceSpan` bounds. Provider exception messages are
discarded; `DatasetError` retains only document ID and exception type.

Each generated example is marked synthetic and stores source document ID/metadata, spans,
provider type and optional fingerprint, generator version, deterministic per-document seed,
confidence, and `unreviewed` status. Supporting span text becomes reference context; the whole
document is used when no spans are supplied. IDs and dataset versions are deterministic for
identical validated outputs. Provider credentials, prompts, caching, and retry policy remain
provider-owned in V0.1; exact/estimated generation usage is returned separately.

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

`StopContext` carries committed totals, elapsed time, success/failure counts, and objective score
history in durable trial order. Built-in conditions are `MaxTrials(limit)`, `CostBudget(limit,
count_estimated=True)`, `TimeBudget(seconds)`, `TargetScore(target)`, `MaxFailures(limit,
consecutive=False)`, and `NoImprovement(patience, min_delta=0, warmup_trials=1)`. Objective scores
are benefit-oriented, so targets and improvements always use larger-is-better comparisons.
Failures count as non-improving trials; consecutive failures are represented by trailing missing
objective scores. Every built-in condition fingerprints its parameters for resume compatibility.

Public package errors derive from `TunaRAGError` and expose stable `ErrorCode`, message, stage,
retryability, and recursively redacted structured details. Implemented subclasses cover
configuration, search space, dataset, adapter, evaluation, store, resume, budget, optional dependency,
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

## Optional MLflow mirror

`tunarag.integrations.MLflowCallback(store, experiment_id="0", tracking_uri=None, tags=None,
client=None)` implements `EventCallback`. Install with `pip install 'tunarag-python[mlflow]'`;
V0.1 supports MLflow `>=3,<4`. Supplying a client enables testing or custom authentication without
importing MLflow. A callback instance creates one MLflow run per study encountered in the current
process. On terminal trial events it reads already committed candidates and metrics from SQLite,
logs redacted candidate parameters under sequence-qualified names, logs metrics at the durable
trial sequence step, and records trial status. Study completion/failure/cancellation terminates
the mirror run as `FINISHED`, `FAILED`, or `KILLED`.

SQLite remains authoritative. Local committed state is read before MLflow network calls, and the
blocking low-level client runs in a worker thread without sharing the SQLite connection there.
MLflow failures follow normal callback isolation: they append `callback.failed` diagnostics and
never alter trial or study outcomes. Resume callback delivery does not replay historical events,
so a newly attached callback creates a new run for resumed events rather than reconstructing the
old mirror. Sensitive keys and `Secret` values are redacted; MLflow keys are deterministically
normalized to its supported character and length limits.

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
overshoot by work already in the active batch. Score, stagnation, and failure rules have the same
bounded batch overshoot; use `concurrency=1` when exact immediate stopping is required.
Evaluation examples are currently materialized
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
and a valid no-success outcome. `ranked_trials` orders successful available objectives from best
to worst with trial sequence as the stable tie-breaker. `metric_names` returns a lexical union;
`metric_leaders(name, direction=...)` independently ranks available values for one metric.
`TrialSummary.metric(name)` returns one observation or `None`.

`as_dict()` returns report schema version 1 with summary counts, aggregate usage, redacted
candidates, per-trial metrics, raw usage records, objective, attempts, cache state, and bounded
error text. `to_json()` is deterministic UTF-8-capable JSON; `write_json(path)` adds a final
newline. `write_csv(path)` emits one trial per row, a redacted canonical candidate JSON cell,
trial/objective/attempt/cache fields, per-trial usage totals, and three columns per metric for
value, status, and coverage. Writers replace existing files but do not create parent directories.
`Secret` values and sensitive mapping keys are recursively redacted in both formats.

Each `TrialSummary` reports attempt count and whether metrics came from cache. `InMemoryDataset`
provides a repeatable versioned dataset. Formal Pareto/frontier reporting remains post-V0.1;
V0.1 ranks the configured scalar objective and individual metrics. Study forking, streaming
sample windows, and mandatory custom-component fingerprints remain planned V0.1 work.

## Versioning

The distribution is `tunarag-python`; the import package is `tunarag`. Public APIs follow
semantic versioning. SQLite schemas and cache formats have independent versions and explicit
migration or invalidation rules.
