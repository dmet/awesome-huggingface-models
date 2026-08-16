# precon-probe

A functional test, not a product. It answers one question: **can a current VLM
read the equipment schedules in your sets accurately enough to build on?**

Everything runs against an API, so there is no GPU to rent for the first pass.

## Setup

```bash
pip install requests pillow
sudo apt install poppler-utils        # macOS: brew install poppler
export OPENROUTER_API_KEY=sk-...
```

DuckDB is optional and only needed for `query.sql`.

## Run order

```bash
# 1. See the bill before paying it
python render.py set.pdf --pages all --dry-run

# 2. Render only candidate sheets. Long edge capped at 1600px.
python render.py set.pdf --pages 40-52 --max-px 1600 --out pages/

# 3. Extract. Resumable -- rerun after a crash and it skips finished pages.
python extract.py pages/ --out facts.jsonl --project riverside --rev 2

# 4. Score against schedules you keyed by hand
python score.py facts.jsonl truth.jsonl --by-field

# 5. Query the log
duckdb -c ".read query.sql"
```

## The cost lever

Image tokens dominate. Qwen-VL tokenizes at a 28x28 effective patch, so a page
costs roughly `(width * height) / 784` tokens. Halving the long edge quarters
the bill:

| long edge | tokens/page | 400 sheets @ $0.45/M |
|---|---|---|
| 3200 px | ~13,000 | ~$2.34 |
| 1600 px | ~3,300  | ~$0.59 |
| 1100 px | ~1,500  | ~$0.28 |

Find the smallest size where `score.py` still passes. That number is worth more
than any model choice, and it is why sending whole sheet sets at full
resolution is the wrong instinct even when the context window allows it.

Two more levers: use Instruct rather than Thinking variants (reasoning tokens
bill at the output rate, and schedule reading is not a reasoning task), and
render once per revision rather than per query. Vision runs at ingest; every
question afterward is cheap text over `facts.jsonl`.

## Keying truth

Twenty to thirty rows is enough to be decisive. Copy real values from the sheets
by hand into `truth.jsonl`, one row per line:

```json
{"type":"equipment_schedule_row","tag":"AHU-1","attrs":{"CFM":"6000","TONS":"15"},"source":{"sheet":"M-501"}}
```

`score.py` normalizes commas, case, and whitespace before comparing, so you do
not have to match the model's typography, only its meaning.

## What the log gives you

Every record is one line, append-only, and carries its own provenance and
schema version. That shape buys three things at once:

- **Resumability.** A crash on sheet 300 costs the last page, not the run.
- **Supersession.** New revisions append rather than overwrite, so "what changed
  since we last priced this" is a query (`query.sql` #3), not a diff exercise.
- **Auditability.** Every fact points back to sheet, revision, and page, which
  is the minimum bar for anything a bid decision touches.

## Suggested first experiment

Run the same 20 sheets through three models and compare `score.py` output:

- `qwen/qwen3-vl-8b-instruct` — cheap, likely sufficient for clean printed schedules
- `qwen/qwen3-vl-32b-instruct` — a real step up in reading effort, not just size
- one closed model as a ceiling

Check OpenRouter's live model list before picking an ID -- `qwen/qwen3-vl-8b`
and `qwen/qwen3.8-27b` both look plausible but don't exist; the working IDs
carry an explicit `-instruct` (or `-thinking`) suffix.

If the 8B scores within a point or two of the 32B on your sheets, that decides
your architecture and your budget in an afternoon. Public benchmarks cannot
answer this because they do not test your documents.

## Row-batched extraction (`--batch`)

A single flat call works for a small, isolated table (a cropped door schedule
of ~20 rows). It does not work for a real full sheet: a table with hundreds of
rows cannot fit in one completion, at any resolution, for either model tried
here. `qwen/qwen3-vl-8b-instruct` just returns zero rows on a busy sheet
(server-side image resizing caps effective resolution well below what
`render.py`'s own `--max-px` implies, so more pixels doesn't help once you're
past ~2000px effective width). `qwen/qwen3-vl-32b-instruct` tries harder and
gets further, but a ~150-row table needs more JSON than any completion budget
allows -- OpenRouter's hard ceiling for this model is 32,768 completion
tokens, not something `--max-tokens` can raise, and the response cuts off
mid-object.

`row_batch.py` (ported from `hf-spaces/realeyesvr-test-lab/row_segmentation.py`,
minus the PaddleOCR reviewer that pipeline uses to get a row-count estimate --
staying API-only here) detects row bands in an already-cropped table image and
groups them into small stacked batches, so each call only has to return a
handful of records:

```bash
python extract.py pages/ --out facts.jsonl --batch --batch-size 4 \
  --header-fraction 0.06 --footer-fraction 0.02 --model qwen/qwen3-vl-8b-instruct
```

`--header-fraction` / `--footer-fraction` trim the title/header strip and any
trailing whitespace before row detection runs; get this wrong and either the
header text itself gets counted as a data row, or the last batch runs past the
real end of the table into blank space. Three things had to be true at once
to get this working cleanly, each one a real bug hit while building it, not a
hypothetical:

- **The model needs the header row in view.** Row-band images alone carry no
  column names; without them the model either invents keys or echoes each
  cell's own value back as its key. `extract_batched` crops the header once
  and prepends it to every batch.
- **The header crop must be scaled to match the row crops.** Row bands get
  enlarged 2x width in `_crops_from_bounds`; a header pasted in at native
  scale sits in half the frame at a different visual scale than the data
  below it, and the model responds by returning nothing rather than guessing.
- **The model can silently drop the required `{"tag": ..., "attrs": {...}}`
  envelope** under the batch-specific prompt, flattening every column to a
  top-level key instead. Code that does `row.get("attrs", {})` then discards
  real data with no error -- `normalize_row()` in `extract.py` salvages a
  flat response into `attrs` rather than trusting the envelope blindly.

## Redacting a real sheet for testing

`CONCEPT.md`'s own rule is public, synthetic, personally owned, or explicitly
authorized documents only. To use a real client sheet as a test fixture:
drop the source into `sheets/raw/` (gitignored -- never committable, even by
`git add -A`), render and inspect it, black out every client-identifying
region (title block, firm branding, registration/seal, project info, any
file-path breadcrumbs), save only the redacted image under `sheets/`, then
delete `sheets/raw/`. `sheets/redact.py` and `sheets/table_crop.png` /
`sheets/full_sheet.png` are the record of that process for this repo's sample
sheet -- re-verify redaction by eye for any new source, box coordinates don't
transfer between documents.

## Scope

Schedules and title blocks only. Symbol recognition, plan-to-detail callouts,
and anything scale-dependent are deliberately out, those are the hard problems
and they are not on the path to a first useful output.
