# TunaRAG code audit: does the code do what the docs say?

**Date:** 2026-11-21. **Version audited:** `tunarag-python` 0.3.0 (`main` at `db8b5e2`).

**Method:**
- Read every source module in full (5,555 lines), plus the README, the examples and the reference docs.
- Ran the full test suite in a fresh environment with every extra installed.
- Built three real RAG apps (LangChain, LangGraph and Google ADK) on OpenRouter, using `gpt-4.1-mini` and `text-embedding-3-small`.
- Ran every TunaRAG feature against those apps.
- Ran the repo's shipped examples and its paid live tests.
- Wrote targeted probe scripts for each suspicious claim.

Every finding below was **reproduced**. The scripts are in [`scripts/`](scripts/).

**Environment:**
- Windows 11, Python 3.12.
- Frameworks: google-adk 2.15.0, langchain 1.5.2, langchain-classic 1.0.8, langgraph 1.2.24.
- Integrations: ragas 0.4.4, mlflow 3.18.0, openai 3.3.0, litellm.

## Status: all findings fixed (2026-11-21)

Every finding below was fixed in the same session. Each has a regression test in
[`tests/test_audit_regressions.py`](../../tests/test_audit_regressions.py) (27 tests), and the
real-model runs were repeated against the fixed code.

**Results after the fixes:**
- Unit suite: 186 passed (268 after rebasing onto upstream 0.3.1, which added tests).
- Repo live tests with paid OpenRouter calls: 6 of 6 passed.
- `mypy --strict`: clean.

**What changed in the real runs:**
- The LangChain `create_retrieval_chain` app now records 4,502 tokens and a $0.0026 estimated cost (it recorded 0 before).
- RAGAS coverage is 1.0 on every trial.
- ADK retrieval recall is now measurable (coverage 1.0).
- A real provider timeout is retried, for 3 attempts in total.
- A kill and resume leaves one MLflow run.
- The shipped example now reports 5,793 / 1,018 tokens, about $0.0039.

| Finding | Fix |
|---|---|
| H-1 NaN/inf crashes study | `MetricValue`/`UsageRecord` reject non-finite values, so the failure stays inside the trial; the objective is guarded too |
| H-2 Ctrl-C / crash unresumable | Cancellation finishes attempts as cancelled and leaves trials recoverable; `cancelled`/`failed` studies resume |
| H-3 Cost tracking | LangChain `UsageMetadataCallbackHandler` capture; new `token_prices` on all adapters; unknown cost reported `unavailable`; per-sample usage kept on timeout and cancel |
| H-4 Provider errors not retried | Structural classification by type name, HTTP status and wrapped cause |
| H-5 Stale cache / resume identity | Without `identity`: code digests for scorers, factories, mappers, wrapped functions, graph nodes and ADK agents, plus a warning for adapters. With `identity`: the declared version is used instead (`MetricEvaluator(identity=)` is new) |
| H-6 RAGAS race / coverage | Per-call metric copies; partial coverage makes the objective `estimated`; `ObjectiveTerm.min_coverage` |
| M-1 ADK evidence | Default output adds `tool_responses`; new `events_mapper` |
| M-2 MLflow second run | Reuses the run tagged with the study ID and reopens it on resume |
| M-3 Custom parameter crash | Canonical hashing supports objects with `describe()` |
| M-4 Unused settings | Documented as application-level values (`seed`, `artifact_dir`, paths) |
| M-5 Opaque errors | TunaRAG messages kept; ADK error code persisted; underlying cause logged to the `tunarag` logger (third-party text is not persisted, for privacy) |
| L-1 … L-9 | Active time across resumes; order-independent dataset version; duplicate rows name their records; synthetic `allow_partial` plus per-document causes; LLMSearch replay matches the live run; consecutive `MaxFailures` uses failure history; type-tagged floats; README version text; RAGAS test made environment-independent |

**Breaking change:** identity hashes changed (dataset version, float encoding, fingerprints).
Studies started before these fixes cannot be resumed, and their cache entries are not reused.
See `CHANGELOG.md` and `docs/decision.md`.

---

## Summary (as found, before the fixes)

| | Count |
|---|---|
| Unit tests (all extras installed) | **158 passed**, 1 failed (environment-sensitive test, see L-9) |
| Repo live tests with real paid OpenRouter calls (L1–L6) | **6 / 6 passed** |
| Real RAG apps built and tuned | 3 (LangChain, LangGraph, Google ADK); all studies completed |
| Shipped examples run unmodified | `langchain_full_rag.py` ✔, `google_adk_tuning.py` ✔, `quickstart.py` ✔ (unit test) |
| Broken promises found | **6 high**, 5 medium, 9 low |

