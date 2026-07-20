"""
Proactive Conversation Layer for CHIDVI 555.

Monitors user idle time and triggers natural, non-intrusive conversation
prompts with configurable cooldowns to avoid repetition.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, List
from core.logging import get_logger

logger = get_logger(__name__)


class ConversationTriggerType(Enum):
    """Types of proactive conversation triggers."""
    GREETING = "greeting"
    HELP_OFFER = "help_offer"
    TASK_REMINDER = "task_reminder"
    TIME_COMMENT = "time_comment"
    CONVERSATION_CONTINUATION = "conversation_continuation"
    WEATHER_COMMENT = "weather_comment"
    SYSTEM_STATUS = "system_status"


@dataclass
class ConversationTrigger:
    """A single proactive conversation trigger."""
    trigger_type: ConversationTriggerType
    message: str
    min_idle_seconds: float
    max_idle_seconds: float
    cooldown_seconds: float
    last_triggered: float = 0
    priority: int = 1  # Higher = more important
    conditions: List[Callable[[], bool]] = field(default_factory=list)


class ProactiveConversationManager:
    """
    Manages proactive conversation triggers based on user idle time.
    
    Features:
    - Configurable idle time thresholds per trigger type
    - Per-trigger cooldowns to prevent repetition
    - Priority system for trigger selection
    - Conditions for contextual relevance
    - Never interrupts active user speech
    """

    # Default trigger configurations
    DEFAULT_TRIGGERS = [
        ConversationTrigger(
            trigger_type=ConversationTriggerType.GREETING,
            message="Hello there! How can I help you today?",
            min_idle_seconds=30,
            max_idle_seconds=60,
            cooldown_seconds=300,  # 5 minutes
            priority=3,
        ),
        ConversationTrigger(
            trigger_type=ConversationTriggerType.HELP_OFFER,
            message="Is there something I can help you with?",
            min_idle_seconds=60,
            max_idle_seconds=120,
            cooldown_seconds=600,  # 10 minutes
            priority=2,
        ),
        ConversationTrigger(
            trigger_type=ConversationTriggerType.TIME_COMMENT,
            message="It's getting late. Do you need a reminder for anything?",
            min_idle_seconds=180,
            max_idle_seconds=300,
            cooldown_seconds=900,  # 15 minutes
            priority=2,
            conditions=[lambda: _is_evening()],
        ),
        ConversationTrigger(
            trigger_type=ConversationTriggerType.CONVERSATION_CONTINUATION,
            message="We were talking about {topic} earlier. Want to continue?",
            min_idle_seconds=120,
            max_idle_seconds=240,
            cooldown_seconds=1800,  # 30 minutes
            priority=3,
            conditions=[lambda: _has_recent_topic()],
        ),
        ConversationTrigger(
            trigger_type=ConversationTriggerType.SYSTEM_STATUS,
            message="System running smoothly. CPU at {cpu}%, memory at {mem}%.",
            min_idle_seconds=300,
            max_idle_seconds=600,
            cooldown_seconds=1800,  # 30 minutes
            priority=1,
        ),
    ]

    def __init__(
        self,
        send_message_callback: Callable[[str], None],
        is_user_speaking: Callable[[], bool],
        is_assistant_speaking: Callable[[], bool],
        get_idle_time: Callable[[], float],
        get_recent_topic: Callable[[], Optional[str]] = None,
        get_system_stats: Callable[[], dict] = None,
    ):
        """
        Initialize the proactive conversation manager.

        Args:
            send_message_callback: Function to send a message to the user (triggers TTS)
            is_user_speaking: Function returning True if user is currently speaking
            is_assistant_speaking: Function returning True if assistant is currently speaking
            get_idle_time: Function returning seconds since last user interaction
            get_recent_topic: Optional function returning the last conversation topic
            get_system_stats: Optional function returning dict with 'cpu' and 'mem' keys
        """
        self._send_message = send_message_callback
        self._is_user_speaking = is_user_speaking
        self._is_assistant_speaking = is_assistant_speaking
        self._get_idle_time = get_idle_time
        self._get_recent_topic = get_recent_topic or (lambda: None)
        self._get_system_stats = get_system_stats or (lambda: {"cpu": 0, "mem": 0})

        self._triggers: List[ConversationTrigger] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._check_interval = 5.0  # Check every 5 seconds
        self._recent_topic: Optional[str] = None

        # Load default triggers
        self.reset_to_defaults()

    def reset_to_defaults(self):
        """Reset triggers to default configuration."""
        self._triggers = [self._clone_trigger(t) for t in self.DEFAULT_TRIGGERS]

    def _clone_trigger(self, trigger: ConversationTrigger) -> ConversationTrigger:
        """Create a copy of a trigger with fresh state."""
        return ConversationTrigger(
            trigger_type=trigger.trigger_type,
            message=trigger.message,
            min_idle_seconds=trigger.min_idle_seconds,
            max_idle_seconds=trigger.max_idle_seconds,
            cooldown_seconds=trigger.cooldown_seconds,
            last_triggered=0,
            priority=trigger.priority,
            conditions=list(trigger.conditions),
        )

    def add_trigger(self, trigger: ConversationTrigger):
        """Add a custom trigger."""
        self._triggers.append(trigger)

    def remove_trigger(self, trigger_type: ConversationTriggerType):
        """Remove a trigger by type."""
        self._triggers = [t for t in self._triggers if t.trigger_type != trigger_type]

    def set_trigger_cooldown(self, trigger_type: ConversationTriggerType, cooldown_seconds: float):
        """Update cooldown for a specific trigger type."""
        for t in self._triggers:
            if t.trigger_type == trigger_type:
                t.cooldown_seconds = cooldown_seconds

    def set_trigger_idle_range(self, trigger_type: ConversationTriggerType, min_sec: float, max_sec: float):
        """Update idle time range for a trigger."""
        for t in self._triggers:
            if t.trigger_type == trigger_type:
                t.min_idle_seconds = min_sec
                t.max_idle_seconds = max_sec

    def set_trigger_priority(self, trigger_type: ConversationTriggerType, priority: int):
        """Update priority for a trigger."""
        for t in self._triggers:
            if t.trigger_type == trigger_type:
                t.priority = priority

    def enable_trigger(self, trigger_type: ConversationTriggerType, enabled: bool = True):
        """Enable or disable a trigger by setting its cooldown to infinity."""
        for t in self._triggers:
            if t.trigger_type == trigger_type:
                t.cooldown_seconds = float('inf') if not enabled else self.DEFAULT_TRIGGERS[
                    [i for i, dt in enumerate(self.DEFAULT_TRIGGERS) if dt.trigger_type == trigger_type][0]
                ].cooldown_seconds

    async def start(self):
        """Start the proactive conversation monitor."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Proactive conversation manager started")

    async def stop(self):
        """Stop the proactive conversation monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Proactive conversation manager stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_triggers()
            except Exception as e:
                logger.error(f"Error in proactive conversation monitor: {e}")
            await asyncio.sleep(self._check_interval)

    async def _check_triggers(self):
        """Check all triggers and fire eligible ones."""
        # Don't trigger if user or assistant is speaking
        if self._is_user_speaking() or self._is_assistant_speaking():
            return

        idle_time = self._get_idle_time()
        if idle_time <= 0:
            return

        now = time.time()
        eligible_triggers = []

        for trigger in self._triggers:
            # Check cooldown
            if now - trigger.last_triggered < trigger.cooldown_seconds:
                continue

            # Check idle time range
            if not (trigger.min_idle_seconds <= idle_time <= trigger.max_idle_seconds):
                continue

            # Check conditions
            if not all(cond() for cond in trigger.conditions):
                continue

            eligible_triggers.append(trigger)

        if not eligible_triggers:
            return

        # Select highest priority trigger (with some randomness for variety)
        eligible_triggers.sort(key=lambda t: (-t.priority, random.random()))
        selected = eligible_triggers[0]

        # Format message with dynamic values
        message = self._format_message(selected.message)

        # Fire the trigger
        selected.last_triggered = now
        logger.info(f"Firing proactive trigger: {selected.trigger_type.value} - {message[:50]}...")

        try:
            self._send_message(message)
        except Exception as e:
            logger.error(f"Failed to send proactive message: {e}")

    def _format_message(self, template: str) -> str:
        """Format message template with dynamic values."""
        recent_topic = self._get_recent_topic()
        stats = self._get_system_stats()

        return template.format(
            topic=recent_topic or "that",
            cpu=stats.get("cpu", 0),
            mem=stats.get("mem", 0),
            time=time.strftime("%I:%M %p"),
        )

    def get_status(self) -> dict:
        """Get current status for debugging."""
        now = time.time()
        idle_time = self._get_idle_time()
        return {
            "running": self._running,
            "idle_time": idle_time,
            "user_speaking": self._is_user_speaking(),
            "assistant_speaking": self._is_assistant_speaking(),
            "triggers": [
                {
                    "type": t.trigger_type.value,
                    "priority": t.priority,
                    "cooldown_remaining": max(0, t.cooldown_seconds - (now - t.last_triggered)),
                    "idle_range": f"{t.min_idle_seconds}-{t.max_idle_seconds}s",
                    "eligible": (
                        t.min_idle_seconds <= idle_time <= t.max_idle_seconds and
                        now - t.last_triggered >= t.cooldown_seconds and
                        all(cond() for cond in t.conditions)
                    ),
                }
                for t in self._triggers
            ],
        }


def _is_evening() -> bool:
    """Check if it's evening (after 6 PM)."""
    hour = time.localtime().tm_hour
    return hour >= 18


