# scripts/ — live API probes and the board page builder

Everything here was written while working out whether Runway could carry a
storyboard. The probes **spend credits**; the builders do not.

Run them from the repo root with the venv active. All paths are derived from the
repo, so nothing needs editing first.

## Probes (these cost money)

| Script | Spends | What it establishes |
|---|---|---|
| `probe_reference_images.py` | 15 cr | `gen4_image` reference images + `@tag` in prompt text hold a character and a location across new framings |
| `probe_reference_face.py` | 5 cr | The same identity survives a new seed, angle, and lighting — with the face actually visible |
| `probe_aleph2_keyframes.py` | 196 cr | `aleph2` video-to-video preserves a source cut to the exact frame, and keyframe content bleeds across shot boundaries |
| `gen_sheet_panels.py` | 13 cr | The 1080×1920 crane plate and the second panel of the carried-over tracking shot |

`probe_aleph2_keyframes.py` is the expensive one — 196 credits for 7 seconds.
Read the numbers in the root README before running it again.

## Builders (free)

| Script | Produces |
|---|---|
| `build_previewer.py` | `output/renders/sheet2_previewer.mp4` — panels cut to the measured shot extents with the real track. Undrawn shots and coverage holes play as slates, so it never flatters the state of the work. The C-A crane is a real ffmpeg crop path over the tall plate. |
| `build_board.py` | `output/build/board.html` — the storyboard sheet, with `board_tpl.html` as its template |

`build_board.py` needs `output/build/img/*.jpg` (web-sized copies of the panels)
and `output/build/prev_web.mp4` (a downscaled previewer for embedding). Both are
gitignored build intermediates; make them with:

```bash
for n in A_man B_desert C_composed D_face G_follow; do
  ffmpeg -y -i "output/panels/test/$n.png" -vf scale=720:-1 -q:v 6 "output/build/img/$n.jpg"
done
ffmpeg -y -i output/panels/test/F_tall.png -vf scale=440:-1 -q:v 6 output/build/img/F_tall.jpg
ffmpeg -y -i output/renders/sheet2_previewer.mp4 -vf scale=960:540 \
  -c:v libx264 -crf 27 -preset slow -c:a aac -b:a 112k output/build/prev_web.mp4
```

## Provenance

`output/panels/test/runlog.json` and `runlog2.json` record the seed, task id,
ratio and exact prompt behind every panel in the repo, so any of them can be
regenerated or varied deliberately rather than by accident.
