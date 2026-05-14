# Version: 03.14.03
# Phase: PHASE2
"""
ui/editor_pipeline.py
[v01.00.16] 모드/상태 정의 문서 반영
- _on_save: is_locked 체크 제거 (상태 무관 저장)
- _on_prev: 생성 중 중단 + 단일 다이얼로그 (main_window 중복 제거)
- update_progress: 완료 조건 단일화 (EditorPipeline만 완료 판단)
- 기존 기능 100% 유지
"""
from PyQt6.QtCore import QTimer

from ui.editor.editor_pipeline_cleanup import EditorPipelineCleanupMixin
from ui.editor.editor_pipeline_completion import EditorPipelineCompletionMixin
from ui.editor.editor_pipeline_partial_rerun import EditorPipelinePartialRerunMixin
from ui.editor.editor_pipeline_playhead_actions import EditorPipelinePlayheadActionsMixin
from ui.editor.editor_pipeline_signal_bridge import EditorPipelineSignalBridgeMixin
from ui.editor.editor_pipeline_startup import EditorPipelineStartupMixin
from ui.editor.editor_pipeline_status import EditorPipelineStatusMixin


class EditorPipelineMixin(
    EditorPipelineStartupMixin,
    EditorPipelineSignalBridgeMixin,
    EditorPipelinePartialRerunMixin,
    EditorPipelineStatusMixin,
    EditorPipelineCompletionMixin,
    EditorPipelinePlayheadActionsMixin,
    EditorPipelineCleanupMixin,
):
    pass
