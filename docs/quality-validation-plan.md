# Ordered quality and reliability test plan

## Aim and scope

Prove that TunaRAG can measure useful answers, select configurations without test
leakage, and preserve reliable execution. Earlier framework campaigns established
the main execution paths, but high faithfulness and context recall did not ensure
answer completeness. Start with that gap instead of building unrelated infrastructure.

This plan does not claim native Gemini/Vertex, OCR, hosted authentication, or
distributed workers are implemented. Test those only when the supported application
integration or explicit new implementation requires them.

## Order and stage gates

| Order | Tests | Acceptance / exit gate | Status at start |
| --- | --- | --- | --- |
| 0 | Refresh provider usage, model prices, request guard and existing cumulative ledger; freeze references and facts. | Same cumulative $5 authorization, no credential exposure, reserve costs before sends; never reset prior spending. | Required before paid calls. |
| 1 | Calibrate a completeness-aware reference judge using complete/paraphrased/partial/wrong/negated answers, inappropriate and appropriate abstention, fabricated claims, instruction injection, and the observed wavelength-only answer. Repeat each twice. | All 20 expected scores match; complete/paraphrased beat partial; wrong/fabricated/injected answers score zero. Strict verdict parsing and versioned fingerprints pass offline. | Completed with prompt version 3. |
| 2 | Rescore existing frozen baseline/winner answers: ten stratified LangChain held-out questions and three ADK questions, both configurations. | Every response receives valid scores; identical baseline/winner question sets; no regeneration or selecting a new winner from test labels. Publish paired changes, individual regressions and answer samples. Improvement is not artificially required. | Completed: 26 answers scored. |
| 3 | New quality-aware tuning plus repeated optimization seeds. | Use development labels only; freeze selected candidates before held-out evaluation; run at least three seeds and retain negative results. Report dispersion and failures, not only the best run. | Planned, not covered by retrospective rescoring. |
| 4 | ADK LLMSearch, actual framework retrieval tools and concurrent sessions. | Valid suggestions apply; bounded tool/model calls; independent session state and cleanup; deterministic trial/event ordering. First verify a guarded tool-capable transport offline: current private paid guard deliberately rejects tools. | Planned after quality gate; no bypass of guard. |
| 5 | Whole-run usage and budget exhaustion. | Account for adapter generation, embeddings, evaluators, suggestions and retries separately; compare recorded usage to provider bill; reject new sends after a cap. In-flight calls may still finish and incur charges. | Existing guard checks are partial evidence, not full reconciliation. |
| 6 | Real-provider interruption/resume, then workload-specific load. | Kill a provider-backed worker mid-study; preserve committed trials, recover expired attempts and report ambiguous charges. Increase concurrency gradually against an explicit target with separately allocated reservations. | Planned; existing deterministic crash tests are not this live scenario. |

Stages 3–6 must remain visibly pending until executed. Completion of stages 1–2
does not establish production readiness or statistical generalization. If calibration
fails, preserve the verdicts and investigate before interpreting held-out scores.

## Reference-quality scoring

`tests/live/attention_quality_rubric.json` adds atomic facts for ten existing held-out
records without editing their frozen questions or reference answers. Facts capture
relationships and units, not just keywords. Correct abstention is required for the
unanswerable H100 question; false premises must be corrected explicitly.

`ReferenceQualityEvaluator` is a test-harness implementation of the existing
pluggable evaluator contract. It makes one structured-output OpenRouter judge call
per answer. It returns:

- `quality.completeness`: fraction of required atomic facts actually communicated.
- `quality.contradiction`: 1 if the answer contradicts a rubric fact, otherwise 0.
- `quality.reference_score`: completeness, or zero when a contradiction is found.

These scores are **estimated LLM judgments**, not exact truth. The judge receives
question, reference, facts and answer—not retrieved context—so retrieved support
cannot substitute for answer completeness. Unsupported facts outside the brief
reference are not comprehensively assessed; retain separate faithfulness checks and
manual review. A high reference score alone is insufficient to establish safety.
Fingerprint the rubric, judge model and prompt version to invalidate stale caches.

## Execute the initial stages

Offline checks run with ordinary tests:

```powershell
python -m pytest tests/test_reference_quality.py
```

Paid calibration requires all three live gates:

```powershell
python -m pytest tests/live/test_quality.py::test_live_reference_judge_calibration --live --live-paid --live-campaign --live-env=tests/live/.env --live-request-limit=30 --basetemp=live-test-output/quality-calibration
```

After passing calibration, pass existing report paths to the held-out check:

