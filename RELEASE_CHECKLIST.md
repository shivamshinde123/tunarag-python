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
- [x] Verify the existing `pypi` trusted publisher for `.github/workflows/publish.yml`.
- [x] Create an annotated `v0.3.0` tag from the merged release PR after all 11 CI checks pass.
- [x] Build from a clean Actions checkout and inspect wheel/sdist contents.
- [x] Run the automated archive allowlist guard and rebuild a wheel from the lean sdist.
- [x] Publish to PyPI; verify index metadata, hashes, fresh installation and offline LangChain
  quickstart; create the GitHub release using the changelog scope.
- TestPyPI was not used for this release; the existing production trusted publisher was used.

## Publication evidence (2026-10-09)

- Release PR: #48; tag commit: `4fab625689aab4f17933718355a1584419f03d6c`.
- Successful trusted publication: Actions run `37981326626`.
- PyPI wheel: 67,908 bytes; source archive: 71,827 bytes. Published archives independently
  downloaded, checked against index SHA-256 digests, and passed the content allowlist.
- Fresh PyPI installation with the LangChain extra ran the provider-free quickstart and wrote
  SQLite, JSON and CSV outputs. No paid provider requests were made.
- Local source suite: 195 passed, 39 skipped; opt-in adversarial-prompt limitations remain
  documented in `docs/multicorpus-validation.md` and are not claimed fixed.

Publishing uses GitHub Actions OIDC trusted publishing. No long-lived package-index token belongs in
the repository or GitHub secrets.
