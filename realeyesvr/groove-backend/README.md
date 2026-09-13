# musicTest — Suno track → beat-cut Runway music video

Take a song made in Suno, analyse its beat grid and structure, generate a Runway
clip per shot, and cut the result **on the downbeats** with the original audio
back on top.

## The thing to understand first

**Runway understands duration, not phase.**

- *Duration* — yes, and precisely. `duration` is a hard parameter: gen4.5 takes
  any integer 2–10 seconds and gives you exactly that. This is the only time
  handle the API offers, and it is the one BPM can reach.
- *Phase* — **not in text-to-video.** There is no way to tell `gen4.5` that the
  whip pan lands at t=2.184s. Putting "137 BPM" or "on the beat" in a prompt is
  a vibe cue, not an instruction.
- *Motion rate* — no. You cannot ask for a pan that cycles every 0.437s.

So BPM reaches text-to-video only after you convert it into a requested
duration. Everything else about the rhythm has to be built in the edit.

**Video-to-video is a different story, and it is the way in.** `aleph2` on
`video_to_video` takes `keyframes` — up to 5 timed guidance images, each at a
float `seconds` offset into a source video you supply. That is an addressable
timeline. Measured on a 7.083s source (see *What the API actually does*): frame
count and duration came back untouched, and the source's own cuts came back on
the **identical frame**.

Which inverts the pipeline. You stop buying timing and start supplying it: draw
panels, cut them to the beat in ffmpeg for nothing, then hand that edit to
`aleph2` as the source. The alignment is structural — you authored it, and the
model never needs to know the BPM.

(Reference audio exists but cannot carry a song. `hailuo3` caps combined audio
reference at **15s** and `seedance2_5` at **under 30s**, and the SDK calls it
"additional context for the output" — no sync claim. Those models also carry
`audio: bool` and generate their own audio, which for a Suno track is a
liability. It is mood conditioning for one short clip, not a spine.)

The rhythm comes from the **edit**, not the generation:

```
Suno mp3 ──► analyse ──► shot list ──► Runway ──► assemble ──► final.mp4
        │    beats,       every cut     one clip    fit to bar,
        │    downbeats,   on a down-    per shot    concat, mux
        │    energy       beat; length              original audio
        │                 in bars
        └──► lyrics  ─────────┘
             align the sheet to the timeline:
             real verse/chorus/bridge bounds,
             and the words sung over each shot
```

What this gives you: cuts that land on the beat, shot length that follows the
bar, and cut *rate* that follows section energy — quiet sections hold, loud
sections cut fast.

What it does not give you: motion *inside* a clip hitting the downbeats. The
model doesn't know where the beat is, so a camera move won't punch on the one.
Only the cuts are locked to the music.

### Fitting a clip to a bar

A bar is never a whole number of seconds, so the clip you can buy never matches
the slot you need. Two ways to reconcile, set by `FIT_MODE`:

- `retime` (default) — buy the length **nearest** the slot (nearest in ratio, so
  a 6.5s slot takes 8s at x0.81 over 5s at x1.30), then `setpts` it to fit
  exactly. Keeps the entire shot.
- `trim` — buy the next length up and cut the tail off, discarding whatever the
  camera move was building toward.

On the 278s test track retime buys 297s of video where trim buys 347s — 14%
cheaper *and* nothing is thrown away. Retimes beyond `MAX_RETIME` (default
1.35x) fall back to trimming; with the full 2–10s range none do.

## Layout

```
audio/                    your Suno downloads (gitignored)
config/settings.py        env defaults, paths
prompts/*.json            look + subject pool + camera vocabulary
lyrics/                   lyric sheets with [Section] markers
src/musicvideo/
  analyze.py    1. tempo, beat grid, downbeats, sections, energy   (librosa)
  lyrics.py     1b. align a lyric sheet to the timeline     (faster-whisper)
  shotlist.py   2. beat-aligned shot list + prompts                (no API)
  generate.py   3. one Runway text-to-video call per shot          ($$)
  assemble.py   4. trim to exact bars, concat, mux audio           (ffmpeg)
  cli.py        entry point
output/analysis|shotlists|clips|renders/
output/runs.csv           flat log of every generation
scripts/                  live API probes + the board page builder
tests/                    offline, no key needed
```

