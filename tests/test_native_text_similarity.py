import unittest
from difflib import SequenceMatcher

from core import native_text_similarity as sim


class NativeTextSimilarityTests(unittest.TestCase):
    def test_fallback_matches_difflib_when_native_disabled(self):
        previous = sim._rapidfuzz_fuzz
        try:
            sim._rapidfuzz_fuzz = None
            left = "티니핑유스어드벤처"
            right = "티니핑유스어드벤쳐"

            self.assertEqual(sim.text_similarity_backend(), "difflib")
            self.assertAlmostEqual(
                sim.similarity_ratio(left, right),
                SequenceMatcher(None, left, right).ratio(),
                places=9,
            )
        finally:
            sim._rapidfuzz_fuzz = previous

    def test_similarity_ratio_is_normalized(self):
        self.assertEqual(sim.similarity_ratio("", ""), 1.0)
        self.assertEqual(sim.similarity_ratio("abc", ""), 0.0)
        self.assertGreaterEqual(sim.similarity_ratio("hello", "hallo"), 0.0)
        self.assertLessEqual(sim.similarity_ratio("hello", "hallo"), 1.0)

    def test_edit_distance_supports_strings_and_token_sequences(self):
        self.assertEqual(sim.edit_distance("kitten", "sitting"), 3)
        self.assertEqual(sim.edit_distance(["A", "B", "C"], ["A", "C"]), 1)
        self.assertAlmostEqual(sim.character_error_rate("가나다", "가다"), 1 / 3)


if __name__ == "__main__":
    unittest.main()
