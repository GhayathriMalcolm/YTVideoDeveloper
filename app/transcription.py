import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict

from faster_whisper import WhisperModel

from . import config

_model: WhisperModel | None = None

SENTENCE_END_RE = re.compile(r'[.!?]["\')\]]*\s*$')


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(config.WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def _format_timestamp(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _remux_clean_wav(audio_path: Path, dest_path: Path) -> None:
    """Re-encodes audio_path through ffmpeg into a clean mono 16kHz WAV.

    Some recordings (notably chunked browser mic captures saved as .mp3)
    contain a handful of malformed frames partway through. ffmpeg's CLI
    demuxer resyncs past them and decodes the full file, but faster-whisper's
    internal PyAV-based decoder stops dead at the first bad frame - silently
    truncating the transcription. Pre-transcoding with the ffmpeg CLI first
    avoids handing that raw, potentially-corrupt file to Whisper at all.
    """
    subprocess.run(
        [
            config.FFMPEG_PATH,
            "-y",
            "-i", str(audio_path),
            "-ac", "1",
            "-ar", "16000",
            str(dest_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def transcribe(audio_path: Path) -> List[Dict[str, str]]:
    """Runs local Whisper transcription and groups words into sentence-level
    timestamped lines, one new timestamp per sentence/idea boundary."""
    model = _get_model()
    with tempfile.TemporaryDirectory() as tmp_dir:
        clean_wav = Path(tmp_dir) / "clean.wav"
        _remux_clean_wav(audio_path, clean_wav)
        segments, info = model.transcribe(
            str(clean_wav),
            word_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False,
        )

        words = []
        for segment in segments:
            if segment.words:
                words.extend(segment.words)
            else:
                words.append(type("W", (), {"start": segment.start, "word": segment.text})())

    lines: List[Dict[str, str]] = []
    current_words: List[str] = []
    current_start = None

    for w in words:
        token = w.word.strip()
        if not token:
            continue
        if current_start is None:
            current_start = w.start
        current_words.append(token)
        if SENTENCE_END_RE.search(token):
            text = " ".join(current_words).strip()
            text = re.sub(r"\s+([.,!?;:])", r"\1", text)
            lines.append({"timestamp": _format_timestamp(current_start), "text": text})
            current_words = []
            current_start = None

    if current_words:
        text = " ".join(current_words).strip()
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        lines.append({"timestamp": _format_timestamp(current_start or 0.0), "text": text})

    last_word_end = words[-1].end if words and hasattr(words[-1], "end") else 0.0
    if info.duration > 30 and last_word_end < info.duration * 0.9:
        raise RuntimeError(
            f"Transcription stopped early at {_format_timestamp(last_word_end)} but the "
            f"audio is {_format_timestamp(info.duration)} long. This usually means Whisper "
            "hit a hallucination loop partway through - try re-uploading the audio."
        )

    return lines


def lines_to_text(lines: List[Dict[str, str]]) -> str:
    return "\n\n".join(f"[{ln['timestamp']}] {ln['text']}" for ln in lines)
