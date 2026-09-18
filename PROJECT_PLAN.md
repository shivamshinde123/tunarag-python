# tunarag-python Project Plan

## Goal

Build the `tunarag-python` V0.1 package described by the design documents in `docs/`. The package optimizes configurations of an existing RAG system without owning or rewriting that system.

## Scope

V0.1 is a local, single-process Python library with async-first internals and a synchronous convenience API. It includes typed search spaces, random and LLM-guided strategies, pluggable evaluation, quality/cost/latency objectives, SQLite persistence, caching, retries, resumability, structured events, callbacks, and actionable results.

The reference Auto-RAG-Research implementation remains an example adapter and is not a runtime dependency of the installable package.

## Delivery phases

### Phase 0: Repository and quality baseline

- Establish the `src` layout and package metadata.
- Add supported Python versions, dependency groups, linting, formatting, type checking, and test configuration.
- Add public documentation skeleton, security guidance, changelog, and contribution guidance.
- Add CI for tests, static checks, and supported Python versions.
- Acceptance: a clean checkout installs and the test command passes.

### Phase 1: Domain contracts and configuration

- Implement typed public models, validation errors, secret redaction, canonical serialization, and configuration resolution.
- Implement search-space primitives and deterministic candidate hashing.
- Implement adapter, dataset, evaluation, objective, usage, stop-condition, and event contracts.
- Acceptance: invalid inputs fail predictably; secrets never appear in representations or canonical hashes; contract tests cover the public API.

### Phase 2: Persistence and cache foundations

- Implement SQLite schema, migrations, repositories, sequence allocation, and transactional writes.
- Implement append-only event and usage records, study/trial lifecycle state, and recovery queries.
- Implement versioned cache keys, checksums, atomic writes, corruption quarantine, namespaces, and retention/privacy metadata.
- Acceptance: state survives process restart; transactions preserve invariants; corrupt cache entries become misses; schema tests pass.

### Phase 3: Execution engine

- Implement the async study loop and synchronous wrapper.
- Execute isolated trials through the adapter, evaluation plugins, objective aggregation, usage accounting, retry policy, timeouts, cancellation, and callbacks.
- Add cache lookup/write behavior and durable terminal state transitions.
- Acceptance: successful, failed, retried, cancelled, cached, and resumed trials have deterministic persisted outcomes.

### Phase 4: Search strategies

- Implement deterministic random search with seeded reproducibility.
- Implement the LLM strategy behind an injectable provider contract, with schema validation, bounded suggestions, fallback behavior, and secret-safe prompts/events.
- Implement strategy state replay for resume and explicit study fork semantics.
- Acceptance: both strategies satisfy the common interface, replay terminal observations, and respect budgets and stop conditions.

### Phase 5: Integrations and reporting

- Add optional RAGAS evaluation integration, provider integrations, and optional MLflow mirroring without making them core dependencies.
- Add result ranking, Pareto/frontier reporting, usage and budget summaries, and export APIs.
- Add the example adapter and demonstration workflow outside the installable core.
- Acceptance: optional dependencies are isolated; absent integrations produce actionable errors; reports distinguish exact, estimated, mixed, and unavailable values.

### Phase 6: Hardening and release readiness

- Add end-to-end examples, property-based tests for serialization/search spaces, concurrency and recovery tests, and documentation examples.
- Review security requirements, secret handling, data retention, compatibility, and error messages.
- Publish packaging metadata and a V0.1 release checklist.
- Acceptance: CI is green, public imports are documented, package builds successfully, and the documented quickstart works from a clean environment.

## Dependency direction

`models` and contracts are the lowest layer. Search, evaluation, objectives, and usage depend on those contracts. Storage and cache implement persistence concerns. Orchestration depends on contracts, strategies, evaluation, storage, and cache. Optional integrations depend on public contracts and are never required by core imports. Examples depend on the public package only.

## Verification strategy

- Unit tests for pure models, validation, canonical serialization, objective math, retries, and stop conditions.
- Contract tests for adapters, strategies, evaluators, stores, caches, callbacks, and optional integrations.
- SQLite integration tests for migrations, transactions, recovery, ordering, and concurrent readers/writers.
- End-to-end tests for new studies, resume, retry, cache hits, budget exhaustion, cancellation, and export.
- Static checks: formatter, linter, type checker, test coverage threshold, package build, and import smoke test.

## Git and review workflow

1. Keep `main` releasable and use a new branch for each feature or coherent milestone.
2. Make focused commits as behavior becomes complete and verified.
3. Push the feature branch and open a pull request against `main`.
4. Review and merge are performed by the repository owner.
5. Update `FLOW.md`, `DECISIONS.md`, and relevant documentation in the same branch as the behavior they describe.

## Initial feature sequence

The first implementation branch will deliver Phase 0 and the smallest useful slice of Phase 1: package scaffolding, core public models/contracts, deterministic serialization, and tests. Subsequent features will be proposed as separate branches and pull requests.

## Risks and mitigations

- **Contract breadth:** start from the API specification and keep models independent of providers.
- **Recovery correctness:** make every state transition explicit and test crash/restart paths against SQLite.
- **Secret leakage:** centralize redaction and canonicalization; add negative tests for logs, errors, events, exports, and cache metadata.
- **Optional dependency drift:** isolate integrations behind extras and import boundaries.
- **LLM nondeterminism:** validate suggestions, record provider identity/configuration safely, and preserve replayable observations.