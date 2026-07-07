from enum import Enum
import random
import time


class Emotion(Enum):
    CALM = "calm"
    HAPPY = "happy"
    THINKING = "thinking"
    EXCITED = "excited"
    CARING = "caring"
    PLAYFUL = "playful"
    FOCUSED = "focused"


class EmotionEngine:

    def __init__(self):
        self.current = Emotion.CALM
        self.last_change = time.time()

    def set(self, emotion):
        self.current = emotion
        self.last_change = time.time()

    def get(self):
        return self.current

    def random_idle(self):
        self.current = random.choice([
            Emotion.CALM,
            Emotion.THINKING,
            Emotion.HAPPY
        ])