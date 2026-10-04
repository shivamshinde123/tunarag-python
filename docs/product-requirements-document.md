# TunaRAG Product Requirements

## Product and users

TunaRAG optimizes an existing RAG pipeline without prescribing a RAG framework. RAG engineers
compare configurations; evaluation engineers combine custom and optional RAGAS metrics;
platform engineers enforce cost, latency, retry, caching, and provenance policies; researchers
compare reproducible random and LLM-guided search.

## V0.1 goals

1. Wrap a user-owned pipeline through an async `RAGAdapter`.
2. Support arbitrary typed search spaces and canonical candidate identity.
3. Ship interchangeable RandomSearch and LLMSearch.
4. Support custom evaluators and optional RAGAS.
5. Optimize weighted quality, cost, and latency objectives.
6. Preserve exact, estimated, mixed, and unavailable usage provenance.
7. Persist and resume studies through SQLite.
8. Isolate trials and support retries, caching, callbacks, and bounded concurrency.
9. Return a rich result even when no trial succeeds.
10. Keep the reference RAG under `examples/`, outside core dependencies.

## Non-goals

V0.1 does not build or host a production RAG, vector database, model gateway, document
platform, distributed worker system, hosted service, dashboard, or deployment service.
LangChain, LlamaIndex, RAGAS, MLflow, and provider SDKs are not mandatory. Pareto and Bayesian
optimization are later candidates.

## Acceptance criteria

An existing async pipeline can be wrapped without framework imports. Seeded random search is
reproducible. LLMSearch validates suggestions and has deterministic fallback. One trial failure
does not stop a study by default. Compatible resume avoids committed work. Cache corruption is
a quarantined miss. Usage retains confidence. Core imports without optional integrations, CI
passes, and the documented quickstart works from a clean supported environment.

## V0.2 framework-integration goals

1. Wrap an existing LangChain runnable with `LangChainAdapter(existing_chain)`.
2. Wrap a compiled LangGraph with `LangGraphAdapter(compiled_graph)`.
3. Apply candidate parameters through the shared `configurable` namespace by default.
4. Support custom graph state, configuration, output, usage, and construction-time mapping.
5. Capture framework latency and standard message token usage without provider coupling.
6. Keep core installation and imports independent from both frameworks.
7. Verify supported LangChain 1.x and LangGraph 1.x objects in dedicated CI.

V0.2 does not build a production RAG, select providers, manage credentials, create vector stores,
or prescribe chain/graph state. It removes TunaRAG-specific adapter boilerplate after the user
has assembled a framework pipeline.

## Roadmap

Post-V0.2 candidates include GridSearch, Bayesian and formal multiobjective search, a LlamaIndex
adapter, Postgres, distributed execution, service APIs, and a TypeScript implementation.
