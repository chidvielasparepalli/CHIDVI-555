from resemblyzer import VoiceEncoder, preprocess_wav
from pathlib import Path
import numpy as np

print("Loading voice profile...")

encoder = VoiceEncoder()

reference_wav = preprocess_wav(Path("my_voice.wav"))
reference_embedding = encoder.embed_utterance(reference_wav)

def verify_voice(test_file):
    print("Reference:", Path("my_voice.wav").resolve())
    print("Test:", Path(test_file).resolve())
    test_wav = preprocess_wav(Path(test_file))
    test_embedding = encoder.embed_utterance(test_wav)

    similarity = np.dot(
        reference_embedding,
        test_embedding
    )

    print(f"Similarity: {similarity:.6f}")

    return similarity > 0.75
if __name__ == "__main__":
    result = verify_voice("abc.wav")

    if result:
        print("VOICE MATCHED")
    else:
        print("VOICE REJECTED")