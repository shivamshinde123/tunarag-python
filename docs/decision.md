# TunaRAG Decision Log

## 2026-10-06 Provide a complete single-file LangChain tuning example

Provide one executable example that uses standard LangChain components for document splitting,
OpenAI embeddings, an in-memory vector store, retrieval, prompting, and generation, then connects
the runnable through `LangChainAdapter`. Keep provider packages explicit rather than adding OpenAI
to TunaRAG's provider-neutral `langchain` extra. Tune runtime RAG parameters without rebuilding a
custom adapter or making the reference RAG part of the package.

## 2026-10-05 Store README illustrations inside the MkDocs source tree

Keep canonical README illustrations under `docs/assets/tunarag-python-readme-illustrations/` and
reference them with repository-relative paths from `README.md`. This supersedes the earlier raw-URL
decision because unauthenticated `raw.githubusercontent.com` URLs do not render assets from a
private repository. Repository-relative paths render on private GitHub pages, and keeping the files
below `docs/` lets MkDocs publish the same assets without duplication. PyPI rendering should be
checked separately if the repository remains private at the next release.

## 2026-10-05 Add sparse hand-drawn README illustrations

Use six consistent Xiaohei-style article illustrations as cognitive anchors in the comprehensive
README rather than decorating every section. Place them at the optimization loop, adapter boundary,
dataset preparation, search strategy, persistence/resume, and result-reporting concepts. Keep the
PNG sources in a versioned root asset directory and reference their raw GitHub URLs so they render
consistently on GitHub, PyPI, and the generated MkDocs usage page. Every image has descriptive alt
text; prose and code remain sufficient when images are unavailable.

## 2026-10-05 Publish documentation with MkDocs Material and GitHub Pages

Build the public documentation from the repository's Markdown with MkDocs Material and deploy the
static site to GitHub Pages through GitHub Actions. Keep `README.md` as the canonical comprehensive
usage guide and include it during the documentation build to prevent a divergent copy. Generate the
Python API reference from source signatures and docstrings with `mkdocstrings`, while retaining the
hand-written architecture and design documents for concepts and rationale. Validate every pull
request with a strict documentation build and deploy only from `main`. This provides a free,
searchable, mobile-friendly site without introducing a hosted documentation service or credentials.

Decisions are chronological. Superseding entries preserve the original reasoning.

## 2026-10-04 Publish `0.2.1` through GitHub OIDC

Publish the first package-index release as `0.2.1` because the existing `v0.2.0` tag predates the
final public README and executable documentation fixes. Use a manually dispatched GitHub Actions
workflow with separate `testpypi` and `pypi` protected environments and PyPA's trusted-publishing
action. Do not store a long-lived PyPI API token in the repository or GitHub secrets.

## 2026-10-04 Lead the README with the product, not the manual

The README begins with a concise product definition, the problem TunaRAG solves, representative use
cases, target users, and the boundary between TunaRAG and the user's RAG application. The detailed
usage guide follows this overview. Use ASCII punctuation in compatibility-critical introductory text
to avoid mojibake in package-index and repository renderers.

## 2026-10-04 Promote the comprehensive guide to `README.md`

Supersede the separate-root-guide portion of the decisions below. `README.md` is now the single
canonical package guide used by GitHub and distribution metadata. The separate `Usage.md` is removed
to avoid duplicate content and drift. Executable documentation tests now read Python fences directly
from `README.md`.

## 2026-10-04 Execute every `Usage.md` Python example in CI

Treat every Python fence in the canonical usage guide as executable documentation. The documentation
test extracts all fences, asserts the expected count, runs every example with controlled fixtures,
and verifies its observable result. Optional provider boundaries may use local test doubles, while
installed LangChain and LangGraph packages are exercised directly. Any added, removed, or
behaviorally changed example must update the harness in the same pull request.

## 2026-10-04 Comprehensive usage guide

Maintain a root-level `Usage.md` as the canonical package usage guide. It covers all public V0.2
features, copy-oriented examples, lifecycle diagrams, edge cases, and production guidance. Focused
API and architecture documents remain authoritative for design detail; material behavior changes
must update both those specifications and the usage guide.

## 2026-10-03 Naming

