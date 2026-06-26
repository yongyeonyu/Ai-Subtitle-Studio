import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.project.nle_snapshot import (
    build_project_nle_snapshot,
    markers_from_roughcut_sidecar_payload,
    markers_from_stitched_cut_boundaries,
)
from core.project.nle_project_state import (
    NLEProjectState,
    NLE_PROJECT_STATE_RUNTIME_KEY,
    NLE_PROJECT_STATE_SCHEMA,
    assert_nle_editor_rows_consistent,
    build_project_nle_state,
    project_segments_from_nle_state,
    sync_project_nle_state_from_editor_rows,
)
from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)
from core.project.project_manager import save_project
from ui.editor.editor_project_open_native import load_stitched_cut_boundaries_for_srt_open


class ProjectNleSnapshotTests(unittest.TestCase):
    def test_snapshot_projects_existing_project_state_without_mutating_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "clip.mp4"
            media_path.write_bytes(b"media")
            project = {
                "project_name": "nle_snapshot_case",
                "mode": "single",
                "timeline": {
                    "total_duration": 8.0,
                    "timebase": {"primary_fps": 30.0},
                    "tracks": [
                        {
                            "clips": [
                                {
                                    "id": "clip_main",
                                    "source_path": str(media_path),
                                    "type": "video",
                                    "source_duration": 8.0,
                                    "timeline_start": 0.0,
                                    "timeline_end": 8.0,
                                    "fps": 30.0,
                                    "width": 1920,
                                    "height": 1080,
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
                        {"start": 0.0, "end": 2.0, "text": "첫 자막", "speaker": "00"},
                        {"start": 4.0, "end": 5.5, "text": "둘째 자막", "speaker": "01"},
                    ],
                    primary_fps=30.0,
                ),
                "analysis": {
                    "cut_boundaries": [
                        {
                            "time": 4.0,
                            "source": "visual",
                            "status": "confirmed",
                        }
                    ]
                },
                "roughcut_state": {
                    "selected_candidate_id": "roughcut_a",
                    "candidates": [
                        {
                            "candidate_id": "roughcut_a",
                            "name": "후보 A",
                            "outputs": {
                                "edl": {
                                    "duration": 6.0,
                                    "segments": [
                                        {
                                            "segment_id": "seg_a",
                                            "source_path": str(media_path),
                                            "source_start": 0.0,
                                            "source_end": 3.0,
                                            "output_start": 0.0,
                                            "output_end": 3.0,
                                            "timeline_start": 0.0,
                                            "timeline_end": 3.0,
                                        },
                                        {
                                            "segment_id": "seg_b",
                                            "source_path": str(media_path),
                                            "source_start": 5.0,
                                            "source_end": 8.0,
                                            "output_start": 3.0,
                                            "output_end": 6.0,
                                            "timeline_start": 5.0,
                                            "timeline_end": 8.0,
                                        },
                                    ],
                                    "stitched_cut_boundaries": [
                                        {
                                            "time": 3.0,
                                            "timeline_sec": 3.0,
                                            "source": "roughcut_concat_join",
                                            "segment_before_id": "seg_a",
                                            "segment_after_id": "seg_b",
                                            "source_before_path": str(media_path),
                                            "source_after_path": str(media_path),
                                            "output_before_end": 3.0,
                                            "output_after_start": 3.0,
                                        }
                                    ],
                                },
                                "render_plan": {
                                    "output_path": str(Path(tmp) / "roughcut.mov"),
                                    "render_mode": "sync_safe",
                                    "segment_manifest": [
                                        {
                                            "segment_id": "seg_a",
                                            "source_path": str(media_path),
                                            "source_start": 0.0,
                                            "source_end": 3.0,
                                            "output_end": 3.0,
                                        }
                                    ],
                                },
                            },
                        }
                    ],
                },
            }
            before = copy.deepcopy(project)

            snapshot = build_project_nle_snapshot(project, project_path=str(Path(tmp) / "case.aissproj"))

        self.assertEqual(project, before)
        self.assertTrue(snapshot.metadata["read_only"])
        self.assertEqual(snapshot.source_project_path.endswith("case.aissproj"), True)
        self.assertEqual(len(snapshot.assets), 1)
        self.assertFalse(snapshot.assets[0].missing)

        sequence = snapshot.sequences[0]
        self.assertEqual(sequence.duration, 8.0)
        self.assertEqual(len(sequence.clips), 1)
        self.assertEqual(sequence.clips[0].sequence_start, 0.0)
        self.assertEqual(sequence.clips[0].sequence_end, 8.0)
        self.assertEqual([caption.text for caption in sequence.captions], ["첫 자막", "둘째 자막"])
        self.assertEqual([(caption.sequence_start, caption.sequence_end) for caption in sequence.captions], [(0.0, 2.0), (4.0, 5.5)])

        cut_markers = [marker for marker in sequence.markers if marker.kind == "cut_boundary"]
        exact_markers = [marker for marker in sequence.markers if marker.kind == "roughcut_exact_join"]
        self.assertEqual([marker.time for marker in cut_markers], [4.0])
        self.assertEqual(len(exact_markers), 1)
        self.assertEqual(exact_markers[0].time_domain, "output")
        self.assertEqual(exact_markers[0].metadata["exact_join"]["segment_before_id"], "seg_a")
        self.assertEqual(exact_markers[0].metadata["exact_join"]["segment_after_id"], "seg_b")

        self.assertEqual(len(snapshot.render_plans), 1)
        self.assertEqual(snapshot.render_plans[0].render_mode, "sync_safe")
        self.assertEqual(snapshot.render_plans[0].output_duration, 6.0)

    def test_legacy_project_without_timeline_still_projects_media_and_subtitles(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "legacy.mp4"
            media_path.write_bytes(b"media")
            project = {
                "project_name": "legacy",
                "video": {
                    "duration_sec": 5.0,
                    "primary_fps": 24.0,
                    "timebase": {"primary_fps": 24.0},
                },
                "media": [{"path": str(media_path), "duration": 5.0, "order": 0}],
                "subtitles": {
                    "segments": [
                        {"start": 0.5, "end": 1.5, "text": "legacy one"},
                        {"start": 3.0, "end": 4.0, "text": "legacy two"},
                    ]
                },
            }

            snapshot = build_project_nle_snapshot(project)

        sequence = snapshot.sequences[0]
        self.assertEqual(len(snapshot.assets), 1)
        self.assertEqual(len(sequence.clips), 1)
        self.assertEqual(sequence.clips[0].sequence_end, 5.0)
        self.assertEqual(sequence.fps, 24.0)
        self.assertEqual([caption.text for caption in sequence.captions], ["legacy one", "legacy two"])
        self.assertEqual(sequence.duration, 5.0)

    def test_stitched_cut_boundaries_are_output_markers_not_clip_spans(self):
        markers = markers_from_stitched_cut_boundaries(
            [
                {
                    "time": 2.5,
                    "timeline_sec": 2.5,
                    "source": "roughcut_concat_join",
                    "segment_before_id": "before",
                    "segment_after_id": "after",
                    "source_before_path": "a.mov",
                    "source_after_path": "b.mov",
                    "output_before_end": 2.5,
                    "output_after_start": 2.5,
                    "timeline_before_end": 8.0,
                    "timeline_after_start": 11.0,
                }
            ]
        )

        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0].kind, "roughcut_exact_join")
        self.assertEqual(markers[0].time_domain, "output")
        self.assertEqual(markers[0].time, 2.5)
        self.assertNotIn("boundary_span", markers[0].metadata)
        self.assertEqual(markers[0].metadata["exact_join"]["timeline_before_end"], 8.0)
        self.assertEqual(markers[0].metadata["exact_join"]["timeline_after_start"], 11.0)

    def test_roughcut_sidecar_payload_shapes_project_to_exact_join_markers(self):
        row = {
            "timeline_sec": 4.0,
            "time": 4.0,
            "source": "roughcut_concat_join",
            "segment_before_id": "chapter_0001",
            "segment_after_id": "chapter_0002",
            "timeline_before_end": 4.0,
            "timeline_after_start": 5.0,
            "output_before_end": 4.0,
            "output_after_start": 4.0,
        }
        payloads = [
            {"stitched_cut_boundaries": [row]},
            {"edl": {"stitched_cut_boundaries": [row]}},
            {"render_plan": {"stitched_cut_boundaries": [row]}},
            {"outputs": {"render_plan": {"stitched_cut_boundaries": [row]}}},
        ]

        for payload in payloads:
            with self.subTest(payload=tuple(payload.keys())):
                markers = markers_from_roughcut_sidecar_payload(payload, primary_fps=30.0)
                self.assertEqual(len(markers), 1)
                self.assertEqual(markers[0].kind, "roughcut_exact_join")
                self.assertEqual(markers[0].time_domain, "output")
                self.assertEqual(markers[0].time, 4.0)
                self.assertEqual(markers[0].metadata["exact_join"]["segment_before_id"], "chapter_0001")
                self.assertEqual(markers[0].metadata["exact_join"]["segment_after_id"], "chapter_0002")

    def test_direct_srt_sidecar_rows_project_to_nle_exact_join_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt_path = root / "clip_roughcut.srt"
            media_path = root / "clip.mov"
            sidecar_path = root / "clip_roughcut_render_plan.json"
            srt_path.write_text("1\n00:00:01,000 --> 00:00:02,000\n외부 SRT\n\n", encoding="utf-8")
            media_path.write_bytes(b"video")
            sidecar_path.write_text(
                json.dumps(
                    {
                        "render_plan": {
                            "stitched_cut_boundaries": [
                                {
                                    "timeline_sec": 4.0,
                                    "time": 4.0,
                                    "source": "roughcut_concat_join",
                                    "segment_before_id": "chapter_0001",
                                    "segment_after_id": "chapter_0002",
                                    "timeline_before_end": 4.0,
                                    "timeline_after_start": 5.0,
                                }
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            rows, loaded_sidecar_path = load_stitched_cut_boundaries_for_srt_open(str(srt_path), str(media_path))
            markers = markers_from_stitched_cut_boundaries(rows)

        self.assertEqual(Path(loaded_sidecar_path).name, "clip_roughcut_render_plan.json")
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0].kind, "roughcut_exact_join")
        self.assertEqual(markers[0].time_domain, "output")
        self.assertEqual(markers[0].time, 4.0)
        self.assertEqual(markers[0].metadata["exact_join"]["segment_before_id"], "chapter_0001")
        self.assertEqual(markers[0].metadata["exact_join"]["segment_after_id"], "chapter_0002")

    def test_top_level_sidecar_rows_win_over_nested_rows_like_existing_reader(self):
        payload = {
            "stitched_cut_boundaries": [
                {
                    "timeline_sec": 3.0,
                    "source": "roughcut_concat_join",
                    "segment_before_id": "top_before",
                    "segment_after_id": "top_after",
                }
            ],
            "render_plan": {
                "stitched_cut_boundaries": [
                    {
                        "timeline_sec": 7.0,
                        "source": "roughcut_concat_join",
                        "segment_before_id": "nested_before",
                        "segment_after_id": "nested_after",
                    }
                ]
            },
            "outputs": {
                "render_plan": {
                    "stitched_cut_boundaries": [
                        {
                            "timeline_sec": 9.0,
                            "source": "roughcut_concat_join",
                            "segment_before_id": "outputs_before",
                            "segment_after_id": "outputs_after",
                        }
                    ]
                }
            },
        }

        markers = markers_from_roughcut_sidecar_payload(payload)

        self.assertEqual([marker.time for marker in markers], [3.0])
        self.assertEqual(markers[0].metadata["exact_join"]["segment_before_id"], "top_before")

    def test_selected_candidate_outputs_do_not_duplicate_exact_join_markers(self):
        row = {
            "timeline_sec": 4.0,
            "source": "roughcut_concat_join",
            "segment_before_id": "chapter_0001",
            "segment_after_id": "chapter_0002",
        }
        project = {
            "project_name": "roughcut_duplicate_guard",
            "video": {"duration_sec": 8.0, "primary_fps": 30.0},
            "roughcut_state": {
                "selected_candidate_id": "roughcut_a",
                "candidates": [
                    {
                        "candidate_id": "roughcut_a",
                        "outputs": {
                            "edl": {
                                "duration": 8.0,
                                "stitched_cut_boundaries": [row],
                                "segments": [
                                    {
                                        "output_start": 0.0,
                                        "output_end": 8.0,
                                    }
                                ],
                            },
                            "render_plan": {"stitched_cut_boundaries": [row]},
                        },
                    }
                ],
            },
        }

        snapshot = build_project_nle_snapshot(project)

        exact_markers = [
            marker
            for marker in snapshot.sequences[0].markers
            if marker.kind == "roughcut_exact_join"
        ]
        self.assertEqual(len(exact_markers), 1)
        self.assertEqual(exact_markers[0].time, 4.0)

    def test_legacy_gap_rows_remain_non_destructive_while_snapshot_preserves_sequence_duration(self):
        project = {
            "project_name": "gap_integrity",
            "video": {"duration_sec": 8.0, "primary_fps": 30.0},
            "editor_state": build_editor_state(
                mode="single",
                media_files=["/tmp/source.mov"],
                segments=[
                    {"start": 0.0, "end": 2.0, "text": "before"},
                    {"start": 2.0, "end": 5.0, "text": "", "is_gap": True},
                    {"start": 5.0, "end": 8.0, "text": "after"},
                ],
                primary_fps=30.0,
            ),
        }
        before_rows = project_segments_to_editor(project)
        before = copy.deepcopy(project)

        snapshot = build_project_nle_snapshot(project)
        after_rows = project_segments_to_editor(project)

        self.assertEqual(project, before)
        self.assertEqual(before_rows, after_rows)
        self.assertTrue(any(row.get("is_gap") for row in after_rows))
        self.assertEqual(snapshot.sequences[0].duration, 8.0)
        self.assertEqual(
            [(caption.sequence_start, caption.sequence_end, caption.text) for caption in snapshot.sequences[0].captions],
            [(0.0, 2.0, "before"), (5.0, 8.0, "after")],
        )

    def test_project_file_roundtrip_does_not_persist_snapshot_fields_or_drop_asset_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_media = root / "missing_source.mov"
            proxy_path = root / "proxy.mov"
            project_path = root / "case.aissproj"
            project = {
                "project_name": "roundtrip",
                "timeline": {
                    "total_duration": 5.0,
                    "timebase": {"primary_fps": 30.0},
                    "tracks": [
                        {
                            "clips": [
                                {
                                    "id": "clip_missing",
                                    "source_path": str(missing_media),
                                    "type": "video",
                                    "source_duration": 5.0,
                                    "timeline_start": 0.0,
                                    "timeline_end": 5.0,
                                    "fps": 30.0,
                                    "proxy_path": str(proxy_path),
                                    "cache_key": "cache-001",
                                    "relink": {"last_known_path": str(missing_media)},
                                }
                            ]
                        }
                    ],
                },
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[str(missing_media)],
                    segments=[{"start": 1.0, "end": 2.0, "text": "roundtrip"}],
                    primary_fps=30.0,
                ),
            }
            before = build_project_nle_snapshot(project)

            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            after = build_project_nle_snapshot(loaded, project_path=str(project_path))

        self.assertNotIn("nle", storage)
        self.assertNotIn("nle_snapshot", storage)
        stored_clip = storage["timeline"]["tracks"][0]["clips"][0]
        self.assertEqual(stored_clip["proxy_path"], str(proxy_path))
        self.assertEqual(stored_clip["cache_key"], "cache-001")
        self.assertEqual(stored_clip["relink"]["last_known_path"], str(missing_media))
        self.assertTrue(before.assets[0].missing)
        self.assertTrue(after.assets[0].missing)
        self.assertEqual(before.assets[0].duration, 5.0)
        self.assertEqual(after.assets[0].duration, 5.0)
        self.assertEqual(after.assets[0].fps, 30.0)
        self.assertEqual(before.assets[0].metadata["proxy_path"], str(proxy_path))
        self.assertEqual(after.assets[0].metadata["proxy_path"], str(proxy_path))
        self.assertEqual(after.assets[0].metadata["cache_key"], "cache-001")
        self.assertEqual(after.assets[0].metadata["relink"]["last_known_path"], str(missing_media))
        self.assertEqual(after.sequences[0].duration, 5.0)
        self.assertEqual(
            [(caption.sequence_start, caption.sequence_end, caption.text) for caption in after.sequences[0].captions],
            [(1.0, 2.0, "roundtrip")],
        )

    def test_project_load_hydrates_runtime_nle_project_state_without_persisting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_path = root / "runtime-nle.aissproj"
            project = {
                "project_name": "runtime_nle",
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

            write_project_file(str(project_path), copy.deepcopy(project))
            storage_before = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
            projected_rows = project_segments_from_nle_state(loaded)
            write_project_file(str(project_path), loaded)
            storage_after = read_project_storage_payload(str(project_path))

        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_before)
        self.assertNotIn("nle", storage_before)
        self.assertNotIn("nle_snapshot", storage_before)
        self.assertIsInstance(state, NLEProjectState)
        self.assertEqual(state.schema, NLE_PROJECT_STATE_SCHEMA)
        self.assertEqual(state.metadata["hydrated_from"], "legacy_project_payload")
        self.assertEqual(len(state.captions), 2)
        self.assertEqual([row.get("text", "") for row in projected_rows], ["first", ""])
        self.assertTrue(projected_rows[1].get("is_gap"))
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage_after)
        self.assertNotIn("nle", storage_after)
        self.assertNotIn("nle_snapshot", storage_after)

    def test_save_project_routes_editor_rows_through_runtime_nle_state_without_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_path = root / "save-nle.aissproj"
            project = {
                "project_name": "save_nle",
                "timeline": {
                    "total_duration": 4.0,
                    "timebase": {"primary_fps": 30.0},
                    "tracks": [{"clips": []}],
                },
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=[{"id": "caption_1", "start": 0.0, "end": 1.0, "text": "before", "speaker": "00"}],
                    primary_fps=30.0,
                ),
            }
            updated_rows = [
                {
                    "id": "caption_1",
                    "start": 1.0,
                    "end": 2.0,
                    "text": "after",
                    "speaker": "01",
                    "quality_candidates": [{"candidate_id": "qc1"}],
                    "frame_range": {"source_frame_rate": 30.0, "clip_local_start": 30, "clip_local_end": 60},
                },
                {
                    "id": "gap_1",
                    "start": 2.0,
                    "end": 3.0,
                    "text": "",
                    "is_gap": True,
                },
            ]

            write_project_file(str(project_path), copy.deepcopy(project))
            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            state = sync_project_nle_state_from_editor_rows(loaded, updated_rows, project_path=str(project_path))
            projected = project_segments_from_nle_state(loaded)
            assert_nle_editor_rows_consistent(updated_rows, projected, primary_fps=30.0)

            save_project(
                str(project_path),
                segments=updated_rows,
                persist_analysis_artifacts=False,
            )
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            reopened = read_project_file(str(project_path))
            reopened_rows = project_segments_to_editor(reopened)

        self.assertEqual(state.metadata["last_editor_sync_count"], 2)
        self.assertEqual([(row["start_frame"], row["end_frame"], row.get("text", "")) for row in projected], [(30, 60, "after"), (60, 90, "")])
        self.assertEqual(projected[0]["quality_candidates"][0]["candidate_id"], "qc1")
        self.assertEqual(projected[0]["frame_range"]["source_frame_rate"], 30.0)
        self.assertTrue(projected[1]["is_gap"])
        self.assertNotIn(NLE_PROJECT_STATE_RUNTIME_KEY, storage)
        self.assertNotIn("nle", storage)
        self.assertNotIn("nle_snapshot", storage)
        self.assertEqual([(row.get("text", ""), row.get("start_frame"), row.get("end_frame")) for row in reopened_rows], [("after", 30, 60), ("", 60, 90)])
        self.assertTrue(reopened_rows[1].get("is_gap"))
        self.assertIsInstance(reopened.get(NLE_PROJECT_STATE_RUNTIME_KEY), NLEProjectState)

    def test_nle_project_state_handles_direct_srt_rows_without_media_or_sidecar(self):
        project = {
            "project_name": "direct_srt_only",
            "video": {"primary_fps": 30.0},
            "subtitles": {
                "segments": [
                    {"id": "srt_1", "start": 0.5, "end": 1.5, "text": "외부 SRT"},
                ]
            },
        }

        state = build_project_nle_state(project)
        projected = state.editor_rows()

        self.assertEqual(state.schema, NLE_PROJECT_STATE_SCHEMA)
        self.assertEqual(len(state.captions), 1)
        self.assertEqual(projected[0]["text"], "외부 SRT")
        self.assertEqual((projected[0]["start_frame"], projected[0]["end_frame"]), (15, 45))
        self.assertEqual(len(state.snapshot.assets), 0)

    def test_nle_project_state_preserves_roughcut_exact_join_marker_parity(self):
        row = {
            "timeline_sec": 4.0,
            "source": "roughcut_concat_join",
            "segment_before_id": "chapter_0001",
            "segment_after_id": "chapter_0002",
        }
        project = {
            "project_name": "roughcut_nle_state",
            "video": {"duration_sec": 8.0, "primary_fps": 30.0},
            "roughcut_state": {
                "selected_candidate_id": "roughcut_a",
                "candidates": [
                    {
                        "candidate_id": "roughcut_a",
                        "outputs": {
                            "edl": {
                                "duration": 8.0,
                                "stitched_cut_boundaries": [row],
                                "segments": [{"output_start": 0.0, "output_end": 8.0}],
                            },
                            "render_plan": {"stitched_cut_boundaries": [row]},
                        },
                    }
                ],
            },
        }

        state = build_project_nle_state(project)
        exact_markers = [
            marker
            for marker in state.snapshot.sequences[0].markers
            if marker.kind == "roughcut_exact_join"
        ]

        self.assertEqual(len(exact_markers), 1)
        self.assertEqual(exact_markers[0].time, 4.0)
        self.assertEqual(exact_markers[0].metadata["exact_join"]["segment_before_id"], "chapter_0001")
        self.assertEqual(exact_markers[0].metadata["exact_join"]["segment_after_id"], "chapter_0002")

    def test_compatibility_characterization_locks_legacy_rows_and_nle_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_path = root / "source.mov"
            proxy_path = root / "proxy.mov"
            project_path = root / "compatibility.aissproj"
            media_path.write_bytes(b"media")
            proxy_path.write_bytes(b"proxy")
            fps = 60000 / 1001
            duration_sec = 3000 / fps
            first_start_frame = 2676
            boundary_frame = 2677
            first_end_frame = 2766
            gap_end_frame = 2826
            last_end_frame = 2946
            exact_join = {
                "time": boundary_frame / fps,
                "timeline_sec": boundary_frame / fps,
                "frame": boundary_frame,
                "source": "roughcut_concat_join",
                "detector": "roughcut-edl-join-v1",
                "reason": "roughcut_concat_segment_join",
                "segment_before_id": "chapter_0001",
                "segment_after_id": "chapter_0002",
                "source_before_path": str(media_path),
                "source_after_path": str(media_path),
                "output_before_end": boundary_frame / fps,
                "output_after_start": boundary_frame / fps,
                "timeline_before_end": boundary_frame / fps,
                "timeline_after_start": first_end_frame / fps,
                "join_gap_sec": (first_end_frame - boundary_frame) / fps,
            }
            project = {
                "project_name": "compatibility_characterization",
                "mode": "single",
                "video": {"duration_sec": duration_sec, "primary_fps": fps},
                "timeline": {
                    "total_duration": duration_sec,
                    "timebase": {"primary_fps": fps},
                    "tracks": [
                        {
                            "clips": [
                                {
                                    "id": "clip_main",
                                    "source_path": str(media_path),
                                    "type": "video",
                                    "source_duration": duration_sec,
                                    "timeline_start": 0.0,
                                    "timeline_end": duration_sec,
                                    "fps": fps,
                                    "width": 1280,
                                    "height": 720,
                                    "order": 0,
                                    "proxy_path": str(proxy_path),
                                    "cache_key": "preview-cache-001",
                                    "relink": {"last_known_path": str(media_path)},
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
                            "id": "caption_first",
                            "start_frame": first_start_frame,
                            "end_frame": first_end_frame,
                            "timeline_start_frame": first_start_frame,
                            "timeline_end_frame": first_end_frame,
                            "frame_rate": fps,
                            "timeline_frame_rate": fps,
                            "text": "first subtitle",
                            "speaker": "00",
                            "words": [{"word": "first", "start": 1.0, "end": 1.2}],
                            "quality_candidates": [{"candidate_id": "qc1", "score": 0.91}],
                            "stt_ensemble_source": "STT1",
                            "subtitle_stage_confidence": {
                                "stages": {"stt": {"label": "green", "score": 91}},
                                "stage_order": ["stt"],
                            },
                            "clip_local_start_frame": first_start_frame,
                            "clip_local_end_frame": first_end_frame,
                            "source_frame_rate": fps,
                        },
                        {
                            "id": "gap_middle",
                            "start_frame": first_end_frame,
                            "end_frame": gap_end_frame,
                            "timeline_start_frame": first_end_frame,
                            "timeline_end_frame": gap_end_frame,
                            "frame_rate": fps,
                            "timeline_frame_rate": fps,
                            "text": "",
                            "is_gap": True,
                        },
                        {
                            "id": "caption_last",
                            "start_frame": gap_end_frame,
                            "end_frame": last_end_frame,
                            "timeline_start_frame": gap_end_frame,
                            "timeline_end_frame": last_end_frame,
                            "frame_rate": fps,
                            "timeline_frame_rate": fps,
                            "text": "last subtitle",
                            "speaker": "01",
                            "quality": {"confidence_label": "green"},
                        },
                    ],
                    primary_fps=fps,
                ),
                "roughcut_state": {
                    "selected_candidate_id": "roughcut_a",
                    "candidates": [
                        {
                            "candidate_id": "roughcut_a",
                            "name": "roughcut A",
                            "outputs": {
                                "edl": {
                                    "duration": 4.0,
                                    "metadata": {
                                        "source": "compatibility",
                                        "roughcut_v2": {"major_segment_count": 2},
                                    },
                                    "segments": [
                                        {
                                            "segment_id": "chapter_0001",
                                            "chapter_id": "chapter_0001",
                                            "source_path": str(media_path),
                                            "source_start": 0.0,
                                            "source_end": boundary_frame / fps,
                                            "output_start": 0.0,
                                            "output_end": boundary_frame / fps,
                                            "timeline_start": 0.0,
                                            "timeline_end": boundary_frame / fps,
                                            "metadata": {"major_id": "A", "minor_code": "A1"},
                                        },
                                        {
                                            "segment_id": "chapter_0002",
                                            "chapter_id": "chapter_0002",
                                            "source_path": str(media_path),
                                            "source_start": first_end_frame / fps,
                                            "source_end": duration_sec,
                                            "output_start": boundary_frame / fps,
                                            "output_end": 4.0,
                                            "timeline_start": first_end_frame / fps,
                                            "timeline_end": duration_sec,
                                            "metadata": {"major_id": "B", "minor_code": "B1"},
                                        },
                                    ],
                                    "stitched_cut_boundaries": [exact_join],
                                },
                                "render_plan": {
                                    "output_path": str(root / "roughcut.mov"),
                                    "render_mode": "sync_safe",
                                    "segment_manifest": [
                                        {
                                            "segment_id": "chapter_0001",
                                            "source_path": str(media_path),
                                            "source_start": 0.0,
                                            "source_end": boundary_frame / fps,
                                            "output_end": boundary_frame / fps,
                                            "metadata": {"manifest_shape": "legacy"},
                                        }
                                    ],
                                    "stitched_cut_boundaries": [exact_join],
                                },
                            },
                        }
                    ],
                },
            }

            write_project_file(str(project_path), copy.deepcopy(project))
            storage = read_project_storage_payload(str(project_path))
            clear_project_file_cache(str(project_path))
            loaded = read_project_file(str(project_path))
            rows = project_segments_to_editor(loaded)
            snapshot = build_project_nle_snapshot(loaded, project_path=str(project_path))

        self.assertNotIn("nle", storage)
        self.assertNotIn("nle_snapshot", storage)
        stored_clip = storage["timeline"]["tracks"][0]["clips"][0]
        self.assertEqual(stored_clip["proxy_path"], str(proxy_path))
        self.assertEqual(stored_clip["cache_key"], "preview-cache-001")
        self.assertEqual(stored_clip["relink"]["last_known_path"], str(media_path))

        subtitle_rows = [row for row in rows if not row.get("is_gap")]
        gap_rows = [row for row in rows if row.get("is_gap")]
        self.assertEqual(len(subtitle_rows), 2)
        self.assertEqual(len(gap_rows), 1)
        self.assertEqual((subtitle_rows[0]["start_frame"], subtitle_rows[-1]["end_frame"]), (first_start_frame, last_end_frame))
        self.assertEqual((gap_rows[0]["start_frame"], gap_rows[0]["end_frame"]), (first_end_frame, gap_end_frame))
        self.assertEqual(subtitle_rows[0]["quality_candidates"][0]["candidate_id"], "qc1")
        self.assertEqual(subtitle_rows[0]["words"][0]["word"], "first")
        self.assertEqual(subtitle_rows[0]["stt_ensemble_source"], "STT1")
        self.assertEqual(subtitle_rows[0]["subtitle_stage_confidence"]["stages"]["stt"]["score"], 91)
        self.assertEqual(subtitle_rows[0]["clip_local_start_frame"], first_start_frame)

        sequence = snapshot.sequences[0]
        self.assertEqual(snapshot.metadata["caption_count"], 2)
        self.assertEqual(sequence.duration, round(duration_sec, 6))
        self.assertEqual(
            [caption.text for caption in sequence.captions],
            ["first subtitle", "last subtitle"],
        )
        self.assertAlmostEqual(sequence.captions[0].sequence_start, first_start_frame / fps)
        self.assertAlmostEqual(sequence.captions[0].sequence_end, first_end_frame / fps)
        self.assertAlmostEqual(sequence.captions[1].sequence_start, gap_end_frame / fps)
        self.assertAlmostEqual(sequence.captions[1].sequence_end, last_end_frame / fps)
        self.assertEqual(sequence.captions[0].metadata["quality_candidates"][0]["candidate_id"], "qc1")
        self.assertEqual(sequence.captions[0].metadata["words"][0]["word"], "first")
        self.assertEqual(sequence.captions[0].metadata["subtitle_stage_confidence"]["stages"]["stt"]["score"], 91)
        self.assertEqual(sequence.captions[0].metadata["start_frame"], first_start_frame)

        render_plan = snapshot.render_plans[0]
        self.assertEqual(render_plan.output_duration, 4.0)
        self.assertEqual(render_plan.segments[0]["metadata"]["major_id"], "A")
        self.assertEqual(render_plan.segment_manifest[0]["metadata"]["manifest_shape"], "legacy")
        self.assertEqual(render_plan.stitched_cut_boundaries[0]["segment_before_id"], "chapter_0001")
        exact_markers = [
            marker
            for marker in sequence.markers
            if marker.kind == "roughcut_exact_join"
        ]
        self.assertEqual(len(exact_markers), 1)
        self.assertAlmostEqual(exact_markers[0].time, boundary_frame / fps)
        self.assertEqual(exact_markers[0].metadata["frame"], boundary_frame)
        self.assertEqual(exact_markers[0].metadata["detector"], "roughcut-edl-join-v1")
        self.assertEqual(exact_markers[0].metadata["exact_join"]["segment_after_id"], "chapter_0002")


if __name__ == "__main__":
    unittest.main()
