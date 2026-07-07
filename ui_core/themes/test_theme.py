from ui_core.themes.theme_manager import theme_manager

print(theme_manager.get())

theme_manager.switch("HINATA")

print(theme_manager.get())

theme_manager.switch("CHIDVI")

print(theme_manager.get())