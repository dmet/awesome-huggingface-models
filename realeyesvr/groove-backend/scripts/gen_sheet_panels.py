"""Two more panels so the board's new structure is real, not notional.

  F_tall   1080:1920 plate for the C-A crane composite (needs real height)
  G_follow second panel of the carried-over V1-A tracking shot
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

P = PANELS

def ref(name, tag):
    b = base64.b64encode((P / (name + ".png")).read_bytes()).decode()
    return {"uri": "data:image/png;base64," + b, "tag": tag}

LOOK = ("cinematic realism, poetic documentary photography, natural skin texture, "
        "atmospheric dust, heat haze, dramatic natural light, restrained earth tones, "
        "shallow depth of field, subtle film grain")

c = get_client()
before = c.organization.retrieve().credit_balance
print("balance before:", before)
log = []


def go(name, prompt, ratio, refs, seed):
    t0 = time.time()
    print("\n[%s] %s  %d ref(s)" % (name, ratio, len(refs)))
    task = c.text_to_image.create(model="gen4_image", prompt_text=prompt,
                                  ratio=ratio, seed=seed, reference_images=refs)
    res = task.wait_for_task_output()
    url = (getattr(res, "output", None) or [None])[0]
    if not url:
        print("  FAILED status=%s" % getattr(res, "status", "?"))
        return
    dest = P / (name + ".png")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        dest.write_bytes(r.content)
    print("  OK %.1fs  %dKB -> %s" % (time.time() - t0, dest.stat().st_size // 1024, dest.name))
    log.append({"name": name, "seed": seed, "ratio": ratio, "url": url,
                "task_id": getattr(task, "id", ""), "prompt": prompt})


# Tall plate: a crane path needs vertical room. Top of frame distant, bottom at the
# ground, so a 16:9 window can travel down it.
go("F_tall",
   ("Vertical composition of @desert seen from high above looking down, "
    "distant rocky mountains and pale sky across the top of frame, the dry wash "
    "receding through the middle, cracked earth filling the bottom of frame in "
    "sharp close detail, continuous unbroken view from horizon to ground, "
    "no people, " + LOOK),
   "1080:1920", [ref("B_desert", "desert")], 31415)

# Second panel of the continuing tracking shot -- same framing logic as C_composed,
# further along the walk.
go("G_follow",
   ("Tracking shot following @man from behind as he walks through @desert, "
    "camera moving with him at his pace, he is further along the dry wash now, "
    "shoulders low, dust kicked up around his boots, mountains closer, "
    "same faded blue work shirt, " + LOOK),
   "1280:720", [ref("A_man", "man"), ref("B_desert", "desert")], 27182)

(P / "runlog2.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
after = c.organization.retrieve().credit_balance
print("\nbalance after: %d   spent: %d credits" % (after, before - after))
