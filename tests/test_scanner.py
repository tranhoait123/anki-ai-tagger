import unittest
from unittest.mock import Mock, patch

import config
import scanner


class ScannerPresetTest(unittest.TestCase):
    def setUp(self):
        self.old_values = {
            "FIELDS_TO_EXCLUDE": config.FIELDS_TO_EXCLUDE,
            "CURRENT_PRESET": config.CURRENT_PRESET,
            "CURRENT_PRESET_ID": config.CURRENT_PRESET_ID,
            "SYSTEM_PROMPT": config.SYSTEM_PROMPT,
            "GEMINI_API_KEYS": config.GEMINI_API_KEYS,
            "CARD_SELECTION_MODE": config.CARD_SELECTION_MODE,
            "BATCH_SIZE": config.BATCH_SIZE,
            "MAX_CARDS_PER_RUN": config.MAX_CARDS_PER_RUN,
            "STOP_SCAN": config.STOP_SCAN,
        }

    def tearDown(self):
        for key, value in self.old_values.items():
            setattr(config, key, value)

    def test_comma_separated_field_mode_reads_multiple_fields(self):
        config.FIELDS_TO_EXCLUDE = []
        note = {
            "fields": {
                "Ques": {"value": "Câu hỏi dài"},
                "A": {"value": "Đáp án A"},
                "B": {"value": "Đáp án B"},
                "Other": {"value": "Không lấy"},
            }
        }

        content = scanner._build_note_content(note, "Ques, A, B")

        self.assertIn("[Ques]: Câu hỏi dài", content)
        self.assertIn("[A]: Đáp án A", content)
        self.assertIn("[B]: Đáp án B", content)
        self.assertNotIn("Other", content)

    def test_duplicate_review_forces_similar_selection(self):
        config.CURRENT_PRESET = {
            "id": "dup",
            "name": "Duplicate",
            "kind": "duplicate_review",
            "allowed_tags": ["AI_DUP_REVIEW"],
            "skip_tags": [],
            "scan_mode": "sequential",
            "fields_to_read": [],
        }
        config.SYSTEM_PROMPT = "duplicate prompt"
        config.GEMINI_API_KEYS = ["valid-key"]
        config.CARD_SELECTION_MODE = "sequential"
        config.BATCH_SIZE = 10
        config.MAX_CARDS_PER_RUN = None
        config.STOP_SCAN = False

        note = {
            "noteId": 123,
            "tags": [],
            "fields": {
                "Ques": {"value": "Một câu hỏi đủ dài để không bị bỏ qua"},
                "A": {"value": "Đáp án"},
            },
        }
        selector = Mock(return_value=([{
            "note_id": 123,
            "existing_tags": [],
            "content": "Một câu hỏi đủ dài để không bị bỏ qua",
            "compare_text": "Một câu hỏi đủ dài",
        }], {"mode": "seed", "seed": "", "score": 1.0}))

        with patch.object(scanner, "get_notes", return_value=[123]), \
                patch.object(scanner, "get_notes_info", return_value=[note]), \
                patch.object(scanner, "select_similar_cards", selector), \
                patch.object(scanner, "analyze_batch_clinical_text", return_value=type("Result", (), {"results": []})()):
            list(scanner.run_scan_generator())

        selector.assert_called_once()


if __name__ == "__main__":
    unittest.main()
