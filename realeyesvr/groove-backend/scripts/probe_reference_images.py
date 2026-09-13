"""Test 2 -- does the reference-image + tag mechanism hold a character?

Three calls:
  A  character plate, no refs        -> the man
  B  location plate, no refs         -> the desert
  C  composed, refs A+B with tags    -> does @man survive into a new framing?
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

OUT = PANELS
OUT.mkdir(parents=True, exist_ok=True)

LOOK = ("cinematic realism, poetic documentary photography, natural skin texture, "
        "atmospheric dust, heat haze, dramatic natural light, restrained earth tones, "
        "shallow depth of field, subtle film grain")

c = get_client()
SEED = 20260826
log = []


def go(name, prompt, refs=None, seed=SEED):
    params = dict(model="gen4_image", prompt_text=prompt, ratio="1280:720", seed=seed)
    if refs:
        params["reference_images"] = refs
    t0 = time.time()
    print(f"\n[{name}] {len(prompt)} chars, {len(refs or [])} ref(s)")
    task = c.text_to_image.create(**params)
    res = task.wait_for_task_output()
    url = (getattr(res, "output", None) or [None])[0]
    dt = round(time.time() - t0, 1)
    if not url:
        print(f"  FAILED status={getattr(res,'status','?')}")
        return None
    dest = OUT / f"{name}.png"
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        dest.write_bytes(r.content)
    kb = dest.stat().st_size // 1024
    print(f"  OK {dt}s  {kb}KB  -> {dest.name}")
    log.append({"name": name, "task_id": getattr(task, "id", ""), "seed": seed,
                "elapsed_s": dt, "url": url, "path": str(dest), "prompt": prompt})
    return url


# A -- the character. Specific, repeatable features so drift is measurable.
url_a = go("A_man", (
    "Medium close-up portrait of a man in his thirties, weathered sunburnt face, "
    "short black hair, three-day stubble, a small scar through his left eyebrow, "
    "dust caked in the creases of his skin, cracked lips, dark brown eyes squinting "
    "against hard sunlight, faded blue collared work shirt, " + LOOK))

# B -- the location.
url_b = go("B_desert", (
    "Extreme wide landscape of the Sonoran Desert, sun-bleached cracked earth, "
    "distant rocky mountains, a dry wash cutting through, towering saguaros, "
    "empty and vast, no people, " + LOOK))

# C -- composed against both, referenced by tag.
if url_a and url_b:
    go("C_composed", (
        "@man walks away from camera into @desert, seen from behind in an extreme "
        "wide shot, tiny against the landscape, heat haze rising, " + LOOK),
        refs=[{"uri": url_a, "tag": "man"}, {"uri": url_b, "tag": "desert"}])

(OUT / "runlog.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
print(f"\n{len(log)} image(s) -> {OUT}")

bal = c.organization.retrieve().credit_balance
print(f"credit balance now: {bal}  (was 500)")
