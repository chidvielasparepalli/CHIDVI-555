# CHIDVI 555 - Architecture Integration Guide

## Overview

This document describes the new modular architecture for CHIDVI 555. The system has been refactored from a monolithic script into a professional-grade AI operating system with clean separation of concerns.

## New Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CHIDVI 555 System                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                   Personality Manager               │  │
│  │  (Central hub for all personality state)            │  │
│  │  - Manages personality switching                    │  │
│  │  - Coordinates theme, voice, avatar changes        │  │
│  │  - Publishes personality events                     │  │
│  └──────────────────────────────────────────────────────┘  │
│           ↓              ↓             ↓             ↓      │
│      Theme System   Voice System   Avatar Manager   Events  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Command Router                           │  │
│  │  (Single entry point for all commands)              │  │
│  │  - Parses user input (voice or text)               │  │
│  │  - Routes to local executors or Gemini             │  │
│  │  - Unified pipeline                                │  │
│  └──────────────────────────────────────────────────────┘  │
│      ↓                                    ↓                 │
│   Local Commands              Gemini Commands               │
│   (Internal executors)        (API routing)                 │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Session Manager                             │  │
│  │  (Gemini session lifecycle)                         │  │
│  │  - Maintains active session                         │  │
│  │  - Handles reconnection                             │  │
│  │  - Preserves state on disconnect                    │  │
│  └──────────────────────────────────────────────────────┘  │
│           ↓                                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        API Key Pool Manager                         │  │
│  │  (Automatic key rotation & rate limiting)           │  │
│  │  - Rotates through available keys                   │  │
│  │  - Detects rate limits                              │  │
│  │  - Recovers failed keys                             │  │
│  │  - Retries transparently                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                    ↓                                        │
│              Google Gemini API                              │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        Animation Engine                             │  │
│  │  (Avatar animations & emotions)                     │  │
│  │  - State animations (idle, listening, etc)         │  │
│  │  - Emotion blending                                 │  │
│  │  - Personality-specific styles                      │  │
│  │  - Lip sync from audio                              │  │
│  │  - Auto blinking & breathing                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                    ↓                                        │
│              VRM Avatar Renderer                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Component Descriptions

### 1. Configuration System (`core/config.py`)

**Purpose**: Centralized configuration management

**Features**:
- Load from JSON files
- Environment variable overrides
- Dot notation for nested access
- No hardcoded values

**Usage**:
```python
from core.config import config

# Get configuration values
api_keys = config.get("api.gemini_keys")
model = config.get("api.model")
theme = config.get("ui.theme")

# Set values programmatically
config.set("ui.theme", "HINATA")
```

### 2. Logging System (`core/logging.py`)

**Purpose**: Replace print() debugging with structured logging

**Features**:
- Multiple levels: DEBUG, INFO, WARNING, ERROR
- Console and file output
- Colored output (Windows-compatible)
- Automatic log rotation

**Usage**:
```python
from core.logging import get_logger

logger = get_logger(__name__)

logger.info("Starting assistant")
logger.warning("Slow response detected")
logger.error("Connection failed", exc_info=True)
```

### 3. Event Bus (`core/event_bus.py`)

**Purpose**: Decoupled communication between modules

**Features**:
- Publish-subscribe pattern
- 20+ event types defined
- Async event publishing
- Thread-safe

**Usage**:
```python
from core.event_bus import publish_event, subscribe_to_event, EventType

# Subscribe to events
def on_personality_changed(event):
    print(f"Personality: {event.data['personality']}")

subscribe_to_event(EventType.PERSONALITY_CHANGED, on_personality_changed)

# Publish events
publish_event(EventType.PERSONALITY_CHANGED, {
    "personality": "HINATA"
})
```

### 4. Dependency Injection (`core/dependency_injection.py`)

**Purpose**: Manage object creation and dependencies

**Features**:
- Service registry
- Singletons and factories
- Loose coupling

**Usage**:
```python
from core.dependency_injection import register_service, get_service

# Register
register_service("config_manager", config_manager_instance)

# Retrieve
manager = get_service("config_manager")
```

### 5. Personality Manager (`core/personality_manager.py`)

**Purpose**: SINGLE SOURCE OF TRUTH for personality state

**Features**:
- Unified personality switching
- Automatic theme/voice/avatar coordination
- Async-aware switching
- Event-driven updates
- Backward compatible with old code

**Key Personalities**:
- **CHIDVI**: Professional, calm, minimal movement
- **HINATA**: Energetic, expressive, playful

**Usage**:
```python
from core.personality_manager import get_personality_manager, PersonalityID

manager = get_personality_manager()

# Set session restart callback (for Gemini restart)
async def restart_session():
    # Restart logic
    pass

manager.set_session_restart_callback(restart_session)

# Switch personality
async def change_personality():
    success = await manager.switch_to(PersonalityID.HINATA)
    if success:
        print("Personality switched!")

# Get current state
current = manager.get_current()  # PersonalityID.CHIDVI
prompt = manager.get_system_prompt()
voice = manager.get_voice()
```

