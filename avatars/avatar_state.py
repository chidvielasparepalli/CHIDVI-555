from enum import Enum, auto


class AvatarState(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()

    HAPPY = auto()
    SMILE = auto()
    LAUGH = auto()

    SAD = auto()
    WORRIED = auto()

    SURPRISED = auto()

    BLUSH = auto()

    SLEEPY = auto()

    WAVE = auto()

    LOOK_LEFT = auto()
    LOOK_RIGHT = auto()

    BLINK = auto()

    GREETING = auto()

    GOODBYE = auto()