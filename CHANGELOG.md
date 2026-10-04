# Changelog

All notable changes to TunaRAG follow semantic versioning.

## 0.1.0 - 2026-10-04

### Added

- Typed `RAGAdapter`, dataset, evaluator, search, objective, usage, callback, and result contracts.
- Random and provider-neutral LLM search over arbitrary typed search spaces.
- Async optimization with a safe synchronous wrapper, bounded concurrency, retry policies,
  timeouts, caching, failure isolation, stopping rules, and resumable studies.
- SQLite-first experiment storage with lifecycle events, recovery leases, and durable usage.
- Canonical JSON/JSONL/CSV dataset ingestion, deterministic splitting, and synthetic QA support.
- Optional lazy RAGAS evaluation and best-effort MLflow event mirroring.
- Redacted JSON/CSV reports and a deterministic provider-free reference RAG quickstart.

### Deferred

- Formal Pareto-front reporting, Bayesian and grid search, distributed execution, a CLI, and
  framework-specific LangChain/LlamaIndex adapters remain post-0.1 work.
