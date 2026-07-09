"""
Lazy Faster Whisper wrapper for local command recognition.

Importing this module must be cheap. The model is loaded only when the first
transcription is requested, which keeps the main UI/Gemini startup responsive.
"""

from functools import lru_cache
from pathlib import Path
from typing import Iterable


@lru_cache(maxsize=1)
def get_whisper_model():
    try:
        from faster_whisper import WhisperModel
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install requirements.txt before "
            "using local speech recognition."
        ) from exc

    return WhisperModel(
        "base",
        device="cpu",
        compute_type="int8",
    )


def transcribe_file(path: str | Path) -> str:
    segments, _ = get_whisper_model().transcribe(str(path), vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe_segments(path: str | Path) -> Iterable[str]:
    segments, _ = get_whisper_model().transcribe(str(path), vad_filter=True)
    for segment in segments:
        text = segment.text.strip()
        if text:
            yield text
