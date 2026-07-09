"""
Compatibility wrapper for the canonical command router.

New code should import from commands.router. This module remains so older
imports do not silently keep a separate command path alive.
"""

from commands.router import (  # noqa: F401
    Command,
    CommandCategory,
    CommandRouter,
    CommandType,
    get_command_router,
    parse_and_route_command,
)
