"""
Application runtime bootstrap for CHIDVI 555.

This module owns startup sequencing and dependency construction. The concrete
UI and live-session classes are injected so `main.py` can remain a thin entry
point while later refactors move Gemini/audio responsibilities behind managers.
"""

import asyncio
import atexit
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen


_RENDERER_URL = "http://127.0.0.1:5173/"
_renderer_process: subprocess.Popen | None = None


def _renderer_is_available() -> bool:
    try:
        with urlopen(_RENDERER_URL, timeout=0.5) as response:
            return 200 <= response.status < 400
    except (URLError, OSError):
        return False


def ensure_renderer_server() -> None:
    """Reuse or start the local Vite renderer before WebEngine loads it."""
    global _renderer_process

    if _renderer_is_available():
        return

    project_root = Path(__file__).resolve().parents[1]
    web_root = project_root / "web"
    npm_command = "npm.cmd" if os.name == "nt" else "npm"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    _renderer_process = subprocess.Popen(
        [npm_command, "run", "dev", "--", "--host", "127.0.0.1"],
        cwd=web_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    for _ in range(40):
        if _renderer_is_available():
            return
        if _renderer_process.poll() is not None:
            break
        time.sleep(0.25)

    raise RuntimeError("The local VRM renderer could not start on port 5173.")


def _stop_renderer_server() -> None:
    if _renderer_process and _renderer_process.poll() is None:
        _renderer_process.terminate()


atexit.register(_stop_renderer_server)


def start_background_runtime(
    ui,
    live_factory: Callable,
    run_async: Callable = asyncio.run,
) -> threading.Thread:
    """Start the assistant runtime loop in a daemon thread."""

    def runner():
        ui.wait_for_api_key()
        live = live_factory(ui)
        try:
            run_async(live.run())
        except KeyboardInterrupt:
            print("Shutting down...")

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread


def run_desktop_app(
    ui_factory: Callable,
    live_factory: Callable,
    face_path: str = "face.png",
    run_async: Callable = asyncio.run,
) -> None:
    """Create the desktop UI and start the background assistant runtime."""
    ui = ui_factory(face_path)
    start_background_runtime(ui, live_factory, run_async=run_async)
    ui.root.mainloop()
