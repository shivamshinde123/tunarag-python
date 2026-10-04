# TunaRAG Decision Log

Decisions are chronological. Superseding entries preserve the original reasoning.

## 2026-10-03 Naming

Use TunaRAG as the product, `tunarag-python` as the repository and Python distribution, and
`tunarag` as the import package. A TypeScript implementation will use a separate repository.

## 2026-10-03 Runtime boundary

Build async-first internals with a synchronous wrapper. Users supply a `RAGAdapter`; TunaRAG
does not own their production RAG. Keep RAGAS, MLflow, providers, LangChain, and LlamaIndex as
optional edge integrations.

## 2026-10-03 Values and identity

Use frozen slotted dataclasses for core values, protocols for extension points, canonical JSON
and domain-separated SHA-256 for identity, and omit secret values from identity mappings.

## 2026-10-03 Search and accounting

Random search owns an isolated seeded random stream. Objective and usage results retain
`exact`, `estimated`, or `unavailable` status; unknown values never silently become zero.

## 2026-10-03 Persistence

Use standard-library `sqlite3` and explicit transactions as V0.1 authority. MLflow is an
optional mirror. Defer an ORM until a second relational backend justifies it.

## 2026-10-03 Cross-platform quality gate

Run formatting, linting, strict typing, tests, and package builds on Linux and Windows with the
oldest and newest supported Python versions. Force LF for source and documentation so local
Git settings do not create formatter-only differences.

## 2026-10-03 SQLite cache foundation

Store foundation cache payloads as SQLite BLOBs with an independently versioned schema,
canonical namespaced keys, SHA-256 payload checksums, explicit privacy metadata, and persisted
expiry/quarantine states. Return explicit lookup outcomes and never return unverified bytes.

This keeps V0.1 atomic and zero-infrastructure. External payload files remain a later option if
measured payload sizes justify the additional atomic-write and cleanup complexity.

## 2026-10-03 Explicit configuration and structured errors

Resolve only defaults, explicitly selected TOML, known `TUNARAG_` variables, and explicit
overrides, in that precedence order. Do not auto-load `.env`, provider credentials, or a hidden
environment mode. Keep settings immutable and provider-secret free.

Represent package-boundary failures with stable codes, stage, retryability, and recursively
redacted details. Keep low-level validation exceptions until the boundary that can add useful
context, rather than obscuring their causes prematurely.

## 2026-10-03 Experiment schema version 2

Migrate version-1 databases transactionally and add guarded study/trial lifecycle state,
unique per-study candidates, leased attempts, aggregate metrics, append-only usage, and ordered
events. Allocate trial and event sequences under immediate write transactions. Commit terminal
attempt state, observations, trial state, and event atomically.

Keep a retryable trial running after a failed or abandoned attempt; each retry receives a new
monotonic attempt number. Resume first abandons expired leases, then queries running trials with
no active attempt. This separates execution attempts from the semantic candidate trial.

## 2026-10-03 Sequential optimizer baseline

Make `Optimizer.aoptimize` the authoritative entry point and provide `optimize` only when no
event loop is active. Deliver a sequential end-to-end path before adding concurrency so adapter,
evaluation, objective, persistence, isolation, and stopping semantics are testable without
scheduler races.

Aggregate repeated sample metrics by name using arithmetic mean, explicit coverage, and the
least-confident observed status. Persist partial usage when a trial fails, but do not expose raw
third-party exception messages. Observe only committed successful trials under the current
strategy contract. Add retries, cache use, replay/resume, callbacks, and concurrency in focused
follow-up branches.

## 2026-10-04 Retry, timeout, and evaluation-cache semantics

Treat a trial as one semantic candidate and each execution as a durable attempt. Retry only
explicitly transient structured failures, timeouts, and connection failures; use deterministic
capped exponential backoff. Persist each failed attempt and its observed usage atomically so
retries never erase real spend. Apply a timeout to each adapter/evaluator call and a separate
deadline to the complete candidate execution.

Cache only successfully aggregated evaluation metrics, never objective scores or usage. Read
and write according to the explicit cache policy, recompute the current objective on hits, and
record zero current-run usage for cached work. Write only after the authoritative trial commit.
Treat cache transport, corruption, or semantic-decoding problems as observable misses rather
than trial failures. V0.1 keys use dataset version, candidate, payload format, and component
type names; richer component configuration fingerprints remain future work.

## 2026-10-04 Compatible resume and strategy replay

Expose separate `aresume` and `resume` entry points rather than overloading new-study creation.
Resume requires the same semantic configuration hash, preserves failed/cancelled terminality,
and refuses unexpired leases to avoid duplicate execution. It scopes expired-attempt recovery
to the requested study, reconstructs terminal results and budgets from SQLite, replays committed
successes in sequence, and finishes reserved work before requesting new candidates. Completed
studies are reloadable without provider calls. Persist the winning stop reason as an ordered
event so a reloaded result remains meaningful.

Allow strategies to implement a distinct replay hook and components to contribute optional
semantic fingerprints. `RandomSearch` fingerprints its search space and seed, then verifies and
advances generator state during replay. Components without a fingerprint retain type-only
identity in V0.1. Store candidate payloads with a reversible, number-preserving, secret-safe JSON
serializer while retaining the existing canonical serializer exclusively for hashes.

## 2026-10-04 Post-commit callback dispatch

