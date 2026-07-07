from avatars.avatar_state import AvatarState
from avatars.avatar_logger import logger

class AvatarManager:

    def reset(self):
        self.current_state = AvatarState.IDLE

    def __init__(self):

        self.current_state = AvatarState.IDLE

    def set_state(self, state: AvatarState):

        if self.current_state == state:
            return

        self.current_state = state

        logger.info(f"Avatar State -> {state.name}")

    def get_state(self):

        return self.current_state