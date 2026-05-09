# Version: 03.09.29
# Phase: PHASE2
import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import core.project.project_io as project_io
from core.project.project_io import clear_project_file_cache, read_project_file, write_project_file
from core.project.project_manager import extract_model_settings, load_project, merge_project_model_settings, save_project
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
from core.project.project_assets import externalize_project_text_assets
from core.project.project_srt import parse_srt_to_segments
from core.cut_boundary import split_segments_by_cut_boundaries


def _state_segments(state: dict) -> list[dict]:
    return project_segments_to_editor({"editor_state": state})


class ProjectContextTests(unittest.TestCase):
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
        self.assertEqual(vector_canvas["renderer"]["active_surface"], "timeline-qopenglwidget")
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
        self.assertEqual(pending["subtitle_status_color"], "#FFCC00")
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

        self.assertEqual(loaded["version"], "03.00.26")
        self.assertEqual(project_active_work_mode(loaded), "roughcut")
        self.assertEqual(project_roughcut_state(loaded)["source_signature"], "sig")
        self.assertEqual(project_roughcut_state(loaded)["selected_candidate_id"], "candidate_a")
        self.assertEqual(len(project_roughcut_state(loaded)["candidates"]), 1)
        self.assertEqual(project_segments_to_editor(loaded)[0]["text"], "저장")

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
        self.assertEqual(voice_segment["start_frame"], 12)
        self.assertEqual(voice_segment["end_frame"], 30)
        self.assertEqual(voice_segment["score"], 82.0)
        self.assertEqual(voice_segment["selection_state"], "llm_selected")
        self.assertEqual(voice_segment["frame_range"]["unit"], "frame")
        self.assertEqual(voice_segment["frame_range"]["start"], 12)
        editor_voice = loaded["editor_state"]["analysis"]["voice_activity_segments"][0]
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
        self.assertEqual(preview["_clip_idx"], 1)
        self.assertEqual(preview["start_frame"], 240)
        self.assertEqual(preview["end_frame"], 264)

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
        self.assertEqual(first["subtitle_status_color"], "#FFCC00")
        self.assertEqual(first["stt_candidates"][0]["stt_score_color"], "#52C759")
        self.assertEqual(second["subtitle_review_state"], "confirmed")
        self.assertEqual(second["subtitle_status_color"], "#34C759")
        editor_first = project_segments_to_editor(loaded)[0]
        self.assertEqual(editor_first["subtitle_review_state"], "pending")
        preview = project_stt_preview_segments(loaded)[0]
        self.assertEqual(preview["stt_score"], 91)
        self.assertEqual(preview["stt_score_color"], "#52C759")

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
        self.assertAlmostEqual(previews[0]["start"], 3.0, places=6)

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

            raw_payload = json.loads(path.read_text(encoding="utf-8"))
            final_srt = path.parent / raw_payload["subtitles"]["srt_path"]
            stt1_srt = path.parent / raw_payload["asset_storage"]["tracks"]["stt_stt1"]["path"]
            stt2_srt = path.parent / raw_payload["asset_storage"]["tracks"]["stt_stt2"]["path"]

            self.assertEqual(raw_payload["subtitles"]["storage"], "external_srt")
            self.assertEqual(raw_payload["editor_state"]["rendering"]["subtitle_canvas"]["segments"], [])
            self.assertEqual(raw_payload["editor_state"]["stt"]["candidate_tracks"], {})
            self.assertNotIn("stt_candidate_tracks", raw_payload["analysis"])
            self.assertTrue(final_srt.exists())
            self.assertTrue(stt1_srt.exists())
            self.assertTrue(stt2_srt.exists())
            self.assertIn("최종 자막", final_srt.read_text(encoding="utf-8"))
            self.assertNotIn("후보 하나", path.read_text(encoding="utf-8"))

            loaded = load_project(str(path))
            segment = project_segments_to_editor(loaded)[0]
            previews = project_stt_preview_segments(loaded)

        self.assertEqual(segment["text"], "최종 자막")
        self.assertEqual([candidate["source"] for candidate in segment["stt_candidates"]], ["STT1", "STT2"])
        self.assertEqual([row["text"] for row in previews], ["후보 하나", "후보 둘"])

    def test_external_stt_assets_are_deduped_to_non_overlapping_tracks(self):
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

        self.assertEqual([row["text"] for row in stt1_rows], ["첫 후보", "둘 후보"])
        self.assertLessEqual(stt1_rows[0]["end"], stt1_rows[1]["start"])
        self.assertEqual([row["text"] for row in stt1_previews], ["첫 후보", "둘 후보"])
        self.assertLessEqual(stt1_previews[0]["end"], stt1_previews[1]["start"])

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
                            "subtitle_status_color": "#FFCC00",
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
        self.assertEqual(preview["subtitle_status_color"], "#FFCC00")
        self.assertEqual(preview["subtitle_status_source"], "STT1")

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
