# README diagram sources

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
