# TunaRAG Code Flow

## Current flow

```text
caller
  -> Settings.resolve(defaults, selected TOML, known environment, overrides)
  -> construct Candidate, MetricValue, and UsageRecord
  -> sample SearchSpace through seeded RandomSearch
  -> aggregate metrics through Objective
  -> evaluate MaxTrials or CostBudget
  -> SQLiteStore.initialize
  -> create_study -> create_trial -> transition_trial -> get_trial
  -> CacheKey.from_parts
  -> SQLiteCache.put -> get -> verify checksum/TTL -> hit or explicit miss status
```

Canonical serialization produces deterministic JSON and domain-separated hashes. SQLite owns
durable lifecycle and cache state. A corrupt cache payload is transactionally quarantined and
never returned; expired payloads become misses and can be pruned. No current entry point
executes an adapter or evaluator. Package boundaries will translate contextual failures into
structured `TunaRAGError` subclasses; diagnostic details are redacted recursively.

## Target optimization flow

```text
Optimizer.aoptimize
  -> resolve and validate inputs
  -> create or resume study; recover attempts and replay observations
  -> suggest, validate, deduplicate, and reserve candidate
  -> read compatible cache or execute bounded adapter samples
  -> collect usage; evaluate and aggregate metrics/objective
  -> commit terminal state
  -> notify strategy and post-commit callbacks
  -> evaluate stopping rules
  -> repeat or return OptimizationResult
```

Strategies observe committed outcomes only. Provider calls, user code, sleeps, and callbacks
never run in database transactions. Resume compares semantic fingerprints. Trial and sample
concurrency are bounded separately, and a trial failure is isolated unless policy stops the
study. Dependencies point from public contracts through search/evaluation/storage into
orchestration, then outward to optional integrations and examples.
