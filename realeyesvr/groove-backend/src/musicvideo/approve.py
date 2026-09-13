"""The approval gate.

Generation is the only stage that costs money and the only one that cannot be
undone, so nothing reaches it unreviewed. `approve` writes the plan out in two
forms -- a page to read and a sheet to edit -- and `generate` refuses to run
any shot the sheet has not signed off.

The sheet is the source of truth, and its prompt column is editable: whatever
is written there is what gets sent.
"""
import csv
import html
import json
from pathlib import Path

from config import settings

# Ordered like a board caption, so the sheet scans the way a shot list reads.
COLUMNS = ["shot", "slate", "approve", "start_s", "end_s", "slot_s",
           "gen_duration_s", "section", "size", "movement", "direction",
           "lens", "pov", "from_board", "lyric", "action", "prompt"]


def sheet_path(song: str) -> Path:
    return settings.SHOTLIST_DIR / f"{song}.approval.csv"


def write(shotlist_path: Path) -> tuple[Path, Path]:
    """Write the review sheet and the review page. Existing decisions survive."""
    plan = json.loads(shotlist_path.read_text(encoding="utf-8"))
    song = shotlist_path.stem
    sheet = sheet_path(song)

    prior = {}
    if sheet.exists():
        with open(sheet, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                prior[int(row["shot"])] = row

    rows = []
    for shot in plan["shots"]:
        was = prior.get(shot["shot"], {})
        rows.append({
            "shot": shot["shot"],
            "approve": was.get("approve", "yes"),
            "start_s": shot["start_s"], "end_s": shot["end_s"],
            "slot_s": shot["slot_s"], "gen_duration_s": shot["gen_duration_s"],
            "slate": shot.get("slate", ""),
            "section": shot["label"],
            "size": shot.get("size", ""), "movement": shot.get("movement", ""),
            "direction": shot.get("direction", ""), "lens": shot.get("lens", ""),
            "pov": shot.get("pov", ""),
            "from_board": "yes" if shot.get("from_board") else "no",
            "lyric": shot.get("lyric", ""), "action": shot.get("action", ""),
            # a prompt already edited in the sheet wins over the planner's
            "prompt": was.get("prompt") or shot["prompt"],
        })

    sheet.parent.mkdir(parents=True, exist_ok=True)
    with open(sheet, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    page = _page(song, plan, rows)
    return sheet, page


def read(song: str) -> dict[int, dict] | None:
    """Approved shots by index, or None when the gate has never been run."""
    sheet = sheet_path(song)
    if not sheet.exists():
        return None
    out = {}
    with open(sheet, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            out[int(row["shot"])] = row
    return out


def is_approved(row: dict) -> bool:
    return (row.get("approve") or "").strip().lower() in ("yes", "y", "true", "1", "x")


def _page(song: str, plan: dict, rows: list[dict]) -> Path:
    ok = [r for r in rows if is_approved(r)]
    secs = "".join(_row_html(r) for r in rows)
    out = Path("output/boards") / f"{song}.review.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"""<!doctype html><meta charset="utf-8">
<title>{html.escape(song)} — shot review</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;background:#14110e;color:#e8e2d9;margin:0;padding:28px}}
 h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#a09585;margin-bottom:22px}}
 table{{border-collapse:collapse;width:100%}}
 td,th{{padding:9px 11px;border-bottom:1px solid #2c2620;vertical-align:top;text-align:left}}
 th{{color:#a09585;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
 .t{{white-space:nowrap;color:#c9a227;font-variant-numeric:tabular-nums}}
 .sec{{white-space:nowrap;color:#d98g55}} .no{{opacity:.35}}
 .lyric{{color:#b9ad9c;font-style:italic}} .p{{color:#e8e2d9}}
 .b{{display:inline-block;padding:1px 6px;border-radius:3px;background:#3a2f22;color:#d9b877;font-size:11px}}
</style>
<h1>{html.escape(song)} — shot review</h1>
<div class="sub">{len(rows)} shots &middot; {len(ok)} approved &middot;
{sum(int(r['gen_duration_s']) for r in ok)}s of video to buy &middot;
model {html.escape(plan.get('model',''))}</div>
<table><tr><th>#</th><th>time</th><th>section</th><th>lyric / action</th><th>prompt</th></tr>
{secs}</table>""", encoding="utf-8")
    return out


def _row_html(r: dict) -> str:
    cls = "" if is_approved(r) else ' class="no"'
    badge = ' <span class="b">board</span>' if r["from_board"] == "yes" else ""
    note = html.escape(r["lyric"] or r["action"] or "")
    # the board-caption line: size · movement · direction
    grammar = " · ".join(x for x in (r.get("size"), r.get("movement"),
                                     r.get("direction")) if x)
    return (f'<tr{cls}><td><b>{html.escape(r.get("slate") or str(r["shot"]))}</b><br><span style="color:#7d7264">{r["shot"]}</span></td>'
            f'<td class="t">{float(r["start_s"]):.1f}–{float(r["end_s"]):.1f}s'
            f'<br><span style="color:#7d7264">{r["gen_duration_s"]}s buy</span></td>'
            f'<td class="sec">{html.escape(r["section"])}{badge}'
            f'<br><span style="color:#8a7f6f;font-size:12px">{html.escape(grammar)}</span></td>'
            f'<td class="lyric">{note}</td>'
            f'<td class="p">{html.escape(r["prompt"])}</td></tr>')
