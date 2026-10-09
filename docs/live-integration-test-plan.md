# Live integration test plan

## Purpose and current status

Verify the boundaries that offline README checks cannot prove: actual OpenRouter chat
and embedding responses, genuine RAGAS scores, and HTTP writes to a running MLflow
server. The implementation is in `tests/live/`; it is opt-in in the normal test suite.
A separate CI job enables only credential-free real-dependency checks. Do not
interpret an unexecuted paid test as a pass.

The harness uses official LangChain retrieval and document-chain components, an
in-memory vector store, a two-value `top_k` search space, TunaRAG evaluators, SQLite,
and the evaluation cache. It does not implement a handwritten RAG runtime.

Before paid execution, local validation has exercised real non-LLM RAGAS scoring,
real MLflow HTTP tracking, and construction of the real provider/judge clients with
zero provider requests. Checked versions: RAGAS 0.4.3, langchain-community 0.3.31,
MLflow 3.17.0, and langchain-openai 1.7.0 on Windows/Python 3.12.14. OpenRouter-backed
generation, embeddings, judge calibration, and both optimization studies were
subsequently executed successfully with the user's public paper and authorized budget.
Private run artifacts remain outside Git. The normal unit suite also verifies the
harness offline. See [comprehensive testing](comprehensive-testing.md) for the
separately gated full-PDF follow-up and its remaining limitations.

## Test matrix and acceptance criteria

| ID | Test | Credentials | Pass criteria |
| --- | --- | --- | --- |
| L1 | Real RAGAS non-LLM scoring | None | `ExactMatch` returns 1 for SQLite and 0 for Redis through `RagasEvaluator`, not a replacement module. |
| L2 | Local MLflow HTTP tracking | None | A real server accepts the callback; one run matches the authoritative study ID, completes as FINISHED, and has the same per-trial parameter values and metric steps as SQLite. No `callback.failed` events. |
| L3 | OpenRouter RAG tuning | Restricted OpenRouter key | Real embeddings build the vector store; real chat answers are generated for both `top_k` values; both trials succeed, retrieval scores are finite in [0,1], message token usage is captured, and the highest-scoring trial is selected. |
| L4 | OpenRouter-backed RAGAS tuning | Same key | Real judge scores through the package's `RagasEvaluator`; both trials succeed with finite faithfulness scores in [0,1], and the result ranks the measured scores correctly. |
| L5 | Judge calibration | Same key | A plainly supported answer scores higher than a contradictory answer for the same factual context. Failure is a judge/prompt/model compatibility signal, not something to hide by lowering a threshold. |
| L6 | Resume and cache | Included in L3/L4 | A fresh optimizer reloads the completed study without new outbound requests; a fresh study with identical semantic inputs hits the evaluation cache for both trials and makes no provider requests. |
| S1 | Harness safety | None; normal unit suite | Reject exhausted request budgets and non-OpenRouter destinations; reject invalid source references; run the optimization/report/resume/cache harness with offline framework models. |
| S2 | Real SDK construction | None; dummy placeholder key | Construct the actual OpenRouter clients and RAGAS judge wrapper with zero outbound requests. |

L3/L4 check parameter application, scoring, persistence, and ranking, not guaranteed
quality improvement. A tie is a valid outcome. There is no assertion that `top_k=2`
must win with a real model. L2 intentionally does not need paid generation, so tracking
can be diagnosed independently from provider problems.

## Phase 1: isolated installation

Use a separate virtual environment. The main unit suite currently includes tests that
intentionally expect optional dependencies to be absent; run the dedicated live tests
in the optional-dependency environment rather than mixing these installation modes.

PowerShell, from the repository root:

```powershell
python -m venv .tmp/live-venv
.tmp/live-venv/Scripts/python.exe -m pip install -e ".[live-test]"
.tmp/live-venv/Scripts/python.exe -m pip freeze > .tmp/live-versions.txt
```

