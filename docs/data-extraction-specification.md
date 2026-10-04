# TunaRAG Data Extraction Specification

## Evaluator privacy boundary

The optional `RagasEvaluator` never introspects arbitrary adapter outputs or dataset examples.
Its required `sample_mapper(output, example)` selects the exact fields sent into RAGAS
`SingleTurnSample`. Applications must omit secrets, personal data, proprietary context, and raw
documents unless the configured evaluator provider is explicitly allowed to process them. Mapper
and provider exception messages are not retained by TunaRAG; only exception types cross the
public error boundary. Metric scores, names, status, and coverage may be persisted and cached.

## Scope and sample model

Dataset ingestion and optional synthetic generation are planned for V0.1 and are not yet
implemented. TunaRAG is not a production content-ingestion platform. Each sample will carry a
stable ID, nonempty query, optional answer and reference contexts, relevant document IDs,
tags, JSON metadata, provenance, and immutable split assignment.

## Inputs, normalization, and validation

V0.1 targets JSONL, JSON arrays, explicit-mapping CSV, and Python iterables. Optional
generation may read text and Markdown; PDF extraction is optional. Normalize UTF-8, line
endings, Unicode NFC, a leading BOM, outer whitespace, and disallowed controls without
silently rewriting meaning. Reject empty queries, conflicting IDs, invalid metadata or split
labels, malformed records, and fields missing for selected evaluators. Reports include source
location and bounded examples.

## Splits, hashes, and cache identity

Canonical splits are `optimize`, `validation`, and `test`; exact defaults remain `TBD` until
implementation. Assignment is deterministic by seed and stable identity, with grouped records
kept together. Dataset hashes use domain-separated SHA-256 over normalized semantic content,
schema version, and split membership, excluding local paths and ingestion timestamps.

## Synthetic data and privacy

Generated samples retain source spans, model, prompt/generator versions, seed, usage,
confidence, and review status. They are always labeled synthetic. Queries, answers, contexts,
documents, rationales, and spans are sensitive; default logs/events contain identifiers and
aggregates only. External-provider transmission is an explicit user decision.
