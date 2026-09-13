"""Measure which way a clip actually moves, so screen direction can be enforced.

Screen direction is a statement about the image plane, and a text prompt is a
poor way to control it -- models mirror. It is, however, the one continuity
property that can be fixed exactly after the fact: a horizontal flip costs
nothing and is always right.

So rather than trusting the prompt, measure the clip and flip it if it
disagrees with the plan.
"""
import subprocess

import numpy as np

W, H = 128, 72         # small, but not so small that a slow drift vanishes
FPS = 6                # enough to track a pan, cheap to decode
STRIDE = 3             # compare frames half a second apart, so slow motion
                       # accumulates past the one-pixel search floor
MAX_SHIFT = 16         # px at this width
DEADZONE = 0.10        # below this the clip counts as having no direction
MIN_CORR = 0.50        # the matched profiles must actually correlate this well.
                       # Measured on fixtures: a real pan scores 0.94-1.00,
                       # incoherent texture 0.10. A z-score against the other
                       # candidates does NOT separate these (1.9 vs 3.0) --
                       # absolute correlation does.

HORIZONTAL = {"left to right": 1, "right to left": -1}


def _frames(path: str) -> np.ndarray:
    """Decode the clip as a small grayscale stack."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path),
           "-vf", f"fps={FPS},scale={W}:{H}", "-f", "rawvideo",
           "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (W * H)
    if n < 2:
        return np.empty((0, H, W))
    return np.frombuffer(raw[: n * W * H], np.uint8).reshape(n, H, W).astype(np.float32)


def measure(path: str) -> float:
    """Mean horizontal shift per frame, in pixels at the reduced width.

    Positive means image content travels rightward across the frame -- what a
    board would call left-to-right screen direction.
    """
    frames = _frames(path)
    if len(frames) < 2:
        return 0.0

    # collapse each frame to a column profile; dominant horizontal motion
    # survives that, and it makes the correlation a 1-D search
    profiles = frames.mean(axis=1)
    profiles -= profiles.mean(axis=1, keepdims=True)

    shifts = []
    for a, b in zip(profiles, profiles[STRIDE:]):
        scores = np.array([_ncc(a, b, s) for s in range(-MAX_SHIFT, MAX_SHIFT + 1)])
        peak = int(scores.argmax())
        # if nothing matches well at any offset there is no motion to read,
        # only texture, and inventing a direction here would flip a good clip
        if scores[peak] < MIN_CORR:
            continue
        shifts.append((peak - MAX_SHIFT) / STRIDE)

    if not shifts:
        return 0.0
    # sign calibrated against synthetic clips of known travel: the search
    # returns the shift applied to the later frame, the negative of the
    # direction the content actually moved.
    return -float(np.mean(shifts))


def _ncc(a: np.ndarray, b: np.ndarray, s: int) -> float:
    """Normalised correlation of two profiles at horizontal offset `s`."""
    if s > 0:
        x, y = a[s:], b[: len(b) - s]
    elif s < 0:
        x, y = a[:s], b[-s:]
    else:
        x, y = a, b
    if len(x) < 8:
        return -1.0
    nx, ny = np.linalg.norm(x), np.linalg.norm(y)
    return float(np.dot(x, y) / (nx * ny)) if nx and ny else -1.0


def label(shift: float) -> str:
    """Turn a measurement into board vocabulary."""
    if abs(shift) < DEADZONE:
        return ""
    return "left to right" if shift > 0 else "right to left"


def needs_flip(path: str, wanted: str) -> tuple[bool, float]:
    """Should this clip be mirrored to match the planned direction?"""
    if wanted not in HORIZONTAL:
        return False, 0.0        # toward/away from camera survives a flip
    shift = measure(path)
    got = label(shift)
    return bool(got and got != wanted), shift