The core design is sound. The optimization loop, the SQLite store, cache integrity, deterministic splitting, the stop rules and hard-kill recovery all behave as documented, including under real models.

The problems cluster in four areas:
- **What happens when something goes wrong:** NaN values, Ctrl-C, provider errors.
- **Cost and usage accounting:** it is close to non-functional with real providers.
- **Identity and caching:** lambdas, and adapters without `identity`, give stale results.
- **Integration edges:** RAGAS concurrency, ADK retrieval evidence, and MLflow after a resume.

---

## High severity: silently wrong results, crashes, or broken headline promises

### H-1. One NaN or infinite value crashes the whole study, and it can't be resumed

**Claim:** "isolates failures"; "terminal trial failures do not abort the rest of an optimization study" (`examples/langchain_full_rag.py`).

**Reality:**
- `MetricValue` and `UsageRecord` accept NaN and infinity ([domain.py:39](../../src/tunarag/domain.py), [domain.py:60](../../src/tunarag/domain.py)).
- The trial commits as *succeeded* with a NaN score.
- The next `StopContext` validation then raises `ValueError` ([stopping.py:40](../../src/tunarag/stopping.py)) and the study is marked **failed**.
- Failed studies can't be resumed (see H-2).
- `MetricEvaluator` cleans NaN, but custom evaluator classes, which the README itself recommends, and usage mappers don't.

**Probe** (`probe_values.py`):
- Custom evaluator returns NaN → `WHOLE STUDY RAISED ValueError: objective scores must be finite or None (study status: failed)`.
- Same for `inf`, and for a NaN `cost` in usage.

### H-2. Ctrl-C or any unhandled error makes the study unresumable

**Claim:** "supports resumable execution"; README diagram story: interrupted → resume.

**Reality:**
- Cancellation, which is what `asyncio.run` does on Ctrl-C, marks the study `cancelled` ([engine.py:246](../../src/tunarag/engine.py)).
- Any other exception marks it `failed` ([engine.py:251](../../src/tunarag/engine.py)).
- `aresume` rejects both ([engine.py:146](../../src/tunarag/engine.py)).
- Only a hard process kill leaves a resumable study, and only after the recovery lease expires (trial timeout + 60 s; 6 min by default).

**Probes:**
- `probe_claims.py` P1: cancel → `ResumeError: failed or cancelled studies are terminal and cannot resume`.
- `kill_resume.py`: a hard kill **does** resume correctly after 62 s. It skipped the 2 committed trials, re-ran the 2 interrupted ones and completed 6 distinct candidates.

### H-3. Cost and usage tracking doesn't work with real providers, so `CostBudget` never fires

Three separate defects add up to this:

1. **The standard LangChain RAG chain reports 0 tokens.**
   - `create_retrieval_chain` and `create_stuff_documents_chain` return a plain-string answer, so the default usage discovery ([runnables.py:198](../../src/tunarag/integrations/runnables.py)) finds no `usage_metadata`.
   - Evidence: the shipped `examples/langchain_full_rag.py` ran 8 real trials (40 RAG calls) and its `result.json` reports `input_tokens: 0, output_tokens: 0`.
   - LangGraph works when the `AIMessage` stays in state (3,952 tokens captured), and so does ADK (11,428 tokens).
2. **Unknown cost is reported as an *exact* $0.00.**
   - `UsageRecord.status` defaults to `EXACT`, and `_usage_summary` sums `cost or 0.0` ([engine.py:952](../../src/tunarag/engine.py)).
   - Every real study reported `cost_exact=0.0 status=exact` for paid calls. This contradicts "Usage separates exact and estimated cost".
   - No adapter ever supplies a dollar cost, so `CostBudget` can never trigger without a custom usage mapper.
3. **Timed-out attempts lose the money they already spent.**
   - A trial timeout raises out of `_execute_candidate` and the usage of finished samples is dropped ([engine.py:534](../../src/tunarag/engine.py)).
   - This contradicts "Attempt usage is append-only, including failed attempts".
   - Probe P4: 3 attempts made 3 real $1 calls; recorded cost was $0, and `CostBudget(0.5)` never stopped the run.

### H-4. Retries never fire for real provider failures

**Claim:** "Timeouts and connection errors are retryable."

**Reality:**
- `RetryPolicy.is_retryable` only recognises Python's built-in `TimeoutError` and `ConnectionError` ([retry.py:55](../../src/tunarag/retry.py)).
- Errors from the OpenAI SDK and httpx are none of those: `APITimeoutError`, `APIConnectionError`, `RateLimitError` (429), `InternalServerError` (503), `httpx.ConnectTimeout`. All were checked and classified `retryable=False`.

