import unittest

from core.state_manager import AppState, RuntimeState, StateManager


class StateManagerTests(unittest.TestCase):
    def test_runtime_updates_speaking_flag(self):
        manager = StateManager()

        speaking = manager.set_runtime(RuntimeState.SPEAKING)
        self.assertEqual(speaking.runtime, RuntimeState.SPEAKING)
        self.assertTrue(speaking.speaking)

        listening = manager.set_runtime("listening")
        self.assertEqual(listening.runtime, RuntimeState.LISTENING)
        self.assertFalse(listening.speaking)

    def test_mute_updates_runtime_and_preserves_public_snapshot(self):
        manager = StateManager()

        muted = manager.set_muted(True)
        self.assertTrue(muted.muted)
        self.assertEqual(muted.runtime, RuntimeState.MUTED)
        self.assertFalse(muted.speaking)

        unmuted = manager.set_muted(False)
        self.assertFalse(unmuted.muted)
        self.assertEqual(unmuted.runtime, RuntimeState.LISTENING)
        self.assertIsInstance(manager.snapshot(), AppState)

    def test_personality_updates_avatar_by_default(self):
        manager = StateManager()

        hinata = manager.set_personality("hinata")
        self.assertEqual(hinata.active_personality, "HINATA")
        self.assertEqual(hinata.active_avatar, "Hinata.vrm")

        custom = manager.set_personality("chidvi", avatar="Custom.vrm")
        self.assertEqual(custom.active_personality, "CHIDVI")
        self.assertEqual(custom.active_avatar, "Custom.vrm")

    def test_subscribers_receive_changed_state(self):
        manager = StateManager()
        seen = []
        unsubscribe = manager.subscribe(seen.append)

        manager.set_runtime(RuntimeState.THINKING)
        unsubscribe()
        manager.set_runtime(RuntimeState.LISTENING)

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].runtime, RuntimeState.THINKING)


if __name__ == "__main__":
    unittest.main()
