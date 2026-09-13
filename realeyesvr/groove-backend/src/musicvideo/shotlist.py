"""Stage 2 -- turn the beat grid + a style file into a beat-aligned shot list.

This is where the music actually drives the edit: every shot boundary is a
downbeat, shot length is measured in bars, and section energy decides how fast
the cuts come.
"""
import csv
import json
import math
from pathlib import Path

from config import settings

# downbeats are 4dp, section bounds 3dp -- compare with slack
SNAP_TOL = 0.01
# an instrumental stretch shorter than this is folded into the sung section
MIN_INSTRUMENTAL_S = 6.0
# gen4.5: promptText is capped at 1000 UTF-16 code units
PROMPT_BUDGET = 1000

CSV_COLUMNS = [
    "shot", "slate", "label", "start_s", "end_s", "slot_s", "bars",
    "size", "lens", "movement", "direction", "pov", "subject",
    "lyric", "action", "gen_duration_s", "from_board", "prompt",
]


def sections_from_lyrics(analysis: dict, lyr: dict) -> list[dict]:
    """Replace the guessed sections with the ones the lyric sheet states.

    Clustering finds *changes* in timbre; it cannot tell a pre-chorus from a
    verse because they often sound the same. The lyric sheet names the real
    structure, and the instrumental stretches between sung sections become
    Intro / Break / Outro.
    """
    duration = analysis["duration_s"]
    downbeats = analysis["downbeats"]
    env, hz = analysis.get("rms", []), analysis.get("rms_hz", 10)

    named, last = [], 0.0
    for sec in lyr["sections"]:
        start = _snap(sec["start_s"], downbeats)
        if start - last > MIN_INSTRUMENTAL_S:
            named.append((last, start, "Intro" if not named else "Break", []))
        elif named:
            named[-1] = (*named[-1][:1], start, *named[-1][2:])
        end = _snap(sec["end_s"], downbeats)
        named.append((start, end, sec["label"], sec.get("lines", [])))
        last = end

    if duration - last > MIN_INSTRUMENTAL_S:
        named.append((last, duration, "Outro", []))
    elif named:
        named[-1] = (*named[-1][:1], duration, *named[-1][2:])

    out = []
    for start, end, label, lines in named:
        if end - start < 1.0:
            continue
        out.append({
            "index": len(out), "label": label,
            "start_s": round(start, 3), "end_s": round(end, 3),
            "duration_s": round(end - start, 3),
            "energy": round(_energy(env, hz, start, end), 3),
            "lines": lines,
        })
    return out


def sections_from_board(analysis: dict, rows: list[dict]) -> list[dict]:
    """Board rows become sections; the stretches between them keep their names.

    A storyboard is written against sung lines, so it says nothing about the
    intro, the instrumental breaks or the outro. Those become Intro / Break /
    Outro and fall through to the treatment's arc for their prompts.
    """
    duration = analysis["duration_s"]
    downbeats = analysis["downbeats"]
    env, hz = analysis.get("rms", []), analysis.get("rms_hz", 10)

    spans, last = [], 0.0
    for row in rows:
        start, end = _snap(row["start_s"], downbeats), _snap(row["end_s"], downbeats)
        if start - last > 1.0:
            spans.append((last, start, "Intro" if not spans else "Break", None, None))
        spans.append((start, end, row["label"], row["prompt"], row.get("action")))
        last = end
    if duration - last > 1.0:
        spans.append((last, duration, "Outro", None, None))

    out = []
    for start, end, label, prompt, action in spans:
        if end - start < 1.0:
            continue
        out.append({
            "index": len(out), "label": label,
            "start_s": round(start, 3), "end_s": round(end, 3),
            "duration_s": round(end - start, 3),
            "energy": round(_energy(env, hz, start, end), 3),
            "board_prompt": prompt, "action": action, "lines": [],
        })
    return out


def _energy(env, hz, start, end) -> float:
    if not env:
        return 0.5
    a, b = int(start * hz), max(int(end * hz), int(start * hz) + 1)
    window = env[a:b]
    return sum(window) / len(window) if window else 0.0


def _snap(t, grid):
    return min(grid, key=lambda g: abs(g - t)) if grid else t


def _relative_energy(sections) -> dict:
    """Rescale section energy across this track.

    A mastered track is compressed -- absolute RMS might only span 0.2-0.5, so
    mapping it straight onto the bar range leaves most of that range unused.
    Stretching quietest->0 and loudest->1 makes the cut rate actually vary.
    """
    vals = [s["energy"] for s in sections]
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-6:
        return {s["index"]: 0.5 for s in sections}
    return {s["index"]: (s["energy"] - lo) / (hi - lo) for s in sections}


