import asyncio
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from api.key_pool import APIKeyPool
from commands.router import CommandCategory, CommandRouter, CommandType
from core.config import ConfigManager
from core.personality_manager import (
    PersonalityID,
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

            self.assertTrue(asyncio.run(manager.switch_to(PersonalityID.HINATA)))
            self.assertTrue(state_path.exists())

            restored = PersonalityManager(state_path=state_path)
            self.assertEqual(restored.get_current(), PersonalityID.HINATA)


class ConfigTests(unittest.TestCase):
    def test_config_loads_key_array(self):
        keys = ConfigManager().get("api.gemini_keys")
        self.assertIsInstance(keys, list)
        self.assertTrue(keys)


if __name__ == "__main__":
    unittest.main()
