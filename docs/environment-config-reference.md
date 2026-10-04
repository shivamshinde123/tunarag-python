# TunaRAG Environment Configuration Reference

## Status and hierarchy

No environment configuration is currently read. Planned precedence is explicit call arguments,
constructor settings, an explicitly selected TOML file, `TUNARAG_` variables, then defaults.
TunaRAG never implicitly loads `.env` or changes semantics through a hidden environment mode.

| Planned variable | Proposed default | Purpose |
|---|---|---|
| `TUNARAG_HOME` | Platform data directory | Base local state |
| `TUNARAG_DB_PATH` | `<home>/experiments.db` | SQLite database |
| `TUNARAG_CACHE_DIR` | `<home>/cache` | Cache payloads |
| `TUNARAG_ARTIFACT_DIR` | `<home>/artifacts` | Reports and exports |
| `TUNARAG_MAX_TRIALS` | `25` | Trial limit |
| `TUNARAG_CONCURRENCY` | `4` | Trial concurrency |
| `TUNARAG_SAMPLE_CONCURRENCY` | `8` | Per-trial sample concurrency |
| `TUNARAG_SEED` | `0` | Root seed |
| `TUNARAG_MAX_RETRIES` | `2` | Retry limit |
| `TUNARAG_CACHE_POLICY` | `read_write` | Cache behavior |

Names and defaults remain `TBD` until implemented. Prefer injected provider clients. Optional
integrations may read provider-standard keys only when no client is injected. Secrets are
never snapshotted or included in hashes, persistence, events, logs, errors, or exports.
