"""Test 3 -- THE decisive one. Does aleph2 honor float keyframe timestamps?

Source: 7.083s panel slideshow, cuts on real downbeats at 1.781 / 3.552 / 5.301.
Keyframes: 0.0 (at a cut), 2.667 (MID-shot, inside the desert wide), 5.301 (at a cut).
If content shifts at 2.667s, arbitrary float placement is real.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "output" / "build"
PANELS = ROOT / "output" / "panels" / "test"
BUILD.mkdir(parents=True, exist_ok=True)
PANELS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import requests
from musicvideo.client import get_client

S = BUILD
P = PANELS
OUT = PANELS

c = get_client()
before = c.organization.retrieve().credit_balance
print(f"balance before: {before}")

src_b64 = "data:video/mp4;base64," + base64.b64encode((S / "src_beat.mp4").read_bytes()).decode()
print(f"source data URI: {len(src_b64)/1048576:.2f} MB (cap 16MB)")

log = json.loads((P / "runlog.json").read_text(encoding="utf-8"))
by = {r["name"]: r["url"] for r in log}

kf = [
    {"seconds": 0.0,   "uri": by["A_man"]},
    {"seconds": 2.667, "uri": by["B_desert"]},   # mid-shot placement -- the test
    {"seconds": 5.301, "uri": by["C_composed"]},
]
print("keyframes:", [k["seconds"] for k in kf])

params = dict(
    model="aleph2",
    video_uri=src_b64,
    keyframes=kf,
    prompt_text=("Cinematic live-action desert footage, natural camera movement, "
                 "drifting dust and heat haze, subtle film grain, photographic realism"),
    seed=4242,
)

t0 = time.time()
try:
    task = c.video_to_video.create(**params)
    print(f"task accepted: {getattr(task,'id','?')}")
    res = task.wait_for_task_output(timeout=900)
    url = (getattr(res, "output", None) or [None])[0]
    dt = round(time.time() - t0, 1)
    if not url:
        print(f"NO OUTPUT status={getattr(res,'status','?')} detail={res}")
    else:
        dest = OUT / "E_aleph2.mp4"
        with requests.get(url, stream=True, timeout=900) as r:
            r.raise_for_status()
            dest.write_bytes(r.content)
        print(f"OK {dt}s  {dest.stat().st_size//1024}KB -> {dest}")
except Exception as e:
    print(f"FAILED after {round(time.time()-t0,1)}s -- {type(e).__name__}: {e}")

after = c.organization.retrieve().credit_balance
print(f"balance after: {after}   spent: {before - after} credits")
