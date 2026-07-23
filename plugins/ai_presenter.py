"""
ai_presenter.py — AI Autonomous Presenter with Vision-Guided Navigation

Autonomously presents apps, websites, PPTs, or code projects:
  - Captures screen → analyzes with Gemini Vision → decides next action
  - Moves cursor, clicks elements, scrolls, changes slides/tabs
  - Narrates everything using AI TTS voice in real-time
  - Records everything to MP4 and saves to /recordings

Usage:
  - "Present my React dashboard"
  - "Present this PowerPoint"
  - "Demo the web application at localhost:3000"
"""

import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import PIL.Image
import pyautogui

from google import genai
from google.genai import types as gtypes

from api.key_pool import get_next_api_key
from plugins.screen_recorder import get_recorder as _get_recorder


# ── Paths ──────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"
_RECORDINGS_DIR = _BASE / "recordings"


# ── Config ─────────────────────────────────────────────────────────────

_IMG_MAX_W = 640
_IMG_MAX_H = 360
_JPEG_Q = 60
_MAX_ITERATIONS = 50
_STARTUP_DELAY = 5  # seconds for user to switch to the target app


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_api_key() -> str:
    """Get an API key from the shared pool, with fallback to config file."""
    key = get_next_api_key()
    if key:
        return key
    # Fallback: load from config directly
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8")).get("gemini_api_key", "")
    except Exception:
        pass
    raise RuntimeError("No Gemini API key available. Check config/api_keys.json or .env")


# ── AIPresenter ────────────────────────────────────────────────────────

