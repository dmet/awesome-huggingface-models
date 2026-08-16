#!/usr/bin/env python3
"""Score extracted facts against hand-keyed truth. This is the whole point.

truth.jsonl uses the same record shape you key by hand:
  {"type":"equipment_schedule_row","tag":"AHU-1","attrs":{"CFM":"6000"},
   "source":{"sheet":"M-501"}}

  python score.py facts.jsonl truth.jsonl
  python score.py facts.jsonl truth.jsonl --by-field
"""
import argparse
import collections
import json
import re


def norm(v):
    """Compare on meaning, not typography. 6,000 == 6000. '15 TON' == '15 ton'."""
    if v is None:
        return ""
    s = str(v).strip().lower().replace(",", "")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r'["“”]', "", s)
    return s


def load(path, kind="equipment_schedule_row"):
    out = {}
    errors = 0
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("type") == "extraction_error":
            errors += 1
        if r.get("type") != kind:
            continue
        key = (norm(r.get("source", {}).get("sheet")), norm(r.get("tag")))
        out[key] = {norm(k): norm(v) for k, v in (r.get("attrs") or {}).items()}
    return out, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("facts")
    ap.add_argument("truth")
    ap.add_argument("--by-field", action="store_true")
    args = ap.parse_args()

    got, errs = load(args.facts)
    want, _ = load(args.truth)

    found = set(got) & set(want)
    missed = set(want) - set(got)
    spurious = set(got) - set(want)

    field_ok = collections.Counter()
    field_tot = collections.Counter()
    wrong = []
    for key in sorted(found):
        for f, expect in want[key].items():
            field_tot[f] += 1
            actual = got[key].get(f)
            if actual == expect:
                field_ok[f] += 1
            else:
                wrong.append((key, f, expect, actual))

    print(f"rows: {len(found)}/{len(want)} found, "
          f"{len(missed)} missed, {len(spurious)} spurious")
    if errs:
        print(f"pages that failed extraction outright: {errs}")

    tot = sum(field_tot.values())
    ok = sum(field_ok.values())
    if tot:
        print(f"fields on matched rows: {ok}/{tot} correct ({ok / tot:.1%})")

    if args.by_field and field_tot:
        print("\nby field:")
        for f, n in field_tot.most_common():
            print(f"  {f:<28} {field_ok[f]:>3}/{n:<3} {field_ok[f] / n:6.1%}")

    if missed:
        print("\nmissed rows:")
        for sheet, tag in sorted(missed)[:15]:
            print(f"  {sheet or '?':<10} {tag}")
    if wrong:
        print("\nwrong values (first 15):")
        for (sheet, tag), f, e, a in wrong[:15]:
            print(f"  {sheet}/{tag} [{f}] want={e!r} got={a!r}")


if __name__ == "__main__":
    main()
