"""Test 2b -- the face test I should have run. New framing, face visible."""
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

OUT = PANELS
log = json.loads((OUT / "runlog.json").read_text(encoding="utf-8"))
url_a = next(r["url"] for r in log if r["name"] == "A_man")

LOOK = ("cinematic realism, poetic documentary photography, natural skin texture, "
        "atmospheric dust, heat haze, dramatic natural light, restrained earth tones, "
        "shallow depth of field, subtle film grain")

c = get_client()
# Deliberately different: low angle, face up, different light, different emotion.
task = c.text_to_image.create(
    model="gen4_image", ratio="1280:720", seed=99001,
    prompt_text=("Low angle close-up of @man on his knees on cracked desert ground, "
                 "head tilted back, eyes shut, mouth open shouting upward, "
                 "harsh overhead noon sun, " + LOOK),
    reference_images=[{"uri": url_a, "tag": "man"}])
res = task.wait_for_task_output()
url = (getattr(res, "output", None) or [None])[0]
dest = OUT / "D_face.png"
dest.write_bytes(requests.get(url, timeout=300).content)
print(f"OK -> {dest}  {dest.stat().st_size//1024}KB")
print("balance:", c.organization.retrieve().credit_balance)
