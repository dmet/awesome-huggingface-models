"""Beat-exact previewer for the whole sheet, 29.632 -> 86.300 (56.668s).

Every segment length is a measured shot extent. Undrawn shots and the coverage
hole play as slates, so the previewer never flatters the state of the work.
The C-A crane is a real crop path over the tall plate -- no generation.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "output" / "build"
PANELS = ROOT / "output" / "panels" / "test"
BUILD.mkdir(parents=True, exist_ok=True)
PANELS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import subprocess, sys

P = PANELS
S = BUILD
OUT = ROOT / "output" / "renders"
FONT = "C\\:/Windows/Fonts/arial.ttf"
FPS = 24
SHEET_START = 29.632

# (name, frames, kind, payload)
SEGS = [
    ("s0_v1a1", 170, "drift",  "C_composed"),
    ("s0_v1a2", 165, "drift",  "G_follow"),
    ("s1_v1b",  163, "slate",  "V1-B|no panel drawn|5 cr to draw"),
    ("s2_v1c",  212, "push",   "A_man"),
    ("s3_hole", 169, "hole",   "59.21 - 66.26|no row|falls through to the arc"),
    ("s4_ca",   481, "crane",  "F_tall"),
]
TOTAL = sum(s[1] for s in SEGS)


def run(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        print("FAILED:", " ".join(args[:9]), "...")
        print(r.stderr[-1400:])
        sys.exit(1)


def esc(t):
    return t.replace(":", "\\:").replace("'", "")


for name, frames, kind, payload in SEGS:
    dur = frames / FPS
    out = str(S / (name + ".mp4"))
    if kind in ("drift", "push"):
        src = str(P / (payload + ".png"))
        if kind == "push":
            vf = ("scale=1920:-1,zoompan=z='min(zoom+0.0009,1.35)':d=%d"
                  ":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps=%d"
                  ",format=yuv420p" % (frames, FPS))
        else:
            # lateral drift -- the camera travelling with him
            vf = ("scale=1600:-1,crop=1280:720:'(iw-1280)*(0.5-0.5*cos(PI*t/%f))':"
                  "(ih-720)/2,fps=%d,format=yuv420p" % (dur, FPS))
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", src,
             "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-crf", "20", out])
    elif kind == "crane":
        src = str(P / (payload + ".png"))
        # 1080x1920 plate, 16:9 window at full width = 1080x608, travel y 0 -> 1312
        vf = ("crop=1080:608:0:'1312*(0.5-0.5*cos(PI*t/%f))',scale=1280:720"
              ",fps=%d,format=yuv420p" % (dur, FPS))
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", src,
             "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-crf", "20", out])
    else:
        a, b, c = payload.split("|")
        bg = "0x1B2226" if kind == "slate" else "0x241A1A"
        accent = "0xA9CDE1" if kind == "slate" else "0xE8703F"
        vf = (("drawtext=fontfile='%s':text='%s':fontcolor=%s:fontsize=30:"
               "x=(w-text_w)/2:y=h/2-72," % (FONT, esc(a), accent)) +
              ("drawtext=fontfile='%s':text='%s':fontcolor=0x9BA7AE:fontsize=42:"
               "x=(w-text_w)/2:y=h/2-24," % (FONT, esc(b))) +
              ("drawtext=fontfile='%s':text='%s':fontcolor=0x6B767C:fontsize=24:"
               "x=(w-text_w)/2:y=h/2+42" % (FONT, esc(c))))
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             "color=c=%s:s=1280x720:r=%d" % (bg, FPS), "-vf", vf,
             "-frames:v", str(frames), "-c:v", "libx264", "-crf", "20", out])
    print("  %-10s %4d frames  %6.3fs  %s" % (name, frames, dur, kind))

# concat
lst = S / "prev.txt"
lst.write_text("".join("file '%s/%s.mp4'\n" % (S.as_posix(), s[0]) for s in SEGS),
               encoding="utf-8")
run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
     "-i", str(lst), "-c:v", "copy", str(S / "prev_v.mp4")])

# audio from the real track at the sheet's start; apad + shortest so the mux
# lands on the video's frame count instead of truncating it
run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(SHEET_START),
     "-i", str(ROOT / "audio" / "Face in the dust.mp3"), "-vn",
     "-t", str(TOTAL / FPS + 1), "-c:a", "aac", "-b:a", "192k", str(S / "prev_a.m4a")])
run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(S / "prev_v.mp4"),
     "-i", str(S / "prev_a.m4a"), "-map", "0:v:0", "-map", "1:a:0",
     "-af", "apad", "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
     "-movflags", "+faststart", str(OUT / "sheet2_previewer.mp4")])

r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=nb_frames,duration",
                    "-of", "default=nw=1", str(OUT / "sheet2_previewer.mp4")],
                   capture_output=True, text=True)
print("\nexpected %d frames / %.3fs" % (TOTAL, TOTAL / FPS))
print(r.stdout.strip())
print("%.0f KB" % ((OUT / "sheet2_previewer.mp4").stat().st_size / 1024))
