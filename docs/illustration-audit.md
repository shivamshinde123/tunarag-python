# Illustration audit

Reviewed every existing Ian/Xiaohei illustration against the current framework-only
README on 2026-10-09. A visual earns its space when it explains an otherwise easy-to-miss
boundary, decision or failure path. Decoration and duplicate summaries do not qualify.

## Existing illustrations

| Original file | Decision | Reason and placement |
|---|---|---|
| `01-optimization-loop.png` | Remove | Repeats the adjacent Mermaid flow; generic "learn" label can imply RandomSearch learns from observations. |
| `02-rag-adapter-boundary.png` | Replace | Shows only output flowing into TunaRAG; omits candidate settings/query flowing into the framework. |
| `03-dataset-preparation.png` | Replace | Dense normalization metaphor and ambiguous optimize/test trays do not explain leakage prevention. |
| `04-search-strategies.png` | Keep | Distinguishes proposal from validation and illustrates bounded invalid-LLM fallback to random search. |
| `05-persistence-and-resume.png` | Keep | Makes the durable commit versus interrupted work boundary memorable. Resume still requires compatible identities and lease recovery. |
| `06-results-and-reports.png` | Move to Objectives | Three competing axes clarify a user-defined tradeoff, not a universally best result. Export APIs remain text-only. |

Removed assets are deleted from the current tree, not merely hidden; git history retains
their previous versions. README and the documentation site's included usage guide consume
the same five remaining assets. Illustrations are excluded from PyPI archives.

## New illustration specifications and QA

Both were generated with the built-in image tool, inspected visually, and saved under
`docs/assets/tunarag-python-readme-illustrations/`. No existing asset was overwritten.

| File | Placement and core meaning | Structure/action | Labels |
|---|---|---|---|
| `07-framework-adapter-control.png` | Official adapters: parameters/query go out, answer/usage return; framework ownership stays separate. | System fragment; Xiaohei actively joins paired cables. | TunaRAG; adapter; framework RAG; settings + query; answer + usage |
| `08-held-out-evaluation.png` | Dataset splitting: choose on tuning data, reserve test data for a frozen final check. | Separation metaphor; Xiaohei seals the untouched test envelope. | tune; choose config; untouched test; final check |

| QA check | 07 | 08 |
|---|---|---|
| 16:9 horizontal (rounded raster dimensions) | Pass | Pass |
| White background / ample whitespace | Pass | Pass |
| Xiaohei performs the core action | Pass | Pass |
| English labels readable and sparse | Pass: five | Pass: four |
| No header/title or formal slide look | Pass | Pass |
| Fresh metaphor, not copied from skill examples | Pass | Pass |
| Semantic boundary | Opposite arrows visibly distinct | No test-to-tuning connection |
| Saved PNG | `07-framework-adapter-control.png` | `08-held-out-evaluation.png` |

Captions supply the technical qualifications that a sketch cannot: candidate settings
must actually be consumed by the framework; split selection and final evaluation remain
the caller's responsibility. A tied envelope is a leakage-prevention metaphor, not an
encryption/security guarantee. The tradeoff winner is best among evaluated trials under
the chosen objective, not a globally optimal configuration.

## 2026-10-10 GitHub Pages rendering audit

The deployed home and live Google ADK pages produced empty Mermaid containers in
Chromium; the external Mermaid request returned successfully but no diagram SVG
appeared. All seven Usage Guide PNGs loaded with nonzero intrinsic dimensions.
The architecture outline and seven code-flow outlines were intentionally plain
text rather than broken image files; they now have companion visual diagrams.

| Surface | Correction |
|---|---|
| Home | Static optimization-overview SVG instead of runtime Mermaid |
| Live Google ADK testing | Static PDF/retrieval/ADK/scoring SVG |
| System architecture | Visual framework, storage and callback relationships above the text outline |
| Code flow | Seven visual flows covering setup, optimization, resume, trial lifecycle, quickstart and framework adapters |
| README / Usage Guide | Keep the seven working PNGs unchanged |

Each new SVG has an editable Mermaid source, explanatory alternative text, a white
background and explicit intrinsic dimensions. These prevent dependency on external
Mermaid scripts and avoid tall SVGs collapsing into tiny percentage-sized images.
Detailed text outlines remain available for copying and accessible reading.

Local verification: strict MkDocs build; 17 unique image assets checked across 38
built HTML pages (including 404); browser navigation through all 37 sitemap pages
without broken images or runtime Mermaid containers. Check the seven code-flow
images at 1440px and 390px in light and dark themes. Verify instant navigation to
the live ADK guide preserves the page context and displays its SVG. Browser checks
serve the local build through the production URL layout, not a deployed-site claim.
Automated build checks and regression tests guard missing assets, empty SVGs,
percentage-only sizing and reintroduced browser-dependent diagrams.
