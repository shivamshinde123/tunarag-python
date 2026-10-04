# TunaRAG Technical Design

## Lifecycle and scheduling

Target studies move from created to running, stopping, then completed, with failed and
cancelled terminals. Current trials support pending, running, succeeded, failed, and abandoned.
Retries create attempts instead of moving terminal attempts backward. Sequence numbers are
monotonic and never reused.

The scheduler asks the strategy for capacity-sized candidates, validates them through the
search space, hashes canonical values, and reserves uniqueness in SQLite. The trial runner
prepares the adapter, executes bounded samples, evaluates outputs, aggregates objective and
usage, and cleans up under distinct timeout/cancellation boundaries.

## Retries and resume

Retry decisions use stage, error code, idempotency, attempt count, and provider hints.
Authentication, invalid configuration/output, and missing ground truth are nonretryable;
rate limits, transient networks, and provider 5xx responses are generally retryable. Exhausted
trial failure does not fail the study by default.

Resume compares dataset, search-space, objective, adapter, evaluator, strategy, schema, and
cache fingerprints; abandons expired attempts; reconstructs budgets; replays terminal results;
and continues sequence numbers. Incompatibility requires an explicit fork.

## Cache, objectives, and stopping

Cache keys use domain-separated SHA-256 over canonical semantic inputs and versions. The
implemented foundation stores bytes atomically in an independently versioned SQLite table with
namespace, format version, timestamps, privacy class, checksum, state, hit count, and quarantine
reason. Reads verify TTL and checksum before exposing bytes. The first corrupt read returns a
corrupt outcome and persists quarantine; later reads return quarantined. Expired and quarantined
entries remain inspectable until retention pruning. Partial/failed work is not cached without
an explicit safe negative-cache policy.

Objectives preserve direction, normalization, weight, coverage, and confidence. Unknown values
do not become zero. Stop rules evaluate a committed snapshot with deterministic precedence and
retain the winning reason. Planned rules cover trial count, score target, cost, wall time, no
improvement, search exhaustion, failure threshold, and cancellation.

## Open decisions

Python 3.10 structured concurrency, sortable public IDs, sample checkpoint stability, and a
future size threshold for external cache payload files remain `TBD`.
