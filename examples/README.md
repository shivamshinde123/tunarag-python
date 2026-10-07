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

## Complete LangChain RAG and tuning workflow

`langchain_full_rag.py` is a single-file, provider-backed example that builds a complete LangChain
pipeline with documents, recursive splitting, OpenRouter embeddings, an in-memory vector store,
retrieval, prompting, and generation. It then wraps the standard retrieval chain with
`LangChainAdapter` and tunes retrieval count, retrieval strategy, temperature, and prompt style.

Install the example dependencies from the repository root:

```powershell
python -m pip install tunarag-python langchain langchain-classic langchain-openai langchain-text-splitters python-dotenv
```

Copy the safe template to a local `.env` file, then replace the placeholder with your OpenRouter
API key. The `.env` file is ignored by Git and must never be committed.

```powershell
Copy-Item .env.example .env
# Edit .env and set OPENROUTER_API_KEY=your-real-key
python examples/langchain_full_rag.py
```

The same OpenRouter key is used for the LangChain chat model and embedding model. Change
`TUNARAG_CHAT_MODEL` or `TUNARAG_EMBEDDING_MODEL` in `.env` to select different OpenRouter model
slugs. Optional attribution values are documented in `.env.example`.

The example writes its SQLite study, evaluation cache, JSON result, and CSV trial report under
`tunarag-langchain-output/`.
