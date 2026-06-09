import sounddevice as sd
from scipy.io.wavfile import write

print("Speak for 10 seconds...")
recording = sd.rec(
    int(10 * 16000),
    samplerate=16000,
    channels=1,
    dtype='int16'
)

sd.wait()

write("my_voice.wav", 16000, recording)

print("Voice profile saved.")