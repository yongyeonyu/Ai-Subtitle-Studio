# Version: 03.14.05
# Phase: PHASE2
import unittest
import re

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QTextEdit

from ui.editor.editor_actions import EditorActionsMixin
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_multiclip_ops import EditorMulticlipOpsMixin
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.undo_manager import UndoManager


class _Timer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _TextEdit:
    def __init__(self):
        self.cleared = False

    def clear(self):
        self.cleared = True


class _VideoPlayer:
    def __init__(self, total_time=0.0):
        self.total_time = float(total_time)
        self.seek_calls = []

    def seek(self, sec):
        self.seek_calls.append(float(sec))


class _ScrollBar:
    def __init__(self):
        self._value = 0

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = int(value)


class _TimelineScroll:
    def __init__(self):
        self._horizontal = _ScrollBar()

    def horizontalScrollBar(self):
        return self._horizontal


class _Timeline:
    def __init__(self):
        self.updated = None
        self.active_calls = []
        self.playhead_calls = []
        self.canvas = type("Canvas", (), {"playhead_sec": 0.0, "segments": []})()
        self.scroll = _TimelineScroll()

    def update_segments(self, segs, active_sec, total_dur):
        self.updated = (list(segs), active_sec, total_dur)
        self.canvas.segments = list(segs)

    def set_active(self, sec):
        self.active_calls.append(float(sec))

    def set_playhead(self, sec, *, preserve_center_lock=False):
        self.canvas.playhead_sec = float(sec)
        self.playhead_calls.append((float(sec), bool(preserve_center_lock)))

    def center_to_sec(self, _sec, smooth=False):
        return None


class _Status:
    def text(self):
        return ""


class _QueueTimer:
    def __init__(self):
        self.started = False
        self.stopped = False

    def isActive(self):
        return False

    def start(self, _ms):
        self.started = True

    def stop(self):
        self.stopped = True


class _ActiveQueueTimer(_QueueTimer):
    def __init__(self):
        super().__init__()
        self.stopped = False

    def isActive(self):
        return True

    def stop(self):
        self.stopped = True


class _SaveFlushEditor(EditorActionsMixin):
    def __init__(self):
        self._queue_timer = _ActiveQueueTimer()
        self._segment_queue = [{"start": 0.0, "end": 1.0, "text": "대기"}]
        self.flushed = False

    def _flush_queue(self):
        self.flushed = True
        self._segment_queue = []


class _LivePreviewEditor(EditorSegmentsMixin):
    def __init__(self):
        self.status_lbl = _Status()
        self.timeline = _Timeline()
        self.video_player = _VideoPlayer(total_time=10.0)
        self._active_seg_start = None
        self._cached_segs = []
        self._segment_queue = []
        self._queue_timer = _QueueTimer()
        self.reload_called_with = None
        self.dirty = False
        self.scheduled = False

    def _get_current_segments(self):
        return list(self._cached_segs)

    def _frame_time(self, sec):
        return round(float(sec), 3)

    def _reload_segments_from_list(self, segs, preserve_view=False):
        self.reload_called_with = list(segs)
        self._cached_segs = list(segs)

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True


class _UndoableLivePreviewEditor(_LivePreviewEditor):
    def __init__(self):
        super().__init__()
        self.text_edit = QTextEdit()
        self._undo_mgr = UndoManager(self)

    def _get_current_segments(self):
        return list(self._cached_segs)

    def _reload_segments_from_list(self, segs, preserve_view=False):
        self.reload_called_with = list(segs)
        self._cached_segs = [dict(seg) for seg in segs]
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()
        for idx, seg in enumerate(self._cached_segs):
            if idx > 0:
                cur.insertText("\n")
            cur.insertText(str(seg.get("text", "") or ""))
            cur.block().setUserData(
                SubtitleBlockData(
                    str(seg.get("speaker", seg.get("spk", "00")) or "00"),
                    float(seg.get("start", 0.0) or 0.0),
                    False,
                    stt_selected_source=str(seg.get("stt_selected_source", "") or ""),
                    quality=dict(seg.get("quality") or {}),
                )
            )
        self._update_timeline_with_confirmed_and_preview(self._cached_segs)


