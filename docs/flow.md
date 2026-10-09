# TunaRAG Code Flow

> V0.3 scope: TunaRAG tunes genuine LangChain runnables, compiled LangGraph graphs, and Google ADK 2.x runners through official adapters. Handwritten RAG adapters are unsupported. Evaluators, search strategies, and callbacks remain extensible.

## Current flow

```text
caller
  -> Settings.resolve(defaults, selected TOML, known environment, overrides)
  -> construct Candidate, MetricValue, and UsageRecord
  -> load EvaluationDataset records and derive a content version
     -> normalize and validate canonical EvaluationExample values
     -> optionally assign deterministic grouped splits
  -> optionally generate SyntheticQA from approved SourceDocument values
     -> validate counts/spans/usage -> create provenance-bearing EvaluationExample values
  -> sample SearchSpace through seeded RandomSearch
  -> aggregate metrics through Objective
  -> evaluate trial, cost, time, target, stagnation, and failure conditions
  -> SQLiteStore.initialize or migrate to schema version 2
  -> create and run study -> atomically reserve unique ordered trial
  -> start leased attempt -> execute outside transaction
  -> atomically commit attempt, metrics, usage, terminal trial, and event
  -> abandon expired leases -> list recoverable trials -> replay ordered events
  -> CacheKey.from_parts
  -> SQLiteCache.put -> get -> verify checksum/TTL -> hit or explicit miss status
```

Canonical serialization produces deterministic JSON and domain-separated hashes. SQLite owns
durable lifecycle, observations, events, and cache state. Immediate transactions allocate
monotonic sequences; short terminal transactions preserve all-or-nothing outcomes. Attempt
leases make interrupted running trials discoverable without reusing attempt numbers. A corrupt
cache payload is quarantined and never returned. The optimizer is the sole current entry point
that executes adapters and evaluators. Package boundaries translate contextual failures into
structured errors.

## Implemented optimizer flow

```text
Optimizer.aoptimize
  -> fingerprint components and create running study
  -> strategy.suggest -> reserve unique candidate and sequence
  -> start leased attempt
  -> read compatible cached metrics or execute candidate
  -> materialize finite dataset -> bounded timed sample workers
  -> aggregate metric means, coverage, and confidence
  -> Objective.evaluate
  -> on transient failure: atomically finish attempt with usage -> backoff -> new attempt
  -> on success: commit metrics, usage, attempt, trial, and event atomically
  -> write successful uncached metrics after commit
  -> dispatch newly durable events to callbacks in sequence order
  -> strategy.observe committed success
  -> evaluate stop conditions or continue
  -> complete study -> build OptimizationResult and UsageSummary
  -> rank objective/metric views or export redacted JSON/CSV reports
  -> optional MLflowCallback reads committed trial state and mirrors it best-effort
```

Adapter, evaluator, and objective exceptions become redacted failed-trial summaries and do not
stop the study. Retryable failures use a bounded `RetryPolicy`; sample calls and whole-trial
execution have independent deadlines. Cache hits recompute the objective and report zero
current-run usage. Cache failures append diagnostic events and fall back to execution.
Cancellation commits the active trial as cancelled, cancels the study, and is re-raised.
Strategy failures are study-level failures because candidate generation or state observation
cannot safely continue. Candidate reservations fill a bounded trial batch; completed summaries
and strategy observations are then applied in trial-sequence order. Callback dispatch uses a
per-study async lock so concurrent trial events remain ordered and nonduplicated.

Callbacks never run inside SQLite transactions. The optimizer advances a per-study event cursor
and dispatches committed events at study, reservation, attempt, retry, cache, and terminal
boundaries. Callback exceptions append `callback.failed` with redacted type-level diagnostics;
these diagnostic events are skipped by dispatch to prevent recursion. Resume initializes the
cursor at the pre-resume event tail, so callbacks receive new recovery/progress events rather
than historical duplicates.

## Implemented resume flow

```text
Optimizer.aresume
  -> load study and compare the current semantic configuration hash
  -> reject failed/cancelled studies and running attempts with live leases
  -> abandon expired attempts scoped to the selected study
  -> rebuild terminal summaries, objective values, usage, attempts, and cache markers
  -> replay successful observations (or strategy-specific replay)
  -> continue pending and recoverable trials before suggesting new candidates
  -> persist stop reason -> complete study -> rebuild OptimizationResult
```

Completed compatible studies are read and replayed without adapter/evaluator execution. A
`Fingerprintable` component can contribute stable secret-safe semantics to study and cache
identity. `RandomSearch` fingerprints its search space and seed and verifies each replayed
candidate while advancing its private generator. Live leases cause a retryable `ResumeError`
rather than unsafe duplicate execution. Failed and cancelled studies remain terminal.