Use TunaRAG as the product, `tunarag-python` as the repository and Python distribution, and
`tunarag` as the import package. A TypeScript implementation will use a separate repository.

## 2026-10-03 Runtime boundary

Build async-first internals with a synchronous wrapper. Users supply a `RAGAdapter`; TunaRAG
does not own their production RAG. Keep RAGAS, MLflow, providers, LangChain, and LlamaIndex as
optional edge integrations.

## 2026-10-03 Values and identity

Use frozen slotted dataclasses for core values, protocols for extension points, canonical JSON
and domain-separated SHA-256 for identity, and omit secret values from identity mappings.

## 2026-10-03 Search and accounting

Random search owns an isolated seeded random stream. Objective and usage results retain
`exact`, `estimated`, or `unavailable` status; unknown values never silently become zero.

## 2026-10-03 Persistence

Use standard-library `sqlite3` and explicit transactions as V0.1 authority. MLflow is an
optional mirror. Defer an ORM until a second relational backend justifies it.

## 2026-10-03 Cross-platform quality gate

Run formatting, linting, strict typing, tests, and package builds on Linux and Windows with the
oldest and newest supported Python versions. Force LF for source and documentation so local
Git settings do not create formatter-only differences.

## 2026-10-03 SQLite cache foundation

Store foundation cache payloads as SQLite BLOBs with an independently versioned schema,
canonical namespaced keys, SHA-256 payload checksums, explicit privacy metadata, and persisted
expiry/quarantine states. Return explicit lookup outcomes and never return unverified bytes.

This keeps V0.1 atomic and zero-infrastructure. External payload files remain a later option if
measured payload sizes justify the additional atomic-write and cleanup complexity.

## 2026-10-03 Explicit configuration and structured errors

Resolve only defaults, explicitly selected TOML, known `TUNARAG_` variables, and explicit
overrides, in that precedence order. Do not auto-load `.env`, provider credentials, or a hidden
environment mode. Keep settings immutable and provider-secret free.

Represent package-boundary failures with stable codes, stage, retryability, and recursively
redacted details. Keep low-level validation exceptions until the boundary that can add useful
context, rather than obscuring their causes prematurely.

## 2026-10-03 Experiment schema version 2

Migrate version-1 databases transactionally and add guarded study/trial lifecycle state,
unique per-study candidates, leased attempts, aggregate metrics, append-only usage, and ordered
events. Allocate trial and event sequences under immediate write transactions. Commit terminal
attempt state, observations, trial state, and event atomically.

Keep a retryable trial running after a failed or abandoned attempt; each retry receives a new
monotonic attempt number. Resume first abandons expired leases, then queries running trials with
no active attempt. This separates execution attempts from the semantic candidate trial.

## 2026-10-03 Sequential optimizer baseline

Make `Optimizer.aoptimize` the authoritative entry point and provide `optimize` only when no
event loop is active. Deliver a sequential end-to-end path before adding concurrency so adapter,
evaluation, objective, persistence, isolation, and stopping semantics are testable without
scheduler races.

Aggregate repeated sample metrics by name using arithmetic mean, explicit coverage, and the
least-confident observed status. Persist partial usage when a trial fails, but do not expose raw
third-party exception messages. Observe only committed successful trials under the current
strategy contract. Add retries, cache use, replay/resume, callbacks, and concurrency in focused
follow-up branches.

## 2026-10-04 Retry, timeout, and evaluation-cache semantics

Treat a trial as one semantic candidate and each execution as a durable attempt. Retry only
explicitly transient structured failures, timeouts, and connection failures; use deterministic
capped exponential backoff. Persist each failed attempt and its observed usage atomically so
retries never erase real spend. Apply a timeout to each adapter/evaluator call and a separate
deadline to the complete candidate execution.

Cache only successfully aggregated evaluation metrics, never objective scores or usage. Read
and write according to the explicit cache policy, recompute the current objective on hits, and
record zero current-run usage for cached work. Write only after the authoritative trial commit.
Treat cache transport, corruption, or semantic-decoding problems as observable misses rather
than trial failures. V0.1 keys use dataset version, candidate, payload format, and component
type names; richer component configuration fingerprints remain future work.

