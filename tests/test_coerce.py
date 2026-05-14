import unittest

from core.coerce import safe_float, safe_int


class CoerceTests(unittest.TestCase):
    def test_safe_float_returns_default_on_invalid_values(self):
        self.assertEqual(safe_float("3.5"), 3.5)
        self.assertEqual(safe_float(None, 1.25), 1.25)
        self.assertEqual(safe_float("abc", -2.0), -2.0)

    def test_safe_int_matches_project_context_conversion_behavior(self):
        self.assertEqual(safe_int("7.9"), 7)
        self.assertEqual(safe_int(None, 4), 4)
        self.assertEqual(safe_int("bad", -1), -1)


if __name__ == "__main__":
    unittest.main()
