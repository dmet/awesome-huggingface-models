#!/usr/bin/env python3
"""One-off redaction record for a full-sheet door schedule test image.

Boxes were hand-located by visually inspecting crops of the rendered page.
The unredacted source has been deleted -- this script is a record of what
was covered and why, not something meant to be re-run; re-verify by eye
against the new source if a similar sheet needs redacting again.
"""
import sys
sys.path.insert(0, "/workspaces/awesome-huggingface-models/.venv/lib/python3.12/site-packages")
from PIL import Image, ImageDraw

SRC = "raw/render/page-1.png"  # deleted after use -- kept here for reference only
OUT = "full_sheet.png"

# (x0, y0, x1, y1) in the full 6300x4500 render, each with a small safety margin
BOXES = [
    (5660, 130, 6300, 1510),   # firm wordmark + address + website
    (5660, 2560, 6300, 3090),  # registration block: name, license no., signature, seal
    (5660, 3620, 6300, 3850),  # project info: phase/date/no./PIC-AIC + project name
    (5660, 4390, 6300, 4430),  # copyright line (names the firm)
    (10, 3470, 160, 4480),     # rotated file-path breadcrumb, left margin
]

im = Image.open(SRC).convert("RGB")
draw = ImageDraw.Draw(im)
for box in BOXES:
    draw.rectangle(box, fill="black")
im.save(OUT)
print(f"wrote {OUT}, size={im.size}")