## Setup

```bash
python -m venv .venv && source .venv/Scripts/activate   # Git Bash
pip install -r requirements.txt
cp .env.example .env      # paste your Runway key in
```

Needs `ffmpeg` on PATH (you have 8.1).

## Getting the audio out of Suno

There is **no public Suno API** (as of 2026 it's a curated partner programme
only), so this step is manual:

1. Open the song in Suno → `...` menu → **Download → MP3** (WAV on paid plans).
2. Optional but worth it: **Download → Stems**. Drop the drum stem in too.
3. Save both into `audio/`, e.g. `audio/mysong.mp3` and `audio/mysong.drums.mp3`.

Tracking beats on an isolated drum stem gives a much cleaner grid than a full
mix — pass it with `--beats`.

## Run

```bash
# 1. analyse  (add --beats audio/mysong.drums.mp3 if you have the stem)
python -m musicvideo.cli analyze audio/mysong.mp3

# 1b. align the lyrics — gives real section names + the words per shot
python -m musicvideo.cli lyrics audio/mysong.mp3

# 2. plan the cuts — free, inspect output/shotlists/mysong.csv and edit prompts
python -m musicvideo.cli plan mysong --style prompts/lyric_style.json

# 3. preview the TIMING for free, before spending anything
python -m musicvideo.cli animatic mysong

# 4. generate  (--dry-run first to see the bill; --limit 2 to sample the look)
python -m musicvideo.cli generate mysong --dry-run
python -m musicvideo.cli generate mysong --limit 2
python -m musicvideo.cli generate mysong

# 5. final cut
python -m musicvideo.cli render mysong

pytest tests/    # offline
```

**Do step 3 before step 4.** The animatic is coloured slates cut to the real
shot list with the real song over it. If the cut timing feels wrong there, it
will feel wrong with expensive footage too — and fixing it costs nothing.

## Lyrics

Put the sheet in `lyrics/<song>.txt`, keeping the `[Verse 1]` / `[Chorus]`
markers — those markers are the point. Then:

```bash
python -m musicvideo.cli lyrics audio/mysong.mp3 [--vocals audio/mysong.vocals.mp3]
```

This is **forced alignment, not transcription**. We already know the words; the
only question is when each is sung, so a noisy ASR pass is enough — it just has
to act as an anchor track. The known lyrics are matched onto the heard words
with a sequence aligner, and unmatched words are interpolated between anchors.

Two things come out of it:

1. **Real song structure.** Timbre clustering finds *changes*; it cannot tell a
   pre-chorus from a verse because they sound alike. The sheet names them. It
   also exposes the instrumental stretches, which become Intro / Break / Outro.
2. **The words sung over each shot.** With `"use_lyrics": true` in the style
   file, the lyric line becomes the shot's subject, so the picture tracks the
   song rather than running a decorative loop beside it. Instrumental sections
   fall back to the `subjects` pool.

The animatic burns the section name and the lyric into each slate, so you can
check the alignment by ear before spending anything.

Set `WHISPER_MODEL` to trade speed for accuracy (`tiny`/`base`/`small`/`medium`,
default `small`). A vocals stem from Suno improves it further.

## Treatments: directing the whole video

A brief like "cinematic music video following migrants across the Sonoran
Desert, begin with lonely wide shots, move closer as the music intensifies,
end on an extreme close-up" is a **treatment, not a prompt**. It cannot be sent
to Runway:

- `promptText` on gen4.5 is capped at **1000 UTF-16 code units**. A full
  treatment runs 2-3x that and the API rejects it.
- A 5-second clip cannot "build with the music" or "reach an emotional peak".
  Those instructions only mean something across a sequence of shots.

So a treatment is stored as *parts*, and each shot gets its own prompt built
from them. See `prompts/desert_treatment.json`.

