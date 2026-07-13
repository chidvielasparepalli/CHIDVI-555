import unittest

from core.audio.diagnostics import AudioDiagnostics


class AudioDiagnosticsTests(unittest.TestCase):
    def test_input_snapshot_reports_levels_and_voice_detection(self):
        diagnostics = AudioDiagnostics()
        diagnostics.configure_input(sample_rate=16000, device=None, buffer_size=1024)
        samples = (2000).to_bytes(2, "little", signed=True) * 64

        diagnostics.record_input(samples)
        snapshot = diagnostics.snapshot()

        self.assertTrue(snapshot["voice_detected"])
        self.assertGreater(snapshot["rms"], 0.05)
        self.assertGreater(snapshot["peak"], 0.05)
        self.assertGreater(snapshot["mic_level"], 0.0)
        self.assertEqual(snapshot["sample_rate"], 16000)
        self.assertEqual(snapshot["device"], "DEFAULT")
        self.assertEqual(snapshot["buffer_size"], 1024)

    def test_update_preserves_pipeline_statuses(self):
        diagnostics = AudioDiagnostics()
        diagnostics.update(stt_status="RECOGNIZED", ai_status="THINKING", tts_status="BUFFERING")

        snapshot = diagnostics.snapshot()

        self.assertEqual(snapshot["stt_status"], "RECOGNIZED")
        self.assertEqual(snapshot["ai_status"], "THINKING")
        self.assertEqual(snapshot["tts_status"], "BUFFERING")


if __name__ == "__main__":
    unittest.main()
