from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import correction_dictionary_db as correction_db
from core.engine.subtitle_text_policy import clean_subtitle_text
from core.runtime import config


def _python_sequential_replace(text: str, corrections: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    applied: list[tuple[str, str]] = []
    for old, new in corrections.items():
        if old and old in text:
            text = text.replace(old, new)
            applied.append((old, new))
    return text, applied


def _with_fillers(corrections: dict[str, str], *, filler_count: int = 128) -> dict[str, str]:
    merged = {f"미사용토큰{idx:03d}": f"unused-{idx:03d}" for idx in range(filler_count)}
    merged.update(corrections)
    return merged


class CorrectionDictionaryDbTests(unittest.TestCase):
    def test_load_corrections_builds_sqlite_index_and_sorts_longest_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "dataset_correction.json"
            saved = correction_db.save_corrections(
                {
                    "ab": "AB",
                    "abcdef": "ABCDEF",
                    "abc": "ABC",
                },
                str(json_path),
            )

            loaded = correction_db.load_corrections(str(json_path))

            self.assertEqual(list(loaded.keys()), ["abcdef", "abc", "ab"])
            self.assertEqual(loaded, saved)
            self.assertTrue(Path(correction_db.correction_db_path(str(json_path))).exists())

    def test_indexed_apply_matches_python_reference_and_finds_late_introduced_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "dataset_correction.json"
            saved = correction_db.save_corrections(
                _with_fillers({
                    "ab": "pqx",
                    "x요": "X요",
                    "pqX요": "완료",
                    "없는규칙": "미사용",
                }),
                str(json_path),
            )
            text = "ab요"

            indexed = correction_db.apply_corrections_indexed(text, saved, correction_json_path=str(json_path))
            expected = _python_sequential_replace(text, saved)

            self.assertEqual(indexed, expected)

    def test_corrections_may_apply_returns_false_when_text_has_no_relevant_heads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "dataset_correction.json"
            saved = correction_db.save_corrections(
                _with_fillers({
                    "소설과 유무시입니다": "소설가유모씨입니다",
                    "티니핑": "티니핑",
                }),
                str(json_path),
            )

            self.assertFalse(
                correction_db.corrections_may_apply(
                    "zzzz qqqq",
                    saved,
                    correction_json_path=str(json_path),
                )
            )

    def test_clean_subtitle_text_uses_indexed_runtime_dictionary_when_config_path_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "dataset_correction.json"
            correction_db.save_corrections(
                _with_fillers({
                    "소설과 유무시입니다": "소설가유모씨입니다",
                    "티니핑": "티니핑.",
                    "티니핑.": "티니핑",
                }),
                str(json_path),
            )
            corrections = correction_db.load_corrections(str(json_path))
            previous_path = config.CORRECTIONS_FILE
            try:
                config.CORRECTIONS_FILE = str(json_path)
                cleaned = clean_subtitle_text("소설과 유무시입니다 티니핑", corrections)
            finally:
                config.CORRECTIONS_FILE = previous_path

            self.assertEqual(cleaned, "소설가유모씨입니다 티니핑")


if __name__ == "__main__":
    unittest.main()
