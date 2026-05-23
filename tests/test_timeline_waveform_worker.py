import unittest
from unittest.mock import patch

import numpy as np

from core.native_swift_subtitle import find_native_cli_path
from core.native_swift_timeline import (
    apply_timing_drag_via_swift,
    build_segment_layout_via_swift,
    build_waveform_columns_via_swift,
    playhead_dirty_rect_via_swift,
)
from ui.timeline.timeline_waveform import (
    WAVEFORM_SAMPLE_RATE,
    _decode_f32le_samples,
    _downsample_waveform_raw,
    _downsample_waveform_samples,
    _ffmpeg_waveform_cmd,
    patch_waveform_buffer,
)


class TimelineWaveformWorkerTests(unittest.TestCase):
    def test_decode_f32le_samples_from_pipe_bytes(self):
        original = np.array([-0.25, 0.5, 1.0], dtype=np.float32)

        decoded = _decode_f32le_samples(original.tobytes())

        np.testing.assert_allclose(decoded, original)
        self.assertEqual(decoded.dtype, np.float32)

    def test_downsample_waveform_samples_normalizes_peaks(self):
        samples = np.zeros(WAVEFORM_SAMPLE_RATE, dtype=np.float32)
        samples[100:110] = 0.5
        samples[1000:1010] = -1.0

        waveform, duration = _downsample_waveform_samples(samples)

        self.assertAlmostEqual(duration, 1.0, places=3)
        self.assertEqual(len(waveform), 100)
        self.assertAlmostEqual(float(waveform.max()), 1.0, places=6)

    def test_downsample_waveform_raw_falls_back_to_python(self):
        samples = np.zeros(WAVEFORM_SAMPLE_RATE, dtype=np.float32)
        samples[100:110] = 0.5
        samples[1000:1010] = -1.0

        waveform, duration = _downsample_waveform_raw(samples.tobytes())

        self.assertAlmostEqual(duration, 1.0, places=3)
        self.assertEqual(len(waveform), 100)
        self.assertAlmostEqual(float(waveform.max()), 1.0, places=6)

    def test_downsample_waveform_raw_prefers_subtitle_waveform_native_helper(self):
        samples = np.zeros(WAVEFORM_SAMPLE_RATE, dtype=np.float32)
        expected = np.array([0.25, 1.0], dtype=np.float32)

        with patch("core.native_subtitle_waveform.downsample_f32le", return_value=(expected, 1.0)) as native_downsample:
            waveform, duration = _downsample_waveform_raw(samples.tobytes())

        native_downsample.assert_called_once()
        self.assertEqual(duration, 1.0)
        np.testing.assert_allclose(waveform, expected)

    def test_ffmpeg_waveform_cmd_streams_to_stdout(self):
        cmd = _ffmpeg_waveform_cmd("/tmp/input.mp4")

        self.assertIn("pipe:1", cmd)
        self.assertIn("-nostdin", cmd)
        self.assertNotIn(".raw", " ".join(cmd))

    def test_patch_waveform_buffer_reuses_existing_allocation(self):
        original = np.zeros(10, dtype=np.float32)

        patched = patch_waveform_buffer(
            original,
            start_px=3,
            total_px=10,
            values=np.array([0.25, 0.5, 0.75], dtype=np.float32),
        )

        self.assertIs(patched, original)
        np.testing.assert_allclose(patched, np.array([0, 0, 0, 0.25, 0.5, 0.75, 0, 0, 0, 0], dtype=np.float32))

    def test_patch_waveform_buffer_allocates_when_target_is_missing(self):
        patched = patch_waveform_buffer(
            None,
            start_px=1,
            total_px=5,
            values=[1.0, 0.5, 0.25],
        )

        self.assertEqual(patched.dtype, np.float32)
        np.testing.assert_allclose(patched, np.array([0, 1.0, 0.5, 0.25, 0], dtype=np.float32))

    def test_swift_timeline_columns_bridge_when_available(self):
        if find_native_cli_path() is None:
            self.skipTest("AIStudioNativeCLI release build is not available")
        wf = np.array([0.0, 0.5, 1.0, 0.25], dtype=np.float32)
        with patch.dict("os.environ", {"AI_SUBTITLE_STUDIO_SWIFT_TIMELINE": "1"}):
            columns = build_waveform_columns_via_swift(
                wf,
                width=4,
                total_duration=4.0,
                vad_segments=[{"start": 1.0, "end": 2.0}],
            )

        self.assertEqual(columns, [(1, False), (7, True), (14, True), (3, False)])

    def test_swift_timeline_segment_layout_bridge_when_available(self):
        if find_native_cli_path() is None:
            self.skipTest("AIStudioNativeCLI release build is not available")
        with patch.dict("os.environ", {"AI_SUBTITLE_STUDIO_SWIFT_TIMELINE": "1"}):
            result = build_segment_layout_via_swift(
                [
                    {"line": 1, "start": 0.0, "end": 0.5},
                    {"line": 2, "start": 1.5, "end": 2.5, "lane": 1},
                ],
                view_start=1.0,
                view_end=3.0,
                width=200,
                top=10,
                row_height=20,
                lane_gap=4,
                playhead_sec=2.0,
            )

        self.assertIsNotNone(result)
        layouts = result.get("layouts", [])
        self.assertEqual(len(layouts), 1)
        self.assertEqual(layouts[0]["line"], 2)
        self.assertEqual(layouts[0]["x"], 50)
        self.assertEqual(layouts[0]["width"], 100)
        self.assertTrue(layouts[0]["isActive"])

    def test_swift_timeline_playhead_dirty_bridge_when_available(self):
        if find_native_cli_path() is None:
            self.skipTest("AIStudioNativeCLI release build is not available")
        with patch.dict("os.environ", {"AI_SUBTITLE_STUDIO_SWIFT_TIMELINE": "1"}):
            rect = playhead_dirty_rect_via_swift(
                old_sec=1.0,
                new_sec=2.0,
                view_start=0.0,
                view_end=4.0,
                width=400,
                height=36,
                extra_px=8,
            )

        self.assertEqual(rect, {"height": 36, "left": 92, "top": 0, "width": 117, "x": 200})

    def test_swift_timing_drag_bridge_shapes_payload(self):
        with patch("core.native_swift_timeline._request_worker", return_value={"end": 2.3}) as request_worker:
            result = apply_timing_drag_via_swift(
                edge="square_right",
                delta=0.28,
                original_start=1.0,
                original_end=2.0,
                min_value=1.1,
                max_value=4.0,
                frame_rate=10.0,
                snap_threshold=0.12,
                candidates=[
                    {"time": 2.3, "kind": "subtitle", "threshold": 0.15},
                    {"time": 3.0, "kind": "timeline"},
                    {"time": "bad"},
                ],
            )

        self.assertEqual(result, {"end": 2.3})
        request_worker.assert_called_once()
        task, payload = request_worker.call_args.args
        self.assertEqual(task, "timing_drag")
        self.assertEqual(payload["edge"], "square_right")
        self.assertAlmostEqual(payload["delta"], 0.28, places=6)
        self.assertEqual(
            payload["candidates"],
            [
                {"time": 2.3, "kind": "subtitle", "threshold": 0.15},
                {"time": 3.0, "kind": "timeline", "threshold": 0.12},
            ],
        )


if __name__ == "__main__":
    unittest.main()
