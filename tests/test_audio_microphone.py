import unittest

from core.audio.microphone import Microphone


class MicrophoneTests(unittest.TestCase):
    def test_should_capture_only_when_not_speaking_and_not_muted(self):
        microphone = Microphone()

        self.assertTrue(microphone.should_capture(False, False))
        self.assertFalse(microphone.should_capture(True, False))
        self.assertFalse(microphone.should_capture(False, True))
        self.assertFalse(microphone.should_capture(True, True))

    def test_constructor_preserves_audio_settings(self):
        microphone = Microphone(sample_rate=8000, channels=2, chunk_size=256, device=4)

        self.assertEqual(microphone.sample_rate, 8000)
        self.assertEqual(microphone.channels, 2)
        self.assertEqual(microphone.chunk_size, 256)
        self.assertEqual(microphone.device, 4)


if __name__ == "__main__":
    unittest.main()
