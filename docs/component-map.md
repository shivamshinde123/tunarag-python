# TunaRAG Component Map

| Component | Responsibility | Status |
|---|---|---|
| Domain and serialization | Immutable values, redaction, canonical identity | Implemented |
| Configuration and errors | Typed precedence, validation, stable redacted failures | Implemented |
| Search space and RandomSearch | Typed sampling and seeded suggestions | Implemented |
| Objectives and stopping | Weighted score and initial budgets | Partially implemented |
| SQLite experiment store | Study and trial lifecycle state | Foundation implemented |
| Cache | Versioned reusable results, expiry, privacy, checksums, quarantine | Implemented |
| Optimizer and trial runner | Validate, schedule, execute, and isolate trials | Planned |
| LLMSearch | Provider-guided validated suggestions | Planned |
| Evaluators | Custom metrics and optional RAGAS | Planned |
| Events and callbacks | Immutable post-commit notifications | Planned |
| Results and reporting | Ranking, usage, failures, and exports | Planned |
| MLflow mirror | Optional post-commit tracking | Later V0.1 |

Dependencies flow inward from entry points and integrations toward protocols and immutable
domain values. The user owns retrieval and generation through `RAGAdapter`. RAGAS, MLflow,
provider SDKs, LangChain, and LlamaIndex never become core dependencies. The reference RAG
belongs under `examples/`.