def _has_recent_topic() -> bool:
    """Placeholder - will be replaced by actual topic tracking."""
    return False


# Global instance (initialized by main.py)
_conversation_manager: Optional[ProactiveConversationManager] = None


def init_conversation_manager(
    send_message_callback: Callable[[str], None],
    is_user_speaking: Callable[[], bool],
    is_assistant_speaking: Callable[[], bool],
    get_idle_time: Callable[[], float],
    get_recent_topic: Callable[[], Optional[str]] = None,
    get_system_stats: Callable[[], dict] = None,
) -> ProactiveConversationManager:
    """Initialize the global proactive conversation manager."""
    global _conversation_manager
    _conversation_manager = ProactiveConversationManager(
        send_message_callback=send_message_callback,
        is_user_speaking=is_user_speaking,
        is_assistant_speaking=is_assistant_speaking,
        get_idle_time=get_idle_time,
        get_recent_topic=get_recent_topic,
        get_system_stats=get_system_stats,
    )
    return _conversation_manager


def get_conversation_manager() -> Optional[ProactiveConversationManager]:
    """Get the global conversation manager instance."""
    return _conversation_manager


def update_conversation_topic(topic: str):
    """Update the recent conversation topic for proactive triggers."""
    if _conversation_manager:
        # This would need a method on the manager - for now we'll track it globally
        pass