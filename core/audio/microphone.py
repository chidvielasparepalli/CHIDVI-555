"""
Microphone capture service for Gemini Live audio.

The service owns sounddevice input streams and forwards PCM chunks to an async
queue only when the assistant is allowed to listen.
"""

import asyncio
from typing import Callable


class Microphone:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = "int16",
        chunk_size: int = 1024,
        device: int | None = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.chunk_size = chunk_size
        self.device = device

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
                loop.call_soon_threadsafe(
                    output_queue.put_nowait,
                    {"data": indata.tobytes(), "mime_type": "audio/pcm"},
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

        with sd.InputStream(**stream_kwargs):
            while True:
                await asyncio.sleep(0.1)
