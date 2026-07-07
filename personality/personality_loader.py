from personality.chidvi import CHIDVI_SYSTEM_PROMPT
from personality.hinata import HINATA_SYSTEM_PROMPT

_current = "CHIDVI"

PROMPTS = {
    "CHIDVI": CHIDVI_SYSTEM_PROMPT,
    "HINATA": HINATA_SYSTEM_PROMPT,
}


def set_personality(name: str):
    global _current
    name = name.upper()
    if name in PROMPTS:
        _current = name


def get_personality():
    return _current


def get_prompt():
    return PROMPTS[_current]


def get_system_prompt():
    return get_prompt()