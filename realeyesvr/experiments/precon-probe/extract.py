#!/usr/bin/env python3
"""Send rendered pages to a VLM and append fact records to a JSONL log.

Design rules this enforces:
  - append-only: one JSON object per line, never rewritten
  - resumable: pages already in the log are skipped, so a crash costs nothing
  - provenance: every fact carries sheet, rev, page, and the extractor version
  - typed: every line has `type` and `schema_version` so a single pass can route

  export OPENROUTER_API_KEY=sk-...
  python extract.py pages/ --out facts.jsonl --rev 2 --model qwen/qwen3-vl-8b-instruct
"""
import argparse
import base64
import datetime
import json
import os
import pathlib
import re
import sys

import requests
from PIL import Image

import row_batch

SCHEMA_VERSION = 1
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

PROMPT = """You are reading one sheet from a construction drawing set.

Return ONLY a JSON object, no prose and no markdown fences:

{
  "sheet": "<sheet number from the title block, e.g. M-501, or null>",
  "sheet_title": "<title block name, or null>",
  "has_equipment_schedule": true|false,
  "rows": [
    {"tag": "AHU-1", "attrs": {"<column header>": "<cell value>"}}
  ]
}

Rules:
- One entry in "rows" per scheduled equipment row. Empty list if none.
- Use the column headers exactly as printed on the sheet as attrs keys.
- If the table has grouped column headers (e.g. a "Door" section and a
  "Frame" section) whose sub-columns repeat a name (both sections have a
  "Material" column, or both have a "Type" column), prefix the attrs key
  with its group so keys stay unique: "Door Material" and "Frame Material",
  "Door Type" and "Frame Type". Never let one column's value silently
  overwrite another's because they share a header name.
- The sheet identifier (e.g. "A2.1") is usually printed in a title block or
  corner box, not inside the schedule table itself. Find it and put it in
  "sheet" even when it is not one of the table's rows or columns.
- Copy values verbatim. Never infer, never fill blanks, never round.
- If a cell is empty or illegible, use null.
"""

# header_note is filled in by extract_batched() depending on whether a
# header band was actually prepended to the stacked image -- claiming "the
# first band is the header" when header_fraction is 0 (no header crop was
# ever built) is what caused the model to discard a real data row as if it
# were a header that was never actually sent.
BATCH_HEADER_NOTE = (
    ' The FIRST band at the top is the table\'s column header row -- use it '
    'to identify real column names for attrs keys, but do not create a row '
    'record for it. Below the header are {n} adjacent data-row bands, '
    'stacked top-to-bottom and separated by thin white gaps.'
)
BATCH_NO_HEADER_NOTE = (
    ' It shows {n} adjacent data-row bands, stacked top-to-bottom and '
    'separated by thin white gaps, with no header row visible -- infer '
    'column meaning from each value\'s shape and units as best you can.'
)

BATCH_INSTRUCTION = """
This image is a small piece of a much larger schedule table, not a full
sheet.{header_note} There is no title block or sheet number visible; leave
"sheet" and "sheet_title" null. Extract exactly one row record per data
band, in top-to-bottom order, using real column names as attrs keys -- never
the row's own cell values. Set "row_band" in each row's attrs to its
1-indexed position among the data bands (1 to {n}). Do not merge two bands
into one record and do not skip a band -- if a band is unreadable, return a
best-effort record for it rather than omitting it. Return exactly {n}
entries in "rows".

Every row object must still use the exact two-key shape from the schema
above: {{"tag": "<the row's own identifying number>", "attrs": {{...}}}}.
Put row_band and every column value inside "attrs" -- never as top-level
keys alongside "tag".
"""


def encode(path):
    return base64.b64encode(path.read_bytes()).decode()


def encode_image(image):
    from io import BytesIO
    buf = BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def done_pages(out):
    """Pages with a successful extraction. Error records don't count as done,
    so a retry after a transient failure actually retries instead of skipping."""
    seen = set()
    if out.exists():
        for line in out.open():
            try:
                record = json.loads(line)
                if record.get("type") == "sheet":
                    seen.add(record["source"]["page"])
            except Exception:
                continue
    return seen


