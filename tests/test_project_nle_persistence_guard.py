import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.project.nle_persistence_guard import (
    NLE_PERSISTENCE_GUARD_SCHEMA,
    NLE_PERSISTENCE_QUARANTINE_KEY,
    assert_no_unapproved_nle_persistence_fields,
    strip_unapproved_nle_persistence_fields,
)
from core.project.nle_project_state import NLEProjectState, NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.project_context import build_editor_state
from core.project.project_format import build_storage_project_payload, hydrate_project_runtime_views
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)


def _legacy_project() -> dict:
    return {
        "project_name": "nle_persistence_guard",
        "mode": "single",
        "video": {"duration_sec": 4.0, "primary_fps": 30.0},
        "timeline": {
            "total_duration": 4.0,
            "timebase": {"primary_fps": 30.0},
            "tracks": [{"clips": []}],
        },
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
            ],
            primary_fps=30.0,
        ),
    }


class NLEPersistenceGuardTests(unittest.TestCase):
    def test_guard_strips_unapproved_nle_payloads_and_records_metadata_quarantine(self):
        project = _legacy_project()
        project["nle"] = {"future": True, "tracks": []}
        project["nle_snapshot"] = {"schema": "future"}
        project[NLE_PROJECT_STATE_RUNTIME_KEY] = {"schema": "persisted_future_state"}

        report = strip_unapproved_nle_persistence_fields(project, source="unit")

        self.assertEqual(report["schema"], NLE_PERSISTENCE_GUARD_SCHEMA)
        self.assertEqual(report["source"], "unit")
        self.assertEqual(
            report["stripped_keys"],
            ["nle", "nle_snapshot", NLE_PROJECT_STATE_RUNTIME_KEY],
        )
        self.assertNotIn("nle", project)
        self.assertNotIn("nle_snapshot", project)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, project)
        self.assertEqual(project[NLE_PERSISTENCE_QUARANTINE_KEY], report)
        assert_no_unapproved_nle_persistence_fields(project, surface="unit")

    def test_runtime_nle_project_state_is_allowed_but_never_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "runtime-state.aissproj"
            project = _legacy_project()
            write_project_file(str(project_path), copy.deepcopy(project))
            clear_project_file_cache(str(project_path))

            loaded = read_project_file(str(project_path))
            state = loaded[NLE_PROJECT_STATE_RUNTIME_KEY]
            report = strip_unapproved_nle_persistence_fields(loaded, source="runtime")
            write_project_file(str(project_path), loaded)
            storage = read_project_storage_payload(str(project_path))

        self.assertIsInstance(state, NLEProjectState)
        self.assertEqual(report, {})
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage)
        self.assertNotIn("nle", storage)
        self.assertNotIn("nle_snapshot", storage)

    def test_reading_raw_project_quarantines_unapproved_nle_payloads_then_resaves_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "future-nle.aissproj"
            raw_project = _legacy_project()
            raw_project["nle"] = {"future_doc": {"tracks": []}}
            raw_project["nle_snapshot"] = {"schema": "future_snapshot"}
            raw_project[NLE_PROJECT_STATE_RUNTIME_KEY] = {"schema": "persisted_future_state"}
            project_path.write_text(json.dumps(raw_project), encoding="utf-8")

            loaded = read_project_file(str(project_path))
            quarantine = loaded.get(NLE_PERSISTENCE_QUARANTINE_KEY)
            state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            reopened = read_project_file(str(project_path))

        self.assertIsInstance(quarantine, dict)
        self.assertEqual(
            quarantine["stripped_keys"],
            ["nle", "nle_snapshot", NLE_PROJECT_STATE_RUNTIME_KEY],
        )
        self.assertIsInstance(state, NLEProjectState)
        self.assertNotIn("nle", loaded)
        self.assertNotIn("nle_snapshot", loaded)
        self.assertNotIn("nle", storage_after)
        self.assertNotIn("nle_snapshot", storage_after)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, reopened)

    def test_storage_builders_strip_unapproved_nle_payloads_without_persisting_quarantine(self):
        project = _legacy_project()
        project["nle"] = {"future": True}
        project["nle_snapshot"] = {"future": True}
        project[NLE_PROJECT_STATE_RUNTIME_KEY] = {"future": True}

        hydrated = hydrate_project_runtime_views(copy.deepcopy(project))
        storage = build_storage_project_payload(copy.deepcopy(project))

        self.assertIn(NLE_PERSISTENCE_QUARANTINE_KEY, hydrated)
        self.assertNotIn("nle", hydrated)
        self.assertNotIn("nle_snapshot", hydrated)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, hydrated)
        self.assertNotIn("nle", storage)
        self.assertNotIn("nle_snapshot", storage)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage)


if __name__ == "__main__":
    unittest.main()
