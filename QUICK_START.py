"""
QUICK START GUIDE - Using the New CHIDVI 555 Architecture

This guide shows you how to use the new modular components
in your code. Start here if you're new to the architecture.
"""

# ============================================================================
# 1. CONFIGURATION
# ============================================================================

"""
Instead of hardcoding values, use the centralized config system.

OLD:
    API_KEY = "your_key_here"
    WINDOW_WIDTH = 980
    THEME = "CHIDVI"

NEW:
"""

from core.config import config

# Get configuration
api_keys = config.get("api.gemini_keys")
model = config.get("api.model")
window_width = config.get("ui.window_width")
theme = config.get("ui.theme")

# Set configuration (at runtime)
config.set("ui.theme", "HINATA")


# ============================================================================
# 2. LOGGING
# ============================================================================

"""
Replace print() with structured logging.

OLD:
    print("Starting...")
    print("ERROR:", error)

NEW:
"""

from core.logging import get_logger

logger = get_logger(__name__)

logger.info("Starting CHIDVI 555")
logger.debug("Debug information")
logger.warning("This is a warning")
logger.error("An error occurred", exc_info=True)

# Enable debug mode
from core.logging import set_debug_mode
set_debug_mode(True)


# ============================================================================
# 3. EVENTS
# ============================================================================

"""
Use events for loose coupling between modules.

OLD:
    # Direct function call - tight coupling
    ui.update_theme(new_theme)

NEW:
"""

from core.event_bus import (
    publish_event, 
    subscribe_to_event, 
    EventType
)

# Subscribe to events
def on_personality_changed(event):
    personality = event.data["personality"]
    logger.info(f"Personality: {personality}")

subscribe_to_event(EventType.PERSONALITY_CHANGED, on_personality_changed)

# Publish events
publish_event(EventType.PERSONALITY_CHANGED, {
    "personality": "HINATA"
})


# ============================================================================
# 4. PERSONALITY MANAGEMENT
# ============================================================================

"""
Use the unified personality manager - single source of truth.

OLD:
    set_personality("HINATA")  # Doesn't restart session
    prompt = get_system_prompt()
    avatar_path = get_avatar()  # Scattered logic

NEW:
"""

from core.personality_manager import (
    get_personality_manager,
    PersonalityID,
    get_current_personality,
    get_system_prompt,
    get_voice,
)

manager = get_personality_manager()

# Get current state
current = get_current_personality()  # Returns PersonalityID
prompt = get_system_prompt()
voice = get_voice()

# Switch personality (async - handles everything)
async def change_personality():
    success = await manager.switch_to(PersonalityID.HINATA)
    # ✓ Changes prompt
    # ✓ Changes avatar
    # ✓ Changes theme
    # ✓ Changes voice
    # ✓ Restarts Gemini session
    # ✓ Notifies all systems


# ============================================================================
# 5. COMMAND ROUTING
# ============================================================================

"""
Use the unified command router for voice and text.

OLD:
    if text == "switch to hinata":
        set_personality("HINATA")
    else:
        await gemini.send(text)  # Different code paths, duplication

NEW:
"""

from commands.router import (
    parse_and_route_command,
    get_command_router,
    CommandType,
)

# Single entry point for ALL commands (voice or text)
async def on_user_input(text):
    # This automatically:
    # 1. Parses the command
    # 2. Classifies it (LOCAL or REMOTE)
    # 3. Routes it to the appropriate handler
    await parse_and_route_command(text)

# OR manually parse and route
async def manual_routing():
    router = get_command_router()
    
    # Parse command
    command = router.parse("Switch to Hinata")
    # → LocalCommand(category=personality, text="...")
    
    command = router.parse("What's the weather?")
    # → RemoteCommand(text="...")
    
    # Register your own handlers
    async def handle_local(cmd):
        print(f"Executing locally: {cmd.text}")
        return True
    
    async def handle_remote(cmd):
        print(f"Sending to Gemini: {cmd.text}")
        return True
    
    router.register_handler(CommandType.LOCAL, handle_local)
    router.register_handler(CommandType.REMOTE, handle_remote)


