import tempfile
import unittest
from pathlib import Path

from core.personalization.nas_truth_learning import (
    build_nas_truth_learning_dry_run,
    build_nas_truth_manifest,
    parse_nas_truth_plan,
)


def _plan_text(root: Path, item_lines: list[str]) -> str:
    return "\n".join(
        [
            "# NAS Subtitle Benchmark 50 Action Plan",
            "",
            f"대상 NAS 루트: `{root}`",
            "앱 버전 기준: `04.00.17`",
            "",
            "## 50 Action Items",
            "",
            *item_lines,
            "",
        ]
    )


def _item_line(index: int, title: str | None = None) -> str:
    name = title or f"영상 {index:02d}"
    return (
        f"- [ ] {index:02d}. `{name}` | "
        f"folder: `[folder-{index:02d}]` | "
        f"video: `{name}.MP4` | "
        f"truth: `{name}.srt`"
    )


class NasTruthLearningTests(unittest.TestCase):
    def test_parse_plan_extracts_nas_root_version_and_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "nas"
            plan_path = Path(tmpdir) / "plan.md"
            plan_path.write_text(
                _plan_text(
                    root,
                    [
                        _item_line(6, "미니 ACEMAN 시승기"),
                        _item_line(48, "헤이딜러_최종"),
                    ],
                ),
                encoding="utf-8",
            )

            parsed = parse_nas_truth_plan(plan_path)

            self.assertEqual(parsed["nas_root"], str(root))
            self.assertEqual(parsed["app_version"], "04.00.17")
            self.assertEqual([item["action_item"] for item in parsed["items"]], [6, 48])
            self.assertEqual(parsed["items"][0]["dataset_split"], "validation")
            self.assertEqual(parsed["items"][1]["dataset_split"], "train")
            self.assertEqual(parsed["items"][1]["fixture_role"], "calibration")

    def test_manifest_resolves_paths_and_missing_reasons(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "nas"
            folder = root / "[folder-48]"
            folder.mkdir(parents=True)
            (folder / "헤이딜러_최종.MP4").write_bytes(b"video")
            plan_path = Path(tmpdir) / "plan.md"
            plan_path.write_text(
                _plan_text(root, [_item_line(48, "헤이딜러_최종")]),
                encoding="utf-8",
            )

            manifest = build_nas_truth_manifest(plan_path=plan_path)

            self.assertEqual(manifest["counts"]["items_total"], 1)
            self.assertEqual(manifest["counts"]["present_pairs"], 0)
            self.assertEqual(manifest["counts"]["missing_media"], 0)
            self.assertEqual(manifest["counts"]["missing_subtitle"], 1)
            item = manifest["items"][0]
            self.assertEqual(item["pair_basis"], "exact_stem_match")
            self.assertTrue(item["exists"]["media"])
            self.assertFalse(item["exists"]["subtitle"])
            self.assertEqual(item["missing_reasons"], ["missing_subtitle"])
            self.assertEqual(item["fixture_role"], "calibration")

    def test_manifest_uses_fixed_train_validation_holdout_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "nas"
            plan_path = Path(tmpdir) / "plan.md"
            plan_path.write_text(
                _plan_text(root, [_item_line(index) for index in range(1, 51)]),
                encoding="utf-8",
            )

            manifest = build_nas_truth_manifest(plan_path=plan_path, check_files=False)

            self.assertEqual(manifest["counts"]["items_total"], 50)
            self.assertEqual(manifest["counts"]["dataset_splits"], {"holdout": 5, "train": 40, "validation": 5})
            self.assertEqual(manifest["counts"]["fixture_roles"], {"calibration": 2, "primary": 48})

    def test_manifest_ignores_extra_candidates_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "nas"
            plan_path = Path(tmpdir) / "plan.md"
            plan_path.write_text(
                _plan_text(root, [_item_line(index) for index in range(1, 51)])
                + "\n".join(
                    [
                        "## Extra Candidates",
                        "",
                        _item_line(51, "BMW X1 m35i 리뷰"),
                        _item_line(52, "M FEST 2026"),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            manifest = build_nas_truth_manifest(plan_path=plan_path, check_files=False)

            self.assertEqual(manifest["counts"]["items_total"], 50)
            self.assertEqual(manifest["items"][-1]["action_item"], 50)

    def test_dry_run_can_build_truth_records_without_writing_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "nas"
            folder = root / "[folder-48]"
            folder.mkdir(parents=True)
            (folder / "헤이딜러_최종.MP4").write_bytes(b"video")
            (folder / "헤이딜러_최종.srt").write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:01,000 --> 00:00:03,000",
                        "(효과음) 안녕하세요.",
                        "",
                        "2",
                        "00:00:04,000 --> 00:00:05,500",
                        "[자막] 좋은 가격입니다.",
                        "",
                        "3",
                        "00:00:06,000 --> 00:00:07,000",
                        "???",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            plan_path = Path(tmpdir) / "plan.md"
            plan_path.write_text(
                _plan_text(root, [_item_line(48, "헤이딜러_최종")]),
                encoding="utf-8",
            )

            dry_run = build_nas_truth_learning_dry_run(
                plan_path=plan_path,
                include_truth_records=True,
            )

            summary = dry_run["summary"]
            self.assertTrue(summary["read_only"])
            self.assertEqual(summary["present_pairs"], 1)
            self.assertEqual(summary["analyzed_pairs"], 1)
            self.assertEqual(summary["truth_rows"], 2)
            self.assertEqual(summary["excluded_parenthetical_rows"], 2)
            self.assertEqual(summary["voice_bridge_rows"], 2)
            self.assertEqual(summary["multimodal_context_rows"], 1)
            self.assertEqual(summary["skipped_empty_text"], 0)
            self.assertEqual(summary["skipped_pure_symbols"], 1)
            self.assertEqual(summary["importable_truth_rows"], 2)
            self.assertEqual(summary["split_analysis_effective_rows"], 3)
            self.assertFalse((root / "lora_personalization").exists())


if __name__ == "__main__":
    unittest.main()