### 6. Command Router (`commands/router.py`)

**Purpose**: Route commands to LOCAL or REMOTE handlers

**Features**:
- Classifies commands by type
- Unified voice/text pipeline
- No logic duplication
- Extensible command definitions

**Command Types**:
- **LOCAL**: Execute in assistant (personality switch, mute, etc.)
- **REMOTE**: Send to Gemini

**Local Commands**:
```
Personality:
- switch to hinata/chidvi
- activate/enable hinata/chidvi

Audio:
- mute/unmute
- stop listening/wake up

Control:
- shutdown/restart
- sleep mode/rest

Settings:
- open settings
- preferences
```

**Usage**:
```python
from commands.router import parse_and_route_command

# Single entry point for all commands (voice or text)
async def on_user_input(text):
    handled = await parse_and_route_command(text)
    if not handled:
        print("Command routing failed")

# Register handlers
from commands.router import get_command_router, CommandType

router = get_command_router()

async def handle_local(command):
    print(f"Executing: {command.text}")
    return True

async def handle_remote(command):
    # Send to Gemini
    return True

router.register_handler(CommandType.LOCAL, handle_local)
router.register_handler(CommandType.REMOTE, handle_remote)
```

### 7. API Key Pool (`api/key_pool.py`)

**Purpose**: Manage multiple API keys with automatic rotation

**Features**:
- Automatic key rotation
- Rate limit detection
- Health monitoring
- Transparent retry
- Failed key recovery

**Usage**:
```python
from api.key_pool import (
    get_api_key_pool,
    mark_api_key_success,
    mark_api_key_rate_limited,
    get_api_pool_stats,
)

# Get next available key
key = get_api_key_pool().get_next_key()

# After successful API call
mark_api_key_success(key)

# If rate limited
mark_api_key_rate_limited(key, cooldown_minutes=60)

# Get stats
stats = get_api_pool_stats()
print(f"Healthy keys: {stats['healthy']}")
print(f"Rate limited: {stats['rate_limited']}")
```

### 8. Session Manager (`core/session_manager.py`)

**Purpose**: Manage Gemini session lifecycle with recovery

**Features**:
- Session start/end
- Automatic reconnection
- State preservation
- Conversation history
- Error recovery

**Usage**:
```python
from core.session_manager import get_session_manager

manager = get_session_manager()

# Set up callbacks
async def on_error(error, is_rate_limit):
    print(f"Session error: {error}")

async def on_recovered():
    print("Session recovered!")

manager.set_callbacks(
    on_error=on_error,
    on_recovered=on_recovered,
)

# Start session
async def create_gemini_session():
    # Return initialized Gemini session object
    pass

await manager.start_session(
    session_id="chidvi_001",
    personality="CHIDVI",
    session_creator=create_gemini_session,
)

# Record conversation
manager.record_turn("user", "What's the weather?")
manager.record_turn("model", "Today is sunny...")

# Get conversation
history = manager.get_conversation_history(limit=10)
```

### 9. Animation Engine (`avatar/animation_engine.py`)

**Purpose**: Manage VRM avatar animations and emotions

**Features**:
- State animations: IDLE, LISTENING, THINKING, SPEAKING
- Emotions: HAPPY, SAD, ANGRY, CONFUSED, SURPRISED, LAUGHING, etc.
- Personality-specific profiles
- Auto blinking & breathing
- Smooth transitions
- Lip sync support

**Animation States**:
- **IDLE**: Default, natural breathing
- **LISTENING**: Head tracking, anticipation
- **THINKING**: Contemplative pose
- **SPEAKING**: Lip sync, gestures

**Usage**:
```python
from avatar.animation_engine import (
    get_animation_controller,
    set_avatar_state,
    set_avatar_emotion,
)

controller = get_animation_controller()

# Set animation state
set_avatar_state("LISTENING")
set_avatar_state("SPEAKING")
set_avatar_state("THINKING")

# Set emotion with intensity
set_avatar_emotion("happy", intensity=1.0)
set_avatar_emotion("sad", intensity=0.7)
set_avatar_emotion("jealous", intensity=0.8, reason="User talking about other girls")

# Start auto animations
controller.start_blinking()
controller.start_breathing()

# Set audio for lip sync
controller.set_audio_data(audio_buffer, sample_rate=24000)

# Get state
state = controller.get_current_state()
print(f"Current: {state['state']}, Emotion: {state['emotion']}")
```

## Event System

The event system enables loose coupling. Key events:

