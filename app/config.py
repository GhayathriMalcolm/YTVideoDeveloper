import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    # Bundled read-only assets (e.g. web/) live in PyInstaller's extraction dir.
    APP_DIR = Path(sys._MEIPASS)
    # User data (.env, projects/) lives in %LOCALAPPDATA%, separate from wherever
    # the program itself is installed - so uninstalling/upgrading the program
    # never risks the user's projects.
    DATA_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "YTVideoDeveloper"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = APP_DIR

BASE_DIR = DATA_DIR
load_dotenv(DATA_DIR / ".env")

PROJECTS_DIR = DATA_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)

WEB_DIR = APP_DIR / "web"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")

# Bundled copy travels with the app, so it works on any machine without the
# user needing FFmpeg installed or on PATH. Priority: explicit .env override,
# then the bundled copy, then whatever's on the system PATH.
_BUNDLED_FFMPEG = APP_DIR / "vendor" / "ffmpeg" / "ffmpeg.exe"
_BUNDLED_FFPROBE = APP_DIR / "vendor" / "ffmpeg" / "ffprobe.exe"

FFMPEG_PATH = (
    os.getenv("FFMPEG_PATH")
    or (str(_BUNDLED_FFMPEG) if _BUNDLED_FFMPEG.exists() else None)
    or shutil.which("ffmpeg")
    or "ffmpeg"
)
FFPROBE_PATH = (
    os.getenv("FFPROBE_PATH")
    or (str(_BUNDLED_FFPROBE) if _BUNDLED_FFPROBE.exists() else None)
    or shutil.which("ffprobe")
    or "ffprobe"
)
