"""
Unified personality manager for CHIDVI 555.

This is the SINGLE SOURCE OF TRUTH for personality management.
Handles:
- Prompt switching
- Avatar switching
- Theme switching
- Voice selection
- Session management
- Memory updates
- Event notifications

Replaces duplicate personality managers throughout the codebase.
"""

from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import threading
import asyncio
from core.config import CONFIG_DIR
from core.logging import get_logger
from core.event_bus import publish_event, subscribe_to_event, EventType

logger = get_logger(__name__)


class PersonalityID(Enum):
    """Available personalities."""
    CHIDVI = "CHIDVI"
    HINATA = "HINATA"


@dataclass
class PersonalityProfile:
    """Profile for a personality."""
    
    id: PersonalityID
    name: str
    system_prompt: str
    voice: str
    theme: str
    animation_style: str
    avatar_model: str
    color_primary: tuple = (0, 100, 150)
    color_secondary: tuple = (100, 50, 150)


class PersonalityManager:
    """
    Centralized personality management.
    
    Single source of truth for active personality.
    Ensures all subsystems stay in sync.
    """
    
    def __init__(self, state_path: Optional[Path] = None):
        self._current_personality: Optional[PersonalityID] = None
        self._profiles: Dict[PersonalityID, PersonalityProfile] = {}
        self._lock = threading.RLock()
        self._session_restart_callback: Optional[Callable] = None
        self._transition_in_progress = False
        self._state_path = Path(state_path) if state_path else CONFIG_DIR / "personality_state.json"
        
        self._load_personalities()
        self._setup_event_listeners()
    
    def _load_personalities(self):
        """Load all available personalities."""
        # CHIDVI Profile
        self._profiles[PersonalityID.CHIDVI] = PersonalityProfile(
            id=PersonalityID.CHIDVI,
            name="CHIDVI",
            system_prompt=self._load_personality_prompt("chidvi"),
            voice="Charon",
            theme="CHIDVI",
            animation_style="professional",
            avatar_model="Chidvi.vrm",
            color_primary=(0, 100, 150),
            color_secondary=(100, 50, 150),
        )
        
        # HINATA Profile
        self._profiles[PersonalityID.HINATA] = PersonalityProfile(
            id=PersonalityID.HINATA,
            name="HINATA",
            system_prompt=self._load_personality_prompt("hinata"),
            voice="Aoede",
            theme="HINATA",
            animation_style="energetic",
            avatar_model="Hinata.vrm",
            color_primary=(200, 50, 100),
            color_secondary=(150, 50, 200),
        )
        
        # Set saved personality or default.
        self._current_personality = self._load_saved_personality() or PersonalityID.CHIDVI
        logger.info("Personalities loaded: CHIDVI, HINATA")

    def _load_saved_personality(self) -> Optional[PersonalityID]:
        try:
            if not self._state_path.exists():
                return None
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return PersonalityID[str(data.get("active_personality", "")).upper()]
        except Exception as exc:
            logger.warning(f"Failed to load saved personality: {exc}")
            return None

    def _save_current_personality(self):
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(
                    {"active_personality": self._current_personality.value},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Failed to save active personality: {exc}")
    
    def _load_personality_prompt(self, name: str) -> str:
        """Load a personality's system prompt."""
        try:
            from personality.chidvi import CHIDVI_SYSTEM_PROMPT
            from personality.hinata import HINATA_SYSTEM_PROMPT
            
            if name.lower() == "chidvi":
                return CHIDVI_SYSTEM_PROMPT
            elif name.lower() == "hinata":
                return HINATA_SYSTEM_PROMPT
        except ImportError:
            pass
        
        return f"You are {name}."
    
    def _setup_event_listeners(self):
        """Set up event listeners for personality changes."""
        subscribe_to_event(EventType.PERSONALITY_CHANGED, self._on_personality_changed)
    
    def _on_personality_changed(self, event):
        """Handle personality change events."""
        logger.debug(f"Personality change event received: {event.data}")
    
    def set_session_restart_callback(self, callback: Callable):
        """
        Set callback for when session needs to restart.
        
        Args:
            callback: Async function that restarts the session
        """
        self._session_restart_callback = callback
    
    def get_current(self) -> PersonalityID:
        """Get current personality."""
        with self._lock:
            return self._current_personality
    
    def get_profile(self, personality: Optional[PersonalityID] = None) -> PersonalityProfile:
        """Get personality profile."""
        if personality is None:
            personality = self.get_current()
        
        return self._profiles[personality]
    
    def get_all_personalities(self) -> List[PersonalityID]:
        """Get list of all available personalities."""
        return list(self._profiles.keys())
    
    def get_system_prompt(self, personality: Optional[PersonalityID] = None) -> str:
        """Get system prompt for personality."""
        profile = self.get_profile(personality)
        return profile.system_prompt
    
    def get_voice(self, personality: Optional[PersonalityID] = None) -> str:
        """Get voice for personality."""
        profile = self.get_profile(personality)
        return profile.voice
    
    def get_theme(self, personality: Optional[PersonalityID] = None) -> str:
        """Get theme for personality."""
        profile = self.get_profile(personality)
        return profile.theme
    
    def get_animation_style(self, personality: Optional[PersonalityID] = None) -> str:
        """Get animation style for personality."""
        profile = self.get_profile(personality)
        return profile.animation_style
    
    def get_avatar_model(self, personality: Optional[PersonalityID] = None) -> str:
        """Get avatar model for personality."""
        profile = self.get_profile(personality)
        return profile.avatar_model
    
    async def switch_to(self, personality: PersonalityID) -> bool:
        """
        Switch to a different personality.
        
        This is a CRITICAL operation that must:
        1. Notify UI of transition
        2. Switch theme
        3. Load new avatar
        4. Restart Gemini session
        5. Update memory context
        
        Args:
            personality: Target personality
        
        Returns:
            True if successful, False otherwise
        """
        if personality not in self._profiles:
            logger.error(f"Unknown personality: {personality}")
            return False
        
        if personality == self._current_personality:
            logger.debug(f"Already using {personality.value}")
            self._save_current_personality()
            return True
        
        with self._lock:
            if self._transition_in_progress:
                logger.warning("Personality transition already in progress")
                return False
            
            self._transition_in_progress = True
        
        try:
            logger.info(f"Switching personality to {personality.value}")
            
            # Publish transition start event
            publish_event(EventType.PERSONALITY_LOADING, {
                "from": self._current_personality.value if self._current_personality else None,
                "to": personality.value,
            })
            
            # Update current personality
            with self._lock:
                self._current_personality = personality
                self._save_current_personality()
            
            profile = self.get_profile(personality)
            
            # Publish theme change event
            publish_event(EventType.UI_THEME_CHANGED, {
                "theme": profile.theme,
                "colors": {
                    "primary": profile.color_primary,
                    "secondary": profile.color_secondary,
                }
            })
            
            # Publish avatar change event
            publish_event(EventType.AVATAR_STATE_CHANGED, {
                "personality": personality.value,
                "model": profile.avatar_model,
                "animation_style": profile.animation_style,
            })
            
            # Restart Gemini session if callback is set
            if self._session_restart_callback:
                logger.debug("Restarting Gemini session...")
                await self._session_restart_callback()
            
            # Publish completion event
            publish_event(EventType.PERSONALITY_CHANGED, {
                "personality": personality.value,
                "profile": {
                    "voice": profile.voice,
                    "theme": profile.theme,
                    "animation_style": profile.animation_style,
                }
            })
            
            logger.info(f"Personality switched to {personality.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to switch personality: {e}", exc_info=True)
            return False
        
        finally:
            with self._lock:
                self._transition_in_progress = False
    
    def is_transition_in_progress(self) -> bool:
        """Check if personality transition is in progress."""
        with self._lock:
            return self._transition_in_progress


# Global singleton instance
_personality_manager: Optional[PersonalityManager] = None
_personality_lock = threading.Lock()


def get_personality_manager() -> PersonalityManager:
    """Get the global personality manager."""
    global _personality_manager
    
    if _personality_manager is None:
        with _personality_lock:
            if _personality_manager is None:
                _personality_manager = PersonalityManager()
    
    return _personality_manager


# Convenience functions
def get_current_personality() -> PersonalityID:
    """Get current personality."""
    return get_personality_manager().get_current()


def get_system_prompt() -> str:
    """Get current system prompt."""
    return get_personality_manager().get_system_prompt()


def get_voice() -> str:
    """Get current voice."""
    return get_personality_manager().get_voice()


def get_theme() -> str:
    """Get current theme."""
    return get_personality_manager().get_theme()


async def switch_personality(personality: str) -> bool:
    """Switch personality."""
    try:
        pid = PersonalityID[personality.upper()]
        return await get_personality_manager().switch_to(pid)
    except KeyError:
        logger.error(f"Unknown personality: {personality}")
        return False


# Backward compatibility aliases
def is_hinata() -> bool:
    """Check if current personality is HINATA."""
    return get_current_personality() == PersonalityID.HINATA


def set_personality(name: str) -> bool:
    """
    Legacy function for backward compatibility.
    Use switch_personality() instead for async-aware switching.
    """
    try:
        pid = PersonalityID[name.upper()]
        manager = get_personality_manager()
        manager._current_personality = pid
        manager._save_current_personality()
        logger.debug(f"Set personality to {pid.value} (sync mode)")
        return True
    except KeyError:
        return False


def get_personality() -> str:
    """Get current personality name (backward compatibility)."""
    return get_current_personality().value
