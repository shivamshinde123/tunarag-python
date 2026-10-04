# TunaRAG Database Schema

## Current schema version 1

`schema_version(version INTEGER PRIMARY KEY)` records version 1.

`studies` stores UUID `id`, nonempty `name`, canonical `config_hash`, and `created_at`.

`trials` stores UUID `id`, required `study_id`, nonnegative `sequence`, `candidate_hash`,
canonical secret-safe `candidate_json`, lifecycle `status`, optional redacted `error`, and
`created_at`. `(study_id, sequence)` is unique and `study_id` references `studies.id`.
Foreign keys are enabled and lifecycle writes use explicit transactions.

## Planned migrations

Future versions add migration checksums, unique candidates per study, attempts and leases,
metrics, usage, ordered events, datasets, samples, recovery indexes, and atomic
terminal commits. Terminal trials and append-only observations remain immutable. Monetary
values retain currency and decimal-safe representation. Exact DDL is `TBD` until each query
and invariant is implemented.

## Cache schema version 1

The cache uses an independently versioned schema so payload-format changes do not imply an
experiment-store migration. `cache_schema_version` records version 1. `cache_entries` has a
composite primary key of namespace, format version, and key digest; BLOB payload; SHA-256
checksum; privacy classification; active, expired, or quarantined state; creation, expiry, and
last-access timestamps; hit count; and quarantine reason. A state/expiry index supports
retention pruning. Writes, hit accounting, expiry transitions, quarantine, and deletion are
transactional. The cache may use its own database or share a physical SQLite file.

## Provenance and lifecycle

Studies will persist semantic fingerprints for dataset, search space, adapter, evaluators,
objective, strategy, schema, and cache format. Resume compares fingerprints before scheduling.
SQLite remains authoritative when optional systems mirror committed observations.