**Real run:**
- A real OpenRouter call timed out under `RetryPolicy(max_retries=2)`.
- Result: `status=failed attempts=1 error=adapter failed: OpenAITimeoutError`, with no retry.
- In practice only LangChain's or LiteLLM's own internal retries protect you.

### H-5. Changed pipelines or evaluators silently get stale cached scores, and resume accepts them

**Claim:** "Identity includes dataset version, candidate, adapter, and evaluators."

**Reality:**
- `MetricEvaluator` identifies its scorer only by `module.qualname` ([evaluators.py:56](../../src/tunarag/evaluators.py)), so **every lambda looks identical**, and editing a function body never changes identity. The README's first example uses a lambda scorer.
- Adapters without `identity=` are identified only by their runnable class name ([runnables.py:88](../../src/tunarag/integrations/runnables.py)), e.g. `RunnableSequence`, so different chains collide.
- The same identity feeds the resume compatibility hash, so resume accepts a changed pipeline too.

**Probes:**
- P2: a scorer changed from 0.1 to 0.9 returned **0.1, cached**.
- P3: a pipeline that always answers wrong scored **1.0, cached**, using the correct pipeline's cache entry.

### H-6. RAGAS scores are computed on a silent subset of samples, and the objective ignores that

**Claim:** RAGAS evaluation per sample; objective over trial metrics.

**Reality:**
- The README's pattern is `RagasEvaluator(metrics=(Faithfulness(),), llm=judge)`. It shares one metric object across all concurrent samples.
- RAGAS's `aevaluate` attaches `llm` to the metric if it's unset and **detaches it in `finally`** (`ragas/evaluation.py:330`). So one sample finishing can strip the judge from another mid-computation: `AssertionError: llm must be set to compute score`.
- With `raise_exceptions=False`, failed samples become `unavailable`, and the trial metric is the mean of whatever survived.
- `Objective.evaluate` never looks at `coverage` ([objective.py:58](../../src/tunarag/objective.py)).

**Real run:**
- The LangChain study logged 5 such assertion errors.
- Trial 0's faithfulness was computed on **4 of 8 questions (coverage 0.5)** yet scored 1.0 and tied for best.
- (The LangChain run's other RAGAS failures, `LLMDidNotFinish`, came from the audit harness's own 160-token judge limit. They show the same silent-subset effect.)
- **Workaround:** construct metrics with the judge attached, e.g. `Faithfulness(llm=judge)`.

---

## Medium severity

### M-1. Google ADK: `output_mapper` cannot expose retrieval evidence

**Claim:** README: "`output_mapper` receives the final ADK event, allowing retrieval evidence to be exposed for RAGAS."

**Reality:**
- In a normal tool-calling RAG agent, retrieved passages live in earlier tool-response events.
- The adapter passes only the final event and then deletes the session ([google_adk.py:93-123](../../src/tunarag/integrations/google_adk.py)).
- Real ADK study: **0 of 32** final events contained tool results.
- Retrieval metrics and RAGAS faithfulness are therefore impossible for ADK pipelines without workarounds.

### M-2. MLflow: a resumed study gets a second run, and the first stays RUNNING forever

**Claim:** "One MLflow run is created per study."

**Reality:**
- Run IDs live only in the callback object's memory ([mlflow.py:64](../../src/tunarag/integrations/mlflow.py)).
- `mlflow_resume.py`: after a kill and resume, the study has **2 runs**. One is `RUNNING` with step 0; the other is `FINISHED` with steps 1–3.

### M-3. The README's custom search-space parameter example crashes the optimizer

**Reality:**
- `EvenInteger`, copied verbatim from "Extension contracts", raises `TypeError: unsupported canonical value: EvenInteger` at study start.
- Strategy fingerprints hash the search space, and `canonicalize` only supports dataclasses and primitives ([serialization.py:34](../../src/tunarag/serialization.py)).
- Custom parameters work only if they are dataclasses, which the README doesn't mention.

### M-4. Documented settings that do nothing

- `seed` / `TUNARAG_SEED` and `artifact_dir` / `TUNARAG_ARTIFACT_DIR` are documented with defaults but never read by any code.
- `db_path` and `cache_dir` are not used automatically either: without `store=`, the optimizer uses an **in-memory** store.
- The quickstart does say "The default store is in memory", but the config table implies otherwise.

### M-5. Failures are reduced to a type name, so the real cause is invisible

