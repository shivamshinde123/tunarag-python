# TunaRAG Technology Stack

> V0.3 scope: TunaRAG tunes genuine LangChain runnables, compiled LangGraph graphs, and Google ADK 2.x runners through official adapters. Handwritten RAG adapters are unsupported. Evaluators, search strategies, and callbacks remain extensible.

| Area | Selection | Rationale |
|---|---|---|
| Language | Python 3.10-3.13 | RAG ecosystem compatibility |
| Packaging | Hatchling and `pyproject.toml` | Standards-based small build |
| Concurrency | `asyncio` | Standard provider-I/O concurrency |
| Persistence | `sqlite3` | Durable zero-infrastructure authority |
| Identity | Canonical JSON and SHA-256 | Inspectable portable hashes |
| Configuration | TOML via `tomllib`/`tomli` | Standard format with Python 3.10 compatibility |
| Models | Frozen dataclasses and protocols | Immutable values and extension points |
| Tests | pytest, pytest-asyncio, Hypothesis | Sync, async, and property tests |
| Quality | Ruff and strict mypy | Fast consistent checks |
| CI | GitHub Actions | Native pull-request verification |
| Documentation | MkDocs Material and mkdocstrings | Searchable Markdown site with generated Python API reference |
| Documentation hosting | GitHub Pages | Free deployment from the repository through GitHub Actions |
| Framework adapters | Validated framework objects | LangChain Runnable, compiled LangGraph, and Google ADK Runner with lazy imports |

RAGAS `>=0.4,<0.5` is an optional evaluator extra loaded only when `RagasEvaluator` executes.
MLflow `>=3,<4` is an optional tracking extra loaded only when `MLflowCallback` first handles an
event without an injected client. LangChain `>=1,<2` and LangGraph `>=1,<2` are optional extras;
Google ADK `>=2,<3` is another optional extra. Engine tests use LangChain fault-injection
fixtures; dedicated compatibility CI also exercises real ADK runners and compiled LangGraph graphs. Provider SDKs and
LlamaIndex remain optional. SQLAlchemy is deferred
until a second relational backend warrants an ORM. AnyIO is deferred until backend neutrality
removes real complexity. Pydantic may validate external boundaries but will not constrain user
models without measured benefit. Optuna may support later search behind TunaRAG protocols.
JSONL is not authoritative lifecycle state because it lacks transactions and uniqueness.

The documentation build treats the root `README.md` as the canonical usage guide and includes it in
the site rather than maintaining a second copy. `mkdocstrings` reads public Python signatures and
docstrings from `src/tunarag`; hand-written guides continue to explain behavior, rationale, and
workflows that cannot be inferred from code.
