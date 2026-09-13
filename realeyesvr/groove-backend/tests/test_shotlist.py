"""Offline tests for the planner. No audio decode, no API calls."""
import csv
import json

import pytest

from musicvideo import shotlist
from musicvideo.assemble import _slot_frames
from config import settings


def _analysis(tempo=120.0, duration=32.0, bars=16):
    bar = (60.0 / tempo) * 4
    downbeats = [round(i * bar, 4) for i in range(bars)]
    return {
        "audio_file": "t.wav", "duration_s": duration, "tempo_bpm": tempo,
        "beats_per_bar": 4, "downbeats": downbeats,
        "sections": [
            {"index": 0, "start_s": 0.0, "end_s": 16.0, "duration_s": 16.0, "energy": 0.05},
            {"index": 1, "start_s": 16.0, "end_s": 32.0, "duration_s": 16.0, "energy": 0.9},
        ],
    }


STYLE = {"look": "cinematic", "subjects": ["a road", "a field"],
         "camera_low": ["slow drift"], "camera_high": ["whip pan"]}


def test_shots_tile_the_track_with_no_gaps_or_overlaps():
    plan = shotlist.build(_analysis(), STYLE)
    shots = plan["shots"]
    assert shots[0]["start_s"] == 0.0
    assert shots[-1]["end_s"] == pytest.approx(32.0)
    for a, b in zip(shots, shots[1:]):
        assert a["end_s"] == pytest.approx(b["start_s"]), "gap or overlap between shots"


def test_every_cut_lands_on_a_downbeat():
    a = _analysis()
    grid = set(a["downbeats"]) | {a["duration_s"]}
    for shot in shotlist.build(a, STYLE)["shots"]:
        assert min(abs(shot["start_s"] - g) for g in grid) < 0.01


def test_loud_sections_cut_faster_than_quiet_ones():
    shots = shotlist.build(_analysis(), STYLE)["shots"]
    quiet = [s["slot_s"] for s in shots if s["section"] == 0]
    loud = [s["slot_s"] for s in shots if s["section"] == 1]
    assert min(quiet) > min(loud), "energy is not driving cut rate"


def test_generated_duration_always_covers_the_slot():
    for shot in shotlist.build(_analysis(), STYLE)["shots"]:
        if shot["slot_s"] <= max(settings.ALLOWED_DURATIONS):
            assert shot["gen_duration_s"] >= shot["slot_s"], "clip too short for its slot"
        assert shot["gen_duration_s"] in settings.ALLOWED_DURATIONS


def test_frame_boundaries_telescope_with_no_drift():
    """Per-shot rounding would random-walk; boundary rounding must not."""
    shots = shotlist.build(_analysis(), STYLE)["shots"]
    total = sum(_slot_frames(s) for s in shots)
    assert total == round(shots[-1]["end_s"] * settings.FPS) - round(
        shots[0]["start_s"] * settings.FPS)


def test_real_track_render_has_zero_accumulated_drift():
    path = settings.SHOTLIST_DIR / "Face in the dust.json"
    if not path.exists():
        pytest.skip("plan the real track first")
    plan = json.loads(path.read_text(encoding="utf-8"))
    frames = sum(_slot_frames(s) for s in plan["shots"])
    assert frames == round(plan["duration_s"] * settings.FPS)


def test_real_shotlist_covers_the_real_analysis():
    """Guards whatever real track has actually been planned."""
    hits = sorted(settings.SHOTLIST_DIR.glob("*.json"))
    if not hits:
        pytest.skip("no planned track yet")
    path = hits[0]
    plan = json.loads(path.read_text(encoding="utf-8"))
    covered = sum(s["slot_s"] for s in plan["shots"])
    assert covered == pytest.approx(plan["duration_s"], abs=0.05)


# --- lyric alignment -------------------------------------------------------

from musicvideo.lyrics import align, parse_lyrics  # noqa: E402


def test_parse_keeps_section_markers(tmp_path):
    sheet = tmp_path / "s.txt"
    sheet.write_text("[Verse 1]\nline one\nline two\n\n[Chorus]\nhook\n", encoding="utf-8")
    secs = parse_lyrics(sheet)
    assert [s["label"] for s in secs] == ["Verse 1", "Chorus"]
    assert secs[0]["lines"] == ["line one", "line two"]


