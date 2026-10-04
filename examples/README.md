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

## Existing LangChain or LangGraph pipeline

Install the matching optional extra and wrap the framework object directly:

```python
from tunarag import LangChainAdapter, LangGraphAdapter

chain_adapter = LangChainAdapter(existing_chain)
graph_adapter = LangGraphAdapter(compiled_graph)
```

Both adapters map an evaluation query to the `question` input and candidate parameters to
`config["configurable"]`. For different state shapes, pass a small mapping function instead of
implementing `RAGAdapter`:

```python
graph_adapter = LangGraphAdapter(
    compiled_graph,
    input_mapper=lambda example, candidate: {
        "messages": [{"role": "user", "content": example.query}],
        "retrieval_k": candidate.parameters["top_k"],
    },
    output_mapper=lambda state: state["answer"],
)
```
