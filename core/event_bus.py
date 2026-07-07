"""
Event system for CHIDVI 555.

Implements a publish-subscribe pattern for system events.
Allows decoupled communication between modules.
"""

from typing import Callable, List, Dict, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import threading
from core.logging import get_logger

logger = get_logger(__name__)


class EventType(Enum):
    """System event types."""
    
    # Personality events
    PERSONALITY_CHANGED = "personality_changed"
    PERSONALITY_LOADING = "personality_loading"
    PERSONALITY_LOADED = "personality_loaded"
    
    # Session events
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    SESSION_ERROR = "session_error"
    SESSION_RECONNECTING = "session_reconnecting"
    
    # Audio events
    AUDIO_STARTED = "audio_started"
    AUDIO_STOPPED = "audio_stopped"
    AUDIO_ERROR = "audio_error"
    AUDIO_MUTED = "audio_muted"
    AUDIO_UNMUTED = "audio_unmuted"
    
    # Command events
    COMMAND_RECEIVED = "command_received"
    COMMAND_LOCAL = "command_local"
    COMMAND_REMOTE = "command_remote"
    COMMAND_EXECUTED = "command_executed"
    COMMAND_FAILED = "command_failed"
    
    # Avatar events
    AVATAR_STATE_CHANGED = "avatar_state_changed"
    AVATAR_EMOTION_CHANGED = "avatar_emotion_changed"
    
    # UI events
    UI_STATE_CHANGED = "ui_state_changed"
    UI_THEME_CHANGED = "ui_theme_changed"
    
    # Gemini/API events
    GEMINI_STREAMING_START = "gemini_streaming_start"
    GEMINI_STREAMING_END = "gemini_streaming_end"
    GEMINI_TOOL_CALL = "gemini_tool_call"
    GEMINI_API_ERROR = "gemini_api_error"
    GEMINI_KEY_ROTATED = "gemini_key_rotated"
    
    # System events
    SYSTEM_READY = "system_ready"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_ERROR = "system_error"


@dataclass
class Event:
    """A system event."""
    
    type: EventType
    data: Dict[str, Any]
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class EventBus:
    """
    Central event bus for publish-subscribe communication.
    
    Allows modules to communicate without direct dependencies.
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._lock = threading.RLock()
    
    def subscribe(self, event_type: EventType, callback: Callable) -> Callable:
        """
        Subscribe to an event type.
        
        Args:
            event_type: The type of event to subscribe to
            callback: Function to call when event is published
                     Signature: callback(event: Event) -> None
        
        Returns:
            Unsubscribe function to remove this subscription
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            self._subscribers[event_type].append(callback)
            logger.debug(f"Subscribed to {event_type.value}")
            
            # Return unsubscribe function
            def unsubscribe():
                self.unsubscribe(event_type, callback)
            
            return unsubscribe
    
    def unsubscribe(self, event_type: EventType, callback: Callable):
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                    logger.debug(f"Unsubscribed from {event_type.value}")
                except ValueError:
                    pass
    
    def publish(self, event: Event, async_mode: bool = False):
        """
        Publish an event to all subscribers.
        
        Args:
            event: The event to publish
            async_mode: If True, call subscribers in separate threads (non-blocking)
        """
        with self._lock:
            subscribers = self._subscribers.get(event.type, [])
        
        logger.debug(f"Publishing event: {event.type.value} with data: {event.data}")
        
        if async_mode:
            for callback in subscribers:
                thread = threading.Thread(target=callback, args=(event,), daemon=True)
                thread.start()
        else:
            for callback in subscribers:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in event handler for {event.type.value}: {e}")
    
    def clear(self):
        """Clear all subscriptions."""
        with self._lock:
            self._subscribers.clear()
    
    def get_subscriber_count(self, event_type: EventType) -> int:
        """Get the number of subscribers for an event type."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))


# Global event bus instance
event_bus = EventBus()


# Helper functions for easier event publishing
def publish_event(event_type: EventType, data: Dict[str, Any] = None, async_mode: bool = False):
    """Publish an event."""
    if data is None:
        data = {}
    event = Event(type=event_type, data=data)
    event_bus.publish(event, async_mode=async_mode)


def subscribe_to_event(event_type: EventType, callback: Callable) -> Callable:
    """Subscribe to an event type."""
    return event_bus.subscribe(event_type, callback)
