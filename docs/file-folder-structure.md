# TunaRAG File and Folder Structure

The site's [Usage Guide](usage.md) is generated from the root `README.md`, which remains the
canonical user-facing guide for installing the package,
connecting custom or framework RAG pipelines, running every public feature, and operating studies.
Its Python fences are executed by `tests/test_usage_documentation.py` so examples cannot silently
drift from the package API.

README illustration source files live under `docs/assets/tunarag-python-readme-illustrations/`.
The README uses repository-relative paths so private GitHub repositories render the images, while
MkDocs copies the same canonical files into the published site.

```text
tunarag-python/
|-- .github/workflows/ci.yml # Linux/Windows quality and build matrix
|-- docs/                    # DOCX specifications and living Markdown
|-- examples/                # User-owned reference RAG and executable quickstart
|-- src/tunarag/             # Installable package
|   |-- __init__.py          # Curated public exports and version
|   |-- py.typed             # PEP 561 marker for downstream type checkers
|   |-- cache.py             # Versioned SQLite cache and key model
|   |-- config.py            # Typed configuration resolution
|   |-- contracts.py         # User and extension protocols
|   |-- dataset.py           # Evaluation examples, ingestion, hashing, and splits
|   |-- domain.py            # Immutable values
|   |-- engine.py            # Async optimizer and sync wrapper
|   |-- errors.py            # Stable structured public errors
|   |-- objective.py         # Objective aggregation
|   |-- evaluators.py        # Custom metric helper and optional RAGAS adapter
|   |-- integrations/        # Optional outward adapters such as MLflow callbacks
|   |   `-- runnables.py     # LangChain and LangGraph async runnable adapters
|   |-- search.py            # Search spaces and RandomSearch
|   |-- serialization.py     # Canonical JSON and hashes
|   |-- stopping.py          # Stop conditions
|   |-- synthetic.py         # Provider-neutral synthetic QA generation
|   |-- result.py            # Optimization and trial summaries
|   |-- retry.py             # Retry classification, backoff, and timeouts
|   `-- store.py             # SQLite lifecycle persistence
|-- tests/                   # Unit and integration tests
|-- CHANGELOG.md             # Versioned user-visible changes and deferrals
|-- CONTRIBUTING.md          # Development and pull-request workflow
|-- PROJECT_PLAN.md          # Delivery phases and gates
|-- RELEASE_CHECKLIST.md     # Repository and package-index release gates
|-- README.md                # Comprehensive public usage guide and package-index description
|-- SECURITY.md              # Vulnerability reporting and trust boundaries
`-- pyproject.toml           # Build and tool configuration
```

Create focused cache, orchestration, event, configuration, evaluator, integration, result, and
dataset modules only as features land. `examples/reference_rag.py` owns the local demonstration
adapter and evaluator; `examples/quickstart.py` composes only public TunaRAG APIs. Put migrations
in a package-owned location when a future schema version requires explicit migration files.
Optional integrations depend inward on public protocols. Avoid generic `utils.py`, provider
imports in core, generated databases in source control, and reference application code under
`src/tunarag`.
