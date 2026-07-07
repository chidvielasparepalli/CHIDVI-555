from avatars.avatar_state import AvatarState


EMOTION_MAP = {
    "idle": AvatarState.IDLE,
    "listening": AvatarState.LISTENING,
    "thinking": AvatarState.THINKING,
    "speaking": AvatarState.SPEAKING,

    "happy": AvatarState.HAPPY,
    "joy": AvatarState.HAPPY,
    "excited": AvatarState.LAUGH,

    "sad": AvatarState.SAD,
    "worried": AvatarState.WORRIED,

    "surprised": AvatarState.SURPRISED,

    "blush": AvatarState.BLUSH,

    "greeting": AvatarState.GREETING,

    "goodbye": AvatarState.GOODBYE
}