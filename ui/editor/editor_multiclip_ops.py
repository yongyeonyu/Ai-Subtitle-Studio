# Version: 03.14.05
# Phase: PHASE2
"""EditorWidget 멀티클립 파일 추가/삭제/리매핑 Mixin."""

from ui.editor.editor_segments_reload import EditorSegmentsReloadMixin
from ui.editor.editor_multiclip_transaction_flow import EditorMulticlipTransactionFlowMixin
from ui.editor.editor_multiclip_runtime_state import EditorMulticlipRuntimeStateMixin


class EditorMulticlipOpsMixin(
    EditorSegmentsReloadMixin,
    EditorMulticlipTransactionFlowMixin,
    EditorMulticlipRuntimeStateMixin,
):
    pass
