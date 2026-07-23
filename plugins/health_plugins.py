"""
health_plugins.py — Health & Wellness Plugin Suite for CHIDVI 555

Features:
  - Water Reminder: interval-based reminders to drink water
  - Screen-Time Monitor: tracks active screen time, alerts for breaks
  - Eye Care: 20-20-20 rule reminders
  - Exercise Coach: AI-generated exercise routines with voice guidance
  - Posture Detection: camera-based posture check with Gemini Vision
  - Sleep Tracker: log sleep/wake times with analytics
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from google import genai
from google.genai import types as gtypes

from api.key_pool import get_next_api_key


# ── Paths & Config ────────────────────────────────────────────────────

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"
_HEALTH_DATA_DIR = _BASE / "recordings" / "health"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_api_key() -> str:
    key = get_next_api_key()
    if key:
        return key
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8")).get("gemini_api_key", "")
    except Exception:
        pass
    raise RuntimeError("No Gemini API key available.")


def _notify(title: str, message: str, duration: int = 5):
    """Show a Windows toast notification."""
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=duration, threaded=True)
    except Exception:
        print(f"[Health] 🔔 {title}: {message}")


# ── Shared Gemini Client ─────────────────────────────────────────────

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if not _client:
        _client = genai.Client(api_key=_get_api_key())
    return _client


# ═══════════════════════════════════════════════════════════════════════
#  1. WATER REMINDER
# ═══════════════════════════════════════════════════════════════════════

_water_timer: Optional[threading.Thread] = None
_water_stop = threading.Event()


def _water_loop(interval_minutes: int):
    """Background loop: send notification every interval_minutes."""
    while not _water_stop.wait(interval_minutes * 60):
        if _water_stop.is_set():
            break
        _notify(
            "💧 Water Reminder",
            "Time to drink water! Stay hydrated 💪",
        )


def health_water_reminder(parameters: dict, **kwargs) -> str:
    """Start or stop the water reminder.

    Parameters:
        action: "start" | "stop"
        interval: minutes between reminders (default 30, for "start")
    """
    global _water_timer, _water_stop
    params = parameters or {}
    action = params.get("action", "start").strip().lower()

    if action == "stop":
        _water_stop.set()
        _water_timer = None
        return "💧 Water reminders stopped."

    interval = int(params.get("interval", 30))
    if interval < 5:
        return "⚠️ Minimum interval is 5 minutes."

    if _water_timer and _water_timer.is_alive():
        _water_stop.set()
        _water_timer.join(timeout=2)

    _water_stop.clear()
    _water_timer = threading.Thread(
        target=_water_loop, args=(interval,), daemon=True,
    )
    _water_timer.start()
    return f"💧 Water reminders started — every {interval} minutes."


# ═══════════════════════════════════════════════════════════════════════
#  2. SCREEN-TIME MONITOR
# ═══════════════════════════════════════════════════════════════════════

_screen_time_thread: Optional[threading.Thread] = None
_screen_time_stop = threading.Event()


def _screen_time_loop(break_interval: int, break_duration: int):
    """Track active time, suggest breaks."""
    elapsed = 0
    while not _screen_time_stop.is_set():
        if _screen_time_stop.wait(60):
            break
        elapsed += 1
        if elapsed >= break_interval:
            _notify(
                "🖥️ Screen-Time Alert",
                f"You've been on screen for {elapsed} minutes. "
                f"Take a {break_duration}-minute break! Stretch and rest your eyes.",
                duration=8,
            )
            elapsed = 0
            # Give break duration to recover
            if _screen_time_stop.wait(break_duration * 60):
                break


def health_screen_time(parameters: dict, **kwargs) -> str:
    """Monitor screen time and suggest breaks.

    Parameters:
        action: "start" | "stop" | "status"
        break_interval: minutes of activity before break alert (default 60)
        break_duration: minutes for break (default 5)
    """
    global _screen_time_thread, _screen_time_stop
    params = parameters or {}
    action = params.get("action", "start").strip().lower()

    if action == "stop":
        _screen_time_stop.set()
        _screen_time_thread = None
        return "🖥️ Screen-time monitoring stopped."

    if action == "status":
        running = _screen_time_thread is not None and _screen_time_thread.is_alive()
        return "🖥️ Screen-time monitor is active." if running else "📴 Screen-time monitor is off."

    interval = int(params.get("break_interval", 60))
    duration = int(params.get("break_duration", 5))

    if _screen_time_thread and _screen_time_thread.is_alive():
        _screen_time_stop.set()
        _screen_time_thread.join(timeout=2)

    _screen_time_stop.clear()
    _screen_time_thread = threading.Thread(
        target=_screen_time_loop, args=(interval, duration), daemon=True,
    )
    _screen_time_thread.start()
    return (
        f"🖥️ Screen-time monitor started. "
        f"Breaks every {interval} min for {duration} min."
    )


# ═══════════════════════════════════════════════════════════════════════
#  3. EYE CARE (20-20-20 Rule)
# ═══════════════════════════════════════════════════════════════════════

_eye_timer: Optional[threading.Thread] = None
_eye_stop = threading.Event()


def _eye_loop(interval_minutes: int):
    """Every N minutes, remind user to look 20 feet away for 20 seconds."""
    while not _eye_stop.is_set():
        if _eye_stop.wait(interval_minutes * 60):
            break
        _notify(
            "👁️ Eye Care — 20-20-20 Rule",
            "Look at something 20 feet away for 20 seconds. "
            "Blink a few times and relax your eyes!",
            duration=8,
        )


def health_eye_care(parameters: dict, **kwargs) -> str:
    """20-20-20 eye care reminders.

    Parameters:
        action: "start" | "stop"
        interval: minutes between reminders (default 20)
    """
    global _eye_timer, _eye_stop
    params = parameters or {}
    action = params.get("action", "start").strip().lower()

    if action == "stop":
        _eye_stop.set()
        _eye_timer = None
        return "👁️ Eye care reminders stopped."

    interval = int(params.get("interval", 20))
    if interval < 5:
        return "⚠️ Minimum interval is 5 minutes."

    if _eye_timer and _eye_timer.is_alive():
        _eye_stop.set()
        _eye_timer.join(timeout=2)

    _eye_stop.clear()
    _eye_timer = threading.Thread(
        target=_eye_loop, args=(interval,), daemon=True,
    )
    _eye_timer.start()
    return f"👁️ Eye care active — 20-20-20 reminders every {interval} minutes."


# ═══════════════════════════════════════════════════════════════════════
#  4. EXERCISE COACH
# ═══════════════════════════════════════════════════════════════════════

_exercise_routines: list[dict] = []
_exercise_index = 0
_exercise_active = False
_exercise_stop = threading.Event()


def _generate_routine(exercise_type: str, duration: int) -> list[dict]:
    """Ask Gemini to create a structured exercise routine."""
    client = _get_client()
    prompt = (
        f"Create a {duration}-minute {exercise_type} exercise routine. "
        "Return ONLY valid JSON array of steps. Each step has:\n"
        "- name: exercise name\n"
        "- duration_seconds: how long to do it\n"
        "- reps: number of reps (or null)\n"
        "- instructions: 1-sentence form guidance\n"
        "- tip: optional safety tip\n\n"
        "Example:\n"
        '[{"name": "Jumping Jacks", "duration_seconds": 30, "reps": null, '
        '"instructions": "Stand with feet together, jump and spread legs while raising arms", '
        '"tip": "Land softly on your heels"}]'
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=gtypes.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=2048,
                response_mime_type="application/json",
            ),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[Health] ⚠️ Routine generation failed: {e}")
        return [
            {"name": "Neck Rolls", "duration_seconds": 30, "reps": 5,
             "instructions": "Slowly roll your neck clockwise, then counter-clockwise"},
            {"name": "Shoulder Shrugs", "duration_seconds": 30, "reps": 10,
             "instructions": "Lift both shoulders toward ears, hold 2s, release"},
            {"name": "Wrist Stretches", "duration_seconds": 30, "reps": 5,
             "instructions": "Extend arm, gently pull fingers back with other hand"},
            {"name": "Deep Breathing", "duration_seconds": 60, "reps": 6,
             "instructions": "Inhale 4s, hold 4s, exhale 4s"},
        ]


def _exercise_loop(speak_callback):
    """Guide through exercise steps with voice."""
    global _exercise_index, _exercise_active
    _exercise_index = 0
    _exercise_active = True

    while _exercise_index < len(_exercise_routines) and not _exercise_stop.is_set():
        step = _exercise_routines[_exercise_index]
        name = step.get("name", "Exercise")
        instr = step.get("instructions", "")
        duration = step.get("duration_seconds", 30)
        tip = step.get("tip", "")

        msg = f"Next: {name}. {instr}"
        print(f"\n[Health] 🏋️ {msg}")
        if speak_callback:
            speak_callback(msg)
        elif _exercise_active:
            _text_to_speech(msg)

        if tip and not _exercise_stop.is_set():
            time.sleep(1)
            print(f"[Health] 💡 Tip: {tip}")

        # Wait for duration, checking for stop
        for _ in range(duration):
            if _exercise_stop.is_set():
                break
            time.sleep(1)

        _exercise_index += 1

    _exercise_active = False
    closing = "Great work! Exercise complete. Stay healthy!"
    print(f"[Health] ✅ {closing}")
    if speak_callback:
        speak_callback(closing)
    else:
        _text_to_speech(closing)


def _text_to_speech(text: str):
    """Direct TTS using Gemini speech modality."""
    try:
        client = _get_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[f"Say this in a motivating coach voice: {text}"],
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
                    import sounddevice as sd
                    audio = np.frombuffer(part.inline_data.data, dtype=np.int16)
                    sd.play(audio.astype(np.float32) / 32768.0, samplerate=24000)
                    sd.wait()
                    return
    except Exception as e:
        print(f"[Health] ⚠️ TTS failed: {e}")

    # Fallback
    try:
        if os.name == "nt":
            escaped = text.replace('"', '`"')
            cmd = (
                'Add-Type -AssemblyName System.Speech; '
                f'$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                f'$synth.Speak("{escaped}")'
            )
            subprocess.run(["powershell", "-Command", cmd], capture_output=True, timeout=30)
    except Exception:
        pass


def health_exercise_coach(parameters: dict, **kwargs) -> str:
    """Generate and guide through an exercise routine.

    Parameters:
        action: "start" | "stop" | "next" | "list"
        exercise_type: type of exercise (default "desk stretch")
        duration: total minutes (default 5)
    """
    global _exercise_routines, _exercise_index, _exercise_active, _exercise_stop
    params = parameters or {}
    action = params.get("action", "start").strip().lower()
    speak_callback = kwargs.get("speak")

    if action == "stop":
        _exercise_stop.set()
        _exercise_active = False
        return "🏋️ Exercise stopped."

    if action == "next":
        if _exercise_active and _exercise_index < len(_exercise_routines) - 1:
            _exercise_index += 1
            step = _exercise_routines[_exercise_index]
            return f"Next: {step['name']} — {step.get('instructions', '')}"
        return "🏋️ No more exercises or no active session."

    if action == "list":
        if _exercise_routines:
            lines = [f"{i+1}. {s['name']} ({s.get('duration_seconds', 30)}s)"
                     for i, s in enumerate(_exercise_routines)]
            return "📋 Exercise Routine:\n" + "\n".join(lines)
        return "📋 No routine generated yet. Start one first!"

    # action == "start"
    exercise_type = params.get("exercise_type", "desk stretch").strip()
    duration = int(params.get("duration", 5))

    _exercise_stop.clear()
    print(f"[Health] 🧠 Generating {exercise_type} routine ({duration} min)...")
    _exercise_routines = _generate_routine(exercise_type, duration)

    if not _exercise_routines:
        return "⚠️ Could not generate a routine. Try again."

    thread = threading.Thread(
        target=_exercise_loop, args=(speak_callback,), daemon=True,
    )
    thread.start()
    total_exercises = len(_exercise_routines)
    return (
        f"🏋️ {exercise_type.title()} routine generated! "
        f"{total_exercises} exercises over {duration} minutes."
    )


# ═══════════════════════════════════════════════════════════════════════
#  5. POSTURE DETECTION
# ═══════════════════════════════════════════════════════════════════════

_posture_alerts = True
_posture_stop = threading.Event()
_posture_thread: Optional[threading.Thread] = None


def _capture_camera_frame() -> Optional[bytes]:
    """Capture a single frame from the camera."""
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return None
        for _ in range(5):
            cap.read()  # warmup
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return buf.tobytes()
    except Exception as e:
        print(f"[Health] ⚠️ Camera error: {e}")
        return None


def _analyze_posture(image_bytes: bytes) -> str:
    """Send image to Gemini Vision for posture analysis."""
    import PIL.Image
    client = _get_client()
    img = PIL.Image.open(io.BytesIO(image_bytes))

    prompt = (
        "Analyze this person's posture from the camera image. Be constructive and supportive.\n"
        "Check:\n"
        "1. Head position — is it tilted or forward?\n"
        "2. Shoulders — are they level or hunched?\n"
        "3. Spine — is it straight or curved?\n"
        "4. Overall sitting/standing alignment\n\n"
        "Return a brief assessment (2-3 sentences) with ONE actionable correction tip.\n"
        "Format as plain text, no JSON."
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, img],
            config=gtypes.GenerateContentConfig(
                temperature=0.2, max_output_tokens=256,
            ),
        )
        return response.text.strip()
    except Exception as e:
        return f"⚠️ Posture analysis failed: {e}"


def _posture_monitor_loop(interval_minutes: int, speak_callback):
    """Periodically check posture."""
    global _posture_alerts
    while not _posture_stop.is_set():
        if _posture_stop.wait(interval_minutes * 60):
            break
        if not _posture_alerts:
            continue
        print("[Health] 🧍 Checking posture...")
        frame = _capture_camera_frame()
        if frame is None:
            print("[Health] ⚠️ Could not access camera for posture check")
            continue
        analysis = _analyze_posture(frame)
        print(f"[Health] 🧍 {analysis}")
        _notify("🧍 Posture Alert", analysis, duration=8)
        if speak_callback:
            speak_callback(f"Posture check: {analysis}")


def health_posture(parameters: dict, **kwargs) -> str:
    """Check or monitor your posture using the camera.

    Parameters:
        action: "check" | "start" | "stop"
        interval: minutes between checks (default 30, for "start")
    """
    global _posture_thread, _posture_stop, _posture_alerts
    params = parameters or {}
    action = params.get("action", "check").strip().lower()
    speak_callback = kwargs.get("speak")

    if action == "stop":
        _posture_stop.set()
        _posture_thread = None
        return "🧍 Posture monitoring stopped."

    if action == "start":
        interval = int(params.get("interval", 30))
        if _posture_thread and _posture_thread.is_alive():
            _posture_stop.set()
            _posture_thread.join(timeout=2)
        _posture_stop.clear()
        _posture_alerts = True
        _posture_thread = threading.Thread(
            target=_posture_monitor_loop, args=(interval, speak_callback), daemon=True,
        )
        _posture_thread.start()
        return f"🧍 Posture monitoring started — checks every {interval} minutes."

    # action == "check" (one-shot)
    print("[Health] 📸 Taking a posture snapshot...")
    frame = _capture_camera_frame()
    if frame is None:
        return "⚠️ Could not access camera. Check if it's in use by another app."

    analysis = _analyze_posture(frame)
    result = f"🧍 **Posture Check**\n{analysis}"

    if speak_callback:
        speak_callback(analysis)
    return result


# ═══════════════════════════════════════════════════════════════════════
#  6. SLEEP TRACKER
# ═══════════════════════════════════════════════════════════════════════

_SLEEP_DATA_FILE = _HEALTH_DATA_DIR / "sleep_log.json"


def _load_sleep_data() -> list[dict]:
    _HEALTH_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _SLEEP_DATA_FILE.exists():
        try:
            return json.loads(_SLEEP_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_sleep_data(data: list[dict]):
    _HEALTH_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SLEEP_DATA_FILE.write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8",
    )


def _sleep_summary(data: list[dict]) -> str:
    """Calculate sleep stats from logs."""
    if not data:
        return "No sleep data recorded yet."

    total_sleeps = len(data)
    total_hours = 0
    for entry in data:
        if "sleep_hours" in entry:
            total_hours += entry["sleep_hours"]

    avg_hours = total_hours / total_sleeps if total_sleeps else 0

    # Last 7 days
    cutoff = datetime.now() - timedelta(days=7)
    recent = [e for e in data if datetime.fromisoformat(e.get("date", "")).replace(tzinfo=None) > cutoff]
    recent_avg = sum(e.get("sleep_hours", 0) for e in recent) / len(recent) if recent else 0

    return (
        f"😴 **Sleep Summary**\n"
        f"Total logs: {total_sleeps}\n"
        f"Average sleep: {avg_hours:.1f}h\n"
        f"Last 7 days average: {recent_avg:.1f}h\n"
        f"Target: 7-9 hours per night"
    )


def health_sleep(parameters: dict, **kwargs) -> str:
    """Log sleep/wake times and view sleep analytics.

    Parameters:
        action: "log_sleep" | "log_wake" | "summary"
        bedtime: when you went to bed (optional, e.g. "23:00", default now)
        waketime: when you woke up (optional for log_sleep, e.g. "07:00")
        notes: optional notes about the sleep
    """
    params = parameters or {}
    action = params.get("action", "summary").strip().lower()
    now = datetime.now()

    if action == "log_sleep":
        data = _load_sleep_data()
        bedtime_str = params.get("bedtime", now.strftime("%H:%M"))
        bedtime = datetime.strptime(bedtime_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day,
        )
        # Check if already logged sleep for today
        today = now.strftime("%Y-%m-%d")
        existing = [e for e in data if e.get("date") == today and "sleep_time" in e]
        if existing:
            return "😴 You already logged sleep for today. Use 'log_wake' when you wake up."

        entry = {
            "date": today,
            "sleep_time": bedtime.isoformat(),
            "notes": params.get("notes", ""),
        }
        data.append(entry)
        _save_sleep_data(data)
        return f"😴 Sleep logged at {bedtime_str}. Good night! 🌙"

    elif action == "log_wake":
        data = _load_sleep_data()
        waketime_str = params.get("waketime", now.strftime("%H:%M"))
        waketime = datetime.strptime(waketime_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day,
        )

        # Find most recent sleep log without wake time
        for entry in reversed(data):
            if "sleep_time" in entry and "wake_time" not in entry:
                sleep_time = datetime.fromisoformat(entry["sleep_time"])
                if sleep_time.replace(tzinfo=None) < waketime.replace(tzinfo=None):
                    sleep_hours = (waketime.replace(tzinfo=None) - sleep_time.replace(tzinfo=None)).total_seconds() / 3600
                    entry["wake_time"] = waketime.isoformat()
                    entry["sleep_hours"] = round(sleep_hours, 1)
                    entry["quality"] = params.get("notes", "")
                    _save_sleep_data(data)
                    return (
                        f"🌅 Wake up logged at {waketime_str}! "
                        f"Slept {sleep_hours:.1f} hours. "
                        + ("Good morning! ☀️" if sleep_hours >= 6
                           else "Try to sleep a bit more tonight! 😴")
                    )

        return "😴 No sleep log found to close. Use 'log_sleep' first."

    # action == "summary"
    data = _load_sleep_data()
    return _sleep_summary(data)


# ═══════════════════════════════════════════════════════════════════════
#  HEALTH HUB — dispatches to individual features by tool name
# ═══════════════════════════════════════════════════════════════════════

_FEATURES = {
    "water_reminder": health_water_reminder,
    "screen_time": health_screen_time,
    "eye_care": health_eye_care,
    "exercise": health_exercise_coach,
    "posture": health_posture,
    "sleep": health_sleep,
}


def health_hub(parameters: dict, **kwargs) -> str:
    """Health & Wellness hub — list available features.

    Parameters:
        feature: specific feature to use
        action: action for that feature
        ...: feature-specific parameters
    """
    params = parameters or {}
    feature = params.get("feature", "").strip().lower()

    if not feature or feature == "list":
        lines = [
            "🏥 **Health & Wellness Features**",
            "  • water_reminder — Drink water reminders",
            "  • screen_time — Screen-time monitor with break alerts",
            "  • eye_care — 20-20-20 eye exercise reminders",
            "  • exercise — Exercise coach with AI routines",
            "  • posture — Camera posture detection",
            "  • sleep — Sleep tracker with analytics",
            "",
            "Example: I want water reminder every 30 minutes",
        ]
        return "\n".join(lines)

    if feature in _FEATURES:
        return _FEATURES[feature](params, **kwargs)

    return (
        f"⚠️ Unknown feature: '{feature}'. "
        f"Available: {', '.join(_FEATURES.keys())}"
    )


# ═══════════════════════════════════════════════════════════════════════
#  HEALTH AUTO MONITOR — runs everything in background on app launch
# ═══════════════════════════════════════════════════════════════════════

class HealthAutoMonitor:
    """Background health monitor — runs continuously without user commands.

    Runs ONE daemon thread that orchestrates all health checks:
      - Screen time: break alerts every 60 min
      - Water: hydration reminders every 30 min
      - Eye care: 20-20-20 rule every 20 min
      - Posture: camera-based check every 10 min (if user present)

    All alerts use toast notifications + optional voice (if speak_callback provided).
    """

    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._speak: Optional[Callable[[str], None]] = None
        self._minute_count = 0
        self._last_water_min = 0
        self._last_eye_min = 0
        self._last_posture_check = 0.0
        self._bad_posture_count = 0
        self._last_camera_warn = 0.0
        self._min_between_posture = 10  # minutes
        self._min_between_water = 30
        self._min_between_eye = 20
        self._min_between_breaks = 60
        self._user_present = False

    # ── Public API ──

    def start(self, speak_callback: Optional[Callable[[str], None]] = None):
        """Start the background health monitor daemon."""
        self._speak = speak_callback
        if self._thread and self._thread.is_alive():
            return  # already running
        self._stop.clear()
        self._minute_count = 0
        self._last_water_min = 0
        self._last_eye_min = 0
        self._last_posture_check = time.time()
        self._bad_posture_count = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Health] 🏥 Auto-monitor started — watching posture, screen time, hydration, eye care")

    def stop(self):
        """Stop the background health monitor."""
        self._stop.set()
        self._thread = None
        print("[Health] 🏥 Auto-monitor stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Main Loop ──

    def _loop(self):
        """Main loop — ticks every 60 seconds."""
        while not self._stop.is_set():
            if self._stop.wait(60):
                break
            self._minute_count += 1
            now = time.time()
            mins = self._minute_count

            # ── Check if user is at desk (cheap OpenCV check) ──
            self._user_present = self._check_user_present()

            # ── Screen-time: break after 60 min ──
            if mins > 0 and mins % self._min_between_breaks == 0:
                self._alert(
                    "🖥️ Time for a Break",
                    f"You've been at your desk for {self._min_between_breaks} minutes. "
                    "Stand up, stretch, and walk around for 5 minutes! 🚶",
                    10,
                )

            # ── Water: every 30 min ──
            if mins - self._last_water_min >= self._min_between_water:
                self._last_water_min = mins
                self._alert(
                    "💧 Hydration Reminder",
                    "Time to drink water! Your body needs hydration to stay focused. 🚰",
                    6,
                )

            # ── Eye care: every 20 min ──
            if mins - self._last_eye_min >= self._min_between_eye:
                self._last_eye_min = mins
                self._alert(
                    "👁️ 20-20-20 Eye Care",
                    "Look at something 20 feet away for 20 seconds. "
                    "Blink and relax your eye muscles! 😌",
                    8,
                )

            # ── Posture: every N min, only if user present ──
            secs_since_posture = now - self._last_posture_check
            if self._user_present and secs_since_posture >= self._min_between_posture * 60:
                self._check_posture()
                self._last_posture_check = time.time()

            # ── If bad posture persisted last time, check again sooner ──
            elif self._bad_posture_count > 0 and secs_since_posture >= 120:
                self._check_posture()
                self._last_posture_check = time.time()

    # ── User Presence Detection (via camera) ──

    def _check_user_present(self) -> bool:
        """Quick camera check — is someone at the desk? Uses OpenCV only, no API call."""
        try:
            import cv2
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                return False
            for _ in range(3):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return False
            # Simple brightness/motion heuristic — if frame is mostly black, nobody's there
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_brightness = gray.mean()
            return mean_brightness > 15  # dark = empty room / no user
        except Exception:
            return False  # no camera = assume present to avoid spam

    # ── Posture Check (Gemini Vision) ──

    def _check_posture(self):
        """Camera snapshot → Gemini analyzes posture → alert if bad."""
        print("[Health] 🧍 Checking posture...")
        try:
            import cv2
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                return
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return

            import PIL.Image
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            img = PIL.Image.open(io.BytesIO(buf.tobytes()))

            client = _get_client()
            prompt = (
                "Analyze this person's posture. Be VERY brief — 1 short sentence.\n"
                "Is their posture GOOD or BAD? "
                "If bad, say what's wrong in 5 words max and give one fix.\n"
                "Start with GOOD: or BAD:"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt, img],
                config=gtypes.GenerateContentConfig(
                    temperature=0.1, max_output_tokens=100,
                ),
            )
            analysis = response.text.strip()
            print(f"[Health] 🧍 {analysis}")

            is_bad = analysis.upper().startswith("BAD") or "bad" in analysis.lower()[:20]
            if is_bad:
                self._bad_posture_count += 1
                self._alert(
                    "🧍 Posture Alert",
                    analysis if len(analysis) < 150 else analysis[:150],
                    8,
                )
                if self._speak and self._bad_posture_count <= 2:
                    # Only interrupt voice on first bad posture detection
                    self._speak(f"Sir, your posture needs attention. {analysis}")
            else:
                self._bad_posture_count = 0

            # Rate-limit API calls: no more than 1 posture check per 60s regardless
            time.sleep(5)

        except Exception as e:
            now = time.time()
            if now - self._last_camera_warn > 300:  # warn every 5 min max
                print(f"[Health] ⚠️ Posture check failed: {e}")
                self._last_camera_warn = now

    # ── Alert Helper ──

    def _alert(self, title: str, message: str, duration: int = 6):
        """Send a toast notification (and voice if available)."""
        _notify(title, message, duration=duration)
        # Only speak critical alerts (posture) during normal monitoring
        if self._speak and "posture" in title.lower() and self._bad_posture_count <= 2:
            pass  # already spoken in _check_posture
        elif self._speak and "break" in title.lower():
            self._speak(f"Reminder: {message[:100]}")


# ── Global auto-monitor instance ──

_auto_monitor = HealthAutoMonitor()


def health_auto_start(speak_callback: Optional[Callable[[str], None]] = None) -> str:
    """Start the background health auto-monitor. Called from main.py on launch."""
    _auto_monitor.start(speak_callback)
    return "🏥 Health auto-monitor started."


def health_auto_stop() -> str:
    """Stop the background health auto-monitor."""
    _auto_monitor.stop()
    return "🏥 Health auto-monitor stopped."


def health_auto_status() -> str:
    """Check if the auto-monitor is running."""
    return "🏥 Auto-monitor is active." if _auto_monitor.is_running else "📴 Auto-monitor is off."
