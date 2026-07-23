"""
screen_recorder.py — Screen Recorder Plugin for CHIDVI 555

Records your screen with voice narration.
Hotkeys:
  F9  — Start recording
  F10 — Stop recording
  F11 — Pause/Resume recording
"""

import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import cv2
import mss
import sounddevice as sd
from scipy.io.wavfile import write as wav_write


# ── Configuration ──────────────────────────────────────────────────────

_RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"
_SAMPLE_RATE = 44100
_CHANNELS = 1
_AUDIO_FORMAT = "int16"
_FPS = 20.0
_FOURCC = cv2.VideoWriter_fourcc(*"mp4v")
_FRAME_INTERVAL = 1.0 / _FPS


class ScreenRecorder:
    """Records screen + microphone audio into an MP4 video."""

    def __init__(self):
        self._recording = False
        self._paused = False
        self._audio_frames: list[np.ndarray] = []
        self._video_writer: Optional[cv2.VideoWriter] = None
        self._video_thread: Optional[threading.Thread] = None
        self._audio_thread: Optional[threading.Thread] = None
        self._audio_stream: Optional[sd.InputStream] = None
        self._start_time: float = 0
        self._output_path: Optional[Path] = None

    # ── Public API ─────────────────────────────────────────────────────

    def start(self) -> str:
        """Start recording. Returns status message."""
        if self._recording:
            return "⚠️ Already recording! Press F10 to stop first."

        _RECORDINGS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._output_path = _RECORDINGS_DIR / f"recording_{timestamp}.mp4"
        self._audio_frames = []
        self._start_time = time.time()

        # Get screen size
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            self._screen_w = monitor["width"]
            self._screen_h = monitor["height"]

        # Setup video writer
        self._video_writer = cv2.VideoWriter(
            str(self._output_path),
            _FOURCC,
            _FPS,
            (self._screen_w, self._screen_h),
        )

        self._recording = True
        self._paused = False

        # Start recording threads
        self._video_thread = threading.Thread(target=self._record_video, daemon=True)
        self._audio_thread = threading.Thread(target=self._record_audio, daemon=True)
        self._video_thread.start()
        self._audio_thread.start()

        return f"🔴 Recording started! Screen: {self._screen_w}x{self._screen_h}\nPress F10 to stop, F11 to pause."

    def stop(self) -> str:
        """Stop recording. Returns the file path."""
        if not self._recording:
            return "⚠️ Not recording! Press F9 to start."

        self._recording = False

        # Wait for threads to finish
        if self._video_thread:
            self._video_thread.join(timeout=5)
        if self._audio_thread:
            self._audio_thread.join(timeout=5)

        # Release video writer
        if self._video_writer:
            self._video_writer.release()
            self._video_writer = None

        # Stop audio stream
        if self._audio_stream:
            self._audio_stream.stop()
            self._audio_stream.close()
            self._audio_stream = None

        # Save audio to temp WAV
        audio_path = self._output_path.with_suffix(".wav")
        if self._audio_frames:
            audio_data = np.concatenate(self._audio_frames, axis=0)
            wav_write(str(audio_path), _SAMPLE_RATE, audio_data)

        # Merge video + audio using ffmpeg
        final_path = self._output_path.with_suffix(".mp4")
        self._merge_audio_video(
            str(self._output_path),
            str(audio_path),
            str(final_path),
        )

        # Clean up temp files
        if self._output_path.exists():
            self._output_path.unlink()
        if audio_path.exists():
            audio_path.unlink()

        duration = time.time() - self._start_time
        mins = int(duration // 60)
        secs = int(duration % 60)

        return f"✅ Recording saved!\n📁 {final_path}\n⏱️ Duration: {mins}m {secs}s"

    def pause_resume(self) -> str:
        """Toggle pause. Returns status message."""
        if not self._recording:
            return "⚠️ Not recording!"

        self._paused = not self._paused
        if self._paused:
            return "⏸️ Recording paused."
        else:
            return "▶️ Recording resumed."

    # ── Internal methods ───────────────────────────────────────────────

    def _record_video(self):
        """Capture screen frames in a loop."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            while self._recording:
                if self._paused:
                    time.sleep(0.1)
                    continue

                # Capture screen
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                # Convert BGRA to BGR (OpenCV format)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                if self._video_writer:
                    self._video_writer.write(frame)

                # Control frame rate
                time.sleep(_FRAME_INTERVAL)

    def _record_audio(self):
        """Capture microphone audio in a stream."""
        def audio_callback(indata, frames, time_info, status):
            if self._recording and not self._paused:
                self._audio_frames.append(indata.copy())

        self._audio_stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype=_AUDIO_FORMAT,
            callback=audio_callback,
            blocksize=1024,
        )
        self._audio_stream.start()

        # Keep thread alive while recording
        while self._recording:
            time.sleep(0.1)

    def _merge_audio_video(self, video_path: str, audio_path: str, output_path: str):
        """Merge video and audio using ffmpeg."""
        try:
            import subprocess
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",
                output_path,
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)
        except FileNotFoundError:
            # ffmpeg not found — just save video without audio
            import shutil
            shutil.copy2(video_path, output_path)
            print("[ScreenRecorder] ⚠️ ffmpeg not found — saved video without audio")
        except Exception as e:
            import shutil
            shutil.copy2(video_path, output_path)
            print(f"[ScreenRecorder] ⚠️ ffmpeg merge failed: {e}")


# ── Singleton instance ─────────────────────────────────────────────────

_recorder = ScreenRecorder()


def get_recorder() -> ScreenRecorder:
    """Get the singleton ScreenRecorder instance for reuse by other plugins."""
    return _recorder


def screen_record(parameters: dict, **kwargs) -> str:
    """
    Main entry point. Called from the tool dispatch in main.py.

    Parameters:
      action : "start" | "stop" | "pause"
    """
    params = parameters or {}
    action = params.get("action", "start").strip().lower()

    if action == "start":
        return _recorder.start()
    elif action == "stop":
        return _recorder.stop()
    elif action in ("pause", "resume", "toggle"):
        return _recorder.pause_resume()
    else:
        return f"⚠️ Unknown action: '{action}'. Use 'start', 'stop', or 'pause'."


if __name__ == "__main__":
    print("=== Screen Recorder ===")
    print("F9  — Start  |  F10 — Stop  |  F11 — Pause")
    print("Or use: python screen_recorder.py start/stop/pause\n")

    action = input("Action (start/stop/pause): ").strip().lower() or "start"
    result = screen_record({"action": action})
    print(result)
