"""
Local speech command recognizer.

This module is intentionally small: it combines Faster Whisper transcription
with the canonical command router parser. It can be used by microphone code to
detect local commands before forwarding normal conversation to Gemini.
"""

from dataclasses import dataclass
from pathlib import Path

from commands.router import Command, CommandType, get_command_router
from core.speech.whisper_engine import transcribe_file


@dataclass
class RecognitionResult:
    text: str
    command: Command

    @property
    def is_local_command(self) -> bool:
        return self.command.type == CommandType.LOCAL


class LocalCommandRecognizer:
    def __init__(self):
        self._router = get_command_router()

    def recognize_file(self, path: str | Path) -> RecognitionResult:
        text = transcribe_file(path)
        command = self._router.parse(text) if text else self._router.parse("")
        return RecognitionResult(text=text, command=command)
