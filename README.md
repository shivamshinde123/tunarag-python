# tunarag-python

`tunarag-python` is a typed, local-first Python library for comparing and optimizing configurations of an existing RAG system.

The implementation is being developed against the design baseline in [`docs/`](docs/) and the phased delivery plan in [`PROJECT_PLAN.md`](PROJECT_PLAN.md).

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

The public package is imported as `tunarag`.