# README example verification

## Scope and reproduction

All 36 Python code blocks in the README are executed by
`tests/test_usage_documentation.py`. Most blocks are feature fragments, not standalone
scripts: the tests supply variables introduced earlier or assumed by the snippet.

```bash
python -m pip install -e ".[dev,frameworks]"
python -m pytest tests/test_usage_documentation.py tests/test_readme_tuning.py tests/test_google_adk_integration.py
```

`tests/test_readme_tuning.py` additionally checks that parameters reach real LangChain
and LangGraph components, produce different scores, and select the better candidate.
ADK tests use a real SDK runner with an offline agent to verify parameter-to-result
behavior and session cleanup. These are deterministic correctness tests, not evidence
of production LLM quality gains.

## Coverage map

Block numbers refer to Python fences in README order.

| Blocks | Feature | Verification |
| --- | --- | --- |
| 1 | Quickstart | Real LangChain retrieval; `top_k=1` recalls one of two reference contexts (score 0.5); `top_k=2` scores 1.0 and wins. |
| 2–3 | Adapter setup and identity | Execute construction and identity examples. |
| 4 | Configurable LangChain | Actual snippet tunes two configurations; scores 1 and 2 select `top_k=2`. |
| 5 | Retrieval-chain factory | Real retrieval and document chains; verify context count changes with `top_k` and model factory selection changes scores. |
| 6 | Adapter mappings | Execute input, configuration, output, and usage mappings with supplied runnable. |
| 7–8 | LangGraph | Real compiled graphs; tuning changes output and selects `top_k=2`. |
| 9–12 | Models and datasets | Execute construction, ingestion, normalization, splitting, and dataset examples. |
| 13 | Synthetic generation | Injected deterministic client; no remote generation call. |
| 14–16 | Search spaces and strategies | Execute search examples; LLMSearch also tunes the real LangChain snippet with an injected suggestion client. |
| 17 | Custom evaluators | Execute metric/evaluator definitions and evaluations. |
| 18 | RAGAS | Evaluator construction using a test module; not real RAGAS scoring. |
| 19–20 | Objective and settings | Execute weighted objective and settings examples. |
| 21–24 | Optimization and retries | Execute optimization and policy fragments; async/sync entrypoints also select the higher-scoring candidate with the real LangChain snippet. |
| 25–26 | Cache | Execute cache-backed tuning and direct cache operations; verify winner selection. Optimizer tests separately cover cache hits and retries. |
| 27–28 | Resume and SQLite | Execute completed-study resume and store queries; separate optimizer tests cover interruption recovery. |
| 29 | Callbacks | Execute callback-backed tuning with the real LangChain snippet and verify winner selection. |
| 30 | MLflow | Callback construction only; no live tracking server. |
| 31–33 | Results and exports | Execute result inspection, metric leaders, JSON and CSV export. |
| 34–36 | Errors, secrets, extensions | Execute error handling, secret handling, and custom search-parameter fragments. |

## Corrections discovered

- The previous quickstart had constant answers and a constant metric: it could not
  demonstrate a better candidate. The updated version scores retrieved contexts
  while keeping embeddings and generation offline.
- The factory used the default `question` key, but `create_retrieval_chain` requires
  `input`. The README sets `input_key="input"`; tests now use the real chain rather
  than a permissive replacement.
- The development extra includes `langchain-classic`, which provides these chain helpers.

## Limits

No paid provider calls, live OpenRouter requests, real RAGAS scoring, or live MLflow
tracking are checked. Fake embeddings, responses, and injected clients allow
reproducible checks without credentials. Live-provider smoke tests remain necessary
for model availability, response formats, rate limits, billing, and evaluation quality.
