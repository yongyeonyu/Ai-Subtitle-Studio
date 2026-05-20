import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.debug_guided_subtitle_memory import (
    _has_completed_guided_snapshot,
    status_flag_summary,
    status_is_processing,
)


class DebugGuidedSubtitleMemoryTests(unittest.TestCase):
    def test_status_is_processing_detects_backend_and_editor_state(self):
        self.assertTrue(status_is_processing({"backend_active": True}))
        self.assertTrue(status_is_processing({"editor_state": "ST_PROC"}))
        self.assertTrue(status_is_processing({"runtime_resource": {"active_labels": ["pipeline"]}}))
        self.assertTrue(status_is_processing({"queue_runtime": {"active_probe_text": "자막 생성 중"}}))
        self.assertFalse(status_is_processing({"queue_runtime": {"all_done": True}}))

    def test_status_flag_summary_detects_critical_worker_reuse_stop_log(self):
        flags = status_flag_summary(
            {
                "recent_stage_logs": ["메모리 critical: STT persistent worker 재사용 중단"],
                "recent_logs": [],
            }
        )

        self.assertTrue(flags["saw_critical_reuse_stop"])
        self.assertEqual(flags["recent_stage_log_count"], 1)

    def test_has_completed_guided_snapshot_detects_completed_png(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "06_completed.png").write_bytes(b"png")
            self.assertTrue(_has_completed_guided_snapshot(path))


if __name__ == "__main__":
    unittest.main()
