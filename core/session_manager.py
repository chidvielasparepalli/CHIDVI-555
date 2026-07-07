"""
Session manager for Gemini connections in CHIDVI 555.

Handles:
- Session lifecycle (start, maintain, recover, end)
- Automatic reconnection on failure
- State preservation during recovery
- Conversation history
- Error recovery without exposing errors to user
"""

from typing import Optional, Callable, Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import threading
import asyncio
from core.logging import get_logger
from core.event_bus import publish_event, EventType
from api.key_pool import get_api_key_pool, mark_api_key_rate_limited, mark_api_key_success

logger = get_logger(__name__)


class SessionState(Enum):
    """States of a Gemini session."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSED = "closed"


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    
    timestamp: datetime
    role: str  # "user" or "model"
    content: str
    turn_id: Optional[str] = None


@dataclass
class SessionMetadata:
    """Metadata about a session."""
    
    session_id: str
    personality: str
    created_at: datetime
    last_activity: datetime = field(default_factory=datetime.now)
    conversation_history: List[ConversationTurn] = field(default_factory=list)
    connection_attempts: int = 0
    consecutive_errors: int = 0


class SessionManager:
    """
    Manages Gemini session lifecycle.
    
    Ensures:
    - Sessions can be recovered after disconnects
    - Conversation state is preserved
    - Personality is preserved
    - UI state is preserved
    - Never shows internal errors
    """
    
    def __init__(self):
        self._session_state = SessionState.IDLE
        self._metadata: Optional[SessionMetadata] = None
        self._lock = threading.RLock()
        self._session_object = None  # Will hold the actual Gemini session
        
        # Callbacks
        self._on_session_error: Optional[Callable] = None
        self._on_session_recovered: Optional[Callable] = None
        self._on_state_changed: Optional[Callable] = None
    
    def set_callbacks(self,
                      on_error: Callable = None,
                      on_recovered: Callable = None,
                      on_state_changed: Callable = None):
        """Set session callbacks."""
        if on_error:
            self._on_session_error = on_error
        if on_recovered:
            self._on_session_recovered = on_recovered
        if on_state_changed:
            self._on_state_changed = on_state_changed
    
    async def start_session(self, session_id: str, personality: str,
                          session_creator: Callable) -> bool:
        """
        Start a new session.
        
        Args:
            session_id: Unique session ID
            personality: Current personality
            session_creator: Async callable that creates the session object
        
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            if self._session_state in [SessionState.ACTIVE, SessionState.INITIALIZING]:
                logger.warning("Session already active")
                return True
            
            self._set_state(SessionState.INITIALIZING)
        
        try:
            logger.info(f"Starting session: {session_id} ({personality})")
            
            # Create session
            self._session_object = await session_creator()
            
            # Create metadata
            with self._lock:
                self._metadata = SessionMetadata(
                    session_id=session_id,
                    personality=personality,
                    created_at=datetime.now(),
                )
            
            with self._lock:
                self._set_state(SessionState.ACTIVE)
            
            publish_event(EventType.SESSION_STARTED, {
                "session_id": session_id,
                "personality": personality,
            })
            
            logger.info(f"Session started successfully: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start session: {e}", exc_info=True)
            with self._lock:
                self._set_state(SessionState.ERROR)
            
            publish_event(EventType.SESSION_ERROR, {
                "error": str(e),
                "phase": "start",
            })
            
            return False
    
    async def end_session(self):
        """End the current session."""
        with self._lock:
            if self._session_state == SessionState.CLOSED:
                return
            
            self._set_state(SessionState.CLOSED)
            session_id = self._metadata.session_id if self._metadata else "unknown"
        
        try:
            logger.info(f"Ending session: {session_id}")
            
            # Close session object if it has a close method
            if self._session_object and hasattr(self._session_object, 'close'):
                await self._session_object.close()
            
            with self._lock:
                self._session_object = None
                self._metadata = None
            
            publish_event(EventType.SESSION_ENDED, {
                "session_id": session_id,
            })
            
            logger.info(f"Session ended: {session_id}")
            
        except Exception as e:
            logger.error(f"Error ending session: {e}")
    
    async def recover_session(self, session_recreator: Callable) -> bool:
        """
        Attempt to recover a failed session.
        
        Preserves:
        - Session ID
        - Personality
        - Conversation history
        - UI state
        
        Args:
            session_recreator: Async callable that recreates the session
        
        Returns:
            True if recovered, False otherwise
        """
        with self._lock:
            if not self._metadata:
                logger.warning("No session metadata to recover")
                return False
            
            if self._metadata.connection_attempts >= 5:
                logger.error("Max recovery attempts reached")
                return False
            
            self._metadata.connection_attempts += 1
            self._set_state(SessionState.RECONNECTING)
        
        try:
            logger.info(f"Recovering session: {self._metadata.session_id}")
            
            publish_event(EventType.SESSION_RECONNECTING, {
                "session_id": self._metadata.session_id,
                "attempt": self._metadata.connection_attempts,
            })
            
            # Wait briefly before reconnecting
            await asyncio.sleep(min(self._metadata.connection_attempts, 5))
            
            # Try to recreate session
            self._session_object = await session_recreator()
            
            with self._lock:
                self._metadata.connection_attempts = 0
                self._metadata.consecutive_errors = 0
                self._set_state(SessionState.ACTIVE)
            
            # Call recovery callback
            if self._on_session_recovered:
                await self._on_session_recovered()
            
            publish_event(EventType.SESSION_STARTED, {
                "type": "recovered",
                "session_id": self._metadata.session_id,
            })
            
            logger.info(f"Session recovered: {self._metadata.session_id}")
            return True
            
        except Exception as e:
            logger.warning(f"Session recovery attempt failed: {e}")
            
            with self._lock:
                self._metadata.consecutive_errors += 1
                if self._metadata.consecutive_errors > 3:
                    self._set_state(SessionState.ERROR)
                else:
                    self._set_state(SessionState.RECONNECTING)
            
            return False
    
    def _set_state(self, state: SessionState):
        """Set session state (with lock already held)."""
        if state != self._session_state:
            old_state = self._session_state
            self._session_state = state
            logger.debug(f"Session state: {old_state.value} -> {state.value}")
            
            if self._on_state_changed:
                self._on_state_changed(state)
    
    def get_state(self) -> SessionState:
        """Get current session state."""
        with self._lock:
            return self._session_state
    
    def get_session(self) -> Optional[Any]:
        """Get the session object."""
        with self._lock:
            return self._session_object
    
    def is_active(self) -> bool:
        """Check if session is active."""
        with self._lock:
            return self._session_state == SessionState.ACTIVE
    
    def record_turn(self, role: str, content: str, turn_id: str = None):
        """Record a conversation turn."""
        with self._lock:
            if not self._metadata:
                return
            
            turn = ConversationTurn(
                timestamp=datetime.now(),
                role=role,
                content=content,
                turn_id=turn_id,
            )
            
            self._metadata.conversation_history.append(turn)
            self._metadata.last_activity = datetime.now()
            
            logger.debug(f"Recorded turn: {role}")
    
    def get_conversation_history(self, limit: int = None) -> List[ConversationTurn]:
        """Get conversation history."""
        with self._lock:
            if not self._metadata:
                return []
            
            history = self._metadata.conversation_history
            if limit:
                history = history[-limit:]
            
            return history.copy()
    
    def handle_error(self, error: str, is_rate_limit: bool = False, key: str = None):
        """
        Handle session error.
        
        Args:
            error: Error message
            is_rate_limit: If True, this is a rate limit error
            key: API key that failed (if applicable)
        """
        logger.warning(f"Session error: {error} (rate_limit={is_rate_limit})")
        
        # Handle rate limits specially
        if is_rate_limit and key:
            mark_api_key_rate_limited(key, cooldown_minutes=60)
        
        with self._lock:
            if self._metadata:
                self._metadata.consecutive_errors += 1
        
        # Call error callback
        if self._on_session_error:
            self._on_session_error(error, is_rate_limit)


# Global instance
_session_manager: Optional[SessionManager] = None
_manager_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    """Get the global session manager."""
    global _session_manager
    
    if _session_manager is None:
        with _manager_lock:
            if _session_manager is None:
                _session_manager = SessionManager()
    
    return _session_manager
