# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Install dependencies (Python 3.12, Windows):
```bash
pip install -r requirements.txt
```

Run in dev mode (plain console, hot-editable):
```bash
python run.py
```
Starts FastAPI/uvicorn on `http://127.0.0.1:8000` and opens a browser tab. No test suite or linter is configured in this project.

Build the standalone Windows app (PyInstaller, windowed/no-console, bundles FFmpeg):
```bash
.\.venv\Scripts\python.exe -m PyInstaller run.py --name "YTVideoDeveloper" --onedir --windowed --icon "assets\app_icon.ico" --add-data "web;web" --add-data "vendor\ffmpeg\ffmpeg.exe;vendor\ffmpeg" --add-data "vendor\ffmpeg\ffprobe.exe;vendor\ffmpeg" --collect-all faster_whisper --collect-all ctranslate2 --collect-all onnxruntime --collect-all tokenizers --collect-all huggingface_hub --collect-all pystray --hidden-import PIL._tkinter_finder --noconfirm
```
`vendor/ffmpeg/{ffmpeg,ffprobe}.exe` must exist locally first (copied from a real FFmpeg install; gitignored, not committed - exceeds GitHub's 100MB file limit).

Build the installer (after the PyInstaller build above):
```bash
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
```
Produces `installer_output\YTVideoDeveloper-Setup-<version>.exe`.

**Release checklist** for shipping a new version: bump `__version__` in `app/version.py` *and* `MyAppVersion` in `installer.iss` (must match) -> rebuild PyInstaller bundle -> recompile installer -> commit/push -> publish a GitHub release tagged `vX.Y.Z` with the new installer `.exe` attached as a release asset (use the dedicated binary-attachment drop zone on the release page, not the description textbox - that one rejects `.exe`).

## Architecture

This is a FastAPI backend + vanilla JS/HTML frontend (`web/`) that automates a YouTube video content pipeline, run either as a local dev server (`python run.py`) or packaged as a standalone Windows desktop app (PyInstaller + Inno Setup installer). The dual-mode nature (dev script vs. frozen app) is the main thing to keep in mind when touching `app/config.py` or `run.py`.

**Pipeline stages** (each is one FastAPI endpoint in `app/main.py`, called in sequence by the frontend wizard in `web/app.js`), state persisted per-project as `projects/<slug>/state.json` via `app/state.py`:

1. `POST /api/projects` - `app/llm.py` calls Claude to write a narration script from a topic, per strict rules baked into the system prompt (word count, rhythm, hook/echo structure).
2. `POST /api/projects/{slug}/audio` - user uploads their own voiceover recording (recorded externally - no TTS API is used); `app/transcription.py` runs local `faster-whisper`, converting word-level timestamps into sentence-level timestamped lines.
3. `POST /api/projects/{slug}/image-prompts` - `app/llm.py` turns each transcript line into a detailed doodle-style image prompt. **Important**: this is chunked (`IMAGE_PROMPT_CHUNK_SIZE = 35` lines/call) rather than one big Claude call, because a single-call response for long scripts (100+ lines) reliably hit `max_tokens` and produced truncated/invalid JSON - chunking with prior-scene context passed forward keeps each call small while preserving the "hold scene across consecutive timestamps" continuity rule.
4. `POST /api/projects/{slug}/images/upload` - user generates images externally in Google Flow (no public API exists for it, so this stays manual by design) and bulk-uploads them. Files are sorted by natural filename order (`_natural_sort_key`) and mapped 1:1 to prompts in chronological order, then saved as `[MM-SS].png` (bracketed, colon-to-dash) so filenames self-document which prompt/timestamp they match.
5. `POST /api/projects/{slug}/assemble` - `app/video.py` shells out to FFmpeg, building an ffconcat timeline (each image's duration = time until the next timestamp) and muxing in the narration audio to produce the final MP4.
6. `POST /api/projects/{slug}/metadata` - Claude generates YouTube titles/description/tags from the topic + script.

**Frontend wizard gating** (`web/app.js`): steps unlock based on `state.status`. The `STEP_REQUIREMENT` map pairs each "shows completed output" step with the "next action" step it unlocks, at the *same* status rank (e.g. once a script exists, both viewing it and starting the audio upload become active together) - this pairing must stay consistent across every step or a step silently locks itself out (this exact bug happened once: `step-images` required a status that could only be reached *after* uploading images).

**Frozen vs. dev path resolution** (`app/config.py`): when packaged (`sys.frozen`), `APP_DIR` (read-only bundled assets: `web/`, `vendor/ffmpeg/`) is PyInstaller's extraction dir, while `DATA_DIR` (writable: `.env`, `projects/`) is `%LOCALAPPDATA%\YTVideoDeveloper` - deliberately separate from wherever the program binary is installed, so uninstalling/reinstalling the program never touches user projects or the saved API key. In dev mode both are just the repo root. FFmpeg path resolution priority: explicit `.env` override -> bundled copy in `vendor/ffmpeg/` -> system PATH.

**Packaged-app runtime quirks** (`run.py`): a `--windowed` PyInstaller build has `sys.stdout`/`sys.stderr` as `None` (no real console); several dependencies call `warnings.warn()`/`print()` at import time and crash with `AttributeError` unless stdio is redirected to a log file *before* any other imports happen - this redirect is the very first thing in `run.py`, ahead of the `uvicorn`/`app.main` imports. The frozen app also does a single-instance check (probe port 8000 before binding; if already open, just re-open the browser and exit) and runs a `pystray` tray icon whose Quit handler sets `uvicorn.Server.should_exit = True` and joins the server thread for a clean shutdown - this is the actual mechanism behind "close properly every time."

**Update checking** (`app/updater.py`, `app/version.py`): the app calls GitHub's public releases API for `UPDATE_REPO` on every startup (via `GET /api/version`) and shows a banner if `__version__` is behind the latest published tag. Fails silently on any network error by design - an update check must never block startup.
