"""Synthesize the light background bed -> public/music/bed.mp3 (numpy + ffmpeg, no downloads).

105 BPM, C - Am - F - G, with soft keys, a plucked arpeggio, a round bass and light drums.
Sections change every 8 bars so the loop does not feel stuck.
"""

import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 105
BEAT = 60 / BPM
BAR = 4 * BEAT
SECONDS = 205
OUT = Path(__file__).parent / "public" / "music"

N = int(SECONDS * SR)
left = np.zeros(N)
right = np.zeros(N)


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def add(sig: np.ndarray, start: float, pan: float = 0.0) -> None:
    i = int(start * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    left[i : i + len(sig)] += sig * (1 - pan) / 2**0.5
    right[i : i + len(sig)] += sig * (1 + pan) / 2**0.5


def tone(
    freq: float, dur: float, decay: float, harmonics=((1, 1.0),), attack: float = 0.004
) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    wave = sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in harmonics)
    env = np.exp(-t / decay) * np.minimum(1, t / attack)
    return wave * env


def keys(freq: float, dur: float) -> np.ndarray:  # soft electric piano
    t = np.arange(int(dur * SR)) / SR
    trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    return tone(freq, dur, 1.1, ((1, 1.0), (2, 0.25), (3, 0.06)), attack=0.012) * trem


def pluck(freq: float) -> np.ndarray:  # marimba-ish
    return tone(freq, 0.6, 0.16, ((1, 1.0), (4, 0.18), (10, 0.03)))


def bass(freq: float, dur: float) -> np.ndarray:
    return tone(freq, dur, 0.5, ((1, 1.0), (2, 0.35)), attack=0.01)


def kick() -> np.ndarray:
    t = np.arange(int(0.3 * SR)) / SR
    f = 50 + 70 * np.exp(-t / 0.04)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.11)


rng = np.random.default_rng(7)


def hat(length: float = 0.05) -> np.ndarray:
    n = rng.standard_normal(int(length * SR))
    n = np.diff(n, prepend=0)  # crude high-pass
    return n * np.exp(-np.arange(len(n)) / SR / (length / 4))


def snap() -> np.ndarray:
    n = rng.standard_normal(int(0.12 * SR))
    t = np.arange(len(n)) / SR
    return (0.6 * n + np.sin(2 * np.pi * 190 * t)) * np.exp(-t / 0.035)


# C, Am, F, G (root midi, chord tones)
CHORDS = [
    (48, [60, 64, 67, 72]),
    (45, [57, 60, 64, 69]),
    (41, [57, 60, 65, 69]),
    (43, [55, 59, 62, 67]),
]
ARP_A = [0, 1, 2, 3, 2, 1, 2, 3]
ARP_B = [3, 2, 1, 2, 0, 2, 1, 3]

bars = int(SECONDS / BAR) + 1
for b in range(bars):
    t0 = b * BAR
    section = (b // 8) % 4  # 0 intro-ish, 1 groove, 2 variation, 3 groove
    root, notes = CHORDS[b % 4]

    for n in notes[:3]:
        add(0.10 * keys(hz(n), BAR * 0.98), t0, pan=-0.2)

    arp = ARP_B if section == 2 else ARP_A
    if section > 0 or b >= 2:
        for i, k in enumerate(arp):
            octave = 12 if section == 2 and i % 4 == 3 else 0
            add(0.09 * pluck(hz(notes[k] + 12 + octave)), t0 + i * BEAT / 2, pan=0.35)

    add(0.30 * bass(hz(root), BEAT * 1.6), t0)
    add(0.24 * bass(hz(root + 7), BEAT * 0.9), t0 + 2.5 * BEAT)
    add(0.20 * bass(hz(root + 12 if b % 2 else root), BEAT * 0.9), t0 + 3 * BEAT)

    if section > 0:
        add(0.35 * kick(), t0)
        add(0.30 * kick(), t0 + 2 * BEAT)
        add(0.08 * snap(), t0 + BEAT, pan=0.1)
        add(0.08 * snap(), t0 + 3 * BEAT, pan=0.1)
    for e in range(8):
        add((0.035 if e % 2 else 0.018) * hat(), t0 + e * BEAT / 2, pan=0.5)

# Light stereo "room": two feedback-free echoes.
for d, g in ((0.11, 0.18), (0.23, 0.10)):
    k = int(d * SR)
    left[k:] += g * right[:-k]
    right[k:] += g * left[:-k]

mix = np.stack([left, right], axis=1)
fade = np.minimum(1, np.arange(N) / (1.5 * SR))
mix *= fade[:, None]
mix /= np.max(np.abs(mix)) / 0.89

OUT.mkdir(parents=True, exist_ok=True)
wav = OUT / "bed.wav"
pcm = (mix * 32767).astype("<i2")
with wave.open(str(wav), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
subprocess.run(
    ["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-b:a", "192k", str(OUT / "bed.mp3")],
    check=True,
)
wav.unlink()
print("wrote", OUT / "bed.mp3")
