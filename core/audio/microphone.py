"""
Microphone capture service for Gemini Live audio.

The service owns sounddevice input streams and forwards PCM chunks to an async
queue only when the assistant is allowed to listen.
"""

import asyncio
from typing import Callable

from core.audio.diagnostics import AudioDiagnostics


class Microphone:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = "int16",
        chunk_size: int = 1024,
        device: int | None = None,
        diagnostics: AudioDiagnostics | None = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.chunk_size = chunk_size
        self.device = device
        self.diagnostics = diagnostics

    def should_capture(self, is_speaking: bool, is_muted: bool) -> bool:
        return not is_speaking and not is_muted

    async def stream_to_queue(
        self,
        output_queue: asyncio.Queue,
        is_speaking: Callable[[], bool],
        is_muted: Callable[[], bool],
    ):
        try:
            import sounddevice as sd
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "sounddevice is not installed. Install requirements.txt before "
                "using microphone capture."
            ) from exc

        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if self.should_capture(is_speaking(), is_muted()):
                payload = indata.tobytes()
                if self.diagnostics:
                    self.diagnostics.record_input(payload)
                loop.call_soon_threadsafe(
                    output_queue.put_nowait,
                    {"data": payload, "mime_type": "audio/pcm"},
                )

        stream_kwargs = {
            "samplerate": self.sample_rate,
            "channels": self.channels,
            "dtype": self.dtype,
            "blocksize": self.chunk_size,
            "callback": callback,
        }
        if self.device is not None:
            stream_kwargs["device"] = self.device

        if self.diagnostics:
            self.diagnostics.configure_input(self.sample_rate, self.device, self.chunk_size)
            self.diagnostics.update(mic_active=True, stt_status="LISTENING", last_error="")
        try:
            with sd.InputStream(**stream_kwargs):
                while True:
                    await asyncio.sleep(0.1)
        except Exception as exc:
            if self.diagnostics:
                self.diagnostics.update(mic_active=False, stt_status="ERROR", last_error=str(exc))
            raise
        finally:
            if self.diagnostics:
                self.diagnostics.update(mic_active=False)
