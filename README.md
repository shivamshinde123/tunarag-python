# tunarag-python

`tunarag-python` is a typed, local-first Python library for comparing and optimizing configurations of an existing RAG system.

The implementation is developed against the detailed DOCX baseline and living Markdown
documents in [`docs/`](docs/), plus the phased delivery plan in
[`PROJECT_PLAN.md`](PROJECT_PLAN.md). Start with the product requirements, system architecture,
technical design, and API specification in `docs/`.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

The public package is imported as `tunarag`.
