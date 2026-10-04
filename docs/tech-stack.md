# TunaRAG Technology Stack

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

RAGAS, MLflow, provider SDKs, LangChain, and LlamaIndex remain optional. SQLAlchemy is deferred
until a second relational backend warrants an ORM. AnyIO is deferred until backend neutrality
removes real complexity. Pydantic may validate external boundaries but will not constrain user
models without measured benefit. Optuna may support later search behind TunaRAG protocols.
JSONL is not authoritative lifecycle state because it lacks transactions and uniqueness.
