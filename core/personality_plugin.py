"""
Personality plugin system for CHIDVI 555.

Provides plugin discovery, manifest loading, and validation
for self-contained personality folders under personalities/.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)

# Default base path: project-root / personalities
_DEFAULT_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "personalities"


@dataclass
class AnimationProfile:
    """Animation profile matching the web frontend's PERSONALITY_PROFILES format."""
    idle: str = "idle"
    listening: str = "breathing_idle"
    thinking: str = "thinking"
    speaking: list = field(default_factory=lambda: ["talking", "talking2"])
    minimalGestures: bool = False
    name: str = "UNKNOWN"


@dataclass
class ThemeConfig:
    """Theme configuration matching the Qt theme dict format."""
    name: str = ""
    primary: str = "#00D8FF"
    secondary: str = "#0099FF"
    background: str = "#050A14"
    text: str = "#FFFFFF"
    accent: str = "#00FFFF"
    avatar: str = ""
    music: str = ""
    background_video: str = ""


@dataclass
class PersonalityPlugin:
    """
    A self-contained personality plugin loaded from a manifest.json.
    """
    # Core identity
    name: str
    display_name: str
    version: str = "0.0.0"
    author: str = ""
    description: str = ""

    # File paths
    manifest_path: Path = field(default=None)  # type: ignore
    base_path: Path = field(default=None)  # type: ignore

    # System prompt (loaded from file referenced in manifest)
    system_prompt: str = ""

    # Voice (Gemini TTS voice name)
    voice: str = "Charon"

    # Avatar model filename (e.g. "Chidvi.vrm")
    avatar_model: str = "Chidvi.vrm"

    # Animation profile (sent to JS via window.setAnimationProfile)
    animation_profile: AnimationProfile = field(default_factory=AnimationProfile)

    # Qt theme config
    theme: ThemeConfig = field(default_factory=ThemeConfig)

    # Legacy personality fields
    emotion_profile: str = ""
    greeting_style: str = "professional"
    animation_style: str = "professional"
    idle_animation: str = ""

    # Color tuples for event publishing
    color_primary: tuple = (0, 100, 150)
    color_secondary: tuple = (100, 50, 150)

    @property
    def id(self) -> str:
        """Return the personality name as its ID (replaces PersonalityID.value)."""
        return self.name

    def to_runtime_dict(self) -> dict:
        """Return a dict for event publishing (compatible with PersonalityProfile.to_runtime_dict)."""
        return {
            "id": self.name,
            "name": self.name,
            "voice": self.voice,
            "theme": self.theme.name or self.name,
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


class PluginLoaderError(Exception):
    """Raised when a personality plugin cannot be loaded."""


class PluginLoader:
    """
    Static methods for discovering and loading personality plugins.
    """

    @staticmethod
    def discover(base_path: Optional[Path] = None) -> list[PersonalityPlugin]:
        """
        Scan a directory for personality plugin folders.

        Each subfolder containing a valid ``manifest.json`` is loaded as a plugin.

        Args:
            base_path: Directory to scan. Defaults to ``personalities/`` at project root.

        Returns:
            A list of :class:`PersonalityPlugin` instances (empty if none found).
        """
        base = base_path or _DEFAULT_PLUGIN_DIR
        if not base.is_dir():
            logger.warning("Plugin directory not found: %s", base)
            return []

        plugins: list[PersonalityPlugin] = []
        for entry in sorted(base.iterdir()):
            if not entry.is_dir() or entry.name.startswith("__"):
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.is_file():
                logger.debug("Skipping %s (no manifest.json)", entry.name)
                continue
            try:
                plugin = PluginLoader.load(manifest_path)
                if plugin:
                    plugins.append(plugin)
            except PluginLoaderError as exc:
                logger.error("Failed to load personality plugin %s: %s", entry.name, exc)

        if not plugins:
            logger.warning("No personality plugins found in %s", base)

        return plugins

    @staticmethod
    def load(manifest_path: Path) -> PersonalityPlugin:
        """
        Load a single personality plugin from its ``manifest.json`` path.

        Args:
            manifest_path: Path to the manifest file.

        Returns:
            A :class:`PersonalityPlugin` instance.

        Raises:
            PluginLoaderError: If the manifest is invalid or required files are missing.
        """
        folder = manifest_path.resolve().parent
        if not manifest_path.is_file():
            raise PluginLoaderError(f"manifest.json not found: {manifest_path}")

        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PluginLoaderError(f"Invalid JSON in {manifest_path}: {exc}") from exc

        name = raw.get("name", "")
        if not name:
            raise PluginLoaderError(f"manifest.json at {manifest_path} missing 'name' field")

        # Load system prompt from file
        system_prompt_file = raw.get("system_prompt", "system_prompt.txt")
        system_prompt = PluginLoader._load_text(folder / system_prompt_file)
        if not system_prompt:
            raise PluginLoaderError(
                f"Personality '{name}': system_prompt file not found or empty: "
                f"{folder / system_prompt_file}"
            )

        # Build animation profile
        anim_raw = raw.get("animation_profile", {})
        animation_profile = AnimationProfile(
            idle=anim_raw.get("idle", "idle"),
            listening=anim_raw.get("listening", "breathing_idle"),
            thinking=anim_raw.get("thinking", "thinking"),
            speaking=anim_raw.get("speaking", ["talking", "talking2"]),
            minimalGestures=anim_raw.get("minimalGestures", False),
            name=anim_raw.get("name", name),
        )

        # Build theme config
        theme_raw = raw.get("theme", {})
        theme = ThemeConfig(
            name=theme_raw.get("name", name),
            primary=theme_raw.get("primary", "#00D8FF"),
            secondary=theme_raw.get("secondary", "#0099FF"),
            background=theme_raw.get("background", "#050A14"),
            text=theme_raw.get("text", "#FFFFFF"),
            accent=theme_raw.get("accent", "#00FFFF"),
            avatar=theme_raw.get("avatar", name),
            music=theme_raw.get("music", ""),
            background_video=theme_raw.get("background_video", ""),
        )

        # Colors
        colors = raw.get("colors", {})
        color_primary = tuple(colors.get("primary", [0, 100, 150]))
        color_secondary = tuple(colors.get("secondary", [100, 50, 150]))

        return PersonalityPlugin(
            name=name,
            display_name=raw.get("display_name", name),
            version=raw.get("version", "0.0.0"),
            author=raw.get("author", ""),
            description=raw.get("description", ""),
            manifest_path=manifest_path,
            base_path=folder,
            system_prompt=system_prompt,
            voice=raw.get("voice", "Charon"),
            avatar_model=raw.get("avatar_model", "Chidvi.vrm"),
            animation_profile=animation_profile,
            theme=theme,
            emotion_profile=raw.get("emotion_profile", ""),
            greeting_style=raw.get("greeting_style", "professional"),
            animation_style=raw.get("animation_style", "professional"),
            idle_animation=raw.get("idle_animation", ""),
            color_primary=color_primary,
            color_secondary=color_secondary,
        )

    @staticmethod
    def _load_text(path: Path) -> str:
        """Load a text file, stripping leading/trailing whitespace."""
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8").strip()

    @staticmethod
    def animation_profile_to_js(profile: AnimationProfile) -> str:
        """
        Serialize an AnimationProfile to a JavaScript object literal
        suitable for ``window.setAnimationProfile()`` or the frontend's
        ``registerProfile()``.
        """
        speaking_json = json.dumps(
            profile.speaking if isinstance(profile.speaking, list) else [profile.speaking]
        )
        return (
            "{"
            f'idle: "{profile.idle}", '
            f'listening: "{profile.listening}", '
            f'thinking: "{profile.thinking}", '
            f"speaking: {speaking_json}, "
            f"minimalGestures: {'true' if profile.minimalGestures else 'false'}, "
            f'name: "{profile.name}"'
            "}"
        )
