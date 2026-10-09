# Changelog

## 0.3.1 - 2026-10-09

- Replace both raw Mermaid README blocks with pre-rendered PNG diagrams compatible with PyPI.
  Use public absolute documentation/image URLs and add the documentation metadata link.

- Add the complete MIT license with warranty and liability disclaimers to the repository,
  wheel and source archive. Require the license file in distribution-content checks.
- Audit all six README illustrations: remove the redundant loop, replace misleading
  adapter/dataset visuals with two-way framework control and untouched holdout illustrations,
  and move the quality/cost/latency illustration to the objective explanation.

All notable changes to TunaRAG follow semantic versioning.

## 0.3.0 - 2026-10-09

### Changed

- Tune framework pipelines exclusively through official adapters. `Optimizer` rejects custom
  `run` objects; the public `RAGAdapter` and `AsyncRunnable` extension contracts are removed.
- Validate genuine LangChain `Runnable` and LangGraph `CompiledStateGraph` objects, including
  per-candidate factory results. Handwritten `ainvoke` objects are no longer accepted.
- Replace the handwritten reference RAG with an offline LangChain retrieval-chain quickstart.

### Added

- Lean source distributions containing runtime source, build configuration, README, changelog,
  and generated metadata only. CI and publishing reject repository-only assets in archives.

- `GoogleADKAdapter` for Google ADK 2.x runners, with fresh evaluation sessions, session-state
  candidate mapping, final-answer extraction, reported token usage, and guaranteed cleanup.
- Optional `google-adk` extra (Python 3.10+), ADK runner example, and real-framework tests.
- Opt-in OpenRouter, real RAGAS, and local MLflow tests, with a separate `live-test`
  extra, explicit paid-execution gates, request caps, and a documented test plan.

### Fixed

- Seeded RandomSearch resume now skips duplicate draws omitted from persisted trials.
- Callback dispatch no longer skips events committed while another callback awaits.
- Constrain the legacy LangChain community dependency used by RAGAS 0.4 to retain
  the imports required by its evaluator wrappers.

### Migration

- Install the appropriate framework extra and wrap an existing framework pipeline with
  `LangChainAdapter`, `LangGraphAdapter`, or `GoogleADKAdapter`.
- Custom evaluators, search strategies, objectives, callbacks, and synthetic providers remain
  supported. Existing SQLite studies remain readable; changed pipeline identities require new
  studies rather than silently resuming under different semantics.

## 0.2.1 - 2026-10-04

### Added

- Comprehensive product-first README with executable examples for every public workflow.
- CI coverage that extracts and runs all 36 Python examples from the README.
- Manual trusted-publishing workflow for separate TestPyPI and PyPI environments.

### Fixed

- Corrected dataset, LangGraph state, cache, resumability, optimizer-construction, and report-path
  examples found through runtime documentation testing.
- Replaced corrupted version-range punctuation in package metadata.

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