```powershell
python -m pytest tests/live/test_quality.py::test_live_saved_held_out_answer_quality --live --live-paid --live-campaign --live-env=tests/live/.env --live-quality-report="path/to/langchain/held-out.json" --live-quality-report="path/to/adk/held-out.json" --live-request-limit=40 --basetemp=live-test-output/quality-held-out
```

Install `.[live-test]` for paid tests. Request limits alone are not dollar limits:
use a provider-side key limit and the approved private cumulative reservation guard
for this execution. Use unique temporary paths because pytest cleans `--basetemp`.
Save every verdict incrementally, including failures; do not repeat generation to
rescore saved answers. Judge tokens appear in the quality evidence, not magically
in the original optimizer's adapter-usage total. Never commit keys or private results.

## Evidence and review

Record model/dependency versions, reference/rubric fingerprints, question IDs,
repeats, verdicts/reasons, estimated scores, provider-reported tokens, paired changes,
exact test counts and observed cumulative spending. Review the known positional-
encoding under-answer, numeric role swaps, abstention, and multi-fact omissions.
Clearly separate original live pipeline evidence from retrospective judging.

Initial execution results are kept under the ignored `live-test-output/comprehensive/`
tree. Update this plan's results section after execution; never mark pending stages
passed merely because their test code exists.

## Initial execution results — 2026-10-09

Stages 0–2 are complete; stages 3–6 are pending. Nine focused offline checks passed,
including a real LangChain runnable and optimizer selecting the complete answer
with the reference-quality objective. Full source regression passed 174 tests with
23 opt-in skips; isolated built-wheel regression passed 166 with 24 skips.

Initial calibration caught the judge inferring different frequencies from a plural
noun. Tightening entailment rules passed that calibration, but manual held-out
review then caught a second mistake: inferring both sine and cosine from a generic
wavelength description. The observed answer became a golden regression. Prompt
version 3 requires names or explicit formulas for separately requested functions;
all 20 live calibration comparisons then passed. Expected scores and original
reference answers were not relaxed. Earlier verdicts remain in private evidence.

| Estimated reference score | Baseline | Previously selected winner | Improved / regressed / unchanged questions |
| --- | ---: | ---: | --- |
| LangChain, 10 held-out questions | 0.600000 | 0.866667 | 3 / 0 / 7 |
| ADK, 3 held-out questions | 0.444444 | 0.777778 | 1 / 0 / 2 |

The ADK positional-encoding under-answer now receives only partial completeness,
despite its earlier RAGAS faithfulness and context recall of 1. The LangChain winner
still fails to correct the feed-forward dimension false premise and omits a fact
in the multi-part training question. These are application-quality limitations,
not evidence that the optimizer failed to execute.

This is **retrospective judging of existing winners**, not new tuning using these
metrics. Held-out review informed judge refinement, so these scores are diagnostic,
not an untouched confirmatory benchmark. Freeze the final judge and use new unseen
questions for a later confirmatory assessment. Small samples and LLM variability
still require manual review and repeated independent trials.

The refreshed observed cumulative provider usage was $0.29854430 of the same $5
authorization; this stage added $0.02236720 including earlier attempts. Private
conservative cumulative reservations reached $4.57671332, below the $4.75 guard
ceiling. Further paid stages must fit remaining reservations or obtain an explicit
budget-policy change; do not silently reset the ledger based on lower actual bills.
No further paid stages ran during this initial milestone.

Local evidence: `live-test-output/comprehensive/quality-results.md`,
`quality-summary.json`, and `quality-evidence.zip`. Raw judge verdicts, calibration
attempts, usage, frozen facts, and passing JUnit reports are included in the
credential-scanned archive; keys and original PDF data are not.

## Follow-up execution — 2026-10-09

Stages 3–6 have now passed within the bounded scope documented in
[reliability validation](reliability-validation.md). Three two-trial quality-aware
studies selected candidates before four new held-out questions were evaluated.
Estimated held-out means were baseline 0.750, seed 1 0.750, seed 4 0.750 and seed 7
0.875; improvement was not universal and the inference-length answer remained partial.
These small-sample scores do not establish generalization.

ADK LLMSearch produced two valid suggestions, with four model-directed framework
retrieval calls and four isolated concurrent sessions. Reload was provider-free.
Real-provider lost-response recovery preserved the committed trial, waited for actual
lease expiry and recovered the unfinished attempt. Load checks measured peaks 1/2/4.

Explicit user approval permitted reconciliation of 1,162 settled receipts and release
of unused reservations while retaining full history, the $4.75 active ceiling and
the original cumulative $5 cap. Final 1,263 receipts reconcile to $0.32051424 provider
usage; this follow-up cost $0.02196994 including setup retries and the lost paid reply.
It does not test a real upstream outage or production-scale/distributed capacity.
