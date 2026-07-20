"""
Compatibility facade for the core personality manager.

The active personality lives in core.personality_manager. Keeping this file as
a thin wrapper prevents older imports from creating a second source of truth.
"""

from core.personality_manager import (  # noqa: F401
    get_personality,
    get_system_prompt,
    set_personality,
)
