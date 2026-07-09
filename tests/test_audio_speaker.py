import unittest

from core.audio.speaker import Speaker


class SpeakerTests(unittest.TestCase):
    def test_mono_to_stereo_duplicates_samples(self):
        speaker = Speaker()
        mono = b"\x01\x00\x02\x00"

        self.assertEqual(
            speaker.mono_to_stereo(mono),
            b"\x01\x00\x01\x00\x02\x00\x02\x00",
        )

    def test_boost_voice_chunk_clamps_samples(self):
        speaker = Speaker()
        samples = bytearray()
        samples.extend((1000).to_bytes(2, "little", signed=True))
        samples.extend((32000).to_bytes(2, "little", signed=True))
        boosted = speaker.boost_voice_chunk(bytes(samples))

        first = int.from_bytes(boosted[0:2], "little", signed=True)
        second = int.from_bytes(boosted[2:4], "little", signed=True)

        self.assertEqual(first, 1180)
        self.assertEqual(second, 32767)


if __name__ == "__main__":
    unittest.main()
