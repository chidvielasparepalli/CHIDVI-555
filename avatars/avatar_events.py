from enum import Enum, auto


class AvatarEvent(Enum):
    IDLE = auto()
    USER_STARTED_SPEAKING = auto()

    AI_STARTED_THINKING = auto()

    AI_STARTED_SPEAKING = auto()
    AI_STOPPED_SPEAKING = auto()