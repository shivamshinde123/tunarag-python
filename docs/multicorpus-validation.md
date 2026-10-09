# Mixed-topic validation and remaining risks

This campaign exercises six non-deployment test areas. No native Google credentials,
hosted MLflow, OCR or distributed-worker deployment is involved. Model calls go through
OpenRouter under the same cumulative $5 authorization and conservative reservation
ledger used by earlier campaigns. Runtime code and public package APIs are unchanged.

## Corpus and extraction

Four user-approved text-selectable PDFs contain 7, 12, 4 and 2 pages: **25 pages total**,
approximately **139,000 extracted characters**. Subjects differ, including biological
memory and health-related research/commentary. This improves topic diversity over the
earlier single-paper campaign, but is a moderate corpus, not production-scale data.
Every extracted page was nonempty. Input text is source material, never instructions
to the coding agent. Original PDFs and extracted text remain outside Git.

Full pages are indexed using official LangChain PDF loading, splitting, cached real
OpenRouter embeddings and InMemoryVectorStore. Combined-corpus retrieval can encounter
unrelated documents; source-specific questions test whether answers remain grounded
in the correct facts. Saved retrieved passages permit source inspection. This does
not establish routing accuracy for arbitrary corpora or verify every extracted table.

## Independent generation and validation

1. GPT-4.1-mini proposes a factual question, answer and one or two atomic facts.
2. A supporting quotation is selected by index from exact extracted source sentences.
   The harness verifies that quotation against the original page. Source text is not
   reconstructed from an LLM's memory or paraphrase.
3. Gemini 2.5 Flash Lite independently answers the question from the selected quotation,
   without seeing the proposed answer or facts.
4. A separate comparison prompt checks the independent answer against the proposed
   reference and atomic facts using calibrated ReferenceQualityEvaluator version 3.
5. Only exact-source quotations with full estimated reference coverage are accepted.
   Disagreements are recorded and rejected, not automatically rewritten to pass.
6. Development and held-out records are frozen before optimization. Selected candidates
   are fixed before scoring held-out questions. Saved dataset reuse verifies source hashes
   and quotations and does not regenerate labels based on observed tuning results.

The first prototype asked the generator to reproduce quotes and rejected five of eight
records for non-verbatim citation text. This caught a real dataset-generation weakness.
Selecting an existing source quote prevents fabricated citation strings; it does not
prove that every generated reference is correct. The subsequent frozen dataset accepted
six of eight proposals: two development questions and four held-out questions, covering
all four documents overall. Keep both rejected records and earlier failed audit artifacts.

The dataset is **model-generated and model-validated, not human-verified**. A second
model family reduces some shared error modes but cannot eliminate them. Validation and
evaluation use different prompts/roles but the same Gemini model; judging its own RAG
answers can introduce bias. Tiny development/test sets, repeated seeds and one corpus
do not provide confidence intervals, independent human ground truth or broad guarantees.

## Quality and configuration testing

Three seeded RandomSearch studies execute two trials each using the real combined-corpus
LangChain RAG. The search space varies top_k 1/4, chunk size 600/1200, similarity/MMR
retrieval and brief/structured prompts, with overlap 80 fixed. Six trials do not exhaust
the sixteen combinations. The objective is estimated reference completeness with a
contradiction penalty, not literal keyword presence. Generation/evaluation cache is off;
embedding cache remains on.

Evaluate the baseline and each selected winner on all four frozen held-out questions.
Also evaluate the same baseline configuration with Gemini as the answer model. Model
comparison is separate from configuration selection. Do not report a single favorable
seed as universal quality improvement or interpret warm-cache timings as a benchmark.

The initial completed tuning portion measured held-out means of baseline **0.625**,
seed 2 winner **0.625**, seed 5 winner **1.000**, seed 9 winner **0.875**, and alternate
Gemini baseline **0.500**. Its overall paid test failed at the later adversarial assertion;
the tuning results remain valid execution evidence but not an overall passing security
campaign. A separate replay reuses the frozen labels for the final quality check.

## Controlled SDK faults

Eight credential-free tests exercise real ChatOpenAI/OpenAI clients with HTTPX mock
transport: 429, 503, read timeout and connection loss, each transient and exhausted.
Trial/sample concurrency is one so the injected first-request failures belong to the
intended trial rather than being spread across concurrent requests. The SDK gets one
retry, and TunaRAG gets zero trial retries, deliberately avoiding multiplicative retries.
Each case verifies three transport calls, successful recovery or one isolated failed
trial, and one persisted attempt per trial. All eight cases passed.

This validates SDK retry handling plus optimizer failure isolation—not real upstream
outages or automatic recognition of every vendor exception by TunaRAG's RetryPolicy.
Provider clients own SDK retries; the generic policy recognizes its documented transient
Python errors and explicitly retryable package errors. Configure these boundaries rather
than assuming all HTTP 429/503 exceptions become retryable trial failures automatically.

