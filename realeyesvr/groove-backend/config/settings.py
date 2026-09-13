"""Env-driven defaults and path constants. No secrets in this file."""
import os
from pathlib import Path

from dotenv import load_dotenv

CODE_ROOT = Path(__file__).resolve().parents[1]
# The web service gives every upload its own project root. Keeping code assets
# separate from mutable project data prevents concurrent jobs from sharing
# audio, plans, clips, or renders.
PROJECT_ROOT = Path(os.getenv("GROOVE_PROJECT_ROOT", CODE_ROOT)).resolve()
load_dotenv(CODE_ROOT / ".env")

# --- Runway ---------------------------------------------------------------
API_SECRET = os.getenv("RUNWAYML_API_SECRET")
MODEL = os.getenv("RUNWAY_MODEL", "gen4.5")
RATIO = os.getenv("RUNWAY_RATIO", "1280:720")

# Durations the model will accept. The planner picks the smallest one that
# covers a shot's slot, then the assembler trims down to the exact frame.
# VERIFY against the API reference for your chosen model before a big batch.
ALLOWED_DURATIONS = [
    int(d) for d in os.getenv("RUNWAY_DURATIONS", "2,3,4,5,6,7,8,9,10").split(",") if d.strip()
]

# How a generated clip is made to fill its bar-length slot:
#   retime -- buy the nearest allowed length, then speed/slow to fit exactly.
#             Keeps the whole shot. BPM sets the target length.
#   trim   -- buy the next length up and cut the tail off.
FIT_MODE = os.getenv("FIT_MODE", "retime").strip().lower()
# Refuse to retime beyond this factor; fall back to trimming instead.
MAX_RETIME = float(os.getenv("MAX_RETIME", "1.35"))
# A "hold" is deliberately one generation stretched over a whole section, so it
# needs a far looser cap -- the resulting slow motion is the intended look.
HOLD_MAX_RETIME = float(os.getenv("HOLD_MAX_RETIME", "4.0"))

# Measure each clip's actual motion and mirror it when it contradicts the
# board's screen direction. Cheap, exact, and more reliable than prompting.
ENFORCE_DIRECTION = os.getenv("ENFORCE_DIRECTION", "true").lower() != "false"

# --- Render ---------------------------------------------------------------
FPS = int(os.getenv("RENDER_FPS", "24"))
WIDTH, HEIGHT = (int(x) for x in os.getenv("RENDER_SIZE", "1280x720").split("x"))
FONT_FILE = os.getenv(
    "ANIMATIC_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
)

# --- Shot planning --------------------------------------------------------
BEATS_PER_BAR = int(os.getenv("BEATS_PER_BAR", "4"))
# A shot lasts a whole number of bars, clamped to this range.
MIN_BARS = int(os.getenv("MIN_BARS_PER_SHOT", "2"))
MAX_BARS = int(os.getenv("MAX_BARS_PER_SHOT", "4"))

# --- Paths ----------------------------------------------------------------
AUDIO_DIR = PROJECT_ROOT / "audio"
ANALYSIS_DIR = PROJECT_ROOT / "output" / "analysis"
SHOTLIST_DIR = PROJECT_ROOT / "output" / "shotlists"
CLIP_DIR = PROJECT_ROOT / "output" / "clips"
RENDER_DIR = PROJECT_ROOT / "output" / "renders"
PROMPTS_DIR = CODE_ROOT / "prompts"
RUNS_CSV = PROJECT_ROOT / "output" / "runs.csv"


def require_api_secret() -> str:
    if not API_SECRET:
        raise RuntimeError(
            "RUNWAYML_API_SECRET is not set. Copy .env.example to .env and fill it in."
        )
    return API_SECRET
