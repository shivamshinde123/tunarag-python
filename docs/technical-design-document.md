# TunaRAG Technical Design

## Lifecycle and scheduling

Implemented studies move from created to running then completed, with failed and cancelled
terminals; a separate stopping state may be added with orchestration. Trials support pending,
running, succeeded, failed, abandoned, and cancelled. Terminal states are immutable. Completed
studies cannot contain active trials. Retries create attempts instead of moving terminal
attempts backward. Trial, attempt, and event sequence numbers are monotonic and never reused.

The scheduler asks the strategy for capacity-sized candidates, validates them through the
search space, hashes canonical values, and reserves uniqueness in SQLite. The trial runner
prepares the adapter, executes bounded samples, evaluates outputs, aggregates objective and
usage, and cleans up under distinct timeout/cancellation boundaries.

The implemented scheduler reserves up to `concurrency` trials, executes them concurrently, then
sorts completed summaries by durable sequence before strategy observation. `MaxTrials` limits
reservations exactly. Cost/time conditions inspect committed snapshots and may overshoot by one
in-flight batch. Recovery finishes already reserved trials before new suggestions. Within each
trial, the finite evaluation dataset is materialized and executed through a semaphore capped by
`sample_concurrency`; outcomes are folded in dataset order. All observed usage is retained if
any sample fails, while partial metrics are discarded. Duplicate metric names within a sample
and the reserved `tunarag.objective` name remain invalid.

Configured callbacks implement async `on_event(StudyEvent)`. Dispatch occurs after commit and
follows durable event sequence. Retry-scheduled events are dispatched before sleeping. Callback
exceptions are isolated from optimization and recorded as `callback.failed` with source
sequence, callback index/type, and exception type; exception messages are omitted. Failure
events are not redispatched, preventing recursive storms. Resume begins callback delivery after
the historical event tail.

`LLMSearch` sends an immutable structured request to an injected provider and validates every
response as untrusted input through `SearchSpace.validate`. Attempts are bounded. Exhaustion
uses a stateless deterministic fallback derived from fallback seed and durable suggestion number,
which makes resume independent of hidden RNG state. Disabling fallback produces a structured
error containing only exception type names. Prior candidate observations are recursively
redacted at the provider boundary. Provider semantic configuration participates in resume when
it implements `fingerprint()`. Strategy-provider usage accounting remains an explicit extension
because the current strategy contract returns only a candidate.

## Retries and resume

Retry decisions use stage, error code, idempotency, attempt count, and provider hints.
Authentication, invalid configuration/output, and missing ground truth are nonretryable;
rate limits, transient networks, and provider 5xx responses are generally retryable. Exhausted
trial failure does not fail the study by default.

The implemented `RetryPolicy` retries structured errors explicitly marked retryable plus
timeouts and connection failures. Attempt numbers start at zero and every retry starts a new
leased attempt. Backoff is deterministic exponential delay capped by policy. A failed
retryable attempt commits its observed usage and terminal attempt state in one transaction,
while the trial remains running. Sample timeout wraps each adapter and evaluator call; trial
timeout wraps complete dataset execution. Cancellation is never converted into a retry.

Resume compares dataset, search-space, objective, adapter, evaluator, strategy, schema, and
cache fingerprints; abandons expired attempts; reconstructs budgets; replays terminal results;
and continues sequence numbers. Incompatibility requires an explicit fork.

This flow is implemented for created, running, and completed compatible studies. Failed and
cancelled studies are terminal. Recovery is scoped to one study, and unexpired attempt leases
produce a retryable `ResumeError`. Terminal summaries are rebuilt from metrics, append-only
usage, attempts, trial errors, and cache-hit events. Pending and recoverable trials execute
before new suggestions. The durable `study.stopping` event preserves the result stop reason.
Ordinary strategies receive successful observations in sequence order. Replay-aware strategies
receive every reserved candidate, including failed and unfinished trials, through the optional
`replay` method. `RandomSearch` verifies and advances seeded generator state.

The implemented store provides attempt leases, persisted abandonment, and a recoverable-trial
query. A terminal commit transaction writes metrics, append-only usage, terminal attempt state,
terminal trial state, and the corresponding ordered event. Validation failures roll the whole
transaction back. Strategy replay consumes ordered committed events only.

