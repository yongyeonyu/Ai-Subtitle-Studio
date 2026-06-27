import copy
import tempfile
import unittest
from pathlib import Path

from core.project.nle_render_export_parity import (
    NLE_RENDER_EXPORT_PARITY_SCHEMA,
    assert_project_nle_render_export_parity,
    build_project_nle_render_export_parity_report,
)
from core.project.project_context import build_editor_state
from core.project.project_io import clear_project_file_cache, read_project_file, write_project_file


def _project_with_render_exports(root: Path) -> dict:
    media_path = root / "source.mov"
    media_path.write_bytes(b"media")
    segment_rows = [
        {
            "segment_id": "chapter_0001",
            "source_path": str(media_path),
            "source_start": 0.0,
            "source_end": 2.0,
            "output_start": 0.0,
            "output_end": 2.0,
            "chapter_id": "chapter_0001",
        },
        {
            "segment_id": "chapter_0002",
            "source_path": str(media_path),
            "source_start": 3.0,
            "source_end": 6.0,
            "output_start": 2.0,
            "output_end": 5.0,
            "chapter_id": "chapter_0002",
        },
    ]
    manifest_rows = [
        {
            "segment_id": row["segment_id"],
            "source_path": row["source_path"],
            "source_start": row["source_start"],
            "source_end": row["source_end"],
            "output_start": row["output_start"],
            "output_end": row["output_end"],
        }
        for row in segment_rows
    ]
    stitched = [
        {
            "time": 2.0,
            "timeline_sec": 2.0,
            "source": "roughcut_concat_join",
            "segment_before_id": "chapter_0001",
            "segment_after_id": "chapter_0002",
        }
    ]
    return {
        "project_name": "render_export_parity",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "timeline": {
            "total_duration": 6.0,
            "timebase": {"primary_fps": 30.0},
            "tracks": [
                {
                    "clips": [
                        {
                            "id": "clip_main",
                            "source_path": str(media_path),
                            "type": "video",
                            "source_duration": 6.0,
                            "timeline_start": 0.0,
                            "timeline_end": 6.0,
                            "fps": 30.0,
                            "order": 0,
                        }
                    ]
                }
            ],
        },
        "editor_state": build_editor_state(
            mode="single",
            media_files=[str(media_path)],
            segments=[
                {
                    "id": "caption_1",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "first",
                    "speaker": "00",
                    "stt_candidates": [
                        {"source": "STT1", "start": 0.0, "end": 1.0, "text": "first raw", "score": 0.8}
                    ],
                },
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                {
                    "id": "caption_2",
                    "start": 2.0,
                    "end": 3.0,
                    "text": "second",
                    "speaker": "01",
                    "stt_candidates": [
                        {"source": "STT2", "start": 2.0, "end": 3.0, "text": "second raw", "score": 0.7}
                    ],
                },
            ],
            stt_preview_segments=[
                {"start": 4.0, "end": 5.0, "text": "diagnostic only", "stt_preview_source": "STT1"}
            ],
            cut_boundaries=[{"time": 2.0, "source": "visual", "status": "confirmed"}],
            primary_fps=30.0,
        ),
        "analysis": {"cut_boundaries": [{"time": 2.0, "source": "visual", "status": "confirmed"}]},
        "roughcut_state": {
            "selected_candidate_id": "roughcut_a",
            "candidates": [
                {
                    "candidate_id": "roughcut_a",
                    "name": "roughcut A",
                    "outputs": {
                        "edl": {
                            "duration": 5.0,
                            "segments": segment_rows,
                            "stitched_cut_boundaries": stitched,
                        },
                        "render_plan": {
                            "output_path": str(root / "roughcut.mov"),
                            "render_mode": "sync_safe",
                            "segment_manifest": manifest_rows,
                            "stitched_cut_boundaries": stitched,
                        },
                    },
                }
            ],
        },
    }


class ProjectNleRenderExportParityTests(unittest.TestCase):
    def test_render_export_parity_surfaces_read_same_final_nle_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_path = root / "render-export-parity.aissproj"
            project = _project_with_render_exports(root)

            write_project_file(str(project_path), copy.deepcopy(project))
            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            report = assert_project_nle_render_export_parity(loaded, project_path=str(project_path))

        self.assertEqual(report.schema, NLE_RENDER_EXPORT_PARITY_SCHEMA)
        self.assertEqual(report.diff_summary, "ok")
        self.assertEqual(report.caption_count, 2)
        self.assertEqual(report.gap_count, 1)
        self.assertEqual(report.overlap_count, 0)
        self.assertEqual(report.max_active_segments, 1)
        self.assertEqual(report.render_segment_count, 2)
        self.assertEqual(report.manifest_count, 2)
        self.assertEqual(report.stitched_boundary_count, 1)
        surfaces = {surface.target_surface: surface for surface in report.surface_reports}
        self.assertEqual(
            set(surfaces),
            {"source_subtitles", "final_overlay", "global_canvas", "roughcut_sidecar", "exported_assets"},
        )
        self.assertTrue(all(surface.stable for surface in surfaces.values()))
        self.assertEqual(surfaces["source_subtitles"].projection_hash, report.final_projection_hash)
        self.assertEqual(surfaces["final_overlay"].projection_hash, report.final_projection_hash)
        self.assertEqual(surfaces["global_canvas"].projection_hash, report.final_projection_hash)
        self.assertEqual(surfaces["final_overlay"].candidate_count, 0)
        self.assertEqual(surfaces["final_overlay"].gap_count, 0)
        self.assertEqual(surfaces["global_canvas"].gap_count, 1)
        self.assertGreaterEqual(surfaces["global_canvas"].candidate_count, 2)
        self.assertEqual(surfaces["roughcut_sidecar"].marker_count, 1)
        self.assertEqual(surfaces["exported_assets"].render_segment_count, 2)
        self.assertEqual(surfaces["exported_assets"].manifest_count, 2)

    def test_render_export_parity_rejects_export_manifest_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _project_with_render_exports(root)
            candidate = project["roughcut_state"]["candidates"][0]
            candidate["outputs"]["render_plan"]["segment_manifest"] = candidate["outputs"]["render_plan"]["segment_manifest"][:1]

            report = build_project_nle_render_export_parity_report(project, project_path=str(root / "drift.aissproj"))

        self.assertIn("export_asset_projection_drift", report.diff_summary)
        surfaces = {surface.target_surface: surface for surface in report.surface_reports}
        self.assertFalse(surfaces["exported_assets"].stable)
        with self.assertRaisesRegex(ValueError, "nle_render_export_parity_failed:export_asset_projection_drift"):
            assert_project_nle_render_export_parity(project)


if __name__ == "__main__":
    unittest.main()
