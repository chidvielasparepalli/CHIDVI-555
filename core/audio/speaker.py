"""
Speaker playback service for Gemini Live audio.

The service owns sounddevice output streams and output audio transforms so the
runtime does not need to manage speaker hardware directly.
"""

from array import array
import asyncio
from typing import Callable


class Speaker:
    def __init__(
        self,
        device: int | None = 3,
        sample_rate: int = 24000,
        channels: int = 2,
        chunk_size: int = 1024,
    ):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size

    def boost_voice_chunk(self, chunk: bytes) -> bytes:
        try:
            samples = array("h")
            samples.frombytes(chunk)
            for index, sample in enumerate(samples):
                value = int(sample * 1.18)
                if value > 32767:
                    value = 32767
                elif value < -32768:
                    value = -32768
                samples[index] = value
            return samples.tobytes()
        except Exception:
            return chunk

    def mono_to_stereo(self, mono: bytes) -> bytes:
        stereo = bytearray()
        for index in range(0, len(mono), 2):
            sample = mono[index:index + 2]
            stereo.extend(sample)
            stereo.extend(sample)
        return bytes(stereo)

    async def play_queue(
        self,
        audio_queue: asyncio.Queue,
        turn_done_event: asyncio.Event,
        set_speaking: Callable[[bool], None],
    ):
        try:
            import sounddevice as sd
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "sounddevice is not installed. Install requirements.txt before "
                "using speaker playback."
            ) from exc

        stream = sd.RawOutputStream(
            device=self.device,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.chunk_size,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        audio_queue.get(),
                        timeout=0.1,
                    )
                except asyncio.TimeoutError:
                    if turn_done_event.is_set() and audio_queue.empty():
                        set_speaking(False)
                        turn_done_event.clear()
                    continue

                set_speaking(True)
                mono = self.boost_voice_chunk(chunk)
                await asyncio.to_thread(stream.write, self.mono_to_stereo(mono))
        finally:
            set_speaking(False)
            stream.stop()
            stream.close()
