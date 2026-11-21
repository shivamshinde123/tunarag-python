# TunaRAG, explained in 7 diagrams

A visual story of how TunaRAG works, from the big picture down to each stage. Read the diagrams
in order: each one zooms into a single step (the `n / 7` in the top-right corner shows where you
are), and the yellow sticky note at the bottom is the one thing to remember.

- `*.excalidraw`: editable sources. Open them at [excalidraw.com](https://excalidraw.com) or in
  the VS Code Excalidraw extension. Logos and icons are embedded in the file.
- `png/*.png`: 2x exports, ready for slides, the README, or the docs site.

Colour key: **blue** = your app (what you own) · **orange** = TunaRAG · **green** = results ·
**grey** = storage and data · **violet** = optional LLM helpers · **yellow** = notes and rules.

| # | Diagram | Talk track (one line to say while showing it) |
|---|---|---|
| 1 | [Big picture](png/01-big-picture.png) | "Tuning RAG by eye is slow and unrepeatable. You give TunaRAG your questions, the settings to try and your goal, and it finds the best settings for the pipeline you already have." |
| 2 | [The loop](png/02-optimization-loop.png) | "Everything is one loop: pick settings, run your RAG on every question, grade the answers, score them, learn, repeat. One lap is a trial, and every trial is saved to SQLite." |
| 3 | [Test data](png/03-test-data.png) | "Bring JSON, JSONL or CSV, or generate Q&A with an LLM. It all becomes one versioned dataset, split the same way every time into optimize, validation and test." |
| 4 | [Adapter](png/04-adapter-boundary.png) | "Your app keeps its index, prompts and keys. The official adapter only passes settings and a question in, and an answer plus usage back out." |
| 5 | [Search](png/05-search-strategies.png) | "You define the knobs. Random search gives a fair, repeatable baseline; LLM-guided search makes smarter guesses and falls back to random if its suggestions keep failing." |
| 6 | [Scoring](png/06-scoring.png) | "Evaluators (your checks or RAGAS) produce metrics; the objective weighs quality, cost and latency into one number. Stop rules end the study." |
| 7 | [Results](png/07-results-and-reliability.png) | "SQLite is the source of truth: a crashed run resumes where it stopped, the cache skips repeat work, and results export to JSON or CSV, with an optional MLflow mirror." |

Numbers shown in the diagrams (weights, scores, costs) are illustrative examples.
