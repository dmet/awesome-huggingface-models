#!/usr/bin/env python3
"""Rasterize selected PDF pages to PNG under a pixel budget.

Image tokens dominate VLM cost. Qwen-VL models tokenize at a 28x28 effective
patch, so tokens ~= (w*h)/784. This script caps the long edge and prints the
projected token count BEFORE you spend anything.

  python render.py set.pdf --pages 40-52 --max-px 1600 --out pages/
  python render.py set.pdf --pages all --dry-run
"""
import argparse
import pathlib
import subprocess
import sys

from PIL import Image

PATCH = 28  # Qwen-VL effective patch size after 2x2 merge


def parse_pages(spec, total):
    if spec == "all":
        return list(range(1, total + 1))
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [p for p in out if 1 <= p <= total]


def page_count(pdf):
    txt = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    for line in txt.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise SystemExit("could not read page count -- is poppler-utils installed?")


def render_page(pdf, page, dpi, outdir):
    prefix = outdir / f"p{page:04d}"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page),
         str(pdf), str(prefix)],
        check=True, capture_output=True,
    )
    hits = sorted(outdir.glob(f"p{page:04d}*.png"))
    if not hits:
        raise SystemExit(f"pdftoppm produced nothing for page {page}")
    final = outdir / f"p{page:04d}.png"
    if hits[0] != final:
        hits[0].rename(final)
    return final


def downscale(path, max_px):
    img = Image.open(path)
    if max(img.size) > max_px:
        ratio = max_px / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)),
                         Image.LANCZOS)
        img.save(path)
    return img.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", default="all", help="'all', '3', '5-12', '2,7,9-11'")
    ap.add_argument("--dpi", type=int, default=200, help="render DPI before downscale")
    ap.add_argument("--max-px", type=int, default=1600, help="cap on the long edge")
    ap.add_argument("--out", default="pages")
    ap.add_argument("--dry-run", action="store_true",
                    help="estimate tokens only, render nothing")
    ap.add_argument("--in-price", type=float, default=0.45,
                    help="USD per 1M input tokens")
    args = ap.parse_args()

    pdf = pathlib.Path(args.pdf)
    if not pdf.exists():
        sys.exit(f"no such file: {pdf}")
    total = page_count(pdf)
    pages = parse_pages(args.pages, total)
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        # square worst case at the cap
        est = (args.max_px * args.max_px) // (PATCH * PATCH)
        tot = est * len(pages)
        print(f"{len(pages)} of {total} pages, <= {est:,} image tokens each")
        print(f"upper bound {tot:,} input tokens = ${tot / 1e6 * args.in_price:.2f}")
        return

    grand = 0
    for p in pages:
        path = render_page(pdf, p, args.dpi, outdir)
        w, h = downscale(path, args.max_px)
        tok = (w * h) // (PATCH * PATCH)
        grand += tok
        print(f"page {p:>4}  {w}x{h}  ~{tok:,} tokens  {path}")
    print(f"\ntotal ~{grand:,} input tokens = ${grand / 1e6 * args.in_price:.2f}")


if __name__ == "__main__":
    main()
