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
