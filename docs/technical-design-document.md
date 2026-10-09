# TunaRAG Technical Design

> V0.3 scope: TunaRAG tunes genuine LangChain runnables, compiled LangGraph graphs, and Google ADK 2.x runners through official adapters. Handwritten RAG adapters are unsupported. Evaluators, search strategies, and callbacks remain extensible.

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

Event dispatch acknowledges only the snapshot entries it actually visits. Events
committed while a callback awaits remain after the cursor and are delivered by the
next dispatch. Advancing directly to the latest durable event would lose concurrent
trial completions and their optional tracking projections.

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
`replay` method. `RandomSearch` verifies and advances seeded generator state, skipping
draws equal to previously replayed candidates because duplicate suggestions never
reserve a second trial. An unseen mismatch still fails replay; scanning is bounded
to 10,000 draws per reserved candidate to prevent unbounded recovery work.

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

## Synthetic generation

Synthetic generation is a typed provider boundary, not a provider SDK integration. The builder
derives a domain-separated seed per document, bounds concurrent calls, gathers in source order,
and validates exact response cardinality, span ranges, confidence, and usage. Generated IDs hash
document ID, output index, query, answer, and provenance. Every example is labeled synthetic and
unreviewed. Source text is transmitted only because the caller explicitly supplies it; exception
messages and generated content never enter errors or events.

Objectives preserve direction, normalization, weight, coverage, and confidence. Unknown values
do not become zero. Stop rules evaluate a committed snapshot with deterministic precedence and
retain the winning reason. Implemented rules cover trial count, score target, cost, wall time,
no improvement, search exhaustion, and total/consecutive failure thresholds. Cancellation is an
external async control path rather than a polling rule.

`StopContext.objective_scores` follows durable trial sequence and uses `None` for failed trials.
`NoImprovement` establishes the first available score as baseline and resets patience only when a
later score exceeds best plus `min_delta`; failures consume patience. Concurrent scheduling checks
conditions between committed batches, so every snapshot rule may overshoot by at most the active
batch. All built-in rule parameters participate in the study configuration hash.

## Open decisions

Python 3.10 structured concurrency, sortable public IDs, sample checkpoint stability, and a
future size threshold for external cache payload files remain `TBD`.

## LangChain and LangGraph runnable design

The V0.2 adapters depend structurally on `ainvoke` and do not import framework classes. A fixed
runnable supports cheap runtime configuration; `factory(candidate)` supports construction-time
parameters. Exactly one source is required and every resolved object is validated before use.
For canonical examples, the default input is `{"question": query}` and the default config is
`{"configurable": candidate.parameters}`. Each mapping stage is replaceable independently.

Raw output is preserved unless an output mapper is supplied, ensuring evaluators can inspect
answers, contexts, messages, and graph state. Standard message usage is discovered recursively
with object-identity deduplication; malformed or negative token counts are ignored rather than
invented. An explicit usage mapper replaces discovery. Invocation latency is always appended as
a separate framework usage record. Provider exceptions are not wrapped here because the engine
already owns retry classification, timeout conversion, redaction, and failure isolation.

Fingerprinting includes callable/type names and explicit caller identity but never serializes
framework internals. This avoids credential leakage and unstable hashes. Users must provide
`identity` when two same-type pipelines have different behavior not represented by candidates or
mapper identities.

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

## MLflow event mirror

MLflow is a projection of committed SQLite state, never an authority. `MLflowCallback` consumes
the same ordered post-commit events as user callbacks. It gathers trial records and metrics on
the event-loop thread, then calls the blocking low-level MLflow client through `asyncio.to_thread`;
the SQLite connection never crosses threads. One in-memory run ID is retained per study for the
callback lifetime. Terminal study events map to MLflow terminal statuses.

The mirror logs only redacted candidate parameters, numeric metrics, durable sequence, and
lifecycle tags. Keys are normalized and hash-suffixed when unsupported characters or length
require a change. A missing extra raises `MissingOptionalDependencyError`, which callback
isolation records without failing optimization. Historical events are not replayed on resume, so
cross-process continuation intentionally starts a separate run unless a future durable run-ID
mapping is introduced.
