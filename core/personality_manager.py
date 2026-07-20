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

from typing import Dict, Optional, Callable, List
from dataclasses import dataclass
import json
from pathlib import Path
import threading
import logging

from core.config import CONFIG_DIR
from core.event_bus import publish_event, subscribe_to_event, EventType
from core.personality_plugin import PluginLoader, PersonalityPlugin, PluginLoaderError

logger = logging.getLogger(__name__)

# Backward compatibility: PersonalityID enum replaced by string-based IDs.
# Code that used `PersonalityID[name]` should use just `name` directly.
# Code that used `profile.id.value` should use `profile.id` (already a string).


@dataclass
class PersonalityProfile:
    """Profile for a personality."""
    
    id: str
    name: str
    system_prompt: str
    voice: str
    theme: str
    avatar_model: str
    idle_animation: str
    emotion_profile: str
    greeting_style: str
    animation_style: str
    color_primary: tuple = (0, 100, 150)
    color_secondary: tuple = (100, 50, 150)

    def to_runtime_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "voice": self.voice,
            "theme": self.theme,
            "avatar_model": self.avatar_model,
            "idle_animation": self.idle_animation,
            "emotion_profile": self.emotion_profile,
            "greeting_style": self.greeting_style,
            "animation_style": self.animation_style,
            "colors": {
                "primary": self.color_primary,
                "secondary": self.color_secondary,
            },
        }

    @staticmethod
    def from_plugin(plugin: PersonalityPlugin) -> "PersonalityProfile":
        """Convert a PersonalityPlugin to the legacy PersonalityProfile format."""
        return PersonalityProfile(
            id=plugin.name,
            name=plugin.name,
            system_prompt=plugin.system_prompt,
            voice=plugin.voice,
            theme=plugin.theme.name or plugin.name,
            avatar_model=plugin.avatar_model,
            idle_animation=plugin.idle_animation,
            emotion_profile=plugin.emotion_profile,
            greeting_style=plugin.greeting_style,
            animation_style=plugin.animation_style,
            color_primary=plugin.color_primary,
            color_secondary=plugin.color_secondary,
        )


# Path to personality plugins directory
DEFAULT_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "personalities"


