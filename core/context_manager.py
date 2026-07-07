from core.emotion_engine import Emotion

def detect_emotion(user_text: str):

    text = user_text.lower()

    if any(word in text for word in [
        "thank",
        "awesome",
        "done",
        "completed",
        "finished"
    ]):
        return Emotion.EXCITED

    if any(word in text for word in [
        "sad",
        "cry",
        "depressed",
        "stress"
    ]):
        return Emotion.CARING

    if any(word in text for word in [
        "code",
        "python",
        "bug",
        "error"
    ]):
        return Emotion.FOCUSED

    return Emotion.CALM