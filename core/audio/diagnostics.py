"""Thread-safe runtime measurements for the live audio pipeline."""

from __future__ import annotations

import logging
import math
import threading
import time

logger = logging.getLogger(__name__)


def _linear_to_db(linear: float) -> float:
    """Convert linear amplitude [0.0–1.0] to dB [-100.0–0.0]."""
    if linear <= 0.0:
        return -100.0
    return max(-100.0, min(0.0, 20.0 * math.log10(linear)))


class AudioDiagnostics:
    """Shared snapshot updated by audio callbacks and read by the Qt UI.

    Microphone pipeline calls ``record_input`` on every captured PCM block.
    Speaker pipeline calls ``record_output`` on every played PCM block.
    The Qt timer calls ``snapshot`` to poll the latest values at 30–60 FPS.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict = {
            # ── mic ──
            "mic_level": 0.0,
            "mic_rms": 0.0,
            "mic_peak": 0.0,
            "mic_db": -100.0,
            "mic_peak_db": -100.0,
            "voice_detected": False,
            "mic_active": False,
            "mic_queue_depth": 0,
            # ── speaker ──
            "spk_level": 0.0,
            "spk_rms": 0.0,
            "spk_peak": 0.0,
            "spk_db": -100.0,
            "spk_peak_db": -100.0,
            "tts_status": "IDLE",
            "spk_playing": False,
            # ── session ──
            "stt_status": "IDLE",
            "last_text": "--",
            "ai_status": "IDLE",
            # ── hardware ──
            "sample_rate": 0,
            "device": "DEFAULT",
            "buffer_size": 0,
            "latency_ms": 0.0,
            "frame_rate": 0.0,
            "last_error": "",
        }
        self._frame_count = 0
        self._frame_window_started = time.monotonic()
        self._last_voice_detected = False

    # ── configuration ──────────────────────────────────────────────────

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

    # ── microphone recording ───────────────────────────────────────────

    def record_input(self, pcm: bytes) -> None:
        """Called from the sounddevice audio thread on every captured block."""
        import array as _array
        samples = _array.array("h")
        try:
            samples.frombytes(pcm)
        except ValueError:
            return
        if not samples:
            return

        n = len(samples)
        peak = max(abs(s) for s in samples) / 32768.0
        rms = math.sqrt(sum(s * s for s in samples) / n) / 32768.0

        mic_db = _linear_to_db(rms)
        mic_peak_db = _linear_to_db(peak)

        now = time.monotonic()
        with self._lock:
            self._data["mic_rms"] = rms
            self._data["mic_peak"] = peak
            self._data["mic_db"] = mic_db
            self._data["mic_peak_db"] = mic_peak_db
            self._data["mic_level"] = self._data["mic_level"] * 0.72 + rms * 0.28

            voice_detected = rms >= 0.012
            self._data["voice_detected"] = voice_detected
            if voice_detected != self._last_voice_detected:
                self._last_voice_detected = voice_detected
                logger.info("[VOICE] %s", "Detected" if voice_detected else "Silence")

            self._frame_count += 1
            elapsed = now - self._frame_window_started
            if elapsed >= 1.0:
                self._data["frame_rate"] = self._frame_count / elapsed
                self._frame_count = 0
                self._frame_window_started = now

    # ── speaker recording ──────────────────────────────────────────────

    def record_output(self, pcm: bytes) -> None:
        """Called from the speaker playback loop on every played block."""
        import array as _array
        samples = _array.array("h")
        try:
            samples.frombytes(pcm)
        except ValueError:
            return
        if not samples:
            return

        n = len(samples)
        peak = max(abs(s) for s in samples) / 32768.0
        rms = math.sqrt(sum(s * s for s in samples) / n) / 32768.0

        spk_db = _linear_to_db(rms)
        spk_peak_db = _linear_to_db(peak)

        with self._lock:
            self._data["spk_rms"] = rms
            self._data["spk_peak"] = peak
            self._data["spk_db"] = spk_db
            self._data["spk_peak_db"] = spk_peak_db
            self._data["spk_level"] = self._data["spk_level"] * 0.65 + rms * 0.35
            self._data["spk_playing"] = True

    def mark_speaker_idle(self) -> None:
        """Called when speaker stops playing."""
        with self._lock:
            self._data["spk_playing"] = False

    # ── snapshot for Qt UI ─────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)
