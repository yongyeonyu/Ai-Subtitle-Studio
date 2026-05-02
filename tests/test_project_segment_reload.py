# Version: 03.08.10
# Phase: PHASE2
import unittest

from ui.editor.editor_actions import EditorActionsMixin
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_multiclip_ops import EditorMulticlipOpsMixin


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

    def _get_current_segments(self):
        return list(self._cached_segs)

    def _frame_time(self, sec):
        return round(float(sec), 3)


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

    def test_final_segments_drop_overlapping_live_preview(self):
        editor = _LivePreviewEditor()
        editor.preview_stt_segments([{"start": 1.0, "end": 2.0, "text": "미리보기"}])

        editor.append_segments([{"start": 1.1, "end": 2.1, "text": "최종"}])

        self.assertEqual(editor._live_stt_preview_segments, [])
        self.assertEqual(editor._segment_queue[0]["text"], "최종")
        self.assertTrue(editor._queue_timer.started)

    def test_save_flushes_pending_segment_queue_before_empty_check(self):
        editor = _SaveFlushEditor()

        editor._flush_pending_segment_queue_now()

        self.assertTrue(editor._queue_timer.stopped)
        self.assertTrue(editor.flushed)
        self.assertEqual(editor._segment_queue, [])


if __name__ == "__main__":
    unittest.main()
