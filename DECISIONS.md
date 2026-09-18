# Decision Log

## Planning baseline

### Use a Python-first library with async-first internals

Decision: implement the core orchestration asynchronously and provide a synchronous convenience wrapper.

Reasoning: RAG calls, evaluators, and provider calls are commonly I/O-bound; async orchestration supports timeouts, cancellation, and future concurrency while the wrapper keeps simple scripts approachable.

### Keep the RAG application outside the package

Decision: require a user-supplied `RAGAdapter` contract rather than prescribing a framework or owning the application pipeline.

Reasoning: the package optimizes existing systems and must work across frameworks. This keeps the core portable and prevents the reference Auto-RAG-Research implementation from becoming a hidden dependency.

### Make integrations optional

Decision: keep RAGAS, MLflow, and provider-specific integrations behind optional dependency groups and import boundaries.

Reasoning: the core evaluation, storage, and orchestration contracts should remain installable and testable without external services or heavyweight packages.

### Use SQLite as the default source of durable state

Decision: store studies, trials, attempts, metrics, usage, events, and recovery state in SQLite; treat MLflow as an optional mirror.

Reasoning: SQLite is local, transactional, auditable, and sufficient for the V0.1 single-process scope. An external tracking service should not be required for correctness or resume.

### Record exactness explicitly

Decision: usage and aggregate reports distinguish exact, estimated, mixed, and unavailable values.

Reasoning: unknown cost or latency must not silently become zero, and derived pricing must remain auditable. Budget policies can then state how estimates and unknowns affect scheduling.

### Preserve secret safety as a cross-cutting invariant

Decision: use redacted secret types, centralized canonical serialization, and explicit exclusions for secrets from hashes, logs, events, exports, cache metadata, and MLflow parameters.

Reasoning: configuration and provider credentials cross many boundaries; local fixes at individual call sites are too easy to miss.

### Begin with contracts and deterministic primitives

Decision: the first feature branch delivers scaffolding, public models/contracts, canonical serialization, and tests before orchestration or integrations.

Reasoning: the API specification and later persistence/search work depend on stable types and reproducible identity. Establishing those boundaries first reduces rework and makes each later branch reviewable.

### Use `tunarag` as the import package name

Decision: publish the distribution as `tunarag-python` and expose it through the `tunarag` Python import package.

Reasoning: the repository/distribution name follows the requested project name while the shorter import name is idiomatic and leaves room for related tooling without a hyphenated module.

### Use frozen dataclasses for core values

Decision: represent the first domain values with frozen, slotted dataclasses and keep extension points as typing protocols.

Reasoning: immutable values make trial identity and persistence safer, while protocols let callers implement adapters without adopting a package-specific model framework.

### Exclude secret fields from canonical identity

Decision: canonical mappings omit `Secret` values entirely and represent standalone secrets only with a redacted marker.

Reasoning: credentials must never influence cache identity or appear in serialized bytes; nonsecret configuration remains stable and hashable.

## Update rule

Every important implementation choice records what was chosen, why it fits the design documents, and what alternative was rejected. Entries are added as decisions are made; this file is not a generic project diary.