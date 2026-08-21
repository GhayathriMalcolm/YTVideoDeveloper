import re
import shutil
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, transcription, updater, video
from .state import Project
from .version import __version__

app = FastAPI(title="YT Video Developer")


class TopicRequest(BaseModel):
    topic: str


class NextRequest(BaseModel):
    pass


def _project_or_404(slug: str) -> Project:
    try:
        return Project.load(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")


@app.get("/api/projects")
def list_projects():
    projects = []
    for slug in Project.list_all():
        state = Project(slug).read()
        projects.append(
            {
                "slug": slug,
                "topic": state.get("topic"),
                "title": state.get("title"),
                "status": state.get("status"),
            }
        )
    return projects


@app.post("/api/projects")
def create_project(req: TopicRequest):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Topic is required")

    project = Project.create(req.topic)
    try:
        result = llm.generate_script(req.topic)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Script generation failed: {exc}")

    filename = f"script_{project.slug}.txt"
    project.write_text_file(filename, result["script"])
    state = project.save(
        {
            "title": result["title"],
            "script": result["script"],
            "script_file": filename,
            "status": "script_ready",
        }
    )
    return state


@app.get("/api/projects/{slug}")
def get_project(slug: str):
    return _project_or_404(slug).read()


@app.get("/api/projects/{slug}/download/{filename}")
def download_file(slug: str, filename: str):
    project = _project_or_404(slug)
    file_path = project.path(filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)


@app.post("/api/projects/{slug}/audio")
async def upload_audio(slug: str, file: UploadFile = File(...)):
    project = _project_or_404(slug)
    audio_path = project.path("narration" + Path(file.filename).suffix or ".mp3")
    with audio_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        lines = transcription.transcribe(audio_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")

    transcript_text = transcription.lines_to_text(lines)
    transcript_filename = f"transcript_{slug}.txt"
    project.write_text_file(transcript_filename, transcript_text)

    state = project.save(
        {
            "audio_file": audio_path.name,
            "timestamped_lines": lines,
            "transcript_file": transcript_filename,
            "status": "transcript_ready",
        }
    )
    return state


@app.post("/api/projects/{slug}/image-prompts")
def create_image_prompts(slug: str):
    project = _project_or_404(slug)
    state = project.read()
    lines = state.get("timestamped_lines")
    if not lines:
        raise HTTPException(status_code=400, detail="No transcript found yet")

    try:
        prompts = llm.generate_image_prompts(lines)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image prompt generation failed: {exc}")

    combined = "\n\n".join(p["prompt"] for p in prompts)
    prompts_filename = f"image_prompts_{slug}.txt"
    project.write_text_file(prompts_filename, combined)

    state = project.save(
        {
            "image_prompts": prompts,
            "image_prompts_file": prompts_filename,
            "status": "prompts_ready",
        }
    )
    return state


def _natural_sort_key(filename: str):
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", filename)]


def _timestamp_filename(timestamp: str, ext: str, used_names: set) -> str:
    # Colons aren't valid in Windows filenames, so "00:11" becomes "[00-11]".
    base = f"[{timestamp.replace(':', '-')}]"
    name = f"{base}{ext}"
    if name not in used_names:
        used_names.add(name)
        return name
    # Two lines can round to the same second; disambiguate rather than overwrite.
    suffix = 2
    while f"{base}_{suffix}{ext}" in used_names:
        suffix += 1
    name = f"{base}_{suffix}{ext}"
    used_names.add(name)
    return name


@app.post("/api/projects/{slug}/images/upload")
async def upload_images(slug: str, files: List[UploadFile] = File(...)):
    project = _project_or_404(slug)
    state = project.read()
    prompts = state.get("image_prompts")
    if not prompts:
        raise HTTPException(status_code=400, detail="No image prompts found yet")

    if len(files) != len(prompts):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Expected {len(prompts)} images (one per timestamp) but received "
                f"{len(files)}. Select exactly one image per prompt, generated in "
                "order, then upload again."
            ),
        )

    sorted_files = sorted(files, key=lambda f: _natural_sort_key(f.filename or ""))

    images_dir = project.path("images")
    images_dir.mkdir(exist_ok=True)
    for old_file in images_dir.glob("*"):
        old_file.unlink()

    results = []
    used_names: set = set()
    for prompt_obj, upload in zip(prompts, sorted_files):
        ext = Path(upload.filename or "").suffix or ".png"
        filename = _timestamp_filename(prompt_obj["timestamp"], ext, used_names)
        out_path = images_dir / filename
        with out_path.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        results.append({"timestamp": prompt_obj["timestamp"], "file": filename})

    state = project.save({"images": results, "image_errors": [], "status": "images_ready"})
    return state


@app.post("/api/projects/{slug}/assemble")
def assemble(slug: str):
    project = _project_or_404(slug)
    state = project.read()
    images = state.get("images")
    audio_file = state.get("audio_file")
    if not images or any(img is None for img in images):
        raise HTTPException(status_code=400, detail="Images are not fully generated yet")
    if not audio_file:
        raise HTTPException(status_code=400, detail="No narration audio uploaded yet")

    image_paths = [project.path("images", img["file"]) for img in images]
    timestamps = [img["timestamp"] for img in images]
    audio_path = project.path(audio_file)
    output_filename = f"final_{slug}.mp4"
    output_path = project.path(output_filename)

    try:
        video.assemble_video(image_paths, timestamps, audio_path, output_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Video assembly failed: {exc}")

    state = project.save({"video_file": output_filename, "status": "video_ready"})
    return state


@app.post("/api/projects/{slug}/metadata")
def metadata(slug: str):
    project = _project_or_404(slug)
    state = project.read()
    script = state.get("script")
    topic = state.get("topic")
    if not script:
        raise HTTPException(status_code=400, detail="No script found yet")

    try:
        data = llm.generate_metadata(topic, script)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Metadata generation failed: {exc}")

    state = project.save(
        {
            "titles": data.get("titles", []),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
            "status": "complete",
        }
    )
    return state


@app.get("/files/{slug}/{path:path}")
def serve_project_file(slug: str, path: str):
    project = _project_or_404(slug)
    file_path = project.path(*path.split("/"))
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.get("/api/health")
def health():
    return JSONResponse({"ok": True})


@app.get("/api/version")
def version():
    update = updater.check_for_update()
    return {
        "version": __version__,
        "update_available": update is not None,
        "latest_version": update[1] if update else None,
        "download_url": update[0] if update else None,
    }


if config.WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")