def build(analysis: dict, style: dict) -> dict:
    downbeats = analysis["downbeats"]
    duration = analysis["duration_s"]
    sections = analysis["sections"]
    bar_s = (60.0 / analysis["tempo_bpm"]) * analysis["beats_per_bar"]
    rel = _relative_energy(sections)

    overrides = style.get("sections", {})
    shots = []
    for sec in sections:
        rule = overrides.get(_label(sec), {})

        # a held section is one generation stretched across the whole thing,
        # so the picture sits still until the next section cuts in
        if rule.get("hold"):
            shots.append(_shot(len(shots), 0, sec, sec["start_s"], sec["end_s"],
                               style, 0, rel[sec["index"]], duration, hold=True))
            continue

        # tolerance matters: downbeats are stored to 4dp and section bounds to
        # 3dp, so an exact >= test can round a boundary past its own downbeat
        # and silently drop a bar.
        grid = [d for d in downbeats
                if sec["start_s"] - SNAP_TOL <= d < sec["end_s"] - SNAP_TOL]
        if not grid or abs(grid[0] - sec["start_s"]) > SNAP_TOL:
            grid.insert(0, sec["start_s"])
        bars_per_shot = int(rule.get("bars") or _bars_for_energy(rel[sec["index"]]))

        i = local = 0
        while i < len(grid):
            start = grid[i]
            j = min(i + bars_per_shot, len(grid))
            end = grid[j] if j < len(grid) else sec["end_s"]
            if end - start < 0.5:  # never emit a sliver
                break
            shots.append(_shot(len(shots), local, sec, start, end, style,
                               bars_per_shot, rel[sec["index"]], duration))
            local += 1
            i = j

    shots = _merge_runts(shots, bar_s)

    # The beat tracker rarely puts a downbeat at t=0, which would leave the
    # head of the track uncovered and shift every cut earlier than the music.
    # Absorb the lead-in into shot 0.
    if shots and shots[0]["start_s"] > 0.0:
        first = shots[0]
        first["start_s"] = 0.0
        first["slot_s"] = round(first["end_s"], 3)
        first["gen_duration_s"] = _snap_duration(first["slot_s"])

    # make the last shot run to the end of the track
    if shots and shots[-1]["end_s"] < duration:
        last = shots[-1]
        last["end_s"] = round(duration, 3)
        last["slot_s"] = round(duration - last["start_s"], 3)
        last["gen_duration_s"] = _snap_duration(last["slot_s"])

    _assert_contiguous(shots, duration)
    crossings = check_screen_direction(shots)

    return {
        "audio_file": analysis["audio_file"],
        "tempo_bpm": analysis["tempo_bpm"],
        "bar_s": round(bar_s, 4),
        "duration_s": duration,
        "model": settings.MODEL,
        "ratio": settings.RATIO,
        "negative": style.get("negative", ""),
        "shot_count": len(shots),
        "line_crossings": crossings,
        "generated_seconds": sum(s["gen_duration_s"] for s in shots),
        "shots": shots,
    }


def _merge_runts(shots, bar_s):
    """Absorb undersized tail shots into their predecessor.

    A section rarely holds a whole number of shots, so the last one can come
    out a fraction of a bar long. Those are both ugly on screen and force an
    extreme retime factor, so fold them back into the shot before.
    """
    floor = settings.MIN_BARS * bar_s * 0.75
    out = []
    for shot in shots:
        if out and shot["slot_s"] < floor and not shot.get("hold") and not out[-1].get("hold"):
            prev = out[-1]
            prev["end_s"] = shot["end_s"]
            prev["slot_s"] = round(prev["end_s"] - prev["start_s"], 3)
            prev["gen_duration_s"] = _snap_duration(prev["slot_s"])
        else:
            out.append(shot)
    for i, shot in enumerate(out):
        shot["shot"] = i
    return out


def check_screen_direction(shots) -> list[dict]:
    """Flag cuts that reverse screen direction -- the 180-degree rule.

    If one shot has the subject moving left to right and the next has them
    moving right to left, the cut reads as the subject turning round. A board
    artist tracks this by eye; a generator has no idea, and each of our clips
    is an independent generation, so nothing enforces it.

    This does not block anything. It reports, because sometimes crossing the
    line is the point.
    """
    out = []
    for a, b in zip(shots, shots[1:]):
        da, db = a.get("direction", ""), b.get("direction", "")
        if da and db and OPPOSITE.get(da) == db:
            out.append({"from_shot": a["shot"], "to_shot": b["shot"],
                        "at_s": b["start_s"], "from": da, "to": db})
    return out


