"""
Microphone capture service for Gemini Live audio.

The service owns sounddevice input streams and forwards PCM chunks to an async
queue only when the assistant is allowed to listen.
"""

import asyncio
import time
import logging
from typing import Callable

from core.audio.diagnostics import AudioDiagnostics

logger = logging.getLogger("MIC")


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
        self._callback_count = 0
        self._last_callback_time: float = 0.0

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

        def enqueue_capture(payload: bytes) -> None:
            try:
                output_queue.put_nowait({"data": payload, "mime_type": "audio/pcm"})
                logger.debug("QUEUE PUSH %d bytes", len(payload))
            except asyncio.QueueFull:
                if self.diagnostics:
                    self.diagnostics.update(last_error="Input queue full: dropped audio block")
                logger.warning("QUEUE FULL - dropped audio block")

        def callback(indata, frames, time_info, status):
            if status:
                logger.warning("MIC CALLBACK STATUS: %s", status)
            self._callback_count += 1
            self._last_callback_time = time.monotonic()
            if self.should_capture(is_speaking(), is_muted()):
                payload = indata.tobytes()
                if self.diagnostics:
                    self.diagnostics.record_input(payload)
                loop.call_soon_threadsafe(enqueue_capture, payload)
                if self._callback_count % 200 == 1:
                    logger.info("MIC CALLBACK #%d - captured %d bytes", self._callback_count, len(payload))
            else:
                if self._callback_count % 500 == 1:
                    logger.debug("MIC CALLBACK #%d - skipped (speaking=%s muted=%s)",
                                 self._callback_count, is_speaking(), is_muted())

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

        logger.info("STREAM OPEN - sr=%d ch=%d device=%s", self.sample_rate, self.channels, self.device)
        try:
            with sd.InputStream(**stream_kwargs):
                logger.info("STREAM ACTIVE - waiting for cancellation")
                while True:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("STREAM CANCELLED - closing cleanly")
            raise
        except Exception as exc:
            logger.error("STREAM ERROR: %s", exc)
            if self.diagnostics:
                self.diagnostics.update(mic_active=False, stt_status="ERROR", last_error=str(exc))
            raise
        finally:
            logger.info("STREAM CLOSED - callbacks served: %d", self._callback_count)
            if self.diagnostics:
                self.diagnostics.update(mic_active=False)
