"""
Central application state for CHIDVI 555.

This module is deliberately independent from PyQt, Gemini, and sounddevice.
Managers can share this state without reaching into UI or session objects.
"""

from dataclasses import dataclass, replace
from enum import Enum
import threading
from typing import Callable, List

from core.event_bus import EventType, publish_event


class RuntimeState(Enum):
    STARTING = "starting"
    THINKING = "thinking"
    LISTENING = "listening"
    SPEAKING = "speaking"
    MUTED = "muted"
    RECONNECTING = "reconnecting"
    STOPPED = "stopped"


@dataclass(frozen=True)
class AppState:
    runtime: RuntimeState = RuntimeState.STARTING
    muted: bool = False
    speaking: bool = False
    active_personality: str = "CHIDVI"
    active_avatar: str = "Chidvi.vrm"


class StateManager:
    """Thread-safe application state manager."""

    def __init__(self, initial_state: AppState | None = None):
        self._state = initial_state or AppState()
        self._lock = threading.RLock()
        self._subscribers: List[Callable[[AppState], None]] = []

    def snapshot(self) -> AppState:
        with self._lock:
            return self._state

    def subscribe(self, callback: Callable[[AppState], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe():
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def set_runtime(self, runtime: RuntimeState | str) -> AppState:
        if isinstance(runtime, str):
            runtime = RuntimeState[runtime.upper()]

        speaking = runtime == RuntimeState.SPEAKING
        return self._update(runtime=runtime, speaking=speaking)

    def set_muted(self, muted: bool) -> AppState:
        state = self._update(
            muted=bool(muted),
            runtime=RuntimeState.MUTED if muted else RuntimeState.LISTENING,
            speaking=False if muted else self.snapshot().speaking,
        )
        publish_event(EventType.AUDIO_MUTED if muted else EventType.AUDIO_UNMUTED)
        return state

    def set_personality(self, personality: str, avatar: str | None = None) -> AppState:
        personality = personality.upper()
        if avatar is None:
            avatar = "Hinata.vrm" if personality == "HINATA" else "Chidvi.vrm"
        return self._update(active_personality=personality, active_avatar=avatar)

    def set_avatar(self, avatar: str) -> AppState:
        return self._update(active_avatar=avatar)

    def _update(self, **changes) -> AppState:
        with self._lock:
            new_state = replace(self._state, **changes)
            if new_state == self._state:
                return self._state

            self._state = new_state
            subscribers = list(self._subscribers)

        publish_event(
            EventType.UI_STATE_CHANGED,
            {
                "runtime": new_state.runtime.value,
                "muted": new_state.muted,
                "speaking": new_state.speaking,
                "active_personality": new_state.active_personality,
                "active_avatar": new_state.active_avatar,
            },
        )

        for callback in subscribers:
            callback(new_state)

        return new_state


_state_manager: StateManager | None = None
_state_manager_lock = threading.Lock()


def get_state_manager() -> StateManager:
    global _state_manager
    if _state_manager is None:
        with _state_manager_lock:
            if _state_manager is None:
                _state_manager = StateManager()
    return _state_manager
