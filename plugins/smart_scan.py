"""
smart_scan.py — Smart Scan Plugin for CHIDVI 555

Opens the camera with a scanning animation (blue box + moving scan line),
captures a frame, and uses Gemini Vision to analyze it.

Modes:
  - object  : identify the object and describe it
  - food    : identify food and say if it's safe/healthy to eat
  - health  : analyze a person's appearance (health, mood, expression)
"""

import base64
import io
import json
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from google import genai
from google.genai import types as gtypes


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_api_key() -> str:
    key = _load_config().get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key not found in config.")
    return key


# ── Scanning animation ──────────────────────────────────────────────────

_SCAN_DURATION = 4.0       # seconds before capture
_SCAN_LINE_COLOR = (255, 180, 0)    # BGR — bright cyan-blue
_BOX_COLOR = (255, 180, 0)          # BGR
_BOX_THICKNESS = 3
_WINDOW_NAME = "CHIDVI 555 — Smart Scan"
_FRAME_WIDTH = 640
_FRAME_HEIGHT = 480


def _show_scanning_animation() -> Optional[np.ndarray]:
    """
    Opens the camera, draws a scanning box with an animated scan line,
    and returns the final frame after _SCAN_DURATION seconds.
    Returns None if camera cannot be opened.
    """
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[SmartScan] ❌ Could not open camera.")
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, _FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, _FRAME_HEIGHT)

    cv2.namedWindow(_WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(_WINDOW_NAME, _FRAME_WIDTH, _FRAME_HEIGHT)

    start_time = time.time()
    final_frame = None
    scan_speed = 60.0  # pixels per second for scan line

    # Box inset (10 % margin)
    margin_x = int(_FRAME_WIDTH * 0.08)
    margin_y = int(_FRAME_HEIGHT * 0.10)
    box_x1, box_y1 = margin_x, margin_y
    box_x2, box_y2 = _FRAME_WIDTH - margin_x, _FRAME_HEIGHT - margin_y
    box_h = box_y2 - box_y1

    while time.time() - start_time < _SCAN_DURATION:
        ret, frame = cap.read()
        if not ret:
            break

        # Animate scan line — ping-pong from top to bottom
        elapsed = time.time() - start_time
        phase = (elapsed * scan_speed) % (box_h * 2)
        line_y = box_y1 + int(phase) if phase < box_h else box_y1 + int(2 * box_h - phase)
        line_y = max(box_y1 + 2, min(box_y2 - 2, line_y))

        # Draw the scanning box (rectangle border)
        cv2.rectangle(frame, (box_x1, box_y1), (box_x2, box_y2),
                      _BOX_COLOR, _BOX_THICKNESS)

        # Draw corner accents for a tech look
        corner_len = 20
        for (cx, cy, dx, dy) in [
            (box_x1, box_y1, 1, 1), (box_x2, box_y1, -1, 1),
            (box_x1, box_y2, 1, -1), (box_x2, box_y2, -1, -1),
        ]:
            cv2.line(frame, (cx, cy), (cx + corner_len * dx, cy), _BOX_COLOR, 2)
            cv2.line(frame, (cx, cy), (cx, cy + corner_len * dy), _BOX_COLOR, 2)

        # Draw the scan line (horizontal line across the box)
        cv2.line(frame, (box_x1 + 4, line_y), (box_x2 - 4, line_y),
                 _SCAN_LINE_COLOR, 2)

        # Semi-transparent overlay for scan line glow
        overlay = frame.copy()
        cv2.line(overlay, (box_x1 + 4, line_y), (box_x2 - 4, line_y),
                 _SCAN_LINE_COLOR, 6)
        frame = cv2.addWeighted(overlay, 0.25, frame, 0.75, 0)

        # Label
        cv2.putText(frame, "SCANNING...", (box_x1 + 10, box_y1 + 30),
                    cv2.FONT_HERSHEY_DUPLEX, 0.6, _SCAN_LINE_COLOR, 1)

        cv2.imshow(_WINDOW_NAME, frame)

        # Allow early exit with ESC or Q
        key = cv2.waitKey(16) & 0xFF
        if key in (27, ord('q'), ord('Q')):
            break

        final_frame = frame.copy()

    cap.release()
    cv2.destroyWindow(_WINDOW_NAME)

    # If no frame was captured during the loop, grab one final frame
    if final_frame is None:
        ret, final_frame = cap.read()
        cap.release()
        if not ret:
            return None

    return final_frame


# ── Gemini analysis ─────────────────────────────────────────────────────

_SYSTEM_PROMPTS = {
    "object": (
        "You are a smart object scanner. Identify the main object in the image "
        "and tell the user what it is, what it's used for, and any interesting "
        "facts about it. Be conversational and helpful. "
        "If you cannot identify it, say what it looks like."
    ),
    "food": (
        "You are a food safety and nutrition scanner. Identify the food in the image. "
        "Tell the user: (1) what food it is, (2) whether it looks fresh and safe to eat, "
        "(3) whether it is healthy or unhealthy, and (4) any serving suggestions. "
        "If it looks spoiled or unsafe, warn the user clearly."
    ),
    "health": (
        "You are a wellness scanner. Look at the person in the image and provide "
        "a friendly analysis covering: (1) overall appearance, (2) apparent mood or emotion "
        "(happy, sad, neutral, tired, energetic, etc.), (3) general health indicators "
        "(skin tone, posture if visible). Keep it positive and encouraging. "
        "Do NOT diagnose medical conditions. Be supportive."
    ),
}


def _analyze_with_gemini(image_bytes: bytes, mode: str) -> str:
    """Send the captured image to Gemini for analysis."""
    prompt = _SYSTEM_PROMPTS.get(mode, _SYSTEM_PROMPTS["object"])

    client = genai.Client(api_key=_get_api_key())

    # Create image part with inline data
    img_part = gtypes.Part(
        inline_data=gtypes.Blob(
            mime_type="image/jpeg",
            data=image_bytes
        )
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt, img_part],
        config=gtypes.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=512,
        ),
    )

    return response.text.strip() if response.text else "I couldn't analyze that image."


# ── Public API ──────────────────────────────────────────────────────────

def smart_scan(parameters: dict, **kwargs) -> str:
    """
    Main entry point.  Called from the tool dispatch in main.py.

    Parameters:
      mode : "object" | "food" | "health"  (default: "object")
    """
    params = parameters or {}
    mode = params.get("mode", "object").strip().lower()

    if mode not in _SYSTEM_PROMPTS:
        mode = "object"

    print(f"[SmartScan] 🔍 Starting scan in '{mode}' mode...")

    # Step 1 — show scanning animation and capture frame
    frame = _show_scanning_animation()
    if frame is None:
        return "I couldn't access the camera. Please check your webcam."

    print(f"[SmartScan] ✅ Frame captured: {frame.shape[1]}x{frame.shape[0]}")

    # Step 2 — encode to JPEG bytes
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    image_bytes = buf.tobytes()

    print(f"[SmartScan] 📤 Sending {len(image_bytes):,} bytes to Gemini...")

    # Step 3 — analyze with Gemini
    result = _analyze_with_gemini(image_bytes, mode)

    print(f"[SmartScan] 💬 Result: {result[:100]}...")
    return result


if __name__ == "__main__":
    mode = input("Mode (object/food/health): ").strip().lower() or "object"
    result = smart_scan({"mode": mode})
    print(f"\n=== RESULT ===\n{result}")
