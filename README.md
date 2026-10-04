# tunarag-python

`tunarag-python` is a typed, local-first Python library for comparing and optimizing configurations of an existing RAG system.

The implementation is developed against the detailed DOCX baseline and living Markdown
documents in [`docs/`](docs/), plus the phased delivery plan in
[`PROJECT_PLAN.md`](PROJECT_PLAN.md). Start with the product requirements, system architecture,
technical design, and API specification in `docs/`.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

The public package is imported as `tunarag`.

Implemented foundations include typed domain values, canonical identity, typed search spaces,
seeded random search, objective and stopping primitives, SQLite study/trial persistence, and a
versioned SQLite cache with expiry and corruption quarantine. Typed settings resolve explicit
overrides, selected TOML, and known environment variables; structured package errors expose
redacted diagnostics. The experiment store includes guarded study/trial state, atomic trial
reservation and terminal commits, attempt leases and recovery, metrics, usage, and ordered
events. `Optimizer.aoptimize` now runs sequential async studies with per-sample adapter and
evaluator calls, objective scoring, durable terminal commits, failure isolation, stopping, and
an inspectable result; `optimize` provides the safe synchronous wrapper. Trial attempts now
apply bounded retries with deterministic backoff, separate sample/trial timeouts, append-only
attempt usage, and versioned evaluation-cache reads/writes. Resume, callbacks, and bounded
concurrency are subsequent features.
