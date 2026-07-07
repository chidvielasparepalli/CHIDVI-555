"""
Centralized configuration system for CHIDVI 555.

Loads configuration from:
1. config/ directory (JSON files)
2. Environment variables
3. Defaults

All hardcoded configuration goes here.
No configuration should be scattered throughout the codebase.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


def _get_base_dir() -> Path:
    """Get the project root directory."""
    if getattr(__import__('sys'), "frozen", False):
        return Path(__import__('sys').executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
MEDIA_DIR = BASE_DIR / "media"


class ConfigManager:
    """
    Centralized configuration manager.
    
    Loads and manages all application configuration.
    """
    
    _instance = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._load_configs()
    
    def _load_configs(self):
        """Load all configuration files."""
        self._config = {
            "base_dir": str(BASE_DIR),
            "config_dir": str(CONFIG_DIR),
            "media_dir": str(MEDIA_DIR),
        }
        
        # Load API keys configuration
        self._config["api"] = self._load_api_config()
        
        # Load personality configuration
        self._config["personalities"] = self._load_personality_config()
        
        # Load audio configuration
        self._config["audio"] = self._load_audio_config()
        
        # Load UI configuration
        self._config["ui"] = self._load_ui_config()
        
        # Load avatar configuration
        self._config["avatar"] = self._load_avatar_config()
        
        # Load animation configuration
        self._config["animations"] = self._load_animation_config()
        
        # Load command configuration
        self._config["commands"] = self._load_command_config()
        
        # Load media configuration
        self._config["media"] = self._load_media_config()
    
    def _load_json_file(self, filename: str, default: dict = None) -> dict:
        """Load a JSON configuration file."""
        if default is None:
            default = {}
        
        filepath = CONFIG_DIR / filename
        try:
            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load {filename}: {e}")
        
        return default
    
    def _load_api_config(self) -> dict:
        """Load API configuration."""
        api_config = self._load_json_file("api_keys.json", {})
        
        return {
            "gemini_keys": api_config.get("gemini_keys", [
                api_config.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")
            ]),
            "model": os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-native-audio-preview-12-2025"),
            "timeout": 30,
            "max_retries": 3,
        }
    
    def _load_personality_config(self) -> dict:
        """Load personality configuration."""
        return {
            "default": "CHIDVI",
            "available": ["CHIDVI", "HINATA"],
            "settings": {
                "CHIDVI": {
                    "voice": "Charon",
                    "theme": "CHIDVI",
                    "animation_style": "professional",
                },
                "HINATA": {
                    "voice": "Aoede",
                    "theme": "HINATA",
                    "animation_style": "energetic",
                },
            }
        }
    
    def _load_audio_config(self) -> dict:
        """Load audio configuration."""
        return {
            "send_sample_rate": 16000,
            "receive_sample_rate": 24000,
            "channels": 1,
            "chunk_size": 1024,
            "device": None,  # None = default device
        }
    
    def _load_ui_config(self) -> dict:
        """Load UI configuration."""
        ui_config = self._load_json_file("ui.json", {})
        return {
            "window_width": ui_config.get("window_width", 980),
            "window_height": ui_config.get("window_height", 700),
            "theme": "CHIDVI",
            "background_opacity": ui_config.get("background_opacity", 0.95),
        }
    
    def _load_avatar_config(self) -> dict:
        """Load avatar configuration."""
        avatar_config = self._load_json_file("avatar.json", {})
        return {
            "model_dir": str(BASE_DIR / "avatar"),
            "default_model": "Chidvi.vrm",
            "personality_models": {
                "CHIDVI": "Chidvi.vrm",
                "HINATA": "Hinata.vrm",
            },
            "settings": avatar_config.get("settings", {}),
        }
    
    def _load_animation_config(self) -> dict:
        """Load animation configuration."""
        anim_config = self._load_json_file("animations.json", {})
        return {
            "enabled": anim_config.get("enabled", True),
            "idle_animation": "idle",
            "listening_animation": "listening",
            "thinking_animation": "thinking",
            "speaking_animation": "speaking",
            "blink_interval": 3.0,
            "breathing_enabled": True,
        }
    
    def _load_command_config(self) -> dict:
        """Load command configuration."""
        return {
            "local_commands": {
                "personality": ["switch to hinata", "switch to chidvi", "hinata", "chidvi"],
                "audio": ["mute", "unmute", "stop listening", "wake up"],
                "control": ["shutdown", "restart", "sleep mode", "open settings"],
            },
        }
    
    def _load_media_config(self) -> dict:
        """Load media configuration."""
        media_config = self._load_json_file("media.json", {})
        return {
            "background_volume": media_config.get("background_volume", 0.35),
            "background_music": media_config.get("background_music", None),
            "work_music": media_config.get("work_music", None),
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation."""
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value if value is not None else default
    
    def set(self, key: str, value: Any):
        """Set a configuration value using dot notation."""
        keys = key.split(".")
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration."""
        return self._config.copy()
    
    def reload(self):
        """Reload all configuration."""
        self._config.clear()
        self._load_configs()


# Global singleton
config = ConfigManager()