def _assert_contiguous(shots, duration):
    """A gap here shifts every later cut off the beat, so fail loudly."""
    if not shots:
        raise ValueError("planner produced no shots")
    if shots[0]["start_s"] != 0.0:
        raise ValueError(f"timeline starts at {shots[0]['start_s']}s, not 0")
    for a, b in zip(shots, shots[1:]):
        if abs(a["end_s"] - b["start_s"]) > 0.001:
            raise ValueError(
                f"gap between shot {a['shot']} (ends {a['end_s']}s) and "
                f"{b['shot']} (starts {b['start_s']}s)")
    if abs(shots[-1]["end_s"] - duration) > 0.001:
        raise ValueError(f"timeline ends at {shots[-1]['end_s']}s, track is {duration}s")


def _shot(idx, local_idx, sec, start, end, style, bars, rel_energy, duration, hold=False):
    slot = round(end - start, 3)
    lyric = _lyric_for(sec, start, end)
    rule = style.get("sections", {}).get(_label(sec), {})
    grammar = _grammar(idx, local_idx, rel_energy, style, rule, start / duration)
    return {
        "hold": hold,
        "shot": idx,
        "slate": _slate(_label(sec), local_idx),
        **{f: grammar[f] for f in GRAMMAR},
        "section": sec["index"],
        "start_s": round(start, 3),
        "end_s": round(end, 3),
        "slot_s": slot,
        "bars": bars,
        "label": _label(sec),
        "action": sec.get("action") or "",
        "from_board": bool(sec.get("board_prompt")),
        "lyric": lyric,
        "energy": sec["energy"],
        "energy_rel": round(rel_energy, 3),
        "gen_duration_s": (max(settings.ALLOWED_DURATIONS) if hold
                           else _snap_duration(slot)),
        "prompt": _prompt(idx, local_idx, rel_energy, style, lyric, sec,
                          start / duration, grammar),
        "clip_path": "",
        "status": "planned",
    }


def _label(sec) -> str:
    """Clustered sections have no name; lyric sections do."""
    return sec.get("label") or f"section {sec['index']}"


def _bars_for_energy(energy: float) -> int:
    """Loud sections cut fast, quiet sections hold. Linear across the range."""
    span = settings.MAX_BARS - settings.MIN_BARS
    return int(round(settings.MAX_BARS - energy * span))


def _snap_duration(slot: float) -> int:
    """Pick the generation length to buy for a slot.

    Runway only accepts a fixed set of durations and a bar is never one of
    them, so the slot and the clip will not match. Two ways to reconcile:

    retime -- buy the NEAREST length and let the assembler stretch it to fit.
              Nearest in ratio, not in seconds: a 6.5s slot is better served
              by 8s (x0.81) than by 5s (x1.30). Keeps the whole shot.
    trim   -- buy the next length UP and cut the tail off.
    """
    allowed = sorted(settings.ALLOWED_DURATIONS)
    if settings.FIT_MODE == "retime":
        return min(allowed, key=lambda d: abs(math.log(slot / d)))
    for d in allowed:
        if d >= slot:
            return d
    return allowed[-1]


def _lyric_for(sec, start, end) -> str:
    """The lyric line(s) sung during this shot."""
    hits = [l["text"] for l in sec.get("lines", [])
            if l["end_s"] > start and l["start_s"] < end]
    return " / ".join(hits)


# Film-grammar fields, in the order a real board caption states them.
# A storyboard has separated these for a century: shot size, lens, camera
# movement, screen direction and POV are distinct pieces of information, not
# one sentence. Keeping them apart makes the sheet scannable, the prompts
# consistent, and screen direction checkable.
GRAMMAR = ("movement", "size", "pov", "subject", "direction", "lens")

# Screen direction. Cutting straight from one to its opposite reads as the
# subject reversing -- the 180-degree rule. NEUTRAL is a safe pivot.
OPPOSITE = {"left to right": "right to left", "right to left": "left to right",
            "toward camera": "away from camera", "away from camera": "toward camera"}


def _slate(label: str, local_idx: int) -> str:
    """A board-style shot id: VERSE 1 shot 3 -> V1-C, not shot 27."""
    words = [w for w in label.replace("-", " ").split() if w]
    stem = "".join(w[0].upper() if not w[0].isdigit() else w for w in words) or "S"
    stem = "".join(c for c in stem if c.isalnum())
    letter = ""
    n = local_idx
    while True:
        letter = chr(ord("A") + n % 26) + letter
        n = n // 26 - 1
        if n < 0:
            break
    return f"{stem}-{letter}"


