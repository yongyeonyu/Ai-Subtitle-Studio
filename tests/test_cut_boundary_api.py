import unittest
from unittest.mock import patch

from core.cut_boundary_api import (
    CUT_BOUNDARY_ALGORITHM_ID,
    CUT_BOUNDARY_ALGORITHM_VERSION,
    CUT_BOUNDARY_API_VERSION,
    CutBoundaryAPI,
    CutBoundaryRequest,
    library_info,
    normalize_cut_boundary_rows,
)


class CutBoundaryAPITests(unittest.TestCase):
    def test_library_version_is_locked_to_0100(self):
        self.assertEqual(CUT_BOUNDARY_API_VERSION, "01.00")
        self.assertEqual(CUT_BOUNDARY_ALGORITHM_VERSION, "01.00")
        self.assertEqual(library_info()["algorithm_id"], CUT_BOUNDARY_ALGORITHM_ID)

    def test_detect_stamps_rows_and_forwards_versioned_settings(self):
        captured = {}

        def fake_detect(path, **kwargs):
            captured["path"] = path
            captured["kwargs"] = kwargs
            return [{"timeline_sec": 1.0, "time": 1.0, "timeline_frame": 30, "fps": 30.0}]

        api = CutBoundaryAPI()
        with patch("core.cut_boundary.detect_media_cut_boundaries", side_effect=fake_detect), patch(
            "core.cut_boundary.cut_boundary_scan_profile",
            return_value={"level": "medium", "positions": (1, 3, 4, 5, 7), "mask": "cross5"},
        ), patch("core.cut_boundary_backend_router.select_cut_boundary_backend") as backend_mock:
            backend_mock.return_value.backend = "native_opencv"
            backend_mock.return_value.scan_path = "/tmp/proxy.mp4"
            backend_mock.return_value.reason = "unit"
            backend_mock.return_value.use_proxy = True

            result = api.detect(
                CutBoundaryRequest(
                    media_path="/tmp/sample.mp4",
                    level="medium",
                    settings={"scan_cut_auto_threshold": 30.0},
                )
            )

        self.assertEqual(captured["path"], "/tmp/sample.mp4")
        self.assertTrue(captured["kwargs"]["settings_preloaded"])
        self.assertEqual(captured["kwargs"]["settings"]["cut_boundary_api_version"], "01.00")
        self.assertEqual(captured["kwargs"]["threshold"], 30.0)
        self.assertEqual(result.count, 1)
        self.assertEqual(result.metadata["backend"], "native_opencv")
        self.assertEqual(result.rows[0]["cut_boundary_api_version"], "01.00")
        self.assertEqual(result.rows[0]["cut_boundary_algorithm_id"], CUT_BOUNDARY_ALGORITHM_ID)

    def test_normalize_rows_uses_api_contract_metadata(self):
        rows = normalize_cut_boundary_rows(
            [{"timeline_sec": 2.0, "time": 2.0}],
            primary_fps=24.0,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timeline_frame"], 48)
        self.assertEqual(rows[0]["cut_boundary_algorithm_version"], "01.00")


if __name__ == "__main__":
    unittest.main()