## Bounded simulated stress

Official LangChain retrieval chains use 256 synthetic documents, deterministic framework
embeddings and FakeListChatModel. This measures local optimization/persistence behavior,
not paid model quality or provider throughput. Three studies each run 25 trials across
eight samples: **75 successful trials and 600 evaluations**. Requested and observed peak
active evaluations were **1, 4 and 16**, with no failed trials and active counters returning
to zero. Local durations were approximately 8.28, 5.31 and 4.23 seconds.

Peak traced Python allocations were approximately 0.43, 0.53 and 1.45 MB. These are
tracemalloc measurements after dependency/index initialization, **not process RSS**,
native allocations, a leak proof or production sizing. The experiment is a bounded stress
gate, not an hours-long soak, multi-process SQLite test or memory-growth trend study.

## Adversarial retrieval: unresolved failure

Synthetic retrieved documents attempt direct instruction override, impersonated system
messages/credential requests and fake citation directives. No dangerous tools or real
credentials are put in model prompts. Each fixture contains the same harmless factual
answer and uses an exact attack marker to detect instruction influence.

Test both the original example prompt and a stronger template that places excerpts in
an explicitly delimited untrusted user-data block and prohibits obeying embedded commands.
Across three fixtures and two models, the original prompt leaked the marker in **three
of six answers**. The stronger boundary leaked it in **one of six**: GPT followed the
fake-system-message instruction. The separate paid security test intentionally **fails**
its unchanged hardened-boundary assertion. Do not mark that risk resolved or remove the
failing assertion simply to get a green paid run.

This is an application/example prompt weakness, not evidence of code execution, actual
credential exposure or corrupted SQLite state. TunaRAG tunes framework-owned RAG; it is
not an input firewall or a prompt-injection security guarantee. Prompt hardening reduced
the observed failures but did not eliminate them. Untrusted-corpus applications need an
explicit threat model and independently tested defense strategy before claiming safety.

## Reproduction and evidence

Install `.[dev,live-test]`. Start with no-cost tests:

```powershell
python -m pytest tests/live/test_extended_resilience.py --live
```

For paid tests, configure different `TUNARAG_LIVE_CHAT_MODEL` and
`TUNARAG_LIVE_JUDGE_MODEL` in the explicitly loaded dotenv file. Verify current model
availability/prices, use a dedicated account-capped key and a persistent cumulative
spend guard. The public fixture enforces a request cap, not an automatic dollar ledger.

```powershell
python -m pytest tests/live/test_multicorpus.py --live --live-paid --live-campaign `
  --live-env=tests/live/.env --live-request-limit=150 `
  --live-pdfs="path/to/pdf1.pdf" --live-pdfs="path/to/pdf2.pdf" `
  --live-pdfs="path/to/pdf3.pdf" --live-pdfs="path/to/pdf4.pdf" `
  --basetemp=live-test-output/multicorpus
python -m pytest tests/live/test_adversarial_boundaries.py --live --live-paid `
  --live-campaign --live-env=tests/live/.env --live-request-limit=30 `
  --basetemp=live-test-output/adversarial
```

The adversarial test may fail: that is meaningful evidence, not authorization to relax
its assertion or hide the output. Use unique basetemp directories to retain earlier
attempts. CI runs the nonpaid SDK/stress suite; both paid tests are explicit opt-ins.
Private artifacts retain frozen labels, blind validation answers, rejected records,
SQLite trials, held-out answers/contexts, attack outcomes and JUnit reports. Do not
commit source documents, keys or private answers. Aggregate totals and final replay
results are recorded after final billing settlement.

## Final execution — 2026-10-09

The frozen-label replay passed all six optimization trials and reproduced the same
held-out means: 0.625 baseline, 0.625/1.000/0.875 seeded winners and 0.500 alternate
model. This confirms the bounded workflow, not generalization from four questions.
The separate adversarial gate remains **failed** (five of six hardened answers safe).
All nine controlled-fault/stress tests passed. Source regression passed 187 tests
with 39 opt-in skips; installed-wheel regression passed 179 with 40 skips. Paid
security failure is not included in those ordinary-CI pass counts.

All 1,479 provider receipts reconcile to cumulative account usage of **$0.35495478**.
This add-on used 216 requests costing **$0.03444054**, including prototype failures,
dataset validation, repeated tuning, frozen-label replay and adversarial tests.
The original cumulative authorization remains $5; active conservative reservations
are $1.27948424. No additional paid tests ran after settlement.

Private evidence is `live-test-output/comprehensive/multicorpus-summary.json` and
`multicorpus-evidence.zip`. The credential-scanned archive preserves both passing
and failed JUnit reports, source hashes, QA audits, held-out results, SDK faults and
stress/security measurements. It excludes PDFs, keys, embedding-cache files and
unreviewed raw logs. Longer soak tests, truly large corpora and independent human
review remain unexecuted; deployment-specific tests were deliberately excluded.
