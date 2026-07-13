"""Thread-safe runtime measurements for the live audio pipeline."""

from __future__ import annotations

from array import array
import threading
import time


class AudioDiagnostics:
    """Small shared snapshot updated by audio callbacks and read by the Qt UI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = {
            "mic_level": 0.0,
            "rms": 0.0,
            "peak": 0.0,
            "voice_detected": False,
            "mic_active": False,
            "stt_status": "IDLE",
            "last_text": "--",
            "ai_status": "IDLE",
            "tts_status": "IDLE",
            "sample_rate": 0,
            "device": "DEFAULT",
            "buffer_size": 0,
            "latency_ms": 0.0,
            "frame_rate": 0.0,
            "last_error": "",
        }
        self._frame_count = 0
        self._frame_window_started = time.monotonic()

    def configure_input(self, sample_rate: int, device: int | None, buffer_size: int) -> None:
        self.update(
            sample_rate=sample_rate,
            device="DEFAULT" if device is None else str(device),
            buffer_size=buffer_size,
            latency_ms=(buffer_size / sample_rate * 1000) if sample_rate else 0.0,
        )

    def update(self, **values) -> None:
        with self._lock:
            self._data.update(values)

    def record_input(self, pcm: bytes) -> None:
        samples = array("h")
        try:
            samples.frombytes(pcm)
        except ValueError:
            return
        if not samples:
            return

        peak = max(abs(sample) for sample in samples) / 32768.0
        rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5 / 32768.0
        now = time.monotonic()
        with self._lock:
            # Smooth UI input without hiding a real peak. The threshold is
            # intentionally modest for ordinary desktop microphones.
            self._data["rms"] = rms
            self._data["peak"] = peak
            self._data["mic_level"] = self._data["mic_level"] * 0.72 + rms * 0.28
            self._data["voice_detected"] = rms >= 0.012
            self._frame_count += 1
            elapsed = now - self._frame_window_started
            if elapsed >= 1.0:
                self._data["frame_rate"] = self._frame_count / elapsed
                self._frame_count = 0
                self._frame_window_started = now

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)
