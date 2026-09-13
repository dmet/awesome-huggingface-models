"""Private Groove prototype API.

Each project is processed by a separate CLI subprocess with its own
GROOVE_PROJECT_ROOT. This keeps the inherited path-based pipeline isolated
without weakening its explicit approval gate.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parents[1]
WEB_ROOT = REPO_ROOT / "realeyesvr" / "website" / "groove"
DATA_ROOT = Path(os.getenv("GROOVE_DATA_ROOT", BACKEND_ROOT / "data")).resolve()
MAX_UPLOAD_BYTES = int(os.getenv("GROOVE_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
ALLOWED_AUDIO = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
STYLE_FILES = {
    "Desert": "desert_treatment.json",
    "Dreamlike": "lyric_style.json",
    "Neon": "sketch_treatment.json",
    "Cinematic": "example_style.json",
}
APPROVAL_COLUMNS = [
    "shot", "slate", "approve", "start_s", "end_s", "slot_s",
    "gen_duration_s", "section", "size", "movement", "direction",
    "lens", "pov", "from_board", "lyric", "action", "prompt",
]

app = FastAPI(title="Groove private prototype", version="0.1.0")
origins = [x.strip() for x in os.getenv(
    "GROOVE_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
).split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


class ShotEdit(BaseModel):
    shot: int
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    prompt: str = Field(min_length=1, max_length=1000)


class StoryboardUpdate(BaseModel):
    shots: list[ShotEdit]


class ApprovedShot(BaseModel):
    shot: int
    approved: bool = False
    prompt: str = Field(min_length=1, max_length=1000)


class GenerationRequest(BaseModel):
    shots: list[ApprovedShot]


def project_root(project_id: str) -> Path:
    try:
        parsed = uuid.UUID(project_id)
    except ValueError as exc:
        raise HTTPException(404, "Project not found") from exc
    root = DATA_ROOT / str(parsed)
    if not root.is_dir():
        raise HTTPException(404, "Project not found")
    return root


def metadata(root: Path) -> dict:
    path = root / "project.json"
    if not path.exists():
        raise HTTPException(404, "Project metadata not found")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    tmp.replace(path)


def run_cli(root: Path, *args: str) -> None:
    env = os.environ.copy()
    env["GROOVE_PROJECT_ROOT"] = str(root)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(BACKEND_ROOT), str(BACKEND_ROOT / "src"), env.get("PYTHONPATH", "")]
    )
    result = subprocess.run(
        [sys.executable, "-m", "musicvideo.cli", *args], cwd=BACKEND_ROOT,
        env=env, capture_output=True, text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "Pipeline failed")[-3000:]
        raise RuntimeError(detail)


def payload(root: Path) -> dict:
    meta = metadata(root)
    song = meta["song"]
    analysis_path = root / "output" / "analysis" / f"{song}.json"
    plan_path = root / "output" / "shotlists" / f"{song}.json"
    status_path = root / "generation.json"
    return {
        **meta,
        "analysis": json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path.exists() else None,
        "storyboard": json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None,
        "generation": json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else None,
        "animatic_url": f"/api/groove/projects/{meta['id']}/animatic" if (root / "output" / "renders" / f"{song}_animatic.mp4").exists() else None,
        "final_url": f"/api/groove/projects/{meta['id']}/final" if (root / "output" / "renders" / f"{song}_final.mp4").exists() else None,
    }


@app.get("/api/groove/health")
def health() -> dict:
    return {"ok": True, "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe"))}


@app.post("/api/groove/projects")
async def create_project(
    audio: Annotated[UploadFile, File()],
    style: Annotated[Literal["Desert", "Dreamlike", "Neon", "Cinematic"], Form()],
) -> dict:
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(415, "Use MP3, WAV, FLAC, M4A, or OGG audio")
    project_id = str(uuid.uuid4())
    root = DATA_ROOT / project_id
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True)
    song = "track"
    audio_path = audio_dir / f"{song}{suffix}"
    size = 0
    try:
        with audio_path.open("wb") as target:
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Audio upload exceeds the configured limit")
                target.write(chunk)
        meta = {"id": project_id, "song": song, "filename": audio.filename, "style": style}
        write_json(root / "project.json", meta)
        run_cli(root, "analyze", str(audio_path))
        style_path = BACKEND_ROOT / "prompts" / STYLE_FILES[style]
        run_cli(root, "plan", song, "--style", str(style_path), "--no-lyrics")
        return payload(root)
    except HTTPException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(500, f"Audio analysis failed: {exc}") from exc


@app.get("/api/groove/projects/{project_id}")
def get_project(project_id: str) -> dict:
    return payload(project_root(project_id))


@app.put("/api/groove/projects/{project_id}/storyboard")
def update_storyboard(project_id: str, update: StoryboardUpdate) -> dict:
    root = project_root(project_id)
    meta = metadata(root)
    path = root / "output" / "shotlists" / f"{meta['song']}.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    if len(update.shots) != len(plan["shots"]):
        raise HTTPException(400, "Every storyboard shot must be included")
    edits = sorted(update.shots, key=lambda item: item.shot)
    if [x.shot for x in edits] != list(range(len(plan["shots"]))):
        raise HTTPException(400, "Shot numbers must be complete and unique")
    duration = float(plan["duration_s"])
    for index, edit in enumerate(edits):
        expected_start = 0.0 if index == 0 else edits[index - 1].end_s
        if abs(edit.start_s - expected_start) > 0.01 or edit.end_s <= edit.start_s:
            raise HTTPException(400, "Shot timings must be positive and contiguous")
    if abs(edits[-1].end_s - duration) > 0.01:
        raise HTTPException(400, "The storyboard must cover the complete track")
    for shot, edit in zip(plan["shots"], edits):
        shot["start_s"], shot["end_s"] = round(edit.start_s, 3), round(edit.end_s, 3)
        shot["slot_s"] = round(edit.end_s - edit.start_s, 3)
        allowed = [int(value) for value in os.getenv("RUNWAY_DURATIONS", "2,3,4,5,6,7,8,9,10").split(",")]
        shot["gen_duration_s"] = next(
            (duration for duration in allowed if duration >= shot["slot_s"]), allowed[-1]
        )
        shot["prompt"] = edit.prompt.strip()
    write_json(path, plan)
    return payload(root)


@app.post("/api/groove/projects/{project_id}/animatic")
def render_animatic(project_id: str) -> dict:
    root = project_root(project_id)
    try:
        run_cli(root, "animatic", metadata(root)["song"])
    except Exception as exc:
        raise HTTPException(500, f"Animatic render failed: {exc}") from exc
    return payload(root)


def write_approval(root: Path, request: GenerationRequest) -> int:
    meta = metadata(root)
    song = meta["song"]
    plan_path = root / "output" / "shotlists" / f"{song}.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    decisions = {item.shot: item for item in request.shots}
    if set(decisions) != {shot["shot"] for shot in plan["shots"]}:
        raise HTTPException(400, "Approval decisions are required for every shot")
    sheet = root / "output" / "shotlists" / f"{song}.approval.csv"
    with sheet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=APPROVAL_COLUMNS)
        writer.writeheader()
        for shot in plan["shots"]:
            item = decisions[shot["shot"]]
            writer.writerow({
                "shot": shot["shot"], "slate": shot.get("slate", ""),
                "approve": "yes" if item.approved else "no",
                "start_s": shot["start_s"], "end_s": shot["end_s"],
                "slot_s": shot["slot_s"], "gen_duration_s": shot["gen_duration_s"],
                "section": shot["label"], "size": shot.get("size", ""),
                "movement": shot.get("movement", ""), "direction": shot.get("direction", ""),
                "lens": shot.get("lens", ""), "pov": shot.get("pov", ""),
                "from_board": "yes" if shot.get("from_board") else "no",
                "lyric": shot.get("lyric", ""), "action": shot.get("action", ""),
                "prompt": item.prompt.strip(),
            })
    return sum(item.approved for item in request.shots)


def generation_worker(root: Path) -> None:
    state_path = root / "generation.json"
    try:
        run_cli(root, "generate", metadata(root)["song"])
        write_json(state_path, {"status": "rendering", "message": "Assembling approved Runway clips"})
        run_cli(root, "render", metadata(root)["song"])
        write_json(state_path, {"status": "complete", "message": "Final video is ready"})
    except Exception as exc:
        write_json(state_path, {"status": "failed", "message": str(exc)[-2000:]})


@app.post("/api/groove/projects/{project_id}/generate", status_code=202)
def generate(project_id: str, request: GenerationRequest) -> dict:
    root = project_root(project_id)
    state_path = root / "generation.json"
    if state_path.exists() and json.loads(state_path.read_text())["status"] in {"queued", "generating", "rendering"}:
        raise HTTPException(409, "Generation is already running")
    count = write_approval(root, request)
    if not count:
        raise HTTPException(400, "Approve at least one shot before paid generation")
    write_json(state_path, {"status": "generating", "message": f"Generating {count} approved shots with Runway"})
    thread = threading.Thread(target=generation_worker, args=(root,), daemon=True)
    thread.start()
    return payload(root)


def video_response(project_id: str, suffix: str) -> FileResponse:
    root = project_root(project_id)
    song = metadata(root)["song"]
    path = root / "output" / "renders" / f"{song}_{suffix}.mp4"
    if not path.exists():
        raise HTTPException(404, "Video is not ready")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/api/groove/projects/{project_id}/animatic")
def animatic_file(project_id: str) -> FileResponse:
    return video_response(project_id, "animatic")


@app.get("/api/groove/projects/{project_id}/final")
def final_file(project_id: str) -> FileResponse:
    return video_response(project_id, "final")


if WEB_ROOT.exists():
    app.mount("/groove", StaticFiles(directory=WEB_ROOT, html=True), name="groove")
