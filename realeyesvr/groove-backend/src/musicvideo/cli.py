"""Pipeline entry point.

  python -m musicvideo.cli analyze  audio/song.mp3 [--beats audio/song.drums.mp3]
  python -m musicvideo.cli plan     song --style prompts/example_style.json
  python -m musicvideo.cli animatic song          # free timing preview
  python -m musicvideo.cli generate song [--limit 3] [--dry-run]
  python -m musicvideo.cli render   song
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config import settings  # noqa: E402


def _audio_for(song: str) -> Path:
    hits = [p for p in settings.AUDIO_DIR.iterdir()
            if p.stem == song and p.suffix.lower() in (".mp3", ".wav", ".flac", ".m4a")]
    if not hits:
        raise SystemExit(f"no audio file named '{song}' in {settings.AUDIO_DIR}")
    return hits[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Suno -> Runway beat-aligned music video")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="tempo, beat grid, downbeats, sections")
    a.add_argument("audio", type=Path)
    a.add_argument("--beats", type=Path, default=None,
                   help="optional percussion stem to track beats on")

    ly = sub.add_parser("lyrics", help="align a lyric sheet to the timeline")
    ly.add_argument("audio", type=Path)
    ly.add_argument("--sheet", type=Path, default=None,
                    help="default: lyrics/<song>.txt")
    ly.add_argument("--vocals", type=Path, default=None,
                    help="optional vocals stem -- much better alignment")

    p = sub.add_parser("plan", help="build the beat-aligned shot list")
    p.add_argument("song")
    p.add_argument("--style", type=Path,
                   default=settings.PROMPTS_DIR / "example_style.json")
    p.add_argument("--board", type=Path, default=None,
                   help="storyboard JSON; default boards/<song>.json if present")
    p.add_argument("--no-lyrics", action="store_true",
                   help="ignore the aligned lyric timeline even if present")

    ap_ = sub.add_parser("approve", help="write the review sheet + page (the gate)")
    ap_.add_argument("song")

    g = sub.add_parser("generate", help="call Runway for each planned shot")
    g.add_argument("song")
    g.add_argument("--limit", type=int, default=None, help="only the first N shots")
    g.add_argument("--dry-run", action="store_true", help="print shots, spend nothing")
    g.add_argument("--force", action="store_true",
                   help="bypass the approval gate (not recommended)")

    an = sub.add_parser("animatic", help="free coloured-slate timing preview")
    an.add_argument("song")

    r = sub.add_parser("render", help="cut the real clips and mux the song")
    r.add_argument("song")

    args = ap.parse_args(argv)

    if args.cmd == "analyze":
        from musicvideo import analyze
        out = analyze.run(args.audio, args.beats)
        import json
        d = json.loads(out.read_text(encoding="utf-8"))
        print(f"{d['tempo_bpm']} BPM | {d['beat_count']} beats | "
              f"{len(d['downbeats'])} bars | {len(d['sections'])} sections "
              f"| {d['duration_s']}s")
        print(f"-> {out}")
        return 0

    if args.cmd == "lyrics":
        from musicvideo import lyrics
        sheet = args.sheet or (ROOT / "lyrics" / f"{args.audio.stem}.txt")
        if not sheet.exists():
            raise SystemExit(f"no lyric sheet at {sheet}")
        out = lyrics.run(args.audio, sheet, args.vocals)
        import json
        d = json.loads(out.read_text(encoding="utf-8"))
        print(f"matched {d['matched_words']}/{d['word_count']} lyric words "
              f"({d['match_rate']:.0%}) against {d['asr_word_count']} heard words")
        for s_ in d["sections"]:
            print(f"  {s_['start_s']:>7.2f} -> {s_['end_s']:>7.2f}s  {s_['label']}")
        print(f"-> {out}")
        return 0

    if args.cmd == "plan":
        from musicvideo import shotlist
        lyr = settings.ANALYSIS_DIR / f"{args.song}.lyrics.json"
        brd = args.board or (ROOT / "boards" / f"{args.song}.json")
        out = shotlist.run(settings.ANALYSIS_DIR / f"{args.song}.json", args.style,
                           None if args.no_lyrics else lyr,
                           brd if brd.exists() else None)
        import json
        d = json.loads(out.read_text(encoding="utf-8"))
        used = "lyric sections" if (lyr.exists() and not args.no_lyrics) else "audio clustering"
        if brd.exists():
            n = sum(1 for s_ in d["shots"] if s_.get("from_board"))
            used = f"storyboard ({n} shots) + {used}"
        print(f"{d['shot_count']} shots | {d['generated_seconds']}s to generate | {used}")
        print(f"-> {out}  (and the .csv beside it)")
        return 0

    if args.cmd == "approve":
        from musicvideo import approve
        sheet, page = approve.write(settings.SHOTLIST_DIR / f"{args.song}.json")
        rows = approve.read(args.song)
        ok = [r for r in rows.values() if approve.is_approved(r)]
        print(f"{len(rows)} shots, {len(ok)} marked approved, "
              f"{sum(int(r['gen_duration_s']) for r in ok)}s of video to buy")
        print(f"  review : {page}")
        print(f"  edit   : {sheet}   (approve column: yes/no; prompt column is editable)")
        return 0

    if args.cmd == "generate":
        from musicvideo import generate
        generate.run(settings.SHOTLIST_DIR / f"{args.song}.json",
                     limit=args.limit, dry_run=args.dry_run, force=args.force)
        return 0

    from musicvideo import assemble
    assemble.run(settings.SHOTLIST_DIR / f"{args.song}.json",
                 _audio_for(args.song), animatic=(args.cmd == "animatic"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
