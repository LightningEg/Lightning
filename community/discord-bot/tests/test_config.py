import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import Settings, validate_channel_name, validate_public_text

class SettingsTests(unittest.TestCase):
    def test_operator_ids_required(self):
        with self.assertRaisesRegex(ValueError, "DISCORD_OPERATOR_IDS"):
            Settings.from_environ({"DISCORD_BOT_TOKEN": "test", "DISCORD_GUILD_ID": "123"})

    def test_operator_requires_correct_server(self):
        cfg = Settings.from_environ({"DISCORD_BOT_TOKEN": "test", "DISCORD_GUILD_ID": "123", "DISCORD_OPERATOR_IDS": "4,5"})
        self.assertTrue(cfg.is_operator(4, 123))
        self.assertFalse(cfg.is_operator(4, 124))
        self.assertFalse(cfg.is_operator(6, 123))

    def test_validates_public_data(self):
        self.assertEqual(validate_channel_name("start-here"), "start-here")
        for name in ("X", "", "Uppercase", "some name", "x" * 81):
            with self.assertRaises(ValueError): validate_channel_name(name)
        self.assertEqual(validate_public_text(" hello "), "hello")
        for body in ("  ", "a" * 1901):
            with self.assertRaises(ValueError): validate_public_text(body)

if __name__ == "__main__":
    unittest.main()
