"""
Animation engine for VRM avatars in CHIDVI 555.

Handles:
- State-based animations (IDLE, LISTENING, THINKING, SPEAKING)
- Emotion-based animations (HAPPY, SAD, ANGRY, CONFUSED, SURPRISED, LAUGHING)
- Smooth transitions between states
- Lip sync with audio
- Blinking and breathing
- Head movement and eye tracking
- Gesture expressions
- Personality-specific animation profiles

The avatar should feel ALIVE:
- Natural idle motion
- Reactive to user input
- Expressive with emotions
- Smooth animations (no jerky movements)
- Personality-specific style
"""

from enum import Enum
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading
import time
from core.logging import get_logger
from core.event_bus import publish_event, subscribe_to_event, EventType

logger = get_logger(__name__)


class AnimationState(Enum):
    """Avatar animation states."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class EmotionState(Enum):
    """Avatar emotion states."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    CONFUSED = "confused"
    SURPRISED = "surprised"
    LAUGHING = "laughing"
    JEALOUS = "jealous"
    BLUSH = "blush"
    CARING = "caring"


@dataclass
class AnimationProfile:
    """
    Animation profile for a personality.
    
    Defines how animations should be played.
    """
    
    name: str
    idle_speed: float = 1.0              # Animation speed multiplier
    idle_motion_range: float = 0.3       # How much the avatar moves
    listening_movement: float = 0.5      # Head tracking intensity
    blink_interval: float = 3.0          # Seconds between blinks
    blink_duration: float = 0.15         # Duration of blink animation
    breathing_enabled: bool = True
    breathing_speed: float = 1.0
    head_movement_range: float = 15.0    # Degrees
    eye_tracking_enabled: bool = True
    gesture_intensity: float = 1.0       # How expressive gestures are
    emotion_blend_smooth: bool = True    # Smooth emotion transitions
    animation_style: str = "professional"  # "professional" or "energetic"


@dataclass
class BlendShape:
    """Blend shape (morphing) for facial expression."""
    
    name: str
    value: float = 0.0
    target: float = 0.0
    speed: float = 1.0


@dataclass
class EmotionBlend:
    """Emotion blend with intensity."""
    
    emotion: EmotionState
    intensity: float
    blend_shapes: Dict[str, float] = field(default_factory=dict)