## 2026-10-04 Compatible resume and strategy replay

Expose separate `aresume` and `resume` entry points rather than overloading new-study creation.
Resume requires the same semantic configuration hash, preserves failed/cancelled terminality,
and refuses unexpired leases to avoid duplicate execution. It scopes expired-attempt recovery
to the requested study, reconstructs terminal results and budgets from SQLite, replays committed
successes in sequence, and finishes reserved work before requesting new candidates. Completed
studies are reloadable without provider calls. Persist the winning stop reason as an ordered
event so a reloaded result remains meaningful.

Allow strategies to implement a distinct replay hook and components to contribute optional
semantic fingerprints. `RandomSearch` fingerprints its search space and seed, then verifies and
advances generator state during replay. Components without a fingerprint retain type-only
identity in V0.1. Store candidate payloads with a reversible, number-preserving, secret-safe JSON
serializer while retaining the existing canonical serializer exclusively for hashes.

## 2026-10-04 Post-commit callback dispatch

Make callbacks async objects consuming durable `StudyEvent` records. Dispatch only after SQLite
commits and preserve event sequence, including notifying retry scheduling before backoff. Do not
replay historical callback notifications on resume; callers can query the event store when they
want history. Isolate callback exceptions from authoritative optimization state and append a
redacted `callback.failed` diagnostic containing no exception message. Never dispatch callback
failure events back through callbacks, preventing recursive failure storms.

## 2026-10-04 Deterministic bounded concurrency

Run trials in batches capped by `concurrency` and samples through a separate semaphore capped by
`sample_concurrency`. Reserve candidates serially, execute concurrently, then apply results and
strategy observations in durable trial-sequence order so completion timing does not alter search
state. Keep `MaxTrials` as a hard cap; allow snapshot cost/time budgets to overshoot only by the
active batch and document that bound. Serialize callback draining per study. Materialize each
finite evaluation split before sample work in V0.1; streaming windows remain a later extension.

## 2026-10-04 Provider-neutral LLMSearch

Define LLM-guided search around an injected structured provider rather than any provider SDK or
prompt framework. Validate exact candidate keys and value bounds, bound invalid/provider-failure
attempts, redact prior observations before provider calls, and record only exception types in
errors. Use stateless deterministic fallback keyed by seed and suggestion number so replay does
not depend on hidden random state. Include optional provider fingerprints in compatibility.
Keep strategy-provider usage explicitly unreported until the common strategy contract gains a
durable usage channel; never silently count unknown provider cost as zero.

## 2026-10-04 Optional RAGAS boundary adapter

Keep the optimizer coupled only to the small `Evaluator` protocol. Provide a built-in
`MetricEvaluator` for ordinary sync or async numeric functions and a lazy `RagasEvaluator` for
RAGAS 0.4. Require an explicit sample mapper as a privacy and schema boundary rather than
inspecting arbitrary user objects. Evaluate one engine sample at a time so TunaRAG retains
ownership of concurrency, retries, timeouts, aggregation, and failure isolation. Namespace RAGAS
metrics by default, normalize missing/nonfinite scores to unavailable, redact provider exception
messages, and keep provider credentials/configuration outside TunaRAG.

## 2026-10-04 Canonical evaluation dataset ingestion

Introduce a provider-neutral `EvaluationExample` and `EvaluationDataset` using only the Python
standard library. Accept mappings, JSON arrays, JSONL, and explicit-mapping CSV; never guess
column semantics. Normalize text conservatively, deeply freeze finite JSON metadata, generate
missing IDs from normalized content, and reject duplicate identities. Version ordered semantic
content with domain-separated hashing and exclude paths/timestamps. Use stable hash-based
80/10/10 splits with optional metadata grouping so assignment is independent of input order.
Keep synthetic generation and rich source-span provenance as a separate feature.

## 2026-10-04 Deterministic result reporting and exports

Derive rankings from immutable terminal summaries instead of persisting duplicate report state.
Rank the configured objective descending with durable sequence ties, and expose independent
direction-aware metric leaders. Define JSON report schema version 1 as the lossless portable
format and CSV as a flattened one-row-per-trial analysis format. Apply central recursive
redaction to candidate parameters in every export and retain usage confidence provenance.
Defer formal Pareto/frontier semantics until the post-V0.1 multiobjective design.