Make callbacks async objects consuming durable `StudyEvent` records. Dispatch only after SQLite
commits and preserve event sequence, including notifying retry scheduling before backoff. Do not
replay historical callback notifications on resume; callers can query the event store when they
want history. Isolate callback exceptions from authoritative optimization state and append a
redacted `callback.failed` diagnostic containing no exception message. Never dispatch callback
failure events back through callbacks, preventing recursive failure storms.

## 2026-10-04 Deterministic bounded concurrency

Run trials in batches capped by `concurrency` and samples through a separate semaphore capped by
`sample_concurrency`. Reserve candidates serially, execute concurrently, then apply results and
strategy observations in durable trial-sequence order so completion timing does not alter search
state. Keep `MaxTrials` as a hard cap; allow snapshot cost/time budgets to overshoot only by the
active batch and document that bound. Serialize callback draining per study. Materialize each
finite evaluation split before sample work in V0.1; streaming windows remain a later extension.

## 2026-10-04 Provider-neutral LLMSearch

Define LLM-guided search around an injected structured provider rather than any provider SDK or
prompt framework. Validate exact candidate keys and value bounds, bound invalid/provider-failure
attempts, redact prior observations before provider calls, and record only exception types in
errors. Use stateless deterministic fallback keyed by seed and suggestion number so replay does
not depend on hidden random state. Include optional provider fingerprints in compatibility.
Keep strategy-provider usage explicitly unreported until the common strategy contract gains a
durable usage channel; never silently count unknown provider cost as zero.

## 2026-10-04 Optional RAGAS boundary adapter

Keep the optimizer coupled only to the small `Evaluator` protocol. Provide a built-in
`MetricEvaluator` for ordinary sync or async numeric functions and a lazy `RagasEvaluator` for
RAGAS 0.4. Require an explicit sample mapper as a privacy and schema boundary rather than
inspecting arbitrary user objects. Evaluate one engine sample at a time so TunaRAG retains
ownership of concurrency, retries, timeouts, aggregation, and failure isolation. Namespace RAGAS
metrics by default, normalize missing/nonfinite scores to unavailable, redact provider exception
messages, and keep provider credentials/configuration outside TunaRAG.

## 2026-10-04 Canonical evaluation dataset ingestion

Introduce a provider-neutral `EvaluationExample` and `EvaluationDataset` using only the Python
standard library. Accept mappings, JSON arrays, JSONL, and explicit-mapping CSV; never guess
column semantics. Normalize text conservatively, deeply freeze finite JSON metadata, generate
missing IDs from normalized content, and reject duplicate identities. Version ordered semantic
content with domain-separated hashing and exclude paths/timestamps. Use stable hash-based
80/10/10 splits with optional metadata grouping so assignment is independent of input order.
Keep synthetic generation and rich source-span provenance as a separate feature.

## 2026-10-04 Deterministic result reporting and exports

Derive rankings from immutable terminal summaries instead of persisting duplicate report state.
Rank the configured objective descending with durable sequence ties, and expose independent
direction-aware metric leaders. Define JSON report schema version 1 as the lossless portable
format and CSV as a flattened one-row-per-trial analysis format. Apply central recursive
redaction to candidate parameters in every export and retain usage confidence provenance.
Defer formal Pareto/frontier semantics until the post-V0.1 multiobjective design.

## 2026-10-04 Complete composable stopping rules

Extend committed stop snapshots with success/failure counts and objective history in durable
sequence. Add wall-time, target-score, total/consecutive failure, and no-improvement rules beside
trial and cost budgets. Treat failed trials as non-improvements, require benefit-oriented target
comparisons, and preserve declaration order when multiple rules match. Accept bounded overshoot
from the active concurrency batch; callers requiring exact immediate stopping use concurrency
one. Fingerprint every built-in rule and include the ordered policy list in resume compatibility.

## 2026-10-04 Best-effort MLflow event mirror

Implement MLflow as an optional `EventCallback` projection rather than a store or engine
dependency. Read only committed SQLite state, perform blocking MLflow calls off the event loop,
and rely on callback failure isolation so tracking outages cannot change optimization outcomes.
Log redacted candidate parameters, numeric metrics, sequence, and lifecycle status; normalize
tracking keys deterministically. Keep run IDs in callback memory for V0.1, meaning a resumed
process creates a new mirror run rather than replaying or mutating historical tracking state.

## 2026-10-04 Provider-neutral synthetic QA generation

Keep synthetic generation behind an injected async provider and structured request/response
types. TunaRAG controls deterministic per-document seeds, bounded concurrency, ordering,
validation, provenance, and usage capture without owning prompts, credentials, retries, or SDKs.
Require exact requested cardinality and valid source spans; label every sample synthetic and
unreviewed. Return generation usage separately from optimization accounting.

## 2026-10-04 Keep the reference RAG in examples

Provide a deterministic, provider-free reference RAG under `examples/` rather than under
`src/tunarag`. It demonstrates the standard adapter, evaluator, dataset, search, persistence,
and reporting boundaries through public APIs only. The reference implementation is educational
application code, not a supported retrieval or generation runtime, preserving TunaRAG's role as
an optimizer for user-owned pipelines.

## 2026-10-04 Declare the V0.1 implementation contract complete

Release the implemented package as `0.1.0` after the cross-platform quality matrix, built-wheel
import smoke test, property tests, and reference quickstart pass. Keep formal Pareto semantics,
distributed execution, CLI design, framework adapters, and package-index publication outside
the V0.1 implementation contract. Record public changes through semantic versioning and the
changelog while SQLite and cache formats retain independent schema versions.
