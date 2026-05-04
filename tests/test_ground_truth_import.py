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
                    ]
                ),
                encoding="utf-8",
            )

            result = build_truth_table_records_from_srt(media_path, subtitle_path, media_id="media-001")

            self.assertEqual(result["stats"]["segments_total"], 3)
            self.assertEqual(result["stats"]["truth_rows"], 2)
            self.assertEqual(result["stats"]["excluded_parenthetical_rows"], 2)
            self.assertEqual(result["stats"]["skipped_empty_text"], 1)
            self.assertEqual(result["truth_rows"][0]["speech_training_text"], "안녕하세요!")
            self.assertEqual(result["truth_rows"][0]["excluded_parenthetical_text"], "박수")
            self.assertEqual(result["truth_rows"][1]["detected_split_rule"], "그러니까")
            self.assertEqual(result["truth_rows"][1]["line_break_pattern"], "8|8")

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

            paths = store_paths(store_dir)
            truth_lines = paths["truth_table"].read_text(encoding="utf-8").strip().splitlines()
            excluded_lines = paths["excluded_parentheticals"].read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(truth_lines), 1)
            self.assertEqual(len(excluded_lines), 1)

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