## Cache, objectives, and stopping

Cache keys use domain-separated SHA-256 over canonical semantic inputs and versions. The
implemented foundation stores bytes atomically in an independently versioned SQLite table with
namespace, format version, timestamps, privacy class, checksum, state, hit count, and quarantine
reason. Reads verify TTL and checksum before exposing bytes. The first corrupt read returns a
corrupt outcome and persists quarantine; later reads return quarantined. Expired and quarantined
entries remain inspectable until retention pruning. Partial/failed work is not cached without
an explicit safe negative-cache policy.

The optimizer cache payload is canonical JSON containing only payload version and aggregated
metrics. Objective scores are recomputed so objective weights can change without invalidating
evaluation work; cached usage is intentionally empty because result accounting describes the
current run. Cache keys include format version, dataset version, candidate, and adapter and
evaluator type names. Writes occur only after the durable successful trial commit. Cache read,
decode, and write failures append events and do not change trial success. Configurable component
fingerprints are included when a component implements `fingerprint()`; otherwise type identity
is used. Mandatory fingerprints for every custom component and TTL selection at the optimizer
boundary remain future work.

## Evaluator adapters

The core optimizer depends only on the `Evaluator` protocol. `MetricEvaluator` normalizes a
single sync or async scorer into that protocol and fingerprints callable identity. The optional
`RagasEvaluator` is a boundary adapter, not an engine dependency: it imports RAGAS lazily, creates
one `SingleTurnSample` and one-row `EvaluationDataset` per engine sample, calls `aevaluate`, and
maps numeric results to namespaced TunaRAG metrics. This preserves engine-owned sample
concurrency, timeout, retry, aggregation, and failure-isolation behavior.

An explicit sample mapper is required. TunaRAG never guesses fields from arbitrary adapter
outputs or examples, which prevents accidental disclosure and avoids coupling the core domain to
RAGAS schemas. Missing/nonfinite RAGAS scores are unavailable rather than zero. Integration
errors retain only exception types. RAGAS remains an optional `ragas` extra pinned to the 0.4
compatibility line; version-specific changes remain localized to `evaluators.py`.

## Dataset ingestion and identity

`EvaluationExample` is a normalized frozen boundary model. Text normalization is deliberately
minimal and meaning-preserving: UTF-8 decode, optional BOM removal, Unicode NFC, CR/CRLF to LF,
outer trim, and rejection of controls other than tab/newline. Metadata accepts only finite JSON
types and is recursively frozen. File loaders use the standard library and convert only through a
declared `DatasetFieldMap`; they do not infer schemas from content.

Missing sample IDs hash normalized semantic fields in the `tunarag:example-id:v1` domain.
Dataset versions hash schema version plus ordered semantic examples in the
`tunarag:dataset:v1` domain. Deterministic split assignment converts the first 64 hash bits of
seed plus example/group identity to a fraction and applies configured thresholds. Split
selection produces a new dataset version. Source paths and ingestion timestamps never affect
identity; malformed record values never enter public error messages.

Objectives preserve direction, normalization, weight, coverage, and confidence. Unknown values
do not become zero. Stop rules evaluate a committed snapshot with deterministic precedence and
retain the winning reason. Planned rules cover trial count, score target, cost, wall time, no
improvement, search exhaustion, failure threshold, and cancellation.

## Open decisions

Python 3.10 structured concurrency, sortable public IDs, sample checkpoint stability, and a
future size threshold for external cache payload files remain `TBD`.

## Result reporting and export

`OptimizationResult` remains an immutable in-memory report and adds derived views rather than
persisting duplicate rankings. Objective ranking filters to successful trials with available
scores, sorts descending, and uses durable trial sequence for deterministic ties. Metric leaders
apply caller-selected direction to available values only. Formal Pareto dominance is deferred
because V0.1 has one configured scalar objective and does not define missing-value dominance.

JSON report schema version 1 preserves nested trial metrics and usage. CSV is intentionally
lossier and rectangular: one row per trial, JSON candidate cell, flattened usage totals, and
lexically ordered dynamic metric columns. Both formats recurse through the central redactor, so
`Secret` values and sensitive keys never leave the result boundary. Exports do not include cache
payloads, provider prompts, raw dataset examples, or exception messages beyond already bounded
trial error summaries.
