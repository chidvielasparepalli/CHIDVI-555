from enum import Enum


class Emotion(Enum):
    HAPPY = "happy"
    NEUTRAL = "neutral"
    SHY = "shy"
    BLUSH = "blush"
    JEALOUS = "jealous"
    SAD = "sad"
    ANGRY = "angry"
    PLAYFUL = "playful"


class EmotionEngine:

    def __init__(self):
        self.reset()

    def reset(self):
        self.current = Emotion.NEUTRAL
        self.intensity = 0
        self.reason = ""

    def set(self, emotion: Emotion, intensity: int = 5, reason: str = ""):
        self.current = emotion
        self.intensity = max(1, min(10, intensity))
        self.reason = reason

    def calm_down(self):
        if self.intensity > 0:
            self.intensity -= 1

        if self.intensity <= 0:
            self.current = Emotion.NEUTRAL
            self.reason = ""

    def prompt(self):

        return f"""
Current Emotional State

Emotion : {self.current.value}

Intensity : {self.intensity}/10

Reason : {self.reason}

Stay consistent with this emotional state.
"""
    