# Documentation diagram sources

## GitHub Pages diagrams

The home page, live ADK guide, system architecture and code-flow guide use checked-in
SVG images. These render without Mermaid JavaScript, external CDN requests or browser
initialization. Each image has an editable `.mmd` source with the same filename.
The flow guide retains its detailed copyable text outlines below the diagrams.
Images use white backgrounds to keep labels readable in both light and dark themes.

After editing a source, regenerate all existing Pages SVGs using Mermaid CLI 12.0.0
and the repository renderer. Supply the path to an existing installation:

```sh
python scripts/render_docs_diagrams.py --renderer /path/to/node_modules/@mermaid-js/mermaid-cli/src/cli.js --puppeteer-config /path/to/puppeteer.json
```

Omit `--puppeteer-config` when the renderer already has a browser. The script renders
only `.mmd` files with existing `.svg` counterparts, so it does not replace README PNGs.
It sets explicit intrinsic width/height from the viewBox: percentage-only SVG sizes can
otherwise collapse tall diagrams to tiny images when embedded using Markdown.
Commit source and rendered SVG together. Use the existing-browser configuration below
to avoid downloading another browser. Node and Mermaid CLI are authoring tools only;
the documentation build and installed package do not need them.

Verify every built image reference before publishing:

```sh
python -m mkdocs build --strict
python scripts/check_docs_diagrams.py site
```

Also inspect the changed diagrams in a browser at desktop and mobile widths, in
both themes and after navigating between pages. Build checks catch missing assets
and empty SVGs but do not establish visual readability.

## README and PyPI diagrams

The public package README uses static PNGs because PyPI cannot execute Mermaid.
The matching `.mmd` files remain editable source. Regenerate with Mermaid CLI 12.0.0:

```sh
npx --yes --package @mermaid-js/mermaid-cli@12.0.0 mmdc -i docs/assets/diagrams/optimization-loop.mmd -o docs/assets/diagrams/optimization-loop.png --size 1400 -s 2 -b white -t neutral
npx --yes --package @mermaid-js/mermaid-cli@12.0.0 mmdc -i docs/assets/diagrams/post-commit-callbacks.mmd -o docs/assets/diagrams/post-commit-callbacks.png --size 1200 -s 2 -b white -t neutral
```

When using an existing browser, set `PUPPETEER_SKIP_DOWNLOAD=true` and supply `-p`
with a local Puppeteer JSON configuration containing its `executablePath`. Keep machine
paths out of git. Inspect labels and arrows after regeneration. Commit both source and
PNG; deploy GitHub Pages before uploading a release referencing the public assets.
These files are documentation-only and never belong in wheels or source distributions.
