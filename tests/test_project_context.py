# Version: 03.09.29
# Phase: PHASE2
import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import core.project.project_io as project_io
import core.project.project_manager as project_manager
from core.project.project_io import clear_project_file_cache, read_project_file, write_project_file
from core.project.project_manager import (
    create_project,
    extract_model_settings,
    load_project,
    merge_project_model_settings,
    save_project,
    save_project_roughcut_state,
)
from core.project.project_phase1b import enrich_existing_project_file
from core.project.project_context import (
    SUBTITLE_CANVAS_VECTOR_SCHEMA,
    build_editor_state,
    project_cut_boundary_segments,
    project_cut_boundary_provisional_segments,
    project_active_work_mode,
    project_workspace,
    project_clip_boundaries,
    project_media_files,
    project_mode,
    project_voice_activity_segments,
    project_roughcut_state,
    project_segments_to_editor,
    project_stt_preview_segments,
    segment_signature,
)
from core.project.project_assets import (
    PROJECT_EXTERNAL_STORAGE,
    externalize_project_text_assets,
    hydrate_project_text_asset_cache,
    write_srt_track,
)
from core.project.project_format import PROJECT_SCHEMA_VERSION, PROJECT_STORAGE_SCHEMA, PROJECT_VIDEO_SCHEMA
from core.project.project_srt import parse_srt_to_segments
from core.cut_boundary import split_segments_by_cut_boundaries
from core.roughcut.models import RoughCutDraftState, RoughCutResult, RoughCutSegment


def _state_segments(state: dict) -> list[dict]:
    return project_segments_to_editor({"editor_state": state})


