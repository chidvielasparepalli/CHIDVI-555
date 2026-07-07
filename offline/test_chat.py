from offline.offline_chat import offline_chat
from core.personality_manager import set_personality
from core.personality_manager import (
    get_personality,
    get_system_prompt,
)

print("Current Personality:", get_personality())
print("=" * 50)
print(get_system_prompt()[:300])
print("=" * 50)

set_personality("HINATA")

print("Current Personality:", get_personality())

while True:

    text = input("You : ")

    if text.lower() == "exit":
        break

    print()
    from core.personality_manager import get_personality

    print(f"{get_personality()} :", offline_chat.ask(text))
    print()