class AnimationController:
    """
    Controls avatar animations.
    
    Manages state transitions, emotions, lip sync,
    blinking, breathing, and other animation aspects.
    """
    
    def __init__(self):
        self._current_state = AnimationState.IDLE
        self._current_emotion = EmotionState.NEUTRAL
        self._emotion_blend: Dict[EmotionState, float] = {}
        self._blend_shapes: Dict[str, BlendShape] = {}
        self._animation_profiles: Dict[str, AnimationProfile] = {}
        self._current_profile: Optional[AnimationProfile] = None
        self._lock = threading.RLock()
        
        # Animation timers
        self._blink_timer = None
        self._breathing_timer = None
        self._idle_motion_timer = None
        
        # Audio data for lip sync
        self._audio_buffer = None
        self._audio_sample_rate = 24000
        
        self._load_profiles()
        self._setup_event_listeners()
        logger.info("Animation controller initialized")
    
    def _load_profiles(self):
        """Load animation profiles for each personality."""
        # CHIDVI - professional, calm
        self._animation_profiles["CHIDVI"] = AnimationProfile(
            name="CHIDVI",
            idle_speed=0.8,
            idle_motion_range=0.2,
            listening_movement=0.3,
            blink_interval=3.5,
            gesture_intensity=0.6,
            animation_style="professional",
        )
        
        # HINATA - energetic, expressive
        self._animation_profiles["HINATA"] = AnimationProfile(
            name="HINATA",
            idle_speed=1.2,
            idle_motion_range=0.5,
            listening_movement=0.8,
            blink_interval=2.5,
            gesture_intensity=1.2,
            animation_style="energetic",
        )
        
        # Set default profile
        self.set_profile("CHIDVI")
    
    def _setup_event_listeners(self):
        """Set up event listeners."""
        subscribe_to_event(EventType.PERSONALITY_CHANGED, self._on_personality_changed)
        subscribe_to_event(EventType.AVATAR_STATE_CHANGED, self._on_avatar_state_changed)
        subscribe_to_event(EventType.AVATAR_EMOTION_CHANGED, self._on_emotion_changed)
    
    def _on_personality_changed(self, event):
        """Handle personality change."""
        personality = event.data.get("personality", "CHIDVI")
        animation_style = event.data.get("profile", {}).get("animation_style", "professional")
        self.set_profile(personality)
        logger.debug(f"Animation profile switched to {personality}")
    
    def _on_avatar_state_changed(self, event):
        """Handle avatar state change."""
        # Could be used for model switching, etc.
        pass
    
    def _on_emotion_changed(self, event):
        """Handle emotion change."""
        emotion = event.data.get("emotion", "neutral")
        intensity = event.data.get("intensity", 1.0)
        self.set_emotion(emotion, intensity)
    
    def set_profile(self, personality: str):
        """Set animation profile for personality."""
        if personality in self._animation_profiles:
            self._current_profile = self._animation_profiles[personality]
            logger.debug(f"Animation profile set to {personality}")
        else:
            logger.warning(f"Unknown animation profile: {personality}")
    
    def set_state(self, state: AnimationState):
        """Set current animation state."""
        with self._lock:
            if state == self._current_state:
                return
            
            old_state = self._current_state
            self._current_state = state
            
            logger.debug(f"Avatar state: {old_state.value} -> {state.value}")
            
            # Trigger state-specific animations
            if state == AnimationState.IDLE:
                self._trigger_idle_animation()
            elif state == AnimationState.LISTENING:
                self._trigger_listening_animation()
            elif state == AnimationState.THINKING:
                self._trigger_thinking_animation()
            elif state == AnimationState.SPEAKING:
                self._trigger_speaking_animation()
    
    def _trigger_idle_animation(self):
        """Trigger idle animation."""
        # In real implementation, would send animation commands to avatar renderer
        # For now, this is a placeholder
        pass
    
    def _trigger_listening_animation(self):
        """Trigger listening animation (head tracking, anticipation)."""
        pass
    
    def _trigger_thinking_animation(self):
        """Trigger thinking animation (hand on chin, contemplative)."""
        pass
    
    def _trigger_speaking_animation(self):
        """Trigger speaking animation (lip sync, gestures)."""
        pass
    
    def set_emotion(self, emotion: str, intensity: float = 1.0, reason: str = ""):
        """
        Set or blend emotion.
        
        Args:
            emotion: Emotion name (e.g., "happy", "sad")
            intensity: Intensity from 0.0 to 1.0
            reason: Reason for emotion (for logging)
        """
        try:
            emotion_state = EmotionState[emotion.upper()]
        except KeyError:
            logger.warning(f"Unknown emotion: {emotion}")
            return
        
        with self._lock:
            if self._current_profile.emotion_blend_smooth:
                # Blend emotions smoothly
                self._emotion_blend[emotion_state] = min(1.0, intensity)
                self._update_blend_shapes_for_emotion()
            else:
                # Switch emotions directly
                self._emotion_blend.clear()
                self._emotion_blend[emotion_state] = intensity
                self._current_emotion = emotion_state
            
            logger.debug(f"Emotion set to {emotion} (intensity={intensity})" +
                        (f" - {reason}" if reason else ""))
            
            # Publish event
            publish_event(EventType.AVATAR_EMOTION_CHANGED, {
                "emotion": emotion,
                "intensity": intensity,
                "reason": reason,
            })
    
    def _update_blend_shapes_for_emotion(self):
        """Update blend shapes based on current emotions."""
        # This would be implemented in the actual avatar renderer
        # Maps emotions to blend shape values
        pass
    
    def set_audio_data(self, audio_buffer: bytes, sample_rate: int):
        """
        Set audio data for lip sync.
        
        Args:
            audio_buffer: PCM audio data
            sample_rate: Sample rate of audio
        """
        self._audio_buffer = audio_buffer
        self._audio_sample_rate = sample_rate
    
    def start_blinking(self):
        """Start automatic blinking animation."""
        if self._blink_timer is not None:
            return
        
        if self._current_profile is None:
            return
        
        def blink_loop():
            while self._blink_timer is not None:
                time.sleep(self._current_profile.blink_interval)
                # Trigger blink animation
                self._do_blink()
        
        self._blink_timer = threading.Thread(target=blink_loop, daemon=True)
        self._blink_timer.start()
        logger.debug("Blinking started")
    
    def _do_blink(self):
        """Perform a blink animation."""
        pass
    
    def start_breathing(self):
        """Start automatic breathing animation."""
        if self._breathing_timer is not None:
            return
        
        if self._current_profile is None or not self._current_profile.breathing_enabled:
            return
        
        def breathing_loop():
            while self._breathing_timer is not None:
                time.sleep(3.0 / self._current_profile.breathing_speed)
                # Trigger breathing animation
                self._do_breathing()
        
        self._breathing_timer = threading.Thread(target=breathing_loop, daemon=True)
        self._breathing_timer.start()
        logger.debug("Breathing started")
    
    def _do_breathing(self):
        """Perform breathing animation."""
        pass
    
    def stop_animations(self):
        """Stop all animations."""
        self._blink_timer = None
        self._breathing_timer = None
        self._idle_motion_timer = None
        logger.debug("All animations stopped")
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current animation state."""
        with self._lock:
            return {
                "state": self._current_state.value,
                "emotion": self._current_emotion.value,
                "emotions_blending": {k.value: v for k, v in self._emotion_blend.items()},
                "profile": self._current_profile.name if self._current_profile else None,
            }


# Global instance
_animation_controller: Optional[AnimationController] = None


def get_animation_controller() -> AnimationController:
    """Get the global animation controller."""
    global _animation_controller
    
    if _animation_controller is None:
        _animation_controller = AnimationController()
    
    return _animation_controller


# Convenience functions
def set_avatar_state(state: str):
    """Set avatar animation state."""
    try:
        anim_state = AnimationState[state.upper()]
        get_animation_controller().set_state(anim_state)
    except KeyError:
        logger.warning(f"Unknown animation state: {state}")


def set_avatar_emotion(emotion: str, intensity: float = 1.0, reason: str = ""):
    """Set avatar emotion."""
    get_animation_controller().set_emotion(emotion, intensity, reason)