# ============================================================================
# 6. API KEY MANAGEMENT
# ============================================================================

"""
Use the API key pool for automatic rotation.

OLD:
    API_KEY = os.getenv("GEMINI_API_KEY")
    # Rate limit? Application crashes.

NEW:
"""

from api.key_pool import (
    get_next_api_key,
    mark_api_key_success,
    mark_api_key_rate_limited,
    get_api_pool_stats,
)

# Get next available key (auto-rotates)
key = get_next_api_key()

# After successful API call
mark_api_key_success(key)

# If rate limited (gets cooldown, marked as unavailable)
mark_api_key_rate_limited(key, cooldown_minutes=60)

# Next call automatically uses different key
next_key = get_next_api_key()  # Returns another key

# Get pool stats
stats = get_api_pool_stats()
print(f"Healthy: {stats['healthy']}, Rate limited: {stats['rate_limited']}")


# ============================================================================
# 7. SESSION MANAGEMENT
# ============================================================================

"""
Use the session manager for Gemini lifecycle.

OLD:
    session = await gemini.live_connect(...)
    # If disconnect: manual intervention

NEW:
"""

from core.session_manager import get_session_manager

manager = get_session_manager()

# Set callbacks
async def on_error(error, is_rate_limit):
    logger.error(f"Session error: {error}")

async def on_recovered():
    logger.info("Session recovered!")

manager.set_callbacks(
    on_error=on_error,
    on_recovered=on_recovered,
)

# Create Gemini session
async def create_gemini():
    # Your Gemini initialization code
    pass

# Start session
await manager.start_session(
    session_id="chidvi_001",
    personality="CHIDVI",
    session_creator=create_gemini,
)

# Record conversation
manager.record_turn("user", "What's the weather?")
manager.record_turn("model", "It's sunny...")

# Get conversation history
history = manager.get_conversation_history(limit=10)

# Check session state
if manager.is_active():
    session = manager.get_session()
    # Use session...

# End session
await manager.end_session()


# ============================================================================
# 8. AVATAR ANIMATIONS
# ============================================================================

"""
Use the animation engine for avatar emotions and gestures.

OLD:
    avatar.set_state("speaking")
    # No emotions, no animations

NEW:
"""

from assets.avatar.animation_engine import (
    get_animation_controller,
    set_avatar_state,
    set_avatar_emotion,
)

controller = get_animation_controller()

# Set animation states
set_avatar_state("IDLE")        # Default, breathing
set_avatar_state("LISTENING")   # Head tracking
set_avatar_state("THINKING")    # Contemplative
set_avatar_state("SPEAKING")    # Lip sync + gestures

# Set emotions (with intensity 0.0 to 1.0)
set_avatar_emotion("happy", intensity=1.0)
set_avatar_emotion("sad", intensity=0.7)
set_avatar_emotion("angry", intensity=0.5)
set_avatar_emotion("confused", intensity=0.8)
set_avatar_emotion("surprised", intensity=1.0)
set_avatar_emotion("laughing", intensity=0.9)

# Personality-specific emotions
set_avatar_emotion("jealous", intensity=0.8, reason="Talking about other girls")  # HINATA
set_avatar_emotion("blush", intensity=0.7)  # HINATA

# Start auto animations
controller.start_blinking()
controller.start_breathing()

# Set audio for lip sync
controller.set_audio_data(audio_buffer, sample_rate=24000)

# Get current animation state
state = controller.get_current_state()
# → {"state": "speaking", "emotion": "happy", ...}


# ============================================================================
# 9. PUTTING IT ALL TOGETHER
# ============================================================================

"""
Example: Processing user input with new architecture
"""

async def process_user_input(text: str):
    """Example function showing full pipeline."""
    
    # 1. Log input
    logger.info(f"User: {text}")
    
    # 2. Update avatar
    set_avatar_state("LISTENING")
    
    # 3. Parse and route command
    handled = await parse_and_route_command(text)
    
    # 4. If it's a local command (e.g., personality switch)
    if handled:
        logger.info("Command executed locally")
        return
    
    # 5. If it's a remote command (send to Gemini)
    session = get_session_manager().get_session()
    if session:
        # Send to Gemini
        await session.send_client_content(
            turns={"parts": [{"text": text}]},
            turn_complete=True,
        )
        
        # Update avatar
        set_avatar_state("SPEAKING")
        set_avatar_emotion("focused", intensity=0.8)


