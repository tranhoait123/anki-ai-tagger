import tempfile
import unittest
from pathlib import Path

import preset_manager
from preset_manager import PresetError, build_system_prompt, load_preset, save_preset


class PresetManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir = preset_manager.PRESETS_DIR
        preset_manager.PRESETS_DIR = Path(self.tmp.name)

    def tearDown(self):
        preset_manager.PRESETS_DIR = self.old_dir
        self.tmp.cleanup()

    def test_load_valid_yaml_and_generate_prompt(self):
        Path(self.tmp.name, "Da_lieu.yaml").write_text(
            """
id: Da_lieu
name: Da liễu
kind: tagging
allowed_tags:
  - AI::Da_lieu::Nam_da
default_tag: AI::Da_lieu::0_xac_dinh
skip_tags:
  - AI::Da_lieu
instructions: Phân loại thẻ da liễu.
""",
            encoding="utf-8",
        )

        preset = load_preset("Da_lieu")
        prompt = build_system_prompt(preset)

        self.assertEqual(preset.id, "Da_lieu")
        self.assertIn("AI::Da_lieu::Nam_da", prompt)
        self.assertIn("AI::Da_lieu::0_xac_dinh", prompt)

    def test_missing_allowed_tags_is_invalid(self):
        with self.assertRaises(PresetError):
            save_preset({
                "id": "bad",
                "name": "Bad",
                "kind": "filter",
                "allowed_tags": [],
                "instructions": "No tags",
            })


if __name__ == "__main__":
    unittest.main()
