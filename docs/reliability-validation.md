# Bounded reliability validation

This add-on executes stages 3–6 of the [ordered quality plan](quality-validation-plan.md).
It tests framework integrations and optimization behavior, not a new product feature.
The package runtime and public API are unchanged. Paid execution is explicit opt-in;
ordinary CI never contacts a paid model.

## What each test proves

| Stage | Test | Assertions and evidence |
| --- | --- | --- |
| 3 | `test_reliability_quality` | Three seeded RandomSearch studies, two successful trials each, real LangChain PDF retrieval and OpenRouter generation/judging. Select winners only on two development questions; independently execute baseline and winners on four new held-out questions. Persist each SQLite study, selected parameters, answers, and judgments. |
| 4 | `test_reliability_adk` | Two real LLMSearch suggestions; official ADK agents call the official LangChain retriever tool. Concurrent evaluation uses unique sessions and session-owned tool context; assert retrieved count equals candidate `top_k`, model usage survives, sessions are deleted, and completed resume adds no provider calls. |
| 5 | Receipt reconciliation and negative guard checks | Count provider receipts including embeddings, generation, judges, suggestions and discarded replies. Exact costs must be nonnegative, complete, and match settled key usage before releasing unused reservations. Reject unpriced models, excess output, unauthorized tools and exhausted budgets before sending. |
| 6 | `test_reliability_recovery` and `test_reliability_load` | Kill a real-provider worker waiting for its second reply, wait for actual lease expiry, resume only unfinished work, and reload without calls. Exercise full LangChain PDF RAG with measured concurrency limits 1, 2 and 4. |

## Frozen quality protocol

`tests/live/reliability_questions.json` is frozen before new paid calls. Development
questions cover attention heads/key dimensions and feed-forward dimensions. The new
test questions cover shared embedding weights/scaling, Adam epsilon/beta2, dropout
locations, and inference length/early termination. Facts were checked against the
approved paper. These four questions do not enter search observations or selection.

ReferenceQualityEvaluator remains version 3 from the earlier calibration milestone.
It measures estimated semantic completeness and contradictions. It is not RAGAS,
human ground truth, or a statistical proof of improvement. Generation and evaluation
cache are off; embedding cache remains on. Search explores two of four configurations
for each seed, varying `top_k` (1 or 3) and brief/structured prompts while holding
chunk size 1000, overlap 80 and similarity retrieval fixed.

## ADK tools and session boundaries

`tests/live/adk_tools.py` uses ADK `Agent`/`InMemoryRunner`, the official
`google.adk.integrations.langchain.LangchainTool` bridge, and LangChain
`create_retriever_tool`. Retrieval remains framework-owned. The first model turn
must call `search_paper`; the second must answer without another tool call. A
callback rejects a third model turn before transport execution.

The only authorized tool takes a string `query` and returns local paper excerpts.
It is not a shell, browser, remote fetch or arbitrary execution tool. The real ADK
SDK/tool round trip is also tested with HTTPX MockTransport, without credentials.
Model usage records and runner-latency records are different components: two model
calls produce two model records plus one runner record, not two total records.

Candidate-specific runners are reused between concurrent samples, deliberately
testing same-runner session isolation. An owner ID assertion guards context state;
retrieval rows include session, tool query and actual returned count. LLM suggestions
contain search configurations and observations, never held-out references.

## Spending and provenance

The original cumulative authorization is $5, not $5 per stage. The private execution
wrapper reserves conservatively before every HTTPS OpenRouter request and enforces
a $4.75 active reservation ceiling. It prices approved models only, limits output
to 512 tokens, disables streaming and SDK retry multiplication, and allows only the
local retrieval tool in the ADK phase. Request and response journals survive failures.

With explicit user approval, 1,162 settled receipts reconciled exactly to provider
key usage of $0.29854430. Releasing $4.27816902 of unused reservations preserved the
original ledger, receipt history, $5 authorization and $4.75 ceiling. Gross historical
reservations may exceed the ceiling after release; active unsettled reservations may
not. Do not reset costs or discard old requests to create artificial headroom.

`tests/live/billing.py` validates settlement without mutating history. A missing
receipt, uncertain failure cost, nonfinite/negative cost, delayed key usage or exceeded
authorization prevents settlement. The private journal additionally labels embedding,
generation, evaluator and search requests. SDK token counts may be exact while an
application's price-based estimate is not a provider invoice.

TunaRAG trial usage is not a universal account-level billing ledger: embedding/index
construction, external evaluator/suggestion clients and a reply lost before commit
may not appear in committed trial usage. Provider-side receipts and account usage are
the spending authority for this campaign. Budget stopping rules cannot retroactively
cancel already accepted requests. Avoid concurrent campaigns sharing the same ledger.

