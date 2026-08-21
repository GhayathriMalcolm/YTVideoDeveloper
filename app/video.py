import subprocess
from pathlib import Path
from typing import List, Dict

from . import config


def _parse_timestamp(ts: str) -> float:
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def _get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            config.FFPROBE_PATH,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def assemble_video(
    image_paths: List[Path],
    timestamps: List[str],
    audio_path: Path,
    output_path: Path,
) -> Path:
    """Builds an MP4 by timing each image to its timestamp range and muxing in
    the narration audio. image_paths[i] is shown starting at timestamps[i]."""
    if len(image_paths) != len(timestamps):
        raise ValueError("image_paths and timestamps must be the same length")
    if not image_paths:
        raise ValueError("No images to assemble")

    audio_duration = _get_audio_duration(audio_path)
    starts = [_parse_timestamp(ts) for ts in timestamps]

    durations = []
    for i in range(len(starts)):
        if i + 1 < len(starts):
            durations.append(max(starts[i + 1] - starts[i], 0.1))
        else:
            durations.append(max(audio_duration - starts[i], 0.1))

    concat_file = output_path.parent / "_concat.txt"
    lines = ["ffconcat version 1.0"]
    for img, dur in zip(image_paths, durations):
        posix_path = img.resolve().as_posix()
        lines.append(f"file '{posix_path}'")
        lines.append(f"duration {dur:.3f}")
    lines.append(f"file '{image_paths[-1].resolve().as_posix()}'")
    concat_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        config.FFMPEG_PATH,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-i", str(audio_path),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-r", "30",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    concat_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-4000:]}")
    return output_path
