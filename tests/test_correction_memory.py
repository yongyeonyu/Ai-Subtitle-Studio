# Version: 03.01.25
# Phase: PHASE2
import tempfile
import unittest
from pathlib import Path

from core.subtitle_quality.correction_memory import (
    add_correction_memory_item,
    apply_correction_memory,
    load_correction_memory,
    search_correction_memory,
)
from core.subtitle_quality.wrong_answer_memory import (
    add_wrong_answer_memory_item,
    load_wrong_answer_memory,
    search_wrong_answer_memory,
)


class CorrectionMemoryTests(unittest.TestCase):
    def test_correction_memory_saves_searches_and_applies(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "correction_memory.json"
            add_correction_memory_item("소설가유모씨", "u_mo_c", path=path, source="unit")

            memory = load_correction_memory(path)
            self.assertEqual(memory["items"][0]["corrected"], "u_mo_c")

            matches = search_correction_memory("안녕하세요 소설가유모씨입니다", path=path)
            corrected, applied = apply_correction_memory("소설가유모씨입니다", matches)

            self.assertEqual(corrected, "u_mo_c입니다")
            self.assertEqual(len(applied), 1)

    def test_wrong_answer_memory_saves_and_searches(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "wrong_answer_memory.json"
            add_wrong_answer_memory_item("Thank you for watching", path=path, context="silent")

            memory = load_wrong_answer_memory(path)
            self.assertEqual(memory["items"][0]["phrase"], "Thank you for watching")
            matches = search_wrong_answer_memory("Thank you for watching", path=path)
            self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