def test_align_recovers_timing_from_a_noisy_transcript():
    """The ASR stream is deliberately wrong in places; anchors must still hold."""
    sections = [{"label": "Chorus", "lines": ["face in the dust", "i fell so hard"]}]
    asr = [("face", 10.0, 10.4), ("inn", 10.5, 10.8), ("the", 10.9, 11.1),
           ("dust", 11.2, 11.8), ("i", 12.0, 12.1), ("fell", 12.2, 12.5),
           ("so", 12.6, 12.8), ("hard", 12.9, 13.4)]
    out = align(sections, asr)
    line1, line2 = out["sections"][0]["lines"]
    assert line1["start_s"] == pytest.approx(10.0)
    assert line2["start_s"] == pytest.approx(12.0)
    assert out["match_rate"] > 0.8


def test_lyric_sections_become_the_shot_structure():
    a = _analysis()
    a["rms"] = [0.5] * 320
    a["rms_hz"] = 10
    lyr = {"sections": [{"label": "Verse 1", "start_s": 8.0, "end_s": 20.0,
                         "lines": [{"text": "a line", "start_s": 8.0, "end_s": 20.0}]}]}
    secs = shotlist.sections_from_lyrics(a, lyr)
    labels = [s["label"] for s in secs]
    assert "Verse 1" in labels
    assert labels[0] == "Intro", "instrumental lead-in must be labelled"
    assert secs[-1]["end_s"] == pytest.approx(a["duration_s"])


def test_lyric_becomes_the_prompt_subject():
    a = _analysis()
    a["rms"] = [0.5] * 320
    a["rms_hz"] = 10
    lyr = {"sections": [{"label": "Chorus", "start_s": 8.0, "end_s": 24.0,
                         "lines": [{"text": "face in the dust", "start_s": 8.0,
                                    "end_s": 24.0}]}]}
    a["sections"] = shotlist.sections_from_lyrics(a, lyr)
    style = dict(STYLE, use_lyrics=True)
    sung = [s for s in shotlist.build(a, style)["shots"] if s["label"] == "Chorus"]
    assert sung and all("face in the dust" in s["prompt"] for s in sung)


# --- treatment controls ----------------------------------------------------

from musicvideo.shotlist import _units  # noqa: E402

TREATMENT = {
    "world": "a desert", "cast": "three travellers", "look": "film grain",
    "arc": [{"until": 0.5, "camera": ["wide"]}, {"until": 1.0, "camera": ["close"]}],
    "sections": {"Intro": {"hold": True, "camera": ["held wide"]},
                 "Outro": {"bars": 4, "camera": ["first image", "second image"]}},
    "camera_low": ["drift"], "camera_high": ["push"],
}


def _lyric_analysis():
    a = _analysis()
    a["rms"] = [0.5] * 320
    a["rms_hz"] = 10
    lyr = {"sections": [{"label": "Verse 1", "start_s": 8.0, "end_s": 24.0,
                         "lines": [{"text": "a line", "start_s": 8.0, "end_s": 24.0}]}]}
    a["sections"] = shotlist.sections_from_lyrics(a, lyr)
    return a


def test_held_section_is_one_shot_spanning_the_whole_section():
    shots = shotlist.build(_lyric_analysis(), TREATMENT)["shots"]
    intro = [s for s in shots if s["label"] == "Intro"]
    assert len(intro) == 1, "a hold must not be split into cuts"
    assert intro[0]["hold"] is True
    assert intro[0]["end_s"] == pytest.approx(shots[1]["start_s"])


def test_hold_buys_the_longest_clip_available():
    shots = shotlist.build(_lyric_analysis(), TREATMENT)["shots"]
    intro = next(s for s in shots if s["hold"])
    assert intro["gen_duration_s"] == max(settings.ALLOWED_DURATIONS)


def test_section_camera_list_plays_in_written_order():
    shots = shotlist.build(_lyric_analysis(), TREATMENT)["shots"]
    outro = [s for s in shots if s["label"] == "Outro"]
    if len(outro) >= 2:
        assert outro[0]["prompt"].startswith("first image")
        assert outro[1]["prompt"].startswith("second image")


