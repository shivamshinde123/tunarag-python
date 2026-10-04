# Changelog

All notable changes to TunaRAG follow semantic versioning.

## 0.2.0 - 2026-10-04

### Added

- Official `LangChainAdapter` for any asynchronous LangChain runnable.
- Official `LangGraphAdapter` for compiled LangGraph graphs.
- Default mapping from evaluation queries to `question` input and candidate parameters to the
  framework `configurable` namespace.
- Custom input, configuration, output, usage, and per-candidate runnable-factory hooks.
- Automatic runnable latency and standard message token-usage capture.
- Optional `langchain`, `langgraph`, and combined `frameworks` installation extras.
- Real-framework compatibility tests against supported LangChain 1.x and LangGraph 1.x releases.

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