class AIPresenter:
    """Autonomous AI presenter with vision-guided navigation.

    Uses a see → think → act → narrate loop:
      1. Capture screenshot
      2. Send to Gemini Vision with context
      3. Parse structured JSON response (action, coordinates, narration)
      4. Execute action via pyautogui
      5. Narrate via Gemini TTS (or speak_callback if provided)
      6. Repeat until Gemini signals "done"
    """

    def __init__(self):
        self._client: Optional[genai.Client] = None
        self._action_history: list[dict] = []
        self._sections_covered: list[str] = []
        self._iteration = 0
        self._stop_event = threading.Event()
        self._dup_count = 0
        self._dup_key = ""

    # ── Initialization ────────────────────────────────────────────────

    def _init_gemini(self):
        """Lazy-init the Gemini client using the shared key pool."""
        if not self._client:
            self._client = genai.Client(api_key=_get_api_key())

    # ── Screen Capture ────────────────────────────────────────────────

    def _capture_screen(self) -> tuple[bytes, str]:
        """Capture the primary monitor and return compressed JPEG bytes."""
        import mss
        import mss.tools

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            png = mss.tools.to_png(shot.rgb, shot.size)

        img = PIL.Image.open(io.BytesIO(png)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"

    # ── Vision Cycle ──────────────────────────────────────────────────

    def _build_prompt(self, topic: str, content_info: str) -> str:
        """Build the per-cycle prompt with action history and section context."""
        # Action history
        history = ""
        if self._action_history:
            lines = []
            for i, a in enumerate(self._action_history[-8:], 1):
                t = a.get("target", "")[:50]
                n = a.get("narration", "")[:40]
                lines.append(f"  {i}. {a['action']} — {t} — {n}")
            history = "\n" + "\n".join(lines)

        # Sections covered
        sections = (
            ", ".join(self._sections_covered[-6:])
            if self._sections_covered
            else "none yet"
        )

        return (
            f"You are an AI presenter demonstrating: \"{topic}\".\n"
            f"Additional context: {content_info}\n\n"
            "Your job is to autonomously present this content on screen.\n"
            "Look at the screenshot and decide the NEXT BEST ACTION to demo effectively.\n"
            "You can see buttons, slides, tabs, navigation elements, and content.\n\n"
            f"Actions taken so far ({len(self._action_history)} total):{history}\n"
            f"Sections already covered: {sections}\n\n"
            "What should I do next to present this effectively?\n\n"
            "Return ONLY valid JSON. No markdown, no explanation.\n"
            "{\n"
            '  "action": "click|scroll|key|type|move_cursor|wait|done",\n'
            '  "x": 0.0–1.0 (normalized, for click/move_cursor),\n'
            '  "y": 0.0–1.0 (normalized, for click/move_cursor),\n'
            '  "target": "what element you are interacting with",\n'
            '  "narration": "what to say (1–3 sentences, natural voice)",\n'
            '  "section": "which section of the content this covers",\n'
            '  "key": "ctrl+tab|f5|win+2|... (for action=key)",\n'
            '  "text": "text to type (for action=type)",\n'
            '  "scroll_amount": -300 (negative=down, for action=scroll),\n'
            '  "duration": 2 (seconds, for action=wait, default 2)\n'
            "}"
        )

    def _vision_cycle(self, topic: str, content_info: str) -> Optional[dict]:
        """One iteration: capture screen → Gemini vision → parse response."""
        self._init_gemini()

        # Capture
        try:
            img_bytes, _ = self._capture_screen()
        except Exception as e:
            print(f"[AIPresenter] ⚠️ Screen capture failed: {e}")
            return {"action": "wait", "duration": 3, "narration": ""}

        # Send to Gemini
        img = PIL.Image.open(io.BytesIO(img_bytes))
        prompt = self._build_prompt(topic, content_info)

        try:
            response = self._client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt, img],
                config=gtypes.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                ),
            )

            raw = response.text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0].strip()

            action = json.loads(raw)
            if not isinstance(action, dict) or "action" not in action:
                raise ValueError(f"Missing 'action' field in: {raw[:200]}")

            # Track sections covered
            section = action.get("section", "").strip()
            if section and section not in self._sections_covered:
                self._sections_covered.append(section)

            return action

        except Exception as e:
            print(f"[AIPresenter] ⚠️ Vision analysis failed: {e}")
            return None

    # ── Action Execution ──────────────────────────────────────────────

    def _narrate(self, text: str, speak_callback: Optional[Callable[[str], None]] = None):
        """Speak narration — use callback if available, else direct TTS."""
        if not text:
            return
        if speak_callback:
            speak_callback(text)
        else:
            self._speak(text)

    def _execute_action(self, action: dict,
                        speak_callback: Optional[Callable[[str], None]] = None) -> None:
        """Execute a single action via pyautogui."""
        act = action.get("action", "wait")
        screen_w, screen_h = pyautogui.size()

        # ── Duplicate detection ──
        dup_key = f"{act}_{action.get('x', '')}_{action.get('target', '')}"
        if dup_key == self._dup_key:
            self._dup_count += 1
        else:
            self._dup_count = 0
            self._dup_key = dup_key

        if self._dup_count >= 2:
            print("[AIPresenter] ⚠️ Same action repeated — forcing scroll")
            act = "scroll"
            action = {"action": "scroll", "scroll_amount": -300}

        # ── Coordinate resolver ──
        def _c(val, max_val):
            if isinstance(val, (int, float)):
                return int(val * max_val) if 0.0 <= val <= 1.0 else int(val)
            return max_val // 2

        # ── Narration ──
        narration = action.get("narration", "")
        if narration:
            print(f"[AIPresenter] 🎙️ {narration[:120]}")
            if act != "done":
                # Non-done actions narrate before executing
                self._narrate(narration, speak_callback)
        if act == "click":
            x = _c(action.get("x", 0.5), screen_w)
            y = _c(action.get("y", 0.5), screen_h)
            print(f"[AIPresenter] 🖱️ Click ({x}, {y}) — {action.get('target', '')}")
            pyautogui.click(x, y)

        elif act == "move_cursor":
            x = _c(action.get("x", 0.5), screen_w)
            y = _c(action.get("y", 0.5), screen_h)
            print(f"[AIPresenter] 👆 Cursor → ({x}, {y})")
            pyautogui.moveTo(x, y, duration=0.3)

        elif act == "scroll":
            amount = action.get("scroll_amount", -300)
            print(f"[AIPresenter] 📜 Scroll {amount}")
            pyautogui.scroll(amount)

        elif act == "key":
            key = action.get("key", "")
            if "+" in key:
                pyautogui.hotkey(*key.split("+"))
            else:
                pyautogui.press(key)
            print(f"[AIPresenter] 🔑 Key: {key}")

        elif act == "type":
            text = action.get("text", "")
            if text:
                print(f"[AIPresenter] ⌨️ Type: {text[:40]}")
                pyautogui.typewrite(text, interval=0.05)

        elif act == "wait":
            dur = action.get("duration", 2)
            print(f"[AIPresenter] ⏳ Wait {dur}s")
            time.sleep(dur)

        elif act == "done":
            print(f"[AIPresenter] ✅ Done: {action.get('narration', '')}")
            return

        # Record for history (skip done/wait noise)
        if act not in ("done", "wait"):
            self._action_history.append({
                "action": act,
                "target": action.get("target", ""),
                "narration": narration[:60],
            })

    # ── Text-to-Speech ────────────────────────────────────────────────

    def _speak(self, text: str):
        """TTS via Gemini speech modality, fallback to Windows SAPI."""
        self._init_gemini()

        try:
            response = self._client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[f"Say this in a natural presenter voice: {text}"],
                config=gtypes.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=gtypes.SpeechConfig(
                        voice_config=gtypes.VoiceConfig(
                            prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(
                                voice_name="Kore",
                            )
                        )
                    ),
                ),
            )

            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        self._play_audio(part.inline_data.data)
                        return

            # No audio data — use fallback
            self._speak_fallback(text)

        except Exception as e:
            print(f"[AIPresenter] ⚠️ TTS failed: {e}")
            self._speak_fallback(text)

    def _speak_fallback(self, text: str):
        """Fallback TTS via Windows PowerShell."""
        try:
            if os.name == "nt":
                escaped = text.replace('"', '`"')
                cmd = (
                    'Add-Type -AssemblyName System.Speech; '
                    f'$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                    f'$synth.Speak("{escaped}")'
                )
                subprocess.run(
                    ["powershell", "-Command", cmd],
                    capture_output=True, timeout=30,
                )
        except Exception as e:
            print(f"[AIPresenter] ⚠️ Fallback TTS failed: {e}")

    def _play_audio(self, audio_bytes: bytes):
        """Play raw PCM audio via sounddevice."""
        try:
            import sounddevice as sd
            audio = np.frombuffer(audio_bytes, dtype=np.int16)
            sd.play(audio.astype(np.float32) / 32768.0, samplerate=24000)
            sd.wait()
        except ImportError:
            print("[AIPresenter] ⚠️ sounddevice not installed")
        except Exception as e:
            print(f"[AIPresenter] ⚠️ Audio playback failed: {e}")

    # ── Public API ────────────────────────────────────────────────────

    def stop(self):
        """Signal the presenter to stop gracefully."""
        self._stop_event.set()

    def present(self, topic: str, content_info: str = "",
                speak_callback: Optional[Callable[[str], None]] = None) -> str:
        """Main entry point — record → vision loop → stop → save.

        Args:
            topic: What to present (project name, app, URL, etc.)
            content_info: Additional context (description, path, etc.)
            speak_callback: Optional non-blocking TTS callback (e.g. JarvisLive.speak)

        Returns:
            Status message with recording path.
        """
        print(f"[AIPresenter] 🎬 Autonomous presentation: {topic}")
        self._action_history = []
        self._sections_covered = []
        self._iteration = 0
        self._dup_count = 0
        self._dup_key = ""
        self._stop_event.clear()

        recorder = _get_recorder()

        # ── Start recording ──
        try:
            msg = recorder.start()
            print(msg)
        except Exception as e:
            return f"❌ Failed to start recording: {e}"

        # ── Countdown for user to switch apps ──
        print(f"[AIPresenter] ⏳ You have {_STARTUP_DELAY}s to switch to your app...")
        for i in range(_STARTUP_DELAY, 0, -1):
            if self._stop_event.is_set():
                recorder.stop()
                return "⏹️ Cancelled."
            print(f"  {i}...")
            time.sleep(1)

        # ── Vision presentation loop ──
        try:
            while self._iteration < _MAX_ITERATIONS:
                if self._stop_event.is_set():
                    print("[AIPresenter] ⏹️ Stopped by signal")
                    break

                print(f"\n[AIPresenter] 🔄 Step {self._iteration + 1}/{_MAX_ITERATIONS}")

                action = self._vision_cycle(topic, content_info)

                # Retry on vision failure
                if action is None:
                    print("[AIPresenter] ⚠️ Vision failed, retrying in 3s...")
                    time.sleep(3)
                    self._iteration += 1
                    continue

                # Done signal
                if action.get("action") == "done":
                    closing = action.get("narration", "Presentation complete!")
                    print(f"[AIPresenter] ✅ {closing}")
                    if closing:
                        self._narrate(closing, speak_callback)
                    break

                # Execute (narration is handled inside _execute_action)
                self._execute_action(action, speak_callback)
                self._iteration += 1

            else:
                print(f"[AIPresenter] ⏹️ Reached max {_MAX_ITERATIONS} steps")
                self._narrate("I've reached my time limit. Let me wrap up here.",
                              speak_callback)

        except KeyboardInterrupt:
            print("\n[AIPresenter] ⏹️ Interrupted")
        except Exception as e:
            print(f"[AIPresenter] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            result = recorder.stop()
            print(f"\n{result}")

        return result


# ── Singleton ─────────────────────────────────────────────────────────

_presenter = AIPresenter()


def ai_present(parameters: dict, **kwargs) -> str:
    """Tool entry point. Called from main.py dispatch.

    Parameters:
        topic: What to present (required)
        content_info: Additional context (optional)
    """
    params = parameters or {}
    topic = params.get("topic", "").strip()
    content_info = params.get("content_info", "").strip()

    # Forward speak callback if provided (from JarvisLive.speak)
    speak_callback = kwargs.get("speak")

    if not topic:
        return (
            "⚠️ Please specify what to present. "
            "Examples: 'Present my React dashboard', 'Demo this website'"
        )

    return _presenter.present(topic, content_info, speak_callback)


# ── CLI Entry ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== AI Presenter ===")
    topic = input("What to present? ").strip()
    info = input("Additional context (optional): ").strip()
    result = ai_present({"topic": topic, "content_info": info})
    print(f"\n{result}")
