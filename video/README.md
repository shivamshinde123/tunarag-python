# TunaRAG explainer video

A ~3:15 Remotion explainer for TunaRAG: the motivation (tuning RAG by eye), then the adapter
boundary, the trial loop, test data, search, scoring, reliability, a code walkthrough and a close.
It is repository-only and never ships to PyPI (the sdist includes only `src/` and metadata).

| Path | What it is |
|---|---|
| `narration.json` | The voiceover script, one entry per scene |
| `generate_voiceover.py` | Regenerates `public/voiceover/*.mp3` with `edge-tts` and writes `src/durations.json` |
| `make_music.py` | Synthesizes the background bed `public/music/bed.mp3` (numpy + ffmpeg) |
| `src/ui.tsx` | Palette, fonts and shared pieces (cards, pills, sticky notes, glyph) |
| `src/scenes-a.tsx`, `src/scenes-b.tsx` | The ten scenes; animation times are seconds into each line of narration |
| `src/Video.tsx` | Scene order; each scene lasts as long as its narration plus padding |
| `public/logos/` | Framework logos taken from `docs/diagrams/*.excalidraw` |

```console
npm i
npm run dev                                                # Remotion Studio preview
npx remotion render TunaRAG out/tunarag-explainer.mp4      # final MP4
```

The landing page embeds a web-encoded copy. After a re-render, refresh it from the repository root:

```console
ffmpeg -i video/out/tunarag-explainer.mp4 -c:v libx264 -preset slow -crf 27 -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart docs/landing/media/tunarag-explainer.mp4
ffmpeg -ss 36 -i video/out/tunarag-explainer.mp4 -frames:v 1 -vf scale=1280:-1 -q:v 4 docs/landing/media/tunarag-explainer-poster.jpg
```

To change the narration, edit `narration.json`, run `python generate_voiceover.py`, then adjust
the `at={...}` cue times in the scene files if a line moved.

Write `rag` and `Tune-a-rag` in the narration. Capitalised `RAG` is read letter by letter.