def _grammar(idx, local_idx, rel_energy, style, rule, progress) -> dict:
    """Resolve each board field. Section rule beats arc beats style default."""
    stage = {}
    if style.get("arc"):
        stage = next((a for a in style["arc"] if progress <= a.get("until", 1.0)),
                     style["arc"][-1])

    out = {}
    for field in GRAMMAR:
        for source in (rule, stage, style):
            value = source.get(field)
            if value:
                out[field] = (value[local_idx % len(value)]
                              if isinstance(value, list) else value)
                break
        else:
            out[field] = ""
    return out


def _camera(idx, local_idx, rel_energy, style, rule, progress) -> str:
    """Which camera language this shot gets.

    Precedence: an explicit per-section rule, then the arc (how the framing
    should evolve across the song), then the energy pools.
    """
    if rule.get("camera"):
        # an explicit section list is a storyboard: play it in written order,
        # counting within the section rather than across the whole song
        pool = rule["camera"]
        return pool[min(local_idx, len(pool) - 1)] if pool else ""
    elif style.get("arc"):
        stage = next((a for a in style["arc"] if progress <= a.get("until", 1.0)),
                     style["arc"][-1])
        pool = stage.get("camera") or [stage.get("scale", "")]
    else:
        pool = style["camera_high"] if rel_energy >= 0.5 else style["camera_low"]
    return pool[idx % len(pool)] if pool else ""


def _prompt(idx, local_idx, rel_energy, style, lyric, sec, progress, grammar) -> str:
    """Assemble one shot prompt inside the model's character budget.

    A treatment for a whole music video cannot be a Runway prompt -- gen4.5
    takes 1000 UTF-16 units and a 5s clip cannot "build with the music".
    So the treatment is held here as parts, and each shot gets its own prompt
    built from them in priority order: the specific framing and subject first,
    the global look last, since that is what gets dropped if the budget runs
    out.
    """
    if sec.get("board_prompt"):
        # the storyboard already wrote a complete prompt for this beat of the
        # film; only the global look is optionally layered on
        extra = style.get("look", "") if style.get("board_append_look") else ""
        return _fit([sec["board_prompt"], extra])

    rule = style.get("sections", {}).get(_label(sec), {})

    if any(grammar.values()):
        parts = dict(grammar)
        if not parts["subject"]:
            if rule.get("subjects"):
                parts["subject"] = rule["subjects"][min(local_idx, len(rule["subjects"]) - 1)]
            elif style.get("use_lyrics") and lyric:
                parts["subject"] = lyric.split(" / ")[0]
        return _fit([parts[f] for f in GRAMMAR]
                    + [style.get("cast", ""), style.get("world", ""),
                       style.get("look", "")])

    camera = _camera(idx, local_idx, rel_energy, style, rule, progress)

    if rule.get("subjects"):
        subject = rule["subjects"][min(local_idx, len(rule["subjects"]) - 1)]
    elif style.get("use_lyrics") and lyric:
        subject = lyric.split(" / ")[0]
    elif style.get("arc"):
        subject = ""      # the arc line already describes the shot fully
    else:
        subjects = style.get("subjects") or [style.get("subject", "")]
        subject = subjects[idx % len(subjects)] if subjects else ""

    ordered = [camera, subject, style.get("cast", ""), style.get("world", ""),
               style.get("look", "")]
    return _fit(ordered)


def _fit(parts) -> str:
    """Join parts, dropping from the tail if the budget would be blown."""
    kept = []
    for part in parts:
        part = (part or "").strip().rstrip(",")
        if not part:
            continue
        candidate = ", ".join(kept + [part])
        if _units(candidate) > PROMPT_BUDGET:
            break
        kept.append(part)
    return ", ".join(kept)


def _units(text: str) -> int:
    """gen4.5 measures its 1000-character limit in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def run(analysis_path: Path, style_path: Path, lyrics_path: Path | None = None,
        board_path: Path | None = None) -> Path:
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    style = json.loads(style_path.read_text(encoding="utf-8"))
    lyr = None
    if lyrics_path and lyrics_path.exists():
        lyr = json.loads(lyrics_path.read_text(encoding="utf-8"))
        analysis["sections"] = sections_from_lyrics(analysis, lyr)
    if board_path and board_path.exists():
        if lyr is None:
            raise SystemExit("a storyboard needs the lyric alignment first: run `lyrics`")
        from musicvideo import board as board_mod
        rows = board_mod.anchor(board_mod.load(board_path), lyr, analysis["duration_s"])
        analysis["sections"] = sections_from_board(analysis, rows)
    plan = build(analysis, style)

    settings.SHOTLIST_DIR.mkdir(parents=True, exist_ok=True)
    stem = analysis_path.stem
    out = settings.SHOTLIST_DIR / f"{stem}.json"
    out.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    with open(settings.SHOTLIST_DIR / f"{stem}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(plan["shots"])
    return out
