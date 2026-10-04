# TunaRAG Database Schema

## Experiment schema version 2

`schema_version(version INTEGER PRIMARY KEY)` records applied versions 1 and 2. Opening a
version-1 database migrates it transactionally. Unknown or noncontiguous version sets fail with
`StoreError` rather than being opened optimistically.

`studies` stores UUID `id`, nonempty `name`, canonical `config_hash`, lifecycle `status`, and
creation/update timestamps. Valid package transitions are created to running, failed, or
cancelled; running to completed, failed, or cancelled. Completion rejects active trials.

`trials` stores UUID `id`, required `study_id`, nonnegative `sequence`, `candidate_hash`, stable
secret-safe and number-preserving `candidate_json`, lifecycle `status`, optional redacted
`error`, and timestamps. `(study_id, sequence)` and `(study_id, candidate_hash)` are unique. Valid states
are pending, running, succeeded, failed, abandoned, and cancelled. Terminal states are
immutable.

`trial_attempts` stores UUID, parent trial, monotonic attempt number, state, start/finish epoch
timestamps, lease expiry, and redacted error. One running attempt per trial is enforced by a
partial unique index; a state/lease index supports recovery.

`metric_values` stores one aggregate metric name per trial with nullable value, confidence
status, coverage, and creation time. `usage_records` is append-only and stores component,
tokens, decimal-preserving cost text, latency, confidence, pricing version, and optional
attempt. `study_events` stores canonical redacted JSON with an atomic per-study sequence.

Foreign keys are enabled. Candidate/sequence allocation uses `BEGIN IMMEDIATE`. Terminal
result commit writes metrics, usage, attempt state, trial state, and final event in one
transaction. Provider calls and callbacks never occur inside these transactions.
When a retryable attempt fails, its terminal attempt state and any usage already observed are
committed together while the parent trial remains running. The next attempt receives the next
monotonic attempt number. This preserves real cost across retries without exposing partial
metrics as a semantic trial result.

## Planned migrations

Future versions add migration checksums, datasets, samples, persisted expanded fingerprints,
currency alongside decimal-safe cost, and indexes justified by orchestration queries. Exact
DDL remains `TBD` until each query and invariant is implemented.

## Cache schema version 1

The cache uses an independently versioned schema so payload-format changes do not imply an
experiment-store migration. `cache_schema_version` records version 1. `cache_entries` has a
composite primary key of namespace, format version, and key digest; BLOB payload; SHA-256
checksum; privacy classification; active, expired, or quarantined state; creation, expiry, and
last-access timestamps; hit count; and quarantine reason. A state/expiry index supports
retention pruning. Writes, hit accounting, expiry transitions, quarantine, and deletion are
transactional. The cache may use its own database or share a physical SQLite file.

## Provenance and lifecycle

The study `config_hash` covers dataset version, objective, execution policies, component type
identities, and optional component-provided semantic fingerprints. Resume recomputes and
compares this hash before scheduling. Custom components without `fingerprint()` are identified
by type only. SQLite remains authoritative when optional systems mirror committed observations.
