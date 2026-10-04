# TunaRAG Technical Design

## Lifecycle and scheduling

Implemented studies move from created to running then completed, with failed and cancelled
terminals; a separate stopping state may be added with orchestration. Trials support pending,
running, succeeded, failed, abandoned, and cancelled. Terminal states are immutable. Completed
studies cannot contain active trials. Retries create attempts instead of moving terminal
attempts backward. Trial, attempt, and event sequence numbers are monotonic and never reused.

The scheduler asks the strategy for capacity-sized candidates, validates them through the
search space, hashes canonical values, and reserves uniqueness in SQLite. The trial runner
prepares the adapter, executes bounded samples, evaluates outputs, aggregates objective and
usage, and cleans up under distinct timeout/cancellation boundaries.

The implemented baseline uses capacity one. It iterates a repeatable async dataset, materializes
adapter usage and evaluator outputs at each boundary, rejects duplicate metric names within a
sample and the reserved `tunarag.objective` name, aggregates by metric name, and atomically
commits terminal results. Duplicate suggestions are retried up to a configured bound before
search exhaustion. A later scheduler will increase bounded capacity without changing these
single-trial semantics.

## Retries and resume

Retry decisions use stage, error code, idempotency, attempt count, and provider hints.
Authentication, invalid configuration/output, and missing ground truth are nonretryable;
rate limits, transient networks, and provider 5xx responses are generally retryable. Exhausted
trial failure does not fail the study by default.

The implemented `RetryPolicy` retries structured errors explicitly marked retryable plus
timeouts and connection failures. Attempt numbers start at zero and every retry starts a new
leased attempt. Backoff is deterministic exponential delay capped by policy. A failed
retryable attempt commits its observed usage and terminal attempt state in one transaction,
while the trial remains running. Sample timeout wraps each adapter and evaluator call; trial
timeout wraps complete dataset execution. Cancellation is never converted into a retry.

Resume compares dataset, search-space, objective, adapter, evaluator, strategy, schema, and
cache fingerprints; abandons expired attempts; reconstructs budgets; replays terminal results;
and continues sequence numbers. Incompatibility requires an explicit fork.

This flow is implemented for created, running, and completed compatible studies. Failed and
cancelled studies are terminal. Recovery is scoped to one study, and unexpired attempt leases
produce a retryable `ResumeError`. Terminal summaries are rebuilt from metrics, append-only
usage, attempts, trial errors, and cache-hit events. Pending and recoverable trials execute
before new suggestions. The durable `study.stopping` event preserves the result stop reason.
Ordinary strategies receive successful observations in sequence order. Replay-aware strategies
receive every reserved candidate—including failed and unfinished trials—through the optional
`replay` method. `RandomSearch` verifies and advances seeded generator state.

The implemented store provides attempt leases, persisted abandonment, and a recoverable-trial
query. A terminal commit transaction writes metrics, append-only usage, terminal attempt state,
terminal trial state, and the corresponding ordered event. Validation failures roll the whole
transaction back. Strategy replay consumes ordered committed events only.

## Cache, objectives, and stopping

Cache keys use domain-separated SHA-256 over canonical semantic inputs and versions. The
implemented foundation stores bytes atomically in an independently versioned SQLite table with
namespace, format version, timestamps, privacy class, checksum, state, hit count, and quarantine
reason. Reads verify TTL and checksum before exposing bytes. The first corrupt read returns a
corrupt outcome and persists quarantine; later reads return quarantined. Expired and quarantined
entries remain inspectable until retention pruning. Partial/failed work is not cached without
an explicit safe negative-cache policy.

The optimizer cache payload is canonical JSON containing only payload version and aggregated
metrics. Objective scores are recomputed so objective weights can change without invalidating
evaluation work; cached usage is intentionally empty because result accounting describes the
current run. Cache keys include format version, dataset version, candidate, and adapter and
evaluator type names. Writes occur only after the durable successful trial commit. Cache read,
decode, and write failures append events and do not change trial success. Configurable component
fingerprints are included when a component implements `fingerprint()`; otherwise type identity
is used. Mandatory fingerprints for every custom component and TTL selection at the optimizer
boundary remain future work.

Objectives preserve direction, normalization, weight, coverage, and confidence. Unknown values
do not become zero. Stop rules evaluate a committed snapshot with deterministic precedence and
retain the winning reason. Planned rules cover trial count, score target, cost, wall time, no
improvement, search exhaustion, failure threshold, and cancellation.

## Open decisions

Python 3.10 structured concurrency, sortable public IDs, sample checkpoint stability, and a
future size threshold for external cache payload files remain `TBD`.
