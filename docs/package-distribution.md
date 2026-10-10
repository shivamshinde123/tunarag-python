# Package Contents

TunaRAG's installable distribution contains the optimizer, not the repository's
test datasets, documentation or example applications.

## What pip installs

| Included in the wheel | Not included |
|---|---|
| `tunarag` runtime modules and official adapter code | Tests and validation campaigns |
| `py.typed` for Python typing support | PDFs, provider receipts and generated outputs |
| Package metadata and dependency declarations | Documentation, diagrams and the DOCX handbook |
| README metadata and the full MIT license | Example scripts, CI workflows and authoring tools |

The source distribution contains runtime source and the files needed to rebuild
the wheel: build configuration, README, changelog, license and generated metadata.
It is not a full repository checkout. To run repository tests or examples, use the
[GitHub repository](https://github.com/shivamshinde123/tunarag-python).

## Choose only the extras you need

Dependencies are installed separately, not copied into TunaRAG's wheel. Frameworks,
RAGAS and MLflow can be substantially larger than TunaRAG itself. Use the extra
matching your application:

```console
python -m pip install "tunarag-python[langchain]"
python -m pip install "tunarag-python[langgraph]"
python -m pip install "tunarag-python[google-adk]"
```

Add `ragas` or `mlflow` only when using those integrations, for example:

```console
python -m pip install "tunarag-python[langchain,ragas]"
```

See the [installation guide](usage.md#installation) for setup and supported extras.
Your application still supplies its corpus, pipeline and provider credentials.

## License and safety

The full MIT license ships with the distribution. Review the
[license and responsibility guidance](usage.md#license-and-responsibility) and
[Security Policy](https://github.com/shivamshinde123/tunarag-python/blob/main/SECURITY.md).
Installing a small package does not guarantee safe retrieved content, accurate
answers or controlled provider bills.
