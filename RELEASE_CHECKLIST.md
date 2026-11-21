# Release Checklist

## 0.4.0 release

Ships the code-vs-documentation audit fixes (`docs/audit-2026-11-21/`, PR #57). This is a minor
release because identity hashes changed: studies started with 0.3.x cannot be resumed and old
evaluation-cache entries are not reused (see CHANGELOG, Migration). New options: `token_prices`,
`events_mapper`, `ObjectiveTerm.min_coverage`, `MetricEvaluator(identity=)`, and
`SyntheticDatasetBuilder(allow_partial=)`. Documentation builds now require `mkdocstrings` 1.x.

- [x] All PR #57 CI checks pass (Linux and Windows, Python 3.10-3.13, build, live-dependencies).
- [x] Merge PR #57; create annotated tag `v0.4.0` on the merge commit.
- [x] Run `publish.yml` with `target=pypi` from `v0.4.0`; confirm the trusted publication.
- [x] Verify PyPI metadata and a fresh install (`tunarag.__version__ == "0.4.0"`) running the
  provider-free quickstart.
- [x] Create the GitHub release `v0.4.0` from the CHANGELOG 0.4.0 section.

### Publication evidence (2026-11-21)

- Release PR: #57, merged with an owner-approved admin override because `main` is locked and
  requires a review; merge commit `e17b2d2b1dfeed78ba120f14883d540c855b964f`, annotated tag
  `v0.4.0`. All 11 CI checks passed on head `22fa3ba` before the merge.
- Successful trusted publication: Actions run `44941171649` (build, `twine check`, distribution
  allowlist, then `publish-pypi`). TestPyPI was not used.
- PyPI wheel `tunarag_python-0.4.0-py3-none-any.whl`: 78,021 bytes, SHA-256
  `5a009dee3d9feb86bf1f869e7468e678a304365cc08a8bcfaf7224afdac8cace`.
- PyPI source archive `tunarag_python-0.4.0.tar.gz`: 85,457 bytes, SHA-256
  `952d1a61b0d65167b3f7a52dfa33a8bdfc8913e2a88d2b6e4a10bd0bcadeb9e5`.
- Both archives were downloaded independently, matched the index digests, and passed
  `scripts/check_distribution.py`.
- A fresh `tunarag-python[langchain]==0.4.0` install from PyPI reported 0.4.0, exposed the new
  options, and ran the provider-free quickstart (SQLite, JSON and CSV outputs written).
- Before release: 268 unit tests passed (39 live tests skipped), plus `mypy --strict`, ruff, and
  `mkdocs build --strict` with both docs checks. The paid live suite passed 22 tests with 17
  opt-in campaign tests skipped. Real OpenRouter reruns are recorded in
  `docs/audit-2026-11-21/README.md`.
- GitHub release `v0.4.0` is marked Latest.

## 0.3.1 follow-up

This patch ships PyPI-compatible README diagram images, public documentation/asset URLs,
and the full MIT license from the preceding documentation PR. No optimizer behavior changes.
Use `v0.3.1` for trusted publication after CI passes and the documentation deployment succeeds.
Verify all seven public PNG URLs, renderer output, wheel license text and a fresh index install.
The completed 0.3.0 publication record below remains historical evidence, not a 0.3.1 receipt.

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
