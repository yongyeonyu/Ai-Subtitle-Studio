import unittest
from unittest.mock import Mock, patch

from core.audio import diarize


class DiarizeDependencyTests(unittest.TestCase):
    def setUp(self):
        diarize._missing_dependency_notice_logged = False

    def test_missing_diarization_packages_reports_exact_optional_package(self):
        def fake_find_spec(module_name):
            return None if module_name == "speechbrain" else object()

        with patch("core.audio.diarize.importlib.util.find_spec", side_effect=fake_find_spec):
            self.assertEqual(diarize.missing_diarization_packages(), ["speechbrain"])

    def test_missing_dependency_log_says_stt_continues_as_single_speaker(self):
        logger = Mock()
        with patch("core.audio.diarize.get_logger", return_value=logger):
            diarize.log_missing_diarization_dependencies(["speechbrain"])

        message = logger.log.call_args.args[0]
        self.assertIn("누락: speechbrain", message)
        self.assertIn("단일 화자", message)
        self.assertNotIn("scikit-learn", message)

    def test_missing_dependency_notice_is_logged_once(self):
        logger = Mock()
        with patch("core.audio.diarize.get_logger", return_value=logger):
            diarize.log_missing_diarization_dependencies(["speechbrain"])
            diarize.log_missing_diarization_dependencies(["speechbrain"])

        logger.log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
