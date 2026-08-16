#!/usr/bin/env python3
"""One-off script to write truth.jsonl from a hand transcription of doorsTest.png.

Key names match extract.py's v2 prompt convention, which qualifies every
Door-group column as "Door <name>" and every Frame-group column as
"Frame <name>" (not just the two that actually collide) -- so truth uses the
same convention to keep field-level comparison meaningful.
"""
import json

COMMON = {"Door Width": "3'", "Door Height": "8'", "Door Thickness": '1.75"', "Frame Trim": '2"'}

ROWS = [
    ("101", {"Door Type": "Door", "Door Swing": "Pair", "Door Material": "AL", "Door Finish": "AL",
              "Door Hardware Set": "8", "Frame Material": "AL", "Frame Type": "B",
              "Notes": '3 5/8" Studs with rock both sides, 18" sidelights both sides of door.',
              "Card Reader": "Yes", "Plan Notes": "AL Door assembly - Need Card Reader"}),
    ("102", {"Door Type": "A", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "1", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.'}),
    ("103", {"Door Type": "A", "Door Swing": "RH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "1", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.'}),
    ("104", {"Door Type": "A", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "1", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.'}),
    ("105", {"Door Type": "A", "Door Swing": "RH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "2", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.',
              "Card Reader": "Yes", "Plan Notes": "Need card reader"}),
    ("106", {"Door Type": "A", "Door Swing": "RH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "5", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.'}),
    ("107", {"Door Type": "A", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "5", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.'}),
    ("108", {"Door Type": "A", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "5", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.',
              "Card Reader": "Yes", "Plan Notes": "Need card reader, Need vision kit"}),
    ("109A", {"Door Type": "B", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "4", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.',
              "Card Reader": "Yes", "Plan Notes": "Keep WI Frames and SCWD need vision kit"}),
    ("109B", {"Door Type": "B", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "3", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '10" studs with 5/8" rock both sides.',
              "Plan Notes": "Keep WI Frames and SCWD"}),
    ("114", {"Door Type": "C", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "6", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '10" studs with 5/8" rock both sides.',
              "Plan Notes": "Keep WI Frames and SCWD"}),
    ("115", {"Door Type": "C", "Door Swing": "RH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "6", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '10" studs with 5/8" rock both sides.',
              "Plan Notes": "Keep WI Frames and SCWD"}),
    ("116", {"Door Type": "B", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "4", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '10" studs with 5/8" rock both sides.',
              "Card Reader": "Yes",
              "Plan Notes": "Keep WI Frames and SCWD need vision kit, Need card reader"}),
    ("RR 110", {"Door Type": "-", "Door Swing": "RH", "Door Material": "-", "Door Finish": "Stain",
              "Door Hardware Set": "-", "Frame Material": "WI", "Frame Type": "-",
              "Notes": "Existing Door/Frame - No Change"}),
    ("RR 111", {"Door Type": "-", "Door Swing": "LH", "Door Material": "-", "Door Finish": "Stain",
              "Door Hardware Set": "-", "Frame Material": "WI", "Frame Type": "-",
              "Notes": "Existing Door/Frame - No Change"}),
    ("RR 112", {"Door Type": "C", "Door Swing": "LH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "7", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.',
              "Plan Notes": "Need new lockset, frame and door"}),
    ("RR 113", {"Door Type": "C", "Door Swing": "RH", "Door Material": "SCWD", "Door Finish": "Stain",
              "Door Hardware Set": "7", "Frame Material": "WI", "Frame Type": "A",
              "Notes": '3 5/8" Studs with 5/8" rock both sides.',
              "Plan Notes": "Need new lockset, frame and door"}),
]

with open("truth.jsonl", "w") as fh:
    for tag, attrs in ROWS:
        full = {**COMMON, **attrs}
        fh.write(json.dumps({
            "type": "equipment_schedule_row",
            "tag": tag,
            "attrs": full,
            "source": {"sheet": "A2.1"},
        }) + "\n")

print(f"wrote {len(ROWS)} rows to truth.jsonl")
