from avatars.animation_controller import AnimationController


class ExpressionController:

    def __init__(self, animation: AnimationController):
        self.animation = animation

    def set_expression(self, emotion: str):

        emotion = emotion.lower()

        if emotion == "happy":
            self.animation.happy()

        elif emotion == "sad":
            self.animation.sad()

        elif emotion == "thinking":
            self.animation.thinking()

        elif emotion == "speaking":
            self.animation.speaking()

        elif emotion == "listening":
            self.animation.listening()

        elif emotion == "blush":
            self.animation.blush()

        elif emotion == "worried":
            self.animation.worried()

        else:
            self.animation.idle()