import tempfile
import unittest
from pathlib import Path

from core.personalization.ground_truth_import import (
    build_truth_table_records_from_srt,
    import_ground_truth_pairs,
    pair_ground_truth_assets,
    resolve_ambiguous_matches,
)
from core.personalization.lora_storage import initialize_lora_personalization_store, store_paths


class GroundTruthImportTests(unittest.TestCase):
    def test_build_truth_table_records_excludes_parentheticals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            media_path = root / "clip 01.mp4"
            subtitle_path = root / "clip 01.srt"
            media_path.write_bytes(b"video")
            subtitle_path.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:01,000 --> 00:00:03,000",
                        "(박수) 안녕하세요!",
                        "",
                        "2",
                        "00:00:04,000 --> 00:00:06,000",
                        "[효과음]",
                        "",
                        "3",
                        "00:00:07,000 --> 00:00:09,000",
                        "오늘은 그러니까",
                        "여기까지 할게요.",
                        "",
                        "4",
                        "00:00:10,000 --> 00:00:12,000",
                        "{자료화면} 실제 발화입니다.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = build_truth_table_records_from_srt(media_path, subtitle_path, media_id="media-001")

            self.assertEqual(result["stats"]["segments_total"], 4)
            self.assertEqual(result["stats"]["truth_rows"], 3)
            self.assertEqual(result["stats"]["excluded_parenthetical_rows"], 3)
            self.assertEqual(result["stats"]["skipped_empty_text"], 1)
            self.assertEqual(result["truth_rows"][0]["speech_training_text"], "안녕하세요!")
            self.assertEqual(result["truth_rows"][0]["excluded_parenthetical_text"], "박수")
            self.assertEqual(result["truth_rows"][1]["detected_split_rule"], "그러니까")
            self.assertEqual(result["truth_rows"][1]["line_break_pattern"], "8|8")
            self.assertEqual(result["truth_rows"][2]["speech_training_text"], "실제 발화입니다.")
            self.assertEqual(result["truth_rows"][2]["excluded_parenthetical_text"], "자료화면")
            self.assertEqual(len(result["voice_bridge_rows"]), 3)
            self.assertEqual(result["voice_bridge_rows"][0]["text"], "안녕하세요!")
            self.assertEqual(result["voice_bridge_rows"][0]["clip_path"], str(media_path))
            self.assertEqual(len(result["multimodal_context_rows"]), 1)
            context = result["multimodal_context_rows"][0]
            self.assertEqual(context["task"], "subtitle_generation_context")
            self.assertEqual(context["generation_targets"]["do_not_learn_as_spoken_text"], ["()", "[]", "{}"])
            self.assertEqual(context["subtitle_profile"]["speech_segments"], 3)
            self.assertGreaterEqual(context["subtitle_profile"]["excluded_parenthetical_ratio"], 0.5)

    def test_pair_ground_truth_assets_uses_exact_then_normalized_basename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            media_dir = root / "media"
            subtitle_dir = root / "subs"
            media_dir.mkdir()
            subtitle_dir.mkdir()

            (media_dir / "클립 01.mp4").write_bytes(b"a")
            (media_dir / "Episode-02.mov").write_bytes(b"b")
            (subtitle_dir / "클립 01.srt").write_text("", encoding="utf-8")
            (subtitle_dir / "episode 02.srt").write_text("", encoding="utf-8")
            (subtitle_dir / "orphan.srt").write_text("", encoding="utf-8")

            pairs = pair_ground_truth_assets([media_dir, subtitle_dir])

            self.assertEqual(len(pairs["pairs"]), 2)
            by_match_type = {item["media_path"]: item["match_type"] for item in pairs["pairs"]}
            self.assertEqual(by_match_type[str(media_dir / "클립 01.mp4")], "exact")
            self.assertEqual(by_match_type[str(media_dir / "Episode-02.mov")], "normalized")
            self.assertEqual(pairs["unmatched_subtitle_paths"], [str(subtitle_dir / "orphan.srt")])

    def test_ground_truth_context_classifies_environment_mic_and_topic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            media_path = root / "BMW X5 차량 시승 리뷰.MP4"
            subtitle_path = root / "BMW X5 차량 시승 리뷰.srt"
            media_path.write_bytes(b"video")
            subtitle_path.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:01,000 --> 00:00:03,000",
                        "오늘은 BMW X5 시승을 하면서 주행감과 실내 공간을 봅니다.",
                        "",
                        "2",
                        "00:00:04,000 --> 00:00:06,000",
                        "(엔진음) 고속도로에서 노면 소음도 확인해 볼게요.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = build_truth_table_records_from_srt(media_path, subtitle_path, media_id="bmw-x5")

            classification = result["classification"]
            self.assertEqual(classification["scene_environment"]["label"], "car")
            self.assertEqual(classification["topic"]["primary"], "vehicle_review")
            self.assertIn("engine", classification["microphone_environment"]["noise_sources"])
            self.assertIn("protect_brand_model_names", classification["training_focus"])
            context = result["multimodal_context_rows"][0]
            self.assertEqual(context["context_classification"]["topic"]["primary"], "vehicle_review")

    def test_excluded_parenthetical_text_does_not_drive_context_classification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            media_path = root / "neutral clip.mp4"
            subtitle_path = root / "neutral clip.srt"
            media_path.write_bytes(b"video")
            subtitle_path.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:01,000 --> 00:00:03,000",
                        "좋아요. (BMW X5 차량 시승 리뷰)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = build_truth_table_records_from_srt(media_path, subtitle_path, media_id="neutral")

            self.assertEqual(result["truth_rows"][0]["speech_training_text"], "좋아요.")
            self.assertEqual(result["truth_rows"][0]["excluded_parenthetical_text"], "BMW X5 차량 시승 리뷰")
            self.assertNotEqual(result["classification"]["topic"]["primary"], "vehicle_review")

    def test_import_ground_truth_pairs_writes_truth_table_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            media_path = root / "sample.mp4"
            subtitle_path = root / "sample.srt"
            media_path.write_bytes(b"video")
            subtitle_path.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:01,000 --> 00:00:02,500",
                        "(음악) 테스트 자막입니다.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            store_dir = root / "lora_personalization"
            initialize_lora_personalization_store(store_dir)

            result = import_ground_truth_pairs(
                [{"media_path": str(media_path), "subtitle_path": str(subtitle_path), "media_id": "media-010"}],
                store_dir=store_dir,
            )

            self.assertEqual(result["imported_pairs"], 1)
            self.assertEqual(result["truth_rows"], 1)
            self.assertEqual(result["excluded_rows"], 1)
            self.assertEqual(result["voice_bridge_rows"], 1)
            self.assertEqual(result["multimodal_context_rows"], 1)

            paths = store_paths(store_dir)
            truth_lines = paths["truth_table"].read_text(encoding="utf-8").strip().splitlines()
            excluded_lines = paths["excluded_parentheticals"].read_text(encoding="utf-8").strip().splitlines()
            voice_lines = paths["voice_lora_bridge"].read_text(encoding="utf-8").strip().splitlines()
            context_lines = paths["multimodal_lora_context"].read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(truth_lines), 1)
            self.assertEqual(len(excluded_lines), 1)
            self.assertEqual(len(voice_lines), 1)
            self.assertEqual(len(context_lines), 1)

    def test_resolve_ambiguous_matches_uses_user_choice_callback(self):
        ambiguous = [
            {
                "media_path": "/tmp/media/episode_01.mp4",
                "subtitle_candidates": [
                    "/tmp/subs/episode_01.ko.srt",
                    "/tmp/subs/episode_01.final.srt",
                ],
                "match_type": "normalized",
            }
        ]

        result = resolve_ambiguous_matches(
            ambiguous,
            lambda media_path, candidates, match_type: candidates[1] if media_path.endswith("episode_01.mp4") and match_type == "normalized" else None,
        )

        self.assertEqual(
            result["pairs"],
            [
                {
                    "media_path": "/tmp/media/episode_01.mp4",
                    "subtitle_path": "/tmp/subs/episode_01.final.srt",
                    "match_type": "user_confirmed_normalized",
                }
            ],
        )
        self.assertEqual(result["unresolved"], [])

    def test_resolve_ambiguous_matches_keeps_unselected_items_unresolved(self):
        ambiguous = [
            {
                "media_path": "/tmp/media/episode_02.mp4",
                "subtitle_candidates": [
                    "/tmp/subs/episode_02.a.srt",
                    "/tmp/subs/episode_02.b.srt",
                ],
                "match_type": "exact",
            }
        ]

        result = resolve_ambiguous_matches(
            ambiguous,
            lambda _media_path, _candidates, _match_type: None,
        )

        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["unresolved"], ambiguous)


if __name__ == "__main__":
    unittest.main()
