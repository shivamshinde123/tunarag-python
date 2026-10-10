# TunaRAG Environment Configuration Reference

Google ADK runners own their provider credentials and SDK configuration. `GoogleADKAdapter` does
not load keys, snapshot runner internals, or provision provider clients. Supply a stable, secret-free
pipeline revision through `identity`. Do not use production conversation sessions for evaluation.

## Hierarchy

`Settings.resolve` uses the following ascending precedence: package defaults, an explicitly
selected TOML file, known `TUNARAG_` variables, then explicit overrides. TOML values live under
`[tunarag]`. Unknown TOML or override keys and invalid values raise `ConfigurationError`.
TunaRAG never implicitly loads `.env`, scans arbitrary environment values, creates directories,
or changes semantics through a hidden environment mode.

| Variable | Default | Purpose |
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
| `TUNARAG_SAMPLE_TIMEOUT_SECONDS` | `60.0` | Deadline for each adapter or evaluator call |
| `TUNARAG_TRIAL_TIMEOUT_SECONDS` | `300.0` | Deadline for one complete candidate execution |
| `TUNARAG_CACHE_POLICY` | `read_write` | Cache behavior |

`TUNARAG_CACHE_POLICY` accepts `off`, `read_only`, `write_only`, or `read_write`. Trial and
concurrency values must be positive; retries are nonnegative; integer strings must be canonical
base-10 values; timeout values must be positive finite numbers. `TUNARAG_HOME` uses the
platform data directory when omitted. Dependent paths derive from the resolved home unless set
independently. Environment/TOML settings always enable finite timeouts; advanced callers may
inject a `RetryPolicy` with `None` for a deliberately unbounded sample or trial timeout.

Prefer injected provider clients. Optional integrations may read provider-standard keys only
when no client is injected. Core settings never retain them. Secrets are never snapshotted or
included in hashes, persistence, events, logs, errors, or exports.

The optional `MLflowCallback` accepts `tracking_uri` explicitly. When it is `None`, the MLflow
client applies its standard configuration, including `MLFLOW_TRACKING_URI` and backend-specific
authentication variables. TunaRAG does not read, persist, hash, or emit those credentials.
`experiment_id`, not experiment-name lookup, is required to keep callback network behavior
explicit.

## OpenRouter LangChain example

The standalone `examples/langchain_full_rag.py` application explicitly loads the repository-root
`.env` file with `python-dotenv`. This is application behavior, not implicit TunaRAG core
configuration. Copy `.env.example` to `.env`; Git ignores the resulting secret-bearing file.

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | Required | Authenticates chat and embedding requests |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible API endpoint |
| `OPENROUTER_SITE_URL` | Empty | Optional application attribution URL |
| `OPENROUTER_APP_NAME` | `TunaRAG LangChain Example` | Application attribution title |
| `TUNARAG_CHAT_MODEL` | `openai/gpt-4.1-mini` | OpenRouter chat model slug |
| `TUNARAG_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | OpenRouter embedding model slug |

Never commit `.env`, print the API key, include it in TunaRAG candidate parameters, or place it in
reports. `.env.example` contains placeholders only and is safe to version.