## Target optimization flow

```text
Optimizer.aoptimize
  -> resolve and validate inputs
  -> create or resume study; recover attempts and replay observations
  -> suggest, validate, deduplicate, and reserve candidate
  -> read compatible cache or execute bounded adapter samples
  -> collect usage; evaluate and aggregate metrics/objective
     -> MetricEvaluator calls one sync/async numeric scorer, or
     -> RagasEvaluator explicitly maps one sample, lazily imports RAGAS, and calls aevaluate
  -> commit terminal state
  -> notify strategy and post-commit callbacks
  -> evaluate stopping rules
  -> repeat or return OptimizationResult
```

Strategies observe committed outcomes only. Provider calls, user code, sleeps, and callbacks
never run in database transactions. Resume compares semantic fingerprints. Trial and sample
concurrency are bounded separately, and a trial failure is isolated unless policy stops the
study. Dependencies point from public contracts through search/evaluation/storage into
orchestration, then outward to optional integrations and examples.

## Reference example flow

```text
examples/quickstart.py
  -> create a canonical EvaluationDataset from records
  -> configure an IntegerRange search space for top_k
  -> pass LangChainAdapter and MetricEvaluator to Optimizer
  -> run the safe synchronous entry point
  -> persist the study in SQLite
  -> write redacted JSON and CSV result reports
```

`examples/quickstart.py` composes a LangChain in-memory vector store, retriever, prompt, and
fake LLM. Fake embeddings and generation make it an offline wiring test, not a quality benchmark.
`examples/langchain_full_rag.py` provides a real OpenRouter-backed framework RAG. Neither example
is imported by the installable package.

## Framework runnable flow

```text
LangChainAdapter.run or LangGraphAdapter.run
  -> resolve fixed runnable or factory(candidate)
  -> map EvaluationExample to framework input
  -> map Candidate parameters to config["configurable"]
  -> await runnable.ainvoke(input, config=config)
  -> optionally map raw output
  -> collect standard message usage or custom usage
  -> append exact runnable latency
  -> return through the standard framework adapter contract
```

Framework execution therefore uses the existing optimizer path unchanged. Cache identity includes
the adapter fingerprint and candidate; framework exceptions remain subject to the engine retry,
timeout, redaction, and failure-isolation policy.

## Google ADK flow

```text
GoogleADKAdapter.run(candidate, example)
  -> resolve and validate real ADK Runner or candidate factory result
  -> map candidate to initial session state
  -> create isolated session
  -> consume Runner.run_async events
  -> capture reported tokens and final response
  -> map final event to evaluation output
  -> close event stream and delete temporary session in finally
  -> return output and usage to the shared optimizer
```

Runner factories and input/state/output mappers configure framework components rather than
implementing a new RAG runtime. The application manages runner lifetime and provider credentials.

## Extended verification flow

`tests/live/test_campaign.py` loads a PDF using LangChain, separates development and
held-out records, and builds official retrieval/document chains through a candidate
factory. LangGraph wraps that chain in a compiled graph. Optimizer execution persists
four concurrent trials and mirrors durable events to local MLflow. After compatible
zero-call resume and incompatible-identity rejection, exported winning parameters
rebuild an independent pipeline for held-out evaluation. RAGAS is applied only to the
prespecified held-out subset. See `comprehensive-testing.md` for coverage and limits.

`tests/live/test_google_adk.py` loads/splits the same PDF through LangChain, builds
a cached embedding/vector index, and uses an ADK before-model callback to retrieve
the candidate-controlled number of chunks from session state. ADK LiteLlm executes
generation through the existing budget-guarded OpenRouter client. After-model
metadata carries retrieved contexts into the adapter output mapper and RAGAS.
Two trials persist through SQLite and local MLflow, followed by zero-call completed
resume, incompatible-revision rejection, exported winner reuse, held-out scoring,
and session cleanup. See `live-google-adk-testing.md` for exact scope.

`tests/live/test_quality.py` first calibrates a structured-output reference judge
against contrasting complete, incomplete, incorrect and abstaining answers. Only
after that gate passes does it score existing frozen held-out answer files. It
never reruns retrieval/generation or changes the previously chosen winner. The
test evaluator maps semantic atomic-fact verdicts to estimated completeness,
contradiction and reference-quality metrics; rubric/model/prompt fingerprints
identify the scoring configuration. See `quality-validation-plan.md` for ordered
stages, evidence and unexecuted boundaries. See `reliability-validation.md` for
the bounded follow-up campaigns, tool bridge and guarded recovery gateway.
