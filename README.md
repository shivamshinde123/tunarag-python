# tunarag-python

`tunarag-python` is a typed, local-first Python library for comparing and optimizing configurations of an existing RAG system.

## Release

The current source release is **V0.2.0**, tagged as `v0.2.0`. See
[`CHANGELOG.md`](CHANGELOG.md) for delivered capabilities and deferred work. Package-index
publication is tracked separately in [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md).

## Installation

```powershell
python -m pip install tunarag-python
```

Optional integrations are installed explicitly with `tunarag-python[ragas]` or
`tunarag-python[mlflow]`. Install `tunarag-python[langchain]`,
`tunarag-python[langgraph]`, or `tunarag-python[frameworks]` for framework integrations.
Python 3.10 through 3.13 is supported.

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

For comprehensive, feature-by-feature instructions, examples, lifecycle diagrams, and operational
guidance, read the **[Usage Guide](Usage.md)**.

## Framework integrations

Existing LangChain runnables and compiled LangGraph graphs require no custom adapter class:

```python
from tunarag import LangChainAdapter, LangGraphAdapter

langchain_adapter = LangChainAdapter(existing_chain)
langgraph_adapter = LangGraphAdapter(compiled_graph)
```

By default, TunaRAG sends an `EvaluationExample` as `{"question": example.query}` and exposes
candidate parameters under `config["configurable"]`. Override `input_mapper`, `config_mapper`,
or `output_mapper` only when the pipeline uses a different state shape:

```python
adapter = LangGraphAdapter(
    compiled_graph,
    input_mapper=lambda example, candidate: {
        "question": example.query,
        "top_k": candidate.parameters["top_k"],
    },
    output_mapper=lambda state: state["answer"],
)
```

Use `factory=lambda candidate: build_chain(candidate.parameters)` when a candidate must rebuild
retrievers, splitters, prompts, or models instead of configuring one reusable runnable.

## Quickstart

Run the deterministic, provider-free reference integration from the repository root:

```powershell
python examples/quickstart.py
```

It writes a durable SQLite study plus JSON and CSV reports under
`tunarag-example-output/`. The example shows how a user-owned RAG implements the adapter
boundary without becoming part of the TunaRAG package.

## Capabilities

### Optimization

- Connect an existing RAG pipeline through a typed adapter instead of rebuilding it.
- Search arbitrary typed configuration spaces with seeded `RandomSearch` or provider-neutral
  `LLMSearch`.
- Optimize weighted quality, cost, and latency objectives with composable stopping rules.

### Evaluation and data

- Use custom evaluators or the optional, lazily loaded RAGAS integration.
- Load normalized JSON, JSONL, or CSV evaluation datasets with deterministic hashing and splits.
- Generate optional synthetic QA datasets with explicit provenance and usage records.

### Reliability

- Run async-first optimization with the safe `optimize` synchronous wrapper.
- Bound trial and sample concurrency independently with `concurrency` and `sample_concurrency`.
- Isolate failed trials and apply deterministic retries, backoff, and sample/trial timeouts.
- Resume compatible studies by replaying committed work and recovering expired attempts.

### Persistence and observability

- Persist guarded study and trial lifecycles, metrics, usage, and ordered events in SQLite.
- Reuse versioned cached evaluations with expiry, checksum validation, and corruption quarantine.
- Receive post-commit callbacks without allowing callback failures to alter optimization results.
- Optionally mirror committed trials to MLflow while keeping SQLite authoritative.

### Results

- Inspect the best candidate, ranked trials, metric leaders, failures, and usage summaries through
  `OptimizationResult`.
- Export redacted deterministic JSON reports or flattened CSV trial data.
