# Version: 03.09.29
# Phase: PHASE2
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.project.project_manager import extract_model_settings, load_project, merge_project_model_settings, save_project
from core.project.project_context import (
    build_editor_state,
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
        self.assertEqual(state["subtitles"]["segments"][1]["speaker"], "02")
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

        segment = state["subtitles"]["segments"][0]
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
        )

        segment = state["subtitles"]["segments"][0]
        self.assertEqual(segment["stt_selected_source"], "STT2")
        self.assertEqual(segment["stt_candidates"][1]["text"], "후보2")
        preview = state["stt"]["preview_segments"][0]
        self.assertEqual(preview["stt_preview_source"], "STT2")
        self.assertEqual(preview["_clip_idx"], 1)
        self.assertTrue(preview["_live_stt_preview"])

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
        segment = loaded["subtitles"]["segments"][0]
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
        editor_segment = loaded["editor_state"]["subtitles"]["segments"][0]
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

        segment = loaded["subtitles"]["segments"][0]
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
        segment = loaded["subtitles"]["segments"][0]
        self.assertEqual(segment["start_frame"], 48)
        self.assertEqual(segment["end_frame"], 72)
        self.assertEqual(segment["clip_local_start_frame"], 0)
        self.assertEqual(segment["clip_local_end_frame"], 30)


if __name__ == "__main__":
    unittest.main()
