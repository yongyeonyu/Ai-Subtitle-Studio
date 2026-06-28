import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.project.project_assets import copy_project_rows, externalize_project_text_assets, write_srt_track


class _StreamingRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __bool__(self):
        raise AssertionError("streaming rows should not be truth-tested")

    def __iter__(self):
        return iter(self._rows)


class ProjectAssetsTests(unittest.TestCase):
    def test_copy_project_rows_accepts_streaming_rows_without_truth_testing(self):
        rows = _StreamingRows([{"text": "a"}, "skip", {"text": "b"}])

        copied = copy_project_rows(rows)
        copied[0]["text"] = "changed"

        self.assertEqual([row["text"] for row in copied], ["changed", "b"])
        self.assertEqual(rows._rows[0]["text"], "a")

    def test_write_srt_track_reuses_single_materialized_stream_for_fps_inference(self):
        rows = _StreamingRows(
            [
                {"start": 0.0, "end": 1.0, "text": "첫 자막", "timeline_frame_rate": 30.0},
                {"start": 1.0, "end": 2.0, "text": "둘째 자막", "timeline_frame_rate": 30.0},
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "track.srt"

            info = write_srt_track(rows, str(path))

            text = path.read_text(encoding="utf-8")
        self.assertEqual(info["count"], 2)
        self.assertIn("첫 자막", text)
        self.assertIn("둘째 자막", text)

    def test_write_srt_track_can_return_compact_metadata_in_same_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "track.srt"

            info = write_srt_track(
                [{"start": 0.0, "end": 1.0, "text": "메타데이터", "speaker": "00"}],
                str(path),
                metadata_source="STT1",
                metadata_default_fps=30.0,
            )

        self.assertEqual(info["count"], 1)
        self.assertEqual(info["metadata"][0]["source"], "STT1")
        self.assertTrue(info["metadata"][0]["text_hash"])

    def test_externalize_project_text_assets_accepts_streaming_rows_without_truth_testing(self):
        final_rows = _StreamingRows(
            [
                {"start": 0.02, "end": 1.08, "text": "최종", "timeline_frame_rate": 30.0},
            ]
        )
        stt_rows = _StreamingRows(
            [
                {"start": 0.03, "end": 1.04, "text": "후보", "speaker": "00"},
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "project.json"
            project = {
                "project_path": str(project_path),
                "subtitles": {},
                "editor_state": {"stt": {"candidate_tracks": {}}},
                "analysis": {},
            }

            externalize_project_text_assets(
                str(project_path),
                project,
                final_segments=final_rows,
                stt_tracks={"STT1": stt_rows},
            )

            final_srt = (Path(tmp) / "project.assets" / "subtitles" / "final.srt").read_text(encoding="utf-8")
            stt_srt = (Path(tmp) / "project.assets" / "subtitles" / "stt1.srt").read_text(encoding="utf-8")

        self.assertIn("최종", final_srt)
        self.assertIn("후보", stt_srt)

    def test_externalize_project_text_assets_can_reuse_existing_stt_assets_without_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "project.json"
            project = {
                "project_path": str(project_path),
                "subtitles": {},
                "editor_state": {"stt": {"candidate_tracks": {}}},
                "analysis": {},
            }

            externalize_project_text_assets(
                str(project_path),
                project,
                final_segments=[{"start": 0.0, "end": 1.0, "text": "최종", "speaker": "00"}],
                stt_tracks={
                    "STT1": [{"start": 0.0, "end": 1.0, "text": "후보 일", "speaker": "00"}],
                    "STT2": [{"start": 0.0, "end": 1.0, "text": "후보 이", "speaker": "00"}],
                },
            )

            subtitle_dir = Path(tmp) / "project.assets" / "subtitles"
            stt1_path = subtitle_dir / "stt1.srt"
            stt2_path = subtitle_dir / "stt2.srt"
            before_stt1 = stt1_path.read_text(encoding="utf-8")
            before_stt2 = stt2_path.read_text(encoding="utf-8")

            with patch("core.project.project_assets.write_srt_track", wraps=write_srt_track) as writer:
                externalize_project_text_assets(
                    str(project_path),
                    project,
                    final_segments=[{"start": 0.0, "end": 1.0, "text": "수정 최종", "speaker": "00"}],
                    stt_tracks={},
                    rewrite_stt_reference_tracks=False,
                )
            self.assertEqual([Path(call.args[1]).name for call in writer.call_args_list], ["final.srt"])
            self.assertEqual(stt1_path.read_text(encoding="utf-8"), before_stt1)
            self.assertEqual(stt2_path.read_text(encoding="utf-8"), before_stt2)

    def test_externalize_project_text_assets_routes_final_srt_through_nle_save_export_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "project.json"
            project = {
                "project_path": str(project_path),
                "video": {"primary_fps": 30.0},
                "subtitles": {},
                "editor_state": {"stt": {"candidate_tracks": {}}},
                "analysis": {},
            }

            externalize_project_text_assets(
                str(project_path),
                project,
                final_segments=[
                    {
                        "id": "caption_1",
                        "start": 0.0,
                        "end": 1.0,
                        "text": "최종 자막",
                        "speaker": "00",
                        "stt_candidates": [{"source": "STT1", "text": "후보"}],
                    },
                    {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                    {"id": "preview_1", "start": 1.1, "end": 1.8, "text": "프리뷰", "_live_stt_preview": True},
                    {"id": "caption_2", "start": 2.0, "end": 3.0, "text": "저장 자막", "speaker": "01"},
                ],
                stt_tracks={},
            )

            final_srt = (Path(tmp) / "project.assets" / "subtitles" / "final.srt").read_text(encoding="utf-8")
            hot_cache = project["_hot_open_subtitle_segments_cache"]
            gap_rows = project["editor_state"]["rendering"]["subtitle_canvas"]["gap_segments"]
            metadata = project["asset_storage"]["tracks"]["final"]["metadata"]

        self.assertIn("최종 자막", final_srt)
        self.assertIn("저장 자막", final_srt)
        self.assertNotIn("프리뷰", final_srt)
        self.assertNotIn("후보", final_srt)
        self.assertEqual([row["text"] for row in hot_cache], ["최종 자막", "저장 자막"])
        self.assertTrue(all(row.get("_nle_runtime_surface") == "save_export" for row in hot_cache))
        self.assertFalse(any("stt_candidates" in row for row in hot_cache))
        self.assertEqual(len(gap_rows), 1)
        self.assertEqual([row.get("_nle_runtime_surface") for row in metadata], ["save_export", "save_export"])

    def test_externalize_project_text_assets_repairs_srt_quantized_micro_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "project.json"
            project = {
                "project_path": str(project_path),
                "video": {"primary_fps": 60.0},
                "subtitles": {},
                "editor_state": {"stt": {"candidate_tracks": {}}},
                "analysis": {},
            }

            externalize_project_text_assets(
                str(project_path),
                project,
                final_segments=[
                    {"id": "caption_1", "start": 162.233, "end": 163.633, "text": "첫째", "speaker": "00"},
                    {"id": "caption_2", "start": 163.6, "end": 166.9, "text": "둘째", "speaker": "01"},
                ],
                stt_tracks={},
            )

            final_srt = (Path(tmp) / "project.assets" / "subtitles" / "final.srt").read_text(encoding="utf-8")
            metadata = project["asset_storage"]["tracks"]["final"]["metadata"]

        self.assertIn("00:02:42,233 --> 00:02:43,633", final_srt)
        self.assertIn("00:02:43,633 --> 00:02:46,900", final_srt)
        self.assertEqual(metadata[0]["end_frame"], metadata[1]["start_frame"])
        self.assertEqual(project["subtitles"]["segment_count"], 2)

    def test_externalize_project_text_assets_normalizes_vector_canvas_time_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "project.json"
            project = {
                "project_path": str(project_path),
                "video": {"primary_fps": 30.0},
                "subtitles": {},
                "editor_state": {"stt": {"candidate_tracks": {}}},
                "analysis": {},
            }

            externalize_project_text_assets(
                str(project_path),
                project,
                final_segments=[
                    {
                        "id": "caption_1",
                        "kind": "subtitle_segment",
                        "time": {
                            "unit": "frame",
                            "start_frame": 60,
                            "end_frame": 120,
                            "timeline_frame_rate": 60.0,
                        },
                        "text": "벡터 첫째",
                        "speaker": "00",
                    },
                    {
                        "id": "caption_2",
                        "kind": "subtitle_segment",
                        "time": {
                            "unit": "frame",
                            "start_frame": 120,
                            "end_frame": 180,
                            "timeline_frame_rate": 60.0,
                        },
                        "text": "벡터 둘째",
                        "speaker": "01",
                    },
                ],
                stt_tracks={},
            )

            final_srt = (Path(tmp) / "project.assets" / "subtitles" / "final.srt").read_text(encoding="utf-8")
            hot_cache = project["_hot_open_subtitle_segments_cache"]
            metadata = project["asset_storage"]["tracks"]["final"]["metadata"]

        self.assertIn("00:00:01,000 --> 00:00:02,000", final_srt)
        self.assertIn("00:00:02,000 --> 00:00:03,000", final_srt)
        self.assertEqual([row["text"] for row in hot_cache], ["벡터 첫째", "벡터 둘째"])
        self.assertEqual([row["start"] for row in hot_cache], [1.0, 2.0])
        self.assertEqual([row["end"] for row in hot_cache], [2.0, 3.0])
        self.assertEqual([row["start_frame"] for row in metadata], [30, 60])
        self.assertEqual([row["end_frame"] for row in metadata], [60, 90])


if __name__ == "__main__":
    unittest.main()