The package supports RAGAS 0.4.x and MLflow 3.x for this suite. Tests exercise the
package's existing RAGAS `aevaluate` integration with legacy metrics and a LangChain
LLM wrapper. RAGAS documents those APIs as deprecated; a future collections-API
migration is separate from this compatibility test. See the
[official migration guide](https://docs.ragas.io/en/stable/howtos/migrations/migrate_from_v03_to_v04/).

The RAGAS extra constrains `langchain-community` to 0.3.31–0.3.x because its 0.4.x
release removes the legacy Vertex AI module imported by RAGAS 0.4's LLM wrappers.
This constraint was discovered with the real dependency installation, not a mock.

## Phase 2: credential-free real dependencies

```powershell
.tmp/live-venv/Scripts/python.exe -m pytest tests/live --live -m "not paid" --basetemp=.tmp/live-local --junitxml=.tmp/live-local-results.xml
```

The MLflow fixture starts a server on an ephemeral loopback port with a temporary
SQLite backend, waits up to 90 seconds for readiness, and terminates its process tree
after the test. It does not expose a public port, use a hosted service, or require an
account. Its `server.log` and the authoritative store remain under the pytest base
directory. If startup fails, inspect that log before rerunning.

MLflow's server and SQLite backend are supported by its
[official self-hosting documentation](https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server/).

## Phase 3: configure a restricted provider key

```powershell
Copy-Item tests/live/.env.example tests/live/.env
```

Edit the ignored `tests/live/.env` locally:

| Variable | Purpose | Default model |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | Required only for paid tests | No default |
| `TUNARAG_LIVE_CHAT_MODEL` | RAG answer model | `openai/gpt-4.1-mini` |
| `TUNARAG_LIVE_JUDGE_MODEL` | RAGAS judge; should reliably follow structured-output prompts | `openai/gpt-4.1-mini` |
| `TUNARAG_LIVE_EMBEDDING_MODEL` | Source and query embeddings | `openai/text-embedding-3-small` |

Model slugs are configuration examples, not a promise of future availability or
pricing. Verify account access and rates before authorizing execution. The suite fixes
the base URL to `https://openrouter.ai/api/v1`; it cannot send the key to a custom host.
The embeddings request uses the
[documented OpenRouter endpoint](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings).

Do not paste a key into chat, source code, or a GitHub secret for this initial run.
Use a dedicated key with a small provider-side credit limit. Confirm a maximum spend
before we run the paid phase. Loading is explicit through `--live-env`; existing process
environment values take precedence over dotenv. If changing keys/models, also clear
any existing process variables that would override the file.

## Phase 4: run paid tests deliberately

Start with OpenRouter retrieval scoring, then calibration, then full RAGAS tuning:

```powershell
.tmp/live-venv/Scripts/python.exe -m pytest tests/live/test_provider.py --live --live-paid --live-env=tests/live/.env -k retrieval_recall --live-request-limit=12 --basetemp=.tmp/live-openrouter --junitxml=.tmp/live-openrouter-results.xml
.tmp/live-venv/Scripts/python.exe -m pytest tests/live/test_provider.py --live --live-paid --live-env=tests/live/.env -k contradictory --live-request-limit=10 --basetemp=.tmp/live-calibration --junitxml=.tmp/live-calibration-results.xml
.tmp/live-venv/Scripts/python.exe -m pytest tests/live/test_provider.py --live --live-paid --live-env=tests/live/.env -k ragas.faithfulness --live-request-limit=30 --basetemp=.tmp/live-ragas --junitxml=.tmp/live-ragas-results.xml
```

Or run the entire live suite once:

```powershell
.tmp/live-venv/Scripts/python.exe -m pytest tests/live --live --live-paid --live-env=tests/live/.env --live-request-limit=40 --basetemp=.tmp/live-all --junitxml=.tmp/live-results.xml
```

Do not rerun commands blindly: each fresh process can incur new charges. Reusing a
`--basetemp` directory causes pytest to clean its previous contents; archive needed
results first. The smoke-test source data shipped in the repository needs no upload.

## Safeguards and limits

- Normal `pytest` skips all six live test cases. `--live` enables credential-free
  checks; `--live-paid` additionally authorizes provider requests. The separate
  `live-dependencies` CI job sets only `--live` and excludes paid tests. Supplying a
  key alone never enables paid tests.
- A session-shared HTTP hook caps OpenRouter requests at 40 by default (allowed 1–500),
  including embeddings and judge calls. It counts attempts before sending them. A
  failed or blocked attempt may consume a slot. No request body or key is logged by
  the hook. SDK retries are zero; TunaRAG retries are zero. RAGAS `aevaluate` initializes
  its own run configuration (up to 10 attempts in checked 0.4.3), overriding wrapper
  retry settings. Those internal attempts still pass through the shared request cap
  and outer sample deadline; a wrapper-only retry setting is not a safety guarantee.
- This is a **request cap, not a guaranteed dollar cap**. Input context, judge prompts,
  model pricing, and provider-side billing determine charges. Set a provider-side
  key credit limit. Chat/judge output is limited to 512 tokens per call, and tests use
  two trials, at most three questions, and sequential samples.
- The HTTP request hook enforces 45-second transport timeouts even if a wrapper
  changes SDK timeout settings. RAGAS's checked default run timeout is 180 seconds;
  sample and whole-calibration timeouts are 180 seconds, and trial timeout is 600
  seconds. These reduce runaway execution but do
  not reverse billing for a request already accepted by a provider.
- RAGAS analytics and LangSmith tracing are disabled for live tests. Data still goes
  to OpenRouter and the selected underlying model providers. Source text, questions,
  reference answers, and model outputs can appear in local cache/store/test failures.
  The reports and SQLite files are not a secret vault. Use sanitized data and keep
  all generated artifacts private until reviewed.
- Generation message token usage is asserted. Judge/embedding billing is not fully
  attributable through the package's current evaluator interface; OpenRouter billing
  remains the authority. Do not report a complete study dollar cost from partial usage.

## Data for a representative follow-up

No PDF is required for the initial smoke tests. For your domain, provide a small
sanitized text-selectable PDF (roughly 3–10 pages), or Markdown/text/JSON source data,
plus 5–10 human-reviewed questions with correct answers and supporting page/section
references. Confirm that sending it to OpenRouter and model providers is permitted.
Scanned PDFs need OCR first; extraction quality must be checked before tuning.

The implemented smoke harness accepts normalized JSON, not PDF paths. Use LangChain
document loaders to extract PDFs in a separate preparation step, manually verify the
text, then produce:

```json
[
  {"id": "section-1", "text": "Verified source text..."},
  {"id": "section-2", "text": "More verified source text..."}
]
```

And a separate evaluation JSON file:

```json
[
  {"id": "q1", "query": "A question?", "reference_answer": "A supported answer.", "relevant_document_ids": ["section-1"]}
]
```

Run with `--live-documents=path/to/documents.json --live-dataset=path/to/dataset.json`.
The bounded smoke test accepts 2–10 documents (up to 2,000 characters each) and 1–3
questions (query and reference each up to 1,000 characters). Use the first 1–3 reviewed
questions initially; the remaining questions are for a later held-out quality study,
not for enlarging this smoke test unnoticed. Keep private data outside tracked files.

## Failure diagnosis and deferred checks

| Symptom | Action |
| --- | --- |
| Missing key, invalid corpus, absent optional dependency | Fix setup before provider requests; do not mark skipped tests as passed. |
| 401/403 | Check key, model access, and provider policy; never publish request headers. |
| 402 or request budget exhausted | Stop. Inspect billing and obtain fresh spending authorization before retrying. |
| 429 or timeout | Record a transient provider failure; no automatic broad retry in this suite. |
| NaN/unavailable RAGAS score, judge calibration failure, JSON parsing error | Inspect model compatibility and prompt truncation privately; do not substitute a constant score. |
| Successful study but no MLflow run/metrics | Check durable `callback.failed` events and server log; tracking failures are intentionally isolated by the optimizer. |
| Resume makes new calls or cached study reruns generation | Fail the test and investigate identity/cache correctness before using larger data. |

The initial implementation does not test a hosted/authenticated MLflow deployment,
MLflow outage recovery, injected real-provider 429 errors, interrupted mid-request
resume, LangGraph/ADK provider-backed runs, LLMSearch's remote suggestion provider,
or statistically significant quality improvement. Existing offline tests cover retry,
failure isolation, and interrupted-study recovery. Later live quality experiments
need a held-out dataset, larger search budget, judge validation, and repeated runs;
keep that separate from smoke-test acceptance.

## Evidence to retain

Keep dependency versions, OS/Python version, selected model slugs, dataset hashes,
JUnit report, local SQLite studies, JSON/CSV results, and local MLflow logs together.
Record test outcomes as pass/fail/skip/not-run and whether real provider calls occurred.
Do not put credentials, raw private PDFs, request headers, or unreviewed provider
exceptions into a PR. The plan and harness can be shipped before paid tests run.
