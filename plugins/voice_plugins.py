"""
voice_plugins.py — Voice Plugin suite for CHIDVI 555

Features:
  - Voice Notes: record short notes, transcribe, save text + audio
  - Meeting Recorder: record meetings, transcribe, summarize action items
  - Live Translator: capture speech and translate it
  - Accent Trainer: analyze accent clarity and give training feedback
  - Pronunciation Coach: evaluate pronunciation for a target phrase
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types as gtypes

from api.key_pool import get_next_api_key


_SAMPLE_RATE = 16000
_CHANNELS = 1
_DTYPE = "int16"
_BLOCKSIZE = 1024


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"
_OUTPUT_DIR = _BASE / "recordings" / "voice_plugins"
_VOICE_CLONE_DIR = _BASE / "voice_profiles"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_api_key() -> str:
    key = get_next_api_key()
    if key:
        return key
    key = _load_config().get("gemini_api_key", "")
    if key:
        return key
    raise RuntimeError("No Gemini API key available. Check config/api_keys.json or .env")


def _get_elevenlabs_api_key() -> str:
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    config = _load_config()
    return (
        config.get("elevenlabs_api_key")
        or config.get("eleven_labs_api_key")
        or config.get("ELEVENLABS_API_KEY")
        or ""
    ).strip()


def _require_requests():
    try:
        import requests  # type: ignore
        return requests
    except Exception as exc:
        raise RuntimeError("Install requests to use ElevenLabs voice cloning: pip install requests") from exc


def _elevenlabs_headers(api_key: str) -> dict:
    return {"xi-api-key": api_key}


def _elevenlabs_create_voice(profile_name: str, audio_path: Path, description: str) -> str:
    api_key = _get_elevenlabs_api_key()
    if not api_key:
        return ""

    requests = _require_requests()
    url = "https://api.elevenlabs.io/v1/voices/add"
    data = {
        "name": profile_name,
        "description": description[:900],
        "labels": json.dumps({"use": "personal", "consent": "own_voice"}),
    }
    with audio_path.open("rb") as handle:
        files = {"files": (audio_path.name, handle, "audio/wav")}
        response = requests.post(
            url,
            headers=_elevenlabs_headers(api_key),
            data=data,
            files=files,
            timeout=120,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"ElevenLabs voice creation failed: {response.status_code} {response.text[:500]}")
    payload = response.json()
    voice_id = payload.get("voice_id") or payload.get("voice", {}).get("voice_id")
    if not voice_id:
        raise RuntimeError(f"ElevenLabs did not return a voice_id: {payload}")
    return voice_id


def _elevenlabs_synthesize(voice_id: str, text: str, output_path: Path) -> Path:
    api_key = _get_elevenlabs_api_key()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured.")

    requests = _require_requests()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    response = requests.post(
        url,
        headers={
            **_elevenlabs_headers(api_key),
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True,
            },
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"ElevenLabs synthesis failed: {response.status_code} {response.text[:500]}")
    output_path.write_bytes(response.content)
    return output_path


def _slug(value: str, fallback: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:60] or fallback


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_wav(path: Path, frames: list[np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if frames:
        data = np.concatenate(frames, axis=0)
    else:
        data = np.zeros((0, _CHANNELS), dtype=np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(_CHANNELS)
        wav.setsampwidth(np.dtype(np.int16).itemsize)
        wav.setframerate(_SAMPLE_RATE)
        wav.writeframes(data.astype(np.int16).tobytes())


def _record_for_seconds(duration: float) -> list[np.ndarray]:
    duration = max(1.0, min(float(duration or 10), 60 * 60))
    frames: list[np.ndarray] = []

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    with sd.InputStream(
        samplerate=_SAMPLE_RATE,
        channels=_CHANNELS,
        dtype=_DTYPE,
        blocksize=_BLOCKSIZE,
        callback=callback,
    ):
        time.sleep(duration)

    return frames


def _analyze_audio(audio_path: Path, prompt: str, *, temperature: float = 0.2, max_tokens: int = 2048) -> str:
    client = genai.Client(api_key=_get_api_key())
    audio_bytes = audio_path.read_bytes()
    audio_part = gtypes.Part(
        inline_data=gtypes.Blob(mime_type="audio/wav", data=audio_bytes)
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt, audio_part],
        config=gtypes.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text.strip() if response.text else "I couldn't analyze the recording."


@dataclass
class _StreamingRecorder:
    name: str
    frames: list[np.ndarray] = field(default_factory=list)
    active: bool = False
    started_at: float = 0.0
    stream: Optional[sd.InputStream] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> str:
        with self.lock:
            if self.active:
                return f"⚠️ {self.name} is already recording. Say stop when you are done."
            self.frames = []
            self.started_at = time.time()
            self.stream = sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype=_DTYPE,
                blocksize=_BLOCKSIZE,
                callback=self._callback,
            )
            self.stream.start()
            self.active = True
            return f"🎙️ {self.name} recording started. Say stop when you are done."

    def stop(self) -> tuple[Optional[Path], float, str]:
        with self.lock:
            if not self.active:
                return None, 0.0, f"⚠️ {self.name} is not recording."
            self.active = False
            duration = time.time() - self.started_at
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            path = _OUTPUT_DIR / f"{_slug(self.name, 'voice')}_{_timestamp()}.wav"
            _save_wav(path, self.frames)
            self.frames = []
            return path, duration, ""

    def _callback(self, indata, frame_count, time_info, status):
        if self.active:
            self.frames.append(indata.copy())


_voice_note_recorder = _StreamingRecorder("Voice Notes")
_meeting_recorder = _StreamingRecorder("Meeting Recorder")


def voice_notes(parameters: dict, **kwargs) -> str:
    """Record, transcribe, and save voice notes."""
    params = parameters or {}
    action = params.get("action", "record").strip().lower()
    title = params.get("title", "voice note")

    if action in ("start", "record") and not params.get("duration"):
        return _voice_note_recorder.start()

    if action == "stop":
        audio_path, duration, error = _voice_note_recorder.stop()
        if error:
            return error
    else:
        duration = float(params.get("duration", 15))
        frames = _record_for_seconds(duration)
        audio_path = _OUTPUT_DIR / f"voice_note_{_timestamp()}.wav"
        _save_wav(audio_path, frames)

    prompt = (
        "Transcribe this voice note accurately. Then provide a concise cleaned note "
        "with key points and any action items. Return in markdown with headings: "
        "Transcript, Clean Note, Action Items."
    )
    result = _analyze_audio(audio_path, prompt)
    text_path = audio_path.with_name(f"{_slug(title, 'voice_note')}_{audio_path.stem}.md")
    text_path.write_text(result, encoding="utf-8")
    mins, secs = divmod(int(duration), 60)
    return f"✅ Voice note saved.\n🎧 Audio: {audio_path}\n📝 Note: {text_path}\n⏱️ Duration: {mins}m {secs}s\n\n{result}"


def meeting_recorder(parameters: dict, **kwargs) -> str:
    """Record a meeting, then transcribe and summarize it."""
    params = parameters or {}
    action = params.get("action", "start").strip().lower()
    meeting_title = params.get("title", "meeting")

    if action == "start":
        return _meeting_recorder.start()

    if action == "stop":
        audio_path, duration, error = _meeting_recorder.stop()
        if error:
            return error
    else:
        duration = float(params.get("duration", 300))
        frames = _record_for_seconds(duration)
        audio_path = _OUTPUT_DIR / f"meeting_{_timestamp()}.wav"
        _save_wav(audio_path, frames)

    prompt = (
        "You are a meeting assistant. Transcribe this meeting and produce structured notes. "
        "Return markdown with headings: Summary, Decisions, Action Items with owners if mentioned, "
        "Questions, Full Transcript. If speakers are unclear, label them Speaker 1, Speaker 2, etc."
    )
    result = _analyze_audio(audio_path, prompt, max_tokens=4096)
    notes_path = audio_path.with_name(f"{_slug(meeting_title, 'meeting')}_{audio_path.stem}.md")
    notes_path.write_text(result, encoding="utf-8")
    mins, secs = divmod(int(duration), 60)
    return f"✅ Meeting recording processed.\n🎧 Audio: {audio_path}\n📋 Notes: {notes_path}\n⏱️ Duration: {mins}m {secs}s\n\n{result}"


def live_translator(parameters: dict, **kwargs) -> str:
    """Capture a short speech segment and translate it."""
    params = parameters or {}
    target_language = params.get("target_language", "English")
    source_language = params.get("source_language", "auto-detect")
    duration = float(params.get("duration", 10))

    frames = _record_for_seconds(duration)
    audio_path = _OUTPUT_DIR / f"live_translation_{_timestamp()}.wav"
    _save_wav(audio_path, frames)
    prompt = (
        f"The source language is {source_language}. Translate this audio into {target_language}. "
        "Return markdown with: Detected Language, Original Transcript, Translation, Notes. "
        "Keep the translation natural and conversational."
    )
    result = _analyze_audio(audio_path, prompt)
    return f"🌍 Translation complete.\n🎧 Audio: {audio_path}\n\n{result}"


def accent_trainer(parameters: dict, **kwargs) -> str:
    """Analyze spoken English accent clarity and provide practice tips."""
    params = parameters or {}
    target_accent = params.get("target_accent", "neutral international English")
    practice_text = params.get("practice_text", "")
    duration = float(params.get("duration", 12))

    frames = _record_for_seconds(duration)
    audio_path = _OUTPUT_DIR / f"accent_trainer_{_timestamp()}.wav"
    _save_wav(audio_path, frames)
    prompt = (
        f"You are an accent trainer. Target accent: {target_accent}. "
        f"Practice text, if provided: {practice_text or 'not provided'}. "
        "Analyze rhythm, stress, vowel clarity, consonants, intonation, and overall understandability. "
        "Do not shame the speaker. Return a score out of 100, strengths, top 3 improvements, "
        "and 3 short practice drills."
    )
    result = _analyze_audio(audio_path, prompt)
    return f"🗣️ Accent training feedback ready.\n🎧 Audio: {audio_path}\n\n{result}"


def pronunciation_coach(parameters: dict, **kwargs) -> str:
    """Evaluate pronunciation against a target word or phrase."""
    params = parameters or {}
    phrase = params.get("phrase") or params.get("target_phrase") or ""
    duration = float(params.get("duration", 8))

    if not phrase:
        return "Please provide a word or phrase to practice pronunciation."

    frames = _record_for_seconds(duration)
    audio_path = _OUTPUT_DIR / f"pronunciation_coach_{_timestamp()}.wav"
    _save_wav(audio_path, frames)
    prompt = (
        f"You are a pronunciation coach. The target phrase is: {phrase!r}. "
        "Compare the speaker's pronunciation to the target. Return markdown with: "
        "Accuracy Score out of 100, What sounded correct, What to fix, Syllable-by-syllable guidance, "
        "Mouth/tongue placement tips, and one repeat-after-me practice line."
    )
    result = _analyze_audio(audio_path, prompt)
    return f"🎯 Pronunciation feedback ready for: {phrase}\n🎧 Audio: {audio_path}\n\n{result}"


def _voice_clone_consent_ok(params: dict) -> bool:
    consent = str(params.get("consent", "")).strip().lower()
    personal_use = params.get("personal_use", False)
    return consent in {"yes", "true", "i consent", "my voice", "personal use"} and bool(personal_use)


def _voice_profile_path(profile_name: str) -> Path:
    return _VOICE_CLONE_DIR / _slug(profile_name, "my_voice") / "profile.json"


def voice_cloning(parameters: dict, **kwargs) -> str:
    """
    Personal-use voice cloning profile manager.

    This intentionally requires explicit consent and stores a local voice profile.
    When ELEVENLABS_API_KEY is configured, it also creates an ElevenLabs voice and
    can synthesize text to MP3 using that consented personal voice profile.
    """
    params = parameters or {}
    action = params.get("action", "create_profile").strip().lower()
    profile_name = params.get("profile_name", "my voice")

    if action in {"create", "create_profile", "record"}:
        if not _voice_clone_consent_ok(params):
            return (
                "For safety, Voice Cloning only works for your own voice with explicit consent. "
                "Call it with consent='my voice' and personal_use=True."
            )

        duration = float(params.get("duration", 30))
        frames = _record_for_seconds(duration)
        profile_dir = _voice_profile_path(profile_name).parent
        profile_dir.mkdir(parents=True, exist_ok=True)
        audio_path = profile_dir / f"reference_{_timestamp()}.wav"
        _save_wav(audio_path, frames)

        prompt = (
            "Analyze this consenting user's voice for personal-use voice profile setup. "
            "Do not identify the person. Describe non-sensitive voice characteristics useful for TTS: "
            "pitch range, pace, energy, clarity, tone, accent-neutral observations, and recording quality. "
            "Return concise JSON with keys: voice_style, tts_guidance, recording_quality, suggested_sample_script."
        )
        analysis = _analyze_audio(audio_path, prompt, temperature=0.1)
        backend = "local_profile_only"
        provider_voice_id = ""
        provider_note = "Set ELEVENLABS_API_KEY to upload this profile and synthesize cloned speech."
        if _get_elevenlabs_api_key():
            provider_voice_id = _elevenlabs_create_voice(
                profile_name=profile_name,
                audio_path=audio_path,
                description="Personal-use consented voice profile created by CHIDVI 555.",
            )
            backend = "elevenlabs"
            provider_note = "ElevenLabs voice created and ready for synthesis."

        profile = {
            "profile_name": profile_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "personal_use_only": True,
            "consent": "User confirmed this is their own voice for personal use.",
            "reference_audio": str(audio_path),
            "analysis": analysis,
            "synthesis_backend": backend,
            "provider_voice_id": provider_voice_id,
        }
        profile_path = _voice_profile_path(profile_name)
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        return (
            "✅ Personal voice profile created.\n"
            f"👤 Profile: {profile_name}\n"
            f"🎧 Reference: {audio_path}\n"
            f"📄 Manifest: {profile_path}\n\n"
            f"{provider_note}"
        )

    if action == "list":
        if not _VOICE_CLONE_DIR.exists():
            return "No personal voice profiles found yet."
        profiles = sorted(p.parent.name for p in _VOICE_CLONE_DIR.glob("*/profile.json"))
        return "Personal voice profiles:\n" + "\n".join(f"- {name}" for name in profiles) if profiles else "No personal voice profiles found yet."

    if action in {"speak", "synthesize", "generate"}:
        text = params.get("text", "").strip()
        profile_path = _voice_profile_path(profile_name)
        if not profile_path.exists():
            return f"Voice profile '{profile_name}' was not found. Create it first with explicit consent."
        if not text:
            return "Please provide text to synthesize."
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        voice_id = profile.get("provider_voice_id", "")
        if not voice_id:
            return (
                "This profile has no ElevenLabs voice_id yet. Recreate the profile after setting "
                "ELEVENLABS_API_KEY in your environment or config/api_keys.json as elevenlabs_api_key.\n"
                f"Profile: {profile_path}"
            )
        output_path = profile_path.parent / f"clone_speech_{_timestamp()}.mp3"
        _elevenlabs_synthesize(voice_id=voice_id, text=text, output_path=output_path)
        return (
            "✅ Cloned speech generated for personal use.\n"
            f"👤 Profile: {profile.get('profile_name', profile_name)}\n"
            f"🔊 Audio: {output_path}"
        )

    return "Unknown Voice Cloning action. Use create_profile, list, or synthesize."
