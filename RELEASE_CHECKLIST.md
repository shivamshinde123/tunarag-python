# V0.1 Release Checklist

## Required gates

- [x] Public version is `0.1.0` in package code and distribution metadata.
- [x] Python 3.10 and 3.13 pass on Linux and Windows; intermediate versions are classified.
- [x] Ruff formatting/linting, strict mypy, tests, sdist, and wheel builds pass.
- [x] CI force-installs and imports the built wheel.
- [x] The provider-free quickstart writes SQLite, JSON, and CSV outputs.
- [x] README, changelog, contribution, security guidance, and license metadata exist.
- [x] Optional RAGAS and MLflow imports remain outside core package import paths.
- [x] V0.1 non-goals and deferred formal Pareto semantics are documented.

## Publish-time gates

- [ ] Confirm the `tunarag-python` name and owner account on the target package index.
- [ ] Create an annotated `v0.1.0` tag from the final green `main` commit.
- [ ] Build from a clean checkout and inspect wheel/sdist contents.
- [ ] Publish to TestPyPI and run the quickstart in a fresh environment.
- [ ] Publish to PyPI, verify metadata links, then create the GitHub release from `CHANGELOG.md`.

Publishing credentials and package-index publication are intentionally manual external actions.
