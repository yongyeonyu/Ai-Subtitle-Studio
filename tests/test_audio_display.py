import unittest

from core.audio.audio_display import audio_filter_display_name


class AudioDisplayTests(unittest.TestCase):
    def test_none_with_basic_filter_shows_actual_initial_path(self):
        self.assertEqual(
            audio_filter_display_name({"selected_audio_ai": "none", "use_basic_filter": True}),
            "FFMPEG 기본필터",
        )

    def test_none_without_basic_filter_stays_unused(self):
        self.assertEqual(
            audio_filter_display_name({"selected_audio_ai": "none", "use_basic_filter": False}),
            "미사용",
        )

    def test_runtime_auto_suffix_is_preserved_for_none_route(self):
        self.assertEqual(
            audio_filter_display_name(
                {
                    "selected_audio_ai": "none",
                    "use_basic_filter": True,
                    "_runtime_auto_audio_ai_selected": True,
                }
            ),
            "FFMPEG 기본필터 자동",
        )


if __name__ == "__main__":
    unittest.main()
