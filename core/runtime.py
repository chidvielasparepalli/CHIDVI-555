"""
Application runtime bootstrap for CHIDVI 555.

This module owns startup sequencing and dependency construction. The concrete
UI and live-session classes are injected so `main.py` can remain a thin entry
point while later refactors move Gemini/audio responsibilities behind managers.
"""

import asyncio
import threading
from typing import Callable


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
