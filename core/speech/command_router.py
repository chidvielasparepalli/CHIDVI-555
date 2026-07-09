from core.personality_manager import set_personality

LOCAL_COMMANDS = {
    "switch to hinata": "HINATA",
    "enable hinata": "HINATA",
    "hinata": "HINATA",

    "switch to chidvi": "CHIDVI",
    "enable chidvi": "CHIDVI",
    "chidvi": "CHIDVI",
}


class CommandRouter:

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def handle(self, text: str):

        command = text.lower().strip()

        if command not in LOCAL_COMMANDS:
            return False

        personality = LOCAL_COMMANDS[command]

        self.jarvis._pending_personality = personality

        self.jarvis.ui.switch_theme(personality)

        self.jarvis.ui.write_log(
            f"SYS: Personality -> {personality}"
        )

        self.jarvis._restart_requested = True

        return True