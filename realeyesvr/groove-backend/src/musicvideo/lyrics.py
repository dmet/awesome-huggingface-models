"""Align known lyrics to the audio timeline.

This is forced alignment, not transcription: we already have the words, so the
job is only to find *when* each one is sung. ASR on sung vocals is unreliable
on its own, but a noisy transcript is plenty when it only has to act as an
anchor track for text we already know.

The payoff is the section markers. [Verse 1] / [Chorus] / [Bridge] in the lyric
sheet are ground truth for song structure -- far better than guessing at it by
clustering timbre.
"""
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

from config import settings

WORD = re.compile(r"[a-z0-9']+")


def parse_lyrics(path: Path) -> list[dict]:
    """Lyric sheet -> [{label, lines: [...]}] keeping [Section] markers."""
    sections, current = [], None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        marker = re.fullmatch(r"\[(.+)\]", line)
        if marker:
            current = {"label": marker.group(1).strip(), "lines": []}
            sections.append(current)
        elif current is not None:
            current["lines"].append(line)
    return sections


def _norm(text: str) -> list[str]:
    return WORD.findall(text.lower().replace("’", "'"))


def transcribe(audio: Path, model_size: str, vocals: Path | None = None):
    """Return [(word, start, end)] with word-level timing."""
    from faster_whisper import WhisperModel

    src = vocals if vocals and vocals.exists() else audio
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(src), word_timestamps=True, vad_filter=False, beam_size=5,
        condition_on_previous_text=False,
    )
    words = []
    for seg in segments:
        for w in (seg.words or []):
            token = _norm(w.word)
            if token:
                words.append((token[0], float(w.start), float(w.end)))
    return words


def align(sections: list[dict], asr: list[tuple]) -> dict:
    """Map every lyric word onto a time by anchoring to the ASR stream."""
    lyric_words, owner = [], []          # owner[i] = (section_idx, line_idx)
    for si, sec in enumerate(sections):
        for li, line in enumerate(sec["lines"]):
            for token in _norm(line):
                lyric_words.append(token)
                owner.append((si, li))

    asr_tokens = [w for w, _, _ in asr]
    times: list[float | None] = [None] * len(lyric_words)

    matcher = SequenceMatcher(None, lyric_words, asr_tokens, autojunk=False)
    matched = 0
    for i, j, n in matcher.get_matching_blocks():
        for k in range(n):
            times[i + k] = asr[j + k][1]
            matched += 1

    _interpolate(times)

    # roll word times up into lines, then lines up into sections
    out_sections = []
    for si, sec in enumerate(sections):
        lines = []
        for li, text in enumerate(sec["lines"]):
            spans = [t for t, o in zip(times, owner) if o == (si, li) and t is not None]
            if spans:
                lines.append({"text": text, "start_s": round(min(spans), 3),
                              "end_s": round(max(spans), 3)})
        if not lines:
            continue
        out_sections.append({
            "index": len(out_sections),
            "label": sec["label"],
            "start_s": lines[0]["start_s"],
            "end_s": max(l["end_s"] for l in lines),
            "lines": lines,
        })

    return {
        "word_count": len(lyric_words),
        "matched_words": matched,
        "match_rate": round(matched / len(lyric_words), 3) if lyric_words else 0.0,
        "asr_word_count": len(asr),
        "sections": out_sections,
    }


def _interpolate(times: list) -> None:
    """Fill unmatched words by walking between the anchors either side."""
    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        return
    for i in range(len(times)):
        if times[i] is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is None:
            times[i] = times[known[0]]
        elif nxt is None:
            times[i] = times[known[-1]]
        else:
            span = (times[nxt] - times[prev]) / (nxt - prev)
            times[i] = times[prev] + span * (i - prev)


def run(audio: Path, lyrics_path: Path, vocals: Path | None = None) -> Path:
    model_size = os.getenv("WHISPER_MODEL", "small")
    sections = parse_lyrics(lyrics_path)
    asr = transcribe(audio, model_size, vocals)
    data = align(sections, asr)
    data["audio_file"] = audio.name
    data["whisper_model"] = model_size
    data["vocals_source"] = vocals.name if vocals and vocals.exists() else None

    settings.ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out = settings.ANALYSIS_DIR / f"{audio.stem}.lyrics.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out
