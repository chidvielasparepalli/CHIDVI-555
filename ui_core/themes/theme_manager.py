from ui_core.themes.chidvi_theme import CHIDVI_THEME
from ui_core.themes.hinata_theme import HINATA_THEME


class ThemeManager:

    def __init__(self):
        self._themes = {
            "CHIDVI": CHIDVI_THEME,
            "HINATA": HINATA_THEME,
        }
        self.current = CHIDVI_THEME

    def register_theme(self, name: str, theme_dict: dict):
        """Register a theme from a personality plugin manifest."""
        self._themes[name.upper()] = theme_dict

    def register_theme_from_manifest(self, personality_name: str, theme_config):
        """
        Register a theme from a PersonalityPlugin ThemeConfig object.

        Args:
            personality_name: The personality name (e.g. "HINATA")
            theme_config: A ThemeConfig dataclass from personality_plugin.py
        """
        theme_dict = {
            "name": getattr(theme_config, "name", personality_name),
            "primary": getattr(theme_config, "primary", "#00D8FF"),
            "secondary": getattr(theme_config, "secondary", "#0099FF"),
            "background": getattr(theme_config, "background", "#050A14"),
            "text": getattr(theme_config, "text", "#FFFFFF"),
            "accent": getattr(theme_config, "accent", "#00FFFF"),
            "avatar": getattr(theme_config, "avatar", personality_name),
            "music": getattr(theme_config, "music", ""),
            "background_video": getattr(theme_config, "background_video", ""),
        }
        self.register_theme(personality_name, theme_dict)

    def switch(self, theme_name: str):
        theme_name = theme_name.upper()

        if theme_name in self._themes:
            self.current = self._themes[theme_name]
        else:
            # Fallback to CHIDVI theme if unknown
            self.current = self._themes.get("CHIDVI", CHIDVI_THEME)

        print(f"[THEME] Switched to {self.current.get('name', theme_name)}")

    def get(self):
        return self.current


theme_manager = ThemeManager()