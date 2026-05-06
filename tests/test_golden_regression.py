import json
import tempfile
import unittest
from pathlib import Path

from core.personalization.golden_regression import (
    GOLDEN_SUITE_MANIFEST_SCHEMA,
    evaluate_golden_case,
    evaluate_golden_suite,
    evaluate_golden_suite_manifest,
    golden_regression_cli,
    load_golden_suite_manifest,
    write_golden_report,
)


def _write_srt(path: Path, blocks: list[tuple[str, str, str]]) -> None:
    lines: list[str] = []
    for index, (start, end, text) in enumerate(blocks, start=1):
        lines.extend([str(index), f"{start} --> {end}", text, ""])
    path.write_text("\n".join(lines), encoding="utf-8")


class GoldenRegressionTests(unittest.TestCase):
    def test_golden_case_passes_for_close_candidate_and_reports_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            truth = root / "truth.srt"
            candidate = root / "candidate.srt"
            _write_srt(
                truth,
                [
                    ("00:00:01,000", "00:00:03,000", "안녕하세요"),
                    ("00:00:03,200", "00:00:05,800", "오늘은 그러니까\n여기까지 할게요"),
                ],
            )
            _write_srt(
                candidate,
                [
                    ("00:00:01,000", "00:00:03,000", "안녕하세요"),
                    ("00:00:03,250", "00:00:05,750", "오늘은 그러니까\n여기까지 할게요"),
                ],
            )

            report = evaluate_golden_case(
                truth_srt_path=truth,
                candidate_srt_path=candidate,
                case_id="close-case",
                settings={"sub_max_cps": 14},
            )

            self.assertTrue(report["passed"])
            self.assertGreater(report["metrics"]["final_score"], 90.0)
            self.assertLess(report["metrics"]["cer"], 0.05)
            self.assertGreater(report["metrics"]["timing_iou"], 0.9)
            self.assertIn("decision_explanations", report)

    def test_golden_suite_fails_bad_candidate_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            truth = root / "truth.srt"
            bad = root / "bad.srt"
            output = root / "report.json"
            _write_srt(
                truth,
                [
                    ("00:00:01,000", "00:00:03,000", "행사장에 도착했습니다"),
                    ("00:00:03,200", "00:00:05,800", "차량을 살펴볼게요"),
                ],
            )
            _write_srt(
                bad,
                [
                    ("00:00:10,000", "00:00:11,000", "Thank you for watching"),
                    ("00:00:12,000", "00:00:13,000", "전혀 다른 자막입니다"),
                ],
            )

            suite = evaluate_golden_suite(
                [{"case_id": "bad-case", "truth_srt_path": truth, "candidate_srt_path": bad}],
                thresholds={"final_score_min": 80.0, "hallucination_proxy_rate_max": 0.0},
            )
            saved_path = write_golden_report(suite, output)
            saved = json.loads(Path(saved_path).read_text(encoding="utf-8"))

            self.assertFalse(suite["passed"])
            self.assertEqual(saved["failed_cases"], 1)
            self.assertTrue(saved["cases"][0]["failures"])
            self.assertGreater(saved["cases"][0]["metrics"]["hallucination_proxy_rate"], 0.0)

    def test_manifest_evaluation_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            truth = root / "truth.srt"
            candidate = root / "candidate.srt"
            manifest = root / "golden_suite.json"
            output = root / "manifest_report.json"
            _write_srt(
                truth,
                [
                    ("00:00:01,000", "00:00:03,000", "테스트 자막입니다"),
                    ("00:00:03,200", "00:00:04,800", "스타일을 유지합니다"),
                ],
            )
            _write_srt(
                candidate,
                [
                    ("00:00:01,020", "00:00:03,000", "테스트 자막입니다"),
                    ("00:00:03,220", "00:00:04,780", "스타일을 유지합니다"),
                ],
            )
            manifest.write_text(
                json.dumps(
                    {
                        "schema": GOLDEN_SUITE_MANIFEST_SCHEMA,
                        "thresholds": {"final_score_min": 80.0},
                        "cases": [
                            {
                                "case_id": "manifest-case",
                                "truth_srt_path": str(truth),
                                "candidate_srt_path": str(candidate),
                                "settings": {"sub_max_cps": 16},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            loaded = load_golden_suite_manifest(manifest)
            report = evaluate_golden_suite_manifest(manifest, output_path=output)
            saved = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(loaded["schema"], GOLDEN_SUITE_MANIFEST_SCHEMA)
            self.assertEqual(len(loaded["cases"]), 1)
            self.assertTrue(report["passed"])
            self.assertEqual(report["manifest_schema"], GOLDEN_SUITE_MANIFEST_SCHEMA)
            self.assertEqual(saved["total_cases"], 1)
            self.assertEqual(saved["passed_cases"], 1)

    def test_cli_fail_on_regression_returns_non_zero_for_bad_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            truth = root / "truth.srt"
            bad = root / "bad.srt"
            manifest = root / "golden_suite.json"
            output = root / "cli_report.json"
            _write_srt(
                truth,
                [("00:00:01,000", "00:00:03,000", "정답 자막입니다")],
            )
            _write_srt(
                bad,
                [("00:00:10,000", "00:00:11,000", "Thank you for watching")],
            )
            manifest.write_text(
                json.dumps(
                    {
                        "schema": GOLDEN_SUITE_MANIFEST_SCHEMA,
                        "thresholds": {
                            "final_score_min": 99.0,
                            "hallucination_proxy_rate_max": 0.0,
                        },
                        "cases": [
                            {
                                "case_id": "cli-bad-case",
                                "truth_srt_path": str(truth),
                                "candidate_srt_path": str(bad),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            exit_code = golden_regression_cli(
                [
                    "--manifest",
                    str(manifest),
                    "--output",
                    str(output),
                    "--fail-on-regression",
                ]
            )
            saved = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(exit_code, 1)
            self.assertFalse(saved["passed"])
            self.assertEqual(saved["failed_cases"], 1)

    def test_missing_manifest_uses_default_empty_suite(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"

            loaded = load_golden_suite_manifest(missing)

            self.assertEqual(loaded["schema"], GOLDEN_SUITE_MANIFEST_SCHEMA)
            self.assertEqual(loaded["cases"], [])


if __name__ == "__main__":
    unittest.main()