```jsonc
{
  "world":  "the Sonoran Desert on the U.S.-Mexico border, ...",  // setting
  "cast":   "a small group of migrants travelling north on foot", // who
  "look":   "cinematic realism, atmospheric dust, film grain",    // every shot
  "negative": "glossy commercial aesthetic, stock footage look",

  // how the framing evolves; `until` is a fraction of the song
  "arc": [
    { "until": 0.25, "camera": ["enormous lonely extreme wide shot", "..."] },
    { "until": 0.80, "camera": ["intimate handheld close-up on a face", "..."] },
    { "until": 1.00, "camera": ["slow pull back revealing the landscape"] }
  ],

  // per-section overrides, keyed by the lyric sheet's section names
  "sections": {
    "Intro": { "hold": true, "camera": ["enormous wide shot held still"] },
    "Outro": { "bars": 4, "camera": ["first image", "second image"] }
  }
}
```

Prompts are assembled **framing first, look last** — `camera, subject, cast,
world, look` — because the tail is what gets dropped if the budget runs out.
Nothing is ever sent oversize: `generate` refuses the whole batch up front
rather than discovering a rejection halfway through a paid run.

### The controls

| Control | Does |
|---|---|
| `arc` | Framing evolves with position in the song (wide → close → pull back) |
| `sections.<name>.bars` | Override cut rate for one section |
| `sections.<name>.hold` | One shot for the whole section, no cuts |
| `sections.<name>.camera` | An ordered storyboard, played in written order |
| `negative` | Exclusions — **only `veo3.1` / `veo3.1_fast` accept these**; on gen4.5 they are dropped with a warning |

### Holding until the vocal enters

`{"Intro": {"hold": true}}` makes the intro a single unbroken shot that cuts on
the first downbeat of the vocal. On the test track that is one shot 0 → 29.63s,
then a hard cut into Verse 1.

Runway's longest clip is 10s, so a 29.6s hold is one 10s generation stretched
**2.96x**. That reads as deliberate slow motion — fine for a lonely establishing
wide, wrong for anything with visible fast movement. `HOLD_MAX_RETIME` (default
4.0) bounds it. If the slow motion is not the look you want, use `"bars": 8`
instead: roughly two 14s shots, each stretched a much gentler 1.4x.

## Importing a storyboard

A storyboard written from a lyric sheet (by ChatGPT or anyone else) carries good
prompts and a **bad clock**. Whoever wrote it could read the words but never
heard the track, so the section times are guessed -- typically a uniform grid.

On the test track the supplied board claimed Verse 1 at 0:00; it is actually
sung at 30.0s. The error was +30.0s at the top, decaying to +2.9s at the end --
not a constant offset, so it cannot be fixed by shifting.

`boards/<song>.json` holds the rows. Each carries an `anchor` -- its first
lyric line -- and the board's own TIME column is thrown away. Rows are matched
against the measured alignment, searching forward only, so a repeated hook like
"Face in the dust" lands on the right repeat. A row ends at its **last sung
line**, not at the next row, so it cannot swallow an instrumental break.

The board on the test track covers 14 rows over 69% of the song. The remaining
86s -- a 30s intro, two ~16s breaks, a 24s outro -- have no row and fall
through to the treatment's `arc`.

## The approval gate

Generation is the only stage that spends money and the only one that cannot be
undone, so nothing reaches it unreviewed.

```bash
python -m musicvideo.cli approve "mysong"
```

writes two things:

- `output/boards/<song>.review.html` — a page to read: every shot with its time,
  section, lyric or action, and the exact prompt that would be sent.
- `output/shotlists/<song>.approval.csv` — a sheet to edit. `approve` takes
  yes/no; the `prompt` column is editable and **whatever is written there is
  what gets sent**.

`generate` refuses to run until the sheet exists, skips anything not approved,
and uses the sheet's prompts over the planner's. Re-running `approve` after a
re-plan preserves existing decisions. `--force` bypasses the gate.

## The board sheet

`scripts/build_board.py` renders a sheet the way a production board reads —
slate strip, framed panel, caption, movement arrows — with two views over the
same rows:

- **Board**, a grid. Good for judging pictures and story order.
- **Timeline**, width proportional to duration, doubling as the previewer's
  transport. Good for judging rhythm and coverage.

The timeline earns its place by showing what a grid structurally cannot. A row
whose anchor matches no lyric line is silently dropped by `board.py` — on a grid
it looks like a normal cell; on a timeline its absence is a visible hole. Shot
extents differ by seconds and look identical in a grid. A 20s composite reads as
four times its neighbours instead of hiding in an equal box.