```python
EventType.PERSONALITY_CHANGED       # When personality switches
EventType.PERSONALITY_LOADING       # When loading new personality
EventType.SESSION_STARTED           # When Gemini session starts
EventType.SESSION_ERROR             # When session fails
EventType.SESSION_RECONNECTING      # When reconnecting
EventType.COMMAND_LOCAL             # When local command parsed
EventType.COMMAND_REMOTE            # When remote command parsed
EventType.COMMAND_EXECUTED          # When command completed
EventType.COMMAND_FAILED            # When command failed
EventType.AVATAR_STATE_CHANGED      # When avatar state changes
EventType.AVATAR_EMOTION_CHANGED    # When emotion changes
EventType.UI_STATE_CHANGED          # When UI state changes
EventType.UI_THEME_CHANGED          # When theme changes
EventType.GEMINI_STREAMING_START    # When Gemini starts speaking
EventType.GEMINI_STREAMING_END      # When Gemini stops
EventType.GEMINI_API_ERROR          # When API error occurs
EventType.GEMINI_KEY_ROTATED        # When API key rotated
```

## Integration Flow

### 1. User says "Switch to Hinata"

```
Voice Input
    ↓
Speech Recognition (STT)
    ↓
Command Router.parse() → LocalCommand(personality, "HINATA")
    ↓
Command Router.route() → Local Handler
    ↓
Personality Manager.switch_to(HINATA) [ASYNC]
    ↓
    ├─ Publish PERSONALITY_LOADING event
    ├─ Switch prompt internally
    ├─ Publish UI_THEME_CHANGED event → UI updates theme
    ├─ Publish AVATAR_STATE_CHANGED event → Avatar loads Hinata.vrm
    ├─ Call session_restart_callback() → Gemini session restarts
    └─ Publish PERSONALITY_CHANGED event → All systems in sync
```

### 2. User says "What's the weather?"

```
Voice Input
    ↓
Speech Recognition (STT)
    ↓
Command Router.parse() → RemoteCommand
    ↓
Command Router.route() → Remote Handler
    ↓
Session Manager sends to Gemini
    ↓
Gemini responds (with streaming)
    ↓
    ├─ Avatar changes to SPEAKING state
    ├─ Animation Engine triggers speaking animations
    ├─ Audio output with lip sync
    ├─ Avatar changes back to IDLE when done
    └─ Conversation recorded in Session Manager
```

### 3. API Rate Limit Occurs

```
Gemini API Error (429 - Too Many Requests)
    ↓
Session Manager detects rate limit
    ↓
mark_api_key_rate_limited(key)
    ↓
API Key Pool marks key as rate limited with 60-min cooldown
    ↓
Session Manager attempts recovery with next key
    ↓
API Key Pool.get_next_key() returns alternate healthy key
    ↓
Session Manager reconnects with new key
    ↓
To User: "Let me try again" (no error shown)
    ↓
Request succeeds transparently
```

## Migration Notes

### Old Code → New Code

| Old | New |
|-----|-----|
| `print()` | `logger.info()` / `logger.debug()` |
| Global variables | Event bus |
| `set_personality()` | `await personality_manager.switch_to()` |
| Direct Gemini access | Session Manager |
| Hardcoded config | `config.get()` |
| Scattered command logic | `parse_and_route_command()` |
| Multiple personality managers | Single PersonalityManager |
| Direct API key usage | API Key Pool |

### Backward Compatibility

The new system maintains backward compatibility:
- `set_personality()` still works (sync wrapper)
- `get_personality()` still works
- `get_system_prompt()` still works
- `get_voice()` still works
- `is_hinata()` still works

However, for new code, use the async-aware APIs:
```python
# Old (still works)
set_personality("HINATA")

# New (recommended)
await personality_manager.switch_to(PersonalityID.HINATA)
```

## Next Steps for Integration

1. Update `main.py` to use new personality manager
2. Update command handlers to use command router
3. Replace print() with logger
4. Integrate API key pool into Gemini client
5. Add session recovery logic to main loop
6. Connect animation events to avatar renderer
7. Update UI to subscribe to theme change events
8. Add error boundaries with silent recovery

## Design Principles

1. **Single Responsibility**: Each module does one thing well
2. **Loose Coupling**: Modules communicate via events, not direct calls
3. **Dependency Injection**: Services are injected, not created globally
4. **Async-First**: Async operations are prioritized for UI responsiveness
5. **User-Centric**: Errors never exposed to user, recovery is silent
6. **Personality-Aware**: All systems respect current personality
7. **Extensible**: New personalities, commands, animations can be added easily
8. **Testable**: Each component can be tested independently

## File Organization

```
core/
  config.py              ✓ Configuration management
  logging.py             ✓ Structured logging
  event_bus.py           ✓ Event pub/sub
  dependency_injection.py ✓ Service registry
  personality_manager.py ✓ Unified personality
  session_manager.py     ✓ Gemini session lifecycle

api/
  key_pool.py            ✓ API key rotation & pooling

commands/
  router.py              ✓ Command routing & parsing

avatar/
  animation_engine.py    ✓ Animation & emotion system

ui_core/
  (existing UI code)

actions/
  (existing tool actions)

memory/
  (existing memory system)
```

---

**This architecture is designed to grow gracefully over years while maintaining clean code, testability, and responsiveness.**