class ProjectContextTests(unittest.TestCase):
    def test_probe_media_rows_reuses_local_probe_cache_without_aliasing(self):
        cache_key = project_manager._probe_cache_key("clip1.mp4")
        probe_cache = {
            cache_key: {"duration": 10.0, "fps": 30.0, "width": 1920, "height": 1080}
        }

        with patch("core.project.project_manager.probe_media_many_lookup") as batch_probe, patch(
            "core.project.project_manager._get_media_probe"
        ) as single_probe:
            rows = project_manager._probe_media_rows(
                ["clip1.mp4", "clip1.mp4"],
                probe_cache=probe_cache,
            )

        batch_probe.assert_not_called()
        single_probe.assert_not_called()
        self.assertEqual([row["duration"] for row in rows], [10.0, 10.0])
        self.assertIsNot(rows[0], rows[1])
        rows[0]["duration"] = 99.0
        self.assertEqual(rows[1]["duration"], 10.0)
        self.assertEqual(probe_cache[cache_key]["duration"], 10.0)

    def test_create_project_reuses_probe_batch_for_duplicate_media_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "video.mp4"
            media_path.write_bytes(b"video")
            captured = {}

            def _fake_probe_many(paths):
                captured["paths"] = list(paths)
                return {
                    path: {"duration": 10.0, "fps": 30.0, "width": 1920, "height": 1080}
                    for path in paths
                }

            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager.probe_media_many_lookup",
                side_effect=_fake_probe_many,
            ), patch("core.project.project_manager._get_media_probe") as single_probe:
                project_path = Path(
                    create_project(
                        "duplicate_media_probe_cache",
                        media_paths=[str(media_path), str(media_path)],
                        user_settings={},
                    )
                )
                payload = read_project_file(str(project_path))

        self.assertEqual(captured["paths"], [str(media_path)])
        single_probe.assert_not_called()
        clips = payload["timeline"]["tracks"][0]["clips"]
        self.assertEqual(len(clips), 2)
        self.assertEqual(clips[0]["source_duration"], 10.0)
        self.assertEqual(clips[1]["source_duration"], 10.0)

    def test_create_project_externalize_reuses_seed_segments_without_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "video.mp4"
            media_path.write_bytes(b"video")
            srt_path = Path(tmp) / "video.srt"
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n안녕\n", encoding="utf-8")

            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 30.0},
            ), patch(
                "core.project.project_manager.project_segments_to_editor",
                side_effect=AssertionError("create_project should reuse prebuilt editor segments"),
            ):
                project_path = Path(
                    create_project(
                        "seed_segment_reuse",
                        media_paths=[str(media_path)],
                        srt_path=str(srt_path),
                        user_settings={},
                    )
                )
                payload = read_project_file(str(project_path))

        self.assertEqual(payload["subtitles"]["segment_count"], 1)
        self.assertEqual(payload["editor_state"]["subtitles"]["segment_count"], 1)

    def test_create_project_uses_project_only_extension_and_list_ignores_plain_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "video.mp4"
            media_path.write_bytes(b"video")

            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 30.0},
            ):
                project_path = Path(
                    create_project(
                        "project_extension_filter_case",
                        media_paths=[str(media_path)],
                        user_settings={},
                    )
                )
                (Path(tmp) / "not_a_project.json").write_text("{}", encoding="utf-8")
                listed = project_manager.list_projects()

        self.assertEqual(project_path.suffix, project_manager.PROJECT_FILE_EXTENSION)
        self.assertTrue(project_manager.is_project_file_path(project_path.name))
        self.assertEqual([item["path"] for item in listed], [str(project_path)])

    def test_create_project_archives_existing_base_json_inside_backup_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = str(Path(tmp) / "video.mp4")
            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 30.0},
            ):
                first_path = Path(create_project("same_name", media_paths=[media_path], user_settings={}))
                first_payload = read_project_file(str(first_path))
                first_created_at = first_payload["created_at"]
                legacy_root_backup = Path(tmp) / "same_name_1.json"
                legacy_root_backup.write_text(
                    json.dumps({"project_name": "legacy-root-backup"}, ensure_ascii=False),
                    encoding="utf-8",
                )

                second_path = Path(create_project("same_name", media_paths=[media_path], user_settings={}))
                second_payload = read_project_file(str(second_path))

            backup_dir = Path(tmp) / "프로젝트백업"
            legacy_archived = backup_dir / "same_name_1.json"
            archived = backup_dir / f"same_name_1{project_manager.PROJECT_FILE_EXTENSION}"

            self.assertEqual(first_path, second_path)
            self.assertTrue(second_path.exists())
            self.assertTrue(legacy_archived.exists())
            self.assertTrue(archived.exists())
            self.assertFalse((Path(tmp) / "same_name_1.json").exists())
            self.assertEqual(json.loads(legacy_archived.read_text(encoding="utf-8"))["project_name"], "legacy-root-backup")
            self.assertEqual(second_payload["history"]["previous_base_project"], str(archived))
            self.assertEqual(read_project_file(str(archived))["created_at"], first_created_at)

    def test_create_project_strips_plaintext_api_keys_from_user_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "video.mp4"
            media_path.write_bytes(b"video")
            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 30.0},
            ):
                project_path = Path(
                    create_project(
                        "secret_safe_project",
                        media_paths=[str(media_path)],
                        user_settings={
                            "selected_model": "exaone3.5:7.8b",
                            "google_api_key": "google-secret",
                            "openai_api_key": "openai-secret",
                            "huggingface_token": "hf-secret",
                            "google_api_key_saved": True,
                            "openai_api_key_saved": True,
                            "huggingface_token_saved": True,
                        },
                    )
                )
                payload = read_project_file(str(project_path))

        stored = dict(payload.get("user_settings") or {})
        self.assertNotIn("google_api_key", stored)
        self.assertNotIn("openai_api_key", stored)
        self.assertNotIn("huggingface_token", stored)
        self.assertTrue(stored["google_api_key_saved"])
        self.assertTrue(stored["openai_api_key_saved"])
        self.assertTrue(stored["huggingface_token_saved"])

    def test_save_project_removes_legacy_plaintext_api_keys_from_existing_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "video.mp4"
            media_path.write_bytes(b"video")
            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 30.0},
            ):
                project_path = Path(
                    create_project(
                        "legacy_secret_cleanup",
                        media_paths=[str(media_path)],
                        user_settings={"selected_model": "exaone3.5:7.8b"},
                    )
                )

            payload = read_project_file(str(project_path))
            payload["user_settings"] = {
                "selected_model": "exaone3.5:7.8b",
                "google_api_key": "google-secret",
                "openai_api_key": "openai-secret",
                "huggingface_token": "hf-secret",
                "google_api_key_saved": True,
                "openai_api_key_saved": True,
                "huggingface_token_saved": True,
            }
            write_project_file(str(project_path), payload)

            save_project(str(project_path))
            repaired = read_project_file(str(project_path))

        stored = dict(repaired.get("user_settings") or {})
        self.assertNotIn("google_api_key", stored)
        self.assertNotIn("openai_api_key", stored)
        self.assertNotIn("huggingface_token", stored)
        self.assertTrue(stored["google_api_key_saved"])
        self.assertTrue(stored["openai_api_key_saved"])
        self.assertTrue(stored["huggingface_token_saved"])

    def test_create_project_prefills_confirmed_cut_boundaries_and_middle_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "video.mp4"
            media_path.write_bytes(b"video")
            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 300.0, "fps": 24.0},
            ), patch(
                "core.cut_boundary.cut_boundary_scan_profile",
                return_value={"level": "medium", "positions": (0, 2, 4, 6, 8), "mask": "x5"},
            ), patch(
                "core.cut_boundary.scan_media_cut_boundary_provisionals",
                return_value=[{"timeline_sec": 150.0, "timeline_frame": 3600, "fps": 24.0}],
            ), patch(
                "core.cut_boundary.verify_media_cut_boundary_rows",
                return_value=[{"timeline_sec": 150.0, "timeline_frame": 3600, "fps": 24.0, "verified": True}],
            ):
                project_path = Path(
                    create_project(
                        "cut_prefill",
                        media_paths=[str(media_path)],
                        user_settings={"cut_boundary_detection_enabled": True},
                    )
                )
                payload = load_project(str(project_path), hydrate_text_assets=False)

        cut_rows = project_cut_boundary_segments(payload)
        self.assertEqual(len(cut_rows), 1)
        self.assertEqual(cut_rows[0]["timeline_frame"], 3600)
        middle_rows = list(((payload.get("analysis", {}) or {}).get("cut_boundary_topicless_middle_segments")) or [])
        self.assertEqual([row["major_id"] for row in middle_rows], ["A", "B"])
        self.assertEqual(
            [(row["timeline_start_frame"], row["timeline_end_frame"]) for row in middle_rows],
            [(0, 3600), (3600, 7200)],
        )
        self.assertTrue(payload["analysis"]["cut_boundary_topicless_finalized"])

    def test_create_project_with_subtitles_persists_final_middle_segments_and_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "video.mp4"
            media_path.write_bytes(b"video")
            srt_path = Path(tmp) / "video.srt"
            srt_path.write_text(
                "1\n00:00:01,000 --> 00:00:04,000\n도입 자막입니다.\n\n"
                "2\n00:02:35,000 --> 00:02:39,000\n후반 자막입니다.\n",
                encoding="utf-8",
            )
            llm_refs = {}
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        segment_id="major_A",
                        major_id="A",
                        start=0.0,
                        end=150.0,
                        title="도입 주제",
                        summary="앞부분 요약",
                        tags=("오프닝", "제품 소개"),
                        status="confirmed",
                    ),
                    RoughCutSegment(
                        segment_id="major_B",
                        major_id="B",
                        start=150.0,
                        end=300.0,
                        title="후반 주제",
                        summary="뒷부분 요약",
                        tags=("실내", "시트", "디자인 특징"),
                        status="confirmed",
                    ),
                ),
                video_summary="중분류 2개",
                draft_state=RoughCutDraftState(status="confirmed"),
                schema_version="roughcut_result.v2",
            )

            def _fake_llm(*_args, **kwargs):
                llm_refs["reference_major_segments"] = list(kwargs.get("reference_major_segments") or [])
                llm_refs["reviewed_cut_boundaries"] = list(kwargs.get("reviewed_cut_boundaries") or [])
                return None

            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 300.0, "fps": 24.0},
            ), patch(
                "core.cut_boundary.cut_boundary_scan_profile",
                return_value={"level": "medium", "positions": (0, 2, 4, 6, 8), "mask": "x5"},
            ), patch(
                "core.cut_boundary.scan_media_cut_boundary_provisionals",
                return_value=[{"timeline_sec": 150.0, "timeline_frame": 3600, "fps": 24.0}],
            ), patch(
                "core.cut_boundary.verify_media_cut_boundary_rows",
                return_value=[{"timeline_sec": 150.0, "timeline_frame": 3600, "fps": 24.0, "verified": True}],
            ), patch(
                "core.project.project_manager.run_editor_roughcut_llm_draft",
                side_effect=_fake_llm,
            ), patch(
                "core.project.project_manager.build_editor_roughcut_draft_result",
                return_value=result,
            ):
                project_path = Path(
                    create_project(
                        "cut_prefill_with_topics",
                        media_paths=[str(media_path)],
                        srt_path=str(srt_path),
                        user_settings={"cut_boundary_detection_enabled": True},
                    )
                )
                payload = load_project(str(project_path), hydrate_text_assets=False)

        middle_rows = list(((payload.get("analysis", {}) or {}).get("middle_segments")) or [])
        preliminary_rows = list(((payload.get("analysis", {}) or {}).get("preliminary_middle_segments")) or [])
        self.assertEqual([row["major_id"] for row in middle_rows], ["A", "B"])
        self.assertEqual([row["major_id"] for row in preliminary_rows], ["A", "B"])
        self.assertEqual(preliminary_rows[0]["segment_stage"], "preliminary")
        self.assertEqual(preliminary_rows[0]["segment_stage_name"], "예비 중분류 세그먼트")
        self.assertEqual([row["title"] for row in middle_rows], ["도입 주제", "후반 주제"])
        self.assertEqual(middle_rows[0]["tags"], ["오프닝", "제품 소개"])
        self.assertEqual(middle_rows[1]["tags"], ["실내", "시트", "디자인 특징"])
        self.assertEqual(middle_rows[1]["keywords"], ["실내", "시트", "디자인 특징"])
        self.assertEqual(
            [(row["timeline_start_frame"], row["timeline_end_frame"]) for row in middle_rows],
            [(0, 3600), (3600, 7200)],
        )
        self.assertEqual(
            [(row["timeline_start_frame"], row["timeline_end_frame"]) for row in preliminary_rows],
            [(0, 3600), (3600, 7200)],
        )
        self.assertEqual(
            payload["roughcut_state"]["selected_candidate_id"],
            "editor_post_generation_roughcut_draft",
        )
        self.assertEqual(
            [row["major_id"] for row in llm_refs["reference_major_segments"]],
            ["A", "B"],
        )
        self.assertEqual(len(llm_refs["reviewed_cut_boundaries"]), 1)
        self.assertEqual(llm_refs["reviewed_cut_boundaries"][0]["timeline_frame"], 3600)

    def test_build_editor_state_separates_multiclip_and_subtitles(self):
        state = build_editor_state(
            mode="multiclip",
            media_files=["/tmp/a.mp4", "/tmp/b.mp4"],
            segments=[
                {"start": 0.0, "end": 1.0, "text": "첫 자막", "speaker": "01", "_clip_idx": 0},
                {"start": 10.0, "end": 11.0, "text": "둘째 자막", "speaker": "02", "_clip_idx": 1},
            ],
            workspace={"last_playhead": 10.0},
            clip_boundaries=[
                {"start": 0.0, "end": 5.0, "file": "/tmp/a.mp4"},
                {"start": 5.0, "end": 15.0, "file": "/tmp/b.mp4"},
            ],
        )

        self.assertEqual(state["mode"], "multiclip")
        self.assertEqual(len(state["multiclip"]["boundaries"]), 2)
        self.assertEqual(state["single_clip"]["source_path"], "")
        self.assertEqual(state["subtitles"]["storage"], "vector_canvas")
        self.assertEqual(state["subtitles"]["segments"], [])
        self.assertEqual(_state_segments(state)[1]["speaker"], "02")
        vector_canvas = state["rendering"]["subtitle_canvas"]
        self.assertEqual(vector_canvas["schema"], SUBTITLE_CANVAS_VECTOR_SCHEMA)
        self.assertEqual(vector_canvas["renderer"]["active_surface"], "timeline-qwidget-2d")
        self.assertEqual(vector_canvas["segments"][1]["text"], "둘째 자막")
        self.assertEqual(vector_canvas["segments"][1]["clip"]["index"], 1)
        self.assertEqual(state["workspace"]["last_playhead"], 10.0)

    def test_workspace_zoom_and_scroll_are_not_persisted(self):
        state = build_editor_state(
            mode="single",
            media_files=["/tmp/a.mp4"],
            segments=[],
            workspace={
                "last_playhead": 10.0,
                "zoom_pps": 999.0,
                "pps": 888.0,
                "scroll_position": 77,
                "scroll_x": 66,
            },
        )

        self.assertEqual(state["workspace"], {"last_playhead": 10.0})
        self.assertEqual(
            project_workspace({"editor_state": {"workspace": state["workspace"]}}),
            {"last_playhead": 10.0},
        )

    def test_vector_canvas_uses_project_video_fps_for_frame_coordinates(self):
        state = build_editor_state(
            mode="single",
            media_files=["/tmp/a.mp4"],
            segments=[
                {"start": 2.0, "end": 3.0, "text": "fps 기준 자막", "speaker": "01"},
            ],
            primary_fps=24.0,
        )

        vector_canvas = state["rendering"]["subtitle_canvas"]
        vector_segment = vector_canvas["segments"][0]
        self.assertEqual(vector_canvas["coordinate_space"]["timeline_frame_rate"], 24.0)
        self.assertEqual(vector_segment["time"]["timeline_frame_rate"], 24.0)
        self.assertEqual(vector_segment["time"]["start_frame"], 48)
        self.assertEqual(vector_segment["time"]["end_frame"], 72)

    def test_build_editor_state_reuses_segment_signature_for_vector_canvas(self):
        with patch("core.project.project_context.segment_signature", wraps=segment_signature) as signature_mock:
            state = build_editor_state(
                mode="single",
                media_files=["/tmp/a.mp4"],
                segments=[
                    {"start": 0.0, "end": 1.0, "text": "첫 줄", "speaker": "00"},
                    {"start": 1.0, "end": 2.0, "text": "둘째 줄", "speaker": "01"},
                ],
                primary_fps=30.0,
            )

        self.assertEqual(signature_mock.call_count, 1)
        self.assertEqual(
            state["subtitles"]["segment_signature"],
            state["rendering"]["subtitle_canvas"]["segment_signature"],
        )

    def test_build_editor_state_roundtrip_preserves_gap_segments(self):
        state = build_editor_state(
            mode="single",
            media_files=["/tmp/a.mp4"],
            segments=[
                {"start": 0.0, "end": 1.0, "text": "앞 자막", "speaker": "00"},
                {"start": 1.0, "end": 2.0, "text": "", "speaker": "00", "is_gap": True},
                {"start": 2.0, "end": 3.0, "text": "뒤 자막", "speaker": "00"},
            ],
            primary_fps=30.0,
        )

        vector_canvas = state["rendering"]["subtitle_canvas"]
        self.assertEqual([row["text"] for row in vector_canvas["segments"]], ["앞 자막", "뒤 자막"])
        self.assertEqual(len(vector_canvas["gap_segments"]), 1)
        self.assertEqual(vector_canvas["gap_segments"][0]["kind"], "subtitle_gap")
        self.assertEqual(vector_canvas["gap_segments"][0]["time"]["start_frame"], 30)
        self.assertEqual(vector_canvas["gap_segments"][0]["time"]["end_frame"], 60)

        restored = _state_segments(state)
        self.assertEqual([bool(seg.get("is_gap")) for seg in restored], [False, True, False])
        self.assertEqual(restored[1]["text"], "")
        self.assertEqual(restored[1]["start_frame"], 30)
        self.assertEqual(restored[1]["end_frame"], 60)

    def test_project_io_roundtrip_preserves_stt_unicode_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            payload = {
                "project_name": "테스트",
                "analysis": {
                    "stt_candidate_tracks": {
                        "STT1": [{"start": 0.0, "end": 1.0, "text": "안녕하세요"}],
                        "STT2": [{"start": 0.0, "end": 1.0, "text": "안녕 하세요"}],
                    }
                },
            }

            write_project_file(str(path), payload)
            loaded = read_project_file(str(path))

        self.assertEqual(loaded["project_name"], "테스트")
        self.assertEqual(loaded["analysis"]["stt_candidate_tracks"]["STT2"][0]["text"], "안녕 하세요")

    def test_project_io_writes_binary_envelope_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.aissproj"
            payload = {
                "project_name": "binary-fast",
                "editor_state": {
                    "rendering": {
                        "subtitle_canvas": {
                            "segments": [
                                {
                                    "id": f"seg-{idx}",
                                    "start": idx * 1.0,
                                    "end": idx * 1.0 + 0.5,
                                    "text": "반복 저장 성능 확인 " * 4,
                                }
                                for idx in range(400)
                            ]
                        }
                    }
                },
            }

            write_project_file(str(path), payload)
            raw = path.read_bytes()
            stored = project_io.read_project_storage_payload(str(path))
            pretty_json = json.dumps(
                project_io._project_payload_for_disk(payload),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")

        self.assertTrue(raw.startswith(project_io._PROJECT_BINARY_MAGIC))
        self.assertFalse(raw.lstrip().startswith(b"{"))
        self.assertLess(len(raw), int(len(pretty_json) * 0.75))
        self.assertEqual(stored["project_name"], "binary-fast")
        self.assertEqual(
            stored["editor_state"]["rendering"]["subtitle_canvas"]["segments"][3]["text"],
            "반복 저장 성능 확인 " * 4,
        )

    def test_project_io_reads_legacy_json_project_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.aissproj"
            path.write_text(json.dumps({"project_name": "legacy-json"}, ensure_ascii=False), encoding="utf-8")
            clear_project_file_cache(str(path))

            loaded = read_project_file(str(path))

        self.assertEqual(loaded["project_name"], "legacy-json")

    def test_project_io_reuses_memory_cache_for_heavy_project_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            payload = {
                "project_name": "large",
                "editor_state": {
                    "rendering": {
                        "subtitle_canvas": {
                            "segments": [
                                {"start": i * 1.0, "end": i * 1.0 + 0.5, "text": f"row {i}"}
                                for i in range(250)
                            ]
                        }
                    }
                },
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            clear_project_file_cache(str(path))

            with patch("core.project.project_io._read_project_payload_from_disk", wraps=project_io._read_project_payload_from_disk) as load_mock:
                first = read_project_file(str(path))
                second = read_project_file(str(path))

            self.assertIs(first, second)
            self.assertEqual(load_mock.call_count, 1)
            self.assertEqual(second["editor_state"]["rendering"]["subtitle_canvas"]["segments"][42]["text"], "row 42")

    def test_project_io_write_primes_memory_cache_without_reparse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            clear_project_file_cache(str(path))
            payload = {"project_name": "cached-save", "workspace": {"last_playhead": 12.0}}

            write_project_file(str(path), payload)
            with patch("core.project.project_io._read_project_payload_from_disk", wraps=project_io._read_project_payload_from_disk) as load_mock:
                loaded = read_project_file(str(path))

            self.assertIs(loaded, payload)
            self.assertEqual(load_mock.call_count, 0)

    def test_project_io_reloads_cache_when_project_file_changes_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            clear_project_file_cache(str(path))
            path.write_text(json.dumps({"project_name": "first"}), encoding="utf-8")

            with patch("core.project.project_io._project_file_signature", side_effect=[(1, 10), (2, 11)]), \
                 patch("core.project.project_io._read_project_payload_from_disk", wraps=project_io._read_project_payload_from_disk) as load_mock:
                first = read_project_file(str(path))
                path.write_text(json.dumps({"project_name": "second", "changed": True}), encoding="utf-8")
                second = read_project_file(str(path))

            self.assertEqual(first["project_name"], "first")
            self.assertEqual(second["project_name"], "second")
            self.assertEqual(load_mock.call_count, 2)

    def test_project_io_lru_prunes_older_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            clear_project_file_cache()
            paths = []
            for idx in range(project_io._PROJECT_FILE_CACHE_MAX + 2):
                path = Path(tmp) / f"project_{idx}.json"
                path.write_text(json.dumps({"project_name": f"p{idx}"}), encoding="utf-8")
                read_project_file(str(path))
                paths.append(str(path))

            self.assertLessEqual(len(project_io._PROJECT_FILE_CACHE), project_io._PROJECT_FILE_CACHE_MAX)
            self.assertNotIn(project_io._project_cache_key(paths[0]), project_io._PROJECT_FILE_CACHE)

    def test_save_project_strips_legacy_workspace_zoom_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {"zoom_pps": 999.0, "scroll_x": 100},
                        "editor_state": {"workspace": {"pps": 888.0, "scroll_position": 200}},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            save_project(
                str(path),
                workspace={
                    "last_playhead": 3.0,
                    "zoom_pps": 777.0,
                    "pps": 666.0,
                    "scroll_x": 55,
                    "scroll_position": 44,
                },
            )
            loaded = load_project(str(path))

        self.assertEqual(loaded["workspace"], {"last_playhead": 3.0})
        self.assertEqual(loaded["editor_state"]["workspace"], {"last_playhead": 3.0})

    def test_project_segments_to_editor_preserves_clip_and_speaker_fields(self):
        project = {
            "editor_state": {
                "mode": "multiclip",
                "media_files": ["/tmp/a.mp4", "/tmp/b.mp4"],
                "multiclip": {
                    "boundaries": [
                        {"start": 0.0, "end": 5.0, "file": "/tmp/a.mp4"},
                        {"start": 5.0, "end": 15.0, "file": "/tmp/b.mp4"},
                    ],
                },
                "subtitles": {
                    "segments": [
                        {"start": 5.5, "end": 7.0, "text": "반영", "speaker": "03", "_clip_idx": 1},
                    ],
                },
            }
        }

        self.assertEqual(project_mode(project), "multiclip")
        self.assertEqual(project_media_files(project), ["/tmp/a.mp4", "/tmp/b.mp4"])
        self.assertEqual(project_clip_boundaries(project)[1]["file"], "/tmp/b.mp4")
        segments = project_segments_to_editor(project)
        self.assertEqual(segments[0]["_clip_idx"], 1)
        self.assertEqual(segments[0]["speaker"], "03")

    def test_project_segments_to_editor_can_restore_from_vector_canvas_layer(self):
        project = {
            "editor_state": {
                "mode": "single",
                "media_files": ["/tmp/a.mp4"],
                "rendering": {
                    "subtitle_canvas": {
                        "schema": SUBTITLE_CANVAS_VECTOR_SCHEMA,
                        "coordinate_space": {
                            "timeline_frame_rate": 24.0,
                        },
                        "segments": [
                            {
                                "line": 0,
                                "time": {
                                    "unit": "frame",
                                    "start_frame": 48,
                                    "end_frame": 72,
                                    "timeline_frame_rate": 24.0,
                                },
                                "text": "벡터 자막",
                                "speaker": "04",
                                "clip": {"index": 0, "file": "/tmp/a.mp4"},
                            }
                        ],
                    },
                },
            }
        }

        segment = project_segments_to_editor(project)[0]
        self.assertEqual(segment["text"], "벡터 자막")
        self.assertEqual(segment["speaker"], "04")
        self.assertAlmostEqual(segment["start"], 2.0)
        self.assertAlmostEqual(segment["end"], 3.0)
        self.assertEqual(segment["_clip_file"], "/tmp/a.mp4")

    def test_editor_state_preserves_quality_metadata(self):
        state = build_editor_state(
            mode="single",
            media_files=["/tmp/movie.mp4"],
            segments=[
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "품질",
                    "speaker": "00",
                    "quality": {"confidence_label": "red", "confidence_score": 40},
                    "quality_history": [{"confidence_label": "gray"}],
                    "quality_candidates": [{"candidate_id": "c1", "text": "품질"}],
                }
            ],
        )

        segment = _state_segments(state)[0]
        self.assertEqual(segment["quality"]["confidence_label"], "red")
        self.assertEqual(segment["quality_history"][0]["confidence_label"], "gray")
        self.assertEqual(segment["quality_candidates"][0]["candidate_id"], "c1")

    def test_editor_state_preserves_stt_metadata_and_preview_candidates(self):
        state = build_editor_state(
            mode="multiclip",
            media_files=["/tmp/a.mp4", "/tmp/b.mp4"],
            segments=[
                {
                    "start": 5.0,
                    "end": 6.0,
                    "text": "최종",
                    "speaker": "00",
                    "_clip_idx": 1,
                    "stt_selected_source": "STT2",
                    "stt_candidates": [
                        {"source": "STT1", "start": 5.0, "end": 6.0, "text": "후보1"},
                        {"source": "STT2", "start": 5.0, "end": 6.0, "text": "후보2"},
                    ],
                    "stt_ensemble_llm_selected_source": "STT2",
                }
            ],
            stt_preview_segments=[
                {
                    "start": 5.0,
                    "end": 6.0,
                    "text": "후보2",
                    "stt_preview_source": "STT2",
                    "_clip_idx": 1,
                    "_clip_file": "/tmp/b.mp4",
                }
            ],
            provisional_cut_boundaries=[
                {"timeline_sec": 5.25, "timeline_frame": 126, "fps": 24.0, "status": "provisional"}
            ],
        )

        segment = _state_segments(state)[0]
        self.assertEqual(segment["stt_selected_source"], "STT2")
        self.assertEqual(segment["stt_candidates"][1]["text"], "후보2")
        preview = state["stt"]["preview_segments"][0]
        self.assertEqual(preview["stt_preview_source"], "STT2")
        self.assertEqual(preview["_clip_idx"], 1)
        self.assertTrue(preview["_live_stt_preview"])
        self.assertEqual(state["analysis"]["cut_boundary_provisional_boundaries"][0]["timeline_frame"], 126)

    def test_editor_state_persists_subtitle_review_status(self):
        state = build_editor_state(
            mode="single",
            media_files=["/tmp/movie.mp4"],
            segments=[
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "자동 선택",
                    "speaker": "00",
                    "quality": {"confidence_label": "green", "confidence_score": 96},
                    "stt_ensemble_llm_selected_source": "STT1",
                    "stt_candidates": [{"source": "STT1", "score": 0.96, "text": "자동 선택"}],
                },
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "확정",
                    "speaker": "00",
                    "quality": {
                        "confidence_label": "green",
                        "confidence_score": 98,
                        "manual_confirmed": True,
                        "flags": ["manual_confirmed"],
                    },
                },
            ],
        )

        pending, confirmed = _state_segments(state)
        self.assertEqual(pending["subtitle_review_state"], "pending")
        self.assertEqual(pending["subtitle_status_color"], "#FFD60A")
        self.assertEqual(pending["subtitle_status_schema"], "subtitle_status.v1")
        self.assertEqual(pending["subtitle_status_source"], "STT1")
        self.assertEqual(confirmed["subtitle_review_state"], "confirmed")
        self.assertEqual(confirmed["subtitle_status_color"], "#34C759")

    def test_segment_signature_changes_when_subtitle_text_changes(self):
        before = segment_signature([{"start": 0.0, "end": 1.0, "text": "원본", "speaker": "00"}])
        after = segment_signature([{"start": 0.0, "end": 1.0, "text": "수정", "speaker": "00"}])

        self.assertNotEqual(before, after)

    def test_project_helpers_read_active_roughcut_state(self):
        project = {
            "workspace": {"active_work_mode": "roughcut"},
            "roughcut_state": {"source_signature": "abc", "user_edits": {"chapter_0001": {"title": "수정"}}},
        }

        self.assertEqual(project_active_work_mode(project), "roughcut")
        self.assertEqual(project_roughcut_state(project)["source_signature"], "abc")

    def test_save_project_persists_editor_and_roughcut_state_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {
                            "tracks": [
                                {
                                    "clips": [
                                        {
                                            "id": "clip_a",
                                            "source_path": "/tmp/a.mp4",
                                            "timeline_start": 0.0,
                                            "timeline_end": 10.0,
                                            "order": 0,
                                        }
                                    ]
                                }
                            ]
                        },
                        "media": [{"order": 0, "path": "/tmp/a.mp4"}],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            save_project(
                str(path),
                segments=[{"start": 1.0, "end": 2.0, "text": "저장", "speaker": "01"}],
                roughcut_state={
                    "source_signature": "sig",
                    "chapters": [],
                    "edl_segments": [],
                    "selected_candidate_id": "candidate_a",
                    "candidates": [{"candidate_id": "candidate_a", "source_signature": "sig", "chapters": [], "edl_segments": []}],
                },
                active_work_mode="roughcut",
            )
            loaded = load_project(str(path))

        self.assertEqual(loaded["version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(project_active_work_mode(loaded), "roughcut")
        self.assertEqual(loaded["editor_state"]["workspace"]["active_work_mode"], "roughcut")
        self.assertEqual(project_roughcut_state(loaded)["source_signature"], "sig")
        self.assertEqual(project_roughcut_state(loaded)["selected_candidate_id"], "candidate_a")
        self.assertEqual(len(project_roughcut_state(loaded)["candidates"]), 1)
        self.assertEqual(project_segments_to_editor(loaded)[0]["text"], "저장")

    def test_save_project_roughcut_state_preserves_existing_subtitle_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.aissproj"
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {
                            "tracks": [
                                {
                                    "clips": [
                                        {
                                            "id": "clip_a",
                                            "source_path": "/tmp/a.mp4",
                                            "timeline_start": 0.0,
                                            "timeline_end": 10.0,
                                            "timeline_start_frame": 0,
                                            "timeline_end_frame": 300,
                                            "source_frame_rate": 30.0,
                                            "fps": 30.0,
                                            "order": 0,
                                        }
                                    ]
                                }
                            ]
                        },
                        "media": [{"order": 0, "path": "/tmp/a.mp4", "fps": 30.0}],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            save_project(
                str(path),
                segments=[{"start": 1.0, "end": 2.0, "text": "기존 자막", "speaker": "01"}],
            )
            middle_rows = [
                {
                    "major_id": "A",
                    "title": "도입",
                    "summary": "도입부 요약",
                    "start": 1.0,
                    "end": 4.0,
                    "status": "confirmed",
                }
            ]
            roughcut_state = {
                "selected_candidate_id": "candidate_a",
                "candidates": [{"candidate_id": "candidate_a", "segments": list(middle_rows)}],
            }
            with patch("core.project.project_manager._externalize_project_payload") as externalize:
                save_project_roughcut_state(
                    str(path),
                    middle_segments=middle_rows,
                    roughcut_result={"segments": list(middle_rows)},
                    roughcut_state=roughcut_state,
                    preliminary_middle_segments=[],
                    active_work_mode="editor",
                )
            loaded = load_project(str(path))

        externalize.assert_not_called()
        self.assertEqual(project_segments_to_editor(loaded)[0]["text"], "기존 자막")
        self.assertEqual(project_active_work_mode(loaded), "editor")
        self.assertEqual(loaded["middle_segments"][0]["title"], "도입")
        self.assertEqual(project_roughcut_state(loaded)["selected_candidate_id"], "candidate_a")

    def test_save_project_compacts_roughcut_middle_segments_to_frame_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.aissproj"
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {
                            "tracks": [
                                {
                                    "clips": [
                                        {
                                            "id": "clip_a",
                                            "source_path": "/tmp/a.mp4",
                                            "timeline_start": 0.0,
                                            "timeline_end": 10.0,
                                            "timeline_start_frame": 0,
                                            "timeline_end_frame": 599,
                                            "source_frame_rate": 59.94,
                                            "fps": 59.94,
                                            "order": 0,
                                        }
                                    ]
                                }
                            ]
                        },
                        "media": [{"order": 0, "path": "/tmp/a.mp4", "fps": 59.94}],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            middle_rows = [
                {
                    "major_id": "A",
                    "title": "도입",
                    "summary": "중분류 요약",
                    "start": 2.0,
                    "end": 4.0,
                    "status": "confirmed",
                }
            ]
            roughcut_result = {
                "segments": list(middle_rows),
                "chapters": [
                    {
                        "chapter_id": "A_0001",
                        "major_id": "A",
                        "title": "첫 챕터",
                        "start": 2.0,
                        "end": 3.0,
                    }
                ],
                "guide_markdown": "guide",
                "markdown_guide": "guide",
                "schema_version": "roughcut_result.v2",
            }
            roughcut_state = {
                "selected_candidate_id": "candidate_a",
                "candidates": [
                    {
                        "candidate_id": "candidate_a",
                        "segments": list(middle_rows),
                        "chapters": list(roughcut_result["chapters"]),
                        "guide_markdown": "guide",
                        "markdown_guide": "guide",
                        "schema_version": "roughcut_result.v2",
                    }
                ],
            }

            save_project(
                str(path),
                middle_segments=middle_rows,
                roughcut_result=roughcut_result,
                roughcut_state=roughcut_state,
            )
            raw = project_io.read_project_storage_payload(str(path))
            loaded = load_project(str(path))

        self.assertEqual(raw["storage_schema"], PROJECT_STORAGE_SCHEMA)
        self.assertNotIn("middle_segments", raw)
        self.assertNotIn("roughcut_result", raw)
        stored_middle = raw["analysis"]["middle_segments"][0]
        self.assertEqual((stored_middle["start_frame"], stored_middle["end_frame"]), (120, 240))
        self.assertNotIn("start", stored_middle)
        stored_result = raw["analysis"]["roughcut_result"]["segments"][0]
        self.assertEqual((stored_result["start_frame"], stored_result["end_frame"]), (120, 240))
        self.assertNotIn("start", stored_result)
        stored_candidate = raw["roughcut_state"]["candidates"][0]["segments"][0]
        self.assertEqual((stored_candidate["start_frame"], stored_candidate["end_frame"]), (120, 240))
        self.assertNotIn("start", stored_candidate)
        self.assertEqual(loaded["middle_segments"][0]["major_id"], "A")
        self.assertAlmostEqual(loaded["middle_segments"][0]["start"], 120.0 / 59.94, places=6)
        self.assertAlmostEqual(loaded["roughcut_result"]["segments"][0]["end"], 240.0 / 59.94, places=6)
        self.assertEqual(loaded["roughcut_result"]["chapters"][0]["chapter_id"], "A_0001")

    def test_save_project_externalize_reuses_editor_canvas_segments_without_second_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {
                            "tracks": [
                                {
                                    "clips": [
                                        {
                                            "id": "clip_a",
                                            "source_path": "/tmp/a.mp4",
                                            "timeline_start": 0.0,
                                            "timeline_end": 10.0,
                                            "order": 0,
                                        }
                                    ]
                                }
                            ]
                        },
                        "media": [{"order": 0, "path": "/tmp/a.mp4"}],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            original = project_manager.project_segments_to_editor
            calls = {"count": 0}

            def _counting_segments(*args, **kwargs):
                calls["count"] += 1
                return original(*args, **kwargs)

            with patch("core.project.project_manager.project_segments_to_editor", side_effect=_counting_segments):
                save_project(
                    str(path),
                    segments=[{"start": 1.0, "end": 2.0, "text": "저장", "speaker": "01"}],
                )

        self.assertEqual(calls["count"], 1)

    def test_save_project_persists_model_settings_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            save_project(
                str(path),
                user_settings={
                    "selected_audio_ai": "deepfilter",
                    "selected_vad": "silero",
                    "selected_whisper_model": "primary-ko",
                    "stt_ensemble_enabled": True,
                    "selected_whisper_model_secondary": "secondary-large",
                    "selected_llm_provider": "ollama",
                    "selected_model": "exaone3.5:7.8b",
                    "roughcut_llm_enabled": True,
                    "roughcut_llm_use_override": False,
                    "roughcut_llm_model": "inherit",
                    "non_model_ui_key": "ignored",
                },
            )
            loaded = load_project(str(path))

        snapshot = loaded["model_settings"]
        self.assertEqual(snapshot["schema"], "ai_model_settings.v1")
        self.assertEqual(snapshot["models"]["stt1"], "primary-ko")
        self.assertEqual(snapshot["models"]["stt2"], "secondary-large")
        self.assertEqual(snapshot["models"]["roughcut_llm"], "exaone3.5:7.8b")
        restored = merge_project_model_settings({"selected_model": "old", "theme": "dark"}, loaded)
        self.assertEqual(restored["selected_model"], "exaone3.5:7.8b")
        self.assertEqual(restored["selected_whisper_model_secondary"], "secondary-large")
        self.assertEqual(restored["theme"], "dark")
        self.assertNotIn("non_model_ui_key", extract_model_settings(loaded))

    def test_save_project_preliminary_middle_segments_do_not_mutate_input_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            preliminary_rows = [
                {"major_id": "A", "title": "도입", "start": 0.0, "end": 10.0, "source": "llm"}
            ]
            original_rows = [dict(row) for row in preliminary_rows]

            save_project(
                str(path),
                preliminary_middle_segments=preliminary_rows,
            )
            loaded = load_project(str(path))

        self.assertEqual(preliminary_rows, original_rows)
        self.assertEqual(loaded["analysis"]["preliminary_middle_segments"][0]["segment_stage"], "preliminary")

    def test_save_project_adds_frame_timebase_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"fake")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 2.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[{"start": 1.0, "end": 1.5, "text": "프레임", "speaker": "00"}],
                )
            loaded = load_project(str(path))

        timebase = loaded["timeline"]["timebase"]
        clip = loaded["timeline"]["tracks"][0]["clips"][0]
        self.assertNotIn("segments", loaded["subtitles"])
        segment = project_segments_to_editor(loaded)[0]
        self.assertEqual(timebase["unit"], "frame")
        self.assertEqual(timebase["canonical_unit"], "frame")
        self.assertTrue(timebase["seconds_are_derived"])
        self.assertEqual(timebase["primary_fps"], 24.0)
        self.assertEqual(timebase["total_frames"], 48)
        self.assertEqual(loaded["frame_timebase"]["canonical_unit"], "frame")
        self.assertEqual(clip["source_frame_count"], 48)
        self.assertEqual(clip["timeline_start_frame"], 0)
        self.assertEqual(clip["timeline_end_frame"], 48)
        self.assertEqual(clip["source_start_frame"], 0)
        self.assertEqual(clip["source_end_frame"], 48)
        self.assertEqual(segment["timeline_start_frame"], 24)
        self.assertEqual(segment["timeline_end_frame"], 36)
        self.assertEqual(segment["start_frame"], 24)
        self.assertEqual(segment["end_frame"], 36)
        self.assertEqual(segment["clip_local_start_frame"], 24)
        self.assertEqual(segment["frame_range"]["unit"], "frame")
        self.assertEqual(segment["frame_range"]["start"], 24)
        self.assertEqual(loaded["editor_state"]["frame_timebase"]["unit"], "frame")
        editor_segment = project_segments_to_editor(loaded)[0]
        self.assertEqual(editor_segment["start_frame"], 24)
        self.assertEqual(editor_segment["end_frame"], 36)
        self.assertEqual(loaded["video"]["schema"], PROJECT_VIDEO_SCHEMA)
        self.assertEqual(loaded["video"]["primary_fps"], 24.0)
        self.assertEqual(loaded["video"]["duration_sec"], 2.0)
        self.assertEqual(loaded["storage_schema"], PROJECT_STORAGE_SCHEMA)

    def test_save_project_reuses_persisted_video_header_metadata_without_reprobe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"fake")
            project = {
                "video": {
                    "schema": PROJECT_VIDEO_SCHEMA,
                    "primary_path": str(media),
                    "media_kind": "video",
                    "duration_sec": 2.0,
                    "primary_fps": 24.0,
                    "frame_duration": 1.0 / 24.0,
                    "total_frames": 48,
                    "width": 1920,
                    "height": 1080,
                    "resolution": "1920x1080",
                    "clip_count": 1,
                    "clips": [
                        {
                            "id": "clip_a",
                            "order": 0,
                            "path": str(media),
                            "type": "video",
                            "duration_sec": 2.0,
                            "fps": 24.0,
                            "frame_count": 48,
                            "width": 1920,
                            "height": 1080,
                            "timeline_start_sec": 0.0,
                            "timeline_end_sec": 2.0,
                            "timeline_start_frame": 0,
                            "timeline_end_frame": 48,
                        }
                    ],
                    "timebase": {
                        "unit": "frame",
                        "canonical_unit": "frame",
                        "mode": "project_video_header",
                        "primary_fps": 24.0,
                        "frame_duration": 1.0 / 24.0,
                        "timeline_start_frame": 0,
                        "timeline_end_frame": 48,
                        "total_frames": 48,
                        "seconds_are_derived": True,
                        "time_fields_are_compatibility": False,
                    },
                },
                "app": "AI Subtitle Studio",
                "version": "04.00.06",
                "phase": "PHASE2",
                "project_name": "header_fast_path",
                "storage_schema": PROJECT_STORAGE_SCHEMA,
                "timeline": {
                    "total_duration": 2.0,
                    "tracks": [
                        {
                            "id": "video_track_0",
                            "type": "video",
                            "clips": [
                                {
                                    "id": "clip_a",
                                    "source_path": str(media),
                                    "type": "video",
                                    "timeline_start": 0.0,
                                    "timeline_end": 2.0,
                                    "order": 0,
                                }
                            ],
                        }
                    ],
                },
                "subtitles": {"storage": "vector_canvas", "segment_count": 0},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[str(media)],
                    segments=[],
                    primary_fps=24.0,
                ),
                "workspace": {},
            }
            path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

            with patch(
                "core.project.project_manager.probe_media",
                side_effect=AssertionError("save_project should reuse stored video header metadata"),
            ):
                save_project(
                    str(path),
                    segments=[{"start": 0.0, "end": 0.5, "text": "헤더", "speaker": "00"}],
                )
            loaded = load_project(str(path))

        clip = loaded["timeline"]["tracks"][0]["clips"][0]
        self.assertEqual(clip["source_duration"], 2.0)
        self.assertEqual(clip["fps"], 24.0)
        self.assertEqual(clip["width"], 1920)
        self.assertEqual(clip["height"], 1080)
        self.assertEqual(loaded["video"]["primary_fps"], 24.0)
        self.assertEqual(loaded["video"]["width"], 1920)
        self.assertEqual(loaded["video"]["height"], 1080)

    def test_save_project_reuses_existing_status_payload_without_recomputing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"fake")
            project = {
                "app": "AI Subtitle Studio",
                "version": "test",
                "phase": "PHASE2",
                "timeline": {
                    "total_duration": 2.0,
                    "tracks": [
                        {
                            "clips": [
                                {
                                    "id": "clip_a",
                                    "source_path": str(media),
                                    "timeline_start": 0.0,
                                    "timeline_end": 2.0,
                                    "order": 0,
                                }
                            ]
                        }
                    ],
                },
                "media": [{"order": 0, "path": str(media)}],
                "video": {
                    "schema": PROJECT_VIDEO_SCHEMA,
                    "primary_path": str(media),
                    "media_kind": "video",
                    "duration_sec": 2.0,
                    "primary_fps": 30.0,
                    "frame_duration": 1.0 / 30.0,
                    "total_frames": 60,
                    "width": 1920,
                    "height": 1080,
                    "resolution": "1920x1080",
                    "clip_count": 1,
                    "clips": [
                        {
                            "id": "clip_a",
                            "order": 0,
                            "path": str(media),
                            "type": "video",
                            "duration_sec": 2.0,
                            "fps": 30.0,
                            "frame_count": 60,
                            "width": 1920,
                            "height": 1080,
                            "timeline_start_frame": 0,
                            "timeline_end_frame": 60,
                            "source_start_frame": 0,
                            "source_end_frame": 60,
                        }
                    ],
                },
                "subtitles": {"segments": []},
                "workspace": {},
                "user_settings": {},
            }
            write_project_file(str(path), project)

            seg = {
                "id": "seg_1",
                "start": 0.0,
                "end": 1.0,
                "text": "상태 재사용",
                "speaker": "00",
                "start_frame": 0,
                "end_frame": 30,
                "timeline_start_frame": 0,
                "timeline_end_frame": 30,
                "frame_rate": 30.0,
                "subtitle_review_state": "confirmed",
                "subtitle_status_color": "#34C759",
                "subtitle_status_schema": "subtitle_status.v1",
            }

            with patch("core.project.project_manager.subtitle_status_payload", side_effect=AssertionError("save_project should reuse existing status payload")), \
                 patch("core.project.project_context.subtitle_status_payload", side_effect=AssertionError("build_editor_state should reuse existing status payload")), \
                 patch("core.project.project_context.recheck_threshold", side_effect=AssertionError("build_editor_state should not reload threshold when payload already exists")):
                save_project(
                    str(path),
                    segments=[seg],
                    persist_analysis_artifacts=False,
                    rewrite_stt_reference_tracks=False,
                )

            loaded = load_project(str(path))
            editor_segment = project_segments_to_editor(loaded)[0]
            self.assertEqual(editor_segment["subtitle_review_state"], "confirmed")
            self.assertEqual(editor_segment["subtitle_status_schema"], "subtitle_status.v1")

    def test_save_project_uses_effective_settings_threshold_for_missing_status_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"fake")
            project = {
                "app": "AI Subtitle Studio",
                "version": "test",
                "phase": "PHASE2",
                "timeline": {
                    "total_duration": 2.0,
                    "tracks": [
                        {
                            "clips": [
                                {
                                    "id": "clip_a",
                                    "source_path": str(media),
                                    "timeline_start": 0.0,
                                    "timeline_end": 2.0,
                                    "order": 0,
                                }
                            ]
                        }
                    ],
                },
                "media": [{"order": 0, "path": str(media)}],
                "video": {
                    "schema": PROJECT_VIDEO_SCHEMA,
                    "primary_path": str(media),
                    "media_kind": "video",
                    "duration_sec": 2.0,
                    "primary_fps": 30.0,
                    "frame_duration": 1.0 / 30.0,
                    "total_frames": 60,
                    "width": 1920,
                    "height": 1080,
                    "resolution": "1920x1080",
                    "clip_count": 1,
                    "clips": [
                        {
                            "id": "clip_a",
                            "order": 0,
                            "path": str(media),
                            "type": "video",
                            "duration_sec": 2.0,
                            "fps": 30.0,
                            "frame_count": 60,
                            "width": 1920,
                            "height": 1080,
                            "timeline_start_frame": 0,
                            "timeline_end_frame": 60,
                            "source_start_frame": 0,
                            "source_end_frame": 60,
                        }
                    ],
                },
                "subtitles": {"segments": []},
                "workspace": {},
                "user_settings": {},
            }
            write_project_file(str(path), project)

            seg = {
                "id": "seg_1",
                "start": 0.0,
                "end": 1.0,
                "text": "임계값 1회 계산",
                "speaker": "00",
                "start_frame": 0,
                "end_frame": 30,
                "timeline_start_frame": 0,
                "timeline_end_frame": 30,
                "frame_rate": 30.0,
                "stt_score": 72.0,
            }

            with patch("core.project.project_context.recheck_threshold", side_effect=AssertionError("save path should use effective settings threshold without reloading runtime settings")):
                save_project(
                    str(path),
                    segments=[seg],
                    user_settings={"stt_low_score_recheck_threshold": 61.0},
                    persist_analysis_artifacts=False,
                    rewrite_stt_reference_tracks=False,
                )

    def test_saved_project_writes_video_header_first_and_drops_legacy_runtime_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"fake")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 2.0, "fps": 24.0, "width": 1920, "height": 1080},
            ):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[{"start": 0.0, "end": 0.5, "text": "헤더", "speaker": "00"}],
                )

            raw = project_io.read_project_storage_payload(str(path))

        self.assertEqual(list(raw.keys())[:3], ["video", "app", "version"])
        self.assertNotIn("media", raw)
        self.assertNotIn("frame_timebase", raw)
        self.assertNotIn("frame_timebase", raw.get("editor_state", {}))
        self.assertEqual(raw["video"]["schema"], PROJECT_VIDEO_SCHEMA)
        self.assertEqual(raw["video"]["width"], 1920)
        self.assertEqual(raw["video"]["height"], 1080)
        self.assertEqual(raw["video"]["primary_fps"], 24.0)
        self.assertEqual(raw["storage_schema"], PROJECT_STORAGE_SCHEMA)

    def test_load_project_hydrates_timeline_timebase_from_video_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"fake")
            project = {
                "video": {
                    "schema": PROJECT_VIDEO_SCHEMA,
                    "primary_path": str(media),
                    "media_kind": "video",
                    "duration_sec": 10.0,
                    "primary_fps": 59.94,
                    "frame_duration": 1.0 / 59.94,
                    "total_frames": 599,
                    "width": 1920,
                    "height": 1080,
                    "resolution": "1920x1080",
                    "clip_count": 1,
                    "clips": [
                        {
                            "id": "clip_a",
                            "order": 0,
                            "path": str(media),
                            "type": "video",
                            "duration_sec": 10.0,
                            "fps": 59.94,
                            "frame_count": 599,
                            "width": 1920,
                            "height": 1080,
                            "timeline_start_sec": 0.0,
                            "timeline_end_sec": 10.0,
                            "timeline_start_frame": 0,
                            "timeline_end_frame": 599,
                        }
                    ],
                    "timebase": {
                        "unit": "frame",
                        "canonical_unit": "frame",
                        "mode": "project_video_header",
                        "primary_fps": 59.94,
                        "frame_duration": 1.0 / 59.94,
                        "timeline_start_frame": 0,
                        "timeline_end_frame": 599,
                        "total_frames": 599,
                        "seconds_are_derived": True,
                        "time_fields_are_compatibility": False,
                    },
                },
                "app": "AI Subtitle Studio",
                "version": "04.00.01",
                "phase": "PHASE2",
                "project_name": "header_only",
                "storage_schema": PROJECT_STORAGE_SCHEMA,
                "timeline": {
                    "total_duration": 10.0,
                    "tracks": [
                        {
                            "id": "video_track_0",
                            "type": "video",
                            "clips": [
                                {
                                    "id": "clip_a",
                                    "source_path": str(media),
                                    "type": "video",
                                    "source_duration": 10.0,
                                    "timeline_start": 0.0,
                                    "timeline_end": 10.0,
                                }
                            ],
                        }
                    ],
                },
                "subtitles": {"storage": "vector_canvas", "segment_count": 1},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[str(media)],
                    segments=[
                        {
                            "start": 60.0 / 59.94,
                            "end": 120.0 / 59.94,
                            "text": "헤더 fps",
                            "speaker": "00",
                            "start_frame": 60,
                            "end_frame": 120,
                            "timeline_start_frame": 60,
                            "timeline_end_frame": 120,
                            "frame_rate": 59.94,
                            "timeline_frame_rate": 59.94,
                            "frame_range": {
                                "unit": "frame",
                                "start": 60,
                                "end": 120,
                                "timeline_frame_rate": 59.94,
                            },
                        }
                    ],
                    primary_fps=59.94,
                ),
                "workspace": {},
            }
            path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

            loaded = load_project(str(path))

        self.assertEqual(loaded["timeline"]["timebase"]["primary_fps"], 59.94)
        self.assertEqual(loaded["frame_timebase"]["primary_fps"], 59.94)
        seg = project_segments_to_editor(loaded)[0]
        self.assertAlmostEqual(seg["start"], 60.0 / 59.94, places=4)
        self.assertAlmostEqual(seg["end"], 120.0 / 59.94, places=4)

    def test_save_project_persists_voice_activity_segments_with_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"fake")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 2.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[{"start": 0.0, "end": 0.5, "text": "프레임", "speaker": "00"}],
                    voice_activity_segments=[
                        {
                            "start": 0.5,
                            "end": 1.25,
                            "kind": "llm_selected",
                            "label": "STT2 LLM 82점",
                            "source": "STT2",
                            "color": "#70C149",
                            "score": 82.0,
                            "selection_state": "llm_selected",
                        }
                    ],
                )
            loaded = load_project(str(path))

        voice_segment = loaded["analysis"]["voice_activity_segments"][0]
        self.assertEqual(loaded["analysis"]["voice_activity_schema"], "subtitle_detection.v1")
        self.assertEqual(loaded["analysis"]["voice_activity_timebase"]["primary_fps"], 24.0)
        self.assertEqual(voice_segment["start_frame"], 12)
        self.assertEqual(voice_segment["end_frame"], 30)
        self.assertEqual(voice_segment["score"], 82.0)
        self.assertEqual(voice_segment["selection_state"], "llm_selected")
        self.assertEqual(voice_segment["frame_range"]["unit"], "frame")
        self.assertEqual(voice_segment["frame_range"]["start"], 12)
        editor_voice = loaded["editor_state"]["analysis"]["voice_activity_segments"][0]
        self.assertEqual(loaded["editor_state"]["analysis"]["voice_activity_timebase"]["primary_fps"], 24.0)
        self.assertEqual(editor_voice["start_frame"], 12)
        self.assertEqual(editor_voice["end_frame"], 30)
        restored_voice = project_voice_activity_segments(loaded)[0]
        self.assertEqual(restored_voice["start"], 0.5)
        self.assertEqual(restored_voice["end"], 1.25)
        self.assertEqual(restored_voice["source"], "STT2")
        self.assertEqual(restored_voice["score"], 82.0)

    def test_save_project_persists_multiclip_stt_preview_segments_with_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media_a = Path(tmp) / "a.mp4"
            media_b = Path(tmp) / "b.mp4"
            media_a.write_bytes(b"a")
            media_b.write_bytes(b"b")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 10.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media_a), str(media_b)],
                    segments=[
                        {
                            "start": 10.0,
                            "end": 11.0,
                            "text": "최종",
                            "speaker": "00",
                            "stt_selected_source": "STT2",
                            "stt_candidates": [{"source": "STT2", "text": "후보"}],
                        }
                    ],
                    stt_preview_segments=[
                        {
                            "start": 10.0,
                            "end": 11.0,
                            "text": "후보",
                            "stt_preview_source": "STT2",
                            "stt_preview_sublane": 1,
                            "stt_preview_sublane_count": 2,
                            "_clip_idx": 1,
                            "_clip_file": str(media_b),
                        }
                    ],
                )
            loaded = load_project(str(path))

        segment = project_segments_to_editor(loaded)[0]
        self.assertEqual(segment["stt_selected_source"], "STT2")
        self.assertEqual(segment["stt_candidates"][0]["source"], "STT2")
        preview = project_stt_preview_segments(loaded)[0]
        self.assertEqual(preview["stt_preview_source"], "STT2")
        self.assertEqual(preview["stt_preview_sublane"], 1)
        self.assertEqual(preview["stt_preview_sublane_count"], 2)
        self.assertEqual(preview["_clip_idx"], 1)
        self.assertEqual(preview["start_frame"], 240)
        self.assertEqual(preview["end_frame"], 264)

    def test_add_media_to_project_reuses_existing_segments_for_externalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_a = Path(tmp) / "a.mp4"
            media_b = Path(tmp) / "b.mp4"
            media_a.write_bytes(b"a")
            media_b.write_bytes(b"b")
            srt_path = Path(tmp) / "a.srt"
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n기존\n", encoding="utf-8")
            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 24.0},
            ):
                project_path = create_project(
                    "add_media_reuse",
                    media_paths=[str(media_a)],
                    srt_path=str(srt_path),
                    user_settings={},
                )
            original = project_manager.project_segments_to_editor
            calls = {"count": 0}

            def _counting_segments(*args, **kwargs):
                calls["count"] += 1
                return original(*args, **kwargs)

            with patch("core.project.project_manager.project_segments_to_editor", side_effect=_counting_segments), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 24.0},
            ):
                project_manager.add_media_to_project(str(project_path), [str(media_b)])

        self.assertEqual(calls["count"], 1)

    def test_merge_srt_to_project_reuses_seed_segments_without_project_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "video.mp4"
            media_path.write_bytes(b"video")
            srt_path = media_path.with_suffix(".srt")
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n병합\n", encoding="utf-8")
            with patch("core.project.project_manager.PROJECTS_DIR", tmp), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 24.0},
            ):
                project_path = create_project(
                    "merge_srt_reuse",
                    media_paths=[str(media_path)],
                    user_settings={},
                )
            with patch(
                "core.project.project_manager.project_segments_to_editor",
                side_effect=AssertionError("merge_srt_to_project should reuse prebuilt editor segments"),
            ), patch(
                "core.project.project_manager._get_media_probe",
                return_value={"duration": 10.0, "fps": 24.0},
            ):
                merged = project_manager.merge_srt_to_project(str(project_path))

        self.assertEqual(merged, 1)

    def test_save_project_persists_subtitle_status_and_stt_score_colors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 4.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "미확정",
                            "speaker": "00",
                            "quality": {"confidence_label": "green", "confidence_score": 91},
                            "stt_ensemble_llm_selected_source": "STT1",
                            "stt_candidates": [
                                {
                                    "source": "STT1",
                                    "start": 0.0,
                                    "end": 1.0,
                                    "text": "미확정",
                                    "stt_score": 91,
                                    "stt_score_color": "#52C759",
                                }
                            ],
                        },
                        {
                            "start": 1.0,
                            "end": 2.0,
                            "text": "확정",
                            "speaker": "00",
                            "quality": {
                                "confidence_label": "green",
                                "confidence_score": 99,
                                "manual_confirmed": True,
                                "flags": ["manual_confirmed"],
                            },
                        },
                    ],
                    stt_preview_segments=[
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "미확정",
                            "stt_preview_source": "STT1",
                            "stt_score": 91,
                            "stt_score_color": "#52C759",
                        }
                    ],
                )
            loaded = load_project(str(path))

        first, second = project_segments_to_editor(loaded)
        self.assertEqual(first["subtitle_review_state"], "pending")
        self.assertEqual(first["subtitle_status_color"], "#FFD60A")
        self.assertEqual(first["stt_candidates"][0]["stt_score_color"], "#52C759")
        self.assertEqual(second["subtitle_review_state"], "confirmed")
        self.assertEqual(second["subtitle_status_color"], "#34C759")
        editor_first = project_segments_to_editor(loaded)[0]
        self.assertEqual(editor_first["subtitle_review_state"], "pending")
        preview = project_stt_preview_segments(loaded)[0]
        self.assertEqual(preview["stt_score"], 91)
        self.assertEqual(preview["stt_score_color"], "#52C759")

    def test_save_project_resolves_subtitle_recheck_threshold_once_per_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.aissproj"
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "core.project.project_context.recheck_threshold",
                side_effect=AssertionError("save_project should resolve the threshold from effective settings"),
            ):
                save_project(
                    str(path),
                    segments=[
                        {"start": 0.0, "end": 1.0, "text": "첫 줄", "speaker": "00", "stt_score": 82},
                        {"start": 1.0, "end": 2.0, "text": "둘째 줄", "speaker": "00", "stt_score": 79},
                        {"start": 2.0, "end": 3.0, "text": "셋째 줄", "speaker": "00", "stt_score": 58},
                    ],
                    user_settings={"stt_low_score_recheck_threshold": 60.0},
                    persist_analysis_artifacts=False,
                    rewrite_stt_reference_tracks=False,
                )

    def test_project_save_and_phase1b_enrich_preserve_stt1_stt2_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {
                            "tracks": [
                                {
                                    "clips": [
                                        {
                                            "id": "clip_a",
                                            "source_path": str(media),
                                            "timeline_start": 0.0,
                                            "timeline_end": 10.0,
                                            "order": 0,
                                            "fps": 24.0,
                                        }
                                    ]
                                }
                            ],
                            "timebase": {"primary_fps": 24.0},
                        },
                        "media": [{"order": 0, "path": str(media), "type": "video", "duration": 10.0, "offset": 0.0}],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            final_segment = {
                "id": "seg_a",
                "start": 1.0,
                "end": 2.0,
                "text": "최종 자막",
                "speaker": "00",
                "stt_selected_source": "STT2",
                "stt_candidates": [
                    {"source": "STT1", "start": 1.0, "end": 2.0, "text": "후보 일"},
                    {"source": "STT2", "start": 1.0, "end": 2.0, "text": "후보 이"},
                ],
            }
            save_project(
                str(path),
                segments=[final_segment],
                stt_preview_segments=[
                    {"start": 1.0, "end": 2.0, "text": "후보 일", "stt_preview_source": "STT1"},
                    {"start": 1.0, "end": 2.0, "text": "후보 이", "stt_preview_source": "STT2"},
                ],
            )
            save_project(
                str(path),
                segments=[{"id": "seg_a", "start": 1.0, "end": 2.0, "text": "수정 자막", "speaker": "00"}],
            )
            intermediate = load_project(str(path))
            self.assertEqual(
                {*intermediate["editor_state"]["stt"]["candidate_tracks"].keys()},
                {"STT1", "STT2"},
            )

            owner = SimpleNamespace(
                _multiclip_files=[],
                _multiclip_boundaries=[],
                _project_boundary_times=[],
                _dashboard_mode="dashboard",
                _project_panel_visible=True,
                _current_work_mode="editor",
                _active_clip_idx=0,
                _log_visible=False,
            )
            editor = SimpleNamespace(
                media_path=str(media),
                settings={},
                _current_sec=0.0,
                _active_clip_idx=0,
            )
            enrich_existing_project_file(
                str(path),
                owner,
                editor,
                segments=[{"id": "seg_a", "start": 1.0, "end": 2.0, "text": "수정 자막", "speaker": "00"}],
            )
            loaded = load_project(str(path))

        segment = project_segments_to_editor(loaded)[0]
        self.assertEqual(segment["stt_selected_source"], "STT2")
        self.assertEqual(segment["stt_candidates"][0]["source"], "STT1")
        tracks = loaded["editor_state"]["stt"]["candidate_tracks"]
        self.assertEqual({*tracks.keys()}, {"STT1", "STT2"})
        self.assertEqual(tracks["STT1"][0]["text"], "후보 일")
        self.assertEqual(tracks["STT2"][0]["text"], "후보 이")
        self.assertEqual(loaded["analysis"]["stt_candidate_counts"], {"STT1": 1, "STT2": 1})
        previews = project_stt_preview_segments(loaded)
        self.assertEqual([row["stt_preview_source"] for row in previews], ["STT1", "STT2"])

    def test_cut_boundary_fit_prevents_subtitle_and_stt_preview_crossing(self):
        boundaries = [{"timeline_sec": 3.0, "timeline_frame": 72, "fps": 24.0}]
        segments = [
            {
                "start": 2.0,
                "end": 4.0,
                "text": "컷을 넘는 자막",
                "speaker": "00",
                "stt_candidates": [
                    {"source": "STT1", "start": 2.0, "end": 4.0, "text": "후보"}
                ],
            }
        ]

        split = split_segments_by_cut_boundaries(segments, boundaries, primary_fps=24.0)

        self.assertEqual(len(split), 1)
        self.assertAlmostEqual(split[0]["start"], 3.0)
        self.assertAlmostEqual(split[0]["end"], 4.0)
        self.assertEqual(split[0]["cut_local_start"], 0.0)
        self.assertTrue(split[0]["cut_boundary_fitted"])
        self.assertEqual(split[0]["stt_candidates"][0]["start"], 3.0)

    def test_save_project_can_preserve_existing_stt_reference_assets_without_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            save_project(
                str(path),
                media_paths=[str(media)],
                segments=[{"id": "seg_a", "start": 0.0, "end": 1.0, "text": "최종 자막", "speaker": "00"}],
                stt_preview_segments=[
                    {"start": 0.0, "end": 1.0, "text": "후보 일", "stt_preview_source": "STT1"},
                    {"start": 0.0, "end": 1.0, "text": "후보 이", "stt_preview_source": "STT2"},
                ],
            )

            first_payload = project_io.read_project_storage_payload(str(path))
            stt1_path = path.parent / first_payload["asset_storage"]["tracks"]["stt_stt1"]["path"]
            stt2_path = path.parent / first_payload["asset_storage"]["tracks"]["stt_stt2"]["path"]
            before_stt1 = stt1_path.read_text(encoding="utf-8")
            before_stt2 = stt2_path.read_text(encoding="utf-8")

            with patch("core.project.project_assets.write_srt_track", wraps=write_srt_track) as writer:
                save_project(
                    str(path),
                    segments=[{"id": "seg_a", "start": 0.0, "end": 1.0, "text": "수정 자막", "speaker": "00"}],
                    persist_analysis_artifacts=False,
                    rewrite_stt_reference_tracks=False,
                )

            self.assertEqual([Path(call.args[1]).name for call in writer.call_args_list], ["final.srt"])
            self.assertEqual(stt1_path.read_text(encoding="utf-8"), before_stt1)
            self.assertEqual(stt2_path.read_text(encoding="utf-8"), before_stt2)

            loaded = load_project(str(path))

        tracks = loaded["editor_state"]["stt"]["candidate_tracks"]
        self.assertEqual({*tracks.keys()}, {"STT1", "STT2"})
        self.assertEqual(tracks["STT1"][0]["text"], "후보 일")
        self.assertEqual(tracks["STT2"][0]["text"], "후보 이")

    def test_save_project_skips_existing_editor_roundtrip_when_segments_already_carry_stt_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            save_project(
                str(path),
                media_paths=[str(media)],
                segments=[{"id": "seg_a", "start": 0.0, "end": 1.0, "text": "최종 자막", "speaker": "00"}],
                stt_preview_segments=[
                    {"start": 0.0, "end": 1.0, "text": "후보 일", "stt_preview_source": "STT1"},
                    {"start": 0.0, "end": 1.0, "text": "후보 이", "stt_preview_source": "STT2"},
                ],
            )

            loaded = load_project(str(path))
            rich_segments = project_segments_to_editor(loaded)
            rich_segments[0]["text"] = "수정 자막"

            with patch(
                "core.project.project_manager.project_segments_to_editor",
                side_effect=AssertionError("segments with persisted STT metadata should skip project roundtrip"),
            ):
                save_project(
                    str(path),
                    segments=rich_segments,
                    persist_analysis_artifacts=False,
                    rewrite_stt_reference_tracks=False,
                )

            reloaded = load_project(str(path))

        restored = project_segments_to_editor(reloaded)
        self.assertEqual(restored[0]["text"], "수정 자막")
        self.assertTrue(restored[0]["stt_candidates"])
        self.assertEqual({*reloaded["editor_state"]["stt"]["candidate_tracks"].keys()}, {"STT1", "STT2"})

    def test_save_project_reuses_existing_editor_roundtrip_when_segments_are_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            save_project(
                str(path),
                media_paths=[str(media)],
                segments=[{"id": "seg_a", "start": 0.0, "end": 1.0, "text": "최종 자막", "speaker": "00"}],
                stt_preview_segments=[
                    {"start": 0.0, "end": 1.0, "text": "후보 일", "stt_preview_source": "STT1"},
                    {"start": 0.0, "end": 1.0, "text": "후보 이", "stt_preview_source": "STT2"},
                ],
            )

            with patch(
                "core.project.project_manager.project_segments_to_editor",
                wraps=project_manager.project_segments_to_editor,
            ) as roundtrip:
                save_project(
                    str(path),
                    segments=[{"id": "seg_a", "start": 0.0, "end": 1.0, "text": "수정 자막", "speaker": "00"}],
                    persist_analysis_artifacts=False,
                    rewrite_stt_reference_tracks=False,
                )

        roundtrip.assert_called_once()

    def test_save_project_reuses_existing_editor_roundtrip_when_segments_only_carry_status_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            save_project(
                str(path),
                media_paths=[str(media)],
                segments=[{"id": "seg_a", "start": 0.0, "end": 1.0, "text": "최종 자막", "speaker": "00"}],
                stt_preview_segments=[
                    {"start": 0.0, "end": 1.0, "text": "후보 일", "stt_preview_source": "STT1"},
                    {"start": 0.0, "end": 1.0, "text": "후보 이", "stt_preview_source": "STT2"},
                ],
            )

            status_only_segments = [
                {
                    "id": "seg_a",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "수정 자막",
                    "speaker": "00",
                    "score": 91.0,
                    "subtitle_status_schema": "subtitle_status.v1",
                }
            ]

            with patch(
                "core.project.project_manager.project_segments_to_editor",
                wraps=project_manager.project_segments_to_editor,
            ) as roundtrip:
                save_project(
                    str(path),
                    segments=status_only_segments,
                    persist_analysis_artifacts=False,
                    rewrite_stt_reference_tracks=False,
                )

            reloaded = load_project(str(path))

        roundtrip.assert_called_once()
        restored = project_segments_to_editor(reloaded)
        self.assertTrue(restored[0]["stt_candidates"])

    def test_save_project_persists_cut_boundaries_to_project_and_multiclip_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media_a = Path(tmp) / "a.mp4"
            media_b = Path(tmp) / "b.mp4"
            media_a.write_bytes(b"a")
            media_b.write_bytes(b"b")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "analysis": {
                            "cut_boundary_schema": "cut_boundaries.v1",
                            "cut_boundaries": [
                                {"timeline_sec": 3.0, "timeline_frame": 72, "fps": 24.0}
                            ],
                            "cut_boundary_provisional_schema": "cut_boundaries.provisional.v1",
                            "cut_boundary_provisional_boundaries": [
                                {"timeline_sec": 2.9, "timeline_frame": 70, "fps": 24.0, "status": "provisional"}
                            ],
                        },
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 10.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media_a), str(media_b)],
                    user_settings={"cut_boundary_detection_enabled": True},
                    segments=[{"start": 2.0, "end": 4.0, "text": "분할", "speaker": "00"}],
                    stt_preview_segments=[
                        {"start": 2.5, "end": 3.5, "text": "후보", "stt_preview_source": "STT1"}
                    ],
                )
            loaded = load_project(str(path))

        cut_rows = project_cut_boundary_segments(loaded)
        self.assertEqual(len(cut_rows), 1)
        provisional_rows = project_cut_boundary_provisional_segments(loaded)
        self.assertEqual(len(provisional_rows), 1)
        self.assertTrue(loaded["analysis"]["cut_boundary_settings"]["absolute"])
        self.assertEqual(len(loaded["editor_state"]["multiclip"]["cut_boundaries"]), 1)
        self.assertEqual(len(loaded["editor_state"]["multiclip"]["cut_boundary_provisional_boundaries"]), 1)
        subtitles = project_segments_to_editor(loaded)
        self.assertEqual(len(subtitles), 1)
        self.assertAlmostEqual(subtitles[0]["start"], 3.0, places=6)
        previews = project_stt_preview_segments(loaded)
        self.assertEqual(len(previews), 1)
        self.assertAlmostEqual(previews[0]["start"], 2.5, places=6)
        self.assertAlmostEqual(previews[0]["end"], 3.5, places=6)

    def test_project_segments_to_editor_prefers_saved_frame_numbers(self):
        project = {
            "timeline": {
                "timebase": {"unit": "frame", "primary_fps": 24.0},
                "tracks": [{"clips": []}],
            },
            "subtitles": {
                "segments": [
                    {
                        "start": 1.01,
                        "end": 1.54,
                        "start_frame": 24,
                        "end_frame": 36,
                        "text": "프레임 우선",
                        "speaker": "00",
                    }
                ]
            },
        }

        segment = project_segments_to_editor(project)[0]

        self.assertAlmostEqual(segment["start"], 1.0, places=6)
        self.assertAlmostEqual(segment["end"], 1.5, places=6)
        self.assertEqual(segment["start_frame"], 24)
        self.assertEqual(segment["end_frame"], 36)

    def test_save_project_uses_frame_numbers_as_source_of_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"fake")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 2.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[
                        {
                            "start": 1.01,
                            "end": 1.54,
                            "start_frame": 24,
                            "end_frame": 36,
                            "text": "프레임 저장",
                            "speaker": "00",
                        }
                    ],
                )
            loaded = load_project(str(path))

        segment = project_segments_to_editor(loaded)[0]
        self.assertEqual(segment["start_frame"], 24)
        self.assertEqual(segment["end_frame"], 36)
        self.assertAlmostEqual(segment["start"], 1.0, places=6)
        self.assertAlmostEqual(segment["end"], 1.5, places=6)

    def test_multiclip_timeline_frames_use_primary_project_fps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media_a = Path(tmp) / "a.mp4"
            media_b = Path(tmp) / "b.mp4"
            media_a.write_bytes(b"a")
            media_b.write_bytes(b"b")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def _probe(path_str):
                return {"duration": 2.0, "fps": 24.0} if path_str == str(media_a) else {"duration": 3.0, "fps": 30.0}

            with patch("core.project.project_manager.probe_media", side_effect=_probe):
                save_project(
                    str(path),
                    media_paths=[str(media_a), str(media_b)],
                    segments=[{"start": 2.0, "end": 3.0, "text": "둘째", "speaker": "00"}],
                )
            loaded = load_project(str(path))

        clip_a, clip_b = loaded["timeline"]["tracks"][0]["clips"]
        self.assertEqual(loaded["timeline"]["timebase"]["primary_fps"], 24.0)
        self.assertEqual(clip_a["timeline_start_frame"], 0)
        self.assertEqual(clip_a["timeline_end_frame"], 48)
        self.assertEqual(clip_b["timeline_start_frame"], 48)
        self.assertEqual(clip_b["timeline_end_frame"], 120)
        self.assertEqual(clip_b["source_frame_count"], 90)
        segment = project_segments_to_editor(loaded)[0]
        self.assertEqual(segment["start_frame"], 48)
        self.assertEqual(segment["end_frame"], 72)
        self.assertEqual(segment["clip_local_start_frame"], 0)
        self.assertEqual(segment["clip_local_end_frame"], 30)

    def test_save_project_externalizes_subtitles_and_stt_tracks_to_srt_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 4.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "최종 자막",
                            "speaker": "00",
                            "stt_selected_source": "STT2",
                            "stt_candidates": [
                                {"source": "STT1", "start": 0.0, "end": 1.0, "text": "후보 하나"},
                                {"source": "STT2", "start": 0.0, "end": 1.0, "text": "후보 둘"},
                            ],
                        }
                    ],
                    stt_preview_segments=[
                        {"start": 0.0, "end": 1.0, "text": "후보 하나", "stt_preview_source": "STT1"},
                        {"start": 0.0, "end": 1.0, "text": "후보 둘", "stt_preview_source": "STT2"},
                    ],
                )

            raw_payload = project_io.read_project_storage_payload(str(path))
            final_srt = path.parent / raw_payload["subtitles"]["srt_path"]
            stt1_srt = path.parent / raw_payload["asset_storage"]["tracks"]["stt_stt1"]["path"]
            stt2_srt = path.parent / raw_payload["asset_storage"]["tracks"]["stt_stt2"]["path"]
            final_meta = raw_payload["asset_storage"]["tracks"]["final"]["metadata"][0]
            stt1_meta = raw_payload["asset_storage"]["tracks"]["stt_stt1"]["metadata"][0]

            self.assertEqual(raw_payload["subtitles"]["storage"], "external_srt")
            self.assertEqual(raw_payload["asset_storage"]["timebase"]["unit"], "frame")
            self.assertEqual(raw_payload["asset_storage"]["timebase"]["srt_quantization"], "frame_grid_to_srt_millisecond")
            self.assertEqual(raw_payload["asset_storage"]["tracks"]["final"]["timebase"]["unit"], "frame")
            self.assertEqual(raw_payload["editor_state"]["rendering"]["subtitle_canvas"]["segments"], [])
            self.assertEqual(raw_payload["editor_state"]["stt"]["candidate_tracks"], {})
            self.assertNotIn("stt_candidate_tracks", raw_payload["analysis"])
            self.assertTrue(final_srt.exists())
            self.assertTrue(stt1_srt.exists())
            self.assertTrue(stt2_srt.exists())
            self.assertIn("최종 자막", final_srt.read_text(encoding="utf-8"))
            self.assertNotIn("후보 하나", json.dumps(raw_payload, ensure_ascii=False))
            self.assertEqual((final_meta["start_frame"], final_meta["end_frame"]), (0, 24))
            self.assertEqual((stt1_meta["start_frame"], stt1_meta["end_frame"]), (0, 24))
            self.assertEqual(
                (
                    stt1_meta["_stt_original_candidate_start_frame"],
                    stt1_meta["_stt_original_candidate_end_frame"],
                ),
                (0, 24),
            )
            self.assertNotIn("_stt_original_candidate_start", stt1_meta)
            self.assertNotIn("_stt_original_candidate_end", stt1_meta)

            loaded = load_project(str(path))
            segment = project_segments_to_editor(loaded)[0]
            previews = project_stt_preview_segments(loaded)

        self.assertEqual(segment["text"], "최종 자막")
        self.assertEqual([candidate["source"] for candidate in segment["stt_candidates"]], ["STT1", "STT2"])
        self.assertEqual([row["text"] for row in previews], ["후보 하나", "후보 둘"])

    def test_externalized_final_subtitles_restore_selected_stt_anchor_from_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.aissproj"
            project = {
                "project_name": "selected-stt-anchor",
                "project_path": str(path),
                "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=[],
                    primary_fps=30.0,
                ),
            }

            externalize_project_text_assets(
                str(path),
                project,
                final_segments=[
                    {
                        "id": "seg-1",
                        "start": 1.0,
                        "end": 2.0,
                        "text": "최종 자막",
                        "speaker": "00",
                        "stt_selected_source": "STT2",
                        "_stt_original_candidate_start": 0.8,
                        "_stt_original_candidate_end": 2.2,
                    }
                ],
                stt_tracks={},
            )
            write_project_file(str(path), project)
            clear_project_file_cache(str(path))

            loaded = load_project(str(path), hydrate_text_assets=False)
            segment = project_segments_to_editor(loaded, include_analysis_candidates=False)[0]

        self.assertEqual(segment["stt_selected_source"], "STT2")
        self.assertAlmostEqual(segment["_stt_original_candidate_start"], 0.8, places=3)
        self.assertAlmostEqual(segment["_stt_original_candidate_end"], 2.2, places=3)
        self.assertEqual(
            (
                segment["_stt_original_candidate_start_frame"],
                segment["_stt_original_candidate_end_frame"],
            ),
            (24, 66),
        )

    def test_external_stt_assets_preserve_distinct_overlapping_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            project = {
                "project_name": "stt-overlap",
                "project_path": str(path),
                "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=[],
                    stt_preview_segments=[
                        {"start": 0.0, "end": 1.0, "text": "첫 후보", "stt_preview_source": "STT1", "stt_score": 92.0},
                        {"start": 0.1, "end": 0.9, "text": "첫 후보", "stt_preview_source": "STT1", "stt_score": 60.0},
                        {"start": 0.98, "end": 2.0, "text": "둘 후보", "stt_preview_source": "STT1", "stt_score": 91.0},
                        {"start": 1.2, "end": 1.8, "text": "둘 후보", "stt_preview_source": "STT1", "stt_score": 55.0},
                        {"start": 0.5, "end": 1.4, "text": "겹친 다른 후보", "stt_preview_source": "STT1", "stt_score": 89.0},
                        {"start": 0.0, "end": 1.0, "text": "다른 후보", "stt_preview_source": "STT2", "stt_score": 90.0},
                    ],
                    primary_fps=30.0,
                ),
            }

            externalize_project_text_assets(
                str(path),
                project,
                final_segments=[],
                stt_tracks=(project["editor_state"]["stt"]["candidate_tracks"]),
            )
            raw_payload = json.loads(json.dumps(project, ensure_ascii=False))
            stt1_srt = path.parent / raw_payload["asset_storage"]["tracks"]["stt_stt1"]["path"]
            stt1_rows = parse_srt_to_segments(str(stt1_srt))
            loaded_previews = project_stt_preview_segments(raw_payload)
            stt1_previews = [row for row in loaded_previews if row.get("stt_preview_source") == "STT1"]

        self.assertEqual([row["text"] for row in stt1_rows], ["첫 후보", "겹친 다른 후보", "둘 후보"])
        self.assertGreater(stt1_rows[0]["end"], stt1_rows[1]["start"])
        self.assertEqual([row["text"] for row in stt1_previews], ["첫 후보", "겹친 다른 후보", "둘 후보"])
        self.assertGreater(stt1_previews[0]["end"], stt1_previews[1]["start"])

    def test_external_stt_assets_strip_whisper_control_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            project = {
                "project_name": "stt-clean",
                "project_path": str(path),
                "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=[],
                    stt_preview_segments=[
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "<|startoftranscript|><|ko|><|transcribe|><|400|> 오늘은 여기<|900|>",
                            "stt_preview_source": "STT1",
                        },
                        {
                            "start": 1.0,
                            "end": 2.0,
                            "text": "<|1200|><|1300|>",
                            "stt_preview_source": "STT1",
                        },
                    ],
                    primary_fps=30.0,
                ),
            }

            externalize_project_text_assets(
                str(path),
                project,
                final_segments=[
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "<|400|> 최종 자막<|900|>",
                    }
                ],
                stt_tracks=project["editor_state"]["stt"]["candidate_tracks"],
            )
            raw_payload = json.loads(json.dumps(project, ensure_ascii=False))
            final_srt = path.parent / raw_payload["subtitles"]["srt_path"]
            stt1_srt = path.parent / raw_payload["asset_storage"]["tracks"]["stt_stt1"]["path"]
            stt1_rows = parse_srt_to_segments(str(stt1_srt))
            previews = project_stt_preview_segments(raw_payload)
            final_text = final_srt.read_text(encoding="utf-8")
            stt1_text = stt1_srt.read_text(encoding="utf-8")

        self.assertEqual(final_text.count("<|"), 0)
        self.assertEqual(stt1_text.count("<|"), 0)
        self.assertEqual([row["text"] for row in stt1_rows], ["오늘은 여기"])
        self.assertEqual([row["text"] for row in previews], ["오늘은 여기"])

    def test_project_repeated_save_preserves_overlapping_stt_preview_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            previews = [
                {"start": 0.0, "end": 1.0, "text": "STT1 앞", "stt_preview_source": "STT1"},
                {"start": 0.5, "end": 1.5, "text": "STT1 중간", "stt_preview_source": "STT1"},
                {"start": 1.4, "end": 2.0, "text": "STT1 뒤", "stt_preview_source": "STT1"},
                {"start": 0.0, "end": 2.0, "text": "STT2 전체", "stt_preview_source": "STT2"},
            ]
            with patch("core.project.project_manager.probe_media", return_value={"duration": 4.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[{"start": 0.0, "end": 2.0, "text": "최종", "speaker": "00"}],
                    stt_preview_segments=previews,
                )
            first = load_project(str(path))
            first_previews = project_stt_preview_segments(first)
            save_project(
                str(path),
                segments=project_segments_to_editor(first),
                stt_preview_segments=first_previews,
            )
            second = load_project(str(path))
            second_previews = project_stt_preview_segments(second)

        self.assertEqual([row["text"] for row in first_previews], [row["text"] for row in previews])
        self.assertEqual([row["text"] for row in second_previews], [row["text"] for row in previews])

    def test_project_save_keeps_raw_stt_preview_timing_even_when_cut_boundaries_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {},
                        "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
                        "media": [],
                        "subtitles": {"segments": []},
                        "analysis": {
                            "cut_boundaries": [
                                {"timeline_sec": 1.0, "timeline_frame": 24, "fps": 24.0}
                            ]
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            previews = [
                {"start": 0.0, "end": 1.0, "text": "STT1 앞", "stt_preview_source": "STT1"},
                {"start": 0.5, "end": 1.5, "text": "STT1 중간", "stt_preview_source": "STT1"},
                {"start": 1.4, "end": 2.0, "text": "STT1 뒤", "stt_preview_source": "STT1"},
                {"start": 0.0, "end": 2.0, "text": "STT2 전체", "stt_preview_source": "STT2"},
            ]
            with patch("core.project.project_manager.probe_media", return_value={"duration": 4.0, "fps": 24.0}):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[{"start": 0.0, "end": 2.0, "text": "최종", "speaker": "00"}],
                    stt_preview_segments=previews,
                )
            first = load_project(str(path))
            first_previews = project_stt_preview_segments(first)
            save_project(
                str(path),
                segments=project_segments_to_editor(first),
                stt_preview_segments=first_previews,
            )
            second = load_project(str(path))
            second_previews = project_stt_preview_segments(second)

        expected = [
            ("STT1", "STT1 앞", 0.0, 1.0, 0, 24),
            ("STT1", "STT1 중간", 0.5, 1.5, 12, 36),
            ("STT1", "STT1 뒤", 34.0 / 24.0, 2.0, 34, 48),
            ("STT2", "STT2 전체", 0.0, 2.0, 0, 48),
        ]
        self.assertEqual(
            [
                (
                    row["stt_preview_source"],
                    row["text"],
                    row["start"],
                    row["end"],
                    row["start_frame"],
                    row["end_frame"],
                )
                for row in first_previews
            ],
            expected,
        )
        self.assertEqual(
            [
                (
                    row["stt_preview_source"],
                    row["text"],
                    row["start"],
                    row["end"],
                    row["start_frame"],
                    row["end_frame"],
                )
                for row in second_previews
            ],
            expected,
        )
        stt2_rows = [row for row in second_previews if row["stt_preview_source"] == "STT2"]
        self.assertEqual(len(stt2_rows), 1)
        self.assertEqual((stt2_rows[0]["start_frame"], stt2_rows[0]["end_frame"]), (0, 48))
        stt1_tail = next(row for row in second_previews if row["text"] == "STT1 뒤")
        self.assertEqual(
            (
                stt1_tail["_stt_original_candidate_start_frame"],
                stt1_tail["_stt_original_candidate_end_frame"],
            ),
            (34, 48),
        )

    def test_project_open_can_skip_heavy_external_candidate_hydration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            project = {
                "project_name": "lazy-open",
                "project_path": str(path),
                "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=[],
                    primary_fps=30.0,
                ),
            }
            externalize_project_text_assets(
                str(path),
                project,
                final_segments=[{"id": "seg-1", "start": 0.0, "end": 1.0, "text": "최종", "speaker": "00"}],
                stt_tracks={"STT1": [{"start": 0.0, "end": 1.0, "text": "후보", "stt_score": 91.0}]},
            )
            path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

            lazy_loaded = load_project(str(path), hydrate_text_assets=False)
            lazy_segments = project_segments_to_editor(lazy_loaded, include_analysis_candidates=False)
            lazy_had_stt_cache = "_external_stt_tracks_cache" in lazy_loaded
            lazy_candidate_tracks = dict(((lazy_loaded.get("editor_state", {}) or {}).get("stt", {}) or {}).get("candidate_tracks") or {})
            eager_loaded = load_project(str(path), hydrate_text_assets=True)
            eager_segments = project_segments_to_editor(eager_loaded)

        self.assertFalse(lazy_had_stt_cache)
        self.assertEqual(lazy_candidate_tracks, {})
        self.assertEqual(lazy_segments[0]["text"], "최종")
        self.assertNotIn("stt_candidates", lazy_segments[0])
        self.assertIn("_external_stt_tracks_cache", eager_loaded)
        self.assertEqual(eager_segments[0]["stt_candidates"][0]["text"], "후보")

    def test_project_open_reuses_hot_text_caches_after_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            project = {
                "project_name": "hot-open",
                "project_path": str(path),
                "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=[],
                    primary_fps=30.0,
                ),
            }
            externalize_project_text_assets(
                str(path),
                project,
                final_segments=[{"id": "seg-1", "start": 0.0, "end": 1.0, "text": "즉시 열기", "speaker": "00"}],
                stt_tracks={"STT1": [{"start": 0.0, "end": 1.0, "text": "미리보기", "stt_score": 91.0}]},
            )
            project["_hot_open_stt_preview_segments_cache"] = [
                {"start": 0.0, "end": 1.0, "text": "미리보기", "stt_preview_source": "STT1"}
            ]
            write_project_file(str(path), project)

            lazy_loaded = load_project(str(path), hydrate_text_assets=False)
            with patch("core.project.project_assets.parse_srt_to_segments", side_effect=AssertionError("should not parse srt")):
                lazy_segments = project_segments_to_editor(lazy_loaded, include_analysis_candidates=False)
                lazy_previews = project_stt_preview_segments(lazy_loaded)

        self.assertEqual(lazy_segments[0]["text"], "즉시 열기")
        self.assertEqual(lazy_previews[0]["text"], "미리보기")
        self.assertEqual(lazy_previews[0]["stt_preview_source"], "STT1")

    def test_hydrate_project_text_asset_cache_keeps_editor_tracks_independent_from_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            project = {
                "project_name": "cache-alias-safe",
                "project_path": str(path),
                "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=[],
                    primary_fps=30.0,
                ),
            }
            externalize_project_text_assets(
                str(path),
                project,
                final_segments=[{"id": "seg-1", "start": 0.0, "end": 1.0, "text": "최종", "speaker": "00"}],
                stt_tracks={"STT1": [{"start": 0.0, "end": 1.0, "text": "후보", "stt_score": 91.0}]},
            )

            hydrate_project_text_asset_cache(project)
            project["_external_stt_tracks_cache"]["STT1"][0]["text"] = "캐시 변경"

        self.assertEqual(project["editor_state"]["stt"]["candidate_tracks"]["STT1"][0]["text"], "후보")

    def test_write_project_file_strips_external_runtime_views_without_mutating_loaded_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            project = {
                "project_name": "runtime-external",
                "project_path": str(path),
                "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=[],
                    primary_fps=30.0,
                ),
            }
            externalize_project_text_assets(
                str(path),
                project,
                final_segments=[{"id": "seg-1", "start": 0.0, "end": 1.0, "text": "최종", "speaker": "00"}],
                stt_tracks={"STT1": [{"start": 0.0, "end": 1.0, "text": "후보", "stt_score": 91.0}]},
            )
            hydrate_project_text_asset_cache(project)
            project["editor_state"]["rendering"]["subtitle_canvas"]["segments"] = [
                {"start": 0.0, "end": 1.0, "text": "런타임 자막", "speaker": "00"}
            ]
            project["editor_state"]["stt"]["preview_segments"] = [
                {"start": 0.0, "end": 1.0, "text": "런타임 후보", "stt_preview_source": "STT1"}
            ]
            project["editor_state"].setdefault("analysis", {})["stt_candidate_tracks"] = {
                "STT1": [{"start": 0.0, "end": 1.0, "text": "런타임 후보"}]
            }
            project.setdefault("analysis", {})["stt_candidate_tracks"] = {
                "STT1": [{"start": 0.0, "end": 1.0, "text": "런타임 후보"}]
            }

            write_project_file(str(path), project)
            raw_payload = project_io.read_project_storage_payload(str(path))

        self.assertEqual(project["editor_state"]["rendering"]["subtitle_canvas"]["segments"][0]["text"], "런타임 자막")
        self.assertEqual(project["editor_state"]["stt"]["preview_segments"][0]["text"], "런타임 후보")
        self.assertEqual(project["editor_state"]["stt"]["candidate_tracks"]["STT1"][0]["text"], "후보")
        self.assertEqual(raw_payload["editor_state"]["rendering"]["subtitle_canvas"]["segments"], [])
        self.assertEqual(raw_payload["editor_state"]["stt"]["preview_segments"], [])
        self.assertEqual(raw_payload["editor_state"]["stt"]["candidate_tracks"], {})
        self.assertNotIn("stt_candidate_tracks", raw_payload["editor_state"]["analysis"])
        self.assertNotIn("stt_candidate_tracks", raw_payload["analysis"])

    def test_externalized_project_roundtrip_preserves_gap_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.aissproj"
            segments = [
                {"id": "seg-1", "start": 0.0, "end": 1.0, "text": "앞 자막", "speaker": "00"},
                {"id": "gap-1", "start": 1.0, "end": 2.0, "text": "", "speaker": "00", "is_gap": True},
                {"id": "seg-2", "start": 2.0, "end": 3.0, "text": "뒤 자막", "speaker": "00"},
            ]
            project = {
                "project_name": "gap-roundtrip",
                "project_path": str(path),
                "timeline": {
                    "timebase": {"primary_fps": 30.0},
                    "tracks": [{"clips": []}],
                },
                "editor_state": build_editor_state(
                    mode="single",
                    media_files=[],
                    segments=segments,
                    primary_fps=30.0,
                ),
            }
            externalize_project_text_assets(
                str(path),
                project,
                final_segments=segments,
                stt_tracks={},
            )
            write_project_file(str(path), project)
            raw_payload = project_io.read_project_storage_payload(str(path))
            payload = read_project_file(str(path))

        self.assertEqual(raw_payload["editor_state"]["rendering"]["subtitle_canvas"]["segments"], [])
        self.assertEqual(len(raw_payload["editor_state"]["rendering"]["subtitle_canvas"]["gap_segments"]), 1)
        self.assertEqual(
            raw_payload["editor_state"]["rendering"]["subtitle_canvas"]["gap_segments"][0]["time"]["start_frame"],
            30,
        )
        restored = project_segments_to_editor(payload, include_analysis_candidates=False)
        self.assertEqual([bool(seg.get("is_gap")) for seg in restored], [False, True, False])
        self.assertEqual([seg.get("text", "") for seg in restored], ["앞 자막", "", "뒤 자막"])

    def test_project_open_recovers_sibling_external_srt_assets_when_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            asset_dir = path.parent / "project.assets" / "subtitles"
            asset_dir.mkdir(parents=True, exist_ok=True)
            (asset_dir / "final.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n최종 자막\n\n",
                encoding="utf-8",
            )
            (asset_dir / "stt1.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nSTT1 후보\n\n",
                encoding="utf-8",
            )
            (asset_dir / "stt2.srt").write_text(
                "1\n00:00:00,500 --> 00:00:01,500\nSTT2 후보\n\n",
                encoding="utf-8",
            )
            path.write_text(
                json.dumps(
                    {
                        "project_name": "recover-assets",
                        "project_path": str(path),
                        "timeline": {
                            "total_duration": 2.0,
                            "timebase": {"primary_fps": 30.0},
                            "tracks": [{"clips": [{"timeline_start": 0.0, "timeline_end": 2.0, "fps": 30.0}]}],
                        },
                        "media": [{"path": str(path.parent / "clip.mp4"), "duration": 2.0, "offset": 0.0}],
                        "subtitles": {"storage": "editor_state.rendering.subtitle_canvas", "segment_count": 0},
                        "editor_state": build_editor_state(mode="single", media_files=[], segments=[], primary_fps=30.0),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            loaded = load_project(str(path), hydrate_text_assets=False)
            segments = project_segments_to_editor(loaded, include_analysis_candidates=False)
            previews = project_stt_preview_segments(loaded)

        self.assertEqual([row["text"] for row in segments], ["최종 자막"])
        self.assertEqual([row["text"] for row in previews], ["STT1 후보", "STT2 후보"])

    def test_save_project_restores_external_asset_manifest_from_sibling_assets_when_segments_are_temporarily_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            asset_dir = path.parent / "project.assets" / "subtitles"
            asset_dir.mkdir(parents=True, exist_ok=True)
            (asset_dir / "final.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n최종 자막\n\n",
                encoding="utf-8",
            )
            (asset_dir / "stt1.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nSTT1 후보\n\n",
                encoding="utf-8",
            )
            (asset_dir / "stt2.srt").write_text(
                "1\n00:00:00,500 --> 00:00:01,500\nSTT2 후보\n\n",
                encoding="utf-8",
            )
            path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "project_path": str(path),
                        "workspace": {},
                        "timeline": {
                            "total_duration": 2.0,
                            "timebase": {"primary_fps": 30.0},
                            "tracks": [{"clips": [{"timeline_start": 0.0, "timeline_end": 2.0, "fps": 30.0, "source_path": str(media)}]}],
                        },
                        "media": [{"path": str(media), "duration": 2.0, "offset": 0.0}],
                        "subtitles": {"storage": "editor_state.rendering.subtitle_canvas", "segment_count": 0},
                        "editor_state": build_editor_state(mode="single", media_files=[str(media)], segments=[], primary_fps=30.0),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.project.project_manager.probe_media", return_value={"duration": 2.0, "fps": 30.0}):
                save_project(str(path), media_paths=[str(media)], segments=[])

            repaired = load_project(str(path), hydrate_text_assets=False)
            raw_payload = project_io.read_project_storage_payload(str(path))

        self.assertEqual(raw_payload["subtitles"]["storage"], PROJECT_EXTERNAL_STORAGE)
        self.assertIn("asset_storage", raw_payload)
        self.assertIn("final", raw_payload["asset_storage"]["tracks"])
        self.assertIn("stt_stt1", raw_payload["asset_storage"]["tracks"])
        self.assertIn("stt_stt2", raw_payload["asset_storage"]["tracks"])
        self.assertEqual([row["text"] for row in project_segments_to_editor(repaired, include_analysis_candidates=False)], ["최종 자막"])

    def test_save_project_can_intentionally_clear_external_assets_for_full_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"video")
            project = {
                "app": "AI Subtitle Studio",
                "version": "03.00.25",
                "project_path": str(path),
                "workspace": {},
                "timeline": {
                    "total_duration": 2.0,
                    "timebase": {"primary_fps": 30.0},
                    "tracks": [{"clips": [{"timeline_start": 0.0, "timeline_end": 2.0, "fps": 30.0, "source_path": str(media)}]}],
                },
                "media": [{"path": str(media), "duration": 2.0, "offset": 0.0}],
                "editor_state": build_editor_state(mode="single", media_files=[str(media)], segments=[], primary_fps=30.0),
            }
            externalize_project_text_assets(
                str(path),
                project,
                final_segments=[{"start": 0.0, "end": 1.0, "text": "이전 자막"}],
                stt_tracks={
                    "STT1": [{"start": 0.0, "end": 1.0, "text": "이전 후보 1", "stt_preview_source": "STT1"}],
                    "STT2": [{"start": 0.0, "end": 1.0, "text": "이전 후보 2", "stt_preview_source": "STT2"}],
                },
            )
            write_project_file(str(path), project)
            final_srt = path.parent / "project.assets" / "subtitles" / "final.srt"
            stt1_srt = path.parent / "project.assets" / "subtitles" / "stt1.srt"
            stt2_srt = path.parent / "project.assets" / "subtitles" / "stt2.srt"
            self.assertTrue(final_srt.exists())

            with patch("core.project.project_manager.probe_media", return_value={"duration": 2.0, "fps": 30.0}):
                save_project(
                    str(path),
                    media_paths=[str(media)],
                    segments=[],
                    stt_preview_segments=[],
                    recover_external_assets_on_empty=False,
                )

            clear_project_file_cache(str(path))
            raw_payload = project_io.read_project_storage_payload(str(path))
            loaded = load_project(str(path), hydrate_text_assets=False)

        self.assertEqual(raw_payload["subtitles"]["storage"], "editor_state.rendering.subtitle_canvas")
        self.assertEqual(raw_payload["subtitles"]["segment_count"], 0)
        self.assertNotIn("asset_storage", raw_payload)
        self.assertFalse(final_srt.exists())
        self.assertFalse(stt1_srt.exists())
        self.assertFalse(stt2_srt.exists())
        self.assertEqual(project_segments_to_editor(loaded, include_analysis_candidates=False), [])
        self.assertEqual(project_stt_preview_segments(loaded), [])

    def test_project_open_discards_hot_open_segments_beyond_media_duration(self):
        project = {
            "project_path": "/tmp/project.json",
            "timeline": {
                "total_duration": 10.0,
                "timebase": {"primary_fps": 30.0},
                "tracks": [{"clips": [{"timeline_start": 0.0, "timeline_end": 10.0, "fps": 30.0}]}],
            },
            "_hot_open_subtitle_segments_cache": [
                {"start": 1.0, "end": 2.0, "text": "정상", "speaker": "00"},
                {"start": 2800.0, "end": 2810.0, "text": "stale", "speaker": "00"},
            ],
            "_hot_open_stt_preview_segments_cache": [
                {"start": 0.0, "end": 1.0, "text": "STT1", "stt_preview_source": "STT1"},
                {"start": 2900.0, "end": 2910.0, "text": "stale-preview", "stt_preview_source": "STT2"},
            ],
        }

        segments = project_segments_to_editor(project, include_analysis_candidates=False)
        previews = project_stt_preview_segments(project)

        self.assertEqual([row["text"] for row in segments], ["정상"])
        self.assertEqual([row["text"] for row in previews], ["STT1"])

    def test_project_segments_to_editor_reuses_persisted_subtitle_status(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "subtitles": {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "저장된 상태",
                        "speaker": "00",
                        "subtitle_review_state": "confirmed",
                        "subtitle_status_color": "#34C759",
                        "subtitle_status_schema": "subtitle_status.v1",
                        "subtitle_status_score": 0.99,
                        "subtitle_status_source": "user",
                    }
                ]
            },
        }

        with patch("core.project.project_context.subtitle_status_payload", side_effect=AssertionError("should not recompute")):
            segment = project_segments_to_editor(project)[0]

        self.assertEqual(segment["subtitle_review_state"], "confirmed")
        self.assertEqual(segment["subtitle_status_color"], "#34C759")
        self.assertEqual(segment["subtitle_status_source"], "user")

    def test_project_stt_preview_segments_reuses_persisted_subtitle_status(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "editor_state": {
                "stt": {
                    "preview_segments": [
                        {
                            "start": 0.0,
                            "end": 1.0,
                            "text": "미리보기",
                            "speaker": "00",
                            "stt_preview_source": "STT1",
                            "subtitle_review_state": "pending",
                            "subtitle_status_color": "#FFD60A",
                            "subtitle_status_schema": "subtitle_status.v1",
                            "subtitle_status_score": 0.72,
                            "subtitle_status_source": "STT1",
                        }
                    ]
                }
            },
        }

        with patch("core.project.project_context.subtitle_status_payload", side_effect=AssertionError("should not recompute")):
            preview = project_stt_preview_segments(project)[0]

        self.assertEqual(preview["subtitle_review_state"], "pending")
        self.assertEqual(preview["subtitle_status_color"], "#FFD60A")
        self.assertEqual(preview["subtitle_status_source"], "STT1")

    def test_project_stt_preview_segments_from_candidate_tracks_do_not_mutate_source_rows(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "editor_state": {
                "stt": {
                    "candidate_tracks": {
                        "STT2": [
                            {
                                "start": 0.0,
                                "end": 1.0,
                                "text": "후보",
                                "speaker": "00",
                            }
                        ]
                    }
                }
            },
        }

        preview = project_stt_preview_segments(project)[0]

        self.assertEqual(preview["stt_preview_source"], "STT2")
        self.assertNotIn(
            "stt_preview_source",
            project["editor_state"]["stt"]["candidate_tracks"]["STT2"][0],
        )

    def test_project_stt_preview_segments_restores_from_lattice_artifact_when_tracks_are_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            lattice_path = Path(tmp) / "project.stt_lattice.json"
            lattice_path.write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "start": 0.0,
                                "end": 1.0,
                                "candidate_lattice": [
                                    {
                                        "candidate_key": "current",
                                        "source": "STT1_SELECTIVE",
                                        "start": 0.0,
                                        "end": 1.0,
                                        "text": "STT1 후보",
                                        "score": 86.0,
                                    }
                                ],
                            },
                            {
                                "start": 1.2,
                                "end": 2.0,
                                "candidate_lattice": [
                                    {
                                        "candidate_key": "current",
                                        "source": "STT2_SELECTIVE_RECHECK",
                                        "start": 1.2,
                                        "end": 2.0,
                                        "text": "STT2 후보",
                                        "score": 91.5,
                                    }
                                ],
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            project = {
                "project_path": str(Path(tmp) / "project.aissproj"),
                "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
                "subtitles": {"storage": PROJECT_EXTERNAL_STORAGE},
                "analysis": {"stt_lattice_artifact_path": str(lattice_path)},
                "editor_state": {"stt": {"candidate_tracks": {}}},
            }

            previews = project_stt_preview_segments(project)

        self.assertEqual([row["text"] for row in previews], ["STT1 후보", "STT2 후보"])
        self.assertEqual([row["stt_preview_source"] for row in previews], ["STT1", "STT2"])
        self.assertEqual(previews[1]["stt_ensemble_source"], "STT2_SELECTIVE_RECHECK")
        self.assertEqual(previews[1]["stt_score"], 91.5)

    def test_project_segments_to_editor_loads_external_subtitles_once_when_external_storage_is_authoritative(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "subtitles": {
                "storage": PROJECT_EXTERNAL_STORAGE,
                "segments": [{"start": 0.0, "end": 1.0, "text": "inline", "speaker": "00"}],
            },
            "editor_state": {
                "subtitles": {
                    "segments": [{"start": 0.0, "end": 1.0, "text": "editor", "speaker": "00"}]
                }
            },
        }

        with patch("core.project.project_context.load_external_subtitle_segments", return_value=[]) as loader:
            segments = project_segments_to_editor(project, include_analysis_candidates=False)

        self.assertEqual(segments, [])
        loader.assert_called_once_with(project)

    def test_project_segments_to_editor_canonicalizes_external_final_srt_order_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "macau.aissproj"
            srt_path = Path(tmp) / "macau.assets" / "subtitles" / "final.srt"
            write_srt_track(
                [
                    {"start": 10.0, "end": 11.0, "text": "뒤 자막", "speaker": "00"},
                    {"start": 5.0, "end": 6.0, "text": "앞 자막", "speaker": "00"},
                    {"start": 10.0, "end": 11.0, "text": "뒤 자막", "speaker": "00"},
                ],
                str(srt_path),
                metadata_default_fps=24.0,
            )
            project = {
                "project_path": str(project_path),
                "_project_file_path": str(project_path),
                "timeline": {
                    "timebase": {"primary_fps": 24.0},
                    "tracks": [{"clips": [{"timeline_start": 0.0, "duration": 20.0, "source_path": "/tmp/video.mp4"}]}],
                },
                "subtitles": {"storage": PROJECT_EXTERNAL_STORAGE},
                "editor_state": {"subtitles": {"segments": []}},
            }

            segments = project_segments_to_editor(project, include_analysis_candidates=False)

        self.assertEqual([(row["line"], row["index"], row["text"]) for row in segments], [
            (0, 1, "앞 자막"),
            (1, 2, "뒤 자막"),
        ])

    def test_project_stt_preview_segments_loads_external_tracks_once_when_external_storage_is_authoritative(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "subtitles": {"storage": PROJECT_EXTERNAL_STORAGE},
            "editor_state": {
                "analysis": {
                    "stt_candidate_tracks": {
                        "STT1": [{"start": 0.0, "end": 1.0, "text": "analysis", "speaker": "00"}]
                    }
                }
            },
        }
        external_tracks = {
            "STT1": [{"start": 0.0, "end": 1.0, "text": "external", "speaker": "00"}]
        }

        with patch("core.project.project_context.load_external_stt_tracks", return_value=external_tracks) as loader:
            previews = project_stt_preview_segments(project)

        self.assertEqual([row["text"] for row in previews], ["external"])
        loader.assert_called_once_with(project)

    def test_project_segments_to_editor_external_stt_candidates_do_not_mutate_source_rows(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "subtitles": {"storage": PROJECT_EXTERNAL_STORAGE},
            "editor_state": {"subtitles": {"segments": []}},
        }
        external_segments = [{"start": 0.0, "end": 1.0, "text": "최종", "speaker": "00"}]
        external_tracks = {
            "STT1": [{"start": 0.0, "end": 1.0, "text": "후보", "speaker": "00"}]
        }

        with patch(
            "core.project.project_context.load_external_subtitle_segments",
            return_value=external_segments,
        ), patch(
            "core.project.project_context.load_external_stt_tracks",
            return_value=external_tracks,
        ):
            segments = project_segments_to_editor(project)

        self.assertEqual(segments[0]["stt_candidates"][0]["source"], "STT1")
        self.assertNotIn("source", external_tracks["STT1"][0])
        self.assertNotIn("stt_preview_source", external_tracks["STT1"][0])

    def test_project_segments_to_editor_restores_external_stt_candidates_by_overlap_after_final_retiming(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 29.97003}, "tracks": [{"clips": []}]},
            "subtitles": {"storage": PROJECT_EXTERNAL_STORAGE},
            "editor_state": {"subtitles": {"segments": []}},
        }
        external_segments = [
            {"start": 63.063, "end": 64.164, "text": "아 이게 시림프 갈릭 소스", "speaker": "00"},
            {"start": 64.164, "end": 66.5, "text": "이게 그건가 보다", "speaker": "00"},
        ]
        external_tracks = {
            "STT1": [{"start": 63.0, "end": 66.0, "text": "아 이게 시림프 갈릭 소스 이게 그건가 보다"}],
            "STT2": [{"start": 64.431, "end": 65.999, "text": "뭐지?"}],
        }

        with patch(
            "core.project.project_context.load_external_subtitle_segments",
            return_value=external_segments,
        ), patch(
            "core.project.project_context.load_external_stt_tracks",
            return_value=external_tracks,
        ):
            segments = project_segments_to_editor(project)

        self.assertEqual([row["text"] for row in segments], [
            "아 이게 시림프 갈릭 소스",
            "이게 그건가 보다",
        ])
        self.assertEqual(segments[0]["stt_candidates"][0]["source"], "STT1")
        self.assertEqual([candidate["source"] for candidate in segments[1]["stt_candidates"]], ["STT1", "STT2"])

    def test_externalize_project_text_assets_does_not_mutate_input_rows_or_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "project.json"
            segments = [
                {"start": 0.02, "end": 1.08, "text": "최종", "speaker": "00"},
            ]
            stt_tracks = {
                "STT1": [
                    {"start": 0.03, "end": 1.04, "text": "후보", "speaker": "00"},
                ]
            }
            original_segments = [dict(row) for row in segments]
            original_tracks = {
                source: [dict(row) for row in rows]
                for source, rows in stt_tracks.items()
            }
            project = {
                "project_path": str(project_path),
                "subtitles": {},
                "editor_state": {"stt": {"candidate_tracks": {}}},
                "analysis": {},
            }

            externalize_project_text_assets(
                str(project_path),
                project,
                final_segments=segments,
                stt_tracks=stt_tracks,
            )

        self.assertEqual(segments, original_segments)
        self.assertEqual(stt_tracks, original_tracks)

    def test_project_segments_to_editor_hot_open_cache_rows_are_copied(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "_hot_open_subtitle_segments_cache": [
                {"start": 0.0, "end": 1.0, "text": "원본", "speaker": "00"}
            ],
        }

        restored = project_segments_to_editor(project)
        restored[0]["text"] = "수정됨"

        self.assertEqual(project["_hot_open_subtitle_segments_cache"][0]["text"], "원본")

    def test_project_segments_to_editor_resolves_recheck_threshold_once_per_batch(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "subtitles": {
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "첫 줄", "speaker": "00", "stt_score": 82},
                    {"start": 1.0, "end": 2.0, "text": "둘째 줄", "speaker": "00", "stt_score": 79},
                ]
            },
        }

        with patch("core.project.project_context.recheck_threshold", return_value=60.0) as threshold_mock:
            segments = project_segments_to_editor(project)

        self.assertEqual(len(segments), 2)
        threshold_mock.assert_called_once()

    def test_project_stt_preview_segments_resolves_recheck_threshold_once_per_batch(self):
        project = {
            "timeline": {"timebase": {"primary_fps": 24.0}, "tracks": [{"clips": []}]},
            "editor_state": {
                "stt": {
                    "preview_segments": [
                        {"start": 0.0, "end": 1.0, "text": "첫 후보", "speaker": "00", "stt_score": 82},
                        {"start": 1.0, "end": 2.0, "text": "둘째 후보", "speaker": "00", "stt_score": 79},
                    ]
                }
            },
        }

        with patch("core.project.project_context.recheck_threshold", return_value=60.0) as threshold_mock:
            previews = project_stt_preview_segments(project)

        self.assertEqual(len(previews), 2)
        threshold_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
