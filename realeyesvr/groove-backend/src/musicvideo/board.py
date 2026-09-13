"""Anchor an external storyboard onto the measured timeline.

A storyboard written against a lyric sheet carries good prompts and a bad clock:
whoever wrote it could read the words but never heard the track, so the section
times are guessed -- typically a uniform grid that ignores the intro and any
instrumental break.

The prompts are the valuable part. This module throws the board's own times away
and re-anchors each row to where its lyric is actually sung, using the alignment
from `lyrics.py`.
"""
import json
import re
from pathlib import Path

WORD = re.compile(r"[a-z0-9']+")


def _norm(text: str) -> str:
    return " ".join(WORD.findall(text.lower().replace("’", "'")))


def _flatten(lyr: dict) -> list[dict]:
    """Every sung line in order, tagged with its section label."""
    out = []
    for sec in lyr["sections"]:
        for line in sec["lines"]:
            out.append({"label": sec["label"], "text": line["text"],
                        "start_s": line["start_s"], "end_s": line["end_s"]})
    return out


def anchor(board: dict, lyr: dict, duration: float) -> list[dict]:
    """Give every board row a real start and end.

    Rows are matched in order and the search only ever moves forward, so a
    repeated hook like "Face in the dust" lands on the right repeat instead of
    always snapping back to the first one.
    """
    lines = _flatten(lyr)
    placed, cursor = [], 0

    for row in board["rows"]:
        want = _norm(row["anchor"])
        hit = None
        for i in range(cursor, len(lines)):
            line = lines[i]
            if line["label"] != row["label"]:
                continue
            if _norm(line["text"]).startswith(want) or want in _norm(line["text"]):
                hit = i
                break
        if hit is None:
            continue
        placed.append({**row, "start_s": lines[hit]["start_s"], "_line": hit})
        cursor = hit + 1

    # A row runs to the last line actually sung before the next row starts --
    # not all the way to that row. Otherwise a row either side of an
    # instrumental break silently swallows the break, and a prompt written for
    # four sung lines gets held over thirty seconds of music.
    for i, row in enumerate(placed):
        stop = placed[i + 1]["start_s"] if i + 1 < len(placed) else duration
        sung = [l["end_s"] for l in lines[row["_line"]:] if l["start_s"] < stop]
        row["end_s"] = min(max(sung) if sung else stop, stop)
        row.pop("_line", None)

    return [r for r in placed if r["end_s"] - r["start_s"] > 0.5]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def coverage(rows: list[dict], duration: float) -> list[tuple]:
    """Stretches of the track no board row covers -- intro, breaks, outro."""
    gaps, last = [], 0.0
    for row in rows:
        if row["start_s"] - last > 4.0:
            gaps.append((round(last, 2), round(row["start_s"], 2)))
        last = max(last, row["end_s"])
    if duration - last > 4.0:
        gaps.append((round(last, 2), round(duration, 2)))
    return gaps
