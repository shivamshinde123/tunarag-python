# Comprehensive end-to-end verification

## Scope and interpretation

This campaign complements `live-integration-test-plan.md`. It verifies framework
execution and release correctness, then measures quality separately. Passing a
correctness test does not prove universal quality improvement or production readiness.
Live quality is measured on one public research paper, one generation model, and one
judge model. Other domains and providers need their own validation.

The extended suite requires **three explicit gates**: `--live`, `--live-paid`, and
`--live-campaign`. Ordinary CI never enables paid requests. Missing gates produce
skips, not passes. Install `.[live-test]` in a separate environment.

## Executable coverage map

| Area | Evidence | Acceptance |
| --- | --- | --- |
| Public values and identities | `test_domain.py`, `test_properties.py`, `test_package.py` | Typed values, canonical hashes, exports, and invalid input handling. |
| Dataset ingestion | `test_dataset_ingestion.py` | JSON/JSONL/CSV normalization, validation, splits, deterministic identities. |
| Framework boundaries | `test_framework_boundary.py`, `test_framework_compatibility.py`, `test_google_adk_integration.py` | Reject unsupported runtimes; execute supported framework objects; isolate ADK sessions. |
| README examples | `test_readme_tuning.py`, `test_usage_documentation.py`, `test_reference_example.py` | Every extracted Python fragment executes with its declared fixtures and assertions. |
| Complete live pipeline | `live/test_campaign.py::test_full_pdf_campaign` | Real PDF loading, splitting, embeddings, retrieval, generation, tuning, SQLite, MLflow, export, and independent winner reuse. |
| Search | `test_search.py`, `test_llm_search.py`, live campaign | Seeded search, typed validation, invalid suggestions, bounded fallback, remote suggestions. |
| Objectives/stopping | `test_objective_and_stopping.py`, `test_engine.py`, live campaign | Correct direction, weights, unavailable/estimated values, stopping rules, and ranking. |
| Retry/failure isolation | `test_retry.py`, `test_resilience.py`, `live/test_ragas.py` | Bounded backoff and timeouts; real SDK with injected 429/503/malformed JSON isolates failed trials without network calls. |
| Process interruption | `test_process_recovery.py` | Abrupt worker exit during a running trial; new process recovers only unfinished work; third process reloads without execution. |
| Cache | `test_cache.py`, `test_resilience.py`, live smoke | Expiry, corruption, policies, versioned identity, zero-call cache reuse. |
| Concurrency/events | `test_concurrency.py`, `test_callbacks.py`, live campaign | Bounded work, ordered observations/events, callback isolation, matching real MLflow metrics. |
| Reports/privacy | `test_result_reporting.py`, `test_errors.py`, `test_config.py` | JSON/CSV export, exact/estimated usage, redacted errors and secrets. |
| Synthetic QA | `test_synthetic.py`, live campaign synthetic check | Valid provenance and usage; generated answers remain explicitly unreviewed. |
| Real evaluation | `live/test_ragas.py`, `live/test_provider.py`, live campaign | Non-LLM scores, calibrated faithfulness, context recall, finite scores through `RagasEvaluator`. |
| Distribution | Clean wheel installation, full suite without source-path override | Imported code comes from the installed wheel, not the checkout. |
| Compatibility | `.github/workflows/ci.yml` | Windows/Linux and Python 3.10–3.13; real optional framework and evaluation jobs. |

## Live experiment protocol

Use the user's text-selectable **Attention Is All You Need** PDF through LangChain's
`PyPDFLoader`. Source page numbering in question references is one-based; loader
metadata is zero-based and converted when evaluating retrieval. Fail before tuning
if expected source text or page count is absent. This fixture is paper-specific.

`tests/live/attention_questions.json` contains 30 manually authored reference records:

- 10 development questions, available only to optimization.
- 14 held-out factual questions and 6 robustness questions, unavailable to search.
- Robustness cases include unsupported questions, false premises, and a multi-page
  comparison. Their scores are measured, not assumed to pass.

These are agent-authored references, not independently human-reviewed gold labels.
Review them before using scores as product-quality claims. Some development topics
overlap the earlier smoke tests; the held-out partition is protected from search,
not a claim of completely novel subject matter.

Run the Cartesian product of **LangChain/LangGraph × RandomSearch/LLMSearch**. Each
campaign runs four distinct candidates over five typed parameters:

| Parameter | Values | Actual pipeline effect |
| --- | --- | --- |
| `top_k` | 1, 3 | Retriever result count. |
| `chunk_size` | 500, 1000 characters | LangChain recursive splitter boundaries. |
| `overlap` | 0, 80 characters | Splitter overlap. |
| `search_type` | similarity, mmr | LangChain vector-store retriever algorithm. |
| `prompt_style` | brief, structured | Document-chain system instructions. |

This is a bounded search, **not exhaustive enumeration** of all 32 combinations.
Parameter construction is recorded in each manifest. LangGraph orchestrates the same
official retrieval/document chain in a compiled graph; it is not a replacement
handwritten retrieval implementation. Four trials must succeed, be unique, vary at
least two dimensions, and rank according to the declared objective.

The development objective combines answer-term coverage (0.6), source-page recall
(0.25), estimated generation cost benefit (0.1), and latency benefit (0.05). Normalize
quality to [0,1], cost to [0,$0.01], and latency to [0,45s]; minimize cost/latency.
Answer-term coverage is an explicit lexical diagnostic, **not semantic correctness**.
Page recall measures supporting-page retrieval, not exact passage relevance. For
unanswerable questions, page recall is neutral (1.0); inspect abstention separately.