# ============================================================================
# 10. COMMON PATTERNS
# ============================================================================

# Pattern 1: Check if current personality is HINATA
from core.personality_manager import get_personality
if get_personality() == "HINATA":
    set_avatar_emotion("excited", intensity=1.0)

# Pattern 2: Get all available personalities
from core.personality_manager import get_personality_manager
manager = get_personality_manager()
personalities = manager.get_all_profiles()
# → [PersonalityProfile("CHIDVI"), PersonalityProfile("HINATA")]

# Pattern 3: React to personality changes
from core.event_bus import subscribe_to_event, EventType
def on_personality_switched(event):
    new_personality = event.data["personality"]
    logger.info(f"Switched to {new_personality}")
subscribe_to_event(EventType.PERSONALITY_CHANGED, on_personality_switched)

# Pattern 4: Handle command routing errors
from commands.router import parse_and_route_command
try:
    success = await parse_and_route_command("user input")
    if not success:
        logger.warning("Command was not handled")
except Exception as e:
    logger.error(f"Command routing failed: {e}")

# Pattern 5: Monitor API key pool
from api.key_pool import get_api_pool_stats
stats = get_api_pool_stats()
if stats['healthy'] == 0:
    logger.warning("No healthy API keys!")


# ============================================================================
# 11. TESTING
# ============================================================================

"""
Test individual components in isolation
"""

def test_config():
    from core.config import config
    assert config.get("api.gemini_keys") is not None

def test_logging():
    from core.logging import get_logger
    logger = get_logger("test")
    logger.info("Test message")

def test_events():
    from core.event_bus import EventType, publish_event, subscribe_to_event
    
    called = []
    def handler(event):
        called.append(event)
    
    subscribe_to_event(EventType.PERSONALITY_CHANGED, handler)
    publish_event(EventType.PERSONALITY_CHANGED, {"personality": "HINATA"})
    
    assert len(called) == 1

def test_command_router():
    from commands.router import get_command_router, CommandType
    
    router = get_command_router()
    cmd = router.parse("Switch to Hinata")
    assert cmd.type == CommandType.LOCAL
    
    cmd = router.parse("What's the weather?")
    assert cmd.type == CommandType.REMOTE


# ============================================================================
# 12. MIGRATION GUIDE
# ============================================================================

"""
Migrating OLD code to NEW architecture:

OLD:
    print("Status: " + status)
    
NEW:
    logger.info(f"Status: {status}")

OLD:
    if text == "switch to hinata":
        set_personality("HINATA")
    else:
        gemini_send(text)

NEW:
    await parse_and_route_command(text)

OLD:
    API_KEY = "hardcoded_key"
    response = client.send(API_KEY)

NEW:
    key = get_next_api_key()
    response = client.send(key)
    mark_api_key_success(key)

OLD:
    avatar.state = "speaking"

NEW:
    set_avatar_state("SPEAKING")
    set_avatar_emotion("focused", intensity=0.8)
"""


if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║  CHIDVI 555 - New Architecture Quick Start Guide               ║
    ║                                                                ║
    ║  1. Configuration   → core.config.config                      ║
    ║  2. Logging         → core.logging.get_logger()               ║
    ║  3. Events          → core.event_bus                          ║
    ║  4. Personality     → core.personality_manager                ║
    ║  5. Commands        → commands.router                         ║
    ║  6. API Keys        → api.key_pool                            ║
    ║  7. Sessions        → core.session_manager                    ║
    ║  8. Animations      → avatar.animation_engine                 ║
    ║                                                                ║
    ║  Start with ARCHITECTURE.md for complete reference            ║
    ║  Use this file for examples and patterns                      ║
    ║                                                                ║
    ║  Ready to integrate? See INTEGRATION_EXAMPLE.py               ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
