"""Stage 3 -- one Runway text-to-video call per planned shot.

The shot list is updated in place so a failed or interrupted run can be
resumed: shots already marked done are skipped.
"""
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import settings

# only these accept negativePrompt (from the SDK typed params); on anything
# else the exclusions have to live in the positive prompt, which is weaker
NEGATIVE_PROMPT_MODELS = {"veo3.1", "veo3.1_fast"}
# gen4.5 caps promptText at 1000 UTF-16 code units
PROMPT_BUDGET = 1000


def _units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


RUN_COLUMNS = [
    "run_utc", "song", "shot", "status", "elapsed_s",
    "model", "gen_duration_s", "task_id", "clip_path", "error", "prompt",
]


def run(shotlist_path: Path, limit: int | None = None, dry_run: bool = False,
        force: bool = False) -> Path:
    from musicvideo import approve

    plan = json.loads(shotlist_path.read_text(encoding="utf-8"))
    song = shotlist_path.stem
    todo = [s for s in plan["shots"] if s["status"] != "done"]

    # the approval gate: this is the only stage that spends money
    sheet = approve.read(song)
    if sheet is None and not force:
        raise SystemExit("\n".join([
            "nothing approved yet. Run:",
            f'    python -m musicvideo.cli approve "{song}"',
            "then review the sheet, then generate (--force skips the gate).",
        ]))
    if sheet is not None:
        held = [s for s in todo if not approve.is_approved(sheet.get(s["shot"], {}))]
        todo = [s for s in todo if approve.is_approved(sheet.get(s["shot"], {}))]
        for s in todo:                       # the sheet's prompt is the one sent
            edited = (sheet.get(s["shot"], {}).get("prompt") or "").strip()
            if edited and edited != s["prompt"]:
                s["prompt"] = edited
                s["prompt_edited"] = True
        if held:
            print(f"  {len(held)} shot(s) not approved, skipping: "
                  f"{[s['shot'] for s in held][:12]}")

    if limit:
        todo = todo[:limit]
    if not todo:
        raise SystemExit("no approved shots left to generate.")

    # refuse the batch rather than discover a rejection halfway through
    oversize = [s for s in todo if _units(s["prompt"]) > PROMPT_BUDGET]
    if oversize:
        raise SystemExit(
            f"{len(oversize)} prompt(s) exceed the {PROMPT_BUDGET}-unit limit, "
            f"worst is shot {max(oversize, key=lambda s: _units(s['prompt']))['shot']} "
            f"at {max(_units(s['prompt']) for s in oversize)}. Shorten the treatment.")

    negative = plan.get("negative", "")
    if negative and plan["model"] not in NEGATIVE_PROMPT_MODELS:
        print(f"  note: {plan['model']} has no negativePrompt; ignoring "
              f"\"{negative[:50]}...\". Use veo3.1 to enforce exclusions.")
        negative = ""

    print(f"{len(todo)} shot(s) to generate | model={plan['model']} "
          f"| {sum(s['gen_duration_s'] for s in todo)}s of video to buy")
    if dry_run:
        for s in todo:
            print(f"  shot {s['shot']:>3}  {s['gen_duration_s']}s  {s['prompt'][:80]}")
        return shotlist_path

    from musicvideo.client import get_client
    client = get_client()
    clip_dir = settings.CLIP_DIR / song
    clip_dir.mkdir(parents=True, exist_ok=True)

    for s in todo:
        started = time.time()
        rec = {
            "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "song": song, "shot": s["shot"], "model": plan["model"],
            "gen_duration_s": s["gen_duration_s"], "prompt": s["prompt"],
            "task_id": "", "clip_path": "", "error": "", "status": "failed",
        }
        try:
            params = {
                "model": plan["model"],
                "prompt_text": s["prompt"],
                "ratio": plan["ratio"],
                "duration": s["gen_duration_s"],
            }
            if negative:
                params["negative_prompt"] = negative
            task = client.text_to_video.create(**params)
            rec["task_id"] = getattr(task, "id", "")
            result = task.wait_for_task_output()
            outputs = getattr(result, "output", None) or []
            if not outputs:
                raise RuntimeError(f"task returned no output (status={getattr(result,'status','?')})")

            dest = clip_dir / f"shot_{s['shot']:03d}.mp4"
            _download(outputs[0], dest)
            rec["clip_path"] = str(dest)
            rec["status"] = "done"
            s["clip_path"] = str(dest)
            s["status"] = "done"
        except Exception as exc:  # noqa: BLE001 - one bad shot must not kill the batch
            rec["error"] = f"{type(exc).__name__}: {exc}"
            s["status"] = "failed"

        rec["elapsed_s"] = round(time.time() - started, 1)
        _log(rec)
        # persist after every shot so an interrupt loses at most one generation
        shotlist_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(f"  shot {s['shot']:>3}  {rec['status']:<6} {rec['elapsed_s']:>5}s  "
              f"{rec['clip_path'] or rec['error']}")

    done = sum(1 for s in plan["shots"] if s["status"] == "done")
    print(f"\n{done}/{len(plan['shots'])} shots ready")
    return shotlist_path


def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)


def _log(rec: dict) -> None:
    settings.RUNS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not settings.RUNS_CSV.exists()
    with open(settings.RUNS_CSV, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=RUN_COLUMNS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(rec)
