# TunaRAG Decision Log

Decisions are chronological. Superseding entries preserve the original reasoning.

## 2026-10-03 Naming

Use TunaRAG as the product, `tunarag-python` as the repository and Python distribution, and
`tunarag` as the import package. A TypeScript implementation will use a separate repository.

## 2026-10-03 Runtime boundary

Build async-first internals with a synchronous wrapper. Users supply a `RAGAdapter`; TunaRAG
does not own their production RAG. Keep RAGAS, MLflow, providers, LangChain, and LlamaIndex as
optional edge integrations.

## 2026-10-03 Values and identity

Use frozen slotted dataclasses for core values, protocols for extension points, canonical JSON
and domain-separated SHA-256 for identity, and omit secret values from identity mappings.

## 2026-10-03 Search and accounting

Random search owns an isolated seeded random stream. Objective and usage results retain
`exact`, `estimated`, or `unavailable` status; unknown values never silently become zero.

## 2026-10-03 Persistence

Use standard-library `sqlite3` and explicit transactions as V0.1 authority. MLflow is an
optional mirror. Defer an ORM until a second relational backend justifies it.
