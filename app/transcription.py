import re
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


def transcribe(audio_path: Path) -> List[Dict[str, str]]:
    """Runs local Whisper transcription and groups words into sentence-level
    timestamped lines, one new timestamp per sentence/idea boundary."""
    model = _get_model()
    segments, _info = model.transcribe(str(audio_path), word_timestamps=True)

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

    return lines


def lines_to_text(lines: List[Dict[str, str]]) -> str:
    return "\n\n".join(f"[{ln['timestamp']}] {ln['text']}" for ln in lines)
