# Version: 03.00.26
# Phase: PHASE2
import unittest
import json
import tempfile
from pathlib import Path

from core.project.project_manager import load_project, save_project
from core.project.project_context import (
    build_editor_state,
    project_active_work_mode,
    project_clip_boundaries,
    project_media_files,
    project_mode,
    project_roughcut_state,
    project_segments_to_editor,
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
                roughcut_state={"source_signature": "sig", "chapters": [], "edl_segments": []},
                active_work_mode="roughcut",
            )
            loaded = load_project(str(path))

        self.assertEqual(loaded["version"], "03.00.26")
        self.assertEqual(project_active_work_mode(loaded), "roughcut")
        self.assertEqual(project_roughcut_state(loaded)["source_signature"], "sig")
        self.assertEqual(project_segments_to_editor(loaded)[0]["text"], "저장")


if __name__ == "__main__":
    unittest.main()