class PersonalityManager:
    """
    Centralized personality management via plugin discovery.
    Personalities are loaded dynamically from personalities/ at startup.
    """

    def __init__(self, state_path: Optional[Path] = None, plugin_dir: Optional[Path] = None):
        self._current_personality: Optional[str] = None
        self._profiles: Dict[str, PersonalityProfile] = {}
        self._plugins: Dict[str, PersonalityPlugin] = {}
        self._lock = threading.RLock()
        self._session_restart_callback: Optional[Callable] = None
        self._transition_in_progress = False
        self._state_path = Path(state_path) if state_path else CONFIG_DIR / "personality_state.json"
        self._plugin_dir = plugin_dir or DEFAULT_PLUGIN_DIR

        self._discover_plugins()
        self._setup_event_listeners()

    def _discover_plugins(self):
        """Discover and load all personality plugins from the plugin directory."""
        plugins = PluginLoader.discover(self._plugin_dir)
        if not plugins:
            logger.warning("No personality plugins found!")
            self._profiles = {}
            self._plugins = {}
            self._current_personality = None
            return
        self._plugins = {p.name: p for p in plugins}
        self._profiles = {
            name: PersonalityProfile.from_plugin(p)
            for name, p in self._plugins.items()
        }
        saved = self._load_saved_personality()
        if saved and saved in self._profiles:
            self._current_personality = saved
        else:
            first_key = next(iter(self._profiles))
            self._current_personality = self._profiles[first_key].id
            if saved:
                logger.warning(
                    "Saved personality '%s' not found, defaulting to '%s'",
                    saved, self._current_personality,
                )
        logger.info(
            "Discovered %d personality plugin(s): %s",
            len(plugins), ", ".join(p.name for p in plugins),
        )

    def reload_plugins(self):
        """Re-scan the plugin directory at runtime."""
        with self._lock:
            self._discover_plugins()

    def _load_saved_personality(self) -> Optional[str]:
        try:
            if not self._state_path.exists():
                return None
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return str(data.get("active_personality", "")).upper()
        except Exception:
            return None

    def _save_current_personality(self):
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps({"active_personality": self._current_personality}, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save personality state: %s", exc)
    
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
    
    def get_current(self) -> Optional[str]:
        """Get current personality name (string)."""
        with self._lock:
            return self._current_personality

    def get_profile(self, personality: Optional[str] = None) -> PersonalityProfile:
        """Get personality profile by name."""
        if personality is None:
            personality = self.get_current()
        if personality and personality in self._profiles:
            return self._profiles[personality]
        if self._profiles:
            return next(iter(self._profiles.values()))
        raise KeyError("No personality profile available")

    def get_plugin(self, personality: Optional[str] = None) -> Optional[PersonalityPlugin]:
        """Get the PersonalityPlugin object for the given personality."""
        if personality is None:
            personality = self.get_current()
        if personality:
            return self._plugins.get(personality)
        return None

    def get_all_profiles(self) -> List[PersonalityProfile]:
        """Get all available personality profiles."""
        with self._lock:
            return list(self._profiles.values())

    def get_all_plugins(self) -> List[PersonalityPlugin]:
        """Get all loaded PersonalityPlugin objects."""
        with self._lock:
            return list(self._plugins.values())

    def get_animation_profile(self, personality: Optional[str] = None) -> Optional[dict]:
        """Get the animation profile dict for the frontend."""
        if personality is None:
            personality = self.get_current()
        if personality and personality in self._plugins:
            anim = self._plugins[personality].animation_profile
            return {
                "idle": anim.idle,
                "listening": anim.listening,
                "thinking": anim.thinking,
                "speaking": anim.speaking,
                "minimalGestures": anim.minimalGestures,
                "name": anim.name,
            }
        return None
    
    def get_system_prompt(self, personality: Optional[str] = None) -> str:
        """Get system prompt for personality."""
        profile = self.get_profile(personality)
        return profile.system_prompt

    def get_voice(self, personality: Optional[str] = None) -> str:
        """Get voice for personality."""
        profile = self.get_profile(personality)
        return profile.voice

    def get_avatar_model(self, personality: Optional[str] = None) -> str:
        """Get avatar model for personality."""
        profile = self.get_profile(personality)
        return profile.avatar_model
    
    async def switch_to(self, personality: str) -> bool:
        """Switch to a different personality."""
        personality = personality.upper()
        if personality not in self._profiles:
            logger.error("Unknown personality: %s", personality)
            return False
        if personality == self._current_personality:
            self._save_current_personality()
            return True

        with self._lock:
            if self._transition_in_progress:
                logger.warning("Personality transition already in progress")
                return False
            self._transition_in_progress = True

        try:
            logger.info("Switching personality to %s", personality)

            publish_event(EventType.PERSONALITY_LOADING, {
                "from": self._current_personality if self._current_personality else None,
                "to": personality,
            })

            with self._lock:
                self._current_personality = personality
                self._save_current_personality()

            profile = self.get_profile(personality)

            publish_event(EventType.UI_THEME_CHANGED, {
                "theme": profile.theme,
                "avatar_model": profile.avatar_model,
                "idle_animation": profile.idle_animation,
                "emotion_profile": profile.emotion_profile,
                "greeting_style": profile.greeting_style,
                "colors": {
                    "primary": profile.color_primary,
                    "secondary": profile.color_secondary,
                },
            })

            publish_event(EventType.AVATAR_STATE_CHANGED, {
                "personality": personality,
                "model": profile.avatar_model,
                "animation_style": profile.animation_style,
                "idle_animation": profile.idle_animation,
                "emotion_profile": profile.emotion_profile,
            })

            if self._session_restart_callback:
                logger.debug("Restarting Gemini session...")
                await self._session_restart_callback()

            publish_event(EventType.PERSONALITY_CHANGED, {
                "personality": personality,
                "profile": profile.to_runtime_dict(),
            })

            logger.info("Personality switched to %s", personality)
            return True

        except Exception as e:
            logger.error("Failed to switch personality: %s", e, exc_info=True)
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
def get_system_prompt() -> str:
    """Get current system prompt."""
    return get_personality_manager().get_system_prompt()


def get_voice() -> str:
    """Get current voice."""
    return get_personality_manager().get_voice()


def get_active_profile() -> PersonalityProfile:
    """Get current complete personality profile."""
    return get_personality_manager().get_profile()


async def switch_personality(personality: str) -> bool:
    """Switch personality by name."""
    return await get_personality_manager().switch_to(personality)


# Backward compatibility alias
def set_personality(name: str) -> bool:
    """Legacy sync-mode personality switch."""
    manager = get_personality_manager()
    name = name.upper()
    if name not in manager._profiles:
        logger.error("Unknown personality: %s", name)
        return False
    manager._current_personality = name
    manager._save_current_personality()
    logger.debug("Set personality to %s (sync mode)", name)
    return True


def get_personality() -> str:
    """Get current personality name (backward compatibility)."""
    current = get_personality_manager().get_current()
    return current or "CHIDVI"
