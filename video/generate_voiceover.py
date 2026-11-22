"""Regenerate public/voiceover/*.mp3 from narration.json (needs `pip install edge-tts`)."""

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
VOICE = "en-US-BrianNeural"  # casual, approachable; English-only so short lines never switch accent

for scene in json.loads((HERE / "narration.json").read_text(encoding="utf-8")):
    out = HERE / "public" / "voiceover" / f"{scene['id']}.mp3"
    subprocess.run(
        [
            "edge-tts",
            "--voice",
            VOICE,
            "--rate=+6%",
            "--pitch=+2Hz",
            "--text",
            scene["text"],
            "--write-media",
            str(out),
        ],
        check=True,
    )
    print("wrote", out.name)

# Scene lengths drive the timeline in src/Video.tsx.
durations = {}
for mp3 in sorted((HERE / "public" / "voiceover").glob("*.mp3")):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
        check=True,
        capture_output=True,
        text=True,
    )
    durations[mp3.stem] = round(float(probe.stdout), 3)
(HERE / "src" / "durations.json").write_text(json.dumps(durations, indent=2) + "\n")