- Trial errors store only `"{stage} failed: {ExceptionType}"` ([engine.py:488](../../src/tunarag/engine.py)).
- ADK error events become a fixed `AdapterError` message ([google_adk.py:83](../../src/tunarag/integrations/google_adk.py)), dropping ADK's `error_code` and `error_message`.
- Real run: 8 of 8 trials failed with only `adapter failed: AdapterError`. The actual cause, an agent instruction referencing a missing state variable, appeared only in ADK's own logs.
- Redacting secrets is good, but no diagnostic detail survives at all.

---

## Low severity

| ID | Finding | Where |
|---|---|---|
| L-1 | `TimeBudget` restarts from zero on resume | [engine.py:204](../../src/tunarag/engine.py) |
| L-2 | Dataset `version` depends on row order: reordering a CSV invalidates the cache and blocks resume | [dataset.py:139](../../src/tunarag/dataset.py) |
| L-3 | Two rows with the same question and no `id` → `DatasetError` with only `cause: ValueError` | [dataset.py:339](../../src/tunarag/dataset.py) |
| L-4 | Synthetic generation: one bad document discards the whole batch, including already-paid generations | [synthetic.py:154](../../src/tunarag/synthetic.py) |
| L-5 | After resume, `LLMSearch` replays failed and unfinished trials into its history (the original run only observed successes) | [search.py:266](../../src/tunarag/search.py) |
| L-6 | `MaxFailures(consecutive=True)` also counts cancelled trials | [stopping.py:137](../../src/tunarag/stopping.py) |
| L-7 | Canonical hashing turns floats into strings, so candidates `{"x": 0.5}` and `{"x": "0.5"}` collide | [serialization.py:31](../../src/tunarag/serialization.py) |
| L-8 | README "Limitations" still says "V0.2"; the package is 0.3.0 | README |
| L-9 | `test_ragas_evaluator_requires_optional_dependency` fails whenever RAGAS is installed, including the repo's documented live-test environment | `tests/test_evaluators.py:124` |

Environment notes: the project `.venv` is broken because its base Anaconda Python no longer exists. The system Python also has a stale `tunarag-python` 0.2.1 installed, which can mask `src/` changes.

---

## Verified working

**Under real models:**
- **LangChain:** factory per candidate, `input_key`/`output_mapper`, and tuning `top_k`, prompt and temperature.
- **LangGraph:** candidate parameters reach nodes through `config["configurable"]`; token usage is auto-discovered from the `AIMessage` in state.
- **Google ADK:** candidates reach tools through session state; every session is deleted afterwards (0 left); token usage is captured; concurrency of 4 trials × 8 samples works.
- **LLMSearch with a real LLM provider:** it receives past observations, proposals are validated and every candidate is distinct.
- **RAGAS:** a real judge scores answers. Faithfulness, plus the calibration test, pass in live L4/L5.
- **Synthetic dataset generation with a real LLM:** count, spans, provenance and `synthetic=True` all check out.
- **Cache:** an identical second study hit the cache on every trial, with zero provider tokens and identical scores.
- **Resume:** resuming a completed study returns without calling the provider; a hard kill resumes correctly.
- **MLflow (single process):** one run, FINISHED, objective history with one point per trial, secret-looking tag redacted.
- **Callbacks:** delivered in order, no callback failures.
- **Reports:** JSON and CSV export, `ranked_trials`, `metric_leaders`.

**By code reading and tests:**
- Objective formula, all 6 stop rules, RandomSearch determinism and replay.
- Store transactions, state transitions, leases and schema migration.
- Cache checksums, quarantine and expiry.
- Settings precedence.
- `Secret` redaction in events and reports; study config stored only as a hash.
- Framework-only adapters enforced.

---

## Reproduce

Create the environment:

```powershell
python -m venv .tmp/audit-venv
.tmp/audit-venv/Scripts/python.exe -m pip install -e ".[frameworks,ragas,mlflow,dev,live-test]" litellm
```

Run the offline probes; the first two need no API key:

```powershell
$env:PYTHONPATH = "src"; .tmp/audit-venv/Scripts/python.exe docs/audit-2026-11-21/scripts/probe_claims.py
```

```powershell
$env:PYTHONPATH = "src"; .tmp/audit-venv/Scripts/python.exe docs/audit-2026-11-21/scripts/probe_values.py
```

Then run the real-RAG sections. They need `OPENROUTER_API_KEY` in `.env`, and `apps.py` hardcodes the repo path. From `docs/audit-2026-11-21/scripts/`:

```powershell
../../../.tmp/audit-venv/Scripts/python.exe run_all.py langchain work
```

Swap `langchain` for `langgraph`, `adk`, `synthetic` or `data` to run the other sections.
