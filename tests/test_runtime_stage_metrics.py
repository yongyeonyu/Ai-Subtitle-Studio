import unittest

from core.runtime.stage_metrics import (
    classify_resource_label,
    record_native_bridge_metric,
    record_stage_done,
    reset_stage_metrics,
    snapshot_stage_metrics,
)


class RuntimeStageMetricsTests(unittest.TestCase):
    def setUp(self):
        reset_stage_metrics()

    def tearDown(self):
        reset_stage_metrics()

    def test_stage_metrics_roll_up_wait_busy_and_queue_depth(self):
        record_stage_done(
            "app_command:guided-subtitle-status",
            resource_label="automation",
            wait_ms=4.0,
            worker_busy_ms=2.5,
            queue_depth=2,
            ok=True,
        )

        snapshot = snapshot_stage_metrics()

        self.assertEqual(snapshot["event_count"], 1)
        self.assertEqual(snapshot["resources"]["automation"]["stage_done_count"], 1)
        self.assertEqual(snapshot["resources"]["automation"]["total_stage_wait_ms"], 4.0)
        self.assertEqual(snapshot["resources"]["automation"]["total_worker_busy_ms"], 2.5)
        self.assertEqual(snapshot["resources"]["automation"]["max_queue_depth"], 2)

    def test_native_bridge_metrics_roll_up_payload_and_cost(self):
        record_native_bridge_metric(
            "quality-score-jsonl-worker",
            payload_bytes=1024,
            encode_ms=1.25,
            native_ms=8.5,
            decode_ms=0.75,
            ok=True,
        )

        snapshot = snapshot_stage_metrics()

        native = snapshot["resources"]["native"]["native_bridge"]
        self.assertEqual(native["total_payload_bytes"], 1024)
        self.assertEqual(native["total_encode_ms"], 1.25)
        self.assertEqual(native["total_native_ms"], 8.5)
        self.assertEqual(native["total_decode_ms"], 0.75)

    def test_resource_label_classifier_keeps_stage_labels_stable(self):
        self.assertEqual(classify_resource_label("stt_transcribe_chunk:1/13"), "stt1")
        self.assertEqual(classify_resource_label("Fast-STT2 재검사"), "stt2")
        self.assertEqual(classify_resource_label("VAD 후처리"), "vad")
        self.assertEqual(classify_resource_label("자막 LLM cleanup"), "llm")
        self.assertEqual(classify_resource_label("자막 최적화/검수 중"), "subtitle_optimize")
        self.assertEqual(classify_resource_label("⏳ [STT+자막 LLM] 인식 결과 교정/분리 중"), "subtitle_optimize")
        self.assertEqual(classify_resource_label("timeline render playhead"), "render")


if __name__ == "__main__":
    unittest.main()
