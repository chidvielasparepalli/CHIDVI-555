import asyncio
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from api.key_pool import APIKeyPool
from commands.router import CommandCategory, CommandRouter, CommandType
from core.config import ConfigManager
from core.personality_manager import (
    PersonalityManager,
    get_personality_manager,
    get_system_prompt,
    set_personality,
)
from personality.personality_loader import get_personality as legacy_get_personality


class CommandRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = CommandRouter()

    def assert_local(self, text, category, **args):
        command = self.router.parse(text)
        self.assertEqual(command.type, CommandType.LOCAL)
        self.assertEqual(command.category, category)
        for key, value in args.items():
            self.assertEqual(command.args.get(key), value)

    def test_personality_commands_are_local(self):
        self.assert_local(
            "switch to hinata",
            CommandCategory.PERSONALITY,
            personality="HINATA",
        )
        self.assert_local(
            "enable chidvi please",
            CommandCategory.PERSONALITY,
            personality="CHIDVI",
        )
        self.assert_local(
            "activate hinata now",
            CommandCategory.PERSONALITY,
            personality="HINATA",
        )

    def test_personality_mentions_are_not_commands(self):
        for text in ("i love hinata", "hello hinata how are you"):
            command = self.router.parse(text)
            self.assertEqual(command.type, CommandType.REMOTE)
            self.assertIsNone(command.category)

    def test_audio_and_control_commands_are_structured(self):
        self.assert_local("mute please", CommandCategory.AUDIO, action="mute")
        self.assert_local("unmute", CommandCategory.AUDIO, action="unmute")
        self.assert_local("restart", CommandCategory.CONTROL, action="restart")
        self.assert_local("sleep mode", CommandCategory.CONTROL, action="sleep")

    def test_avatar_action_commands_are_local(self):
        self.assert_local("wave your hand", CommandCategory.AVATAR, action="wave")
        self.assert_local("nod your head", CommandCategory.AVATAR, action="nod")
        self.assert_local("shake your head", CommandCategory.AVATAR, action="shake_head")
        self.assert_local("look left", CommandCategory.AVATAR, action="look_left")
        self.assert_local("look at me", CommandCategory.AVATAR, action="look_forward")
        self.assert_local("point at me", CommandCategory.AVATAR, action="point")
        self.assert_local("clap", CommandCategory.AVATAR, action="clap")
        self.assert_local("thinking pose", CommandCategory.AVATAR, action="thinking")
        self.assert_local("greet me", CommandCategory.AVATAR, action="greeting")


class APIKeyPoolTests(unittest.TestCase):
    def test_round_robin_preserves_order_and_skips_limited_keys(self):
        pool = APIKeyPool(["k1", "k2", "k1", ""])
        self.assertEqual(
            [pool.get_next_key() for _ in range(4)],
            ["k1", "k2", "k1", "k2"],
        )

        pool.mark_rate_limit("k1", cooldown_minutes=60)
        self.assertEqual(
            [pool.get_next_key() for _ in range(3)],
            ["k2", "k2", "k2"],
        )


class PersonalityCompatibilityTests(unittest.TestCase):
    def test_legacy_loader_reads_core_personality_state(self):
        manager = get_personality_manager()
        original_path = manager._state_path
        with TemporaryDirectory() as tmpdir:
            manager._state_path = Path(tmpdir) / "personality_state.json"
            try:
                self.assertTrue(set_personality("HINATA"))
                self.assertEqual(legacy_get_personality(), "HINATA")
                self.assertIn("HINATA", get_system_prompt())

                self.assertTrue(set_personality("CHIDVI"))
                self.assertEqual(legacy_get_personality(), "CHIDVI")
                self.assertIn("CHIDVI", get_system_prompt())
            finally:
                manager._state_path = original_path

    def test_personality_manager_persists_active_personality(self):
        with TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "personality_state.json"
            manager = PersonalityManager(state_path=state_path)

            self.assertTrue(asyncio.run(manager.switch_to("HINATA")))
            self.assertTrue(state_path.exists())

            restored = PersonalityManager(state_path=state_path)
            self.assertEqual(restored.get_current(), "HINATA")

    def test_personality_profiles_own_runtime_assets(self):
        manager = PersonalityManager()

        chidvi = manager.get_profile("CHIDVI")
        hinata = manager.get_profile("HINATA")

        self.assertEqual(chidvi.avatar_model, "Chidvi.vrm")
        self.assertEqual(chidvi.voice, "Charon")
        self.assertEqual(chidvi.theme, "CHIDVI")
        self.assertEqual(chidvi.emotion_profile, "chidvi")
        self.assertEqual(chidvi.idle_animation, "chidvi_idle")

        self.assertEqual(hinata.avatar_model, "Hinata.vrm")
        self.assertEqual(hinata.voice, "Aoede")
        self.assertEqual(hinata.theme, "HINATA")
        self.assertEqual(hinata.emotion_profile, "hinata")
        self.assertEqual(hinata.idle_animation, "hinata_idle")
        self.assertNotEqual(chidvi.greeting_style, hinata.greeting_style)

        runtime_profile = hinata.to_runtime_dict()
        self.assertEqual(runtime_profile["avatar_model"], "Hinata.vrm")
        self.assertEqual(runtime_profile["voice"], "Aoede")


class ConfigTests(unittest.TestCase):
    def test_config_loads_key_array(self):
        keys = ConfigManager().get("api.gemini_keys")
        self.assertIsInstance(keys, list)
        self.assertTrue(keys)


if __name__ == "__main__":
    unittest.main()
