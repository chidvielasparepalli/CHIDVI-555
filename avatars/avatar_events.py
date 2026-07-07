from enum import Enum, auto


class AvatarEvent(Enum):
    IDLE = auto()
    USER_STARTED_SPEAKING = auto()
    USER_STOPPED_SPEAKING = auto()

    AI_STARTED_THINKING = auto()
    AI_STOPPED_THINKING = auto()

    AI_STARTED_SPEAKING = auto()
    AI_STOPPED_SPEAKING = auto()

    USER_ARRIVED = auto()
    USER_LEFT = auto()