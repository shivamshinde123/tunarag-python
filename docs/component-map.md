# TunaRAG Component Map

| Component | Responsibility | Status |
|---|---|---|
| Domain and serialization | Immutable values, redaction, canonical identity | Implemented |
| Configuration and errors | Typed precedence, validation, stable redacted failures | Implemented |
| Search space and RandomSearch | Typed sampling and seeded suggestions | Implemented |
| Objectives and stopping | Weighted score; trial, cost, time, target, stagnation, failure rules | Implemented |
| SQLite experiment store | Lifecycle, attempts, observations, events, migration/recovery | Implemented |
| Cache | Versioned reusable results, expiry, privacy, checksums, quarantine | Implemented |
| Retry policy | Retry classification, capped backoff, sample/trial deadlines | Implemented |
| Optimizer and trial runner | Bounded trial/sample concurrency, retries, cache, resume, isolation | Implemented |
| LLMSearch | Provider-neutral bounded suggestions, validation, deterministic fallback | Implemented |
| Evaluators | Custom metric helper and optional lazy RAGAS integration | Implemented |
| Evaluation datasets | Canonical examples, JSON/JSONL/CSV ingestion, hashes, splits | Implemented |
| Synthetic generation | Provider-neutral bounded QA generation with spans/provenance/usage | Implemented |
| Events and callbacks | Durable ordered events and isolated post-commit async dispatch | Implemented |
| Results and reporting | Ranking, metric leaders, usage summaries, JSON/CSV exports | Implemented |
| MLflow mirror | Optional best-effort post-commit tracking callback | Implemented |
| Reference RAG example | Deterministic local adapter, evaluator, dataset, optimization, exports | Implemented |

Dependencies flow inward from entry points and integrations toward protocols and immutable
domain values. The user owns retrieval and generation through `RAGAdapter`. RAGAS, MLflow,
provider SDKs, LangChain, and LlamaIndex never become core dependencies. The reference RAG in
`examples/` demonstrates that boundary and is not shipped as package runtime code.
