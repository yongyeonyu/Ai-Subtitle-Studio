import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.project.nle_persistence_guard import (
    NLE_LEGACY_CANONICAL_LOAD_OWNER,
    NLE_PERSISTENCE_GUARD_SCHEMA,
    NLE_PERSISTENCE_QUARANTINE_KEY,
    NLE_RUNTIME_STATE_PERSISTENCE_APPROVAL_SCHEMA,
    NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
    NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
    NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA,
    NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
    NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA,
    assert_no_unapproved_nle_persistence_fields,
    strip_unapproved_nle_persistence_fields,
)
from core.project.nle_snapshot import (
    NLE_SNAPSHOT_READBACK_PARITY_KEY,
    NLE_SNAPSHOT_READBACK_PARITY_SCHEMA,
    NLE_TOP_LEVEL_SHADOW_SCHEMA,
)
from core.project.nle_project_state import NLEProjectState, NLE_PROJECT_STATE_RUNTIME_KEY, build_project_nle_state
from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.project_format import build_storage_project_payload, hydrate_project_runtime_views
from core.project import project_io
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


def _row_signature(rows: list[dict]) -> list[tuple[str, int, int, bool]]:
    return [
        (
            str(row.get("text") or ""),
            int(row.get("start_frame", row.get("timeline_start_frame", 0)) or 0),
            int(row.get("end_frame", row.get("timeline_end_frame", 0)) or 0),
            bool(row.get("is_gap")),
        )
        for row in rows
        if isinstance(row, dict)
    ]


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

    def test_storage_builder_strips_runtime_nle_project_state_object_without_explicit_policy(self):
        project = _legacy_project()
        project[NLE_PROJECT_STATE_RUNTIME_KEY] = build_project_nle_state(project, project_path="")

        storage = build_storage_project_payload(copy.deepcopy(project))

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

    def test_owner_approved_nle_snapshot_persistence_roundtrips_with_legacy_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "approved-nle-snapshot.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
            }
            expected_rows = _row_signature(project_segments_to_editor(project, include_analysis_candidates=False))

            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            assert_no_unapproved_nle_persistence_fields(storage, surface="approved_snapshot_storage")
            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            loaded_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
            parity = loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY)
            loaded_rows = _row_signature(project_segments_to_editor(loaded, include_analysis_candidates=False))
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))

        self.assertIn("nle_snapshot", storage)
        self.assertNotIn("nle", storage)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage)
        self.assertEqual(storage["nle_snapshot"]["schema"], "ai_subtitle_studio.nle_snapshot.v1")
        self.assertEqual(
            storage["nle_snapshot"]["persistence"]["schema"],
            NLE_SNAPSHOT_PERSISTENCE_APPROVAL_SCHEMA,
        )
        self.assertEqual(
            storage["nle_snapshot"]["persistence"]["approval"],
            NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        )
        self.assertEqual(storage["nle_snapshot"]["metadata"]["caption_count"], 1)
        self.assertEqual(parity["schema"], NLE_SNAPSHOT_READBACK_PARITY_SCHEMA)
        self.assertTrue(parity["checked"])
        self.assertTrue(parity["stable"])
        self.assertEqual(parity["mismatch_count"], 0)
        self.assertEqual(parity["persisted_caption_count"], 1)
        self.assertEqual(parity["fresh_caption_count"], 1)
        self.assertEqual(loaded_rows, expected_rows)
        self.assertIsInstance(loaded_state, NLEProjectState)
        self.assertIn("nle_snapshot", storage_after)
        self.assertEqual(
            storage_after["nle_snapshot"]["persistence"]["approval"],
            NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        )
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after)
        self.assertNotIn(NLE_SNAPSHOT_READBACK_PARITY_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after)

    def test_owner_approved_top_level_nle_shadow_roundtrips_without_load_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "approved-top-level-nle-shadow.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "persist_top_level_nle": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
            }
            expected_rows = _row_signature(project_segments_to_editor(project, include_analysis_candidates=False))

            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            assert_no_unapproved_nle_persistence_fields(storage, surface="approved_top_level_nle_storage")
            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            loaded_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
            parity = loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY)
            loaded_rows = _row_signature(project_segments_to_editor(loaded, include_analysis_candidates=False))
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))

        nle_payload = storage["nle"]
        self.assertIn("nle_snapshot", storage)
        self.assertEqual(nle_payload["schema"], NLE_TOP_LEVEL_SHADOW_SCHEMA)
        self.assertEqual(nle_payload["role"], "shadow_metadata")
        self.assertEqual(nle_payload["canonical_load_owner"], NLE_LEGACY_CANONICAL_LOAD_OWNER)
        self.assertFalse(nle_payload["runtime_project_state_persisted"])
        self.assertEqual(
            nle_payload["persistence"]["schema"],
            NLE_TOP_LEVEL_PERSISTENCE_APPROVAL_SCHEMA,
        )
        self.assertEqual(
            nle_payload["persistence"]["approval"],
            NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        )
        self.assertEqual(nle_payload["metadata"]["caption_count"], 1)
        self.assertEqual(nle_payload["metadata"]["gap_count"], 1)
        self.assertEqual(nle_payload["sequences"][0]["captions"][0]["text"], "first")
        self.assertEqual(nle_payload["sequences"][0]["gaps"][0]["gap_id"], "gap_1")
        self.assertEqual(loaded_rows, expected_rows)
        self.assertIsInstance(loaded_state, NLEProjectState)
        self.assertTrue(parity["checked"])
        self.assertTrue(parity["stable"])
        self.assertIn("nle", storage_after)
        self.assertIn("nle_snapshot", storage_after)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after)
        self.assertNotIn(NLE_SNAPSHOT_READBACK_PARITY_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after)
        storage_without_snapshot = copy.deepcopy(storage)
        storage_without_snapshot.pop("nle_snapshot", None)
        with self.assertRaisesRegex(ValueError, "unapproved_nle_persistence_fields:missing_snapshot_companion:nle"):
            assert_no_unapproved_nle_persistence_fields(
                storage_without_snapshot,
                surface="missing_snapshot_companion",
            )
        report = strip_unapproved_nle_persistence_fields(
            storage_without_snapshot,
            source="missing_snapshot_companion",
        )
        self.assertEqual(report["stripped_keys"], ["nle"])
        self.assertNotIn("nle", storage_without_snapshot)
        self.assertIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_without_snapshot)

    def test_owner_approved_top_level_nle_canonical_load_opt_in_uses_top_level_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "canonical-top-level-nle.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "persist_top_level_nle": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
                "canonical_load_owner": NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
                "canonical_load_owner_change_allowed": True,
            }
            storage = build_storage_project_payload(copy.deepcopy(project))
            storage["nle"]["sequences"][0]["captions"][0]["text"] = "nle canonical first"
            storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = "nle canonical first"
            project_path.write_bytes(project_io._pack_project_payload(storage))

            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))
            reloaded = read_project_file(str(project_path))
            reloaded_rows = project_segments_to_editor(reloaded, include_analysis_candidates=False)

        nle_payload = storage["nle"]
        self.assertEqual(nle_payload["role"], "canonical_load_owner")
        self.assertEqual(nle_payload["canonical_load_owner"], NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER)
        self.assertTrue(nle_payload["persistence"]["canonical_load_owner_change_allowed"])
        self.assertFalse(nle_payload["persistence"]["legacy_editor_state_remains_canonical"])
        self.assertTrue(nle_payload["persistence"]["legacy_editor_state_preserved_for_rollback"])
        self.assertEqual(project_segments_to_editor(project, include_analysis_candidates=False)[0]["text"], "first")
        self.assertEqual(loaded_rows[0]["text"], "nle canonical first")
        self.assertEqual(reloaded_rows[0]["text"], "nle canonical first")
        self.assertEqual(storage_after["nle"]["role"], "canonical_load_owner")
        self.assertEqual(storage_after["nle"]["canonical_load_owner"], NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER)
        self.assertEqual(storage_after["nle"]["sequences"][0]["captions"][0]["text"], "nle canonical first")
        self.assertEqual(
            storage_after["editor_state"]["rendering"]["subtitle_canvas"]["segments"][0]["text"],
            "first",
        )
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after)
        self.assertNotIn(NLE_SNAPSHOT_READBACK_PARITY_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after)

    def test_empty_top_level_nle_canonical_opt_in_falls_back_to_legacy_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "empty-canonical-top-level-nle.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "persist_top_level_nle": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
                "canonical_load_owner": NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
                "canonical_load_owner_change_allowed": True,
            }
            storage = build_storage_project_payload(copy.deepcopy(project))
            storage["nle"]["sequences"][0]["captions"] = []
            storage["nle"]["sequences"][0]["gaps"] = []
            project_path.write_bytes(project_io._pack_project_payload(storage))

            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)

        self.assertEqual(loaded_rows[0]["text"], "first")
        self.assertFalse(any(row.get("_nle_canonical_load_source") for row in loaded_rows))

    def test_top_level_nle_canonical_opt_in_rejects_snapshot_companion_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "drifted-canonical-top-level-nle.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "persist_top_level_nle": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
                "canonical_load_owner": NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
                "canonical_load_owner_change_allowed": True,
            }
            storage = build_storage_project_payload(copy.deepcopy(project))
            storage["nle"]["sequences"][0]["captions"][0]["text"] = "drifted top-level nle text"
            project_path.write_bytes(project_io._pack_project_payload(storage))

            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)

        self.assertEqual(loaded_rows[0]["text"], "first")
        self.assertFalse(any(row.get("_nle_canonical_load_source") for row in loaded_rows))

    def test_top_level_nle_canonical_opt_in_rejects_direct_forged_payload_without_approvals(self):
        project = _legacy_project()
        project["nle_persistence"] = {
            "persist_snapshot": True,
            "persist_top_level_nle": True,
            "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
            "canonical_load_owner": NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
            "canonical_load_owner_change_allowed": True,
        }
        storage = build_storage_project_payload(copy.deepcopy(project))
        storage["nle"]["sequences"][0]["captions"][0]["text"] = "forged canonical first"
        storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = "forged canonical first"
        storage["nle"].pop("persistence", None)
        storage["nle_snapshot"].pop("persistence", None)

        rows = project_segments_to_editor(storage, include_analysis_candidates=False)

        self.assertEqual(rows[0]["text"], "first")
        self.assertFalse(any(row.get("_nle_canonical_load_source") for row in rows))

    def test_owner_approved_nle_snapshot_canonical_load_opt_in_uses_snapshot_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "canonical-nle-snapshot.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
                "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
                "canonical_load_owner_change_allowed": True,
                "nle_snapshot_canonical_load_source_allowed": True,
                "legacy_editor_state_remains_canonical": False,
                "legacy_editor_state_preserved_for_rollback": True,
            }
            storage = build_storage_project_payload(copy.deepcopy(project))
            storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = "snapshot canonical first"
            project_path.write_bytes(project_io._pack_project_payload(storage))

            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))
            reloaded = read_project_file(str(project_path))
            reloaded_rows = project_segments_to_editor(reloaded, include_analysis_candidates=False)

        snapshot_payload = storage["nle_snapshot"]
        self.assertEqual(snapshot_payload["persistence"]["canonical_load_owner"], NLE_SNAPSHOT_CANONICAL_LOAD_OWNER)
        self.assertTrue(snapshot_payload["persistence"]["canonical_load_owner_change_allowed"])
        self.assertTrue(snapshot_payload["persistence"]["nle_snapshot_canonical_load_source_allowed"])
        self.assertFalse(snapshot_payload["persistence"]["legacy_editor_state_remains_canonical"])
        self.assertTrue(snapshot_payload["persistence"]["legacy_editor_state_preserved_for_rollback"])
        self.assertEqual(project_segments_to_editor(project, include_analysis_candidates=False)[0]["text"], "first")
        self.assertEqual(loaded_rows[0]["text"], "snapshot canonical first")
        self.assertEqual(reloaded_rows[0]["text"], "snapshot canonical first")
        self.assertEqual(_row_signature(loaded_rows), _row_signature(reloaded_rows))
        self.assertNotIn("nle", storage_after)
        self.assertEqual(
            storage_after["nle_snapshot"]["sequences"][0]["captions"][0]["text"],
            "snapshot canonical first",
        )
        self.assertEqual(
            storage_after["editor_state"]["rendering"]["subtitle_canvas"]["segments"][0]["text"],
            "first",
        )
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after)
        self.assertNotIn(NLE_SNAPSHOT_READBACK_PARITY_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after)

    def test_owner_approved_runtime_nle_project_state_persistence_roundtrips_as_opt_in_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "runtime-state-persistence-opt-in.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
                "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
                "canonical_load_owner_change_allowed": True,
                "nle_snapshot_canonical_load_source_allowed": True,
                "legacy_editor_state_remains_canonical": False,
                "legacy_editor_state_preserved_for_rollback": True,
                "persist_runtime_project_state": True,
                "runtime_project_state_persistence_allowed": True,
                "default_project_authority_unchanged": True,
                "legacy_disk_shape_replacement_allowed": False,
                "final_cutover_ready": False,
            }
            storage = build_storage_project_payload(copy.deepcopy(project))
            expected_text = "runtime persisted snapshot first"
            storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = expected_text
            storage[NLE_PROJECT_STATE_RUNTIME_KEY]["editor_rows"][0]["text"] = expected_text
            storage[NLE_PROJECT_STATE_RUNTIME_KEY]["snapshot"]["sequences"][0]["captions"][0]["text"] = expected_text
            project_path.write_bytes(project_io._pack_project_payload(storage))

            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            loaded_state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
            loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))
            cached = read_project_file(str(project_path))
            cached_state = cached.get(NLE_PROJECT_STATE_RUNTIME_KEY)
            write_project_file(str(project_path), cached)
            storage_after_cache_hit = read_project_storage_payload(str(project_path))

        persisted = storage_after[NLE_PROJECT_STATE_RUNTIME_KEY]
        self.assertIn("nle_snapshot", storage)
        self.assertIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)
        self.assertEqual(storage[NLE_PROJECT_STATE_RUNTIME_KEY]["schema"], "ai_subtitle_studio.nle_project_state.v1")
        self.assertEqual(
            storage[NLE_PROJECT_STATE_RUNTIME_KEY]["persistence"]["schema"],
            NLE_RUNTIME_STATE_PERSISTENCE_APPROVAL_SCHEMA,
        )
        self.assertIsInstance(loaded_state, NLEProjectState)
        self.assertTrue(loaded_state.metadata["persisted_runtime_state_loaded"])
        self.assertEqual(loaded_rows[0]["text"], expected_text)
        self.assertEqual(loaded_state.editor_rows()[0]["text"], expected_text)
        self.assertEqual(persisted["editor_rows"][0]["text"], expected_text)
        self.assertEqual(
            storage_after["editor_state"]["rendering"]["subtitle_canvas"]["segments"][0]["text"],
            "first",
        )
        self.assertEqual(storage_after["nle_persistence"]["persist_runtime_project_state"], True)
        self.assertEqual(storage_after["nle_persistence"]["runtime_project_state_persistence_allowed"], True)
        self.assertEqual(storage_after["nle_persistence"]["legacy_disk_shape_replacement_allowed"], False)
        self.assertEqual(storage_after["nle_persistence"]["final_cutover_ready"], False)
        self.assertNotIn("nle", storage_after)
        self.assertNotIn(NLE_SNAPSHOT_READBACK_PARITY_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after)
        self.assertIsInstance(cached_state, NLEProjectState)
        self.assertIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after_cache_hit)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after_cache_hit)

    def test_snapshot_canonical_opt_in_strips_unapproved_runtime_state_dict_on_resave(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "canonical-snapshot-forged-runtime-state.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
                "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
                "canonical_load_owner_change_allowed": True,
                "nle_snapshot_canonical_load_source_allowed": True,
                "legacy_editor_state_remains_canonical": False,
                "legacy_editor_state_preserved_for_rollback": True,
            }
            storage = build_storage_project_payload(copy.deepcopy(project))
            storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = "snapshot canonical first"
            storage[NLE_PROJECT_STATE_RUNTIME_KEY] = {"schema": "ai_subtitle_studio.nle_project_state.v1"}
            project_path.write_bytes(project_io._pack_project_payload(storage))

            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            loaded_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))

        self.assertEqual(loaded_rows[0]["text"], "snapshot canonical first")
        self.assertIsInstance(loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY), NLEProjectState)
        self.assertIn(NLE_PERSISTENCE_QUARANTINE_KEY, loaded)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after)

    def test_compatibility_only_nle_snapshot_does_not_become_canonical_load_source(self):
        project = _legacy_project()
        project["nle_persistence"] = {
            "persist_snapshot": True,
            "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        }
        storage = build_storage_project_payload(copy.deepcopy(project))
        storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = "compatibility snapshot first"

        rows = project_segments_to_editor(storage, include_analysis_candidates=False)

        self.assertEqual(rows[0]["text"], "first")
        self.assertFalse(any(row.get("_nle_canonical_load_source") for row in rows))

    def test_nle_snapshot_canonical_opt_in_rejects_direct_forged_payload_without_approval(self):
        project = _legacy_project()
        project["nle_persistence"] = {
            "persist_snapshot": True,
            "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
            "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
            "canonical_load_owner_change_allowed": True,
            "nle_snapshot_canonical_load_source_allowed": True,
            "legacy_editor_state_remains_canonical": False,
            "legacy_editor_state_preserved_for_rollback": True,
        }
        storage = build_storage_project_payload(copy.deepcopy(project))
        storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = "forged snapshot first"
        storage["nle_snapshot"].pop("persistence", None)

        rows = project_segments_to_editor(storage, include_analysis_candidates=False)

        self.assertEqual(rows[0]["text"], "first")
        self.assertFalse(any(row.get("_nle_canonical_load_source") for row in rows))

    def test_empty_nle_snapshot_canonical_opt_in_falls_back_to_legacy_rows(self):
        project = _legacy_project()
        project["nle_persistence"] = {
            "persist_snapshot": True,
            "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
            "canonical_load_owner": NLE_SNAPSHOT_CANONICAL_LOAD_OWNER,
            "canonical_load_owner_change_allowed": True,
            "nle_snapshot_canonical_load_source_allowed": True,
            "legacy_editor_state_remains_canonical": False,
            "legacy_editor_state_preserved_for_rollback": True,
        }
        storage = build_storage_project_payload(copy.deepcopy(project))
        storage["nle_snapshot"]["sequences"][0]["captions"] = []
        storage["nle_snapshot"]["sequences"][0]["gaps"] = []

        rows = project_segments_to_editor(storage, include_analysis_candidates=False)

        self.assertEqual(rows[0]["text"], "first")
        self.assertFalse(any(row.get("_nle_canonical_load_source") for row in rows))

    def test_ambiguous_dual_canonical_owners_fall_back_to_legacy_rows(self):
        project = _legacy_project()
        project["nle_persistence"] = {
            "persist_snapshot": True,
            "persist_top_level_nle": True,
            "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
            "canonical_load_owner": NLE_TOP_LEVEL_CANONICAL_LOAD_OWNER,
            "canonical_load_owner_change_allowed": True,
            "nle_snapshot_canonical_load_source_allowed": True,
            "legacy_editor_state_remains_canonical": False,
            "legacy_editor_state_preserved_for_rollback": True,
        }
        storage = build_storage_project_payload(copy.deepcopy(project))
        storage["nle"]["sequences"][0]["captions"][0]["text"] = "dual canonical first"
        storage["nle_snapshot"]["sequences"][0]["captions"][0]["text"] = "dual canonical first"
        storage["nle_snapshot"]["persistence"]["canonical_load_owner"] = NLE_SNAPSHOT_CANONICAL_LOAD_OWNER
        storage["nle_snapshot"]["persistence"]["canonical_load_owner_change_allowed"] = True
        storage["nle_snapshot"]["persistence"]["nle_snapshot_canonical_load_source_allowed"] = True
        storage["nle_snapshot"]["persistence"]["legacy_editor_state_remains_canonical"] = False
        storage["nle_snapshot"]["persistence"]["legacy_editor_state_preserved_for_rollback"] = True
        storage["nle_snapshot"]["metadata"]["read_only"] = False
        storage["nle_snapshot"]["metadata"]["owner_approved_canonical_load_opt_in"] = True

        rows = project_segments_to_editor(storage, include_analysis_candidates=False)

        self.assertEqual(rows[0]["text"], "first")
        self.assertFalse(any(row.get("_nle_canonical_load_source") for row in rows))

    def test_top_level_nle_shadow_requires_snapshot_persistence_gate(self):
        project = _legacy_project()
        project["nle_persistence"] = {
            "persist_top_level_nle": True,
            "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
        }

        storage = build_storage_project_payload(copy.deepcopy(project))

        self.assertNotIn("nle", storage)
        self.assertNotIn("nle_snapshot", storage)

    def test_corrupted_approved_nle_snapshot_records_runtime_readback_drift_without_persisting_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "corrupted-approved-nle-snapshot.aissproj"
            project = _legacy_project()
            project["nle_persistence"] = {
                "persist_snapshot": True,
                "approval": NLE_SNAPSHOT_PERSISTENCE_APPROVAL_ID,
            }

            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            storage["nle_snapshot"]["sequences"][0]["captions"][0]["sequence_start"] = 3.5
            project_path.write_text(json.dumps(storage), encoding="utf-8")
            clear_project_file_cache(str(project_path))

            loaded = read_project_file(str(project_path))
            parity = loaded.get(NLE_SNAPSHOT_READBACK_PARITY_KEY)
            loaded_rows = _row_signature(project_segments_to_editor(loaded, include_analysis_candidates=False))
            expected_rows = _row_signature(project_segments_to_editor(project, include_analysis_candidates=False))
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))

        self.assertEqual(loaded_rows, expected_rows)
        self.assertEqual(parity["schema"], NLE_SNAPSHOT_READBACK_PARITY_SCHEMA)
        self.assertTrue(parity["checked"])
        self.assertFalse(parity["stable"])
        self.assertGreater(parity["mismatch_count"], 0)
        self.assertTrue(any("sequence_start" in item for item in parity["mismatches"]))
        self.assertIn("nle_snapshot", storage_after)
        self.assertNotIn(NLE_SNAPSHOT_READBACK_PARITY_KEY, storage_after)
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after)
        self.assertNotIn(NLE_PERSISTENCE_QUARANTINE_KEY, storage_after)


if __name__ == "__main__":
    unittest.main()
