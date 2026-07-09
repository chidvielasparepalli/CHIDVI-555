"""
Command router for CHIDVI 555.

This module ensures:
1. Local commands are executed locally (not sent to Gemini)
2. Remote commands are sent to Gemini
3. Voice and text use the same pipeline
4. No command logic duplication

LOCAL COMMANDS include:
- switch to hinata/chidvi
- mute/unmute
- stop listening/wake up
- shutdown/restart
- open settings/sleep mode
"""

from enum import Enum
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass
import re
from core.logging import get_logger
from core.event_bus import publish_event, EventType
from core.config import config

logger = get_logger(__name__)


class CommandType(Enum):
    """Types of commands."""
    LOCAL = "local"           # Execute locally, don't send to Gemini
    REMOTE = "remote"         # Send to Gemini
    UNKNOWN = "unknown"       # Couldn't classify


class CommandCategory(Enum):
    """Categories of local commands."""
    PERSONALITY = "personality"
    AUDIO = "audio"
    CONTROL = "control"
    SETTINGS = "settings"


@dataclass
class Command:
    """A parsed command."""
    
    text: str
    type: CommandType
    category: Optional[CommandCategory] = None
    args: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.args is None:
            self.args = {}


class CommandRouter:
    """
    Routes commands to appropriate handlers.
    
    Determines whether a command should be handled locally
    or sent to Gemini.
    """
    
    def __init__(self):
        self._local_commands = self._load_local_commands()
        self._command_handlers: Dict[CommandType, Callable] = {}
        logger.info("Command router initialized")
    
    def _load_local_commands(self) -> Dict[CommandCategory, List[str]]:
        """Load local command patterns."""
        cfg = config.get("commands.local_commands", {})
        
        commands = {
            CommandCategory.PERSONALITY: [
                "switch to hinata",
                "switch to chidvi",
                "enable hinata",
                "enable chidvi",
                "hinata",
                "chidvi",
                "activate hinata",
                "activate chidvi",
            ],
            CommandCategory.AUDIO: [
                "mute",
                "unmute",
                "stop listening",
                "wake up",
                "silence",
                "quiet",
            ],
            CommandCategory.CONTROL: [
                "shutdown",
                "restart",
                "sleep mode",
                "sleep",
                "rest",
            ],
            CommandCategory.SETTINGS: [
                "open settings",
                "settings",
                "preferences",
                "show settings",
            ],
        }
        
        # Override with config if available
        for category in CommandCategory:
            key = f"{category.value}"
            if key in cfg:
                commands[category] = cfg[key]
        
        return commands
    
    def register_handler(self, command_type: CommandType, handler: Callable):
        """Register a handler for a command type."""
        self._command_handlers[command_type] = handler
        logger.debug(f"Registered handler for {command_type.value} commands")
    
    def parse(self, text: str) -> Command:
        """
        Parse and classify a command.
        
        Args:
            text: Raw command text
        
        Returns:
            Classified command
        """
        # Normalize input
        normalized = self._normalize(text)
        
        logger.debug(f"Parsing command: {text}")
        
        # Check local commands
        for category, patterns in self._local_commands.items():
            for pattern in patterns:
                if normalized == pattern or self._matches_pattern(normalized, pattern):
                    cmd = Command(
                        text=text,
                        type=CommandType.LOCAL,
                        category=category,
                        args=self._extract_args(category, normalized, pattern),
                    )
                    logger.debug(f"Classified as {category.value}: {normalized}")
                    return cmd
        
        # Unknown command - treat as remote
        cmd = Command(
            text=text,
            type=CommandType.REMOTE,
            category=None,
        )
        logger.debug(f"Classified as REMOTE (sending to Gemini)")
        return cmd

    def _normalize(self, text: str) -> str:
        """Normalize user text for command matching."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_args(
        self,
        category: CommandCategory,
        text: str,
        pattern: str,
    ) -> Dict[str, Any]:
        """Extract structured command args from a matched local command."""
        if category == CommandCategory.PERSONALITY:
            if "hinata" in text or "hinata" in pattern:
                return {"personality": "HINATA"}
            if "chidvi" in text or "chidvi" in pattern:
                return {"personality": "CHIDVI"}

        if category == CommandCategory.AUDIO:
            if pattern in {"mute", "stop listening", "silence", "quiet"}:
                return {"action": "mute"}
            if pattern in {"unmute", "wake up"}:
                return {"action": "unmute"}

        if category == CommandCategory.CONTROL:
            if pattern == "restart":
                return {"action": "restart"}
            if pattern == "shutdown":
                return {"action": "shutdown"}
            if pattern in {"sleep", "sleep mode", "rest"}:
                return {"action": "sleep"}

        if category == CommandCategory.SETTINGS:
            return {"action": "settings"}

        return {}
    
    def _matches_pattern(self, text: str, pattern: str) -> bool:
        """
        Check if text matches a pattern.
        
        Supports:
        - Exact match
        - Prefix match
        - Word variations
        """
        # Exact match
        if text == pattern:
            return True
        
        # Prefix match (e.g., "switch to chidvi" matches "switch to chidvi please")
        if text.startswith(pattern):
            rest = text[len(pattern):].strip()
            # Allow trailing words like "please", "now", "ok", etc.
            if not rest or rest in ["please", "now", "ok", "thanks", "thank you"]:
                return True
        
        # Fuzzy match for similar commands
        if self._is_similar(text, pattern):
            return True
        
        return False
    
    def _is_similar(self, text: str, pattern: str) -> bool:
        """Check if text is similar to pattern (Levenshtein distance)."""
        # Simple similarity check
        if len(text) < 3 or len(pattern) < 3:
            return False
        
        # Check if all pattern words are in text
        pattern_words = pattern.split()
        text_words = text.split()
        if len(pattern_words) == 1:
            return False
        if not any(tword.startswith(pattern_words[0][:3]) for tword in text_words):
            return False

        required_words = [word for word in pattern_words if word not in {"to"}]
        match_count = 0
        for pword in required_words:
            if any(tword.startswith(pword[:3]) for tword in text_words):
                match_count += 1

        return match_count == len(required_words)
    
    async def route(self, command: Command) -> bool:
        """
        Route command to appropriate handler.
        
        Args:
            command: Parsed command
        
        Returns:
            True if command was handled, False otherwise
        """
        if command.type == CommandType.LOCAL:
            return await self._handle_local_command(command)
        elif command.type == CommandType.REMOTE:
            return await self._handle_remote_command(command)
        else:
            return False
    
    async def _handle_local_command(self, command: Command) -> bool:
        """Handle a local command."""
        logger.info(f"Handling local command: {command.category.value} - {command.text}")
        
        # Publish event
        publish_event(EventType.COMMAND_LOCAL, {
            "text": command.text,
            "category": command.category.value if command.category else None,
        })
        
        # Check if handler is registered
        if CommandType.LOCAL not in self._command_handlers:
            logger.warning("No handler registered for LOCAL commands")
            return False
        
        try:
            handler = self._command_handlers[CommandType.LOCAL]
            result = await handler(command)
            
            if result:
                publish_event(EventType.COMMAND_EXECUTED, {
                    "text": command.text,
                    "type": "local",
                })
                logger.info(f"Local command executed: {command.text}")
            else:
                publish_event(EventType.COMMAND_FAILED, {
                    "text": command.text,
                    "reason": "handler_returned_false",
                })
            
            return result
        except Exception as e:
            logger.error(f"Error handling local command: {e}", exc_info=True)
            publish_event(EventType.COMMAND_FAILED, {
                "text": command.text,
                "error": str(e),
            })
            return False
    
    async def _handle_remote_command(self, command: Command) -> bool:
        """Handle a remote command (send to Gemini)."""
        logger.debug(f"Routing to Gemini: {command.text}")
        
        # Publish event
        publish_event(EventType.COMMAND_REMOTE, {
            "text": command.text,
        })
        
        # Check if handler is registered
        if CommandType.REMOTE not in self._command_handlers:
            logger.warning("No handler registered for REMOTE commands")
            return False
        
        try:
            handler = self._command_handlers[CommandType.REMOTE]
            result = await handler(command)
            return result
        except Exception as e:
            logger.error(f"Error handling remote command: {e}", exc_info=True)
            return False


# Global router instance
_router: Optional[CommandRouter] = None


def get_command_router() -> CommandRouter:
    """Get the global command router."""
    global _router
    if _router is None:
        _router = CommandRouter()
    return _router


async def parse_and_route_command(text: str) -> bool:
    """
    Parse and route a command.
    
    This is the MAIN ENTRY POINT for all commands,
    whether from voice or text input.
    """
    router = get_command_router()
    command = router.parse(text)
    return await router.route(command)
