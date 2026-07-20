from enum import Enum, auto


class AvatarState(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()

    HAPPY = auto()

    SAD = auto()
    WORRIED = auto()

    BLUSH = auto()