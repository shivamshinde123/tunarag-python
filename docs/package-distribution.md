# Package distribution

Version 0.3.0 is the framework-only release: use the official LangChain, LangGraph, or
Google ADK adapters. See the changelog for migration from 0.2.1.

## What pip downloads

The wheel contains only `tunarag` runtime modules, the `py.typed` marker, and generated
distribution metadata (including the README and MIT license declaration). Normal pip
installation uses this universal Python wheel. Tests, PDFs, illustration images,
documentation-site sources, examples, CI workflows, and developer tools are not bundled.

The source archive contains `src/tunarag`, `pyproject.toml`, `README.md`, `CHANGELOG.md`,
generated `PKG-INFO`, and the small `.gitignore` automatically retained by Hatchling.
It is sufficient to rebuild the wheel with the declared build
backend. Earlier source distributions included repository assets; 0.3.0 explicitly
allowlists required files. Get the GitHub checkout to run tests or build the docs site.

Dependencies are not copied into either archive. Frameworks, RAGAS, MLflow, documentation,
and development dependencies are optional extras, installed only when requested. Their
separate dependencies can be much larger than TunaRAG itself. Install only the extras
needed for your pipeline, for example `pip install "tunarag-python[langchain]==0.3.0"`.

## Release checks

`python scripts/check_distribution.py dist` validates every release archive. Both CI and
the trusted publishing workflow run this gate; unexpected files stop publication. Secrets,
live receipts, private datasets, and local generated outputs must never be included.
Rebuilding from the source archive and importing a freshly installed wheel verifies that
excluding repository assets does not break installation.

Publishing uses GitHub Actions OIDC, not a repository-stored PyPI token. Release from a
green, immutable version tag and verify the published index artifacts in a fresh environment.
Packaging checks do not replace functional testing. In particular, the negative prompt
injection findings in [mixed-topic validation](multicorpus-validation.md) remain known
limitations; this release does not claim malicious retrieved documents are safe.
