import copy
import tempfile
import unittest
from pathlib import Path

from core.project.nle_snapshot import (
    build_project_nle_snapshot,
    markers_from_roughcut_sidecar_payload,
    markers_from_stitched_cut_boundaries,
)
from core.project.project_context import build_editor_state
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)


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


if __name__ == "__main__":
    unittest.main()
