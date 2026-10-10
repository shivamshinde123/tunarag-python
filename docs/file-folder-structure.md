# TunaRAG File and Folder Structure

`LICENSE` holds the complete MIT permission, warranty disclaimer and liability terms;
it ships with runtime distributions. `docs/illustration-audit.md` records the value review
and QA of the five README illustration assets (documentation-only, excluded from PyPI).

`scripts/check_distribution.py` is a repository-only release guard, exercised by
`tests/test_distribution.py` and CI/publishing. `docs/package-distribution.md` defines
the archive boundary: only runtime source and essential build/metadata files reach PyPI.

> V0.3 scope: TunaRAG tunes genuine LangChain runnables, compiled LangGraph graphs, and Google ADK 2.x runners through official adapters. Handwritten RAG adapters are unsupported. Evaluators, search strategies, and callbacks remain extensible.

The site's [Usage Guide](usage.md) is generated from the root `README.md`, which remains the
canonical user-facing guide for installing the package,
connecting supported framework RAG pipelines, running every public feature, and operating studies.
Its Python fences are executed by `tests/test_usage_documentation.py` so examples cannot silently
drift from the package API.

README illustration source files live under `docs/assets/tunarag-python-readme-illustrations/`.
The README uses public GitHub Pages image URLs so GitHub and PyPI can load them even when the
repository is private. MkDocs copies the canonical files into the published site.

`docs/assets/diagrams/` contains editable `.mmd` sources and static SVG/PNG diagrams.
The Pages site uses SVGs rather than browser-side Mermaid rendering. The repository-only
`scripts/check_docs_diagrams.py` verifies all built image references and rejects empty SVGs,
missing images and runtime Mermaid containers before deployment; `tests/test_docs_diagrams.py`
covers these failure cases. Neither diagram assets nor authoring tools enter PyPI archives.
`scripts/render_docs_diagrams.py` regenerates existing Pages SVGs through an installed
Mermaid CLI and sets intrinsic image sizes so tall diagrams do not collapse in browsers.

```text
tunarag-python/
|-- .github/workflows/ci.yml # Linux/Windows quality and build matrix
|-- docs/                    # DOCX specifications and living Markdown
|-- examples/                # Framework pipelines and executable quickstarts
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
|   |   |-- runnables.py     # Validated LangChain and LangGraph adapters
|   |   `-- google_adk.py    # ADK runner, session isolation, and event mapping
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
dataset modules only as features land. `examples/quickstart.py` composes LangChain components with public TunaRAG APIs;
`examples/google_adk_tuning.py` tunes an existing ADK runner. Put migrations
in a package-owned location when a future schema version requires explicit migration files.
Optional integrations depend inward on public protocols. Avoid generic `utils.py`, provider
imports in core, generated databases in source control, and reference application code under
`src/tunarag`.

`tests/live/` contains opt-in real RAGAS scoring, OpenRouter-backed LangChain tuning,
and loopback MLflow tracking tests, their explicit configuration template, and a
public synthetic JSON corpus. `tests/test_live_harness.py` verifies safeguards and
the tuning harness without credentials. Private dotenv files and generated output
stay ignored; `docs/live-integration-test-plan.md` defines execution and acceptance.

`tests/live/test_google_adk.py` adds real ADK/OpenRouter RAG tuning and held-out
evaluation. `tests/live/test_adk_transport.py` checks the same SDK transport path
without network calls or credentials. `docs/live-google-adk-testing.md` documents
the smaller ADK campaign and its provider boundaries.
