# TunaRAG Coding Conventions

## Language and style

- Support CPython 3.10 through 3.13.
- Use Ruff formatting and linting with a 100-character line length.
- Use strict mypy for package code and precise public annotations.
- Run the full quality matrix on Linux and Windows with Python 3.10 and 3.13.
- Keep imports side-effect free and optional dependencies outside core import paths.
- Prefer frozen, slotted dataclasses for values and protocols at replaceable boundaries.
- Use descriptive names; avoid generic utilities and broad manager classes.

## Async, errors, and observability

Internals are async-first. Blocking operations do not run on the event loop. Trial and sample
concurrency are separately bounded. Cancellation is cleaned up and re-raised. Provider,
sample, and trial timeouts remain distinct. Public errors identify stage and corrective action
without secrets or evaluation content. Library code uses the `tunarag` logger without
configuring handlers; structured events are the supported observability surface.

## Persistence and security

Transactions are short and never span provider calls, callbacks, sleeps, or user code.
Foreign keys are enabled. Terminal records are immutable unless a migration says otherwise.
Secrets are excluded from representations, hashes, persisted configuration, cache metadata,
logs, events, errors, exports, and optional tracking integrations.

## Tests and documentation

Unit tests avoid networks, real sleeps, and shared state. Contract tests cover replaceable
boundaries. Behavior changes test success plus relevant validation, failure, retry,
cancellation, cache, and resume paths. Material changes update the affected documents in this
directory in the same branch.

## Optional framework integrations

Framework adapters depend on narrow structural protocols instead of importing third-party base
classes. Keep framework calls async, accept explicit mapping hooks instead of guessing arbitrary
state, and include semantic adapter behavior in fingerprints without serializing framework
internals. Unit tests use fakes; a separate optional-dependency CI job verifies real supported
framework versions. Framework exceptions remain owned by the optimizer's existing retry,
timeout, redaction, and trial-isolation boundaries.
