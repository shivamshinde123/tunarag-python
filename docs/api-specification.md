# TunaRAG API Specification

## Status

This is the living V0.1 Python API contract. The companion
`01_API_Specification.docx` contains the full design narrative. Implemented and planned APIs
are separated below so design commitments are not mistaken for runtime behavior.

## Implemented surface

`tunarag` exports `Candidate`, `MetricValue`, `UsageRecord`, `Secret`, `ValueStatus`, objective
types, `MaxTrials`, `CostBudget`, `SQLiteStore`, study/trial records, and the cache types
`CacheKey`, `CacheEntry`, `CacheLookup`, `CacheLookupStatus`, `CachePrivacy`, and
`SQLiteCache`. Search-space types and `RandomSearch` are currently imported from
`tunarag.search`; extension protocols live in `tunarag.contracts`.

`Candidate` requires a nonempty parameter mapping. Metrics and usage retain `exact`,
`estimated`, or `unavailable` provenance. `Objective.evaluate` combines configured terms.
`SQLiteStore` initializes schema version 1, creates studies and ordered trials, transitions
trials, retrieves trials, and closes its connection.

`CacheKey.from_parts(namespace, *parts, format_version=1)` creates secret-safe canonical
identity. `SQLiteCache.put` atomically stores bytes with privacy and optional positive TTL.
`SQLiteCache.get` returns explicit hit, miss, expired, corrupt, or quarantined status; only a
verified hit contains payload bytes. `delete` removes one key, while `prune` removes expired
entries and optionally quarantined entries. Cache metadata and payloads survive reopen.

Invalid domain values raise `ValueError` or `TypeError`; unknown trial IDs raise `KeyError`;
database constraints raise `sqlite3.IntegrityError`. A package error hierarchy is planned.

## Planned V0.1 entry point

```python
optimizer = Optimizer(
    adapter=adapter,
    search_space=search_space,
    evaluators=evaluators,
    objective=objective,
    strategy=RandomSearch(search_space, seed=42),
)
result = await optimizer.aoptimize(dataset, study_name="support-rag")
```

`aoptimize` is authoritative. `optimize` will be a synchronous wrapper and will reject use
inside an active event loop. `OptimizationResult` will expose the stop reason, ranked trials,
best candidate, metrics, usage, failures, cache/retry diagnostics, and reproducibility data.

## Versioning

The distribution is `tunarag-python`; the import package is `tunarag`. Public APIs follow
semantic versioning. SQLite schemas and cache formats have independent versions and explicit
migration or invalidation rules.