`scripts/build_previewer.py` cuts the panels to the measured shot extents with
the real track over them. Undrawn shots and coverage holes play as slates, so
the previewer never flatters the state of the work. Mux with `apad` and
`-shortest`, not `-shortest` alone — truncating to the shorter stream costs
frames and breaks the exact-frame-count guarantee the render depends on.

## Film grammar

Shots carry the fields a real board caption states separately, rather than one
prose string: `size`, `lens`, `movement`, `direction`, `pov`, `subject`. The
prompt is assembled in that order. Shots also get a board-style slate --
`V1-A`, `C-B`, `FC-F` -- alongside the index.

Set them per arc stage or per section:

```jsonc
"arc": [
  { "until": 0.25, "size": ["extreme wide shot"],
    "movement": ["static locked-off"], "direction": "left to right" }
]
```

### Screen direction and the 180-degree rule

Cutting from a shot where the subject travels left-to-right to one where they
travel right-to-left reads as the subject turning round. A board artist tracks
this by eye; a generator has no idea, and every clip here is an independent
generation.

`plan` reports crossings in `line_crossings`. It does not block them -- crossing
the line is sometimes the point.

Enforcement does **not** rely on the prompt. Direction is a fact about the image
plane, and models mirror it freely. Instead the assembler measures which way
each returned clip actually moves and mirrors it when it contradicts the board.
A horizontal flip is free and exact. Set `ENFORCE_DIRECTION=false` to disable.

The measurement collapses each frame to a column profile and correlates
profiles half a second apart. Two failure modes had to be designed out:

- **Slow drift vanished.** Sub-pixel per-frame motion rounds to zero, so
  comparison is across a stride rather than consecutive frames.
- **Incoherent texture invented a direction**, which would mirror a good clip.
  A z-score against the other offsets does not separate this (1.9 vs 3.0);
  absolute correlation does — measured 0.10 for noise against 0.94–1.00 for a
  real pan. The gate is `MIN_CORR`.

## Tuning the edit

In `.env`:

- `MIN_BARS_PER_SHOT` / `MAX_BARS_PER_SHOT` — the cut-rate range. A loud section
  gets `MIN`, a silent one gets `MAX`, linear in between.
- `BEATS_PER_BAR` — set to 3 for waltz-time, 4 is assumed otherwise.

In your style file: `subjects` is a pool cycled across shots, `camera_low` /
`camera_high` are picked by section energy, `look` is appended to every prompt
so the grade stays consistent.

## How this was verified without spending credits

Three of the four stages never touch Runway, so they were exercised against the
real track directly. For the one stage that costs money, the generated clips
were replaced with ffmpeg-made stand-ins at exactly the durations the planner
asked for — the assembler only sees mp4 files at paths, so it cannot tell the
difference. Each stand-in carries a luma ramp that runs 0→255 exactly once over
its own length, which makes "did the retime preserve the whole shot?" directly
measurable.

Results on *Face in the dust* (278.0s, 137.2 BPM, 67 shots):

| Check | Result |
|---|---|
| Tempo stability | 94.5% of beat intervals within 5% of median; no octave error |
| Downbeat grid (synthetic 120 BPM control) | within **17 ms** over all 16 bars |
| Section boundary (control, true change at 16.0s) | detected 16.01s |
| Shot coverage | 0.0 → 278.0s, zero gaps or overlaps |
| Cut rate | 2-bar shots in loud sections, 4-bar in quiet |
| Retime coverage | 67/67 shots, factors x0.880–x1.060 |
| Motion preserved through retime | 10/10 stand-ins kept their full ramp |
| Render length | 278.000s, 6672 frames = 278 x 24 exactly, no drift |
| Lyric alignment | 236/254 words matched (93%) against 251 heard words |
| Structure agreement | lyric vs audio-clustering bounds within 0.37s (Verse 1), 0.38s and 0.47s (both Choruses), 2.3s (Bridge) |
| Treatment prompts | 56 shots, longest 538 of 1000 units, none oversize |
| Prompt trimming | an over-long treatment drops the look, keeps the framing |
| Board re-anchoring | 14/14 rows placed; repeated hooks hit the right repeat |
| Board coverage | 69% of the song; 86s of instrumental correctly left to the arc |
| Approval gate | blocks unapproved runs, honours no/edits, survives re-planning |
| Direction measurement | 5/5 on fixtures: both pan directions, slow drift, locked-off, incoherent |
| Flip decisions | correct in all cases, including never flipping on a false reading |

