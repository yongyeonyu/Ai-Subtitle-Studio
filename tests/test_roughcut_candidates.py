# Version: 03.01.28
# Phase: PHASE2
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.project.project_context import segment_signature
from core.project.project_manager import save_project
from core.roughcut.models import ChapterMetadata, EDLSegment, EditDecision, RoughCutResult, RoughCutSegment
from ui.roughcut.roughcut_widget import RoughcutWidget


def _result(title: str) -> RoughCutResult:
    return RoughCutResult(
        segments=(RoughCutSegment("chapter_0001", 0.0, 3.0, title=title),),
        chapters=(ChapterMetadata("chapter_0001", title, 0.0, 3.0, summary=title),),
        edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=3.0),),
        edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 3.0, 0.0, 3.0),),
        guide_markdown=f"# {title}",
        schema_version="roughcut_result.v2",
    )


class RoughcutCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_payload_keeps_multiple_candidates_and_selected_candidate(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-a"
            widget._result = _result("첫 후보")
            widget._restored_selected_chapter_id = "chapter_0001"
            widget.safety_filter_combo.setCurrentText("ideal")
            first = widget._roughcut_state_payload()
            first_id = first["selected_candidate_id"]

            widget._selected_candidate_id = ""
            widget._source_signature = "sig-b"
            widget._result = _result("둘째 후보")
            second = widget._roughcut_state_payload()

            self.assertEqual(second["schema"], "ai_subtitle_studio.roughcut_state.v2")
            self.assertEqual(second["candidates"][0]["schema"], "ai_subtitle_studio.roughcut_candidate.v2")
            self.assertIn("settings", second)
            self.assertEqual(second["candidate_count"], 2)
            self.assertNotEqual(second["selected_candidate_id"], first_id)
            self.assertEqual(second["chapters"][0]["title"], "둘째 후보")
            self.assertTrue(second["candidates"][0]["outputs"]["guide_markdown"])
            self.assertEqual(second["candidates"][0]["selected_chapter_id"], "chapter_0001")
            self.assertEqual(second["candidates"][0]["safety_filter"], "ideal")

            widget._apply_candidate_payload(second["candidates"][0], persist=False)
            self.assertEqual(widget._selected_candidate_id, first_id)
            self.assertEqual(widget._result.chapters[0].title, "첫 후보")
            self.assertEqual(widget._result.schema_version, "roughcut_result.v2")
        finally:
            widget.close()

    def test_apply_candidate_payload_restores_selected_chapter_and_filter(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = _result("현재 후보")
            current = widget._roughcut_state_payload()
            current["candidate_id"] = "candidate_current"
            current["source_signature"] = "sig-current"
            current["selected_chapter_id"] = "chapter_0001"
            current["safety_filter"] = "ideal"

            widget._roughcut_candidates = [current]
            widget._apply_candidate_payload(current, persist=True)

            self.assertEqual(widget.safety_filter_combo.currentText(), "ideal")
            self.assertEqual(widget.major_panel._selected_chapter_id, "chapter_0001")
            self.assertEqual(widget.selection_summary_lbl.text(), "선택 chapter_0001 · 확정")
        finally:
            widget.close()

    def test_load_project_roughcut_state_prefers_candidate_matching_current_signature(self):
        widget = RoughcutWidget()
        try:
            widget.owner = SimpleNamespace(_current_project_path="/tmp/roughcut-state.aissproj")
            widget._source_signature = "sig-current"
            widget._result = _result("현재 후보")
            matching = widget._roughcut_state_payload()
            matching["candidate_id"] = "candidate_current"
            matching["source_signature"] = "sig-current"
            matching["name"] = "현재 후보"

            widget._selected_candidate_id = ""
            widget._source_signature = "sig-old"
            widget._result = _result("이전 후보")
            foreign = widget._roughcut_state_payload()
            foreign["candidate_id"] = "candidate_old"
            foreign["source_signature"] = "sig-old"
            foreign["name"] = "이전 후보"

            state = {
                "selected_candidate_id": "candidate_old",
                "candidates": [foreign, matching],
            }

            with mock.patch("ui.roughcut.roughcut_state.os.path.exists", return_value=True), \
                 mock.patch("ui.roughcut.roughcut_state.read_project_file", return_value={"roughcut_state": state}):
                restored = widget._load_project_roughcut_state("sig-current")

            self.assertIsNotNone(restored)
            self.assertEqual(widget._selected_candidate_id, "candidate_current")
            self.assertEqual(widget._result.chapters[0].title, "현재 후보")
            self.assertEqual(widget.candidate_combo.currentData(), "candidate_current")
        finally:
            widget.close()

    def test_load_project_roughcut_state_restores_selected_candidate_without_signature_match(self):
        widget = RoughcutWidget()
        try:
            widget.owner = SimpleNamespace(_current_project_path="/tmp/roughcut-state.aissproj")
            widget._source_signature = "sig-old"
            widget._result = _result("이전 후보")
            foreign = widget._roughcut_state_payload()
            foreign["candidate_id"] = "candidate_old"
            foreign["source_signature"] = "sig-old"
            foreign["name"] = "이전 후보"
            widget._user_edits = {"chapter_0001": {"title": "stale"}}

            state = {
                "selected_candidate_id": "candidate_old",
                "candidates": [foreign],
            }

            with mock.patch("ui.roughcut.roughcut_state.os.path.exists", return_value=True), \
                 mock.patch("ui.roughcut.roughcut_state.read_project_file", return_value={"roughcut_state": state}):
                restored = widget._load_project_roughcut_state("sig-current")

            self.assertIsNotNone(restored)
            self.assertEqual(widget._selected_candidate_id, "candidate_old")
            self.assertEqual(len(widget._roughcut_candidates), 1)
            self.assertEqual(widget._result.chapters[0].title, "이전 후보")
        finally:
            widget.close()

    def test_apply_candidate_payload_restores_minor_groups_from_frame_only_payload(self):
        widget = RoughcutWidget()
        try:
            candidate = {
                "candidate_id": "candidate_frame_only",
                "source_signature": "sig-frame-only",
                "selected_chapter_id": "chapter_0001",
                "safety_filter": "전체",
                "segments": [
                    {
                        "segment_id": "major_A",
                        "major_id": "A",
                        "title": "프레임 기반 후보",
                        "timeline_start_frame": 0,
                        "timeline_end_frame": 240,
                        "frame_range": {"unit": "frame", "start": 0, "end": 240, "timeline_frame_rate": 30.0},
                        "minor_groups": [
                            {
                                "minor_id": "A1",
                                "major_id": "A",
                                "code": "A1",
                                "title": "첫 장면",
                                "chapter_ids": ["chapter_0001"],
                                "timeline_start_frame": 0,
                                "timeline_end_frame": 120,
                                "frame_range": {"unit": "frame", "start": 0, "end": 120, "timeline_frame_rate": 30.0},
                            },
                            {
                                "minor_id": "A2",
                                "major_id": "A",
                                "code": "A2",
                                "title": "둘째 장면",
                                "chapter_ids": ["chapter_0002"],
                                "timeline_start_frame": 120,
                                "timeline_end_frame": 240,
                                "frame_range": {"unit": "frame", "start": 120, "end": 240, "timeline_frame_rate": 30.0},
                            },
                        ],
                    }
                ],
                "chapters": [
                    {"chapter_id": "chapter_0001", "title": "첫 장면", "start": 0.0, "end": 4.0, "major_id": "A", "minor_code": "A1"},
                    {"chapter_id": "chapter_0002", "title": "둘째 장면", "start": 4.0, "end": 8.0, "major_id": "A", "minor_code": "A2"},
                ],
                "edit_decisions": [
                    {"segment_id": "chapter_0001", "action": "keep", "source_start": 0.0, "source_end": 4.0},
                    {"segment_id": "chapter_0002", "action": "keep", "source_start": 4.0, "source_end": 8.0},
                ],
                "edl_segments": [
                    {"source_path": "/tmp/source.mp4", "segment_id": "chapter_0001", "source_start": 0.0, "source_end": 4.0, "output_start": 0.0, "output_end": 4.0},
                    {"source_path": "/tmp/source.mp4", "segment_id": "chapter_0002", "source_start": 4.0, "source_end": 8.0, "output_start": 4.0, "output_end": 8.0},
                ],
                "guide_markdown": "# frame only",
            }

            widget._apply_candidate_payload(candidate, persist=False)

            self.assertIsNotNone(widget._result)
            self.assertEqual(len(widget._result.segments[0].minor_groups), 2)
            self.assertEqual(widget._result.segments[0].minor_groups[0].start, 0.0)
            self.assertEqual(widget._result.segments[0].minor_groups[0].end, 4.0)
            self.assertEqual(widget._result.segments[0].minor_groups[1].start, 4.0)
            self.assertEqual(widget._result.segments[0].minor_groups[1].end, 8.0)
        finally:
            widget.close()

    def test_refresh_from_editor_restores_saved_candidate_filter_and_selection_after_project_roundtrip(self):
        segments = [{"start": 0.0, "end": 3.0, "text": "러프컷 자막", "speaker": "00"}]
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "roughcut_restore.aissproj"
            project_path.write_text(
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
                                            "source_path": "/tmp/source.mp4",
                                            "timeline_start": 0.0,
                                            "timeline_end": 3.0,
                                            "timeline_start_frame": 0,
                                            "timeline_end_frame": 90,
                                            "source_frame_rate": 30.0,
                                            "fps": 30.0,
                                            "order": 0,
                                        }
                                    ]
                                }
                            ]
                        },
                        "media": [{"order": 0, "path": "/tmp/source.mp4", "fps": 30.0}],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            source_editor = SimpleNamespace(
                _cached_segs=[dict(seg) for seg in segments],
                media_path="/tmp/source.mp4",
                video_player=SimpleNamespace(total_time=3.0),
            )
            source_owner = SimpleNamespace(
                _current_project_path=str(project_path),
                _editor_widget=source_editor,
                _multiclip_files=[],
                _multiclip_boundaries=[],
            )
            widget = RoughcutWidget(owner=source_owner)
            try:
                widget._source_signature = segment_signature(segments)
                widget._result = _result("저장 후보")
                widget._selected_candidate_id = "candidate_saved"
                widget._restored_selected_chapter_id = "chapter_0001"
                widget.safety_filter_combo.setCurrentText("ideal")
                state = widget._roughcut_state_payload()
            finally:
                widget.close()

            save_project(
                str(project_path),
                segments=segments,
                roughcut_state=state,
                active_work_mode="roughcut",
            )

            restore_editor = SimpleNamespace(
                _cached_segs=[dict(seg) for seg in segments],
                media_path="/tmp/source.mp4",
                video_player=SimpleNamespace(total_time=3.0),
            )
            restore_owner = SimpleNamespace(
                _current_project_path=str(project_path),
                _editor_widget=restore_editor,
                _multiclip_files=[],
                _multiclip_boundaries=[],
            )
            restored_widget = RoughcutWidget(owner=restore_owner)
            try:
                restored_widget.refresh_from_editor(analyze_if_missing=False)

                self.assertEqual(restored_widget._selected_candidate_id, "candidate_saved")
                self.assertEqual(restored_widget.candidate_combo.currentData(), "candidate_saved")
                self.assertEqual(restored_widget.candidate_state_lbl.text(), "현재 자막 기준")
                self.assertEqual(restored_widget.safety_filter_combo.currentText(), "ideal")
                self.assertEqual(restored_widget.major_panel._selected_chapter_id, "chapter_0001")
                self.assertEqual(restored_widget.selection_summary_lbl.text(), "선택 chapter_0001 · 확정")
                restored_widget.refresh_from_editor(analyze_if_missing=False)
                self.assertEqual(restored_widget._selected_candidate_id, "candidate_saved")
                self.assertEqual(restored_widget._result.chapters[0].title, "저장 후보")
            finally:
                restored_widget.close()

    def test_refresh_from_editor_restores_selected_candidate_when_saved_signature_is_stale(self):
        segments = [{"start": 0.0, "end": 3.0, "text": "러프컷 자막", "speaker": "00"}]
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "roughcut_restore_stale_signature.aissproj"
            project_path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "version": "03.00.25",
                        "workspace": {"active_work_mode": "roughcut"},
                        "timeline": {
                            "tracks": [
                                {
                                    "clips": [
                                        {
                                            "id": "clip_a",
                                            "source_path": "/tmp/source.mp4",
                                            "timeline_start": 0.0,
                                            "timeline_end": 3.0,
                                            "timeline_start_frame": 0,
                                            "timeline_end_frame": 90,
                                            "source_frame_rate": 30.0,
                                            "fps": 30.0,
                                            "order": 0,
                                        }
                                    ]
                                }
                            ]
                        },
                        "media": [{"order": 0, "path": "/tmp/source.mp4", "fps": 30.0}],
                        "subtitles": {"segments": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            source_editor = SimpleNamespace(
                _cached_segs=[dict(seg) for seg in segments],
                media_path="/tmp/source.mp4",
                video_player=SimpleNamespace(total_time=3.0),
            )
            source_owner = SimpleNamespace(
                _current_project_path=str(project_path),
                _editor_widget=source_editor,
                _multiclip_files=[],
                _multiclip_boundaries=[],
            )
            widget = RoughcutWidget(owner=source_owner)
            try:
                widget._source_signature = "sig-saved"
                widget._result = _result("저장 후보")
                widget._selected_candidate_id = "candidate_saved"
                widget._restored_selected_chapter_id = "chapter_0001"
                widget.safety_filter_combo.setCurrentText("ideal")
                state = widget._roughcut_state_payload()
            finally:
                widget.close()

            save_project(
                str(project_path),
                segments=segments,
                roughcut_state=state,
                active_work_mode="roughcut",
            )

            restore_editor = SimpleNamespace(
                _cached_segs=[dict(seg) for seg in segments],
                media_path="/tmp/source.mp4",
                video_player=SimpleNamespace(total_time=3.0),
            )
            restore_owner = SimpleNamespace(
                _current_project_path=str(project_path),
                _editor_widget=restore_editor,
                _multiclip_files=[],
                _multiclip_boundaries=[],
            )
            restored_widget = RoughcutWidget(owner=restore_owner)
            try:
                restored_widget.refresh_from_editor(analyze_if_missing=False)

                self.assertEqual(restored_widget._selected_candidate_id, "candidate_saved")
                self.assertEqual(restored_widget.candidate_combo.currentData(), "candidate_saved")
                self.assertEqual(restored_widget.candidate_state_lbl.text(), "저장된 자막 기준")
                self.assertEqual(restored_widget.safety_filter_combo.currentText(), "ideal")
                self.assertEqual(restored_widget.major_panel._selected_chapter_id, "chapter_0001")
                self.assertEqual(restored_widget.selection_summary_lbl.text(), "선택 chapter_0001 · 확정")
                self.assertEqual(restored_widget._result.chapters[0].title, "저장 후보")
                restored_widget.refresh_from_editor(analyze_if_missing=False)
                self.assertEqual(restored_widget._selected_candidate_id, "candidate_saved")
                self.assertEqual(restored_widget.candidate_state_lbl.text(), "저장된 자막 기준")
                self.assertEqual(restored_widget._result.chapters[0].title, "저장 후보")
            finally:
                restored_widget.close()


if __name__ == "__main__":
    unittest.main()