def test_arc_moves_from_wide_to_close_across_the_song():
    shots = shotlist.build(_lyric_analysis(), TREATMENT)["shots"]
    arced = [s for s in shots if s["label"] not in ("Intro", "Outro")]
    assert arced[0]["prompt"].startswith("wide")
    assert arced[-1]["prompt"].startswith("close")


def test_every_prompt_fits_the_model_budget():
    a = _lyric_analysis()
    fat = dict(TREATMENT, look="x " * 900)      # a treatment far too long to send
    for shot in shotlist.build(a, fat)["shots"]:
        assert _units(shot["prompt"]) <= 1000, "prompt must be trimmed, not sent oversize"


def test_budget_drops_the_tail_not_the_framing():
    """The camera and subject must survive; the global look is what goes."""
    a = _lyric_analysis()
    fat = dict(TREATMENT, look="y " * 900)
    shot = shotlist.build(a, fat)["shots"][1]
    assert shot["prompt"].startswith("wide")
    assert "yyy" not in shot["prompt"].replace(" ", "")


# --- storyboard anchoring + approval gate ----------------------------------

from musicvideo import approve as approve_mod  # noqa: E402
from musicvideo.board import anchor as board_anchor  # noqa: E402


def _aligned():
    return {"sections": [
        {"label": "Verse 1", "lines": [
            {"text": "walking through the desert", "start_s": 30.0, "end_s": 34.0},
            {"text": "boot soles full of grit", "start_s": 34.0, "end_s": 38.0}]},
        {"label": "Chorus", "lines": [
            {"text": "face in the dust", "start_s": 60.0, "end_s": 64.0}]},
        {"label": "Chorus", "lines": [
            {"text": "face in the dust", "start_s": 120.0, "end_s": 124.0}]},
    ]}


def test_board_times_are_discarded_for_measured_ones():
    """The board's own clock is guesswork; the alignment is measurement."""
    b = {"rows": [{"label": "Verse 1", "anchor": "walking through the desert",
                   "prompt": "p1", "time": "0:00"}]}
    rows = board_anchor(b, _aligned(), 180.0)
    assert rows[0]["start_s"] == 30.0, "row must move to where the line is sung"


def test_repeated_hook_anchors_to_the_right_repeat():
    """'face in the dust' appears twice; row 2 must not snap back to row 1."""
    b = {"rows": [
        {"label": "Chorus", "anchor": "face in the dust", "prompt": "first fall"},
        {"label": "Chorus", "anchor": "face in the dust", "prompt": "second fall"}]}
    rows = board_anchor(b, _aligned(), 180.0)
    assert [r["start_s"] for r in rows] == [60.0, 120.0]


def test_row_stops_at_its_last_sung_line_not_the_next_row():
    """Otherwise a row swallows the instrumental break after it."""
    b = {"rows": [
        {"label": "Verse 1", "anchor": "walking through the desert", "prompt": "a"},
        {"label": "Chorus", "anchor": "face in the dust", "prompt": "b"}]}
    rows = board_anchor(b, _aligned(), 180.0)
    assert rows[0]["end_s"] == 38.0, "must end at the last sung line, not at 60.0"