## 2026-10-04 Complete composable stopping rules

Extend committed stop snapshots with success/failure counts and objective history in durable
sequence. Add wall-time, target-score, total/consecutive failure, and no-improvement rules beside
trial and cost budgets. Treat failed trials as non-improvements, require benefit-oriented target
comparisons, and preserve declaration order when multiple rules match. Accept bounded overshoot
from the active concurrency batch; callers requiring exact immediate stopping use concurrency
one. Fingerprint every built-in rule and include the ordered policy list in resume compatibility.

## 2026-10-04 Best-effort MLflow event mirror

Implement MLflow as an optional `EventCallback` projection rather than a store or engine
dependency. Read only committed SQLite state, perform blocking MLflow calls off the event loop,
and rely on callback failure isolation so tracking outages cannot change optimization outcomes.
Log redacted candidate parameters, numeric metrics, sequence, and lifecycle status; normalize
tracking keys deterministically. Keep run IDs in callback memory for V0.1, meaning a resumed
process creates a new mirror run rather than replaying or mutating historical tracking state.

## 2026-10-04 Provider-neutral synthetic QA generation

Keep synthetic generation behind an injected async provider and structured request/response
types. TunaRAG controls deterministic per-document seeds, bounded concurrency, ordering,
validation, provenance, and usage capture without owning prompts, credentials, retries, or SDKs.
Require exact requested cardinality and valid source spans; label every sample synthetic and
unreviewed. Return generation usage separately from optimization accounting.

## 2026-10-04 Keep the reference RAG in examples

Provide a deterministic, provider-free reference RAG under `examples/` rather than under
`src/tunarag`. It demonstrates the standard adapter, evaluator, dataset, search, persistence,
and reporting boundaries through public APIs only. The reference implementation is educational
application code, not a supported retrieval or generation runtime, preserving TunaRAG's role as
an optimizer for user-owned pipelines.

## 2026-10-04 Declare the V0.1 implementation contract complete

Release the implemented package as `0.1.0` after the cross-platform quality matrix, built-wheel
import smoke test, property tests, and reference quickstart pass. Keep formal Pareto semantics,
distributed execution, CLI design, framework adapters, and package-index publication outside
the V0.1 implementation contract. Record public changes through semantic versioning and the
changelog while SQLite and cache formats retain independent schema versions.

## 2026-10-04 Add structural LangChain and LangGraph integrations in V0.2

Provide first-party adapters for LangChain runnables and compiled LangGraph graphs through their
shared asynchronous `ainvoke` shape. Keep framework imports out of core runtime modules and offer
explicit 1.x optional extras plus real compatibility CI. Default canonical queries to a
`question` input and candidate parameters to the `configurable` namespace, while preserving
custom mappers and per-candidate factories for pipeline-specific state and construction needs.
Capture latency and standard message token usage without introspecting framework internals or
credentials. This reduces integration boilerplate without changing the provider-neutral
optimizer contract.

## 2026-10-06 Use OpenRouter and explicit `.env` loading in the complete LangChain example

Configure the complete LangChain RAG example through a repository-root `.env` file and one
`OPENROUTER_API_KEY`. Route both `ChatOpenAI` and `OpenAIEmbeddings` through OpenRouter's
OpenAI-compatible base URL, while keeping model slugs configurable. Load `.env` only inside the
example application; TunaRAG core continues to avoid implicit dotenv loading and never owns,
persists, or reports provider credentials. Version a placeholder-only `.env.example` and keep the
real `.env` ignored.

## 2026-10-09 Restrict V0.3 to official framework pipelines

Supersede the earlier generic RAG adapter decision: users tune pipelines built with LangChain,
LangGraph, or Google ADK 2.x and do not implement handwritten RAG adapters. Reject unsupported
adapters in `Optimizer` before opening a store, remove the public RAG adapter protocol, and
validate actual framework objects rather than accepting lookalike `ainvoke` methods. Keep the
shared optimizer, search, evaluation, storage, retries, and resume machinery intact.

