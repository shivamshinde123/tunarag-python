# Reference RAG Quickstart

This example keeps application code outside the TunaRAG package and demonstrates the intended
integration boundary: a user-owned RAG implements the adapter contract, evaluators score its
outputs, and TunaRAG owns search, orchestration, persistence, and reporting.

From the repository root, after installing the development environment, run:

```powershell
python examples/quickstart.py
```

The command creates `tunarag-example-output/experiments.db`, `result.json`, and `trials.csv`.
The implementation is deterministic, local, uses no provider credentials, and is deliberately
small enough to replace with an existing RAG pipeline.