## Real-provider recovery, precisely scoped

The parent test exposes a loopback gateway. Only the parent has the real key; a child
LangChain prompt/model worker gets a dummy key and a sanitized environment. The parent
forwards through the already guarded OpenRouter client, capturing costs even if the
worker dies. One controlled local 503 validates SDK retry handling without provoking
a real upstream outage. The parent SDK has retries disabled.

Trial one commits. For trial two, the provider completes and the gateway withholds
the paid reply; the test kills only its child process. This proves recovery from a
lost paid response, **not** knowledge of whether OpenRouter was still generating at
the instant of termination. The trial timeout is 30 seconds and recovery lease 90
seconds; the test waits for real wall-clock expiry rather than advancing the store
clock. The old attempt becomes abandoned and a new attempt succeeds. Completed
reload must make no additional requests.

This worker isolates persistence with a provider-backed LangChain prompt/model chain
and an approved paper excerpt. It is not the full retrieval benchmark or a test of
production distributed execution. Its search marker distinguishes persistence slots,
not RAG parameter quality. Full retrieval is exercised separately in the load and
quality campaigns.

## Running safely

Install `.[dev,live-test,live-adk-test]` in an isolated environment. Use an explicit
dotenv file and a dedicated OpenRouter key capped to your approved remaining budget.
Do not paste keys into command arguments or upload raw exception logs.

```powershell
python -m pytest tests/test_paid_payload.py tests/test_live_billing.py
python -m pytest tests/live/test_adk_tools_transport.py --live
python -m pytest tests/live/test_reliability.py --live --live-paid --live-campaign `
  --live-env=tests/live/.env --live-pdf="path/to/paper.pdf" `
  --live-request-limit=150 --basetemp=live-test-output/reliability
```

The public fixture supplies a request-count guard; the cumulative dollar journal used
for the reported run is private execution infrastructure, not automatically enabled
by this command. Maintain your own account cap and conservative spend guard before
running it. New `--basetemp` directories are required for retries so failed evidence
is retained. Start with individual test selectors, one paid process at a time.

## Results and limits

The new held-out estimated reference scores were baseline **0.750**, seed 1 **0.750**,
seed 4 **0.750**, and seed 7 **0.875**. Two winners did not improve on the baseline;
the third gained one partially covered fact. The inference-length question remained
incomplete. This is a small single-paper test, not a quality guarantee.

ADK tools/LLMSearch passed with four isolated sessions, four actual retrieval tool
calls and measured peak four active evaluations. The completed study reloaded
without provider calls. One initial harness setup failure was fixed without altering
package behavior; failed attempts and their costs remain in the private ledger.

Recovery passed with three paid responses: one committed, one lost at the gateway,
and one rerun. A single controlled local 503 produced four local HTTP requests;
it did not add a provider charge. The real lease wait was 88.02 seconds, with
attempt states succeeded/abandoned/succeeded. Completed reload added zero requests.
Two initial recovery harness setup failures (Windows text encoding and input mapping)
were fixed; neither sent a provider request.

Load checks passed with measured peaks **1, 2 and 4**, six successful trials total,
and no failed trials. Study durations were 13.25, 5.72 and 1.94 seconds respectively.
Later runs reuse warm embeddings and indexes: these times are **not** a controlled
speedup benchmark or production throughput promise.

All 1,263 provider receipts were HTTP 200 and reconciled to cumulative key usage of
**$0.32051424**, including the earlier milestones. This follow-up added 101 paid
requests costing **$0.02196994**: 16 embeddings ($0.00066994), 51 generation/tool-model
turns ($0.01361520), 32 evaluator calls ($0.00739360) and two suggestions ($0.00029120).
The same $5 authorization remains. Active conservative reservations are $0.68303816;
gross historical reservations $4.96120718 include the explicitly released amounts.

Source regression passed 187 tests with 28 opt-in skips; the isolated installed
wheel passed 179 with 29 skips. Real optional-dependency checks passed 10 nonpaid
tests. Formatting, lint, strict typing, distribution build and strict documentation
build passed. RAGAS emits existing wrapper deprecation warnings; the real scoring
campaign from the earlier milestone remains separate from this reference judge.

Private evidence is `live-test-output/comprehensive/reliability-summary.json` and
`reliability-evidence.zip`, including passing JUnit files, frozen questions,
answers/verdicts, tool sessions, recovery and load measurements. The archive is
credential-scanned and excludes keys, the PDF and raw worker logs.

Still outside this campaign: native Gemini/Vertex authentication, hosted authenticated
MLflow, scanned-PDF OCR, large private corpora, real upstream fault injection,
multi-host execution and sustained production-scale capacity. Do not represent these
as supported or validated solely because this bounded campaign passes.
