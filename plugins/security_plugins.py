"""
security_plugins.py — Security Suite for CHIDVI 555

Features:
  - Face Unlock     : Register and verify faces via webcam using face_recognition
  - Voice Auth      : Voice biometric verification using spectral/MFCC voiceprints
  - Unknown Person  : Background camera monitoring for unknown faces
  - Webcam Monitor  : Track camera access attempts and usage activity
  - USB Monitor     : Alert on USB device connections/disconnections

Every function follows the plugin pattern:
    security_*(parameters: dict, **kwargs) -> str

Author: Chidvielas Parepalli
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

import numpy as np


# ── Paths & Config ─────────────────────────────────────────────────────

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
_SECURITY_DIR = _BASE / "security"
_FACES_DIR = _SECURITY_DIR / "known_faces"
_VOICEPRINTS_DIR = _SECURITY_DIR / "voiceprints"
_CONFIG_PATH = _SECURITY_DIR / "security_config.json"
_LOG_PATH = _SECURITY_DIR / "security_log.json"

for _d in [_FACES_DIR, _VOICEPRINTS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


# ── Helpers ─────────────────────────────────────────────────────────────

def _notify(title: str, message: str, duration: int = 5):
    """Show a Windows toast notification."""
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=duration, threaded=True)
    except Exception:
        print(f"[Security] 🔔 {title}: {message}")


def _log_event(event_type: str, details: str, level: str = "info") -> dict:
    """Append a timestamped entry to the rolling security log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "details": details,
        "level": level,
    }
    try:
        logs = []
        if _LOG_PATH.exists():
            logs = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        logs.append(entry)
        if len(logs) > 1000:
            logs = logs[-1000:]
        _LOG_PATH.write_text(json.dumps(logs, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Security] Log write error: {e}")
    return entry


def _load_config() -> dict:
    """Load security configuration, returning defaults if absent."""
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "face_unlock": {"enabled": True, "tolerance": 0.5},
        "voice_auth": {"enabled": False, "threshold": 0.7},
        "unknown_person_alert": {"enabled": False, "interval": 10},
        "webcam_monitor": {"enabled": False, "interval": 5},
        "usb_monitor": {"enabled": False},
    }


def _save_config(config: dict):
    """Persist security configuration to disk."""
    _CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _get_camera_frame(warmup: int = 5) -> Optional[np.ndarray]:
    """Capture a single frame from the default webcam."""
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return None
        for _ in range(warmup):
            cap.read()
        ret, frame = cap.read()
        cap.release()
        return frame if ret else None
    except Exception as e:
        print(f"[Security] Camera error: {e}")
        return None


def _record_audio(duration: float = 3.0, sample_rate: int = 16000) -> Optional[np.ndarray]:
    """Record a short mono audio clip and return it as a float32 array."""
    try:
        import sounddevice as sd
        print(f"[Security] 🎤 Recording for {duration}s ...")
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate,
                           channels=1, dtype=np.float32)
        sd.wait()
        return recording.flatten()
    except Exception as e:
        print(f"[Security] Recording error: {e}")
        return None


# ═════════════════════════════════════════════════════════════════════════
#  1. FACE UNLOCK
# ═════════════════════════════════════════════════════════════════════════

def _load_known_faces() -> tuple[list, list]:
    """Load all registered face encodings and names from disk."""
    encodings, names = [], []

    # Prefer cached .npy files (faster)
    for npy_file in sorted(_FACES_DIR.glob("*.npy")):
        try:
            encodings.append(np.load(str(npy_file)))
            names.append(npy_file.stem)
        except Exception:
            continue

    # Fall back to .jpg source images
    if not encodings:
        for jpg_file in sorted(_FACES_DIR.glob("*.jpg")):
            try:
                import face_recognition
                img = face_recognition.load_image_file(str(jpg_file))
                encs = face_recognition.face_encodings(img)
                if encs:
                    encodings.append(encs[0])
                    names.append(jpg_file.stem)
                    np.save(str(_FACES_DIR / f"{jpg_file.stem}.npy"), encs[0])
            except Exception:
                continue

    return encodings, names


