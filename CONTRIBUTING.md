# Contributing

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

On macOS or Linux, activate `.venv` and use `python` in place of the Windows executable.

## Change workflow

1. Create a focused feature, fix, documentation, or chore branch from `main`.
2. Update implementation, tests, and the living documents under `docs/` together.
3. Run `python -m ruff format .`, `python -m ruff check .`, `python -m mypy`,
   `python -m pytest`, and `python -m build`.
4. Open a pull request with a concise summary and verification evidence.
5. Merge only after the Linux and Windows CI matrix passes.

Keep core dependencies provider-neutral. User code, provider calls, callbacks, and sleeps must
not run inside SQLite transactions. New public behavior needs tests and API documentation;
optional integrations must remain importable only when requested.
