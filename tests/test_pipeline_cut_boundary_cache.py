# Version: 03.12.00
# Phase: PHASE2
import json
import os
import tempfile
import unittest
from unittest import mock

import core.cut_boundary as cut_boundary
from core.pipeline.pipeline_helpers import PipelineHelpersMixin


class _DummyUi:
    def __init__(self, project_path: str):
        self._current_project_path = project_path


class _DummyBackend(PipelineHelpersMixin):
    def __init__(self, project_path: str):
        self.ui = _DummyUi(project_path)
        self._cut_boundary_provisional_rows = []


class PipelineCutBoundaryCacheTests(unittest.TestCase):
    def _write_project(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "analysis": {
                        "cut_boundaries": [{"timeline_sec": 10.0, "time": 10.0}],
                        "cut_boundary_provisional_boundaries": [{"timeline_sec": 9.5, "time": 9.5}],
                    }
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def test_cut_boundary_snapshot_is_shared_between_calls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "sample.project.json")
            self._write_project(project_path)
            backend = _DummyBackend(project_path)

            with mock.patch(
                "core.cut_boundary.project_cut_boundaries",
                wraps=cut_boundary.project_cut_boundaries,
            ) as cut_mock, mock.patch(
                "core.cut_boundary.project_cut_provisional_boundaries",
                wraps=cut_boundary.project_cut_provisional_boundaries,
            ) as provisional_mock:
                cuts = backend._project_cut_boundaries_for_pipeline()
                provisional = backend._project_provisional_cut_boundaries_for_pipeline()

            self.assertEqual(len(cuts), 1)
            self.assertEqual(len(provisional), 1)
            self.assertEqual(cut_mock.call_count, 1)
            self.assertEqual(provisional_mock.call_count, 1)

    def test_split_by_saved_cut_boundaries_offset_skips_pre_offset_boundaries(self):
        backend = _DummyBackend("")
        backend._cut_boundary_pipeline_cache = {
            "project_path": "",
            "mtime_ns": None,
            "provisional_signature": "[]",
            "cut_boundaries": [
                {"timeline_sec": 5.0, "time": 5.0},
                {"timeline_sec": 12.0, "time": 12.0},
            ],
            "provisional_cut_boundaries": [],
        }

        seen_boundaries = []

        def fake_split(segments, boundaries, enabled=True):
            seen_boundaries.extend(boundaries)
            return [dict(seg) for seg in segments]

        with mock.patch("core.pipeline.pipeline_helpers.load_settings", return_value={"cut_boundary_detection_enabled": True}), \
             mock.patch("core.cut_boundary.cut_boundary_enabled", return_value=True), \
             mock.patch("core.cut_boundary.split_segments_by_cut_boundaries", side_effect=fake_split):
            backend._split_by_saved_cut_boundaries(
                [{"start": 0.0, "end": 4.0, "text": "hello"}],
                offset=10.0,
                context="test",
            )

        self.assertEqual(len(seen_boundaries), 1)
        self.assertAlmostEqual(float(seen_boundaries[0]["timeline_sec"]), 2.0, places=3)


if __name__ == "__main__":
    unittest.main()