def call(model, img_b64, timeout, max_tokens=None, prompt=PROMPT):
    payload = {"model": model, "temperature": 0,
               "messages": [{"role": "user", "content": [
                   {"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                   {"type": "text", "text": prompt}]}]}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    r = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    return body["choices"][0]["message"]["content"], body.get("usage", {})


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def normalize_row(row):
    """Return (tag, attrs), tolerating a model that drops the nested "attrs"
    envelope and returns column values as top-level keys instead. Salvaging
    the flat fields into attrs beats silently discarding them via .get()
    defaults -- which is what happened before this existed (see README)."""
    if "attrs" in row:
        return (row.get("tag") or ""), row.get("attrs", {})
    return (row.get("tag") or ""), {k: v for k, v in row.items() if k != "tag"}


def extract_batched(img_path, model, timeout, max_tokens, batch_size,
                     header_fraction, footer_fraction):
    """Row-batched extraction for a single already-cropped table image.

    Splits the table into small row-band batches (row_batch.py) so each
    model call only has to return a handful of records -- the fix for the
    full-sheet completion-length wall (a single flat call over a
    hundreds-of-rows table cannot finish within any completion budget,
    regardless of model or max_tokens; see README).

    Returns (rows, warnings, tok_in, tok_out). Falls back to a single flat
    call over the whole image if no row structure could be detected.
    """
    image = Image.open(img_path).convert("RGB")
    detected = row_batch.segment_rows(image, header_fraction=header_fraction,
                                       footer_fraction=footer_fraction)
    if not detected:
        raw, usage = call(model, encode(img_path), timeout, max_tokens)
        data = parse_json(raw)
        return (data.get("rows", []), ["no row structure detected; used one flat call"],
                usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

    width, height = image.size
    header_crop = None
    if header_fraction > 0:
        header_band = image.crop((0, 0, width, round(height * header_fraction)))
        # Match _crops_from_bounds' 2x width scaling so the header renders at
        # the same visual scale as the row crops below it in the stack --
        # otherwise stack_rows sizes the canvas to the wider (enlarged) row
        # crops and pastes the header into just the left half at native size.
        header_band = header_band.resize(
            (header_band.width * 2, header_band.height * 2), Image.Resampling.LANCZOS)
        header_crop = row_batch.RowCrop(0, header_band)

    rows: list[dict] = []
    warnings: list[str] = [f"segmented into {len(detected)} row bands"]
    tok_in = tok_out = 0
    for batch_index, batch in enumerate(row_batch.group_rows(detected, batch_size), start=1):
        expected_bands = [row.row_index for row in batch]
        note = (BATCH_HEADER_NOTE if header_crop is not None else BATCH_NO_HEADER_NOTE) \
            .format(n=len(batch))
        prompt = PROMPT + BATCH_INSTRUCTION.format(n=len(batch), header_note=note)
        try:
            to_stack = ([header_crop] + batch) if header_crop is not None else batch
            stacked = row_batch.stack_rows(to_stack)
            raw, usage = call(model, encode_image(stacked), timeout, max_tokens, prompt)
            data = parse_json(raw)
        except Exception as e:
            warnings.append(f"batch {batch_index} (bands {expected_bands}): {str(e)[:200]}")
            continue
        tok_in += usage.get("prompt_tokens", 0)
        tok_out += usage.get("completion_tokens", 0)
        candidates = data.get("rows", [])
        if len(candidates) != len(batch):
            warnings.append(f"batch {batch_index}: expected {len(batch)} records for "
                             f"bands {expected_bands}, received {len(candidates)}")
        rows.extend(candidates)

    return rows, warnings, tok_in, tok_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pagedir")
    ap.add_argument("--out", default="facts.jsonl")
    ap.add_argument("--model", default="qwen/qwen3-vl-8b-instruct")
    ap.add_argument("--project", default="unnamed")
    ap.add_argument("--rev", type=int, default=0)
    ap.add_argument("--effective", default=datetime.date.today().isoformat())
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--limit", type=int, default=0, help="stop after N pages")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="completion token cap; needed for sheets with many rows")
    ap.add_argument("--batch", action="store_true",
                    help="row-batch a single already-cropped table image instead of "
                         "one flat call -- required for tables too large for one completion")
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--header-fraction", type=float, default=0.0,
                    help="fraction of image height to skip before row detection")
    ap.add_argument("--footer-fraction", type=float, default=0.0,
                    help="fraction of image height to skip after row detection")
    args = ap.parse_args()

    if "OPENROUTER_API_KEY" not in os.environ:
        sys.exit("set OPENROUTER_API_KEY first")

    out = pathlib.Path(args.out)
    skip = done_pages(out)
    imgs = sorted(pathlib.Path(args.pagedir).glob("p*.png"))
    if args.limit:
        imgs = imgs[: args.limit]

    tok_in = tok_out = 0
    with out.open("a") as fh:
        for img in imgs:
            page = int(img.stem[1:])
            if page in skip:
                print(f"page {page}: already in log, skipping")
                continue
            if args.batch:
                try:
                    rows, warnings, b_tok_in, b_tok_out = extract_batched(
                        img, args.model, args.timeout, args.max_tokens, args.batch_size,
                        args.header_fraction, args.footer_fraction)
                except Exception as e:
                    fh.write(json.dumps({
                        "type": "extraction_error", "schema_version": SCHEMA_VERSION,
                        "project": args.project, "error": str(e)[:300],
                        "source": {"page": page, "rev": args.rev},
                        "extractor": args.model,
                    }) + "\n")
                    fh.flush()
                    print(f"page {page}: FAILED {str(e)[:80]}")
                    continue

                tok_in += b_tok_in
                tok_out += b_tok_out
                src = {"sheet": None, "rev": args.rev, "page": page, "image": img.name}
                fh.write(json.dumps({
                    "type": "sheet", "schema_version": SCHEMA_VERSION,
                    "project": args.project, "sheet": None, "title": None,
                    "has_equipment_schedule": len(rows) > 0,
                    "extraction_warnings": warnings,
                    "source": src, "effective": args.effective,
                    "extractor": args.model,
                }) + "\n")
                for row in rows:
                    tag, attrs = normalize_row(row)
                    fh.write(json.dumps({
                        "type": "equipment_schedule_row",
                        "schema_version": SCHEMA_VERSION,
                        "project": args.project,
                        "tag": tag.strip().upper(),
                        "attrs": attrs,
                        "source": src, "effective": args.effective,
                        "extractor": args.model,
                    }) + "\n")
                fh.flush()
                print(f"page {page}: batched, rows={len(rows)}, warnings={len(warnings)}")
                continue

            try:
                raw, usage = call(args.model, encode(img), args.timeout, args.max_tokens)
                data = parse_json(raw)
            except Exception as e:
                # failures are facts too -- they belong in the log
                fh.write(json.dumps({
                    "type": "extraction_error", "schema_version": SCHEMA_VERSION,
                    "project": args.project, "error": str(e)[:300],
                    "source": {"page": page, "rev": args.rev},
                    "extractor": args.model,
                }) + "\n")
                fh.flush()
                print(f"page {page}: FAILED {str(e)[:80]}")
                continue

            tok_in += usage.get("prompt_tokens", 0)
            tok_out += usage.get("completion_tokens", 0)
            src = {"sheet": data.get("sheet"), "rev": args.rev,
                   "page": page, "image": img.name}

            fh.write(json.dumps({
                "type": "sheet", "schema_version": SCHEMA_VERSION,
                "project": args.project, "sheet": data.get("sheet"),
                "title": data.get("sheet_title"),
                "has_equipment_schedule": data.get("has_equipment_schedule", False),
                "source": src, "effective": args.effective,
                "extractor": args.model,
            }) + "\n")

            for row in data.get("rows", []):
                tag, attrs = normalize_row(row)
                fh.write(json.dumps({
                    "type": "equipment_schedule_row",
                    "schema_version": SCHEMA_VERSION,
                    "project": args.project,
                    "tag": tag.strip().upper(),
                    "attrs": attrs,
                    "source": src, "effective": args.effective,
                    "extractor": args.model,
                }) + "\n")
            fh.flush()
            print(f"page {page}: sheet={data.get('sheet')} "
                  f"rows={len(data.get('rows', []))}")

    print(f"\ntokens in={tok_in:,} out={tok_out:,}")


if __name__ == "__main__":
    main()
