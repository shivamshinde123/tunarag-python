# TunaRAG Data Extraction Specification

## Evaluator privacy boundary

The optional `RagasEvaluator` never introspects arbitrary adapter outputs or dataset examples.
Its required `sample_mapper(output, example)` selects the exact fields sent into RAGAS
`SingleTurnSample`. Applications must omit secrets, personal data, proprietary context, and raw
documents unless the configured evaluator provider is explicitly allowed to process them. Mapper
and provider exception messages are not retained by TunaRAG; only exception types cross the
public error boundary. Metric scores, names, status, and coverage may be persisted and cached.

## Scope and sample model

Dataset ingestion is implemented; optional synthetic generation remains planned for V0.1.
TunaRAG is not a production content-ingestion platform. `EvaluationExample` carries a stable ID,
nonempty query, optional reference answer and contexts, relevant document IDs, tags, deeply
immutable JSON metadata, canonical split, and synthetic flag. Richer source-span and generator
provenance remains part of the synthetic-generation slice.

## Inputs, normalization, and validation

`EvaluationDataset` accepts mapping iterables, JSONL, JSON arrays, and explicit-mapping CSV.
`DatasetFieldMap` changes source column names without guessing. CSV collection fields are JSON
arrays and metadata is a JSON object. Inputs are UTF-8 with an optional BOM. Normalize line
endings to LF, Unicode to NFC, and remove outer whitespace and leading BOMs. Reject disallowed
controls without silently rewriting meaning. Reject empty queries, duplicate IDs, invalid finite
JSON metadata, invalid split labels, malformed records, and non-string collection values.
`DatasetError` reports source, one-based record/line where available, and exception type without
including sensitive record values.

## Splits, hashes, and cache identity

Canonical splits are `optimize`, `validation`, and `test`; default ratios are 0.8/0.1/0.1 and
must be finite, nonnegative, and sum to one. Assignment hashes seed plus stable example ID.
Optional grouping hashes a required string/integer metadata value so related examples remain
together. Dataset versions use domain-separated SHA-256 over ordered normalized semantic content,
schema version, and split membership, excluding local paths and ingestion timestamps. Missing IDs
are separately domain-hashed from normalized record content; identical implicit records therefore
collide and are rejected rather than silently duplicated.

## Synthetic data and privacy

Generated samples retain source spans, model, prompt/generator versions, seed, usage,
confidence, and review status. They are always labeled synthetic. Queries, answers, contexts,
documents, rationales, and spans are sensitive; default logs/events contain identifiers and
aggregates only. External-provider transmission is an explicit user decision.
