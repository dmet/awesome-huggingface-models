"""Stage 1 -- pull tempo, a beat grid, downbeats, sections and energy out of a track.

Runway never sees this. It exists so the *cuts* land on the music.
"""
import json
from pathlib import Path

import librosa
import numpy as np

from config import settings

MIN_SECTION_S = 4.0


def analyze(audio_path: Path, beat_source: Path | None = None) -> dict:
    """Analyze `audio_path`. If `beat_source` is given (e.g. a Suno drum stem),
    beats are tracked on that instead -- a percussion-only track gives a much
    cleaner grid than a full mix."""
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = float(len(y) / sr)

    if beat_source and beat_source.exists():
        yb, srb = librosa.load(str(beat_source), sr=None, mono=True)
    else:
        yb, srb = y, sr

    tempo, beat_frames = librosa.beat.beat_track(y=yb, sr=srb, trim=False)
    beats = librosa.frames_to_time(beat_frames, sr=srb).tolist()
    tempo = float(np.atleast_1d(tempo)[0])
    # Ambient, spoken, or unusually quiet tracks may not yield a beat grid.
    # Keep the preview flow usable with a clearly deterministic 120 BPM grid;
    # consumers can still see beat_source=None and the resulting grid values.
    if not beats or tempo <= 0:
        tempo = 120.0
        beat_s = 60.0 / tempo
        beats = np.arange(0.0, duration, beat_s).tolist()

    onset_env = librosa.onset.onset_strength(y=yb, sr=srb)
    downbeats, bar_phase = _find_downbeats(beats, onset_env, srb)
    sections = _find_sections(y, sr, downbeats, duration)

    # coarse loudness envelope, so later stages can score any arbitrary span
    # (e.g. a lyric section) without decoding the audio again
    rms = librosa.feature.rms(y=y)[0]
    rms_hz = 10
    grid = np.arange(0, duration, 1.0 / rms_hz)
    env = np.interp(grid, librosa.times_like(rms, sr=sr), rms)
    env = env / (env.max() or 1.0)

    return {
        "audio_file": audio_path.name,
        "rms_hz": rms_hz,
        "rms": [round(float(v), 4) for v in env],
        "beat_source": beat_source.name if beat_source and beat_source.exists() else None,
        "duration_s": round(duration, 3),
        "tempo_bpm": round(tempo, 2),
        "beats_per_bar": settings.BEATS_PER_BAR,
        "bar_phase": bar_phase,
        "beat_count": len(beats),
        "beats": [round(b, 4) for b in beats],
        "downbeats": [round(b, 4) for b in downbeats],
        "sections": sections,
    }


def _find_downbeats(beats, onset_env, sr):
    """librosa has no downbeat tracker. Assume a fixed meter and pick the phase
    whose beats carry the most onset energy -- a decent proxy for beat 1."""
    n = settings.BEATS_PER_BAR
    if len(beats) < n:
        return list(beats), 0

    times = librosa.times_like(onset_env, sr=sr)
    strength = np.interp(beats, times, onset_env)

    scores = [float(strength[phase::n].mean()) for phase in range(n)]
    phase = int(np.argmax(scores))
    grid = list(beats[phase::n])

    # the tracker usually misses bar 1 near t=0; walk the grid back to the start
    if len(grid) >= 2:
        step = grid[1] - grid[0]
        while grid[0] - step >= -0.05:
            grid.insert(0, max(0.0, grid[0] - step))
    return grid, phase


def _find_sections(y, sr, downbeats, duration):
    """Segment the track by timbre+harmony, then snap each boundary to the
    nearest downbeat so a section change is always a legal cut point."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    feat = np.vstack([
        librosa.util.normalize(chroma, axis=0),
        librosa.util.normalize(mfcc, axis=0),
    ])

    # ~1 section per 15s, kept inside a sane range
    k = int(np.clip(round(duration / 15.0), 3, 10))
    bounds = librosa.segment.agglomerative(feat, k)
    bound_times = librosa.frames_to_time(bounds, sr=sr).tolist()

    edges = sorted({0.0, *(_snap(t, downbeats) for t in bound_times), duration})
    rms = librosa.feature.rms(y=y)[0]
    rms_times = librosa.times_like(rms, sr=sr)
    peak = float(rms.max()) or 1.0

    # merge slivers into the neighbouring segment so no audio is left uncovered
    spans = list(zip(edges, edges[1:]))
    merged: list[list[float]] = []
    for start, end in spans:
        if merged and end - start < MIN_SECTION_S:
            merged[-1][1] = end
        elif merged and merged[-1][1] - merged[-1][0] < MIN_SECTION_S:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    sections = []
    for start, end in merged:
        window = rms[(rms_times >= start) & (rms_times < end)]
        sections.append({
            "index": len(sections),
            "start_s": round(start, 3),
            "end_s": round(end, 3),
            "duration_s": round(end - start, 3),
            "energy": round(float(window.mean() / peak) if window.size else 0.0, 3),
        })
    return sections


def _snap(t, grid):
    if not grid:
        return t
    return min(grid, key=lambda g: abs(g - t))


def run(audio_path: Path, beat_source: Path | None = None) -> Path:
    data = analyze(audio_path, beat_source)
    settings.ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out = settings.ANALYSIS_DIR / f"{audio_path.stem}.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out