## What the API actually does

The above was all offline. These are measured against a live key on 2026-08-26,
with the probes in [`scripts/`](scripts/README.md). Prices are observed, not
quoted.

| Measured | Result |
|---|---|
| `gen4_image` at 1280:720 | **5 credits** per image |
| `gen4_image` at 1080:1920 | **8 credits** — price is resolution-tiered |
| `aleph2` video-to-video | **27.7 credits/sec** (196 cr for 7.083s) |
| A 278s song through `aleph2` | ≈ **7,700 credits**, against a 10,000 monthly cap |
| A 57-panel board | ≈ **285 credits** — 3.7% of the video pass |

**Reference images hold a character.** `gen4_image` takes up to three
`reference_images`, each with a `tag` you then write as `@tag` in the prompt.
A character plate and a location plate held identity across new framings, new
seeds and new lighting. Fine specified details do not survive — a named scar
never rendered — but the person and the place do. This is the fix for the
montage problem below, and it is what makes a storyboard worth drawing.

**`aleph2` preserves your edit, and bleeds your content.** On a 7.083s source
cut on real downbeats: 170 frames in, 170 out, duration identical, output
upscaled 1280x720 → 1920x1080 for free, and two of three cuts returned on the
exact frame. The third vanished — a keyframe at 5.301s propagated *backward* and
replaced the shot before it, so both sides matched and the cut dissolved.

That is the model working as designed, not failing. Interpolating between
keyframes is the point. The unit is therefore **one call per shot**, its
keyframes being moments within one continuous action — the structure a
storyboard already uses when it draws one camera move across several panels.
Cuts belong between calls, in ffmpeg, where they are free and frame-exact.

Two hard limits shape any design here: **5 keyframes per call**, and a keyframe
`range` window measured in **whole seconds** while placement is a float — so
ranges cannot fence individual shots on a 137 BPM grid (a bar is 1.749s).

**Not covered**: whether `gen4.5` text-to-video prompts produce usable footage,
and whether polling and download behave on a long batch. Run
`generate --limit 2` first.

## Caveats worth knowing

- **Duration range is confirmed**: gen4.5 takes *any integer 2–10s*, read from
  the installed SDK's typed params (`runwayml 5.16.0`,
  `types/text_to_video_create_params.py`: "Must be an integer from 2 to 10").
  The help centre's 5/8/10 is wrong. This matters a lot — with a 5s floor only
  19 of 67 shots could be retimed; with the real range all 67 can, and the bill
  drops 14%. `ratio` for gen4.5 is `1280:720` or `720:1280` only.
- **librosa has no downbeat tracker.** `analyze.py` assumes a fixed meter and
  picks the bar phase by onset energy. It's solid on 4/4 with a clear kick;
  expect it to struggle on rubato, swing, or a track with no drums.
- **Section detection is unsupervised** (agglomerative clustering on
  chroma+MFCC, boundaries snapped to downbeats). It finds *changes*, not
  verse/chorus labels. Roughly one section per 15s, clamped 3–10.
- ~~**Shots have no visual continuity.**~~ **Solved, and not by chaining.**
  Generate a character plate and a location plate once, then pass them as tagged
  `reference_images` on every panel. Shots stay independent — parallel,
  rerollable, consistent. Chaining last-frame → next-shot is sequential and
  drifts; this does not. Note `gen4.5`'s `promptImage.position` is
  `Literal["first"]` only, so it cannot take an end frame; the unified
  `generate.video` endpoint exposes `role: "first" | "last"` but requires a
  saved Model Router `configId`.
- Cost scales with shot count. `MAX_BARS_PER_SHOT=8` on a 3-minute track is a
  very different bill from `MIN_BARS_PER_SHOT=1`.