Use per-candidate factories for framework construction settings and mappers for framework state
and output shapes. Google ADK uses fresh temporary sessions per sample and retry, removes them
on terminal execution, and captures reported token counts and elapsed time. Replace the
handwritten reference RAG with an offline LangChain quickstart. Declare the breaking boundary
change as V0.3.0 and require real-framework compatibility tests. Additional frameworks need a
first-party integration; custom evaluators, objectives, strategies, and callbacks remain supported.

## 2026-10-09 Verify README tuning with real framework components

Execute every README Python fragment with explicit fixtures and add assertions that
candidate parameters change framework behavior, scores, and winner selection. Replace
the quickstart's constant metric with retrieval recall and test the factory with real
LangChain retrieval helpers. Document fixture and live-provider limitations in
`readme-example-verification.md`; offline correctness is not production quality evidence.

## 2026-10-09 Separate paid smoke tests from normal CI

Add an explicit `--live` gate for real optional dependencies and a separate
`--live-paid` gate for OpenRouter calls. Use a dedicated environment, sanitized
small sources, explicit dotenv loading, a shared outbound request budget, and a
loopback-only MLflow server. Report provider-side spending limits and partial usage
tracking honestly; a request count is not a dollar guarantee. Preserve the existing
RAGAS 0.4 legacy integration for compatibility testing, rather than silently replacing
it with a different metric API. Fix RandomSearch replay to skip already-reserved
duplicate draws (bounded to 10,000 draws per replay) while rejecting unseen mismatches.

Real dependency checks exposed two additional integration issues: pin the RAGAS
legacy community dependency below 0.4 to retain its required imports, and advance
callback cursors only through events actually visited. Reading the latest durable
sequence after an awaited callback could skip a concurrently committed trial event,
silently losing its MLflow projection despite successful authoritative persistence.

## 2026-10-09 Expand end-to-end verification without paid CI

Add a separately gated full-PDF campaign across LangChain/LangGraph and both search
strategies. Freeze 10 development and 20 held-out questions before tuning; export the
winner and reconstruct it outside the optimizer. Separate lexical diagnostics from
real RAGAS scoring and correctness from generalization. Use real MLflow concurrently
with provider execution. Keep private results and budget ledgers ignored. Raise only
the explicit request-limit upper bound to 500; retain the default of 40 and warn that
request limits do not guarantee dollar limits. Add subprocess death/recovery tests
with simulated expired leases and verify clean built-wheel execution separately.

## 2026-10-09 Add live Google ADK validation through OpenRouter

Use official ADK Agent/Runner orchestration with a LangChain retriever invoked by
ADK model callbacks. Preserve context metadata for real RAGAS scoring. Reuse the
guarded OpenAI-compatible client inside ADK LiteLlm instead of letting a second
transport bypass the request and cumulative dollar budget. Verify that transport
contract without credentials, including provider failure and before-send rejection.
Keep LiteLLM optional in a separate live-adk-test extra. Freeze three development
and three held-out questions for a bounded add-on, not another full benchmark.
Native Gemini/Vertex and model-directed tools remain unvalidated by this campaign.

## 2026-10-09 Prioritize answer completeness before broader integration load

Add a strictly parsed, versioned reference-quality test evaluator through the
existing public contract, not a new mandatory package dependency. Calibrate semantic
fact coverage and contradiction handling against frozen contrasting answers before
rescoring saved held-out answers. Preserve separate retrieval/faithfulness metrics.
Do not regenerate answers, alter references, or select new winners using test labels.
Schedule repeated tuning, ADK tools/concurrency, billing reconciliation and live
interruption recovery after the initial quality gate; label unexecuted stages pending.

## 2026-10-09 Extend bounded live validation without changing the runtime

Freeze new held-out questions and the version 3 judge before repeated quality tuning.
Use the official ADK/LangChain retrieval-tool bridge and force a two-model-turn bound.
With explicit user approval, reconcile fully settled provider receipts against key
usage and release unused reservations without resetting the original $5 authorization
or losing history. Keep external account costs separate from committed trial usage.
Use a credential-free child and guarded parent gateway for lost-response recovery;
wait for real lease expiry. These are test-harness additions, not distributed execution
or native Google-provider support. See `reliability-validation.md` for evidence limits.
