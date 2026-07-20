from avatars.avatar_state import AvatarState


class AnimationController:
    def __init__(self, avatar_manager):
        self.avatar = avatar_manager

    def idle(self):
        self.avatar.set_state(AvatarState.IDLE)

    def listening(self):
        self.avatar.set_state(AvatarState.LISTENING)

    def thinking(self):
        self.avatar.set_state(AvatarState.THINKING)

    def speaking(self):
        self.avatar.set_state(AvatarState.SPEAKING)

    def happy(self):
        self.avatar.set_state(AvatarState.HAPPY)

    def sad(self):
        self.avatar.set_state(AvatarState.SAD)

    def worried(self):
        self.avatar.set_state(AvatarState.WORRIED)

    def blush(self):
        self.avatar.set_state(AvatarState.BLUSH)