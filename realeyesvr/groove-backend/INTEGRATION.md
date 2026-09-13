# Groove private prototype

The finished vanilla Groove/lava interface lives at `../website/groove/`.
This directory contains the isolated Python pipeline and its FastAPI adapter.

## Local run

Install the Python requirements plus the system `ffmpeg` and `ffprobe`
executables, then start from this directory:

```bash
PYTHONPATH=.:src uvicorn api:app --reload --port 8000
```

Open `http://localhost:8000/groove/`. The API serves the UI in local mode.
For a separately hosted API, set `window.GROOVE_API_BASE` in
`website/groove/config.js` to its HTTPS origin and include the website origin
in `GROOVE_ALLOWED_ORIGINS`.

## Configuration

- `GROOVE_DATA_ROOT`: server-owned project data directory (default `data/`).
- `GROOVE_MAX_UPLOAD_BYTES`: maximum audio upload (default 100 MiB).
- `GROOVE_ALLOWED_ORIGINS`: comma-separated browser origins.
- `RUNWAYML_API_SECRET`: server-side provider credential.
- Existing pipeline variables in `.env.example` remain supported.

Every project uses a UUID directory. Pipeline stages run in subprocesses with
that directory as `GROOVE_PROJECT_ROOT`, so uploaded audio, analysis, plans,
approval sheets, clips, and renders do not share mutable paths.

Runway generation is disabled until the user has rendered an animatic,
selected approved shots, and confirmed the paid action. The backend writes the
pipeline's approval sheet and invokes `generate` without `--force`.

This remains a private prototype: local disk is not durable cloud storage,
background threads do not survive restarts, and authentication/quotas are not
implemented. Do not expose it publicly until those controls are added.
