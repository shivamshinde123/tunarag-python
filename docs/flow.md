# TunaRAG Code Flow

## Current flow

```text
caller
  -> construct Candidate, MetricValue, and UsageRecord
  -> sample SearchSpace through seeded RandomSearch
  -> aggregate metrics through Objective
  -> evaluate MaxTrials or CostBudget
  -> SQLiteStore.initialize
  -> create_study -> create_trial -> transition_trial -> get_trial
```

Canonical serialization produces deterministic JSON and domain-separated hashes. SQLite owns
durable lifecycle state. No current entry point executes an adapter or evaluator.

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
