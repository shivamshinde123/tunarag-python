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
seeded random search, objective and stopping primitives, SQLite study/trial persistence, a
custom metric helper plus an optional lazy RAGAS evaluator integration, and a
normalized JSON/JSONL/CSV evaluation dataset model with deterministic splits and hashing.
The versioned SQLite cache supports expiry and corruption quarantine. Typed settings resolve explicit
overrides, selected TOML, and known environment variables; structured package errors expose
redacted diagnostics. The experiment store includes guarded study/trial state, atomic trial
reservation and terminal commits, attempt leases and recovery, metrics, usage, and ordered
events. `Optimizer.aoptimize` now runs sequential async studies with per-sample adapter and
evaluator calls, objective scoring, durable terminal commits, failure isolation, stopping, and
an inspectable result; `optimize` provides the safe synchronous wrapper. Trial attempts now
apply bounded retries with deterministic backoff, separate sample/trial timeouts, append-only
attempt usage, and versioned evaluation-cache reads/writes. Compatible studies can now resume
through `aresume` or `resume`: committed successes are replayed, expired attempts are recovered,
unfinished trials continue, and completed studies reload without provider execution. Callbacks
receive ordered durable lifecycle events after commit; callback failures are isolated and
recorded. Trial batches and per-trial sample execution are independently bounded by
`concurrency` and `sample_concurrency`, with deterministic result/observation ordering.
`RandomSearch` and provider-neutral `LLMSearch` share the strategy contract; LLM suggestions are
strictly validated and fall back deterministically after bounded invalid attempts.
