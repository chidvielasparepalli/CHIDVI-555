from avatars.avatar_manager import AvatarManager
from avatars.animation_controller import AnimationController
from avatars.expression_controller import ExpressionController
from avatars.avatar_events import AvatarEvent

class AvatarService:
    def __init__(self):
        self.manager = AvatarManager()
        self.animation = AnimationController(self.manager)
        self.expression = ExpressionController(self.animation)

    def set_state(self, state: str):
        self.expression.set_expression(state)

    def get_state(self):
        return self.manager.get_state()

    def idle(self):
        self.set_state("idle")


    def listening(self):
        self.set_state("listening")


    def thinking(self):
        self.set_state("thinking")


    def speaking(self):
        self.set_state("speaking")


    def happy(self):
        self.set_state("happy")


    def sad(self):
        self.set_state("sad")


    def blush(self):
        self.set_state("blush")
    def handle_event(self, event: AvatarEvent):

        if event == AvatarEvent.IDLE:
            self.idle()

        elif event == AvatarEvent.USER_STARTED_SPEAKING:
            self.listening()

        elif event == AvatarEvent.AI_STARTED_THINKING:
            self.thinking()

        elif event == AvatarEvent.AI_STARTED_SPEAKING:
            self.speaking()

        elif event == AvatarEvent.AI_STOPPED_SPEAKING:
            self.idle()

        def initialize_avatar():
            print("[HINATA] Avatar Engine Initialized")
            return avatar_service
        
# Global singleton instance
avatar_service = AvatarService()