def test_approval_sheet_round_trips_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SHOTLIST_DIR", tmp_path)
    plan = {"model": "gen4.5", "shots": [
        {"shot": 0, "start_s": 0.0, "end_s": 5.0, "slot_s": 5.0,
         "gen_duration_s": 5, "label": "Intro", "prompt": "original", "lyric": ""}]}
    path = tmp_path / "s.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    approve_mod.write(path)
    sheet = approve_mod.read("s")
    assert approve_mod.is_approved(sheet[0]), "shots default to approved"

    rows = list(csv.DictReader(open(approve_mod.sheet_path("s"),
                                    newline="", encoding="utf-8-sig")))
    rows[0]["approve"] = "no"
    rows[0]["prompt"] = "edited by reviewer"
    with open(approve_mod.sheet_path("s"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    approve_mod.write(path)          # re-planning must not wipe the review
    sheet = approve_mod.read("s")
    assert not approve_mod.is_approved(sheet[0])
    assert sheet[0]["prompt"] == "edited by reviewer"


# --- film grammar ----------------------------------------------------------

from musicvideo.shotlist import _slate, check_screen_direction  # noqa: E402


def test_slate_reads_like_a_board_id():
    assert _slate("Verse 1", 0) == "V1-A"
    assert _slate("Final Chorus", 2) == "FC-C"
    assert _slate("Chorus", 26) == "C-AA"


def test_180_rule_flags_a_reversed_cut():
    shots = [{"shot": 0, "start_s": 0.0, "direction": "left to right"},
             {"shot": 1, "start_s": 4.0, "direction": "right to left"}]
    hits = check_screen_direction(shots)
    assert len(hits) == 1 and hits[0]["at_s"] == 4.0


def test_180_rule_ignores_a_neutral_pivot():
    shots = [{"shot": 0, "start_s": 0.0, "direction": "left to right"},
             {"shot": 1, "start_s": 4.0, "direction": "toward camera"},
             {"shot": 2, "start_s": 8.0, "direction": "right to left"}]
    assert check_screen_direction(shots) == []


def test_grammar_fields_land_on_the_shot_separately():
    a = _lyric_analysis()
    style = {"arc": [{"until": 1.0, "size": ["close up"],
                      "movement": ["handheld push in"],
                      "direction": "toward camera"}],
             "lens": "35mm", "look": "pencil sketch",
             "camera_low": ["x"], "camera_high": ["y"]}
    shot = shotlist.build(a, style)["shots"][0]
    assert shot["size"] == "close up"
    assert shot["movement"] == "handheld push in"
    assert shot["lens"] == "35mm"
    # and the prompt states them in board order: movement, size, ... lens
    assert shot["prompt"].index("handheld push in") < shot["prompt"].index("close up")
    assert shot["prompt"].index("close up") < shot["prompt"].index("35mm")


# --- screen direction enforcement ------------------------------------------

import subprocess  # noqa: E402

from musicvideo import direction as dirmod  # noqa: E402


def test_label_has_a_deadzone_so_stillness_is_not_a_direction():
    assert dirmod.label(0.0) == ""
    assert dirmod.label(dirmod.DEADZONE / 2) == ""
    assert dirmod.label(2.0) == "left to right"
    assert dirmod.label(-2.0) == "right to left"


def test_flip_is_skipped_for_directions_a_mirror_cannot_change():
    """Toward/away from camera survive a horizontal flip, so never measure."""
    flip, shift = dirmod.needs_flip("does-not-exist.mp4", "toward camera")
    assert flip is False and shift == 0.0


def _pan(tmp_path, rightward: bool):
    """A camera pan across a static non-repeating scene."""
    scene = tmp_path / "scene.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                    "-i", "nullsrc=s=960x180", "-vf",
                    "geq=lum='random(1)*255':cb=128:cr=128,boxblur=3:1",
                    "-frames:v", "1", str(scene)], capture_output=True)
    x = "max(0,639-60*t)" if rightward else "min(639,60*t)"
    out = tmp_path / ("r.mp4" if rightward else "l.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(scene),
                    "-t", "3", "-r", "24", "-vf", f"crop=320:180:x='{x}':y=0",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
                   capture_output=True)
    return out


def test_measures_real_pans_in_both_directions(tmp_path):
    assert dirmod.label(dirmod.measure(str(_pan(tmp_path, True)))) == "left to right"
    assert dirmod.label(dirmod.measure(str(_pan(tmp_path, False)))) == "right to left"


def test_flips_only_when_the_clip_contradicts_the_board(tmp_path):
    clip = str(_pan(tmp_path, True))          # content travels left to right
    assert dirmod.needs_flip(clip, "left to right")[0] is False
    assert dirmod.needs_flip(clip, "right to left")[0] is True


def test_incoherent_texture_never_triggers_a_flip(tmp_path):
    """A false direction reading would mirror a perfectly good clip."""
    out = tmp_path / "noise.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                    "-i", "nullsrc=s=320x180:d=3:r=24", "-vf",
                    "geq=lum='random(0)*255':cb=128:cr=128",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
                   capture_output=True)
    assert dirmod.label(dirmod.measure(str(out))) == ""
