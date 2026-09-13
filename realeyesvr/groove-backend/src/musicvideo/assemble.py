"""Stage 4 -- cut the clips to their exact bar-length slots and mux the song back on.

Two modes:
  animatic : coloured slates instead of real clips. Costs nothing, and it is
             the honest way to test whether the cut timing works against the
             music *before* buying any generations.
  final    : the generated Runway clips.
"""
import colorsys
import json
import subprocess
import tempfile
from pathlib import Path

from config import settings


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _slot_frames(shot: dict) -> int:
    """Length of a shot in whole frames, measured from its absolute cut points.

    Rounding each duration on its own lets the errors random-walk, so the last
    cut of a long song drifts off the beat. Rounding the boundaries instead
    makes the lengths telescope: every cut sits on the frame nearest its true
    downbeat, and the total is exact by construction.
    """
    return (round(shot["end_s"] * settings.FPS)
            - round(shot["start_s"] * settings.FPS))


def _hue(shot: dict) -> str:
    """Hue steps every shot so every cut is visible; brightness steps every
    section so section changes read too."""
    h = (shot["shot"] * 0.16) % 1.0
    v = 0.45 + 0.25 * (shot["section"] % 2)
    r, g, b = colorsys.hsv_to_rgb(h, 0.6, v)
    return "0x%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))


def _slate(shot: dict, dur: float, dest: Path) -> None:
    size = f"{settings.WIDTH}x{settings.HEIGHT}"
    src = f"color=c={_hue(shot)}:s={size}:d={dur}:r={settings.FPS}"
    base = ["ffmpeg", "-y", "-f", "lavfi", "-i", src]
    tail = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(dest)]

    font = settings.FONT_FILE.replace(":", r"\:")
    label = _clean(f"{shot.get('label', 'shot')}   "
                   f"shot {shot['shot']}  {shot['bars']} bars  {dur:.2f}s")
    # the words sung over this shot, so alignment can be checked by ear
    body = _clean(shot.get("lyric") or shot["prompt"])[:70]
    draw = (
        f"drawtext=fontfile='{font}':text='{label}':fontcolor=white:fontsize=42:"
        f"x=(w-text_w)/2:y=h/2-70,"
        f"drawtext=fontfile='{font}':text='{body}':fontcolor=white:fontsize=40:"
        f"x=(w-text_w)/2:y=h/2+20"
    )
    if _run(base + ["-vf", draw] + tail).returncode == 0:
        return
    _run(base + tail)  # font missing -> plain colour block


def _clean(text: str) -> str:
    """drawtext chokes on quotes and colons, so reduce to a safe subset.
    Apostrophes are dropped rather than spaced, to keep words readable."""
    text = text.replace("'", "").replace("’", "")
    keep = "".join(c if (c.isalnum() or c in " .-") else " " for c in text)
    return " ".join(keep.split())


def _probe_duration(path: str) -> float | None:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", path])
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return None


def _segment(shot: dict, dur: float, dest: Path) -> tuple[bool, float, bool]:
    """Render one clip into its exact slot. Returns (ok, retime_factor, flipped)."""
    clip = shot.get("clip_path")
    if not clip or not Path(clip).exists():
        return False, 1.0, False

    # Screen direction is the one continuity property that can be fixed
    # exactly rather than prompted for: measure which way the clip actually
    # moves and mirror it if it contradicts the board.
    flipped = False
    if settings.ENFORCE_DIRECTION and shot.get("direction"):
        from musicvideo.direction import needs_flip
        flipped, _ = needs_flip(clip, shot["direction"])

    geom = ("hflip," if flipped else "") + (
        f"scale={settings.WIDTH}:{settings.HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={settings.WIDTH}:{settings.HEIGHT}")

    factor = 1.0
    if settings.FIT_MODE == "retime":
        src = _probe_duration(clip)
        if src and src > 0.05:
            cap = settings.HOLD_MAX_RETIME if shot.get("hold") else settings.MAX_RETIME
            f = dur / src
            if 1 / cap <= f <= cap:
                factor = f

    if factor != 1.0:
        # setpts rescales the whole shot into the slot, so nothing is discarded
        # and the motion lands with the bar. fps after setpts resamples cleanly.
        vf = f"{geom},setpts={factor:.6f}*PTS,fps={settings.FPS}"
    else:
        vf = f"{geom},fps={settings.FPS},tpad=stop_mode=clone:stop_duration=3"

    cmd = ["ffmpeg", "-y", "-i", clip, "-vf", vf, "-t", f"{dur}",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(dest)]
    return _run(cmd).returncode == 0, factor, flipped


def run(shotlist_path: Path, audio_path: Path, animatic: bool = False) -> Path:
    plan = json.loads(shotlist_path.read_text(encoding="utf-8"))
    song = shotlist_path.stem
    settings.RENDER_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts, missing, factors, flips = [], [], [], []
        for shot in plan["shots"]:
            frames = _slot_frames(shot)
            if frames <= 0:
                continue
            dur = round(frames / settings.FPS, 6)
            dest = tmp / f"seg_{shot['shot']:03d}.mp4"
            if animatic:
                _slate(shot, dur, dest)
            else:
                ok, factor, flipped = _segment(shot, dur, dest)
                if ok:
                    factors.append(factor)
                    if flipped:
                        flips.append(shot["shot"])
                else:
                    missing.append(shot["shot"])
                    _slate(shot, dur, dest)  # stand in so timing stays intact
            parts.append(dest)

        if not parts:
            raise RuntimeError("no segments to assemble")

        listing = tmp / "concat.txt"
        listing.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8"
        )
        silent = tmp / "silent.mp4"
        cat = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", str(silent)])
        if cat.returncode != 0:
            raise RuntimeError(f"concat failed:\n{cat.stderr[-2000:]}")

        suffix = "animatic" if animatic else "final"
        out = settings.RENDER_DIR / f"{song}_{suffix}.mp4"
        mux = _run(["ffmpeg", "-y", "-i", str(silent), "-i", str(audio_path),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)])
        if mux.returncode != 0:
            raise RuntimeError(f"mux failed:\n{mux.stderr[-2000:]}")

    if factors:
        off = [f for f in factors if f != 1.0]
        print(f"  fit={settings.FIT_MODE}  retimed {len(off)}/{len(factors)} clips"
              + (f"  (x{min(off):.3f}-x{max(off):.3f})" if off else ""))
    if flips:
        print(f"  mirrored {len(flips)} clip(s) to hold screen direction: {flips[:12]}")
    if missing:
        print(f"  {len(missing)} shot(s) had no clip, slated instead: {missing}")
    print(f"  {len(parts)} segments -> {out}")
    return out