def face_unlock(parameters: dict, **kwargs) -> str:
    """
    Face Unlock — Register and verify identity via webcam face recognition.

    Actions:
      verify   — capture a frame and match against known faces
      register — capture frame, detect face, and save as <name>
      list     — show all registered faces
      delete   — remove a registered face by name
      status   — show face-unlock configuration and face count

    Parameters:
      action (str)       — verify | register | list | delete | status
      name   (str)       — label for register / delete
      tolerance (float)  — match strictness (0.0‑1.0, lower = stricter, default 0.5)
    """
    params = parameters or {}
    action = params.get("action", "verify").strip().lower()
    speak = kwargs.get("speak")

    try:
        import face_recognition
    except ImportError:
        return ("⚠️ Face recognition library is not installed. "
                "Run: pip install face_recognition dlib")

    config = _load_config()
    fu_cfg = config.get("face_unlock", {})

    if action == "status":
        count = len(list(_FACES_DIR.glob("*.jpg")))
        if not count:
            count = len(list(_FACES_DIR.glob("*.npy")))
        return (
            f"🔐 Face Unlock Status\n"
            f"  Enabled:      {fu_cfg.get('enabled', True)}\n"
            f"  Faces known:  {count}\n"
            f"  Tolerance:    {fu_cfg.get('tolerance', 0.5)}\n"
            f"  Data dir:     {_FACES_DIR}"
        )

    if not fu_cfg.get("enabled", True) and action != "register":
        return "🔐 Face unlock is currently disabled."

    if action == "list":
        faces = list(_FACES_DIR.glob("*.jpg"))
        if not faces:
            return "📷 No registered faces. Use action 'register' to add one."
        return "📷 Registered faces:\n  " + "\n  ".join(f"• {f.stem}" for f in faces)

    if action == "delete":
        name = (params.get("name") or "").strip()
        if not name:
            return "⚠️ Please provide a 'name' to delete."
        removed = False
        for ext in (".jpg", ".npy"):
            p = _FACES_DIR / f"{name}{ext}"
            if p.exists():
                p.unlink()
                removed = True
        if removed:
            _log_event("face_delete", f"Deleted face: {name}")
            return f"🗑️ Face '{name}' deleted."
        return f"⚠️ No registered face named '{name}'."

    if action == "register":
        name = (params.get("name") or "").strip()
        if not name:
            return "⚠️ Please provide a 'name' to register."

        # Try several frames to get a good capture
        frame = best_frame = None
        best_locs = []
        for _ in range(6):
            frame = _get_camera_frame(warmup=2)
            if frame is None:
                continue
            locs = face_recognition.face_locations(frame)
            if locs:
                best_frame = frame
                best_locs = locs
                break
            time.sleep(0.3)

        if best_frame is None or not best_locs:
            return "⚠️ No face detected. Ensure good lighting and look at the camera."

        encoding = face_recognition.face_encodings(best_frame, best_locs)
        if not encoding:
            return "⚠️ Could not generate face encoding. Try better lighting."

        # Save annotated image
        import cv2
        top, right, bottom, left = best_locs[0]
        cv2.rectangle(best_frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.putText(best_frame, name, (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imwrite(str(_FACES_DIR / f"{name}.jpg"), best_frame)

        # Cache encoding
        np.save(str(_FACES_DIR / f"{name}.npy"), encoding[0])

        _log_event("face_register", f"Registered face: {name}")
        msg = f"✅ Face registered for '{name}'."
        if speak:
            speak(msg)
        return msg

    # ── verify (default) ──
    frame = _get_camera_frame()
    if frame is None:
        return "⚠️ Could not access camera for verification."

    known_encodings, known_names = _load_known_faces()
    if not known_encodings:
        return "📷 No faces registered yet. Use 'register' first."

    face_locations = face_recognition.face_locations(frame)
    if not face_locations:
        return "🚫 No face visible. Please look at the camera."

    face_encodings = face_recognition.face_encodings(frame, face_locations)
    tolerance = fu_cfg.get("tolerance", 0.5)

    matches = face_recognition.compare_faces(known_encodings, face_encodings[0],
                                             tolerance=tolerance)

    if True in matches:
        idx = matches.index(True)
        name = known_names[idx]
        distances = face_recognition.face_distance(known_encodings, face_encodings[0])
        confidence = max(0.0, min(100.0, (1.0 - distances[idx]) * 100))
        _log_event("face_verify", f"Verified: {name} ({confidence:.0f}%)")
        return f"✅ Face verified: {name} (confidence: {confidence:.0f}%)"

    _log_event("face_verify", "Unknown face — no match", "warning")
    return "🚫 Face not recognized. Access denied."


# ═════════════════════════════════════════════════════════════════════════
#  2. VOICE AUTHENTICATION
# ═════════════════════════════════════════════════════════════════════════

def _dct_type2(data: np.ndarray, axis: int = 0, norm: str = "ortho") -> np.ndarray:
    """
    Pure-numpy type-II DCT (what scipy.fft.dct with type=2 computes).
    Works along the given axis and optionally applies ortho-normalization.
    """
    n = data.shape[axis]
    # Build the DCT-II matrix: C[k, i] = cos(pi*k*(i+0.5)/n)
    k = np.arange(n, dtype=np.float64).reshape(-1, 1)
    i = np.arange(n, dtype=np.float64).reshape(1, -1)
    dct_mat = np.cos(np.pi * k * (i + 0.5) / n)
    if norm == "ortho":
        dct_mat[0] *= np.sqrt(1.0 / (4 * n))
        dct_mat[1:] *= np.sqrt(1.0 / (2 * n))
    # Move the axis, apply, move back
    data_swapped = np.moveaxis(data, axis, -1)
    result = np.dot(data_swapped, dct_mat.T)
    result = np.moveaxis(result, -1, axis)
    return result


def _extract_voice_features(audio: np.ndarray, sample_rate: int = 16000) -> dict:
    """
    Extract a voiceprint from raw audio using spectral features, MFCC-like
    coefficients, pitch, and energy statistics.
    """

    # Pre-emphasis
    pre_emphasis = 0.97
    emphasized = np.append(audio[0], audio[1:] - pre_emphasis * audio[:-1])

    # Framing
    frame_len = int(round(0.025 * sample_rate))   # 25 ms
    frame_step = int(round(0.010 * sample_rate))   # 10 ms
    sig_len = len(emphasized)
    num_frames = int(np.ceil(float(abs(sig_len - frame_len)) / frame_step))
    pad_len = num_frames * frame_step + frame_len
    padded = np.concatenate((emphasized, np.zeros(pad_len - sig_len)))

    indices = np.tile(np.arange(frame_len), (num_frames, 1)) + \
              np.tile(np.arange(0, num_frames * frame_step, frame_step),
                      (frame_len, 1)).T
    frames = padded[indices.astype(np.int32, copy=False)]
    frames *= np.hamming(frame_len)

    # Power spectrum
    nfft = 512
    mag_frames = np.abs(np.fft.rfft(frames, nfft))
    pow_frames = (1.0 / nfft) * (mag_frames ** 2)

    # Mel filterbank
    nfilt = 26
    low_freq, high_freq = 0, sample_rate / 2
    mel_points = 2595 * np.log10(1 + np.arange(0, nfilt + 2) *
                                 (high_freq - low_freq) / (nfilt + 1) / 700)
    fft_bins = np.floor((nfft + 1) * (700 * (10 ** (mel_points / 2595) - 1) /
                        sample_rate)).astype(int)
    fbank = np.zeros((nfilt, nfft // 2 + 1))
    for m in range(1, nfilt + 1):
        f_m_minus, f_m, f_m_plus = fft_bins[m - 1], fft_bins[m], fft_bins[m + 1]
        for k in range(f_m_minus, f_m):
            fbank[m - 1, k] = (k - f_m_minus) / (f_m - f_m_minus)
        for k in range(f_m, f_m_plus):
            fbank[m - 1, k] = (f_m_plus - k) / (f_m_plus - f_m)

    filter_banks = np.dot(pow_frames, fbank.T)
    filter_banks = np.where(filter_banks == 0, np.finfo(float).eps, filter_banks)
    filter_banks = 20 * np.log10(filter_banks)
    mfcc = _dct_type2(filter_banks, axis=1, norm="ortho")[:, :13]

    # Spectral centroid
    centroid = (np.sum(mag_frames * np.arange(mag_frames.shape[1]), axis=1) /
                (np.sum(mag_frames, axis=1) + 1e-10))

    # Spectral rolloff (85th percentile)
    rolloff = np.array([
        np.where(np.cumsum(mag_frames[i]) >= 0.85 * np.sum(mag_frames[i]))[0][0]
        if np.sum(mag_frames[i]) > 0 else 0
        for i in range(mag_frames.shape[0])
    ])

    # Pitch via autocorrelation
    pitch = np.zeros(num_frames)
    for i in range(num_frames):
        f = frames[i]
        corr = np.correlate(f, f, mode="full")
        corr = corr[len(corr) // 2:]
        if len(corr) > 40:
            lo = max(int(sample_rate / 500), 1)          # ~500 Hz max
            hi = min(int(sample_rate / 50), len(corr) - 1)  # ~50 Hz min
            seg = corr[lo:hi + 1]
            if len(seg) > 0 and np.max(seg) > 0:
                pk = np.argmax(seg) + lo
                if corr[pk] > 0.3 * corr[0]:
                    pitch[i] = sample_rate / pk

    non_zero_pitch = pitch[pitch > 0]

    return {
        "mfcc_mean": np.mean(mfcc, axis=0).tolist(),
        "mfcc_std": np.std(mfcc, axis=0).tolist(),
        "centroid_mean": float(np.mean(centroid)),
        "centroid_std": float(np.std(centroid)),
        "rolloff_mean": float(np.mean(rolloff)),
        "rolloff_std": float(np.std(rolloff)),
        "pitch_mean": float(np.mean(non_zero_pitch)) if len(non_zero_pitch) > 0 else 0.0,
        "pitch_std": float(np.std(non_zero_pitch)) if len(non_zero_pitch) > 0 else 0.0,
        "energy_mean": float(np.mean(np.sum(pow_frames, axis=1))),
        "energy_std": float(np.std(np.sum(pow_frames, axis=1))),
        "zcr_mean": float(np.mean(np.sum(np.abs(np.diff(np.sign(frames), axis=1)),
                               axis=1) / (2 * frame_len))),
        "duration": float(len(audio) / sample_rate),
    }


def _cosine_similarity(a: list, b: list) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    return 0.0 if denom == 0 else float(np.dot(a_arr, b_arr) / denom)


def _compare_voiceprints(fp1: dict, fp2: dict) -> float:
    """Return a 0‑1 similarity between two voiceprints."""
    mfcc_sim = _cosine_similarity(fp1["mfcc_mean"], fp2["mfcc_mean"])

    # Centroid proximity
    c1, c2 = fp1.get("centroid_mean", 0), fp2.get("centroid_mean", 0)
    denom = max(c1, c2, 1.0)
    sc_sim = max(0.0, 1.0 - abs(c1 - c2) / denom)

    # Pitch proximity
    p1, p2 = fp1.get("pitch_mean", 0), fp2.get("pitch_mean", 0)
    if p1 > 0 and p2 > 0:
        pitch_sim = max(0.0, 1.0 - abs(p1 - p2) / max(p1, p2, 1.0))
    else:
        pitch_sim = 0.5

    return max(0.0, min(1.0, mfcc_sim * 0.6 + sc_sim * 0.2 + pitch_sim * 0.2))


def voice_auth(parameters: dict, **kwargs) -> str:
    """
    Voice Authentication — Verify identity via acoustic voiceprint.

    Actions:
      verify   — record a short voice sample and match against stored prints
      register — record and save a voiceprint for <name>
      list     — show all registered voiceprints
      delete   — remove a voiceprint by name
      status   — show voice-auth configuration

    Parameters:
      action   (str) — verify | register | list | delete | status
      name     (str) — label for register / delete
      duration (int) — recording length in seconds (2‑10, default 3)
    """
    params = parameters or {}
    action = params.get("action", "verify").strip().lower()
    speak = kwargs.get("speak")
    duration = max(2, min(10, int(params.get("duration", 3))))

    config = _load_config()
    va_cfg = config.get("voice_auth", {})

    if action == "status":
        count = len(list(_VOICEPRINTS_DIR.glob("*.json")))
        return (
            f"🎤 Voice Auth Status\n"
            f"  Enabled:        {va_cfg.get('enabled', False)}\n"
            f"  Voices known:   {count}\n"
            f"  Match threshold: {va_cfg.get('threshold', 0.7)}\n"
            f"  Data dir:       {_VOICEPRINTS_DIR}"
        )

    if not va_cfg.get("enabled", False) and action not in ("register", "status"):
        return "🎤 Voice authentication is disabled. Enable it in security settings."

    if action == "list":
        vps = list(_VOICEPRINTS_DIR.glob("*.json"))
        if not vps:
            return "🎤 No registered voiceprints. Use 'register' first."
        return "🎤 Registered voiceprints:\n  " + "\n  ".join(f"• {vp.stem}" for vp in vps)

    if action == "delete":
        name = (params.get("name") or "").strip()
        if not name:
            return "⚠️ Please provide a 'name' to delete."
        vp_path = _VOICEPRINTS_DIR / f"{name}.json"
        if vp_path.exists():
            vp_path.unlink()
            _log_event("voice_delete", f"Deleted voiceprint: {name}")
            return f"🗑️ Voiceprint '{name}' deleted."
        return f"⚠️ No voiceprint named '{name}'."

    if action == "register":
        name = (params.get("name") or "").strip()
        if not name:
            return "⚠️ Please provide a 'name' for registration."

        if speak:
            speak(f"Recording voice sample for {name}. Speak naturally for {duration} seconds.")

        audio = _record_audio(duration)
        if audio is None:
            return "⚠️ Could not record audio. Check your microphone."

        features = _extract_voice_features(audio)
        (_VOICEPRINTS_DIR / f"{name}.json").write_text(
            json.dumps(features, indent=2), encoding="utf-8")

        _log_event("voice_register", f"Registered voiceprint: {name}")
        msg = f"✅ Voiceprint registered for '{name}'."
        if speak:
            speak(msg)
        return msg

    # ── verify (default) ──
    threshold = va_cfg.get("threshold", 0.7)
    known_vps = {}
    for vp_file in _VOICEPRINTS_DIR.glob("*.json"):
        known_vps[vp_file.stem] = json.loads(vp_file.read_text(encoding="utf-8"))

    if not known_vps:
        return "🎤 No registered voiceprints. Use 'register' first."

    if speak:
        speak("Recording for voice verification. Please speak now.")

    audio = _record_audio(duration)
    if audio is None:
        return "⚠️ Could not record audio."

    features = _extract_voice_features(audio)

    best_name, best_score = "", 0.0
    for name, vp in known_vps.items():
        score = _compare_voiceprints(features, vp)
        if score > best_score:
            best_score = score
            best_name = name

    if best_score >= threshold:
        pct = round(best_score * 100, 1)
        _log_event("voice_verify", f"Verified: {best_name} ({pct}%)")
        return f"✅ Voice verified: {best_name} (confidence: {pct}%)"

    _log_event("voice_verify", f"No match — best: {best_name} ({best_score:.2f})", "warning")
    return (f"🚫 Voice not recognized. Best match: {best_name} "
            f"(score: {best_score:.2f}, threshold: {threshold})")


# ═════════════════════════════════════════════════════════════════════════
#  3. UNKNOWN PERSON ALERT
# ═════════════════════════════════════════════════════════════════════════

_unknown_active = False
_unknown_stop = threading.Event()
_unknown_thread: Optional[threading.Thread] = None


def _unknown_loop(interval: int, speak_cb: Optional[Callable]):
    """Background worker — watches for faces that don't match known ones."""
    global _unknown_active

    try:
        import face_recognition
    except ImportError:
        print("[Security] face_recognition unavailable — cannot detect persons.")
        _unknown_active = False
        return

    known_encodings, known_names = _load_known_faces()
    if not known_encodings:
        print("[Security] No known faces loaded — unknown-person monitor idle.")
        _unknown_active = False
        return

    consecutive = 0

    while not _unknown_stop.wait(interval):
        if _unknown_stop.is_set():
            break

        frame = _get_camera_frame(warmup=2)
        if frame is None:
            continue

        face_locations = face_recognition.face_locations(frame)
        if not face_locations:
            consecutive = 0
            continue

        face_encodings = face_recognition.face_encodings(frame, face_locations)

        any_known = False
        for encoding in face_encodings:
            matches = face_recognition.compare_faces(known_encodings, encoding,
                                                     tolerance=0.5)
            if True in matches:
                any_known = True
                break

        if not any_known:
            consecutive += 1
            if consecutive >= 2:
                ts = datetime.now().strftime("%H:%M:%S")
                msg = f"🚨 Unknown person detected at {ts}! ({len(face_locations)} face(s))"
                _notify("🔐 Security Alert", msg, duration=10)
                _log_event("unknown_person", msg, "warning")
                if speak_cb:
                    speak_cb(f"Security alert. Unknown person detected at your desk. {msg}")
                consecutive = 0
        else:
            consecutive = 0

    _unknown_active = False


def unknown_person_alert(parameters: dict, **kwargs) -> str:
    """
    Unknown Person Alert — background camera monitor for unrecognised faces.

    Actions:
      start  — begin background monitoring
      stop   — stop monitoring
      status — show current state

    Parameters:
      action   (str) — start | stop | status
      interval (int) — seconds between camera checks (5‑300, default 10)
    """
    global _unknown_active, _unknown_thread, _unknown_stop

    params = parameters or {}
    action = params.get("action", "status").strip().lower()
    interval = max(5, min(300, int(params.get("interval", 10))))
    speak = kwargs.get("speak")

    if action == "status":
        face_count = len(list(_FACES_DIR.glob("*.npy")))
        if not face_count:
            face_count = len(list(_FACES_DIR.glob("*.jpg")))
        return (
            f"👁️ Unknown Person Alert\n"
            f"  Active:         {_unknown_active}\n"
            f"  Check interval: {interval}s\n"
            f"  Known faces:    {face_count}\n"
        )

    if action == "start":
        if _unknown_active:
            return "👁️ Unknown-person monitoring is already active."

        if not list(_FACES_DIR.glob("*.npy")) and not list(_FACES_DIR.glob("*.jpg")):
            return "⚠️ No known faces registered. Use 'face_unlock' with action 'register' first."

        _unknown_stop.clear()
        _unknown_active = True
        _unknown_thread = threading.Thread(
            target=_unknown_loop, args=(interval, speak), daemon=True)
        _unknown_thread.start()

        cfg = _load_config()
        cfg["unknown_person_alert"]["enabled"] = True
        cfg["unknown_person_alert"]["interval"] = interval
        _save_config(cfg)

        _log_event("unknown_person_start", f"Monitoring started (interval={interval}s)")
        return f"👁️ Unknown-person monitoring started (check every {interval}s)."

    if action == "stop":
        if not _unknown_active:
            return "👁️ Monitoring is not active."
        _unknown_stop.set()
        _unknown_active = False
        cfg = _load_config()
        cfg["unknown_person_alert"]["enabled"] = False
        _save_config(cfg)
        _log_event("unknown_person_stop", "Monitoring stopped")
        return "👁️ Unknown-person monitoring stopped."

    return "⚠️ Unknown action. Use: start, stop, or status."


# ═════════════════════════════════════════════════════════════════════════
#  4. WEBCAM MONITOR
# ═════════════════════════════════════════════════════════════════════════

_wc_active = False
_wc_stop = threading.Event()
_wc_thread: Optional[threading.Thread] = None
_wc_history: list = []


def _is_camera_in_use() -> bool:
    """Return True if the camera cannot be opened (likely in use elsewhere)."""
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, _ = cap.read()
            cap.release()
            return not ret  # opened but no frame → unusual
        return True  # cannot open → likely locked by another app
    except Exception:
        return False


def _wc_loop(interval: int, speak_cb: Optional[Callable]):
    global _wc_active, _wc_history

    last_state = None
    sustained_count = 0

    while not _wc_stop.wait(interval):
        if _wc_stop.is_set():
            break

        in_use = _is_camera_in_use()
        ts = datetime.now().strftime("%H:%M:%S")

        entry = {"time": ts, "event": "in_use" if in_use else "idle"}
        _wc_history.append(entry)
        if len(_wc_history) > 500:
            _wc_history = _wc_history[-250:]

        if in_use != last_state and last_state is not None:
            sustained_count = 1 if in_use else 0
            if in_use:
                msg = f"📷 Camera access detected at {ts}!"
                _notify("🔐 Camera Monitor", msg, duration=8)
                _log_event("webcam_access", f"Camera accessed by another application", "info")
                if speak_cb:
                    speak_cb("Security: Another application just accessed your camera.")
        elif in_use:
            sustained_count += 1

        last_state = in_use

    _wc_active = False


def webcam_monitor(parameters: dict, **kwargs) -> str:
    """
    Webcam Monitor — watch for camera access by other applications.

    Actions:
      start   — begin background monitoring
      stop    — stop monitoring
      status  — show current state and recent activity
      history — show the last 20 camera events

    Parameters:
      action   (str) — start | stop | status | history
      interval (int) — seconds between polls (2‑60, default 5)
    """
    global _wc_active, _wc_thread, _wc_stop

    params = parameters or {}
    action = params.get("action", "status").strip().lower()
    interval = max(2, min(60, int(params.get("interval", 5))))
    speak = kwargs.get("speak")

    if action == "status":
        recent = _wc_history[-5:] if _wc_history else []
        lines = ""
        if recent:
            lines = "\n  Recent:\n  " + "\n  ".join(
                f"• [{e['time']}] {e['event']}" for e in recent)
        return (
            f"📷 Webcam Monitor\n"
            f"  Active:          {_wc_active}\n"
            f"  Poll interval:   {interval}s\n"
            f"  Events recorded: {len(_wc_history)}{lines}"
        )

    if action == "start":
        if _wc_active:
            return "📷 Webcam monitor is already active."
        _wc_stop.clear()
        _wc_active = True
        _wc_thread = threading.Thread(
            target=_wc_loop, args=(interval, speak), daemon=True)
        _wc_thread.start()

        cfg = _load_config()
        cfg["webcam_monitor"]["enabled"] = True
        cfg["webcam_monitor"]["interval"] = interval
        _save_config(cfg)

        _log_event("webcam_monitor_start", f"Started (interval={interval}s)")
        return f"📷 Webcam monitor started (poll every {interval}s)."

    if action == "stop":
        if not _wc_active:
            return "📷 Webcam monitor is not active."
        _wc_stop.set()
        _wc_active = False
        cfg = _load_config()
        cfg["webcam_monitor"]["enabled"] = False
        _save_config(cfg)
        _log_event("webcam_monitor_stop", "Stopped")
        return "📷 Webcam monitor stopped."

    if action == "history":
        if not _wc_history:
            return "📷 No camera events recorded yet."
        recent = _wc_history[-20:]
        return ("📷 Recent Camera Activity\n" +
                "\n".join(f"  [{e['time']}] {e['event']}" for e in recent))

    return "⚠️ Unknown action. Use: start, stop, status, or history."


# ═════════════════════════════════════════════════════════════════════════
#  5. USB DEVICE MONITOR
# ═════════════════════════════════════════════════════════════════════════

_usb_active = False
_usb_stop = threading.Event()
_usb_thread: Optional[threading.Thread] = None
_usb_known: set = set()
_usb_history: list = []


def _poll_usb_drives() -> set:
    """Return a set of human-readable USB drive descriptors via psutil."""
    drives: set = set()
    try:
        for part in psutil.disk_partitions():
            opts = str(part.opts).lower()
            if "removable" in opts:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    size_gb = usage.total // (1024 ** 3)
                    drives.add(f"{part.device}  ({part.mountpoint})  [{size_gb} GB]")
                except Exception:
                    drives.add(f"{part.device}  ({part.mountpoint})")
    except Exception as e:
        print(f"[Security] USB poll error: {e}")
    return drives


def _usb_loop(interval: int, speak_cb: Optional[Callable]):
    global _usb_active, _usb_known, _usb_history

    _usb_known = _poll_usb_drives()
    print(f"[Security] 🔌 Initial USB devices: {len(_usb_known)}")

    while not _usb_stop.wait(interval):
        if _usb_stop.is_set():
            break

        current = _poll_usb_drives()
        ts = datetime.now().strftime("%H:%M:%S")

        new_devs = current - _usb_known
        removed = _usb_known - current

        for dev in new_devs:
            msg = f"🔌 USB connected: {dev}  [{ts}]"
            _notify("🔐 USB Monitor", msg, duration=8)
            _log_event("usb_connected", msg, "info")
            _usb_history.append({"time": ts, "event": "connected", "device": dev})
            if speak_cb:
                speak_cb(f"New USB device connected: {dev}")

        for dev in removed:
            msg = f"🔌 USB disconnected: {dev}  [{ts}]"
            _log_event("usb_disconnected", msg, "info")
            _usb_history.append({"time": ts, "event": "disconnected", "device": dev})

        _usb_known = current
        if len(_usb_history) > 500:
            _usb_history = _usb_history[-250:]

    _usb_active = False


def usb_monitor(parameters: dict, **kwargs) -> str:
    """
    USB Device Monitor — track USB drive connections / disconnections.

    Actions:
      start   — begin background USB monitoring
      stop    — stop monitoring
      status  — show current state and connected drives
      history — show the last 20 USB events

    Parameters:
      action   (str) — start | stop | status | history
      interval (int) — seconds between polls (2‑60, default 5)
    """
    global _usb_active, _usb_thread, _usb_stop

    params = parameters or {}
    action = params.get("action", "status").strip().lower()
    interval = max(2, min(60, int(params.get("interval", 5))))
    speak = kwargs.get("speak")

    if action == "status":
        current = _poll_usb_drives()
        dev_lines = "\n  ".join(f"• {d}" for d in current) if current else "  (none)"
        recent = _usb_history[-5:] if _usb_history else []
        recent_lines = ""
        if recent:
            recent_lines = "\n  Recent:\n  " + "\n  ".join(
                f"• [{e['time']}] {e['event']} — {e['device']}" for e in recent)

        return (
            f"🔌 USB Device Monitor\n"
            f"  Active:          {_usb_active}\n"
            f"  Poll interval:   {interval}s\n"
            f"  Connected:\n{dev_lines}\n"
            f"  Events recorded: {len(_usb_history)}{recent_lines}"
        )

    if action == "start":
        if _usb_active:
            return "🔌 USB monitor is already active."
        _usb_stop.clear()
        _usb_active = True
        _usb_thread = threading.Thread(
            target=_usb_loop, args=(interval, speak), daemon=True)
        _usb_thread.start()

        cfg = _load_config()
        cfg["usb_monitor"]["enabled"] = True
        _save_config(cfg)

        _log_event("usb_monitor_start", f"Started (interval={interval}s)")
        return f"🔌 USB monitor started (poll every {interval}s)."

    if action == "stop":
        if not _usb_active:
            return "🔌 USB monitor is not active."
        _usb_stop.set()
        _usb_active = False
        cfg = _load_config()
        cfg["usb_monitor"]["enabled"] = False
        _save_config(cfg)
        _log_event("usb_monitor_stop", "Stopped")
        return "🔌 USB monitor stopped."

    if action == "history":
        if not _usb_history:
            return "🔌 No USB events recorded yet."
        recent = _usb_history[-20:]
        return ("🔌 Recent USB Activity\n" +
                "\n".join(f"  [{e['time']}] {e['event']}: {e['device']}" for e in recent))

    return "⚠️ Unknown action. Use: start, stop, status, or history."