class _ReplacementEditor(EditorSegmentsMixin):
    def __init__(self):
        self.text_edit = QTextEdit()
        self.video_player = _VideoPlayer(total_time=20.0)
        self._cached_segs = []
        self.dirty = False
        self.scheduled = False
        self.refreshed = False

    def load_blocks(self, rows):
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()
        for idx, (text, start, is_gap) in enumerate(rows):
            if idx > 0:
                cur.insertText("\n")
            cur.insertText(text)
            cur.block().setUserData(SubtitleBlockData("00", float(start), bool(is_gap)))

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True

    def _refresh_video_subtitle_context(self):
        self.refreshed = True


class _ActualSelectionEditor(EditorMulticlipOpsMixin, EditorSegmentsMixin):
    _JUNK_TS_RE = re.compile(r"(?!)")
    _JUNK_NO_BRACKET_3PART = re.compile(r"(?!)")
    _JUNK_NO_BRACKET_3PART_END = re.compile(r"(?!)")
    _JUNK_START_RE = re.compile(r"(?!)")

    def __init__(self):
        self.status_lbl = _Status()
        self.text_edit = QTextEdit()
        self.text_edit.update_margins = lambda: None
        self.timeline = _Timeline()
        self.video_player = _VideoPlayer(total_time=100.0)
        self.settings = {
            "continuous_threshold": 2.0,
            "gap_push_rate": 0.7,
            "single_subtitle_end": 0.2,
            "spk1_id": "00",
            "spk2_id": "01",
            "subtitle_quality_auto_check_after_generate": False,
        }
        self.video_fps = 30.0
        self._active_seg_start = None
        self._cached_segs = []
        self._segment_queue = []
        self._queue_timer = _QueueTimer()
        self._sync_lock = False
        self._is_initial_load = False
        self.dirty = False
        self.scheduled = False
        self.refreshed = False

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True

    def _refresh_video_subtitle_context(self):
        self.refreshed = True


class _Editor(EditorMulticlipOpsMixin):
    def __init__(self):
        self._queue_timer = _Timer()
        self._segment_queue = [{"start": 9.0, "end": 10.0, "text": "stale"}]
        self._is_initial_load = False
        self.text_edit = _TextEdit()
        self.video_player = _VideoPlayer()
        self.timeline = _Timeline()
        self._active_seg_start = None
        self.dirty = False
        self.scheduled = False

    def append_segments(self, segments):
        self._segment_queue.extend(segments)

    def _mark_dirty(self):
        self.dirty = True

    def _schedule_timeline(self):
        self.scheduled = True


class ProjectSegmentReloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reload_replaces_pending_segments_before_project_restore(self):
        editor = _Editor()
        restored = [{"start": 1.0, "end": 2.0, "text": "restored"}]

        editor._reload_segments_from_list(restored)

        self.assertTrue(editor._queue_timer.stopped)
        self.assertTrue(editor.text_edit.cleared)
        self.assertTrue(editor._is_initial_load)
        self.assertEqual(len(editor._segment_queue), 1)
        self.assertEqual(editor._segment_queue[0]["text"], "restored")
        self.assertEqual(editor._segment_queue[0]["line"], 0)
        self.assertEqual(editor.timeline.updated[0], editor._segment_queue)
        self.assertEqual(editor.timeline.updated[2], 2.0)
        self.assertTrue(editor.dirty)
        self.assertTrue(editor.scheduled)

    def test_live_stt_preview_updates_timeline_without_editor_commit(self):
        editor = _LivePreviewEditor()

        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "미리보기"}])

        self.assertEqual(len(editor._live_stt_preview_segments), 1)
        self.assertTrue(editor._live_stt_preview_segments[0]["stt_pending"])
        subtitle_drafts = [seg for seg in editor.timeline.updated[0] if seg.get("_live_subtitle_preview")]
        stt_previews = [seg for seg in editor.timeline.updated[0] if seg.get("_live_stt_preview")]
        self.assertEqual(subtitle_drafts[0]["text"], "미리보기")
        self.assertEqual(stt_previews[0]["text"], "미리보기")
        self.assertEqual(editor.timeline.updated[2], 10.0)
        self.assertEqual(editor._segment_queue, [])

    def test_live_stt_preview_keeps_stt1_and_stt2_overlap_as_separate_lanes(self):
        editor = _LivePreviewEditor()

        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "STT1", "stt_preview_source": "STT1"}])
        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "STT2", "stt_preview_source": "STT2"}])

        self.assertEqual(len(editor._live_stt_preview_segments), 2)
        self.assertEqual(
            [seg["stt_preview_source"] for seg in editor._live_stt_preview_segments],
            ["STT1", "STT2"],
        )
        subtitle_drafts = [seg for seg in editor.timeline.updated[0] if seg.get("_live_subtitle_preview")]
        stt_previews = [seg for seg in editor.timeline.updated[0] if seg.get("_live_stt_preview")]
        self.assertEqual([seg["text"] for seg in subtitle_drafts], ["STT1"])
        self.assertEqual([seg["text"] for seg in stt_previews], ["STT1", "STT2"])

    def test_live_subtitle_preview_is_removed_when_final_segment_overlaps(self):
        editor = _LivePreviewEditor()
        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "드래프트", "stt_preview_source": "STT1"}])
        self.assertTrue(any(seg.get("_live_subtitle_preview") for seg in editor.timeline.updated[0]))

        editor._cached_segs = [{"start": 1.0, "end": 2.0, "text": "최종", "speaker": "00"}]
        editor._redraw_timeline_with_live_preview()

        subtitle_drafts = [seg for seg in editor.timeline.updated[0] if seg.get("_live_subtitle_preview")]
        stt_previews = [seg for seg in editor.timeline.updated[0] if seg.get("_live_stt_preview")]
        self.assertEqual(subtitle_drafts, [])
        self.assertEqual([seg["text"] for seg in stt_previews], ["드래프트"])

    def test_live_stt_preview_is_visible_in_editor_without_saved_commit(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "실시간 드래프트", "stt_preview_source": "STT1"}
            ])
            editor._flush_live_editor_preview_queue()

            self.assertIn("실시간 드래프트", editor.text_edit.toPlainText())
            self.assertEqual([seg for seg in editor._get_current_segments() if not seg.get("is_gap")], [])
        finally:
            editor.text_edit.close()

    def test_live_stt_preview_autoscrolls_editor_to_latest_draft(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "첫 드래프트", "stt_preview_source": "STT1"},
                {"start": 3.0, "end": 4.0, "text": "둘째 드래프트", "stt_preview_source": "STT1"},
            ])
            editor._flush_live_editor_preview_queue()

            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 1)
            self.assertAlmostEqual(editor._active_seg_start, 3.0)
            self.assertEqual(editor.timeline.active_calls[-1], 3.0)
        finally:
            editor.text_edit.close()

    def test_llm_review_payload_focuses_matching_editor_draft(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "첫 드래프트", "stt_preview_source": "STT1"},
                {"start": 3.0, "end": 4.0, "text": "둘째 드래프트", "stt_preview_source": "STT1"},
            ])
            editor._flush_live_editor_preview_queue()

            focused = editor._focus_editor_block_for_processing_segment({
                "active": True,
                "start": 1.0,
                "end": 2.0,
                "text": "첫 드래프트",
            })

            self.assertTrue(focused)
            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 0)
            self.assertAlmostEqual(editor._active_seg_start, 1.0)
            self.assertEqual(editor.timeline.active_calls[-1], 1.0)
        finally:
            editor.text_edit.close()

    def test_final_segment_replaces_overlapping_live_editor_preview(self):
        editor = _ActualSelectionEditor()
        try:
            editor.preview_stt_segments([
                {"start": 1.0, "end": 2.0, "text": "실시간 드래프트", "stt_preview_source": "STT1"}
            ])
            editor._flush_live_editor_preview_queue()

            editor.append_segments([{"start": 1.0, "end": 2.0, "text": "최종 자막", "speaker": "00"}])
            editor._flush_queue()

            editor_text = editor.text_edit.toPlainText()
            self.assertIn("최종 자막", editor_text)
            self.assertNotIn("실시간 드래프트", editor_text)
            saved = [seg for seg in editor._get_current_segments() if not seg.get("is_gap")]
            self.assertEqual([seg["text"] for seg in saved], ["최종 자막"])
        finally:
            editor.text_edit.close()

    def test_final_live_append_autoscrolls_editor_to_latest_polished_subtitle(self):
        editor = _ActualSelectionEditor()
        try:
            editor.append_segments([
                {"start": 1.0, "end": 2.0, "text": "첫 최종", "speaker": "00"},
                {"start": 3.0, "end": 4.0, "text": "둘째 최종", "speaker": "00"},
            ])
            editor._flush_queue()

            self.assertEqual(editor.text_edit.textCursor().block().text(), "둘째 최종")
            self.assertAlmostEqual(editor._active_seg_start, 2.7)
            self.assertEqual(editor.timeline.active_calls[-1], 2.7)
        finally:
            editor.text_edit.close()

    def test_final_segments_keep_live_preview_candidates_for_manual_selection(self):
        editor = _LivePreviewEditor()
        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "미리보기"}])

        editor.append_segments([{"start": 1.1, "end": 2.1, "text": "최종"}])

        self.assertEqual(len(editor._live_stt_preview_segments), 1)
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "미리보기")
        self.assertEqual(editor._segment_queue[0]["text"], "최종")
        self.assertTrue(editor._queue_timer.started)

    def test_select_stt_candidate_replaces_overlapping_final_segment(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [{"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}]
        editor.preview_stt_segments([
            {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual(editor.reload_called_with[0]["text"], "STT1 후보")
        self.assertEqual(editor.reload_called_with[0]["stt_selected_source"], "STT1")
        self.assertEqual(editor.reload_called_with[0]["quality"]["confidence_label"], "green")
        self.assertEqual(len(editor._live_stt_preview_segments), 1)
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "STT1 후보")

    def test_select_stt_candidate_anchors_playhead_to_candidate_start(self):
        editor = _LivePreviewEditor()
        editor.timeline.canvas.playhead_sec = 99.0
        editor.timeline.scroll.horizontalScrollBar().setValue(37)
        editor._cached_segs = [{"start": 90.0, "end": 100.0, "text": "끝 자막", "speaker": "00"}]
        editor.preview_stt_segments([
            {"start": 12.5, "end": 13.5, "text": "STT2 후보", "stt_preview_source": "STT2"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual(editor._active_seg_start, 12.5)
        self.assertEqual(editor.timeline.active_calls[-1], 12.5)
        self.assertEqual(editor.timeline.playhead_calls[-1], (12.5, True))
        self.assertEqual(editor.timeline.canvas.playhead_sec, 12.5)
        self.assertEqual(editor.video_player.seek_calls[-1], 12.5)
        self.assertEqual(editor.timeline.scroll.horizontalScrollBar().value(), 37)

    def test_select_stt_candidate_fits_near_boundary_candidate_to_original_slot(self):
        editor = _LivePreviewEditor()
        editor.video_fps = 30.0
        editor._cached_segs = [{"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}]
        editor.preview_stt_segments([
            {"start": 0.92, "end": 2.08, "text": "STT2 후보", "stt_preview_source": "STT2"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual([seg["text"] for seg in editor.reload_called_with], ["STT2 후보"])
        self.assertEqual([(seg["start"], seg["end"]) for seg in editor.reload_called_with], [(1.0, 2.0)])
        self.assertEqual(editor.reload_called_with[0]["stt_selected_source"], "STT2")
        self.assertEqual(editor.reload_called_with[0]["stt_candidates"][0]["_stt_placement_mode"], "replace_original_slot")
        self.assertEqual(editor.timeline.playhead_calls[-1], (1.0, True))

    def test_select_stt_candidate_targets_best_original_slot_when_candidate_bleeds_across_boundary(self):
        editor = _LivePreviewEditor()
        editor.video_fps = 30.0
        editor._cached_segs = [
            {"start": 0.0, "end": 1.0, "text": "앞 자막", "speaker": "00"},
            {"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"},
        ]
        editor.preview_stt_segments([
            {"start": 0.94, "end": 2.04, "text": "STT1 후보", "stt_preview_source": "STT1"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual([seg["text"] for seg in editor.reload_called_with], ["앞 자막", "STT1 후보"])
        self.assertEqual([(seg["start"], seg["end"]) for seg in editor.reload_called_with], [(0.0, 1.0), (1.0, 2.0)])
        self.assertEqual(editor.reload_called_with[1]["stt_candidates"][0]["_stt_placement_mode"], "replace_original_slot")

    def test_select_stt_candidate_preserve_reload_flush_does_not_autoseek_to_tail(self):
        editor = _ActualSelectionEditor()
        try:
            editor._reload_segments_from_list([
                {"start": 0.0, "end": 1.0, "text": "앞", "speaker": "00"},
                {"start": 90.0, "end": 95.0, "text": "뒤", "speaker": "00"},
            ], preserve_view=True)
            editor.timeline.playhead_calls.clear()
            editor.video_player.seek_calls.clear()
            editor.timeline.canvas.playhead_sec = 90.0
            editor.preview_stt_segments([
                {"start": 0.0, "end": 1.0, "text": "STT1 선택", "stt_preview_source": "STT1"}
            ])

            editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
            editor._flush_queue()

            self.assertEqual(editor.timeline.playhead_calls, [(0.0, True)])
            self.assertEqual(editor.video_player.seek_calls, [0.0])
            self.assertEqual(editor._segment_queue, [])
            self.assertTrue(editor._queue_timer.stopped)
        finally:
            editor.text_edit.close()

    def test_replace_text_in_all_subtitles_skips_gap_blocks(self):
        editor = _ReplacementEditor()
        try:
            editor.load_blocks([
                ("BMW랑 BMW", 0.0, False),
                ("BMW 쉬는중", 1.0, True),
                ("끝 BMW", 2.0, False),
            ])
            block = editor.text_edit.document().findBlockByNumber(0)
            anchor = QTextCursor(block)
            anchor.setPosition(block.position())
            end = QTextCursor(block)
            end.setPosition(block.position() + 3)

            replaced = editor._replace_text_in_all_subtitles("BMW", "비엠", anchor=anchor, end_cursor=end)

            self.assertEqual(replaced, 3)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["비엠랑 비엠", "BMW 쉬는중", "끝 비엠"])
            self.assertEqual([seg["text"] for seg in editor._cached_segs], ["비엠랑 비엠", "BMW 쉬는중", "끝 비엠"])
            self.assertTrue(editor._cached_segs[1]["is_gap"])
            self.assertTrue(editor.dirty)
            self.assertTrue(editor.scheduled)
            self.assertTrue(editor.refreshed)
            self.assertEqual(editor.text_edit.document().findBlockByNumber(0).userData().start_sec, 0.0)
        finally:
            editor.text_edit.close()

    def test_select_stt_candidate_trims_overlapping_final_segment_edges(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [
            {"start": 0.0, "end": 4.0, "text": "긴 기존 자막", "speaker": "00"},
        ]
        editor.preview_stt_segments([
            {"start": 1.0, "end": 3.0, "text": "STT2 선택", "stt_preview_source": "STT2"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])

        self.assertEqual([seg["text"] for seg in editor.reload_called_with], ["긴 기존 자막", "STT2 선택", "긴 기존 자막"])
        self.assertEqual([(seg["start"], seg["end"]) for seg in editor.reload_called_with], [(0.0, 1.0), (1.0, 3.0), (3.0, 4.0)])
        self.assertEqual(editor.reload_called_with[1]["stt_selected_source"], "STT2")

    def test_select_stt_candidate_keeps_next_final_candidate_selectable(self):
        editor = _LivePreviewEditor()
        editor._cached_segs = [
            {"start": 10.0, "end": 14.0, "text": "STT1 긴 자막", "speaker": "00"},
        ]
        editor.preview_stt_segments([
            {"start": 10.0, "end": 12.0, "text": "STT2 앞", "stt_preview_source": "STT2"},
            {"start": 12.0, "end": 14.0, "text": "STT2 뒤", "stt_preview_source": "STT2"},
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[1])

        self.assertEqual([seg["text"] for seg in editor.reload_called_with], ["STT2 앞", "STT2 뒤"])
        self.assertEqual([(seg["start"], seg["end"]) for seg in editor.reload_called_with], [(10.0, 12.0), (12.0, 14.0)])

    def test_select_stt_candidate_is_undo_redo_snapshot(self):
        editor = _UndoableLivePreviewEditor()
        editor._reload_segments_from_list([
            {"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}
        ])
        editor.preview_stt_segments([
            {"start": 1.0, "end": 2.0, "text": "STT2 후보", "stt_preview_source": "STT2"}
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
        self.assertEqual(editor._cached_segs[0]["text"], "STT2 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT2")

        editor._undo_mgr.undo()
        self.assertEqual(editor._cached_segs[0]["text"], "기존")
        self.assertNotIn("stt_selected_source", editor._cached_segs[0])
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "STT2 후보")

        editor._undo_mgr.redo()
        self.assertEqual(editor._cached_segs[0]["text"], "STT2 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT2")
        self.assertEqual(editor._live_stt_preview_segments[0]["text"], "STT2 후보")

    def test_switching_between_stt1_and_stt2_is_undo_redo_snapshot(self):
        editor = _UndoableLivePreviewEditor()
        editor._reload_segments_from_list([
            {"start": 1.0, "end": 2.0, "text": "기존", "speaker": "00"}
        ])
        editor.preview_stt_segments([
            {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1"},
            {"start": 1.0, "end": 2.0, "text": "STT2 후보", "stt_preview_source": "STT2"},
        ])

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
        self.assertEqual(editor._cached_segs[0]["text"], "STT1 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT1")

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[0])
        self.assertEqual(editor._cached_segs[0]["text"], "STT2 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT2")

        editor._undo_mgr.undo()
        self.assertEqual(editor._cached_segs[0]["text"], "STT1 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT1")

        editor._undo_mgr.undo()
        self.assertEqual(editor._cached_segs[0]["text"], "기존")
        self.assertNotIn("stt_selected_source", editor._cached_segs[0])

        editor._undo_mgr.redo()
        self.assertEqual(editor._cached_segs[0]["text"], "STT1 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT1")

        editor._undo_mgr.redo()
        self.assertEqual(editor._cached_segs[0]["text"], "STT2 후보")
        self.assertEqual(editor._cached_segs[0]["stt_selected_source"], "STT2")

    def test_save_flushes_pending_segment_queue_before_empty_check(self):
        editor = _SaveFlushEditor()

        editor._flush_pending_segment_queue_now()

        self.assertTrue(editor._queue_timer.stopped)
        self.assertTrue(editor.flushed)
        self.assertEqual(editor._segment_queue, [])


if __name__ == "__main__":
    unittest.main()
