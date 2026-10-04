# Code Flow

The canonical living code-flow document is [`docs/flow.md`](docs/flow.md). This root file is
retained for compatibility with existing links. Update both the implementation and canonical
flow document in the same feature branch.

## Status

Phase 2 is in progress. Package metadata, immutable domain values, extension protocols,
canonical serialization, typed search spaces, seeded random search, objective aggregation,
stop conditions, typed configuration, structured errors, SQLite study/trial persistence,
attempt leases and recovery, atomic observations/events, versioned SQLite caching, and contract
tests are implemented. The first sequential async optimizer path now executes adapters and
evaluators, aggregates metrics and usage, isolates trial failures, commits outcomes, observes
successful trials, applies stop conditions, and returns ranked results.
Retries, separate sample/trial timeouts, retry-attempt usage persistence, and policy-controlled
evaluation-cache integration are also implemented.

## Intended entry points

- Public async study runner: accepts a study configuration, adapter, dataset, strategy, evaluator, objective, store, cache, and lifecycle policies.
- Public synchronous convenience wrapper: runs the async entry point for ordinary scripts.
- Public result/reporting APIs: load a completed or resumed study and expose ranked candidates, usage, budgets, and diagnostics.
- Optional CLI or example entry points: demonstrate the library without becoming part of the core runtime contract.

## Intended execution flow

1. Resolve and validate configuration without persisting a wholesale environment snapshot.
2. Open or create a SQLite-backed study and initialize schema/version metadata.
3. Recover expired running attempts, apply retry policy, reconstruct budgets, and replay terminal observations when resuming.
4. Ask the selected strategy for a typed candidate from the search space.
5. Check the versioned cache using canonical candidate, dataset, evaluator, objective, and adapter identity parts.
6. Execute the user-owned RAG adapter against the evaluation split with timeout and cancellation boundaries.
7. Collect append-only usage records and exact/estimated/unavailable accounting.
8. Run evaluation plugins and resolve objective metrics, normalization, direction, weights, and coverage requirements.
9. Persist trial, metrics, usage, events, and cache data transactionally; emit callbacks/events without exposing secrets.
10. Update strategy state, evaluate stop conditions and budgets, then continue or finalize.
11. Return an actionable result with best candidates, tradeoffs, summaries, and recovery diagnostics.

## Dependency flow

Public models/contracts -> search/evaluation/objective/usage -> storage/cache -> orchestration -> optional integrations/examples.

## Persistence flow

Studies own ordered trials. Trials own attempts, candidate configurations, metrics, usage, and terminal events. Sequence numbers are monotonic and are never reused after recovery. Cache entries are independently versioned, checksummed, privacy-classified, and atomically written.

## Recovery flow

Load study and terminal observations, mark expired running attempts abandoned, apply retry policy, reconstruct exact and estimated budgets, initialize strategy state, replay observations, rebuild candidate hashes, continue sequence numbers, and emit a resume event with counts.

## Current implemented flow

The current optimization path resolves a new study, reserves candidates, checks the compatible
evaluation cache, starts leased attempts, iterates the repeatable dataset, calls the adapter and
evaluators under separate sample/trial deadlines, aggregates metrics, computes the objective,
and atomically commits outcomes. Retryable failures persist attempt usage before deterministic
backoff and a fresh attempt; exhausted failures remain isolated to their trial. Successful
uncached metrics are cached only after the durable trial commit, while cache failures become
events rather than trial failures. Resume validates the study configuration hash, rejects live
leases, abandons only expired attempts in the selected study, rebuilds terminal summaries and
usage, replays successful strategy observations, continues pending/recoverable trials, and
persists the final stop reason. The sync wrappers reject an active event loop. Callback dispatch
delivers newly committed events in sequence order, including retry scheduling before backoff;
callback failures append redacted diagnostics without failing optimization. Bounded concurrency
is not implemented yet.

## Update rule

When an entry point, dependency, state transition, or persistence boundary is implemented, update this file in the same feature branch and commit as part of that feature.
