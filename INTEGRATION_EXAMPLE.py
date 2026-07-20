"""
Integration example for CHIDVI 555 new architecture.

This file shows HOW to integrate the new modular components
into the main application loop.

This is a TEMPLATE - shows the pattern, not complete implementation.
"""

import asyncio
import os
from pathlib import Path
from core.logging import get_logger, set_debug_mode
from core.config import config
from core.event_bus import subscribe_to_event, EventType, publish_event
from core.personality_manager import get_personality_manager
from core.session_manager import get_session_manager
from api.key_pool import get_api_key_pool, get_next_api_key
from commands.router import get_command_router, CommandType
from assets.avatar.animation_engine import get_animation_controller

logger = get_logger(__name__)


class CHIDVIAssistant:
    """
    Main application class using new modular architecture.
    
    This integrates all components together:
    - Configuration
    - Logging
    - Events
    - Personality switching
    - Command routing
    - API key pooling
    - Session management
    - Avatar animations
    """
    
    def __init__(self):
        """Initialize the assistant with all components."""
        self.personality_manager = get_personality_manager()
        self.session_manager = get_session_manager()
        self.command_router = get_command_router()
        self.animation_controller = get_animation_controller()
        self.api_key_pool = get_api_key_pool()
        
        self._setup_personality_callbacks()
        self._setup_command_handlers()
        self._setup_event_listeners()
        
        logger.info("CHIDVI 555 Assistant initialized")
    
    def _setup_personality_callbacks(self):
        """Set up personality manager callbacks."""
        async def on_restart_session():
            """Called when personality changes and session needs restart."""
            logger.info("Restarting session for personality change")
            await self._restart_gemini_session()
        
        self.personality_manager.set_session_restart_callback(on_restart_session)
    
    def _setup_command_handlers(self):
        """Register command handlers with the router."""
        
        async def handle_local_command(command):
            """Handle local commands."""
            logger.debug(f"Handling local command: {command.text}")
            
            if command.category.value == "personality":
                return await self._handle_personality_command(command)
            elif command.category.value == "audio":
                return await self._handle_audio_command(command)
            elif command.category.value == "control":
                return await self._handle_control_command(command)
            elif command.category.value == "settings":
                return await self._handle_settings_command(command)
            
            return False
        
        async def handle_remote_command(command):
            """Handle remote commands (send to Gemini)."""
            logger.debug(f"Routing to Gemini: {command.text}")
            
            session = self.session_manager.get_session()
            if not session:
                logger.warning("No active session")
                return False
            
            try:
                # Send to Gemini
                await session.send_client_content(
                    turns={"parts": [{"text": command.text}]},
                    turn_complete=True,
                )
                return True
            except Exception as e:
                logger.error(f"Failed to send command to Gemini: {e}")
                return False
        
        self.command_router.register_handler(CommandType.LOCAL, handle_local_command)
        self.command_router.register_handler(CommandType.REMOTE, handle_remote_command)
    
    def _setup_event_listeners(self):
        """Set up system event listeners."""
        subscribe_to_event(EventType.PERSONALITY_CHANGED, self._on_personality_changed)
        subscribe_to_event(EventType.UI_THEME_CHANGED, self._on_theme_changed)
        subscribe_to_event(EventType.COMMAND_EXECUTED, self._on_command_executed)
        subscribe_to_event(EventType.AVATAR_STATE_CHANGED, self._on_avatar_state_changed)
        subscribe_to_event(EventType.GEMINI_KEY_ROTATED, self._on_key_rotated)
    
    async def _handle_personality_command(self, command):
        """Handle personality switching commands."""
        text = command.text.lower()
        
        if "hinata" in text:
            logger.info("User requested personality: HINATA")
            return await self.personality_manager.switch_to(PersonalityID.HINATA)
        elif "chidvi" in text:
            logger.info("User requested personality: CHIDVI")
            return await self.personality_manager.switch_to(PersonalityID.CHIDVI)
        
        return False
    
    async def _handle_audio_command(self, command):
        """Handle audio control commands."""
        text = command.text.lower()
        
        if "mute" in text:
            logger.info("Muting audio")
            # TODO: Implement mute logic
            return True
        elif "unmute" in text or "wake up" in text:
            logger.info("Unmuting audio")
            # TODO: Implement unmute logic
            return True
        
        return False
    
    async def _handle_control_command(self, command):
        """Handle system control commands."""
        text = command.text.lower()
        
        if "shutdown" in text or "restart" in text:
            logger.warning("Shutdown requested")
            await self.shutdown()
            return True
        elif "sleep" in text:
            logger.info("Entering sleep mode")
            # TODO: Implement sleep logic
            return True
        
        return False
    
    async def _handle_settings_command(self, command):
        """Handle settings commands."""
        logger.info("Opening settings")
        # TODO: Implement settings opening
        return True
    
    def _on_personality_changed(self, event):
        """Handle personality changed event."""
        personality = event.data.get("personality", "CHIDVI")
        logger.info(f"Personality changed to {personality}")
    
    def _on_theme_changed(self, event):
        """Handle theme changed event."""
        theme = event.data.get("theme", "CHIDVI")
        logger.debug(f"Theme changed to {theme}")
    
    def _on_command_executed(self, event):
        """Handle command executed event."""
        logger.debug(f"Command executed: {event.data.get('text', 'unknown')}")
    
    def _on_avatar_state_changed(self, event):
        """Handle avatar state change event."""
        model = event.data.get("model", "unknown")
        logger.debug(f"Avatar model changed to {model}")
    
    def _on_key_rotated(self, event):
        """Handle API key rotation event."""
        reason = event.data.get("reason", "unknown")
        logger.debug(f"API key rotated (reason: {reason})")
    
    async def on_user_input(self, text: str):
        """
        Process user input (voice or text).
        
        This is the MAIN ENTRY POINT for all user commands.
        Both voice and text go through the same pipeline.
        """
        logger.debug(f"User input: {text}")
        
        # Update avatar state
        self.animation_controller.set_state("LISTENING")
        
        # Route command (local or remote)
        await self.command_router.route(self.command_router.parse(text))
        
        # Reset avatar
        self.animation_controller.set_state("IDLE")
    
    async def _restart_gemini_session(self):
        """Restart Gemini session (e.g., for personality change)."""
        logger.info("Restarting Gemini session")
        
        # End current session
        await self.session_manager.end_session()
        
        # Wait briefly
        await asyncio.sleep(1)
        
        # Start new session
        try:
            await self.session_manager.start_session(
                session_id=f"chidvi_{int(asyncio.get_event_loop().time())}",
                personality=str(self.personality_manager.get_current().value),
                session_creator=self._create_gemini_session,
            )
        except Exception as e:
            logger.error(f"Failed to restart session: {e}")
    
    async def _create_gemini_session(self):
        """Create a new Gemini session."""
        # This is where you'd actually create the Google Gemini session
        # For now, this is a placeholder
        logger.debug("Creating Gemini session")
        
        # TODO: Implement actual Gemini session creation
        # Example:
        # from google import genai
        # key = get_next_api_key()
        # client = genai.Client(api_key=key)
        # config = types.LiveConnectConfig(...)
        # session = await client.aio.live.connect(config=config)
        # return session
        
        return None  # Placeholder
    
    async def start(self):
        """Start the assistant."""
        logger.info("Starting CHIDVI 555 Assistant")
        
        # Start Gemini session
        try:
            await self.session_manager.start_session(
                session_id="chidvi_initial",
                personality=str(self.personality_manager.get_current().value),
                session_creator=self._create_gemini_session,
            )
        except Exception as e:
            logger.error(f"Failed to start session: {e}")
        
        # Start avatar animations
        self.animation_controller.start_blinking()
        self.animation_controller.start_breathing()
        
        # Publish system ready event
        publish_event(EventType.SYSTEM_READY, {
            "personality": str(self.personality_manager.get_current().value),
        })
        
        logger.info("CHIDVI 555 Ready!")
    
    async def shutdown(self):
        """Shut down the assistant."""
        logger.info("Shutting down CHIDVI 555 Assistant")
        
        # Stop animations
        self.animation_controller.stop_animations()
        
        # End session
        await self.session_manager.end_session()
        
        # Publish shutdown event
        publish_event(EventType.SYSTEM_SHUTDOWN, {})
        
        logger.info("CHIDVI 555 Shutdown Complete")


# Example usage
async def main():
    """Main entry point."""
    # Enable debug logging
    set_debug_mode(True)
    
    # Create assistant
    assistant = CHIDVIAssistant()
    
    # Start it
    await assistant.start()
    
    # Simulate user input
    await assistant.on_user_input("What's the weather?")
    await asyncio.sleep(2)
    
    await assistant.on_user_input("Switch to Hinata")
    await asyncio.sleep(2)
    
    # Shutdown
    await assistant.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
