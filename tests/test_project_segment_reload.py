# Version: 03.09.31
# Phase: PHASE2
import unittest

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
    total_time = 0.0


class _Timeline:
    def __init__(self):
        self.updated = None

    def update_segments(self, segs, active_sec, total_dur):
        self.updated = (list(segs), active_sec, total_dur)


class _Status:
    def text(self):
        return ""


class _QueueTimer:
    def __init__(self):
        self.started = False

    def isActive(self):
        return False

    def start(self, _ms):
        self.started = True


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
        self.video_player = type("VideoPlayer", (), {"total_time": 10.0})()
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
        self.assertEqual(editor.timeline.updated[0][0]["text"], "미리보기")
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
        self.assertEqual([seg["text"] for seg in editor.timeline.updated[0]], ["STT1", "STT2"])

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

        editor.select_stt_candidate_as_subtitle(editor._live_stt_preview_segments[1])
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
