import json
import os
import tempfile
import unittest

from core.project.project_io import read_project_file, read_project_storage_payload
from core.roughcut.cut_boundary_placeholder import extract_topicless_placeholders_from_project
from ui.project.project_panel import ProjectUIMixin


class _Backend:
    def __init__(self):
        self.calls = []

    def _auto_scan_cut_boundaries_for_start(self, project_path, files):
        self.calls.append((project_path, list(files or [])))


class _ProjectUI(ProjectUIMixin):
    def __init__(self, settings=None):
        self.backend = _Backend()
        self._settings = dict(settings or {})

    def _load_local_settings(self):
        return dict(self._settings)


class ProjectCutBoundaryResumeTests(unittest.TestCase):
    def _write_project(self, path, media, analysis):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": "03.15.00",
                    "media": [{"path": media}],
                    "user_settings": {
                        "scan_cut_boundary_level": "medium",
                        "cut_boundary_level": "medium",
                    },
                    "analysis": dict(analysis or {}),
                },
                handle,
                ensure_ascii=False,
            )

    def test_stale_empty_done_project_restarts_cut_boundary_prescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.json")
            open(media, "wb").close()
            self._write_project(
                project_path,
                media,
                {
                    "cut_boundaries": [],
                    "cut_boundary_prescan_done": True,
                    "cut_boundary_cache_path": "/tmp/empty-cache.json",
                    "cut_boundary_cache_type": "cut_boundaries_only",
                    "cut_boundary_topicless_middle_segments": [
                        {"id": "A", "title": "주제없음", "is_topicless_placeholder": True}
                    ],
                },
            )
            project = read_project_file(project_path)

            ui = _ProjectUI({"scan_cut_boundary_level": "medium", "cut_boundary_level": "medium"})
            resumed = ui._resume_cut_boundary_prescan_for_open_project(project_path, project, [media])

            self.assertTrue(resumed)
            self.assertEqual(ui.backend.calls, [(project_path, [media])])
            saved = read_project_storage_payload(project_path)
            self.assertNotIn("cut_boundary_prescan_done", saved["analysis"])
            self.assertNotIn("cut_boundary_cache_path", saved["analysis"])
            self.assertNotIn("cut_boundary_cache_type", saved["analysis"])

    def test_confirmed_cut_boundaries_do_not_restart_prescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.json")
            open(media, "wb").close()
            self._write_project(
                project_path,
                media,
                {
                    "cut_boundaries": [{"timeline_sec": 12.0, "timeline_frame": 360, "fps": 30.0}],
                    "cut_boundary_prescan_done": True,
                },
            )
            project = read_project_file(project_path)

            ui = _ProjectUI({"scan_cut_boundary_level": "medium", "cut_boundary_level": "medium"})
            resumed = ui._resume_cut_boundary_prescan_for_open_project(project_path, project, [media])

            self.assertFalse(resumed)
            self.assertEqual(ui.backend.calls, [])

    def test_roughcut_exact_stitched_boundaries_skip_prescan_and_seed_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.json")
            open(media, "wb").close()
            self._write_project(
                project_path,
                media,
                {
                    "cut_boundaries": [],
                    "cut_boundary_prescan_done": True,
                    "cut_boundary_cache_path": "/tmp/stale-cache.json",
                    "cut_boundary_cache_type": "cut_boundaries_only",
                    "cut_boundary_provisional_boundaries": [
                        {"timeline_sec": 4.1, "timeline_frame": 123, "fps": 30.0, "status": "provisional"}
                    ],
                },
            )
            saved = read_project_file(project_path)
            saved["roughcut_state"] = {
                "selected_candidate_id": "candidate_a",
                "candidates": [
                    {
                        "candidate_id": "candidate_a",
                        "outputs": {
                            "render_plan": {
                                "stitched_cut_boundaries": [
                                    {
                                        "timeline_sec": 4.0,
                                        "timeline_frame": 120,
                                        "fps": 30.0,
                                        "source": "roughcut_concat_join",
                                        "reason": "roughcut_concat_segment_join",
                                        "verified": True,
                                        "hard_cut_allowed": True,
                                    }
                                ]
                            }
                        },
                    }
                ],
            }
            with open(project_path, "w", encoding="utf-8") as handle:
                json.dump(saved, handle, ensure_ascii=False)

            project = read_project_file(project_path)
            ui = _ProjectUI({"scan_cut_boundary_level": "medium", "cut_boundary_level": "medium"})
            resumed = ui._resume_cut_boundary_prescan_for_open_project(project_path, project, [media])

            self.assertFalse(resumed)
            self.assertEqual(ui.backend.calls, [])
            persisted = read_project_storage_payload(project_path)
            self.assertEqual([row["timeline_sec"] for row in persisted["analysis"]["cut_boundaries"]], [4.0])
            self.assertEqual(persisted["analysis"]["cut_boundary_provisional_boundaries"], [])
            self.assertNotIn("cut_boundary_prescan_done", persisted["analysis"])
            self.assertNotIn("cut_boundary_cache_path", persisted["analysis"])
            self.assertNotIn("cut_boundary_cache_type", persisted["analysis"])

    def test_finalized_topicless_placeholder_only_project_does_not_restart_prescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.json")
            open(media, "wb").close()
            self._write_project(
                project_path,
                media,
                {
                    "cut_boundaries": [],
                    "cut_boundary_topicless_finalized": True,
                    "cut_boundary_topicless_middle_segments": [
                        {
                            "id": "A",
                            "major_id": "A",
                            "title": "주제없음",
                            "is_topicless_placeholder": True,
                            "timeline_start_frame": 0,
                            "timeline_end_frame": 300,
                        }
                    ],
                },
            )
            project = read_project_file(project_path)

            ui = _ProjectUI({"scan_cut_boundary_level": "medium", "cut_boundary_level": "medium"})
            resumed = ui._resume_cut_boundary_prescan_for_open_project(project_path, project, [media])

            self.assertFalse(resumed)
            self.assertEqual(ui.backend.calls, [])

    def test_final_middle_segments_without_confirmed_cuts_do_not_restart_prescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.json")
            open(media, "wb").close()
            self._write_project(
                project_path,
                media,
                {
                    "cut_boundaries": [],
                    "cut_boundary_topicless_middle_segments": [
                        {
                            "id": "A",
                            "major_id": "A",
                            "title": "주제없음",
                            "is_topicless_placeholder": True,
                        }
                    ],
                    "middle_segments": [
                        {
                            "id": "A",
                            "major_id": "A",
                            "title": "도입 주제",
                            "summary": "실제 최종 중분류",
                            "start": 0.0,
                            "end": 12.0,
                            "status": "confirmed",
                        }
                    ],
                },
            )
            project = read_project_file(project_path)

            ui = _ProjectUI({"scan_cut_boundary_level": "medium", "cut_boundary_level": "medium"})
            resumed = ui._resume_cut_boundary_prescan_for_open_project(project_path, project, [media])

            self.assertFalse(resumed)
            self.assertEqual(ui.backend.calls, [])

    def test_extract_topicless_placeholders_prefers_placeholder_rows_over_final_middle_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.json")
            open(media, "wb").close()
            self._write_project(
                project_path,
                media,
                {
                    "cut_boundary_topicless_middle_segments": [
                        {
                            "id": "P1",
                            "major_id": "A",
                            "title": "주제없음",
                            "is_topicless_placeholder": True,
                            "start": 0.0,
                            "end": 10.0,
                        }
                    ],
                    "middle_segments": [
                        {
                            "id": "M1",
                            "major_id": "A",
                            "title": "실제 중분류",
                            "status": "confirmed",
                            "start": 0.0,
                            "end": 10.0,
                        }
                    ],
                },
            )

            rows = extract_topicless_placeholders_from_project(project_path)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "주제없음")
            self.assertTrue(rows[0]["is_topicless_placeholder"])

    def test_extract_topicless_placeholders_returns_empty_without_placeholder_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "sample.mp4")
            project_path = os.path.join(tmp, "sample.json")
            open(media, "wb").close()
            self._write_project(
                project_path,
                media,
                {
                    "middle_segments": [
                        {
                            "id": "M1",
                            "major_id": "A",
                            "title": "실제 중분류",
                            "status": "confirmed",
                            "start": 0.0,
                            "end": 10.0,
                        }
                    ],
                },
            )

            rows = extract_topicless_placeholders_from_project(project_path)

            self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
