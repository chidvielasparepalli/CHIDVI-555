from ui_core.themes.chidvi_theme import CHIDVI_THEME
from ui_core.themes.hinata_theme import HINATA_THEME


class ThemeManager:

    def __init__(self):
        self.current = CHIDVI_THEME

    def switch(self, theme_name):

        theme_name = theme_name.upper()

        if theme_name == "HINATA":
            self.current = HINATA_THEME
        else:
            self.current = CHIDVI_THEME

        print(f"[THEME] Switched to {self.current['name']}")

    def get(self):
        return self.current


theme_manager = ThemeManager()