Generation costs use the checked GPT-4.1-mini prompt/completion rates and are marked
estimated. The private campaign launcher verifies these rates before sending any
paid requests. For different models, update rates and verify them again. The package
does not automatically know evaluator, embedding, or search-provider dollar costs.

After selecting the winner:

1. A fresh optimizer resumes the completed SQLite study with zero new provider calls.
2. Changing the explicit prompt identity rejects incompatible resume before calls.
3. MLflow's FINISHED run and full metric history match authoritative trial records.
4. Save winning parameters as JSON and reconstruct the pipeline outside `Optimizer`.
5. Run baseline and winner on all 20 held-out questions, saving every answer/context.
6. Use real RAGAS faithfulness and context recall on two prespecified held-out questions
   for both configurations. Do not claim RAGAS coverage of all 20 questions.
7. Report baseline/winner scores even when the winner regresses. Do not choose a new
   winner after inspecting held-out answers.

For more complete semantic coverage, use `test_live_full_held_out_scoring` with
`--live-held-out-report` pointing to a completed campaign's `held-out.json`. Score
both configurations on all 17 answerable/false-premise/multi-page questions, using
faithfulness and context recall. The three unsupported questions use explicit
abstention checks instead: reference-context recall is not meaningful for an answer
that the paper does not contain. Reuse saved answers; do not rerun generation or
select a new winner. Run this separately for each search strategy with an approved
remaining allowance. Its result is 34 scored responses and 6 not-applicable responses.

The finite categorical campaign enumerates 32 valid configurations and asks the LLM
to select an unused configuration index using a strict JSON-schema enum. Convert that
selection back to its typed candidate and validate it through TunaRAG. This specific
test provider is not a general solution for unbounded numeric search spaces.
Prompt-only JSON instructions and JSON-object mode produced invalid suggestions;
a full-object schema then exposed repeated proposals. Original failed evidence is
retained. Excluding already-proposed indices prevents costly duplicate loops without
changing the core strategy or accepting invalid values. Do not count a random fallback as a verified remote
suggestion. See [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
for the response-format contract. Invalid proposals/fallback remain covered offline.

Repeat the elementary judge calibration three times. This detects obvious instability;
it does not provide confidence intervals for all paper answers. Live synthetic QA uses
the sanitized source fixture and stores provenance, not the held-out labels.

## Execution

Example for one bounded campaign, after explicit budget authorization and provider-side
key limiting:

```powershell
.tmp/live-venv/Scripts/python.exe -m pytest 'tests/live/test_campaign.py::test_full_pdf_campaign[random-langchain]' --live --live-paid --live-campaign --live-pdf='path/to/NIPS-2017-attention-is-all-you-need-Paper.pdf' --live-env=tests/live/.env --live-request-limit=250 --basetemp=live-test-output/random-langchain --junitxml=live-test-output/random-langchain.xml
```

Other node IDs are `random-langgraph`, `llm-langchain`, and `llm-langgraph`. Run the
synthetic/calibration checks separately with `-k 'not full_pdf_campaign'`. Run original
smoke and credential-free dependency checks as described in the smoke-test plan.

The public harness has a shared **request cap** (default 40, allowed 1–500), not a
guaranteed dollar cap. Large limits require deliberate authorization. The current
private execution uses a persistent cross-process monetary reservation ledger, an
allowlist of priced models/endpoints, bounded output, and a $4.75 reservation ceiling
under the user's $5 total allowance. It includes previously observed key usage.
Reservations are deliberately conservative estimates, not actual charges. Provider
key usage remains the billing authority and can update after a response. Never reset
the ledger or blindly rerun failed phases. Do not run other workloads on the same key.

Each `--basetemp` is unique: pytest can delete the directory it is given. Preserve
failed artifacts before targeted retries. Keep credentials, PDFs, answers, provider
responses, SQLite files, and unreviewed logs out of Git. Only sanitized fixtures,
test code, documentation, and aggregate verification evidence belong in a PR.

## Process-recovery semantics

The subprocess test uses a real LangChain runnable, real optimizer, and real SQLite
store. The worker completes one trial and exits immediately during the second. The
resume process uses an advanced store clock to simulate lease expiration without
waiting 90 seconds. It does not bypass lease validation. The completed first trial
must not execute again; the interrupted trial receives an abandoned attempt and a
successful new attempt. This is a deterministic crash test, not a real-provider
mid-request interruption test. Providers may charge for a request whose result was
lost in a crash; local recovery cannot undo that charge.

## Remaining boundaries

Do not label these unexecuted cases as passed:

- Additional model providers, hosted/authenticated
  MLflow, framework-native durable checkpoints, distributed/multi-host workers.
- Induced upstream 429/outage behavior; transient engine failures are injected offline.
- PDF OCR, encrypted PDFs, huge corpora, malicious source-document instructions,
  production load, billing reconciliation for every evaluator/search call.
- Semantic human review of every answer, confidence intervals, multiple corpora,
  repeated independent optimization campaigns, and universal quality improvement.

If a weakness appears, record it as a release limitation or bug with a reproducer.
Do not alter assertions or reference labels merely to make a paid run pass.

The separately gated ADK/OpenRouter add-on is described in
[Live Google ADK validation](live-google-adk-testing.md). Its smaller question set
and provider boundary are explicit; it is not native Gemini/Vertex validation.
