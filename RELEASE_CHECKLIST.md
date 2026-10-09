# V0.3.0 Release Checklist

## Required gates

- [x] Public version is `0.3.0` in package code and distribution metadata.
- [x] Python 3.10 and 3.13 pass on Linux and Windows; intermediate versions are classified.
- [x] Ruff formatting/linting, strict mypy, tests, sdist, and wheel builds pass.
- [x] CI force-installs and imports the built wheel.
- [x] The provider-free quickstart writes SQLite, JSON, and CSV outputs.
- [x] README, changelog, contribution, security guidance, and license metadata exist.
- [x] LangChain and LangGraph remain optional and outside core import paths.
- [x] Real LangChain 1.x and LangGraph 1.x compatibility tests pass in CI.
- [x] V0.3 framework-only migration, mapping hooks, usage behavior, and non-goals are documented.
- [x] Real Google ADK 2.x runner execution and failure/timeout session cleanup pass locally.

## Publish-time gates

- [x] Confirm `tunarag-python` is currently available on PyPI and TestPyPI.
- [ ] Verify existing trusted publishers for `.github/workflows/publish.yml` using environments
  `testpypi` and `pypi` on their respective indexes.
- [ ] Create an annotated `v0.3.0` tag from the final green `main` commit.
- [ ] Build from a clean checkout and inspect wheel/sdist contents.
- [ ] Run the automated archive allowlist guard and rebuild a wheel from the lean sdist.
- [ ] Publish to TestPyPI and run the quickstart in a fresh environment.
- [ ] Publish to PyPI, verify metadata links, then create the GitHub release from `CHANGELOG.md`.

Publishing uses GitHub Actions OIDC trusted publishing. No long-lived package-index token belongs in
the repository or GitHub secrets.
