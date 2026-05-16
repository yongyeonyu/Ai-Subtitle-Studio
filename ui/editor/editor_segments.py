# Version: 03.14.29
# Phase: PHASE2
"""
ui/editor_segments.py
EditorWidget의 자막 에디터 조작, 큐 처리, 세그먼트 I/O 메서드 모음.
[수정] core 폴더 이동에 따른 데이터 매니저 경로 및 상대 경로 최적화 완료
"""
from core.runtime.logger import get_logger

# 💡 [경로 수정] editor_data_manager -> core.data_manager
from core.project.data_manager import save_correction as _dm_save_correction

# 수정 — 절대 import로 통일 (editor_widget.py, editor_timeline_video.py와 동일)
from ui.editor.editor_roughcut_draft import EditorRoughcutDraftMixin
from ui.editor.editor_segments_block_surgery import EditorSegmentsBlockSurgeryMixin
from ui.editor.editor_segments_bulk_load import EditorSegmentsBulkLoadMixin
from ui.editor.editor_segments_current_state import EditorSegmentsCurrentStateMixin
from ui.editor.editor_segments_live_preview import EditorSegmentsLivePreviewMixin
from ui.editor.editor_segments_manual_edits import EditorSegmentsManualEditsMixin
from ui.editor.editor_segments_queue_flush import EditorSegmentsQueueFlushMixin
from ui.editor.editor_segments_reload import EditorSegmentsReloadMixin
from ui.editor.editor_segments_runtime_cache import EditorSegmentsRuntimeCacheMixin
from ui.editor.editor_segments_stt_candidates import EditorSegmentsSttCandidatesMixin
from ui.editor.editor_segments_stt_selection_flow import EditorSegmentsSttSelectionFlowMixin
from ui.editor.editor_segments_text_ops import EditorSegmentsTextOpsMixin
from ui.editor.editor_segments_timeline_context import EditorSegmentsTimelineContextMixin


class EditorSegmentsMixin(
    EditorSegmentsRuntimeCacheMixin,
    EditorSegmentsBlockSurgeryMixin,
    EditorSegmentsBulkLoadMixin,
    EditorSegmentsCurrentStateMixin,
    EditorSegmentsLivePreviewMixin,
    EditorSegmentsManualEditsMixin,
    EditorSegmentsQueueFlushMixin,
    EditorSegmentsReloadMixin,
    EditorSegmentsSttCandidatesMixin,
    EditorSegmentsSttSelectionFlowMixin,
    EditorSegmentsTextOpsMixin,
    EditorSegmentsTimelineContextMixin,
    EditorRoughcutDraftMixin,
):
    """자막 에디터 조작 / 큐 처리 / 세그먼트 I/O"""
    def _finalize_edit(self):
        self._invalidate_segment_cache()
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            try:
                self.text_edit._schedule_timestamp_area_update()
            except Exception:
                self.text_edit.timestampArea.update()
        self._schedule_timeline()

    def _schedule_cursor_video_seek(self, sec: float, delay_ms: int = 72) -> None:
        try:
            self._pending_cursor_video_seek_sec = float(sec or 0.0)
        except Exception:
            self._pending_cursor_video_seek_sec = 0.0
        timer = getattr(self, "_cursor_video_seek_timer", None)
        if timer is None:
            self._flush_cursor_video_seek()
            return
        timer.start(max(0, int(delay_ms or 0)))

    def _flush_cursor_video_seek(self) -> None:
        player = getattr(self, "video_player", None)
        if player is None:
            return
        sec = getattr(self, "_pending_cursor_video_seek_sec", None)
        if sec is None:
            return
        self._pending_cursor_video_seek_sec = None
        try:
            player.seek(float(sec))
        except Exception:
            pass

    # ---------------------------------------------------------
    # Segment I/O
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # Text Editor Event Handlers
    # ---------------------------------------------------------
    def _save_correction(self, old_word, new_word):
        _dm_save_correction(self.corrections, old_word, new_word)
        try:
            from core.subtitle_quality.correction_memory import add_correction_memory_item
            add_correction_memory_item(
                old_word,
                new_word,
                source="manual_popup",
                context=self.text_edit.textCursor().block().text()[:500],
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 교정 memory 저장 실패: {exc}")
        get_logger().log(f"🔄 교정 사전 등록 및 저장: {old_word} -> {new_word}")
