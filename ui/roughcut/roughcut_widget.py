# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

import random
from dataclasses import replace
from types import SimpleNamespace

from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence, QPainter, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QSize, QTimer, Qt, QVariantAnimation
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QComboBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QSplitterHandle,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.roughcut import build_title_suggestions, default_thumbnail_cache_dir, ensure_thumbnail
from core.roughcut.storyboard_graph import (
    STORYBOARD_CONNECTION_ROLE_COLORS,
    STORYBOARD_ROW_COUNT,
    STORYBOARD_ROW_LABELS,
    STORYBOARD_ROW_ROLE_NAMES,
    build_storyboard_layout_plan,
    selected_storyboard_connection_sequence,
    sorted_storyboard_nodes_by_grid,
    storyboard_row_duration_seconds,
)
from ui.settings.qml_panel import attach_qml_tab_bar
from ui.roughcut.roughcut_bottom_panel import RoughcutBottomPanel
from ui.roughcut.roughcut_export import RoughcutExportMixin
from ui.roughcut.roughcut_format import TABLE_COLUMNS, fmt_time
from ui.roughcut.roughcut_detail import RoughcutDetailMixin
from ui.roughcut.roughcut_log_panel import RoughcutLogPanel
from ui.roughcut.roughcut_major_panel import RoughcutMajorPanel
from ui.roughcut.roughcut_preview import RoughcutPreviewMixin
from ui.roughcut.roughcut_state import RoughcutStateMixin
from ui.roughcut.roughcut_style_panel import DEFAULT_ROUGHCUT_EXPORT_STYLE, RoughcutStylePanel
from ui.roughcut.roughcut_table import RoughcutTableMixin
from ui.roughcut.roughcut_title_panel import RoughcutTitlePanel
from ui.roughcut.editor import RoughcutStoryboardView
from ui.style import COLORS, button_style, label_style, line_icon, panel_style


_ROUGHCUT_FRAME_BOX_GAP = 6
_ROUGHCUT_FRAME_FLOATING_HANDLE_SIZE = 30
_ROUGHCUT_FRAME_MARKER_STROKE = 2
_ROUGHCUT_FRAME_MARKER_COLOR = COLORS["text"]
_ROUGHCUT_WIDTH_MARKER_STEM_X = 24
_ROUGHCUT_HEIGHT_MARKER_STEM_X = 6
_ROUGHCUT_VIDEO_DEFAULT_HEIGHT = 414
_ROUGHCUT_SETTINGS_DEFAULT_HEIGHT = 606
_ROUGHCUT_VIDEO_HOST_MIN_HEIGHT = 173
_ROUGHCUT_VIDEO_CONTROL_HEIGHT = 26
_ROUGHCUT_VIDEO_CONTROL_WIDTH = 32
_ROUGHCUT_VIDEO_PLAY_CONTROL_WIDTH = 36
_ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT = 30
_ROUGHCUT_MATERIAL_PREVIEW_COLUMNS = 7
_ROUGHCUT_MATERIAL_PREVIEW_ROWS = STORYBOARD_ROW_COUNT
_ROUGHCUT_MATERIAL_PREVIEW_ROW_ORDER = tuple(range(STORYBOARD_ROW_COUNT))
_ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT = _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS * _ROUGHCUT_MATERIAL_PREVIEW_ROWS
_ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE = 44
_ROUGHCUT_MATERIAL_PREVIEW_HALF_GRID_SIZE = _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE / 2
_ROUGHCUT_MATERIAL_PREVIEW_CARD_GRID_COLS = 3
_ROUGHCUT_MATERIAL_PREVIEW_CARD_GRID_ROWS = 2
_ROUGHCUT_MATERIAL_PREVIEW_GRID_GAP_CELLS = 2
_ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH = (
    _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE * _ROUGHCUT_MATERIAL_PREVIEW_CARD_GRID_COLS
)
_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT = (
    _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE * _ROUGHCUT_MATERIAL_PREVIEW_CARD_GRID_ROWS
)
_ROUGHCUT_MATERIAL_PREVIEW_NODE_STEP_X = (
    _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE
    * (_ROUGHCUT_MATERIAL_PREVIEW_CARD_GRID_COLS + _ROUGHCUT_MATERIAL_PREVIEW_GRID_GAP_CELLS)
)
_ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y = (
    _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE
    * (_ROUGHCUT_MATERIAL_PREVIEW_CARD_GRID_ROWS + _ROUGHCUT_MATERIAL_PREVIEW_GRID_GAP_CELLS)
)
_ROUGHCUT_STORY_START_DEFAULT_ROW = 2
_ROUGHCUT_STORY_CARD_X = 8
_ROUGHCUT_STORY_CARD_WIDTH = _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE * 2
_ROUGHCUT_STORY_CARD_HEIGHT = _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT
_ROUGHCUT_STORY_CARD_TOP_OFFSET = 0
_ROUGHCUT_MATERIAL_PREVIEW_START_X = (
    _ROUGHCUT_STORY_CARD_X
    + _ROUGHCUT_STORY_CARD_WIDTH
    + (_ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE * _ROUGHCUT_MATERIAL_PREVIEW_GRID_GAP_CELLS)
)
_ROUGHCUT_MATERIAL_PREVIEW_START_Y = 26
_ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH = (
    _ROUGHCUT_MATERIAL_PREVIEW_START_X
    + (_ROUGHCUT_MATERIAL_PREVIEW_COLUMNS * _ROUGHCUT_MATERIAL_PREVIEW_NODE_STEP_X)
)
_ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS = 8
_ROUGHCUT_MATERIAL_PREVIEW_PIN_HIT_RADIUS = 15
_ROUGHCUT_MATERIAL_PREVIEW_SCENE_HEIGHT = (
    _ROUGHCUT_MATERIAL_PREVIEW_START_Y
    + ((_ROUGHCUT_MATERIAL_PREVIEW_ROWS - 1) * _ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y)
    + _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT
    + _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE
)
_ROUGHCUT_MATERIAL_PREVIEW_SORT_ANIMATION_MS = 1200
_ROUGHCUT_MATERIAL_PREVIEW_SHADOW_COLOR = "#00C8FF"
_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES = STORYBOARD_ROW_ROLE_NAMES
_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS = STORYBOARD_CONNECTION_ROLE_COLORS
_ROUGHCUT_MATERIAL_PREVIEW_AUTO_SORT_ON_CONNECT = False
_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_ROWS = {
    role: index for index, role in enumerate(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES)
}
_ROUGHCUT_MATERIAL_PREVIEW_SOURCE_COLORS = (
    "#34C759",
    "#0A84FF",
    "#FF2D93",
    "#FF9F0A",
    "#AF52DE",
    "#64D2FF",
    "#FFD60A",
    "#30D158",
    "#BF5AF2",
    "#FF453A",
    "#5E5CE6",
    "#AC8E68",
)


class _RoughcutResizeHandle(QSplitterHandle):
    def __init__(self, orientation: Qt.Orientation, parent: QSplitter, marker: str, object_name: str):
        super().__init__(orientation, parent)
        self._marker = marker
        self._marker_anchor: QWidget | None = None
        self._marker_anchor_edge = "center"
        self.setObjectName(object_name)
        self.setAccessibleName(object_name)
        self.setMouseTracking(True)
        self.setToolTip("드래그해서 프레임 크기 조절")
        self.setCursor(
            Qt.CursorShape.SplitHCursor
            if orientation == Qt.Orientation.Horizontal
            else Qt.CursorShape.SplitVCursor
        )

    def sizeHint(self) -> QSize:
        return QSize(_ROUGHCUT_FRAME_BOX_GAP, _ROUGHCUT_FRAME_BOX_GAP)

    def set_marker_anchor(self, anchor: QWidget, edge: str = "center") -> None:
        self._marker_anchor = anchor
        self._marker_anchor_edge = edge
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        return


class _RoughcutFrameSplitter(QSplitter):
    def __init__(self, orientation: Qt.Orientation, marker: str, handle_object_name: str, parent: QWidget | None = None):
        super().__init__(orientation, parent)
        self._marker = marker
        self._handle_object_name = handle_object_name
        self.setChildrenCollapsible(False)
        self.setHandleWidth(_ROUGHCUT_FRAME_BOX_GAP)

    def createHandle(self) -> QSplitterHandle:  # noqa: N802 - Qt override
        return _RoughcutResizeHandle(self.orientation(), self, self._marker, self._handle_object_name)

    def refresh_handle_metadata(self) -> None:
        handle = self.handle(1)
        if handle is None:
            return
        handle.setObjectName(self._handle_object_name)
        handle.setAccessibleName(self._handle_object_name)

    def resize_handle(self) -> _RoughcutResizeHandle | None:
        handle = self.handle(1)
        if isinstance(handle, _RoughcutResizeHandle):
            return handle
        return None


class _RoughcutFloatingHandleMarker(QWidget):
    def __init__(self, marker: str, orientation: Qt.Orientation, splitter: QSplitter, parent: QWidget):
        super().__init__(parent)
        self._marker = marker
        self._orientation = orientation
        self._splitter = splitter
        self._drag_origin: QPoint | None = None
        self._drag_start_sizes: list[int] | None = None
        self._secondary_drag_start_sizes: list[int] | None = None
        self.setObjectName(
            "roughcut_width_resize_handle_visual"
            if orientation == Qt.Orientation.Horizontal
            else "roughcut_height_resize_handle_visual"
        )
        self.setAccessibleName(self.objectName())
        self.setFixedSize(_ROUGHCUT_FRAME_FLOATING_HANDLE_SIZE, _ROUGHCUT_FRAME_FLOATING_HANDLE_SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setToolTip("드래그해서 프레임 크기 조절")
        self.setCursor(
            Qt.CursorShape.SplitHCursor
            if orientation == Qt.Orientation.Horizontal
            else Qt.CursorShape.SplitVCursor
        )

    def paintEvent(self, event):  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(_ROUGHCUT_FRAME_MARKER_COLOR))
        pen.setWidth(_ROUGHCUT_FRAME_MARKER_STROKE)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if self._marker == "ㅓ":
            painter.drawLine(_ROUGHCUT_WIDTH_MARKER_STEM_X, 7, _ROUGHCUT_WIDTH_MARKER_STEM_X, 23)
            painter.drawLine(8, 15, _ROUGHCUT_WIDTH_MARKER_STEM_X, 15)
        else:
            painter.drawLine(_ROUGHCUT_HEIGHT_MARKER_STEM_X, 7, _ROUGHCUT_HEIGHT_MARKER_STEM_X, 23)
            painter.drawLine(_ROUGHCUT_HEIGHT_MARKER_STEM_X, 15, 22, 15)
        painter.end()

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._drag_origin = self._event_global_pos(event)
        self._drag_start_sizes = list(self._splitter.sizes())
        secondary_splitter = self._secondary_splitter()
        self._secondary_drag_start_sizes = list(secondary_splitter.sizes()) if secondary_splitter is not None else None
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        if self._drag_origin is None or not self._drag_start_sizes or len(self._drag_start_sizes) < 2:
            super().mouseMoveEvent(event)
            return
        current = self._event_global_pos(event)
        delta = current - self._drag_origin
        offset = delta.x() if self._orientation == Qt.Orientation.Horizontal else delta.y()
        self._apply_splitter_offset(self._splitter, self._drag_start_sizes, offset)
        secondary_splitter = self._secondary_splitter()
        if secondary_splitter is not None and self._secondary_drag_start_sizes:
            self._apply_splitter_offset(secondary_splitter, self._secondary_drag_start_sizes, delta.y())
        parent = self.parent()
        if parent is not None and hasattr(parent, "_sync_roughcut_handle_markers"):
            parent._sync_roughcut_handle_markers()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt override
        self._drag_origin = None
        self._drag_start_sizes = None
        self._secondary_drag_start_sizes = None
        event.accept()

    def _apply_splitter_offset(self, splitter: QSplitter, start_sizes: list[int], offset: int) -> None:
        if len(start_sizes) < 2:
            return
        total = max(2, sum(start_sizes[:2]))
        first = max(1, min(total - 1, start_sizes[0] + offset))
        splitter.setSizes([first, total - first])

    def _secondary_splitter(self) -> QSplitter | None:
        if self._orientation != Qt.Orientation.Horizontal:
            return None
        parent = self.parent()
        candidate = getattr(parent, "left_frame_splitter", None) if parent is not None else None
        if isinstance(candidate, QSplitter):
            return candidate
        return None

    def _event_global_pos(self, event) -> QPoint:
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        return event.globalPos()


class _RoughcutMaterialPreviewView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, owner: "RoughcutWidget"):
        super().__init__(scene)
        self._owner = owner
        self._drag_node_id = ""
        self._drag_offset = QPointF()
        self._drag_insert_shift = False
        self._connect_source_node = 0
        self._connect_source_side = "right"
        self._connect_started_on_press = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MouseButton.RightButton:
            source, target = self._owner._material_preview_connection_at_scene_pos(scene_pos)
            if source and target:
                self._owner._delete_material_preview_connection(source, target)
                event.accept()
                return
            node_id = self._owner._material_preview_node_id_at_scene_pos(scene_pos)
            if node_id:
                original_group = self._owner._material_card_preview_groups.get(node_id)
                original_pos = QPointF(original_group.pos()) if original_group is not None else QPointF(scene_pos)
                copied_node_id = self._owner._copy_material_preview_node_for_drag(
                    int(node_id.rsplit("_", 1)[1])
                )
                group = self._owner._material_card_preview_groups.get(copied_node_id)
                if group is not None and original_group is not None:
                    group.setPos(original_pos)
                    self._drag_node_id = copied_node_id
                    self._drag_offset = scene_pos - original_pos
                    self._drag_insert_shift = True
                    self._owner._begin_material_preview_node_drag(copied_node_id)
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
            super().mousePressEvent(event)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._connect_source_node:
            pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
            if pin_node and pin_side == "left":
                self._owner._connect_material_preview_nodes(
                    self._connect_source_node,
                    pin_node,
                    source_side=self._connect_source_side,
                    target_side=pin_side,
                    clear_routing_before_refresh=True,
                )
                self._connect_source_node = 0
                self._connect_source_side = "right"
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                event.accept()
                return
            if pin_node and pin_side == "right":
                self._connect_source_node = pin_node
                self._connect_source_side = pin_side
                self._connect_started_on_press = True
                self._owner._set_material_preview_connect_source(pin_node, pin_side)
                self._owner._set_material_preview_connect_cursor(scene_pos)
                self._owner._set_material_preview_hover_pin(pin_node, pin_side)
                self.setCursor(Qt.CursorShape.CrossCursor)
                event.accept()
                return
        pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
        if pin_node and pin_side in {"left", "right"}:
            self._connect_source_node = pin_node
            self._connect_source_side = pin_side
            self._connect_started_on_press = True
            self._owner._set_material_preview_connect_source(pin_node, pin_side)
            self._owner._set_material_preview_connect_cursor(scene_pos)
            self._owner._set_material_preview_hover_pin(pin_node, pin_side)
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        source, target = self._owner._material_preview_connection_at_scene_pos(scene_pos)
        if source and target:
            self._owner._cycle_material_preview_connection_role(source, target)
            event.accept()
            return
        node_id = self._owner._material_preview_node_id_at_scene_pos(scene_pos)
        if not node_id:
            super().mousePressEvent(event)
            return
        self._owner._select_material_preview_parallel_target(int(node_id.rsplit("_", 1)[1]))
        group = self._owner._material_card_preview_groups.get(node_id)
        if group is None:
            super().mousePressEvent(event)
            return
        self._drag_node_id = node_id
        self._drag_offset = scene_pos - group.pos()
        self._drag_insert_shift = False
        self._owner._begin_material_preview_node_drag(node_id)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._connect_source_node:
            self._owner._set_material_preview_connect_cursor(scene_pos)
            pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
            if pin_side != "left":
                pin_node, pin_side = 0, ""
            if pin_node != self._connect_source_node or pin_side != self._connect_source_side:
                self._connect_started_on_press = False
            self._owner._set_material_preview_hover_pin(pin_node, pin_side)
            event.accept()
            return
        if not self._drag_node_id:
            pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
            self._owner._set_material_preview_hover_pin(pin_node, pin_side)
            if pin_node:
                self._owner._set_material_preview_hover_connection(0, 0)
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                source, target = self._owner._material_preview_connection_at_scene_pos(scene_pos)
                self._owner._set_material_preview_hover_connection(source, target)
                self.setCursor(Qt.CursorShape.PointingHandCursor if source and target else Qt.CursorShape.OpenHandCursor)
            super().mouseMoveEvent(event)
            return
        self._owner._drag_material_preview_node_to(self._drag_node_id, scene_pos - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt override
        if self._connect_source_node:
            source = self._connect_source_node
            scene_pos = self.mapToScene(event.position().toPoint())
            target, target_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
            if self._connect_started_on_press and target == source and target_side == self._connect_source_side:
                self._connect_started_on_press = False
                self._owner._set_material_preview_connect_cursor(scene_pos)
                self.setCursor(Qt.CursorShape.CrossCursor)
                event.accept()
                return
            if target and target_side == "left":
                self._owner._connect_material_preview_nodes(
                    source,
                    target,
                    source_side=self._connect_source_side,
                    target_side=target_side,
                    clear_routing_before_refresh=True,
                )
                self._connect_source_node = 0
                self._connect_source_side = "right"
                self._connect_started_on_press = False
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self._owner._set_material_preview_connect_cursor(scene_pos)
                self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        if not self._drag_node_id:
            super().mouseReleaseEvent(event)
            return
        node_id = self._drag_node_id
        scene_pos = self.mapToScene(event.position().toPoint())
        insert_shift = self._drag_insert_shift
        self._drag_node_id = ""
        self._drag_offset = QPointF()
        self._drag_insert_shift = False
        self._owner._finish_material_preview_node_drag(
            node_id,
            scene_pos,
            insert_shift=insert_shift,
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        event.accept()

    def leaveEvent(self, event):  # noqa: N802 - Qt override
        self._owner._set_material_preview_hover_pin(0, "")
        self._owner._set_material_preview_hover_connection(0, 0)
        if not self._connect_source_node:
            self._owner._set_material_preview_connect_cursor(None)
        super().leaveEvent(event)

    def keyPressEvent(self, event):  # noqa: N802 - Qt override
        if event.matches(QKeySequence.StandardKey.Copy):
            self._owner._copy_material_preview_selection()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self._owner._paste_material_preview_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)


class RoughcutWidget(
    RoughcutExportMixin,
    RoughcutDetailMixin,
    RoughcutPreviewMixin,
    RoughcutTableMixin,
    RoughcutStateMixin,
    QWidget,
):
    def __init__(self, owner=None, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.uses_integrated_bottom_frame = True
        self._attached_video_editor = None
        self._attached_video_frame = None
        self._attached_video_frame_minimum_size = None
        self._result = None
        self._source_signature = ""
        self._roughcut_candidates: list[dict] = []
        self._selected_candidate_id = ""
        self._segment_order: list[str] = []
        self._chapter_order: list[str] = []
        self._recent_reorder_summary = ""
        self._chapter_thumbnail_lookup_cache: dict[str, str] = {}
        self._chapter_thumbnail_lookup_media_path = ""
        self._refreshing_candidate_combo = False
        self._restored_selected_chapter_id = ""
        self._restored_safety_filter = "전체"
        self._row_chapter_ids: list[str] = []
        self._user_edits: dict[str, dict[str, str]] = {}
        self._updating_table = False
        self._preview_row = -1
        self._preview_end = 0.0
        self._preview_deadline_ms = 0
        self._preview_is_hover = False
        self._preview_loop_enabled = False
        self._roughcut_updating_player_slider = False
        self._sequence_preview_active = False
        self._sequence_preview_rows: list[int] = []
        self._sequence_preview_index = -1
        self._restore_volume: float | None = None
        self._render_thread = None
        self._render_worker = None
        self._last_render_plan = None
        self._last_failed_render_plan = None
        self._roughcut_export_style = dict(DEFAULT_ROUGHCUT_EXPORT_STYLE)
        self._roughcut_export_style_overridden = False
        self._render_log_lines: list[str] = []
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._preview_tick)
        self._candidate_preview_buttons: list[QPushButton] = []
        self._candidate_preview_empty_lbl = None
        self._candidate_preview_filter = "all"
        self.setStyleSheet(f"background: {COLORS['bg']}; color: {COLORS['text']};")
        self._build_ui()

    def compact_for_home_navigation(self) -> None:
        self.release_editor_video_frame()
        stop_preview = getattr(self, "_stop_preview", None)
        if callable(stop_preview):
            try:
                stop_preview()
            except Exception:
                pass
        try:
            self._preview_timer.stop()
        except Exception:
            pass
        if getattr(self, "_render_thread", None) is not None:
            return
        self._result = None
        self._source_signature = ""
        try:
            self._set_empty_state()
        except Exception:
            pass

    def run_main_action(self) -> None:
        """Route the global Start button to roughcut analysis while this page is active."""
        if self._subtitle_generation_active():
            self._set_roughcut_status("자막 생성 중")
            self.preview_summary_lbl.setText("자막 생성이 끝난 뒤 러프컷 분석을 시작할 수 있습니다.")
            return
        self._set_roughcut_status("읽는 중", 15)
        self._append_roughcut_log("에디터 자막을 러프컷 분석 입력으로 읽습니다.")
        self.refresh_from_editor(force_reanalyze=True, analyze_if_missing=True)
        self._set_roughcut_status("분석 완료" if self._result is not None else "분석 대기", 100 if self._result is not None else None)

    def _subtitle_generation_active(self) -> bool:
        owner = self.owner
        backend = getattr(owner, "backend", None) if owner is not None else None
        if bool(getattr(backend, "_active", False)):
            return True
        editor = self._active_editor()
        if editor is None:
            return False
        try:
            from core.state_manager import SubtitleStateManager

            return getattr(getattr(editor, "sm", None), "state", None) == SubtitleStateManager.ST_PROC
        except Exception:
            return bool(getattr(editor, "_is_ai_processing", False))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        self.safety_filter_combo = self._build_safety_filter_combo()

        main_splitter = _RoughcutFrameSplitter(
            Qt.Orientation.Horizontal,
            "ㅓ",
            "roughcut_width_resize_handle",
        )
        self.roughcut_frame_splitter = main_splitter
        root.addWidget(main_splitter, stretch=1)

        self.roughcut_frame = QFrame()
        self.roughcut_frame.setObjectName("RoughcutScenarioMaterialHost")
        self.roughcut_frame.setStyleSheet(
            f"QFrame#RoughcutScenarioMaterialHost {{ background: {COLORS['surface']}; border: none; border-radius: 0px; }}"
        )
        left_lay = QVBoxLayout(self.roughcut_frame)
        left_lay.setContentsMargins(6, 6, 6, 6)
        left_lay.setSpacing(6)
        self.scenario_box = self._build_frame_only_box("scenario_box", "#F5F7FA")
        self._build_scenario_sequence_preview_surface(self.scenario_box)
        self.material_box = self._build_frame_only_box("material_box", "#0A84FF")
        self._build_material_card_preview_surface(self.material_box)
        self.left_frame_splitter = _RoughcutFrameSplitter(
            Qt.Orientation.Vertical,
            "ㅓ",
            "roughcut_left_height_resize_handle",
        )
        self.left_frame_splitter.addWidget(self.scenario_box)
        self.left_frame_splitter.addWidget(self.material_box)
        self.left_frame_splitter.setStretchFactor(0, 1)
        self.left_frame_splitter.setStretchFactor(1, 1)
        self.left_frame_splitter.setSizes([420, 420])
        self.left_frame_splitter.refresh_handle_metadata()
        left_lay.addWidget(self.left_frame_splitter, stretch=1)

        self._legacy_left_host = self._build_hidden_legacy_host(self.roughcut_frame)
        legacy_left_lay = QVBoxLayout(self._legacy_left_host)
        legacy_left_lay.setContentsMargins(0, 0, 0, 0)
        legacy_left_lay.setSpacing(0)
        self.candidate_preview_frame = self._build_candidate_preview_frame()
        legacy_left_lay.addWidget(self.candidate_preview_frame)
        self.major_panel = RoughcutMajorPanel()
        self.major_panel.minorSelected.connect(self._select_chapter_id_from_major_panel)
        self.major_panel.previewRequested.connect(self._preview_chapter_id_from_major_panel)
        self.major_panel.segmentOrderChanged.connect(self._on_major_segment_order_changed)
        self.major_panel.chapterOrderChanged.connect(self._on_major_chapter_order_changed)
        self.table = self._build_table()
        legacy_left_lay.addWidget(self.major_panel)
        main_splitter.addWidget(self.roughcut_frame)

        side = QFrame()
        side.setObjectName("RoughcutVideoSettingsHost")
        side.setStyleSheet(
            f"QFrame#RoughcutVideoSettingsHost {{ background: {COLORS['surface']}; border: none; border-radius: 0px; }}"
        )
        self.roughcut_side_frame = side
        side.setMinimumWidth(396)
        side.setMaximumWidth(468)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(6, 6, 6, 6)
        side_lay.setSpacing(6)
        self.video_box = self._build_frame_only_box("video_box", "#2D3942")
        self._build_roughcut_video_player_surface(self.video_box)
        self.settings_box = self._build_frame_only_box("settings_box", "#FF453A")
        self._build_settings_control_surface(self.settings_box)
        self.right_frame_splitter = _RoughcutFrameSplitter(
            Qt.Orientation.Vertical,
            "ㅏ",
            "roughcut_height_resize_handle",
        )
        self.right_frame_splitter.addWidget(self.video_box)
        self.right_frame_splitter.addWidget(self.settings_box)
        self.right_frame_splitter.setStretchFactor(0, 4)
        self.right_frame_splitter.setStretchFactor(1, 5)
        self.right_frame_splitter.setSizes([_ROUGHCUT_VIDEO_DEFAULT_HEIGHT, _ROUGHCUT_SETTINGS_DEFAULT_HEIGHT])
        self.right_frame_splitter.refresh_handle_metadata()
        side_lay.addWidget(self.right_frame_splitter, stretch=1)

        self._legacy_side_host = self._build_hidden_legacy_host(side)
        legacy_side_lay = QVBoxLayout(self._legacy_side_host)
        legacy_side_lay.setContentsMargins(0, 0, 0, 0)
        legacy_side_lay.setSpacing(0)
        self.video_bridge_frame = QFrame()
        self.video_bridge_frame.setStyleSheet("QFrame { background: #0A0F12; border: 1px solid #2D3942; border-radius: 8px; }")
        self.video_bridge_layout = QVBoxLayout(self.video_bridge_frame)
        self.video_bridge_layout.setContentsMargins(8, 8, 8, 8)
        self.video_bridge_layout.setSpacing(6)
        self.video_bridge_title_lbl = QLabel("비디오 플레이어")
        self.video_bridge_title_lbl.setStyleSheet(label_style("text", 11, bold=True))
        self.video_bridge_hint_lbl = QLabel("러프컷 카드 순서에 맞춰 현재 에디터 플레이어를 그대로 확인합니다.")
        self.video_bridge_hint_lbl.setStyleSheet(label_style("muted", 9))
        self._legacy_video_host = QFrame()
        self._legacy_video_host.setStyleSheet("QFrame { background: #000000; border: 1px solid #1D2730; border-radius: 8px; }")
        self._legacy_video_host_layout = QVBoxLayout(self._legacy_video_host)
        self._legacy_video_host_layout.setContentsMargins(0, 0, 0, 0)
        self._legacy_video_host_layout.setSpacing(0)
        self._legacy_video_host_placeholder = QLabel("현재 에디터 비디오 플레이어를 여기에 유지합니다.")
        self._legacy_video_host_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._legacy_video_host_placeholder.setMinimumHeight(188)
        self._legacy_video_host_placeholder.setStyleSheet(label_style("muted", 10))
        self._legacy_video_host_layout.addWidget(self._legacy_video_host_placeholder)
        self.video_bridge_layout.addWidget(self.video_bridge_title_lbl)
        self.video_bridge_layout.addWidget(self.video_bridge_hint_lbl)
        self.video_bridge_layout.addWidget(self._legacy_video_host, stretch=1)
        legacy_side_lay.addWidget(self.video_bridge_frame)
        self.player_menu_frame = self._build_player_menu_frame()
        legacy_side_lay.addWidget(self.player_menu_frame)

        self.bottom_panel = self._build_bottom_panel()
        self.bottom_tabs = RoughcutBottomPanel(self.bottom_panel)
        self.bottom_tabs.tabs.insertTab(0, self.table, "챕터")
        self.guide_text = QTextEdit()
        self.guide_text.setReadOnly(True)
        self.guide_text.setStyleSheet(
            "QTextEdit { background: #11181C; color: #DCE3EA; border: 1px solid #2D3942; "
            "border-radius: 7px; padding: 10px; font-size: 11px; }"
        )
        self.log_panel = RoughcutLogPanel()
        self.title_panel = RoughcutTitlePanel()
        self.style_panel = RoughcutStylePanel()
        self.title_panel.refreshRequested.connect(self._refresh_title_suggestions)
        self.style_panel.styleSaved.connect(self._save_roughcut_export_style)
        self.bottom_tabs.tabs.addTab(self.log_panel, "로그")
        legacy_side_lay.addWidget(self.bottom_tabs)
        main_splitter.addWidget(side)
        main_splitter.setStretchFactor(0, 6)
        main_splitter.setStretchFactor(1, 2)
        main_splitter.setSizes([1640, 420])
        main_splitter.refresh_handle_metadata()
        width_handle = main_splitter.resize_handle()
        height_handle = self.right_frame_splitter.resize_handle()
        if width_handle is not None and height_handle is not None:
            width_handle.set_marker_anchor(self.material_box, edge="top")
            height_handle.set_marker_anchor(width_handle)
        self.width_handle_marker = _RoughcutFloatingHandleMarker("ㅓ", Qt.Orientation.Horizontal, main_splitter, self)
        self.height_handle_marker = _RoughcutFloatingHandleMarker("ㅏ", Qt.Orientation.Vertical, self.right_frame_splitter, self)
        self.width_handle_marker.show()
        self.height_handle_marker.show()
        main_splitter.splitterMoved.connect(lambda *_args: self._sync_roughcut_handle_markers())
        self.left_frame_splitter.splitterMoved.connect(lambda *_args: self._sync_roughcut_handle_markers())
        self.right_frame_splitter.splitterMoved.connect(lambda *_args: self._sync_roughcut_handle_markers())
        QTimer.singleShot(0, self._sync_roughcut_handle_markers)

        self._set_empty_state()

    def resizeEvent(self, event):  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._sync_roughcut_handle_markers()

    def _roughcut_left_handle_center_y(self) -> int:
        scenario_box = getattr(self, "scenario_box", None)
        material_box = getattr(self, "material_box", None)
        width_handle = getattr(getattr(self, "roughcut_frame_splitter", None), "handle", lambda _index: None)(1)
        if scenario_box is not None and material_box is not None:
            scenario_bottom_y = scenario_box.mapTo(self, QPoint(0, scenario_box.height())).y()
            material_top_y = material_box.mapTo(self, QPoint(0, 0)).y()
            return (scenario_bottom_y + material_top_y) // 2
        if width_handle is not None:
            return width_handle.mapTo(self, width_handle.rect().center()).y()
        return self.height() // 2

    def _sync_roughcut_handle_markers(self) -> None:
        width_marker = getattr(self, "width_handle_marker", None)
        height_marker = getattr(self, "height_handle_marker", None)
        main_splitter = getattr(self, "roughcut_frame_splitter", None)
        right_splitter = getattr(self, "right_frame_splitter", None)
        if width_marker is None or height_marker is None or main_splitter is None or right_splitter is None:
            return
        width_handle = main_splitter.handle(1)
        height_handle = right_splitter.handle(1)
        if width_handle is None or height_handle is None:
            return
        split_x = width_handle.mapTo(self, width_handle.rect().center()).x()
        material_gap_center_y = self._roughcut_left_handle_center_y()
        material_box = getattr(self, "material_box", None)
        if material_box is not None:
            width_corner_x = material_box.mapTo(self, QPoint(material_box.width(), 0)).x()
        else:
            width_corner_x = split_x
        width_marker.move(
            width_corner_x - _ROUGHCUT_WIDTH_MARKER_STEM_X,
            material_gap_center_y - (width_marker.height() // 2),
        )

        settings_box = getattr(self, "settings_box", None)
        if settings_box is not None:
            height_corner = settings_box.mapTo(self, QPoint(0, 0))
            video_box = getattr(self, "video_box", None)
            if video_box is not None:
                video_bottom_y = video_box.mapTo(self, QPoint(0, video_box.height())).y()
                height_y = (video_bottom_y + height_corner.y()) // 2
            else:
                height_y = height_corner.y()
            height_x = height_corner.x() - _ROUGHCUT_HEIGHT_MARKER_STEM_X
        else:
            height_x = split_x + _ROUGHCUT_FRAME_BOX_GAP
            height_y = height_handle.mapTo(self, height_handle.rect().center()).y()
        height_marker.move(
            height_x,
            height_y - (height_marker.height() // 2),
        )
        width_marker.raise_()
        height_marker.raise_()

    def _build_frame_only_box(self, object_name: str, border_color: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(object_name)
        frame.setStyleSheet(
            f"QFrame#{object_name} {{ "
            "background: #0A0F12; "
            f"border: 2px solid {border_color}; "
            "border-radius: 8px; "
            "}"
        )
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return frame

    def _build_scenario_sequence_preview_surface(self, frame: QFrame) -> None:
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(0)

        self.scenario_sequence_scene = QGraphicsScene(frame)
        self.scenario_sequence_scene.setSceneRect(0, 0, 1200, 160)
        self.scenario_sequence_view = QGraphicsView(self.scenario_sequence_scene)
        self.scenario_sequence_view.setObjectName("roughcutScenarioSelectedPathPreview")
        self.scenario_sequence_view.setAccessibleName("시나리오 선택 경로 미리보기")
        self.scenario_sequence_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.scenario_sequence_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.scenario_sequence_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scenario_sequence_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scenario_sequence_view.setFrameShape(QFrame.Shape.NoFrame)
        self.scenario_sequence_view.setStyleSheet(
            "QGraphicsView#roughcutScenarioSelectedPathPreview { background: transparent; border: none; }"
        )
        self.scenario_sequence_cards: list[dict[str, object]] = []
        self.scenario_sequence_summaries: list[dict[str, object]] = []
        self.scenario_sequence_layer = "sequence"
        self.scenario_sequence_detail: dict[str, object] = {}
        lay.addWidget(self.scenario_sequence_view, stretch=1)

    def _build_settings_control_surface(self, frame: QFrame) -> None:
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self.scenario_generate_btn = QPushButton("시나리오생성")
        self.scenario_generate_btn.setObjectName("roughcutScenarioGenerateButton")
        self.scenario_generate_btn.setStyleSheet(button_style("primary", font_size="11px", padding="6px 10px"))
        self.scenario_generate_btn.clicked.connect(self._generate_material_preview_scenario)
        self.material_multi_select_btn = QPushButton("멀티선택")
        self.material_multi_select_btn.setObjectName("roughcutMaterialMultiSelectButton")
        self.material_multi_select_btn.setCheckable(True)
        self.material_multi_select_btn.setStyleSheet(button_style("toolbar", font_size="11px", padding="6px 10px"))
        self.material_multi_select_btn.clicked.connect(self._toggle_material_multi_select)
        self.material_merge_btn = QPushButton("합치기")
        self.material_merge_btn.setObjectName("roughcutMaterialMergeButton")
        self.material_merge_btn.setStyleSheet(button_style("toolbar", font_size="11px", padding="6px 10px"))
        self.material_merge_btn.clicked.connect(self._merge_material_preview_selection)
        self.material_split_btn = QPushButton("분할")
        self.material_split_btn.setObjectName("roughcutMaterialSplitButton")
        self.material_split_btn.setStyleSheet(button_style("toolbar", font_size="11px", padding="6px 10px"))
        self.material_split_btn.clicked.connect(self._split_material_preview_selection)
        self.material_delete_btn = QPushButton("삭제")
        self.material_delete_btn.setObjectName("roughcutMaterialDeleteButton")
        self.material_delete_btn.setStyleSheet(button_style("danger", font_size="11px", padding="6px 10px"))
        self.material_delete_btn.clicked.connect(self._delete_material_preview_selection)
        trim_row = QHBoxLayout()
        trim_row.setContentsMargins(0, 0, 0, 0)
        trim_row.setSpacing(4)
        self.material_trim_left_minus_btn = QPushButton("좌-")
        self.material_trim_left_plus_btn = QPushButton("좌+")
        self.material_trim_right_minus_btn = QPushButton("우-")
        self.material_trim_right_plus_btn = QPushButton("우+")
        for button in (
            self.material_trim_left_minus_btn,
            self.material_trim_left_plus_btn,
            self.material_trim_right_minus_btn,
            self.material_trim_right_plus_btn,
        ):
            button.setStyleSheet(button_style("toolbar", font_size="10px", padding="4px 6px"))
            trim_row.addWidget(button)
        self.material_trim_left_minus_btn.clicked.connect(lambda: self._adjust_material_preview_trim("left", -1))
        self.material_trim_left_plus_btn.clicked.connect(lambda: self._adjust_material_preview_trim("left", 1))
        self.material_trim_right_minus_btn.clicked.connect(lambda: self._adjust_material_preview_trim("right", -1))
        self.material_trim_right_plus_btn.clicked.connect(lambda: self._adjust_material_preview_trim("right", 1))

        for button in (
            self.scenario_generate_btn,
            self.material_multi_select_btn,
            self.material_merge_btn,
            self.material_split_btn,
            self.material_delete_btn,
        ):
            lay.addWidget(button)
        lay.addLayout(trim_row)
        lay.addStretch(1)

    def _build_material_card_preview_surface(self, frame: QFrame) -> None:
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        self.material_random_connect_btn = QPushButton("랜덤 연결")
        self.material_random_connect_btn.setObjectName("roughcutMaterialRandomConnectButton")
        self.material_random_connect_btn.setToolTip("데모용 랜덤 순서선을 생성")
        self.material_random_connect_btn.setStyleSheet(button_style("toolbar", font_size="10px", padding="5px 8px"))
        self.material_random_connect_btn.clicked.connect(self._randomize_material_preview_connections)
        self.material_r_sort_btn = QPushButton("자동정렬")
        self.material_r_sort_btn.setObjectName("roughcutMaterialRSortButton")
        self.material_r_sort_btn.setToolTip("연결 순서를 왼쪽부터 오른쪽 시간축으로 자동 정렬")
        self.material_r_sort_btn.setStyleSheet(button_style("primary", font_size="10px", padding="5px 8px"))
        self.material_r_sort_btn.clicked.connect(self._apply_material_preview_r_order_from_connections)
        controls.addWidget(self.material_random_connect_btn)
        controls.addWidget(self.material_r_sort_btn)
        controls.addStretch(1)
        lay.addLayout(controls)

        self.material_card_preview_scene = QGraphicsScene(frame)
        self.material_card_preview_page_count = (
            (_ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT + _ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT - 1)
            // _ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT
        )
        self.material_card_preview_scene.setSceneRect(
            0,
            0,
            max(1, self.material_card_preview_page_count) * _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH,
            _ROUGHCUT_MATERIAL_PREVIEW_SCENE_HEIGHT,
        )
        self.material_card_preview_order = list(range(1, _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT + 1))
        self.material_card_preview_connections: dict[int, list[int]] = {}
        self.material_card_preview_connection_roles: dict[tuple[int, int], str] = {}
        self.material_card_parallel_selections: dict[int, int] = {}
        self.material_card_preview_grid_slots: dict[int, tuple[int, int]] = self._initial_material_preview_grid_slots(
            self.material_card_preview_order
        )
        self.material_card_preview_source_nodes: dict[int, int] = {
            node: node for node in self.material_card_preview_order
        }
        self.material_card_preview_clipboard: list[int] = []
        self.material_card_preview_next_node = _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT + 1
        self.material_card_preview_hover_pin: tuple[int, str] = (0, "")
        self.material_card_preview_connect_source = 0
        self.material_card_preview_connect_source_side = "right"
        self.material_card_preview_connect_cursor: QPointF | None = None
        self.material_card_preview_connection_shadow_path = QPainterPath()
        self.material_card_preview_hover_connection: tuple[int, int] = (0, 0)
        self.material_card_preview_hover_copy_target: dict[str, object] = {}
        self.material_card_preview_connection_paths: dict[tuple[int, int], QPainterPath] = {}
        self.material_card_preview_connection_sides: dict[tuple[int, int], tuple[str, str]] = {}
        self.material_card_preview_lane_connections: dict[int, int] = {}
        self.material_card_preview_lane_parallel_connections: dict[int, list[int]] = {}
        self.material_card_preview_lane_connection_roles: dict[tuple[int, int], str] = {}
        self.material_story_card_rows: list[int] = [_ROUGHCUT_STORY_START_DEFAULT_ROW]
        self.material_story_card_labels: dict[int, str] = {_ROUGHCUT_STORY_START_DEFAULT_ROW: "메인"}
        self.material_card_preview_parallel_column_counts: tuple[int, ...] = ()
        self.material_card_preview_drag_shadow_slot = 0
        self.material_card_preview_drag_shadow_rect: QRectF | None = None
        self.material_card_preview_drag_shadow_item = None
        self.material_card_preview_selected_node = 1
        self.material_card_preview_multi_select_enabled = False
        self.material_card_preview_multi_selection: list[int] = []
        self.material_card_preview_generated_order: list[int] = []
        self.material_card_preview_deleted_nodes: set[int] = set()
        self.material_card_preview_merged_nodes: dict[int, list[int]] = {}
        self.material_card_preview_split_children: dict[int, list[int]] = {}
        self.material_card_preview_trim_state: dict[int, dict[str, int]] = {}
        self.material_card_preview_last_reorder: dict[str, object] = {}
        self.material_card_preview_last_auto_copy: dict[str, object] = {}
        self.material_card_preview_last_animation: dict[str, object] = {}
        self.material_card_preview_sort_vectors: list[dict[str, object]] = []
        self._material_card_preview_animations: list[QVariantAnimation] = []
        self._material_card_preview_groups: dict[str, object] = {}
        self.material_card_preview_view = RoughcutStoryboardView(self.material_card_preview_scene, self)
        self.material_card_preview_view.setObjectName("roughcutMaterialMiroUmlPreview")
        self.material_card_preview_view.setAccessibleName("중분류 카드 Miro UML 미리보기")
        self.material_card_preview_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.material_card_preview_view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.material_card_preview_view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.material_card_preview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.material_card_preview_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.material_card_preview_view.setFrameShape(QFrame.Shape.NoFrame)
        self.material_card_preview_view.setStyleSheet(
            "QGraphicsView#roughcutMaterialMiroUmlPreview { background: transparent; border: none; }"
        )
        self.material_card_preview_nodes: list[dict[str, object]] = []
        self._populate_material_miro_uml_preview_scene()
        lay.addWidget(self.material_card_preview_view, stretch=1)
        QTimer.singleShot(0, self._scroll_material_preview_to_story_start)
        self._refresh_scenario_sequence_preview()

    def _scroll_material_preview_to_story_start(self) -> None:
        view = getattr(self, "material_card_preview_view", None)
        if view is None:
            return
        view.horizontalScrollBar().setValue(view.horizontalScrollBar().minimum())
        story_rect = self._material_preview_story_card_rect(_ROUGHCUT_STORY_START_DEFAULT_ROW)
        target_y = int(max(view.verticalScrollBar().minimum(), story_rect.top() - _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE))
        view.verticalScrollBar().setValue(min(target_y, view.verticalScrollBar().maximum()))

    def _roughcut_material_preview_state_payload(self) -> dict[str, object]:
        connections = {
            str(source): [int(target) for target in targets]
            for source, targets in getattr(self, "material_card_preview_connections", {}).items()
        }
        connection_roles = [
            {"source": int(source), "target": int(target), "role": str(role)}
            for (source, target), role in getattr(self, "material_card_preview_connection_roles", {}).items()
        ]
        connection_sides = [
            {
                "source": int(source),
                "target": int(target),
                "source_side": str(sides[0] if sides else "right"),
                "target_side": str(sides[1] if len(sides) > 1 else "left"),
            }
            for (source, target), sides in getattr(self, "material_card_preview_connection_sides", {}).items()
        ]
        lane_roles = [
            {"row": int(row), "target": int(target), "role": str(role)}
            for (row, target), role in getattr(self, "material_card_preview_lane_connection_roles", {}).items()
        ]
        return {
            "schema": "ai_subtitle_studio.roughcut_material_storyboard.v1",
            "schema_version": "roughcut_material_storyboard.v1",
            "card_move_grid_step": 1,
            "connector_route_grid_step": 0.5,
            "node_count": _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT,
            "order": [int(node) for node in getattr(self, "material_card_preview_order", [])],
            "grid_slots": {
                str(node): {"row": int(slot[0]), "col": int(slot[1])}
                for node, slot in getattr(self, "material_card_preview_grid_slots", {}).items()
            },
            "source_nodes": {
                str(node): int(source)
                for node, source in getattr(self, "material_card_preview_source_nodes", {}).items()
            },
            "next_node": int(getattr(self, "material_card_preview_next_node", _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT + 1)),
            "connections": connections,
            "connection_roles": connection_roles,
            "connection_sides": connection_sides,
            "parallel_selections": {
                str(source): int(target)
                for source, target in getattr(self, "material_card_parallel_selections", {}).items()
            },
            "parallel_column_counts": [
                int(count) for count in getattr(self, "material_card_preview_parallel_column_counts", ()) or ()
            ],
            "lane_connections": {
                str(row): int(target)
                for row, target in getattr(self, "material_card_preview_lane_connections", {}).items()
            },
            "lane_parallel_connections": {
                str(row): [int(target) for target in targets]
                for row, targets in getattr(self, "material_card_preview_lane_parallel_connections", {}).items()
            },
            "lane_connection_roles": lane_roles,
            "story_card_rows": [int(row) for row in getattr(self, "material_story_card_rows", [])],
            "story_card_labels": {
                str(row): str(label)
                for row, label in getattr(self, "material_story_card_labels", {}).items()
            },
            "selected_node": int(getattr(self, "material_card_preview_selected_node", 0) or 0),
            "multi_select_enabled": bool(getattr(self, "material_card_preview_multi_select_enabled", False)),
            "multi_selection": [int(node) for node in getattr(self, "material_card_preview_multi_selection", [])],
            "generated_order": [int(node) for node in getattr(self, "material_card_preview_generated_order", [])],
            "deleted_nodes": sorted(int(node) for node in getattr(self, "material_card_preview_deleted_nodes", set())),
            "merged_nodes": {
                str(node): [int(child) for child in children]
                for node, children in getattr(self, "material_card_preview_merged_nodes", {}).items()
            },
            "split_children": {
                str(node): [int(child) for child in children]
                for node, children in getattr(self, "material_card_preview_split_children", {}).items()
            },
            "trim_state": {
                str(node): {
                    "left": int(state.get("left", 0)),
                    "right": int(state.get("right", 0)),
                }
                for node, state in getattr(self, "material_card_preview_trim_state", {}).items()
                if isinstance(state, dict)
            },
            "clipboard": [int(node) for node in getattr(self, "material_card_preview_clipboard", [])],
            "scenario_sequence_layer": str(getattr(self, "scenario_sequence_layer", "sequence") or "sequence"),
            "last_reorder": dict(getattr(self, "material_card_preview_last_reorder", {}) or {}),
            "last_auto_copy": dict(getattr(self, "material_card_preview_last_auto_copy", {}) or {}),
        }

    def _restore_roughcut_material_preview_state(self, payload: dict[str, object] | None) -> None:
        if not isinstance(payload, dict):
            return

        def _int_list(value: object) -> list[int]:
            out: list[int] = []
            for item in list(value or []) if isinstance(value, (list, tuple, set)) else []:
                try:
                    out.append(int(item))
                except (TypeError, ValueError):
                    continue
            return out

        source_nodes_raw = payload.get("source_nodes")
        source_nodes: dict[int, int] = {}
        if isinstance(source_nodes_raw, dict):
            for raw_node, raw_source in source_nodes_raw.items():
                try:
                    node = int(raw_node)
                    source_nodes[node] = int(raw_source)
                except (TypeError, ValueError):
                    continue
        order = [node for node in _int_list(payload.get("order")) if node in source_nodes or node > 0]
        if not order:
            order = list(range(1, _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT + 1))
        for node in order:
            source_nodes.setdefault(node, node)
        self.material_card_preview_order = list(dict.fromkeys(order))
        self.material_card_preview_source_nodes = {
            node: source_nodes.get(node, node)
            for node in sorted(set(source_nodes).union(self.material_card_preview_order))
        }

        slots: dict[int, tuple[int, int]] = {}
        grid_slots_raw = payload.get("grid_slots")
        if isinstance(grid_slots_raw, dict):
            for raw_node, raw_slot in grid_slots_raw.items():
                if not isinstance(raw_slot, dict):
                    continue
                try:
                    node = int(raw_node)
                    row = max(0, min(_ROUGHCUT_MATERIAL_PREVIEW_ROWS - 1, int(raw_slot.get("row", 0))))
                    col = max(0, int(raw_slot.get("col", 0)))
                except (TypeError, ValueError):
                    continue
                slots[node] = (row, col)
        fallback_slots = self._initial_material_preview_grid_slots(self.material_card_preview_order)
        for node in self.material_card_preview_order:
            slots.setdefault(node, fallback_slots.get(node, (0, 0)))
        self.material_card_preview_grid_slots = slots

        deleted_nodes = set(_int_list(payload.get("deleted_nodes")))
        self.material_card_preview_deleted_nodes = {
            node for node in deleted_nodes if node in self.material_card_preview_source_nodes
        }
        active_set = set(self._active_material_preview_order())

        self.material_card_preview_connections = {}
        connections_raw = payload.get("connections")
        if isinstance(connections_raw, dict):
            for raw_source, raw_targets in connections_raw.items():
                try:
                    source = int(raw_source)
                except (TypeError, ValueError):
                    continue
                targets = [target for target in _int_list(raw_targets) if target in active_set]
                if source in active_set and targets:
                    self.material_card_preview_connections[source] = list(dict.fromkeys(targets))

        valid_edges = {
            (source, target)
            for source, targets in self.material_card_preview_connections.items()
            for target in targets
        }
        self.material_card_preview_connection_roles = {}
        roles_raw = payload.get("connection_roles")
        if isinstance(roles_raw, list):
            for item in roles_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    edge = (int(item.get("source")), int(item.get("target")))
                except (TypeError, ValueError):
                    continue
                role = str(item.get("role") or "")
                if edge in valid_edges and role in _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES:
                    self.material_card_preview_connection_roles[edge] = role

        self.material_card_preview_connection_sides = {}
        sides_raw = payload.get("connection_sides")
        if isinstance(sides_raw, list):
            for item in sides_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    edge = (int(item.get("source")), int(item.get("target")))
                except (TypeError, ValueError):
                    continue
                source_side = "left" if str(item.get("source_side") or "") == "left" else "right"
                target_side = "right" if str(item.get("target_side") or "") == "right" else "left"
                if edge in valid_edges:
                    self.material_card_preview_connection_sides[edge] = (source_side, target_side)
        for edge in valid_edges:
            self.material_card_preview_connection_sides.setdefault(edge, ("right", "left"))

        self.material_card_parallel_selections = {}
        selections_raw = payload.get("parallel_selections")
        if isinstance(selections_raw, dict):
            for raw_source, raw_target in selections_raw.items():
                try:
                    source = int(raw_source)
                    target = int(raw_target)
                except (TypeError, ValueError):
                    continue
                if target in self.material_card_preview_connections.get(source, []):
                    self.material_card_parallel_selections[source] = target

        self.material_card_preview_parallel_column_counts = tuple(
            count for count in _int_list(payload.get("parallel_column_counts")) if count > 0
        )

        rows = [
            max(0, min(len(STORYBOARD_ROW_LABELS) - 1, row))
            for row in _int_list(payload.get("story_card_rows"))
        ]
        self.material_story_card_rows = sorted(set(rows)) or [_ROUGHCUT_STORY_START_DEFAULT_ROW]
        labels_raw = payload.get("story_card_labels")
        self.material_story_card_labels = {}
        if isinstance(labels_raw, dict):
            for raw_row, raw_label in labels_raw.items():
                try:
                    row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(raw_row)))
                except (TypeError, ValueError):
                    continue
                label = str(raw_label or "").strip()
                if label:
                    self.material_story_card_labels[row] = label
        self.material_story_card_labels.setdefault(_ROUGHCUT_STORY_START_DEFAULT_ROW, "메인")

        lane_targets: dict[int, list[int]] = {}
        lane_connections_raw = payload.get("lane_connections")
        if isinstance(lane_connections_raw, dict):
            for raw_row, raw_target in lane_connections_raw.items():
                try:
                    row = int(raw_row)
                    target = int(raw_target)
                except (TypeError, ValueError):
                    continue
                if target in active_set:
                    lane_targets.setdefault(row, []).append(target)
        lane_parallel_raw = payload.get("lane_parallel_connections")
        if isinstance(lane_parallel_raw, dict):
            for raw_row, raw_targets in lane_parallel_raw.items():
                try:
                    row = int(raw_row)
                except (TypeError, ValueError):
                    continue
                lane_targets.setdefault(row, [])
                for target in _int_list(raw_targets):
                    if target in active_set and target not in lane_targets[row]:
                        lane_targets[row].append(target)
        self.material_card_preview_lane_connections = {}
        self.material_card_preview_lane_parallel_connections = {}
        self.material_card_preview_lane_connection_roles = {}
        for row, targets in lane_targets.items():
            self._sync_material_preview_lane_targets(row, targets)

        lane_roles_raw = payload.get("lane_connection_roles")
        if isinstance(lane_roles_raw, list):
            for item in lane_roles_raw:
                if not isinstance(item, dict):
                    continue
                try:
                    row = int(item.get("row"))
                    target = int(item.get("target"))
                except (TypeError, ValueError):
                    continue
                role = str(item.get("role") or "")
                if target in self._material_preview_lane_targets(row) and role in _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES:
                    self.material_card_preview_lane_connection_roles[(row, target)] = role

        self.material_card_preview_merged_nodes = {
            int(node): [child for child in _int_list(children) if child in self.material_card_preview_source_nodes]
            for node, children in (payload.get("merged_nodes") or {}).items()
        } if isinstance(payload.get("merged_nodes"), dict) else {}
        self.material_card_preview_split_children = {
            int(node): [child for child in _int_list(children) if child in self.material_card_preview_source_nodes]
            for node, children in (payload.get("split_children") or {}).items()
        } if isinstance(payload.get("split_children"), dict) else {}

        self.material_card_preview_trim_state = {}
        trim_raw = payload.get("trim_state")
        if isinstance(trim_raw, dict):
            for raw_node, raw_state in trim_raw.items():
                if not isinstance(raw_state, dict):
                    continue
                try:
                    node = int(raw_node)
                    self.material_card_preview_trim_state[node] = {
                        "left": int(raw_state.get("left", 0)),
                        "right": int(raw_state.get("right", 0)),
                    }
                except (TypeError, ValueError):
                    continue

        try:
            next_node = int(payload.get("next_node", 0))
        except (TypeError, ValueError):
            next_node = 0
        self.material_card_preview_next_node = max(
            next_node,
            max(self.material_card_preview_source_nodes or {0: 0}) + 1,
            _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT + 1,
        )
        selected = int(payload.get("selected_node", 0) or 0)
        self.material_card_preview_selected_node = selected if selected in active_set else (self._active_material_preview_order()[0] if self._active_material_preview_order() else 0)
        self.material_card_preview_multi_select_enabled = bool(payload.get("multi_select_enabled", False))
        self.material_card_preview_multi_selection = [
            node for node in _int_list(payload.get("multi_selection")) if node in active_set
        ]
        self.material_card_preview_generated_order = [
            node for node in _int_list(payload.get("generated_order")) if node in active_set
        ]
        self.material_card_preview_clipboard = [
            node for node in _int_list(payload.get("clipboard")) if node in self.material_card_preview_source_nodes
        ]
        self.scenario_sequence_layer = (
            "card_detail" if str(payload.get("scenario_sequence_layer") or "") == "card_detail" else "sequence"
        )
        self.material_card_preview_last_reorder = dict(payload.get("last_reorder") or {}) if isinstance(payload.get("last_reorder"), dict) else {}
        self.material_card_preview_last_auto_copy = dict(payload.get("last_auto_copy") or {}) if isinstance(payload.get("last_auto_copy"), dict) else {}
        self._clear_material_preview_routing_mode(refresh=False)
        self._populate_material_miro_uml_preview_scene()

    def _material_preview_slot_positions(self) -> tuple[tuple[int, int], ...]:
        lookup = self._material_preview_node_position_lookup()
        return tuple(
            lookup.get(node, (_ROUGHCUT_MATERIAL_PREVIEW_START_X, _ROUGHCUT_MATERIAL_PREVIEW_START_Y))
            for node in self.material_card_preview_order
        )

    def _initial_material_preview_grid_slots(self, nodes: list[int]) -> dict[int, tuple[int, int]]:
        return {
            node: (
                _ROUGHCUT_MATERIAL_PREVIEW_ROW_ORDER[index % _ROUGHCUT_MATERIAL_PREVIEW_ROWS],
                index // _ROUGHCUT_MATERIAL_PREVIEW_ROWS,
            )
            for index, node in enumerate(nodes)
        }

    def _material_preview_display_groups(self) -> tuple[tuple[int, ...], ...]:
        columns: dict[int, list[int]] = {}
        for node in self._active_material_preview_order():
            row, col = self.material_card_preview_grid_slots.get(node, (1, 0))
            columns.setdefault(col, []).append(node)
        return tuple(tuple(sorted(nodes, key=lambda node: self.material_card_preview_grid_slots.get(node, (1, 0))[0])) for _col, nodes in sorted(columns.items()))

    def _material_preview_node_position_lookup(self) -> dict[int, tuple[int, int]]:
        positions: dict[int, tuple[int, int]] = {}
        for node_number in self._active_material_preview_order():
            row, col = self.material_card_preview_grid_slots.get(node_number, (1, 0))
            page = max(0, col) // _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS
            page_col = max(0, col) % _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS
            x_pos = (page * _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH) + _ROUGHCUT_MATERIAL_PREVIEW_START_X + (
                page_col * _ROUGHCUT_MATERIAL_PREVIEW_NODE_STEP_X
            )
            y_pos = _ROUGHCUT_MATERIAL_PREVIEW_START_Y + (
                max(0, min(_ROUGHCUT_MATERIAL_PREVIEW_ROWS - 1, row)) * _ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y
            )
            positions[node_number] = (x_pos, y_pos)
        return positions

    def _material_preview_grid_axis_origin(self, axis: str) -> float:
        cell = _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE
        if axis == "x":
            return float(_ROUGHCUT_MATERIAL_PREVIEW_START_X % cell)
        return float(_ROUGHCUT_MATERIAL_PREVIEW_START_Y % cell)

    def _material_preview_snap_axis_to_grid(self, value: float, axis: str) -> float:
        cell = float(_ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE)
        origin = self._material_preview_grid_axis_origin(axis)
        return origin + (round((float(value) - origin) / cell) * cell)

    def _material_preview_snap_axis_to_half_grid(self, value: float, axis: str) -> float:
        half = float(_ROUGHCUT_MATERIAL_PREVIEW_HALF_GRID_SIZE)
        origin = self._material_preview_grid_axis_origin(axis)
        return origin + (round((float(value) - origin) / half) * half)

    def _material_preview_snap_point_to_grid(self, point: QPointF) -> QPointF:
        return QPointF(
            self._material_preview_snap_axis_to_grid(point.x(), "x"),
            self._material_preview_snap_axis_to_grid(point.y(), "y"),
        )

    def _material_preview_snap_point_to_half_grid(self, point: QPointF) -> QPointF:
        return QPointF(
            self._material_preview_snap_axis_to_half_grid(point.x(), "x"),
            self._material_preview_snap_axis_to_half_grid(point.y(), "y"),
        )

    def _material_preview_snap_route_points_to_half_grid(self, points: list[QPointF]) -> list[QPointF]:
        if len(points) <= 2:
            return list(points)
        return [points[0]] + [
            self._material_preview_snap_point_to_half_grid(point)
            for point in points[1:-1]
        ] + [points[-1]]

    def _material_preview_grid_slot_for_scene_pos(self, scene_pos: QPointF) -> tuple[int, int]:
        page = max(0, int(scene_pos.x() // _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH))
        local_x = scene_pos.x() - (page * _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH)
        col = page * _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS + int(
            round((local_x - _ROUGHCUT_MATERIAL_PREVIEW_START_X) / _ROUGHCUT_MATERIAL_PREVIEW_NODE_STEP_X)
        )
        row = int(round((scene_pos.y() - _ROUGHCUT_MATERIAL_PREVIEW_START_Y) / _ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y))
        return (
            max(0, min(_ROUGHCUT_MATERIAL_PREVIEW_ROWS - 1, row)),
            max(0, col),
        )

    def _material_preview_insert_slot_for_scene_pos(self, scene_pos: QPointF, dragged_node: int) -> int:
        row, col = self._material_preview_grid_slot_for_scene_pos(scene_pos)
        return (col * _ROUGHCUT_MATERIAL_PREVIEW_ROWS) + row

    def _material_preview_shadow_rect_for_insert_slot(self, insert_slot: int, dragged_node: int) -> QRectF:
        row = insert_slot % _ROUGHCUT_MATERIAL_PREVIEW_ROWS
        col = insert_slot // _ROUGHCUT_MATERIAL_PREVIEW_ROWS
        x_pos, y_pos = self._material_preview_position_for_grid_slot(row, col)
        return QRectF(x_pos, y_pos, _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH, _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT)

    def _material_preview_position_for_grid_slot(self, row: int, col: int) -> tuple[int, int]:
        page = max(0, col) // _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS
        page_col = max(0, col) % _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS
        return (
            (page * _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH) + _ROUGHCUT_MATERIAL_PREVIEW_START_X + (
                page_col * _ROUGHCUT_MATERIAL_PREVIEW_NODE_STEP_X
            ),
            _ROUGHCUT_MATERIAL_PREVIEW_START_Y + (
                max(0, min(_ROUGHCUT_MATERIAL_PREVIEW_ROWS - 1, row)) * _ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y
            ),
        )

    def _update_material_preview_drag_shadow(self, node_id: str, scene_pos: QPointF) -> None:
        node_number = int(node_id.rsplit("_", 1)[1])
        insert_slot = self._material_preview_insert_slot_for_scene_pos(scene_pos, node_number)
        shadow_rect = self._material_preview_shadow_rect_for_insert_slot(insert_slot, node_number)
        self.material_card_preview_drag_shadow_slot = insert_slot + 1
        self.material_card_preview_drag_shadow_rect = shadow_rect
        self._draw_material_preview_drag_shadow()

    def _draw_material_preview_drag_shadow(self) -> None:
        self._remove_material_preview_drag_shadow_item()
        shadow_rect = getattr(self, "material_card_preview_drag_shadow_rect", None)
        if shadow_rect is None or shadow_rect.isNull():
            return
        path = QPainterPath()
        path.addRoundedRect(shadow_rect, 8, 8)
        pen = QPen(QColor(_ROUGHCUT_MATERIAL_PREVIEW_SHADOW_COLOR), 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        item = self.material_card_preview_scene.addPath(
            path,
            pen,
            QBrush(QColor(0, 200, 255, 30)),
        )
        item.setZValue(3)
        item.setData(0, "middle_segment_preview_insert_shadow")
        self.material_card_preview_drag_shadow_item = item

    def _remove_material_preview_drag_shadow_item(self) -> None:
        item = getattr(self, "material_card_preview_drag_shadow_item", None)
        if item is not None:
            try:
                self.material_card_preview_scene.removeItem(item)
            except RuntimeError:
                pass
        self.material_card_preview_drag_shadow_item = None

    def _clear_material_preview_drag_shadow(self) -> None:
        self._remove_material_preview_drag_shadow_item()
        self.material_card_preview_drag_shadow_slot = 0
        self.material_card_preview_drag_shadow_rect = None

    def _material_preview_node_centers(self) -> dict[int, QPointF]:
        centers: dict[int, QPointF] = {}
        for node in self.material_card_preview_nodes:
            node_number = int(str(node["id"]).rsplit("_", 1)[1])
            centers[node_number] = QPointF(
                float(node["x"]) + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH / 2),
                float(node["y"]) + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2),
            )
        return centers

    def _material_preview_current_group_positions(self) -> dict[int, QPointF]:
        positions: dict[int, QPointF] = {}
        for node_id, group in self._material_card_preview_groups.items():
            try:
                node_number = int(str(node_id).rsplit("_", 1)[1])
            except (TypeError, ValueError):
                continue
            positions[node_number] = QPointF(group.pos())
        if not positions:
            for node_number, (x_pos, y_pos) in self._material_preview_node_position_lookup().items():
                positions[node_number] = QPointF(float(x_pos), float(y_pos))
        return positions

    def _stop_material_preview_card_animations(self) -> None:
        for animation in list(getattr(self, "_material_card_preview_animations", [])):
            try:
                animation.stop()
            except RuntimeError:
                pass
        self._material_card_preview_animations = []

    def _start_material_preview_card_animations(self, moves: list[tuple[object, QPointF, QPointF]]) -> None:
        self._stop_material_preview_card_animations()
        valid_moves = [
            (group, start_pos, end_pos)
            for group, start_pos, end_pos in moves
            if (start_pos - end_pos).manhattanLength() >= 1
        ]
        self.material_card_preview_last_animation = {
            "mode": "smooth_grid_sort",
            "duration_ms": _ROUGHCUT_MATERIAL_PREVIEW_SORT_ANIMATION_MS,
            "move_count": len(valid_moves),
            "commit": "preview_only",
        }
        for group, start_pos, end_pos in valid_moves:
            animation = QVariantAnimation(self)
            animation.setDuration(_ROUGHCUT_MATERIAL_PREVIEW_SORT_ANIMATION_MS)
            animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            animation.setStartValue(QPointF(start_pos))
            animation.setEndValue(QPointF(end_pos))
            group.setPos(QPointF(start_pos))
            animation.valueChanged.connect(
                lambda value, item=group: item.setPos(QPointF(value))
            )
            animation.finished.connect(
                lambda anim=animation: self._material_card_preview_animations.remove(anim)
                if anim in self._material_card_preview_animations
                else None
            )
            self._material_card_preview_animations.append(animation)
            animation.start()

    def _material_preview_pin_position(self, node_number: int, side: str) -> QPointF:
        if node_number < 0:
            row = self._material_preview_lane_row_from_source(node_number)
            return self._material_preview_lane_pin_position(row) if side == "right" else QPointF()
        group = self._material_card_preview_groups.get(f"middle_segment_preview_node_{node_number:02d}")
        if group is None:
            return QPointF()
        rect = group.sceneBoundingRect()
        x_pos = rect.left() if side == "left" else rect.right()
        return QPointF(x_pos, rect.top() + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2))

    def _material_preview_story_rows(self) -> list[int]:
        rows = sorted(
            {
                max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
                for row in getattr(self, "material_story_card_rows", [_ROUGHCUT_STORY_START_DEFAULT_ROW])
            }
        )
        return rows or [_ROUGHCUT_STORY_START_DEFAULT_ROW]

    def _material_preview_story_row_role(self, row: int) -> str:
        row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
        labels = getattr(self, "material_story_card_labels", {})
        if labels.get(row) == "메인":
            return "main"
        rows = self._material_preview_story_rows()
        non_main_rows = [candidate for candidate in rows if labels.get(candidate) != "메인"]
        try:
            index = non_main_rows.index(row) + 1
        except ValueError:
            index = len(non_main_rows) + 1
        return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES[
            min(index, len(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES) - 1)
        ]

    def _material_preview_lane_targets(self, row: int) -> list[int]:
        row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
        targets: list[int] = []
        primary = getattr(self, "material_card_preview_lane_connections", {}).get(row)
        if primary:
            targets.append(int(primary))
        for target in getattr(self, "material_card_preview_lane_parallel_connections", {}).get(row, []):
            target = int(target)
            if target not in targets:
                targets.append(target)
        return targets

    def _sync_material_preview_lane_targets(self, row: int, targets: list[int]) -> None:
        row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
        active_set = set(self._active_material_preview_order())
        clean_targets: list[int] = []
        for raw_target in targets:
            target = int(raw_target)
            if target in active_set and target not in clean_targets:
                clean_targets.append(target)
        if clean_targets:
            self.material_card_preview_lane_parallel_connections[row] = clean_targets
            self.material_card_preview_lane_connections[row] = clean_targets[0]
            valid_edges = {(row, target) for target in clean_targets}
            self.material_card_preview_lane_connection_roles = {
                edge: role
                for edge, role in self.material_card_preview_lane_connection_roles.items()
                if edge[0] != row or edge in valid_edges
            }
            return
        self.material_card_preview_lane_parallel_connections.pop(row, None)
        self.material_card_preview_lane_connections.pop(row, None)
        self.material_card_preview_lane_connection_roles = {
            edge: role
            for edge, role in self.material_card_preview_lane_connection_roles.items()
            if edge[0] != row
        }

    def _material_preview_lane_connection_role(self, row: int, target: int) -> str:
        return self._material_preview_story_row_role(row)

    def _material_preview_lane_anchor_targets(self) -> dict[int, list[int]]:
        rows = set(getattr(self, "material_card_preview_lane_connections", {}))
        rows.update(getattr(self, "material_card_preview_lane_parallel_connections", {}))
        return {
            row: self._material_preview_lane_targets(row)
            for row in sorted(rows)
            if self._material_preview_lane_targets(row)
        }

    def _material_preview_lane_anchor_target_roles(self) -> dict[tuple[int, int], str]:
        return {
            (row, target): self._material_preview_lane_connection_role(row, target)
            for row, targets in self._material_preview_lane_anchor_targets().items()
            for target in targets
        }

    def _material_preview_story_card_label(self, row: int) -> str:
        labels = getattr(self, "material_story_card_labels", {})
        return str(labels.get(row) or f"스토리 {self._material_preview_story_rows().index(row) + 1}")

    def _material_preview_story_card_rect(self, row: int) -> QRectF:
        row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
        y_pos = _ROUGHCUT_MATERIAL_PREVIEW_START_Y + (row * _ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y)
        return QRectF(
            _ROUGHCUT_STORY_CARD_X,
            y_pos + _ROUGHCUT_STORY_CARD_TOP_OFFSET,
            _ROUGHCUT_STORY_CARD_WIDTH,
            _ROUGHCUT_STORY_CARD_HEIGHT,
        )

    def _material_preview_story_plus_rows(self) -> list[int]:
        rows = self._material_preview_story_rows()
        candidates: list[int] = []
        above = min(rows) - 1
        below = max(rows) + 1
        if above >= 0:
            candidates.append(above)
        if below < len(STORYBOARD_ROW_LABELS):
            candidates.append(below)
        return candidates

    def _material_preview_story_plus_at_scene_pos(self, scene_pos: QPointF) -> int | None:
        for row in self._material_preview_story_plus_rows():
            if self._material_preview_story_card_rect(row).contains(scene_pos):
                return row
        return None

    def _create_material_preview_story_card(self, row: int) -> None:
        row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
        rows = self._material_preview_story_rows()
        if row in rows:
            return
        rows.append(row)
        rows.sort()
        self.material_story_card_rows = rows
        if not hasattr(self, "material_story_card_labels"):
            self.material_story_card_labels = {}
        existing_non_main = sum(1 for label in self.material_story_card_labels.values() if label != "메인")
        self.material_story_card_labels.setdefault(row, f"스토리 {existing_non_main + 2}")
        self.material_card_preview_last_reorder = {
            "mode": "story_card_added",
            "story_row": row,
            "active_story_rows": list(rows),
            "commit": "preview_only",
        }
        self._populate_material_miro_uml_preview_scene()

    def _material_preview_pin_at_scene_pos(self, scene_pos: QPointF) -> tuple[int, str]:
        radius = _ROUGHCUT_MATERIAL_PREVIEW_PIN_HIT_RADIUS
        closest_node = 0
        closest_side = ""
        closest_distance = radius + 1.0
        for node_number in self.material_card_preview_order:
            for side in ("left", "right"):
                pin_pos = self._material_preview_pin_position(node_number, side)
                distance = (scene_pos - pin_pos).manhattanLength()
                if distance <= radius and distance < closest_distance:
                    closest_node = node_number
                    closest_side = side
                    closest_distance = distance
        for row in self._material_preview_story_rows():
            pin_pos = self._material_preview_lane_pin_position(row)
            distance = (scene_pos - pin_pos).manhattanLength()
            if distance <= radius and distance < closest_distance:
                closest_node = self._material_preview_lane_source_id(row)
                closest_side = "right"
                closest_distance = distance
        return closest_node, closest_side

    def _draw_material_preview_connections(self) -> None:
        scene = self.material_card_preview_scene
        self.material_card_preview_connection_paths = {}
        connection_specs: list[dict[str, object]] = []
        active_set = set(self._active_material_preview_order())
        hover_connection = getattr(self, "material_card_preview_hover_connection", (0, 0))
        for row, targets in self._material_preview_lane_anchor_targets().items():
            source = self._material_preview_lane_source_id(row)
            source_pos = self._material_preview_lane_pin_position(row)
            if source_pos.isNull():
                continue
            for lane_index, target in enumerate(targets):
                if target not in active_set:
                    continue
                target_pos = self._material_preview_pin_position(target, "left")
                if target_pos.isNull():
                    continue
                role = self._material_preview_lane_connection_role(row, target)
                is_hovered = hover_connection == (source, target)
                role_color = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, "#5A6A76")
                pen = QPen(QColor("#00C8FF" if is_hovered else role_color))
                pen.setWidth(4 if is_hovered else 3)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                lane_offset = (lane_index - 1) * _ROUGHCUT_MATERIAL_PREVIEW_HALF_GRID_SIZE if len(targets) > 1 else 0
                path, route_points = self._material_preview_connection_path_and_points(
                    source_pos,
                    target_pos,
                    lane_offset,
                    source_node=source,
                    target_node=target,
                    role=role,
                )
                self.material_card_preview_connection_paths[(source, target)] = path
                connector = scene.addPath(path, pen)
                connector.setZValue(1)
                connector.setData(0, f"middle_segment_preview_lane_connection_{row}_{target}_{role}")
                connection_specs.append(
                    {
                        "source": source,
                        "target": target,
                        "role": role,
                        "points": route_points,
                        "color": QColor("#00C8FF" if is_hovered else role_color),
                        "width": 4 if is_hovered else 3,
                        "opacity": 1.0,
                    }
                )
        for source, targets in self.material_card_preview_connections.items():
            if source not in active_set:
                continue
            selected_target = self.material_card_parallel_selections.get(source, targets[0] if targets else 0)
            for lane_index, target in enumerate(targets):
                if target not in active_set:
                    continue
                source_side, target_side = self.material_card_preview_connection_sides.get((source, target), ("right", "left"))
                source_pos = self._material_preview_pin_position(source, source_side)
                target_pos = self._material_preview_pin_position(target, target_side)
                if target_pos.isNull():
                    continue
                if source_pos.isNull():
                    continue
                role = self._material_preview_connection_role(source, target)
                is_lineage = self._material_preview_connection_is_color_lineage(source, target, role)
                is_selected = role == "main" or target == selected_target
                is_hovered = hover_connection == (source, target)
                role_color = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, "#5A6A76")
                pen = QPen(QColor("#00C8FF" if is_hovered else role_color))
                pen.setWidth(4 if is_hovered else (3 if is_selected or is_lineage else 2))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                if role != "main" and not is_hovered and not is_lineage:
                    pen.setStyle(Qt.PenStyle.DashLine)
                lane_offset = (lane_index - 1) * _ROUGHCUT_MATERIAL_PREVIEW_HALF_GRID_SIZE if len(targets) > 1 else 0
                path, route_points = self._material_preview_connection_path_and_points(
                    source_pos,
                    target_pos,
                    lane_offset,
                    source_node=source,
                    target_node=target,
                    role=role,
                )
                self.material_card_preview_connection_paths[(source, target)] = path
                connector = scene.addPath(path, pen)
                if role != "main" and not is_hovered and not is_lineage:
                    connector.setOpacity(0.5)
                connector.setZValue(1)
                connector.setData(0, f"middle_segment_preview_connection_{source}_{target}_{role}")
                connection_specs.append(
                    {
                        "source": source,
                        "target": target,
                        "role": role,
                        "points": route_points,
                        "color": QColor("#00C8FF" if is_hovered else role_color),
                        "width": 4 if is_hovered else (3 if is_selected or is_lineage else 2),
                        "opacity": 1.0 if role == "main" or is_hovered or is_lineage else 0.5,
                    }
                )
        self._draw_material_preview_line_jumps(connection_specs)
        self._draw_material_preview_connection_shadow()

    def _material_preview_connection_path(
        self,
        source_pos: QPointF,
        target_pos: QPointF,
        lane_offset: int = 0,
        *,
        source_node: int = 0,
        target_node: int = 0,
        role: str = "main",
    ) -> QPainterPath:
        path, _points = self._material_preview_connection_path_and_points(
            source_pos,
            target_pos,
            lane_offset,
            source_node=source_node,
            target_node=target_node,
            role=role,
        )
        return path

    def _material_preview_connection_path_and_points(
        self,
        source_pos: QPointF,
        target_pos: QPointF,
        lane_offset: int = 0,
        *,
        source_node: int = 0,
        target_node: int = 0,
        role: str = "main",
    ) -> tuple[QPainterPath, list[QPointF]]:
        channels = self._material_preview_route_channels(role, source_pos, target_pos, lane_offset)
        blockers = self._material_preview_blocking_rects(source_node, target_node)
        blocked_rect = getattr(self, "material_card_preview_drag_shadow_rect", None)
        if blocked_rect is not None and not blocked_rect.isNull():
            blockers.append(blocked_rect.adjusted(-4, -4, 4, 4))
        candidates: list[tuple[int, float, QPainterPath, list[QPointF]]] = []
        for points in self._material_preview_short_connection_candidates(source_pos, target_pos):
            path = self._material_preview_rounded_polyline_path(points)
            intersection_count = self._material_preview_path_intersection_count(path, blockers)
            candidates.append((intersection_count, self._material_preview_polyline_length(points), path, points))
        for channel_y in channels:
            points = self._material_preview_orthogonal_connection_points(source_pos, target_pos, channel_y)
            path = self._material_preview_rounded_polyline_path(points)
            intersection_count = self._material_preview_path_intersection_count(path, blockers)
            candidates.append((intersection_count, self._material_preview_polyline_length(points), path, points))
        if not candidates:
            return QPainterPath(), []
        selected = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))
        if selected[0] > 0:
            blocked = self._material_preview_first_intersecting_rect(selected[2], blockers)
            if blocked is not None:
                detour_points = self._material_preview_detour_points(source_pos, target_pos, blocked)
                detour_path = self._material_preview_rounded_polyline_path(detour_points)
                if not self._material_preview_path_intersects_any_rect(detour_path, blockers):
                    return detour_path, detour_points
        return selected[2], selected[3]

    def _material_preview_polyline_length(self, points: list[QPointF]) -> float:
        total = 0.0
        for previous, current in zip(points, points[1:]):
            total += abs(float(current.x()) - float(previous.x()))
            total += abs(float(current.y()) - float(previous.y()))
        return round(total, 3)

    def _material_preview_route_channels(
        self,
        role: str,
        source_pos: QPointF,
        target_pos: QPointF,
        lane_offset: int = 0,
    ) -> list[float]:
        scene_rect = self.material_card_preview_scene.sceneRect()
        top = scene_rect.top() + 12 + lane_offset
        role_row = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_ROWS.get(role, 0)
        role_y = (
            _ROUGHCUT_MATERIAL_PREVIEW_START_Y
            + (role_row * _ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y)
            + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2)
            + lane_offset
        )
        upper_mid = (
            _ROUGHCUT_MATERIAL_PREVIEW_START_Y
            + _ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y
            + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2)
            + lane_offset
        )
        lower_mid = (
            _ROUGHCUT_MATERIAL_PREVIEW_START_Y
            + ((_ROUGHCUT_MATERIAL_PREVIEW_ROWS - 2) * _ROUGHCUT_MATERIAL_PREVIEW_ROW_STEP_Y)
            + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2)
            + lane_offset
        )
        bottom = scene_rect.bottom() - 12 - lane_offset
        preferred = role_y if role != "main" else (
            upper_mid if min(source_pos.y(), target_pos.y()) < (scene_rect.center().y()) else lower_mid
        )
        return [
            self._material_preview_snap_axis_to_half_grid(value, "y")
            for value in (preferred, top, upper_mid, lower_mid, bottom)
        ]

    def _material_preview_short_connection_candidates(
        self,
        source_pos: QPointF,
        target_pos: QPointF,
    ) -> list[list[QPointF]]:
        if abs(source_pos.y() - target_pos.y()) < 0.1:
            return [[source_pos, target_pos]]
        mid_x = self._material_preview_snap_axis_to_half_grid(
            source_pos.x() + ((target_pos.x() - source_pos.x()) / 2),
            "x",
        )
        return [
            self._material_preview_snap_route_points_to_half_grid([
                source_pos,
                QPointF(mid_x, source_pos.y()),
                QPointF(mid_x, target_pos.y()),
                target_pos,
            ])
        ]

    def _material_preview_orthogonal_connection_points(
        self,
        source_pos: QPointF,
        target_pos: QPointF,
        channel_y: float,
    ) -> list[QPointF]:
        source_anchor_x = self._material_preview_snap_axis_to_half_grid(source_pos.x() + 24, "x")
        target_anchor_x = self._material_preview_snap_axis_to_half_grid(target_pos.x() - 24, "x")
        return self._material_preview_snap_route_points_to_half_grid([
            source_pos,
            QPointF(source_anchor_x, source_pos.y()),
            QPointF(source_anchor_x, channel_y),
            QPointF(target_anchor_x, channel_y),
            QPointF(target_anchor_x, target_pos.y()),
            target_pos,
        ])

    def _material_preview_rounded_polyline_path(self, points: list[QPointF], radius: float = 8.0) -> QPainterPath:
        if not points:
            return QPainterPath()
        path = QPainterPath(points[0])
        if len(points) == 1:
            return path
        for index in range(1, len(points) - 1):
            prev = points[index - 1]
            current = points[index]
            next_point = points[index + 1]
            prev_dx = current.x() - prev.x()
            prev_dy = current.y() - prev.y()
            next_dx = next_point.x() - current.x()
            next_dy = next_point.y() - current.y()
            prev_len = abs(prev_dx) + abs(prev_dy)
            next_len = abs(next_dx) + abs(next_dy)
            is_turn = (prev_dx != 0 and next_dy != 0) or (prev_dy != 0 and next_dx != 0)
            if not is_turn or prev_len <= 2 or next_len <= 2:
                path.lineTo(current)
                continue
            corner_radius = min(radius, prev_len / 2, next_len / 2)
            prev_unit_x = 0 if prev_dx == 0 else (1 if prev_dx > 0 else -1)
            prev_unit_y = 0 if prev_dy == 0 else (1 if prev_dy > 0 else -1)
            next_unit_x = 0 if next_dx == 0 else (1 if next_dx > 0 else -1)
            next_unit_y = 0 if next_dy == 0 else (1 if next_dy > 0 else -1)
            before_corner = QPointF(
                current.x() - (prev_unit_x * corner_radius),
                current.y() - (prev_unit_y * corner_radius),
            )
            after_corner = QPointF(
                current.x() + (next_unit_x * corner_radius),
                current.y() + (next_unit_y * corner_radius),
            )
            path.lineTo(before_corner)
            path.quadTo(current, after_corner)
        path.lineTo(points[-1])
        return path

    def _material_preview_path_intersects_rect(self, path: QPainterPath, rect: QRectF) -> bool:
        shadow_path = QPainterPath()
        shadow_path.addRect(rect.adjusted(-4, -4, 4, 4))
        stroker = QPainterPathStroker()
        stroker.setWidth(6)
        return stroker.createStroke(path).intersects(shadow_path)

    def _material_preview_path_intersects_any_rect(self, path: QPainterPath, rects: list[QRectF]) -> bool:
        return any(self._material_preview_path_intersects_rect(path, rect) for rect in rects)

    def _material_preview_path_intersection_count(self, path: QPainterPath, rects: list[QRectF]) -> int:
        return sum(1 for rect in rects if self._material_preview_path_intersects_rect(path, rect))

    def _material_preview_first_intersecting_rect(self, path: QPainterPath, rects: list[QRectF]) -> QRectF | None:
        for rect in rects:
            if self._material_preview_path_intersects_rect(path, rect):
                return rect
        return None

    def _material_preview_blocking_rects(self, source_node: int = 0, target_node: int = 0) -> list[QRectF]:
        blockers: list[QRectF] = []
        ignored = {source_node, target_node}
        for node_number in self._active_material_preview_order():
            if node_number in ignored:
                continue
            row, col = self.material_card_preview_grid_slots.get(node_number, (0, 0))
            x_pos, y_pos = self._material_preview_position_for_grid_slot(row, col)
            blockers.append(
                QRectF(
                    x_pos,
                    y_pos,
                    _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH,
                    _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT,
                ).adjusted(-6, -6, 6, 6)
            )
        return blockers

    def _draw_material_preview_line_jumps(self, connection_specs: list[dict[str, object]]) -> None:
        rendered: set[tuple[int, int]] = set()
        for index, spec in enumerate(connection_specs):
            points = spec.get("points")
            if not isinstance(points, list):
                continue
            for previous in connection_specs[:index]:
                previous_points = previous.get("points")
                if not isinstance(previous_points, list):
                    continue
                for segment in self._material_preview_axis_segments(points):
                    for previous_segment in self._material_preview_axis_segments(previous_points):
                        crossing = self._material_preview_axis_segment_crossing(segment, previous_segment)
                        if crossing is None:
                            continue
                        key = (round(crossing.x()), round(crossing.y()))
                        if key in rendered:
                            continue
                        rendered.add(key)
                        jump_segment = segment if segment["orientation"] == "h" else previous_segment
                        jump_spec = spec if segment["orientation"] == "h" else previous
                        self._draw_material_preview_jump_bridge(crossing, jump_segment, jump_spec)

    def _material_preview_axis_segments(self, points: list[QPointF]) -> list[dict[str, object]]:
        segments: list[dict[str, object]] = []
        for start, end in zip(points, points[1:]):
            if abs(start.x() - end.x()) < 0.1 and abs(start.y() - end.y()) < 0.1:
                continue
            if abs(start.y() - end.y()) < 0.1:
                orientation = "h"
            elif abs(start.x() - end.x()) < 0.1:
                orientation = "v"
            else:
                continue
            segments.append({"start": start, "end": end, "orientation": orientation})
        return segments

    def _material_preview_axis_segment_crossing(
        self,
        first: dict[str, object],
        second: dict[str, object],
    ) -> QPointF | None:
        first_orientation = first["orientation"]
        second_orientation = second["orientation"]
        if first_orientation == second_orientation:
            return None
        horizontal = first if first_orientation == "h" else second
        vertical = second if first_orientation == "h" else first
        h_start = horizontal["start"]
        h_end = horizontal["end"]
        v_start = vertical["start"]
        v_end = vertical["end"]
        if not isinstance(h_start, QPointF) or not isinstance(h_end, QPointF):
            return None
        if not isinstance(v_start, QPointF) or not isinstance(v_end, QPointF):
            return None
        h_min_x, h_max_x = sorted((h_start.x(), h_end.x()))
        v_min_y, v_max_y = sorted((v_start.y(), v_end.y()))
        x_pos = v_start.x()
        y_pos = h_start.y()
        margin = 10
        if not (h_min_x + margin < x_pos < h_max_x - margin):
            return None
        if not (v_min_y + margin < y_pos < v_max_y - margin):
            return None
        return QPointF(x_pos, y_pos)

    def _draw_material_preview_jump_bridge(
        self,
        crossing: QPointF,
        segment: dict[str, object],
        spec: dict[str, object],
    ) -> None:
        color = spec.get("color")
        if not isinstance(color, QColor):
            color = QColor("#34C759")
        width = int(spec.get("width", 3))
        opacity = float(spec.get("opacity", 1.0))
        orientation = segment.get("orientation")
        background_pen = QPen(QColor("#05080A"), width + 5)
        background_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        bridge_pen = QPen(color, width)
        bridge_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        bridge_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if orientation == "h":
            mask = QPainterPath(QPointF(crossing.x() - 11, crossing.y()))
            mask.lineTo(QPointF(crossing.x() + 11, crossing.y()))
            bridge = QPainterPath(QPointF(crossing.x() - 11, crossing.y()))
            bridge.cubicTo(
                QPointF(crossing.x() - 8, crossing.y() - 11),
                QPointF(crossing.x() + 8, crossing.y() - 11),
                QPointF(crossing.x() + 11, crossing.y()),
            )
        else:
            mask = QPainterPath(QPointF(crossing.x(), crossing.y() - 11))
            mask.lineTo(QPointF(crossing.x(), crossing.y() + 11))
            bridge = QPainterPath(QPointF(crossing.x(), crossing.y() - 11))
            bridge.cubicTo(
                QPointF(crossing.x() + 11, crossing.y() - 8),
                QPointF(crossing.x() + 11, crossing.y() + 8),
                QPointF(crossing.x(), crossing.y() + 11),
            )
        mask_item = self.material_card_preview_scene.addPath(mask, background_pen)
        mask_item.setZValue(1.65)
        mask_item.setData(0, "middle_segment_preview_connection_jump_mask")
        bridge_item = self.material_card_preview_scene.addPath(bridge, bridge_pen)
        bridge_item.setOpacity(opacity)
        bridge_item.setZValue(1.7)
        bridge_item.setData(0, "middle_segment_preview_connection_jump_bridge")

    def _material_preview_detour_points(self, source_pos: QPointF, target_pos: QPointF, blocked_rect: QRectF) -> list[QPointF]:
        scene_rect = self.material_card_preview_scene.sceneRect()
        route_above = source_pos.y() >= blocked_rect.center().y()
        detour_y = blocked_rect.top() - 18 if route_above else blocked_rect.bottom() + 18
        detour_y = max(scene_rect.top() + 8, min(scene_rect.bottom() - 8, detour_y))
        left_to_right = source_pos.x() <= target_pos.x()
        first_x = blocked_rect.left() - 18 if left_to_right else blocked_rect.right() + 18
        second_x = blocked_rect.right() + 18 if left_to_right else blocked_rect.left() - 18
        detour_y = self._material_preview_snap_axis_to_half_grid(detour_y, "y")
        first_x = self._material_preview_snap_axis_to_half_grid(first_x, "x")
        second_x = self._material_preview_snap_axis_to_half_grid(second_x, "x")
        return self._material_preview_snap_route_points_to_half_grid([
            source_pos,
            QPointF(first_x, source_pos.y()),
            QPointF(first_x, detour_y),
            QPointF(second_x, detour_y),
            QPointF(second_x, target_pos.y()),
            target_pos,
        ])

    def _material_preview_detour_path(self, source_pos: QPointF, target_pos: QPointF, blocked_rect: QRectF) -> QPainterPath:
        return self._material_preview_rounded_polyline_path(
            self._material_preview_detour_points(source_pos, target_pos, blocked_rect)
        )

    def _draw_material_preview_connection_shadow(self) -> None:
        self.material_card_preview_connection_shadow_path = QPainterPath()
        source = getattr(self, "material_card_preview_connect_source", 0)
        cursor = getattr(self, "material_card_preview_connect_cursor", None)
        if not source or cursor is None:
            return
        source_side = str(getattr(self, "material_card_preview_connect_source_side", "right") or "right")
        source_pos = self._material_preview_pin_position(source, source_side)
        if source_pos.isNull():
            return
        target_node, target_side = getattr(self, "material_card_preview_hover_pin", (0, ""))
        target_pos = self._material_preview_pin_position(target_node, target_side) if target_node and target_side else cursor
        role = self._pending_material_preview_connection_role(source)
        path = self._material_preview_connection_path(
            source_pos,
            target_pos,
            source_node=source,
            target_node=target_node,
            role=role,
        )
        self.material_card_preview_connection_shadow_path = path
        pen = QPen(QColor("#FF3B30"), 3)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        shadow = self.material_card_preview_scene.addPath(path, pen)
        shadow.setOpacity(0.5)
        shadow.setZValue(4)
        shadow.setData(0, "middle_segment_preview_connection_shadow")

    def _clear_material_preview_routing_mode(self, *, refresh: bool = True) -> None:
        self.material_card_preview_connect_source = 0
        self.material_card_preview_connect_source_side = "right"
        self.material_card_preview_connect_cursor = None
        self.material_card_preview_hover_pin = (0, "")
        self.material_card_preview_hover_copy_target = {}
        if refresh:
            self._populate_material_miro_uml_preview_scene()

    def _pending_material_preview_connection_role(self, source: int) -> str:
        if source < 0:
            row = self._material_preview_lane_row_from_source(source)
            return self._material_preview_story_row_role(row)
        source_role = self._material_preview_node_accent_role(source)
        if source_role:
            return source_role
        targets = self.material_card_preview_connections.get(source, [])
        index = len(targets)
        return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES[
            min(index, len(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES) - 1)
        ]

    def _material_preview_pin_role_color(self, node_number: int, side: str) -> str:
        connect_source = getattr(self, "material_card_preview_connect_source", 0)
        connect_source_side = getattr(self, "material_card_preview_connect_source_side", "right")
        if node_number < 0:
            row = self._material_preview_lane_row_from_source(node_number)
            role = (
                self._pending_material_preview_connection_role(node_number)
                if side == "right" and connect_source == node_number and connect_source_side == "right"
                else self._material_preview_story_row_role(row)
            )
            return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, _ROUGHCUT_MATERIAL_PREVIEW_SHADOW_COLOR)
        if side == connect_source_side and connect_source == node_number:
            role = self._pending_material_preview_connection_role(node_number)
            return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, _ROUGHCUT_MATERIAL_PREVIEW_SHADOW_COLOR)
        if side == "right":
            targets = self.material_card_preview_connections.get(node_number, [])
            if targets:
                role = self._material_preview_connection_role(node_number, targets[0])
                return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, _ROUGHCUT_MATERIAL_PREVIEW_SHADOW_COLOR)
        role = self._material_preview_node_accent_role(node_number)
        if role:
            return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, _ROUGHCUT_MATERIAL_PREVIEW_SHADOW_COLOR)
        return "#0A0F12"

    def _node_label(self, node_number: int) -> str:
        merged = self.material_card_preview_merged_nodes.get(node_number)
        if merged:
            return f"{node_number:02d}+{len(merged) - 1}"
        return f"{node_number:02d}"

    def _material_preview_source_node(self, node_number: int) -> int:
        return self.material_card_preview_source_nodes.get(node_number, node_number)

    def _material_preview_source_color(self, node_number: int) -> str:
        source_node = self._material_preview_source_node(node_number)
        return _ROUGHCUT_MATERIAL_PREVIEW_SOURCE_COLORS[
            (source_node - 1) % len(_ROUGHCUT_MATERIAL_PREVIEW_SOURCE_COLORS)
        ]

    def _material_preview_node_accent_role(self, node_number: int) -> str:
        lane_roles = [
            self._material_preview_lane_connection_role(row, node_number)
            for row, targets in self._material_preview_lane_anchor_targets().items()
            if node_number in targets
        ]
        if lane_roles:
            return "main" if "main" in lane_roles else lane_roles[0]
        incoming_roles = [
            self._material_preview_connection_role(source, node_number)
            for source, targets in self.material_card_preview_connections.items()
            if node_number in targets
        ]
        if incoming_roles:
            return "main" if "main" in incoming_roles else incoming_roles[0]
        return ""

    def _material_preview_node_accent_color(self, node_number: int) -> str:
        role = self._material_preview_node_accent_role(node_number)
        if role:
            return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, _ROUGHCUT_MATERIAL_PREVIEW_SHADOW_COLOR)
        return self._material_preview_source_color(node_number)

    def _material_preview_connection_is_color_lineage(self, source: int, target: int, role: str) -> bool:
        if source < 0:
            return True
        return bool(role and self._material_preview_node_accent_role(source) == role)

    def _material_preview_lane_source_id(self, row: int) -> int:
        row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
        return -(row + 1)

    def _material_preview_lane_row_from_source(self, source: int) -> int:
        return max(0, min(len(STORYBOARD_ROW_LABELS) - 1, abs(int(source)) - 1))

    def _material_preview_lane_pin_position(self, row: int) -> QPointF:
        row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
        rect = self._material_preview_story_card_rect(row)
        return QPointF(rect.right(), rect.center().y())

    def _active_material_preview_order(self) -> list[int]:
        return [node for node in self.material_card_preview_order if node not in self.material_card_preview_deleted_nodes]

    def _refresh_material_preview_scene_rect(self) -> None:
        active_nodes = self._active_material_preview_order()
        total_columns = max(
            1,
            max((self.material_card_preview_grid_slots.get(node, (0, 0))[1] for node in active_nodes), default=0) + 1,
        )
        page_count = (total_columns + _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS - 1) // _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS
        self.material_card_preview_page_count = page_count
        self.material_card_preview_scene.setSceneRect(
            0,
            0,
            page_count * _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH,
            _ROUGHCUT_MATERIAL_PREVIEW_SCENE_HEIGHT,
        )

    def _material_preview_sorted_by_grid(self) -> list[int]:
        return sorted_storyboard_nodes_by_grid(
            self._active_material_preview_order(),
            self.material_card_preview_grid_slots,
        )

    def _assign_material_preview_grid_from_order(self, ordered_nodes: list[int]) -> None:
        self.material_card_preview_grid_slots = {
            node: (
                _ROUGHCUT_MATERIAL_PREVIEW_ROW_ORDER[index % _ROUGHCUT_MATERIAL_PREVIEW_ROWS],
                index // _ROUGHCUT_MATERIAL_PREVIEW_ROWS,
            )
            for index, node in enumerate(ordered_nodes)
        }

    def _align_material_preview_connection_targets(self) -> None:
        active = set(self._active_material_preview_order())
        for source in sorted(
            self.material_card_preview_connections,
            key=lambda node: (
                self.material_card_preview_grid_slots.get(node, (1, 0))[1],
                self.material_card_preview_grid_slots.get(node, (1, 0))[0],
                node,
            ),
        ):
            if source not in active:
                continue
            source_row, source_col = self.material_card_preview_grid_slots.get(source, (1, 0))
            for target in self.material_card_preview_connections.get(source, []):
                if target not in active:
                    continue
                role = self._material_preview_connection_role(source, target)
                target_row = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_ROWS.get(role, source_row)
                self._place_material_preview_node_at_grid_slot(target, target_row, source_col + 1)

    def _place_material_preview_node_at_grid_slot(self, node_number: int, row: int, col: int) -> None:
        row = max(0, min(_ROUGHCUT_MATERIAL_PREVIEW_ROWS - 1, row))
        col = max(0, col)
        for occupant, slot in sorted(
            list(self.material_card_preview_grid_slots.items()),
            key=lambda item: item[1][1],
            reverse=True,
        ):
            if occupant == node_number or occupant in self.material_card_preview_deleted_nodes:
                continue
            slot_row, slot_col = slot
            if slot_row == row and slot_col >= col:
                self.material_card_preview_grid_slots[occupant] = (slot_row, slot_col + 1)
        self.material_card_preview_grid_slots[node_number] = (row, col)
        self.material_card_preview_order = self._material_preview_sorted_by_grid()

    def _move_material_preview_node_to_grid_slot(self, node_number: int, row: int, col: int) -> dict[str, object]:
        row = max(0, min(_ROUGHCUT_MATERIAL_PREVIEW_ROWS - 1, row))
        col = max(0, col)
        old_slot = self.material_card_preview_grid_slots.get(node_number, (row, col))
        swap_node = 0
        for occupant, slot in self.material_card_preview_grid_slots.items():
            if occupant == node_number or occupant in self.material_card_preview_deleted_nodes:
                continue
            if slot == (row, col):
                swap_node = occupant
                break
        self.material_card_preview_grid_slots[node_number] = (row, col)
        if swap_node:
            self.material_card_preview_grid_slots[swap_node] = old_slot
        self.material_card_preview_order = self._material_preview_sorted_by_grid()
        return {
            "mode": "grid_swap" if swap_node else "grid_move_empty",
            "swapped_with": swap_node,
            "old_grid": {"row": old_slot[0], "col": old_slot[1]},
            "target_grid": {"row": row, "col": col},
        }

    def _material_preview_incoming_sources(self, target: int) -> list[int]:
        return [
            source
            for source, targets in self.material_card_preview_connections.items()
            if target in targets
        ]

    def _material_preview_incoming_lane_sources(self, target: int) -> list[int]:
        return [
            self._material_preview_lane_source_id(row)
            for row, targets in self._material_preview_lane_anchor_targets().items()
            if int(target) in targets
        ]

    def _material_preview_all_incoming_sources(self, target: int) -> list[int]:
        return self._material_preview_incoming_sources(target) + self._material_preview_incoming_lane_sources(target)

    def _material_preview_copy_required_inputs(self, source: int, target: int) -> list[int]:
        if source == target or target not in self._active_material_preview_order():
            return []
        incoming_sources = self._material_preview_all_incoming_sources(target)
        if incoming_sources:
            return incoming_sources
        return []

    def _propagate_material_preview_role_from_node(self, node_number: int, role: str) -> None:
        if role not in _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES:
            return
        active_set = set(self._active_material_preview_order())
        stack = [int(node_number)]
        seen: set[int] = set()
        while stack:
            source = stack.pop()
            if source in seen or source not in active_set:
                continue
            seen.add(source)
            for target in list(self.material_card_preview_connections.get(source, [])):
                if target not in active_set:
                    continue
                self.material_card_preview_connection_roles[(source, target)] = role
                stack.append(target)

    def _create_material_preview_node_copy(
        self,
        source_node: int,
        *,
        row: int | None = None,
        col: int | None = None,
        mode: str = "copy_grid_insert",
        select: bool = True,
        populate: bool = True,
    ) -> int:
        if source_node not in self._active_material_preview_order():
            return 0
        next_node = self.material_card_preview_next_node
        self.material_card_preview_next_node += 1
        self.material_card_preview_source_nodes[next_node] = self._material_preview_source_node(source_node)
        if source_node in self.material_card_preview_trim_state:
            self.material_card_preview_trim_state[next_node] = dict(self.material_card_preview_trim_state[source_node])
        source_index = self.material_card_preview_order.index(source_node)
        self.material_card_preview_order.insert(source_index + 1, next_node)
        source_row, source_col = self.material_card_preview_grid_slots.get(source_node, (0, 0))
        self._place_material_preview_node_at_grid_slot(
            next_node,
            source_row if row is None else row,
            source_col + 1 if col is None else col,
        )
        if select:
            self.material_card_preview_selected_node = next_node
            self.material_card_preview_multi_selection = [next_node] if self.material_card_preview_multi_select_enabled else []
        self.material_card_preview_last_reorder = {
            "copied_nodes": [source_node],
            "pasted_nodes": [next_node],
            "mode": mode,
            "commit": "preview_only",
        }
        if populate:
            self._populate_material_miro_uml_preview_scene()
        return next_node

    def _connect_material_preview_nodes(
        self,
        source: int,
        target: int,
        *,
        source_side: str = "right",
        target_side: str = "left",
        clear_routing_before_refresh: bool = False,
    ) -> None:
        if source == target:
            return
        if source < 0:
            self._connect_material_preview_lane_to_node(
                self._material_preview_lane_row_from_source(source),
                target,
                clear_routing_before_refresh=clear_routing_before_refresh,
            )
            return
        if source not in self._active_material_preview_order() or target not in self._active_material_preview_order():
            return
        if target in self.material_card_preview_connections.get(source, []):
            if clear_routing_before_refresh:
                self._clear_material_preview_routing_mode(refresh=False)
            self.material_card_preview_last_reorder = {
                "source": source,
                "target": target,
                "mode": "duplicate_connection_ignored",
                "commit": "preview_only",
            }
            self._populate_material_miro_uml_preview_scene()
            return
        original_source = source
        source_role_hint = self._material_preview_node_accent_role(source)
        source_incoming = (
            self._material_preview_all_incoming_sources(source)
            if source_side == "left"
            else []
        )
        if source_incoming:
            source_row, source_col = self.material_card_preview_grid_slots.get(source, (0, 0))
            copied_source = self._create_material_preview_node_copy(
                source,
                row=source_row,
                col=source_col + 1,
                mode="source_input_auto_copy_grid_insert",
                select=False,
                populate=False,
            )
            if not copied_source:
                return
            source = copied_source
            self.material_card_preview_last_auto_copy = {
                "source": original_source,
                "connected_source": copied_source,
                "requested_source": original_source,
                "target": target,
                "existing_inputs": list(source_incoming),
                "mode": "source_input_auto_copy",
                "commit": "preview_only",
            }
        incoming_sources = self._material_preview_copy_required_inputs(source, target)
        if incoming_sources and source not in incoming_sources:
            target_row, target_col = self.material_card_preview_grid_slots.get(target, (0, 0))
            original_target = target
            copied_target = self._create_material_preview_node_copy(
                target,
                row=target_row,
                col=target_col + 1,
                mode="single_input_auto_copy_grid_insert",
                select=False,
                populate=False,
            )
            if not copied_target:
                return
            target = copied_target
            self.material_card_preview_last_auto_copy = {
                "source": source,
                "requested_target": original_target,
                "connected_target": copied_target,
                "existing_inputs": list(incoming_sources),
                "mode": "single_input_auto_copy",
                "commit": "preview_only",
            }
        targets = self.material_card_preview_connections.setdefault(source, [])
        if target not in targets:
            targets.append(target)
            self.material_card_preview_connection_roles[(source, target)] = self._default_material_preview_connection_role(
                source,
                target,
            )
            if source_role_hint:
                self.material_card_preview_connection_roles[(source, target)] = source_role_hint
            self.material_card_preview_connection_sides[(source, target)] = (
                "left" if source_side == "left" and source > 0 else "right",
                "left" if target_side == "left" else "right",
            )
        self.material_card_preview_connection_roles = {
            edge: role
            for edge, role in self.material_card_preview_connection_roles.items()
            if edge[0] in self.material_card_preview_connections
            and edge[1] in self.material_card_preview_connections.get(edge[0], [])
        }
        self.material_card_preview_connection_sides = {
            edge: sides
            for edge, sides in self.material_card_preview_connection_sides.items()
            if edge[0] in self.material_card_preview_connections
            and edge[1] in self.material_card_preview_connections.get(edge[0], [])
        }
        if source not in self.material_card_parallel_selections and targets:
            self.material_card_parallel_selections[source] = targets[0]
        source_role = self._material_preview_node_accent_role(source)
        if source_role:
            self._propagate_material_preview_role_from_node(target, source_role)
        self.material_card_preview_generated_order = []
        if clear_routing_before_refresh:
            self._clear_material_preview_routing_mode(refresh=False)
        if _ROUGHCUT_MATERIAL_PREVIEW_AUTO_SORT_ON_CONNECT:
            self._apply_material_preview_r_order_from_connections()
        else:
            self.material_card_preview_last_reorder = {
                "source": source,
                "target": target,
                "mode": "connect_without_auto_sort",
                "commit": "preview_only",
            }
            self._populate_material_miro_uml_preview_scene()

    def _default_material_preview_connection_role(self, source: int, target: int) -> str:
        source_role = self._material_preview_node_accent_role(source)
        if source_role:
            return source_role
        targets = self.material_card_preview_connections.get(source, [])
        try:
            index = targets.index(target)
        except ValueError:
            index = 0
        if index == 0:
            source_row = self.material_card_preview_grid_slots.get(source, (1, 0))[0]
            return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES[
                min(source_row, len(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES) - 1)
            ]
        return _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES[
            min(index, len(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES) - 1)
        ]

    def _material_preview_connection_role(self, source: int, target: int) -> str:
        role = self.material_card_preview_connection_roles.get((source, target))
        if role in _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES:
            return role
        return self._default_material_preview_connection_role(source, target)

    def _cycle_material_preview_connection_role(self, source: int, target: int) -> None:
        if source < 0:
            row = self._material_preview_lane_row_from_source(source)
            if target not in self._material_preview_lane_targets(row):
                return
            self.material_card_preview_generated_order = []
            self.material_card_preview_last_reorder = {
                "source": source,
                "target": target,
                "mode": "story_lane_role_locked_to_card_color",
                "commit": "preview_only",
            }
            self._populate_material_miro_uml_preview_scene()
            return
        if target not in self.material_card_preview_connections.get(source, []):
            return
        current = self._material_preview_connection_role(source, target)
        roles = list(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES)
        next_role = roles[(roles.index(current) + 1) % len(roles)]
        self.material_card_preview_connection_roles[(source, target)] = next_role
        if next_role == "main":
            self.material_card_parallel_selections[source] = target
        self.material_card_preview_generated_order = []
        self._populate_material_miro_uml_preview_scene()

    def _delete_material_preview_connection(self, source: int, target: int) -> None:
        animate_from = self._material_preview_current_group_positions()
        if source < 0:
            row = self._material_preview_lane_row_from_source(source)
            targets = self._material_preview_lane_targets(row)
            if target not in targets:
                return
            self.material_card_preview_lane_connection_roles.pop((row, target), None)
            self._sync_material_preview_lane_targets(row, [node for node in targets if node != target])
            self.material_card_preview_hover_connection = (0, 0)
            self.material_card_preview_generated_order = []
            if _ROUGHCUT_MATERIAL_PREVIEW_AUTO_SORT_ON_CONNECT:
                self._apply_material_preview_r_order_from_connections(animate_from=animate_from)
            else:
                self.material_card_preview_last_reorder = {
                    "source": source,
                    "target": target,
                    "mode": "delete_story_anchor_without_auto_sort",
                    "commit": "preview_only",
                }
                self._populate_material_miro_uml_preview_scene()
            return
        targets = self.material_card_preview_connections.get(source)
        if not targets or target not in targets:
            return
        targets.remove(target)
        self.material_card_preview_connection_roles.pop((source, target), None)
        self.material_card_preview_connection_sides.pop((source, target), None)
        if not targets:
            self.material_card_preview_connections.pop(source, None)
            self.material_card_parallel_selections.pop(source, None)
        elif self.material_card_parallel_selections.get(source) == target:
            self.material_card_parallel_selections[source] = targets[0]
        self.material_card_preview_hover_connection = (0, 0)
        self.material_card_preview_generated_order = []
        if _ROUGHCUT_MATERIAL_PREVIEW_AUTO_SORT_ON_CONNECT:
            self._apply_material_preview_r_order_from_connections(animate_from=animate_from)
        else:
            self.material_card_preview_last_reorder = {
                "source": source,
                "target": target,
                "mode": "delete_connection_without_auto_sort",
                "commit": "preview_only",
            }
            self._populate_material_miro_uml_preview_scene()

    def _material_preview_connection_at_scene_pos(self, scene_pos: QPointF) -> tuple[int, int]:
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        for (source, target), path in self.material_card_preview_connection_paths.items():
            if stroker.createStroke(path).contains(scene_pos):
                return source, target
        return 0, 0

    def _set_material_preview_hover_pin(self, node_number: int, side: str) -> None:
        next_state = (node_number, side)
        next_copy: dict[str, object] = {}
        source = int(getattr(self, "material_card_preview_connect_source", 0) or 0)
        if source and node_number > 0 and side == "left":
            source_side = str(getattr(self, "material_card_preview_connect_source_side", "right") or "right")
            source_existing_inputs = (
                self._material_preview_all_incoming_sources(source)
                if source_side == "left" and source > 0
                else []
            )
            if source_existing_inputs:
                next_copy = {
                    "source": source,
                    "requested_source": source,
                    "target": node_number,
                    "existing_inputs": list(source_existing_inputs),
                    "mode": "source_input_hover_copy_preview",
                    "commit": "preview_only",
                }
            else:
                existing_inputs = self._material_preview_copy_required_inputs(source, node_number)
                if existing_inputs:
                    next_copy = {
                        "source": source,
                        "requested_target": node_number,
                        "existing_inputs": list(existing_inputs),
                        "mode": "hover_copy_preview",
                        "commit": "preview_only",
                    }
        if (
            getattr(self, "material_card_preview_hover_pin", (0, "")) == next_state
            and getattr(self, "material_card_preview_hover_copy_target", {}) == next_copy
        ):
            return
        self.material_card_preview_hover_pin = next_state
        self.material_card_preview_hover_copy_target = next_copy
        self._populate_material_miro_uml_preview_scene()

    def _set_material_preview_connect_source(self, node_number: int, side: str = "right") -> None:
        side = "left" if side == "left" and node_number > 0 else "right"
        if (
            getattr(self, "material_card_preview_connect_source", 0) == node_number
            and getattr(self, "material_card_preview_connect_source_side", "right") == side
        ):
            return
        self.material_card_preview_connect_source = node_number
        self.material_card_preview_connect_source_side = side
        self._populate_material_miro_uml_preview_scene()

    def _set_material_preview_connect_cursor(self, scene_pos: QPointF | None) -> None:
        old_cursor = getattr(self, "material_card_preview_connect_cursor", None)
        if scene_pos is None:
            if old_cursor is None:
                return
            self.material_card_preview_connect_cursor = None
            self._populate_material_miro_uml_preview_scene()
            return
        if old_cursor is not None and (old_cursor - scene_pos).manhattanLength() < 2:
            return
        self.material_card_preview_connect_cursor = QPointF(scene_pos)
        self._populate_material_miro_uml_preview_scene()

    def _set_material_preview_hover_connection(self, source: int, target: int) -> None:
        next_state = (source, target)
        if getattr(self, "material_card_preview_hover_connection", (0, 0)) == next_state:
            return
        self.material_card_preview_hover_connection = next_state
        self._populate_material_miro_uml_preview_scene()

    def _randomize_material_preview_connections(self) -> None:
        rng = random.Random(40132)
        order = list(self._active_material_preview_order())
        rng.shuffle(order)
        self.material_card_preview_connections = {
            order[index]: [order[index + 1]]
            for index in range(len(order) - 1)
        }
        for source_index in range(min(4, len(order) - 3)):
            source = order[source_index]
            extras = [order[source_index + 2], order[source_index + 3]]
            for target in extras:
                if target not in self.material_card_preview_connections[source]:
                    self.material_card_preview_connections[source].append(target)
        self.material_card_parallel_selections = {
            source: targets[0]
            for source, targets in self.material_card_preview_connections.items()
            if targets
        }
        self.material_card_preview_parallel_column_counts = ()
        self.material_card_preview_connection_roles = {
            (source, target): _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES[
                min(index, len(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES) - 1)
            ]
            for source, targets in self.material_card_preview_connections.items()
            for index, target in enumerate(targets)
        }
        self.material_card_preview_connection_sides = {
            (source, target): ("right", "left")
            for source, targets in self.material_card_preview_connections.items()
            for target in targets
        }
        self.material_card_preview_generated_order = []
        if _ROUGHCUT_MATERIAL_PREVIEW_AUTO_SORT_ON_CONNECT:
            self._apply_material_preview_r_order_from_connections()
        else:
            self.material_card_preview_last_reorder = {
                "mode": "random_connect_without_auto_sort",
                "commit": "preview_only",
            }
            self._populate_material_miro_uml_preview_scene()

    def _selected_material_connection_sequence(self) -> list[int]:
        return selected_storyboard_connection_sequence(
            self._active_material_preview_order(),
            self.material_card_preview_connections,
            self.material_card_preview_connection_roles,
            self.material_card_parallel_selections,
        )

    def _connect_material_preview_lane_to_node(
        self,
        row: int,
        target: int,
        *,
        clear_routing_before_refresh: bool = False,
    ) -> None:
        if target not in self._active_material_preview_order():
            return
        row = max(0, min(len(STORYBOARD_ROW_LABELS) - 1, int(row)))
        lane_source = self._material_preview_lane_source_id(row)
        if row not in self._material_preview_story_rows():
            rows = self._material_preview_story_rows()
            rows.append(row)
            rows.sort()
            self.material_story_card_rows = rows
            if not hasattr(self, "material_story_card_labels"):
                self.material_story_card_labels = {}
            self.material_story_card_labels.setdefault(row, f"스토리 {len(rows)}")
        targets = self._material_preview_lane_targets(row)
        if target in targets:
            if clear_routing_before_refresh:
                self._clear_material_preview_routing_mode(refresh=False)
            self.material_card_preview_last_reorder = {
                "source": lane_source,
                "target": target,
                "mode": "duplicate_story_anchor_ignored",
                "commit": "preview_only",
            }
            self._populate_material_miro_uml_preview_scene()
            return
        incoming_sources = self._material_preview_copy_required_inputs(lane_source, target)
        if incoming_sources and lane_source not in incoming_sources:
            _target_row, target_col = self.material_card_preview_grid_slots.get(target, (row, 0))
            original_target = target
            copied_target = self._create_material_preview_node_copy(
                target,
                row=row,
                col=target_col + 1,
                mode="story_anchor_auto_copy_grid_insert",
                select=False,
                populate=False,
            )
            if not copied_target:
                return
            target = copied_target
            self.material_card_preview_last_auto_copy = {
                "source": lane_source,
                "requested_target": original_target,
                "connected_target": copied_target,
                "existing_inputs": list(incoming_sources),
                "mode": "story_anchor_auto_copy",
                "commit": "preview_only",
            }
        if target not in targets:
            targets.append(target)
        self._sync_material_preview_lane_targets(row, targets)
        self._propagate_material_preview_role_from_node(target, self._material_preview_story_row_role(row))
        self.material_card_preview_generated_order = []
        if clear_routing_before_refresh:
            self._clear_material_preview_routing_mode(refresh=False)
        if _ROUGHCUT_MATERIAL_PREVIEW_AUTO_SORT_ON_CONNECT:
            self._apply_material_preview_r_order_from_connections()
        else:
            self.material_card_preview_last_reorder = {
                "source": lane_source,
                "target": target,
                "mode": "connect_story_anchor_without_auto_sort",
                "commit": "preview_only",
            }
            self._populate_material_miro_uml_preview_scene()

    def _apply_material_preview_r_order_from_connections(
        self,
        *,
        animate_from: dict[int, QPointF] | None = None,
        ordered_nodes: list[int] | None = None,
    ) -> None:
        if animate_from is None:
            animate_from = self._material_preview_current_group_positions()
        old_order = list(self.material_card_preview_order)
        active_nodes = list(ordered_nodes) if ordered_nodes is not None else self._active_material_preview_order()
        lane_anchor_targets = self._material_preview_lane_anchor_targets()
        plan = build_storyboard_layout_plan(
            active_nodes,
            self.material_card_preview_connections,
            self.material_card_preview_connection_roles,
            parallel_selections=self.material_card_parallel_selections,
            lane_anchors=self.material_card_preview_lane_connections,
            lane_anchor_roles={
                row: self._material_preview_story_row_role(row)
                for row in self.material_card_preview_lane_connections
            },
            lane_anchor_targets=lane_anchor_targets,
            lane_anchor_target_roles=self._material_preview_lane_anchor_target_roles(),
            parallel_column_counts=self.material_card_preview_parallel_column_counts,
            deleted_nodes=self.material_card_preview_deleted_nodes,
        )
        self.material_card_preview_order = list(plan.order)
        self.material_card_preview_grid_slots = dict(plan.grid_slots)
        self.material_card_preview_sort_vectors = [
            {
                "ordinal": vector.ordinal,
                "source": vector.source,
                "target": vector.target,
                "role": vector.role,
                "source_grid": {"row": vector.source_row, "col": vector.source_col},
                "target_grid": {"row": vector.target_row, "col": vector.target_col},
                "delta": {"row": vector.delta_row, "col": vector.delta_col},
                "manhattan_grid_distance": vector.manhattan_grid_distance,
            }
            for vector in plan.vectors
        ]
        self.material_card_preview_last_reorder = {
            "old_order": old_order,
            "new_order": list(plan.order),
            "sort_vectors": list(self.material_card_preview_sort_vectors),
            "mode": "auto_r_parallel_order",
            "commit": "preview_only",
        }
        self.material_card_preview_generated_order = []
        self._populate_material_miro_uml_preview_scene(animate_from=animate_from)

    def _apply_material_preview_parallel_group_layout(
        self,
        group_counts: tuple[int, ...] | list[int],
        *,
        ordered_nodes: list[int] | None = None,
    ) -> None:
        active_order = self._active_material_preview_order()
        active_set = set(active_order)
        ordered: list[int] = []
        for node in ordered_nodes or active_order:
            node = int(node)
            if node in active_set and node not in ordered:
                ordered.append(node)
        ordered.extend(node for node in active_order if node not in ordered)
        self.material_card_preview_parallel_column_counts = tuple(
            count for count in (int(raw_count) for raw_count in group_counts) if count > 0
        )
        self._apply_material_preview_r_order_from_connections(ordered_nodes=ordered)

    def _select_material_preview_parallel_target(self, node_number: int) -> None:
        if node_number not in self._active_material_preview_order():
            return
        self.material_card_preview_selected_node = node_number
        self.scenario_sequence_layer = "card_detail"
        for source, targets in self.material_card_preview_connections.items():
            if node_number in targets:
                self.material_card_parallel_selections[source] = node_number
                break
        if self.material_card_preview_multi_select_enabled and node_number not in self.material_card_preview_multi_selection:
            self.material_card_preview_multi_selection.append(node_number)
        self._populate_material_miro_uml_preview_scene()

    def _toggle_material_multi_select(self) -> None:
        self.material_card_preview_multi_select_enabled = self.material_multi_select_btn.isChecked()
        if not self.material_card_preview_multi_select_enabled:
            self.material_card_preview_multi_selection.clear()
        else:
            self.material_card_preview_multi_selection.clear()
        self._populate_material_miro_uml_preview_scene()

    def _merge_material_preview_selection(self) -> None:
        selection = [node for node in self.material_card_preview_multi_selection if node in self._active_material_preview_order()]
        if len(selection) < 2:
            return
        survivor = selection[0]
        removed = selection[1:]
        self.material_card_preview_merged_nodes[survivor] = selection
        self.material_card_preview_deleted_nodes.update(removed)
        self.material_card_preview_order = [node for node in self.material_card_preview_order if node not in removed]
        self.material_card_preview_connections = {
            source: [target for target in targets if target not in removed]
            for source, targets in self.material_card_preview_connections.items()
            if source not in removed
        }
        self.material_card_preview_connection_roles = {
            edge: role
            for edge, role in self.material_card_preview_connection_roles.items()
            if edge[0] not in removed and edge[1] not in removed
        }
        self.material_card_preview_connection_sides = {
            edge: sides
            for edge, sides in self.material_card_preview_connection_sides.items()
            if edge[0] not in removed and edge[1] not in removed
        }
        self.material_card_parallel_selections = {
            source: target
            for source, target in self.material_card_parallel_selections.items()
            if source not in removed and target not in removed
        }
        self.material_card_preview_selected_node = survivor
        self.material_card_preview_multi_selection = [survivor]
        self._apply_material_preview_r_order_from_connections()

    def _split_material_preview_selection(self) -> None:
        source = self.material_card_preview_selected_node
        if source not in self._active_material_preview_order():
            return
        next_node = max(self.material_card_preview_order or [0]) + 1
        self.material_card_preview_next_node = max(self.material_card_preview_next_node, next_node + 1)
        source_index = self.material_card_preview_order.index(source)
        self.material_card_preview_order.insert(source_index + 1, next_node)
        source_row, source_col = self.material_card_preview_grid_slots.get(source, (1, 0))
        self._place_material_preview_node_at_grid_slot(next_node, source_row, source_col + 1)
        self.material_card_preview_source_nodes[next_node] = self.material_card_preview_source_nodes.get(source, source)
        self.material_card_preview_split_children.setdefault(source, []).append(next_node)
        self.material_card_preview_selected_node = next_node
        self.material_card_preview_multi_selection = [next_node] if self.material_card_preview_multi_select_enabled else []
        self._populate_material_miro_uml_preview_scene()

    def _adjust_material_preview_trim(self, side: str, delta: int) -> None:
        node = self.material_card_preview_selected_node
        if node not in self._active_material_preview_order():
            return
        state = self.material_card_preview_trim_state.setdefault(node, {"left": 0, "right": 0})
        state[side] = state.get(side, 0) + delta
        self._populate_material_miro_uml_preview_scene()

    def _delete_material_preview_selection(self) -> None:
        targets = list(self.material_card_preview_multi_selection) if self.material_card_preview_multi_select_enabled else []
        if not targets and self.material_card_preview_selected_node:
            targets = [self.material_card_preview_selected_node]
        targets = [node for node in targets if node in self._active_material_preview_order()]
        if not targets:
            return
        self.material_card_preview_deleted_nodes.update(targets)
        self.material_card_preview_order = [node for node in self.material_card_preview_order if node not in targets]
        self.material_card_preview_connections = {
            source: [target for target in targets_list if target not in targets]
            for source, targets_list in self.material_card_preview_connections.items()
            if source not in targets
        }
        self.material_card_preview_connection_roles = {
            edge: role
            for edge, role in self.material_card_preview_connection_roles.items()
            if edge[0] not in targets and edge[1] not in targets
        }
        self.material_card_preview_connection_sides = {
            edge: sides
            for edge, sides in self.material_card_preview_connection_sides.items()
            if edge[0] not in targets and edge[1] not in targets
        }
        self.material_card_parallel_selections = {
            source: target
            for source, target in self.material_card_parallel_selections.items()
            if source not in targets and target not in targets
        }
        active = self._active_material_preview_order()
        self.material_card_preview_selected_node = active[0] if active else 0
        self.material_card_preview_multi_selection.clear()
        self._apply_material_preview_r_order_from_connections()

    def _copy_material_preview_selection(self) -> None:
        selection = list(self.material_card_preview_multi_selection) if self.material_card_preview_multi_select_enabled else []
        if not selection and self.material_card_preview_selected_node:
            selection = [self.material_card_preview_selected_node]
        self.material_card_preview_clipboard = [
            node for node in selection if node in self._active_material_preview_order()
        ]

    def _copy_material_preview_node_for_drag(self, source_node: int) -> str:
        next_node = self._create_material_preview_node_copy(
            source_node,
            mode="right_drag_copy_grid_insert",
            select=True,
            populate=True,
        )
        return f"middle_segment_preview_node_{next_node:02d}" if next_node else ""

    def _paste_material_preview_clipboard(self) -> None:
        if not self.material_card_preview_clipboard:
            return
        anchor = self.material_card_preview_selected_node
        anchor_row, anchor_col = self.material_card_preview_grid_slots.get(anchor, (1, -1))
        pasted_nodes: list[int] = []
        for offset, source_node in enumerate(self.material_card_preview_clipboard, start=1):
            if source_node not in self.material_card_preview_source_nodes:
                continue
            next_node = self.material_card_preview_next_node
            self.material_card_preview_next_node += 1
            self.material_card_preview_source_nodes[next_node] = self._material_preview_source_node(source_node)
            if source_node in self.material_card_preview_trim_state:
                self.material_card_preview_trim_state[next_node] = dict(self.material_card_preview_trim_state[source_node])
            self.material_card_preview_order.append(next_node)
            self._place_material_preview_node_at_grid_slot(next_node, anchor_row, anchor_col + offset)
            pasted_nodes.append(next_node)
        if not pasted_nodes:
            return
        self.material_card_preview_selected_node = pasted_nodes[-1]
        self.material_card_preview_multi_selection = pasted_nodes if self.material_card_preview_multi_select_enabled else []
        self.material_card_preview_last_reorder = {
            "copied_nodes": list(self.material_card_preview_clipboard),
            "pasted_nodes": list(pasted_nodes),
            "mode": "copy_paste_grid_insert",
            "commit": "preview_only",
        }
        self._populate_material_miro_uml_preview_scene()

    def _generate_material_preview_scenario(self) -> None:
        self.scenario_sequence_layer = "sequence"
        self.material_card_preview_generated_order = self._selected_material_connection_sequence()
        self._refresh_scenario_sequence_preview()

    def _refresh_scenario_sequence_preview(self) -> None:
        scene = getattr(self, "scenario_sequence_scene", None)
        if scene is None:
            return
        scene.clear()
        selected_node = getattr(self, "material_card_preview_selected_node", 0)
        generated = list(getattr(self, "material_card_preview_generated_order", []))
        if (
            getattr(self, "scenario_sequence_layer", "sequence") == "card_detail"
            and selected_node in self._active_material_preview_order()
        ):
            self._draw_scenario_card_detail_layer(scene, selected_node)
            return
        active_sequence = generated or ([selected_node] if selected_node else [])
        scene_width = max(1200, 46 + (len(active_sequence) * 154))
        scene.setSceneRect(0, 0, scene_width, 190)
        self.scenario_sequence_cards = []
        self.scenario_sequence_summaries = []

        preview_font = QFont()
        preview_font.setPointSize(9)
        preview_font.setBold(True)
        summary_font = QFont()
        summary_font.setPointSize(8)
        summary_font.setBold(True)
        topic_font = QFont()
        topic_font.setPointSize(10)
        topic_font.setBold(True)
        subtitle_font = QFont()
        subtitle_font.setPointSize(8)
        pen = QPen(QColor("#F5F7FA"), 1)
        for row_index, label in enumerate(STORYBOARD_ROW_LABELS):
            row_nodes = [
                node
                for node in self._active_material_preview_order()
                if self.material_card_preview_grid_slots.get(node, (0, 0))[0] == row_index
            ]
            duration_sec = storyboard_row_duration_seconds(row_nodes, self.material_card_preview_trim_state)
            self.scenario_sequence_summaries.append(
                {
                    "row": row_index,
                    "label": label,
                    "nodes": list(row_nodes),
                    "duration_sec": duration_sec,
                }
            )
            chip_x = 24 + (row_index * 178)
            chip_path = QPainterPath()
            chip_path.addRoundedRect(QRectF(chip_x, 10, 162, 26), 8, 8)
            role = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES[
                min(row_index, len(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES) - 1)
            ]
            role_color = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, "#5A6A76")
            scene.addPath(chip_path, QPen(QColor(role_color), 1), QBrush(QColor("#0A0F12")))
            summary_text = scene.addText(f"{label} {duration_sec:.1f}s · {len(row_nodes)}컷", summary_font)
            summary_text.setDefaultTextColor(QColor("#DCE3EA"))
            summary_text.setPos(chip_x + 10, 16)
        for index, node_number in enumerate(active_sequence):
            x_pos = 24 + (index * 154)
            y_pos = 58
            card_path = QPainterPath()
            card_path.addRoundedRect(QRectF(x_pos, y_pos, 132, 96), 8, 8)
            scene.addPath(card_path, pen, QBrush(QColor("#0F1518")))
            preview_path = QPainterPath()
            preview_path.addRoundedRect(QRectF(x_pos + 10, y_pos + 10, 112, 42), 6, 6)
            scene.addPath(preview_path, QPen(QColor("#1D2730"), 1), QBrush(QColor("#05080A")))
            preview_text = scene.addText("영상", preview_font)
            preview_text.setDefaultTextColor(QColor("#8A949E"))
            preview_text.setPos(x_pos + 54, y_pos + 20)
            topic_text = scene.addText(f"카드 {self._node_label(node_number)}", topic_font)
            topic_text.setDefaultTextColor(QColor("#DCE3EA"))
            topic_text.setPos(x_pos + 10, y_pos + 56)
            trim_state = self.material_card_preview_trim_state.get(node_number, {"left": 0, "right": 0})
            subtitle_label = f"자막 preview L{trim_state.get('left', 0):+d} R{trim_state.get('right', 0):+d}"
            subtitle_text = scene.addText(subtitle_label, subtitle_font)
            subtitle_text.setDefaultTextColor(QColor("#8A949E"))
            subtitle_text.setPos(x_pos + 10, y_pos + 76)
            self.scenario_sequence_cards.append(
                {
                    "node": node_number,
                    "x": x_pos,
                    "y": y_pos,
                    "generated": bool(generated),
                    "layer": "sequence",
                }
            )

    def _draw_scenario_card_detail_layer(self, scene: QGraphicsScene, node_number: int) -> None:
        scene.setSceneRect(0, 0, 1200, 190)
        self.scenario_sequence_cards = []
        self.scenario_sequence_summaries = []
        source_node = self._material_preview_source_node(node_number)
        row, col = self.material_card_preview_grid_slots.get(node_number, (0, 0))
        row_label = STORYBOARD_ROW_LABELS[min(max(row, 0), len(STORYBOARD_ROW_LABELS) - 1)]
        trim_state = self.material_card_preview_trim_state.get(node_number, {"left": 0, "right": 0})
        duration_sec = storyboard_row_duration_seconds([node_number], self.material_card_preview_trim_state)
        self.scenario_sequence_detail = {
            "node": node_number,
            "source_node": source_node,
            "row": row,
            "col": col,
            "row_label": row_label,
            "duration_sec": duration_sec,
            "trim": dict(trim_state),
            "layer": "card_detail",
        }

        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        label_font = QFont()
        label_font.setPointSize(9)
        value_font = QFont()
        value_font.setPointSize(10)
        value_font.setBold(True)

        role = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES[
            min(max(row, 0), len(_ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLES) - 1)
        ]
        role_color = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, "#5A6A76")
        detail_path = QPainterPath()
        detail_path.addRoundedRect(QRectF(24, 18, 560, 142), 10, 10)
        scene.addPath(detail_path, QPen(QColor(role_color), 2), QBrush(QColor("#0A0F12")))

        title = scene.addText(f"카드 {self._node_label(node_number)} 상세", title_font)
        title.setDefaultTextColor(QColor("#F5F7FA"))
        title.setPos(46, 32)
        source_text = scene.addText(f"원본 중분류 {source_node:02d} · {row_label} · {col + 1}열", value_font)
        source_text.setDefaultTextColor(QColor("#DCE3EA"))
        source_text.setPos(46, 62)

        fields = (
            ("영상", "선택 카드 미리보기"),
            ("자막", f"자막 preview L{trim_state.get('left', 0):+d} R{trim_state.get('right', 0):+d}"),
            ("길이", f"{duration_sec:.1f}s"),
            ("레이어", "선택 카드 상세"),
        )
        for index, (label, value) in enumerate(fields):
            x_pos = 46 + ((index % 2) * 252)
            y_pos = 98 + ((index // 2) * 32)
            label_item = scene.addText(label, label_font)
            label_item.setDefaultTextColor(QColor("#8A949E"))
            label_item.setPos(x_pos, y_pos)
            value_item = scene.addText(value, label_font)
            value_item.setDefaultTextColor(QColor("#DCE3EA"))
            value_item.setPos(x_pos + 54, y_pos)

        hint = scene.addText("시나리오생성 버튼을 누르면 선택 상세를 뒤로 보내고 순서 레이어를 다시 표시합니다.", label_font)
        hint.setDefaultTextColor(QColor("#8A949E"))
        hint.setPos(620, 44)
        self.scenario_sequence_cards.append(
            {
                "node": node_number,
                "x": 24,
                "y": 18,
                "generated": False,
                "layer": "card_detail",
            }
        )

    def _draw_material_preview_story_cards(self, scene: QGraphicsScene, font: QFont) -> None:
        hover_pin = getattr(self, "material_card_preview_hover_pin", (0, ""))
        connect_source = getattr(self, "material_card_preview_connect_source", 0)
        label_font = QFont(font)
        label_font.setPointSize(9)
        label_font.setBold(True)
        plus_font = QFont(font)
        plus_font.setPointSize(16)
        plus_font.setBold(True)

        for row in self._material_preview_story_plus_rows():
            rect = self._material_preview_story_card_rect(row)
            plus_path = QPainterPath()
            plus_path.addRoundedRect(rect, 10, 10)
            plus_card = scene.addPath(plus_path, QPen(QColor("#5A6570"), 1), QBrush(QColor("#5A6570")))
            plus_card.setOpacity(0.5)
            plus_card.setZValue(1.2)
            plus_card.setData(0, f"middle_segment_storyboard_plus_{row}")
            plus_text = scene.addText("+", plus_font)
            plus_text.setDefaultTextColor(QColor("#DCE3EA"))
            plus_rect = plus_text.boundingRect()
            plus_text.setPos(
                rect.center().x() - (plus_rect.width() / 2),
                rect.center().y() - (plus_rect.height() / 2) - 1,
            )
            plus_text.setOpacity(0.78)
            plus_text.setZValue(1.3)
            plus_text.setData(0, f"middle_segment_storyboard_plus_text_{row}")

        for row in self._material_preview_story_rows():
            rect = self._material_preview_story_card_rect(row)
            role = self._material_preview_story_row_role(row)
            role_color = _ROUGHCUT_MATERIAL_PREVIEW_CONNECTION_ROLE_COLORS.get(role, "#34C759")
            source = self._material_preview_lane_source_id(row)
            hovered = hover_pin == (source, "right")
            connected = row in getattr(self, "material_card_preview_lane_connections", {})
            card_path = QPainterPath()
            card_path.addRoundedRect(rect, 10, 10)
            card = scene.addPath(
                card_path,
                QPen(QColor("#F5F7FA" if hovered else role_color), 2),
                QBrush(QColor("#101820")),
            )
            card.setZValue(1.5)
            card.setData(0, f"middle_segment_storyboard_card_{row}")
            label = scene.addText(self._material_preview_story_card_label(row), label_font)
            label.setDefaultTextColor(QColor("#F5F7FA"))
            label_rect = label.boundingRect()
            label.setPos(rect.left() + 12, rect.center().y() - (label_rect.height() / 2) - 1)
            label.setZValue(1.6)
            label.setData(0, f"middle_segment_storyboard_card_label_{row}")
            pin_color = (
                "#00C8FF"
                if hovered and connect_source != source
                else (role_color if connected or connect_source == source else "#0A0F12")
            )
            pin_pos = self._material_preview_lane_pin_position(row)
            pin = scene.addEllipse(
                pin_pos.x() - _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                pin_pos.y() - _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                QPen(QColor("#F5F7FA" if hovered or connect_source == source else "#DCE3EA"), 1),
                QBrush(QColor(pin_color)),
            )
            pin.setZValue(1.8)
            pin.setData(0, f"middle_segment_storyboard_lane_pin_{row}")

    def _draw_material_preview_grid(self, scene: QGraphicsScene) -> None:
        scene_rect = scene.sceneRect()
        cell = _ROUGHCUT_MATERIAL_PREVIEW_GRID_CELL_SIZE
        origin_x = _ROUGHCUT_MATERIAL_PREVIEW_START_X % cell
        origin_y = _ROUGHCUT_MATERIAL_PREVIEW_START_Y % cell
        cols = int((scene_rect.width() + origin_x) // cell) + 2
        rows = int((scene_rect.height() + origin_y) // cell) + 2
        line_pen = QPen(QColor("#182630"), 1)
        no_pen = QPen(Qt.PenStyle.NoPen)
        fill_a = QColor("#071014")
        fill_b = QColor("#09151B")
        for row in range(rows):
            for col in range(cols):
                x_pos = origin_x + (col * cell)
                y_pos = origin_y + (row * cell)
                square = scene.addRect(
                    x_pos,
                    y_pos,
                    cell,
                    cell,
                    no_pen,
                    QBrush(fill_b if (row + col) % 2 else fill_a),
                )
                square.setOpacity(0.36)
                square.setZValue(-3)
                square.setData(0, "middle_segment_preview_grid_square")
        for col in range(cols + 1):
            x_pos = origin_x + (col * cell)
            line = scene.addLine(x_pos, 0, x_pos, scene_rect.height(), line_pen)
            line.setOpacity(0.42)
            line.setZValue(-2)
            line.setData(0, "middle_segment_preview_grid_line")
        for row in range(rows + 1):
            y_pos = origin_y + (row * cell)
            line = scene.addLine(0, y_pos, scene_rect.width(), y_pos, line_pen)
            line.setOpacity(0.42)
            line.setZValue(-2)
            line.setData(0, "middle_segment_preview_grid_line")

    def _populate_material_miro_uml_preview_scene(
        self,
        *,
        animate_from: dict[int, QPointF] | None = None,
    ) -> None:
        scene = self.material_card_preview_scene
        self._refresh_material_preview_scene_rect()
        self._stop_material_preview_card_animations()
        scene.clear()
        self.material_card_preview_drag_shadow_item = None
        node_positions = self._material_preview_slot_positions()
        animation_moves: list[tuple[object, QPointF, QPointF]] = []
        preview_font = QFont()
        preview_font.setPointSize(9)
        preview_font.setBold(True)
        topic_font = QFont()
        topic_font.setPointSize(10)
        topic_font.setBold(True)
        badge_font = QFont()
        badge_font.setPointSize(12)
        badge_font.setBold(True)
        lane_font = QFont()
        lane_font.setPointSize(9)
        lane_font.setBold(True)
        self.material_card_preview_nodes.clear()
        self._material_card_preview_groups.clear()

        self._draw_material_preview_grid(scene)
        self._draw_material_preview_story_cards(scene, lane_font)

        for slot_index, node_number in enumerate(self.material_card_preview_order, start=1):
            x_pos, y_pos = node_positions[slot_index - 1]
            node_id = f"middle_segment_preview_node_{node_number:02d}"
            is_selected_parallel = node_number in set(self.material_card_parallel_selections.values())
            is_selected_node = node_number == getattr(self, "material_card_preview_selected_node", 0)
            is_multi_selected = node_number in getattr(self, "material_card_preview_multi_selection", [])
            source_color = self._material_preview_source_color(node_number)
            accent_role = self._material_preview_node_accent_role(node_number)
            accent_color = self._material_preview_node_accent_color(node_number)
            has_input_color = bool(accent_role)
            border_color = (
                accent_color
                if has_input_color
                else (source_color if self._material_preview_source_node(node_number) != node_number else "#2D3942")
            )
            if is_selected_parallel:
                border_color = accent_color
            if is_selected_node or is_multi_selected:
                border_color = "#F5F7FA"
            node_path = QPainterPath()
            node_path.addRoundedRect(
                QRectF(
                    0,
                    0,
                    _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH,
                    _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT,
                ),
                8,
                8,
            )
            node = scene.addPath(node_path, QPen(QColor(border_color), 1), QBrush(QColor("#0F1518")))
            node.setData(0, node_id)

            source_strip = scene.addRect(
                9,
                10,
                4,
                _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT - 20,
                QPen(QColor(accent_color), 0),
                QBrush(QColor(accent_color)),
            )
            source_strip.setOpacity(
                0.9
                if has_input_color or self._material_preview_source_node(node_number) != node_number
                else 0.45
            )

            preview_path = QPainterPath()
            preview_path.addRoundedRect(
                QRectF(18, 10, _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH - 36, 38),
                6,
                6,
            )
            preview = scene.addPath(preview_path, QPen(QColor("#1D2730"), 1), QBrush(QColor("#05080A")))
            preview.setData(0, f"middle_segment_preview_slot_{slot_index:02d}")

            preview_text = scene.addText("미리보기", preview_font)
            preview_text.setDefaultTextColor(QColor("#8A949E"))
            preview_rect = preview_text.boundingRect()
            preview_text.setPos(
                (_ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH - preview_rect.width()) / 2,
                20,
            )

            topic_text = scene.addText("중분류 주제", topic_font)
            topic_text.setDefaultTextColor(QColor("#DCE3EA"))
            topic_text.setPos(18, 52)

            if node_number in getattr(self, "material_card_preview_multi_selection", []):
                badge_value = self.material_card_preview_multi_selection.index(node_number) + 1
                badge_label = str(badge_value)
            else:
                badge_label = self._node_label(node_number)
            badge_text = scene.addText(badge_label, badge_font)
            badge_text.setDefaultTextColor(QColor("#F5F7FA"))
            badge_rect = badge_text.boundingRect()
            badge_width = max(30, int(badge_rect.width()) + 12)
            badge_bg_path = QPainterPath()
            badge_bg_path.addRoundedRect(QRectF(18, 6, badge_width, 22), 6, 6)
            badge_bg = scene.addPath(
                badge_bg_path,
                QPen(QColor(accent_color), 1),
                QBrush(QColor("#101820")),
            )
            badge_bg.setOpacity(0.92)
            badge_bg.setData(0, f"middle_segment_preview_badge_bg_{node_number}")
            badge_text.setData(0, f"middle_segment_preview_badge_{node_number}")
            badge_text.setPos(24, 3)

            hover_pin = getattr(self, "material_card_preview_hover_pin", (0, ""))
            connect_source = getattr(self, "material_card_preview_connect_source", 0)
            connect_source_side = getattr(self, "material_card_preview_connect_source_side", "right")
            hover_copy_target = getattr(self, "material_card_preview_hover_copy_target", {}) or {}
            left_pin_hovered = hover_pin == (node_number, "left")
            right_pin_hovered = hover_pin == (node_number, "right")
            left_pin_source_active = connect_source == node_number and connect_source_side == "left"
            right_pin_source_active = connect_source == node_number and connect_source_side == "right"
            left_pin_copy_hovered = (
                left_pin_hovered
                and (
                    int(hover_copy_target.get("requested_target", 0) or 0) == node_number
                    or int(hover_copy_target.get("target", 0) or 0) == node_number
                )
            )
            left_pin_color = (
                "#FFD60A"
                if left_pin_copy_hovered
                else ("#00C8FF" if left_pin_hovered else self._material_preview_pin_role_color(node_number, "left"))
            )
            right_pin_color = (
                "#00C8FF"
                if right_pin_hovered and connect_source != node_number
                else self._material_preview_pin_role_color(node_number, "right")
            )
            left_pin_brush = QBrush(QColor(left_pin_color))
            right_pin_brush = QBrush(QColor(right_pin_color))
            left_pin_pen = QPen(
                QColor("#F5F7FA" if left_pin_hovered or left_pin_source_active else "#DCE3EA"),
                2 if left_pin_copy_hovered or left_pin_source_active else 1,
            )
            right_pin_pen = QPen(
                QColor("#F5F7FA" if right_pin_hovered or right_pin_source_active else "#DCE3EA"),
                1,
            )
            left_pin = scene.addEllipse(
                -_ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2) - _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                left_pin_pen,
                left_pin_brush,
            )
            right_pin = scene.addEllipse(
                _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH - _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2) - _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                right_pin_pen,
                right_pin_brush,
            )
            left_pin.setData(0, f"middle_segment_preview_pin_{node_number}_left")
            right_pin.setData(0, f"middle_segment_preview_pin_{node_number}_right")

            group = scene.createItemGroup([node, source_strip, preview, preview_text, topic_text, badge_bg, badge_text, left_pin, right_pin])
            group.setData(0, node_id)
            group.setPos(x_pos, y_pos)
            group.setZValue(2)
            group.setCursor(Qt.CursorShape.OpenHandCursor)
            self._material_card_preview_groups[node_id] = group
            if animate_from and node_number in animate_from:
                old_pos = QPointF(animate_from[node_number])
                new_pos = QPointF(float(x_pos), float(y_pos))
                if (old_pos - new_pos).manhattanLength() >= 1:
                    animation_moves.append((group, old_pos, new_pos))

            self.material_card_preview_nodes.append(
                {
                    "id": node_id,
                    "x": x_pos,
                    "y": y_pos,
                    "width": _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH,
                    "height": _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT,
                    "labels": ("미리보기", "중분류 주제"),
                    "slot": slot_index,
                }
            )
        self._draw_material_preview_connections()
        self._draw_material_preview_drag_shadow()
        self._refresh_scenario_sequence_preview()
        if animation_moves:
            self._start_material_preview_card_animations(animation_moves)

    def _material_preview_node_id_at_scene_pos(self, scene_pos: QPointF) -> str:
        for node_id, group in sorted(
            self._material_card_preview_groups.items(),
            key=lambda item: item[1].zValue(),
            reverse=True,
        ):
            if group.sceneBoundingRect().contains(scene_pos):
                return node_id
        return ""

    def _begin_material_preview_node_drag(self, node_id: str) -> None:
        group = self._material_card_preview_groups.get(node_id)
        if group is None:
            return
        group.setZValue(10)
        group.setOpacity(0.88)
        self._update_material_preview_drag_shadow(node_id, group.sceneBoundingRect().center())

    def _drag_material_preview_node_to(self, node_id: str, scene_pos: QPointF) -> None:
        group = self._material_card_preview_groups.get(node_id)
        if group is None:
            return
        scene_rect = self.material_card_preview_scene.sceneRect()
        max_x = scene_rect.right() - _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH
        max_y = scene_rect.bottom() - _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT
        target_x = min(max(scene_rect.left(), scene_pos.x()), max_x)
        target_y = min(max(scene_rect.top(), scene_pos.y()), max_y)
        snapped = self._material_preview_snap_point_to_grid(QPointF(target_x, target_y))
        target_x = min(max(scene_rect.left(), snapped.x()), max_x)
        target_y = min(max(scene_rect.top(), snapped.y()), max_y)
        group.setPos(target_x, target_y)
        self._update_material_preview_drag_shadow(node_id, QPointF(target_x, target_y) + QPointF(
            _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH / 2,
            _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2,
        ))

    def _finish_material_preview_node_drag(
        self,
        node_id: str,
        scene_pos: QPointF,
        *,
        insert_shift: bool = False,
    ) -> None:
        group = self._material_card_preview_groups.get(node_id)
        if group is None:
            return
        node_number = int(node_id.rsplit("_", 1)[1])
        node_center = group.sceneBoundingRect().center()
        target_row, target_col = self._material_preview_grid_slot_for_scene_pos(node_center)
        old_order = list(self.material_card_preview_order)
        old_slots = dict(self.material_card_preview_grid_slots)
        if insert_shift:
            self._place_material_preview_node_at_grid_slot(node_number, target_row, target_col)
            move_result = {
                "mode": "grid_insert_shift",
                "swapped_with": 0,
                "old_grid": {
                    "row": old_slots.get(node_number, (target_row, target_col))[0],
                    "col": old_slots.get(node_number, (target_row, target_col))[1],
                },
                "target_grid": {"row": target_row, "col": target_col},
            }
        else:
            move_result = self._move_material_preview_node_to_grid_slot(node_number, target_row, target_col)
        new_order = list(self.material_card_preview_order)
        self.material_card_preview_last_reorder = {
            "node_id": node_id,
            "old_order": old_order,
            "new_order": list(new_order),
            "old_slots": old_slots,
            "new_slots": dict(self.material_card_preview_grid_slots),
            "target_slot": (target_col * _ROUGHCUT_MATERIAL_PREVIEW_ROWS) + target_row + 1,
            "target_grid": {"row": target_row, "col": target_col},
            "old_grid": move_result["old_grid"],
            "swapped_with": move_result["swapped_with"],
            "mode": move_result["mode"],
            "commit": "preview_only",
        }
        self._clear_material_preview_drag_shadow()
        self._populate_material_miro_uml_preview_scene()

    def _build_roughcut_video_player_surface(self, frame: QFrame) -> None:
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 9, 10, 9)
        lay.setSpacing(7)

        self.roughcut_video_title_lbl = QLabel("비디오", frame)
        self.roughcut_video_title_lbl.setStyleSheet(label_style("text", 11, bold=True))
        self.roughcut_video_title_lbl.hide()
        self.roughcut_video_state_lbl = QLabel("대기", frame)
        self.roughcut_video_state_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.roughcut_video_state_lbl.setStyleSheet(self._toolbar_badge_style("#A9B0B7", "#2D3942"))
        self.roughcut_video_state_lbl.hide()

        self.video_host = QFrame()
        self.video_host.setObjectName("roughcutVideoHost")
        self.video_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_host.setMinimumHeight(_ROUGHCUT_VIDEO_HOST_MIN_HEIGHT)
        self.video_host.setStyleSheet(
            "QFrame#roughcutVideoHost { background: #000000; border: 1px solid #1D2730; border-radius: 6px; }"
        )
        self.video_host_layout = QVBoxLayout(self.video_host)
        self.video_host_layout.setContentsMargins(0, 0, 0, 0)
        self.video_host_layout.setSpacing(0)
        self.video_host_placeholder = QLabel("비디오 대기")
        self.video_host_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_host_placeholder.setStyleSheet(label_style("muted", 10))
        self.video_host_layout.addWidget(self.video_host_placeholder)
        lay.addWidget(self.video_host, stretch=1)

        self.roughcut_subtitle_preview_lbl = QLabel("자막 대기")
        self.roughcut_subtitle_preview_lbl.setObjectName("roughcutSubtitlePreview")
        self.roughcut_subtitle_preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.roughcut_subtitle_preview_lbl.setWordWrap(True)
        self.roughcut_subtitle_preview_lbl.setMinimumHeight(44)
        lay.addWidget(self.roughcut_subtitle_preview_lbl)

        self.roughcut_player_seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.roughcut_player_seek_slider.setRange(0, 1000)
        self.roughcut_player_seek_slider.setValue(0)
        self.roughcut_player_seek_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #243038; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 12px; margin: -5px 0; border-radius: 6px; background: #00C8FF; }"
            "QSlider::sub-page:horizontal { background: #007AFF; border-radius: 2px; }"
        )
        self.roughcut_player_seek_slider.sliderMoved.connect(self._on_roughcut_video_slider_moved)
        lay.addWidget(self.roughcut_player_seek_slider)

        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(4)
        self.btn_roughcut_video_prev = self._roughcut_video_control_button("이전", "prev")
        self.btn_roughcut_video_prev.clicked.connect(lambda: self._move_preview_row(-1, autoplay=True))
        self.btn_roughcut_video_play = self._roughcut_video_control_button(
            "재생",
            "play",
            kind="primary",
            width=_ROUGHCUT_VIDEO_PLAY_CONTROL_WIDTH,
        )
        self.btn_roughcut_video_play.clicked.connect(self._start_roughcut_video_playback)
        self.btn_roughcut_video_stop = self._roughcut_video_control_button("정지", "stop")
        self.btn_roughcut_video_stop.clicked.connect(self._stop_preview)
        self.btn_roughcut_video_next = self._roughcut_video_control_button("다음", "next")
        self.btn_roughcut_video_next.clicked.connect(lambda: self._move_preview_row(1, autoplay=True))
        control_row.addStretch(1)
        for button in (
            self.btn_roughcut_video_prev,
            self.btn_roughcut_video_play,
            self.btn_roughcut_video_stop,
            self.btn_roughcut_video_next,
        ):
            control_row.addWidget(button)
        control_row.addStretch(1)
        lay.addLayout(control_row)

        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(6)
        self.roughcut_video_time_lbl = QLabel("00:00.000 / 00:00.000")
        self.roughcut_video_time_lbl.setStyleSheet(label_style("muted", 9, bold=True))
        self.roughcut_video_style_lbl = QLabel("Noto Sans KR · 42")
        self.roughcut_video_style_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.roughcut_video_style_lbl.setStyleSheet(label_style("muted", 9, bold=True))
        info_row.addWidget(self.roughcut_video_time_lbl, stretch=1)
        info_row.addWidget(self.roughcut_video_style_lbl, stretch=1)
        lay.addLayout(info_row)
        self._apply_roughcut_video_subtitle_style()

    def _build_hidden_legacy_host(self, parent: QWidget) -> QWidget:
        host = QWidget(parent)
        host.setObjectName("roughcutLegacyHiddenHost")
        host.setFixedSize(0, 0)
        host.hide()
        return host

    def _build_candidate_preview_frame(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #10161A; border: 1px solid #2D3942; border-radius: 10px; }")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(9, 8, 9, 8)
        lay.setSpacing(6)

        title = QLabel("LLM 후보")
        title.setStyleSheet(label_style("text", 11, bold=True))
        hint = QLabel("후보는 최대 3개만 좁고 긴 세로 기둥으로 옆에 배치하고, 각 기둥 안에 roughcut 세그먼트를 위에서 아래로 넣습니다.")
        hint.setWordWrap(True)
        hint.setStyleSheet(label_style("muted", 9))
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        title_box.addWidget(title)
        title_box.addWidget(hint)
        top_row.addLayout(title_box, stretch=1)
        self.candidate_preview_filter_combo = QComboBox()
        self.candidate_preview_filter_combo.addItem("전체 후보", "all")
        self.candidate_preview_filter_combo.addItem("LLM 결과만", "llm")
        self.candidate_preview_filter_combo.setFixedHeight(30)
        self.candidate_preview_filter_combo.setMinimumWidth(108)
        self.candidate_preview_filter_combo.setStyleSheet(
            "QComboBox { background: #10161A; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: 700; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
        )
        self.candidate_preview_filter_combo.currentIndexChanged.connect(self._on_candidate_preview_filter_changed)
        top_row.addWidget(self.candidate_preview_filter_combo, stretch=0, alignment=Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top_row)

        self.candidate_preview_btn_group = QButtonGroup(frame)
        self.candidate_preview_btn_group.setExclusive(True)
        self.candidate_preview_stack = QWidget()
        self.candidate_preview_stack.setStyleSheet("background: transparent; border: none;")
        self.candidate_preview_layout = QHBoxLayout(self.candidate_preview_stack)
        self.candidate_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.candidate_preview_layout.setSpacing(6)
        self.candidate_preview_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.candidate_preview_stack.setMinimumHeight(332)
        self._candidate_preview_empty_lbl = QLabel("후보 없음")
        self._candidate_preview_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._candidate_preview_empty_lbl.setStyleSheet(label_style("muted", 10, bold=True))
        self.candidate_preview_layout.addWidget(self._candidate_preview_empty_lbl)
        lay.addWidget(self.candidate_preview_stack)
        return frame

    def _candidate_preview_button_style(self, *, selected: bool = False, is_current: bool = False) -> str:
        border = COLORS["accent"] if selected else ("#2B5A3A" if is_current else "#2D3942")
        background = "#133422" if selected else "#11181C"
        color = "#F5F7FA" if selected else "#DCE3EA"
        return (
            "QPushButton { "
            f"background: {background}; color: {color}; border: 1px solid {border}; "
            "border-radius: 10px; padding: 10px 9px; text-align: left top; font-size: 10px; font-weight: 700; }"
            "QPushButton:hover { border-color: #34C759; }"
        )

    def _candidate_preview_lines(self, candidate: dict, index: int) -> tuple[str, str]:
        name = str(candidate.get("name") or f"후보 {index}")
        current_sig = self._current_editor_signature() if hasattr(self, "_current_editor_signature") else ""
        is_current = str(candidate.get("source_signature") or "") == current_sig and bool(current_sig)
        suffix = "현재 자막" if is_current else "저장된 자막"
        origin_label = self._candidate_origin_chip_text(candidate)
        segments = list(candidate.get("segments") or [])
        segment_lines: list[str] = []
        for segment in segments[:4]:
            if not isinstance(segment, dict):
                continue
            major_id = str(segment.get("segment_id") or segment.get("major_id") or "-")
            title = str(segment.get("title") or segment.get("summary") or "세그먼트")
            segment_lines.append(f"{major_id} · {title}")
        if not segment_lines:
            segment_lines.append("세그먼트 없음")
        head = f"{name} · {origin_label} · {suffix}"
        body = "\n".join(segment_lines)
        return head, body

    def _filtered_candidate_preview_candidates(self) -> list[dict]:
        candidates = list(getattr(self, "_roughcut_candidates", []) or [])
        mode = str(getattr(self, "_candidate_preview_filter", "all") or "all")
        if mode == "llm":
            candidates = [candidate for candidate in candidates if self._candidate_origin(candidate) == "llm"]
        return candidates

    def _candidate_origin_chip_text(self, candidate: dict) -> str:
        origin = self._candidate_origin(candidate) if hasattr(self, "_candidate_origin") else "local"
        return {"llm": "실제 LLM", "local": "로컬 초안", "placeholder": "임시 상태"}.get(origin, "로컬 초안")

    def _on_candidate_preview_filter_changed(self, index: int) -> None:
        combo = getattr(self, "candidate_preview_filter_combo", None)
        if combo is None or index < 0:
            return
        self._candidate_preview_filter = str(combo.itemData(index) or "all")
        self._refresh_candidate_preview_frames()

    def _refresh_candidate_preview_frames(self) -> None:
        layout = getattr(self, "candidate_preview_layout", None)
        if layout is None:
            return
        for button in list(getattr(self, "_candidate_preview_buttons", []) or []):
            try:
                self.candidate_preview_btn_group.removeButton(button)
            except Exception:
                pass
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._candidate_preview_buttons = []
        candidates = self._filtered_candidate_preview_candidates()[:3]
        if not candidates:
            empty_message = "실제 LLM 결과 없음" if str(getattr(self, "_candidate_preview_filter", "all") or "all") == "llm" else "후보 없음"
            empty = QLabel(empty_message)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(label_style("muted", 10, bold=True))
            layout.addWidget(empty)
            self._candidate_preview_empty_lbl = empty
            return
        selected_id = str(getattr(self, "_selected_candidate_id", "") or "")
        current_sig = self._current_editor_signature() if hasattr(self, "_current_editor_signature") else ""
        for index, candidate in enumerate(candidates, start=1):
            candidate_id = str(candidate.get("candidate_id") or "")
            is_selected = (candidate_id == selected_id)
            is_current = str(candidate.get("source_signature") or "") == current_sig and bool(current_sig)

            head, body = self._candidate_preview_lines(candidate, index)

            # 1) 후보 프레임 자체가 vertical column 형태의 QPushButton
            button = QPushButton()
            button.setCheckable(True)
            button.setChecked(is_selected)
            button.setProperty("candidate_id", candidate_id)
            button.setFixedWidth(132)
            button.setMinimumHeight(320)
            button.setMaximumHeight(344)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

            # 테스트 검증용 원본 텍스트 주입 (assert 통과 보장)
            button.setText(f"{head}\n{body}")

            border = COLORS["accent"] if is_selected else ("#2B5A3A" if is_current else "#2D3942")
            background = "#133422" if is_selected else "#11181C"
            button.setStyleSheet(
                f"QPushButton {{ background: {background}; border: 1px solid {border}; border-radius: 10px; text-align: left top; color: transparent; }}"
            )
            button.clicked.connect(lambda _checked=False, cid=candidate_id: self._on_candidate_frame_clicked(cid))
            button.toggled.connect(lambda checked, cid=candidate_id: self._on_candidate_frame_toggled(cid, checked))

            # 3) 각 후보 프레임 내부에서 roughcut 세그먼트가 위에서 아래로 수직 stack
            col_lay = QVBoxLayout(button)
            col_lay.setContentsMargins(6, 6, 6, 6)
            col_lay.setSpacing(6)

            # 상단 헤더 라벨
            suffix = "현재 자막" if is_current else "저장된 자막"
            header_lbl = QLabel(f"{candidate.get('name') or f'후보 {index}'}\n{self._candidate_origin_chip_text(candidate)} · {suffix}")
            header_lbl.setWordWrap(True)
            header_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            header_lbl.setStyleSheet(
                f"color: #F5F7FA; font-size: 9px; font-weight: 900; background: {'#173D28' if is_selected else '#1A242B'}; "
                f"border: 1px solid {border}; border-radius: 6px; padding: 4px; qproperty-alignment: 'AlignCenter';"
            )
            col_lay.addWidget(header_lbl)

            # 세분화된 세그먼트 서브 카드 수직 적재
            segments = list(candidate.get("segments") or [])
            for segment in segments[:4]: # 기둥 내 수직 공간 고려 최대 4개
                if not isinstance(segment, dict):
                    continue
                major_id = str(segment.get("segment_id") or segment.get("major_id") or "-")
                title = str(segment.get("title") or segment.get("summary") or "세그먼트")

                seg_card = QFrame()
                seg_card.setObjectName("SegSubCard")
                seg_card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) # 클릭 버블링 허용
                seg_card.setStyleSheet(
                    "QFrame#SegSubCard { background: #0D1317; border: 1px solid #232E35; border-radius: 6px; }"
                )
                seg_card_lay = QVBoxLayout(seg_card)
                seg_card_lay.setContentsMargins(6, 6, 6, 6)
                seg_card_lay.setSpacing(2)

                seg_title = QLabel(f"{major_id} · {title}")
                seg_title.setWordWrap(True)
                seg_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                seg_title.setStyleSheet("color: #DCE3EA; font-size: 9px; font-weight: 700; background: transparent; border: none;")
                seg_card_lay.addWidget(seg_title)

                start = float(segment.get("start") or 0.0)
                end = float(segment.get("end") or 0.0)
                from ui.roughcut.roughcut_format import fmt_time
                seg_time = QLabel(f"{fmt_time(start)} - {fmt_time(end)}")
                seg_time.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                seg_time.setStyleSheet("color: #8A949E; font-size: 8px; background: transparent; border: none;")
                seg_card_lay.addWidget(seg_time)

                col_lay.addWidget(seg_card)

            if not segments:
                no_seg = QLabel("세그먼트 없음")
                no_seg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                no_seg.setStyleSheet("color: #8A949E; font-size: 9px; border: none;")
                no_seg.setAlignment(Qt.AlignmentFlag.AlignCenter)
                col_lay.addWidget(no_seg)

            col_lay.addStretch(1)

            self.candidate_preview_btn_group.addButton(button)
            layout.addWidget(button)
            self._candidate_preview_buttons.append(button)
        layout.addStretch(1)

    def _on_candidate_frame_clicked(self, candidate_id: str) -> None:
        candidate = self._candidate_by_id(candidate_id) if hasattr(self, "_candidate_by_id") else None
        if candidate is None:
            return
        if candidate_id == getattr(self, "_selected_candidate_id", ""):
            self._sync_candidate_state_label(candidate)
            self._refresh_candidate_preview_frames()
            return
        self._apply_candidate_payload(candidate, persist=True)

    def _on_candidate_frame_toggled(self, candidate_id: str, checked: bool) -> None:
        if not checked:
            return
        candidate = self._candidate_by_id(candidate_id) if hasattr(self, "_candidate_by_id") else None
        if candidate is None:
            return
        if candidate_id == getattr(self, "_selected_candidate_id", ""):
            self._sync_candidate_state_label(candidate)
            self._refresh_candidate_preview_frames()
            return
        self._apply_candidate_payload(candidate, persist=True)

    def attach_editor_video_frame(self, editor) -> bool:
        if editor is None:
            return False
        if self._attached_video_editor is editor and self._attached_video_frame is not None:
            return True
        self.release_editor_video_frame()
        detacher = getattr(editor, "detach_video_frame_for_external_host", None)
        if not callable(detacher):
            return False
        frame = detacher()
        if frame is None:
            return False
        self._attached_video_frame_minimum_size = frame.minimumSize()
        try:
            frame.setMinimumHeight(120)
            frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        except Exception:
            pass
        self.video_host_layout.removeWidget(self.video_host_placeholder)
        self.video_host_placeholder.hide()
        self.video_host_layout.addWidget(frame)
        self._attached_video_editor = editor
        self._attached_video_frame = frame
        try:
            frame.show()
            frame.updateGeometry()
        except Exception:
            pass
        restore_video = getattr(getattr(editor, "video_player", None), "restore_after_navigation", None)
        if callable(restore_video):
            restore_video()
        self._apply_roughcut_video_subtitle_style()
        self._refresh_roughcut_video_box()
        return True

    def release_editor_video_frame(self) -> None:
        frame = getattr(self, "_attached_video_frame", None)
        editor = getattr(self, "_attached_video_editor", None)
        if frame is None or editor is None:
            return
        try:
            self.video_host_layout.removeWidget(frame)
        except Exception:
            pass
        restorer = getattr(editor, "restore_video_frame_from_external_host", None)
        if callable(restorer):
            restorer(frame)
        else:
            try:
                frame.setParent(None)
            except Exception:
                pass
        original_minimum = getattr(self, "_attached_video_frame_minimum_size", None)
        if original_minimum is not None:
            try:
                frame.setMinimumSize(original_minimum)
            except Exception:
                pass
        if self.video_host_layout.indexOf(self.video_host_placeholder) < 0:
            self.video_host_layout.addWidget(self.video_host_placeholder)
        self.video_host_placeholder.show()
        self._attached_video_editor = None
        self._attached_video_frame = None
        self._attached_video_frame_minimum_size = None
        self._refresh_roughcut_video_box()

    def _start_roughcut_video_playback(self):
        visible_rows = self._visible_preview_rows()
        if not visible_rows:
            self._set_roughcut_video_state("대기", "#A9B0B7", "#2D3942")
            return False
        row = self._preview_row if self._preview_row in visible_rows else self.table.currentRow()
        if row not in visible_rows:
            row = visible_rows[0]
        self.table.selectRow(row)
        self._preview_row_data(row)
        self._play_preview(row, muted=False)
        return True

    def _set_roughcut_video_state(self, text: str, color: str = "#A9B0B7", border: str = "#2D3942") -> None:
        label = getattr(self, "roughcut_video_state_lbl", None)
        if label is None:
            return
        label.setText(str(text or "대기"))
        label.setStyleSheet(self._toolbar_badge_style(color, border))

    def _roughcut_preview_bounds_for_row(self, row: int) -> tuple[float, float]:
        chapter = self._chapter_for_row(row)
        if chapter is None:
            return 0.0, 0.0
        start = float(chapter.start)
        end = float(chapter.end)
        edl_segment = self._edl_for_row(row)
        if edl_segment is not None:
            start = float(edl_segment.timeline_start if edl_segment.timeline_start is not None else edl_segment.source_start)
            end = float(edl_segment.timeline_end if edl_segment.timeline_end is not None else edl_segment.source_end)
        return start, max(start, end)

    def _roughcut_subtitle_text_for_row(self, row: int) -> str:
        start, end = self._roughcut_preview_bounds_for_row(row)
        if end <= start:
            return ""
        texts: list[str] = []
        for segment in self._editor_segments():
            try:
                seg_start = float(segment.get("start", 0.0) or 0.0)
                seg_end = float(segment.get("end", 0.0) or 0.0)
            except Exception:
                continue
            if seg_end <= start or seg_start >= end:
                continue
            text = str(segment.get("text", "") or "").strip()
            if text:
                texts.append(text)
        if texts:
            return "\n".join(texts[:3])
        chapter = self._chapter_for_row(row)
        return str(getattr(chapter, "summary", "") or getattr(chapter, "title", "") or "")

    def _apply_roughcut_video_subtitle_style(self) -> None:
        if not bool(getattr(self, "_roughcut_export_style_overridden", False)):
            adopted = self._current_editor_video_subtitle_style()
            if adopted:
                style = dict(DEFAULT_ROUGHCUT_EXPORT_STYLE)
                style.update(adopted)
                self._roughcut_export_style = style
        style = dict(DEFAULT_ROUGHCUT_EXPORT_STYLE)
        style.update(getattr(self, "_roughcut_export_style", {}) or {})
        prefer_editor_style = not bool(getattr(self, "_roughcut_export_style_overridden", False)) and (
            "font" in style or "size" in style
        )
        font_family = str(
            (style.get("font") if prefer_editor_style else style.get("font_family"))
            or style.get("font_family")
            or style.get("font")
            or "Noto Sans KR"
        )
        raw_font_size = int(
            (style.get("size") if prefer_editor_style else style.get("font_size"))
            or style.get("font_size")
            or style.get("size")
            or 42
        )
        font_size = max(12, min(30, raw_font_size // 2))
        preview = getattr(self, "roughcut_subtitle_preview_lbl", None)
        if preview is not None:
            preview.setStyleSheet(
                "QLabel#roughcutSubtitlePreview { "
                "background: rgba(0, 0, 0, 190); color: #FFFFFF; "
                "border: 1px solid #2D3942; border-radius: 6px; padding: 6px 8px; "
                f"font-family: '{font_family}'; font-size: {font_size}px; font-weight: 800; "
                "}"
            )
        style_label = getattr(self, "roughcut_video_style_lbl", None)
        if style_label is not None:
            position = (
                (style.get("align") if prefer_editor_style else style.get("position"))
                or style.get("position")
                or style.get("align")
                or "bottom_center"
            )
            style_label.setText(f"{font_family} · {raw_font_size} · {position}")
        player = self._video_player()
        apply_style = getattr(player, "apply_export_subtitle_style", None)
        if callable(apply_style):
            try:
                apply_style(style)
            except Exception:
                pass

    def _current_editor_video_subtitle_style(self) -> dict:
        player = self._video_player()
        if player is None:
            return {}
        for owner in (
            getattr(player, "sub_label", None),
            getattr(player, "quick_subtitle_overlay", None),
            getattr(getattr(getattr(player, "video_widget", None), "subtitle_item", None), "_style", None),
        ):
            if isinstance(owner, dict):
                style = dict(owner)
            else:
                style = dict(getattr(owner, "_export_style", {}) or {})
                if not style:
                    style = dict(getattr(owner, "_style", {}) or {})
            if style:
                return style
        return {}

    def _refresh_roughcut_video_box(self) -> None:
        row = int(getattr(self, "_preview_row", -1) or -1)
        if row < 0:
            subtitle = "자막 대기"
            start, end = 0.0, 0.0
        else:
            subtitle = self._roughcut_subtitle_text_for_row(row) or "자막 없음"
            start, end = self._roughcut_preview_bounds_for_row(row)
        preview = getattr(self, "roughcut_subtitle_preview_lbl", None)
        if preview is not None:
            preview.setText(subtitle)
        self._update_roughcut_video_playbar(start, start=start, end=end)
        if getattr(self, "_attached_video_frame", None) is None:
            self._set_roughcut_video_state("대기", "#A9B0B7", "#2D3942")

    def _update_roughcut_video_for_row(self, row: int, *, playing: bool = False, current_sec: float | None = None) -> None:
        if row >= 0:
            self._preview_row = row
        subtitle = self._roughcut_subtitle_text_for_row(row) or "자막 없음"
        preview = getattr(self, "roughcut_subtitle_preview_lbl", None)
        if preview is not None:
            preview.setText(subtitle)
        start, end = self._roughcut_preview_bounds_for_row(row)
        self._update_roughcut_video_playbar(start if current_sec is None else current_sec, start=start, end=end)
        self._apply_roughcut_video_subtitle_style()
        self._set_roughcut_video_state("재생 중" if playing else "준비", "#9AF0B0" if playing else "#D7EBFF", "#2B5A3A" if playing else "#24527A")

    def _update_roughcut_video_playbar(self, current_sec: float, *, start: float | None = None, end: float | None = None) -> None:
        row = int(getattr(self, "_preview_row", -1) or -1)
        if start is None or end is None:
            start, end = self._roughcut_preview_bounds_for_row(row)
        duration = max(0.0, float(end or 0.0) - float(start or 0.0))
        current = max(float(start or 0.0), min(float(end or 0.0), float(current_sec or 0.0)))
        value = 0 if duration <= 0 else int(round(((current - float(start or 0.0)) / duration) * 1000.0))
        slider = getattr(self, "roughcut_player_seek_slider", None)
        if slider is not None:
            self._roughcut_updating_player_slider = True
            slider.setValue(max(0, min(1000, value)))
            self._roughcut_updating_player_slider = False
        time_label = getattr(self, "roughcut_video_time_lbl", None)
        if time_label is not None:
            time_label.setText(f"{fmt_time(max(0.0, current - float(start or 0.0)))} / {fmt_time(duration)}")

    def _on_roughcut_video_slider_moved(self, value: int) -> None:
        if bool(getattr(self, "_roughcut_updating_player_slider", False)):
            return
        row = int(getattr(self, "_preview_row", -1) or -1)
        start, end = self._roughcut_preview_bounds_for_row(row)
        if end <= start:
            return
        target = start + ((float(value) / 1000.0) * (end - start))
        player = self._video_player()
        if player is not None:
            if hasattr(player, "seek_direct"):
                player.seek_direct(target)
            elif hasattr(player, "seek"):
                player.seek(target)
            elif hasattr(player, "media_player"):
                try:
                    player.media_player.setPosition(int(target * 1000.0))
                except Exception:
                    pass
        self._update_roughcut_video_playbar(target, start=start, end=end)

    def _set_roughcut_status(self, text: str, progress: int | None = None) -> None:
        if hasattr(self, "render_status_lbl"):
            self.render_status_lbl.setText(str(text or "분석 대기"))
        if hasattr(self, "log_panel"):
            self.log_panel.set_status(str(text or "분석 대기"), progress)

    def _append_roughcut_log(self, text: str, level: str = "info") -> None:
        if hasattr(self, "log_panel"):
            self.log_panel.append_log(text, level)

    def _select_chapter_id_from_major_panel(self, chapter_id: str) -> None:
        chapter_id = str(chapter_id or "")
        if not chapter_id or chapter_id not in self._row_chapter_ids:
            return
        row = self._row_chapter_ids.index(chapter_id)
        self.table.selectRow(row)
        self._preview_row_data(row)
        self._play_preview(row, muted=False)

    def _preview_chapter_id_from_major_panel(self, chapter_id: str, hover: bool) -> None:
        chapter_id = str(chapter_id or "")
        if not chapter_id or chapter_id not in self._row_chapter_ids:
            return
        row = self._row_chapter_ids.index(chapter_id)
        if hover:
            self._prepare_thumbnail_for_row(row)
            self._play_preview(row, muted=True, hover=True, update_preview_data=False)
            return
        self._select_chapter_id_from_major_panel(chapter_id)

    def _on_major_segment_order_changed(self, ordered_segment_ids: tuple[str, ...]) -> None:
        previous_order = list(getattr(self, "_segment_order", []) or [])
        order = [str(segment_id) for segment_id in ordered_segment_ids if str(segment_id or "")]
        if not order or order == list(getattr(self, "_segment_order", []) or []):
            return
        self._segment_order = order
        self._set_reorder_summary_label(self._format_segment_reorder_summary(previous_order, order), active=True)
        current_chapter_id = ""
        if hasattr(self, "_current_selected_chapter_id"):
            current_chapter_id = self._current_selected_chapter_id()
        if self._result is None:
            self._persist_roughcut_state()
            return
        self._restored_selected_chapter_id = current_chapter_id
        self._result = self._result_with_user_edits(self._result)
        self._populate_result()
        self._persist_roughcut_state()

    def _on_major_chapter_order_changed(self, ordered_chapter_ids: tuple[str, ...]) -> None:
        previous_order = list(getattr(self, "_chapter_order", []) or [])
        order = [str(chapter_id) for chapter_id in ordered_chapter_ids if str(chapter_id or "")]
        if not order or order == list(getattr(self, "_chapter_order", []) or []):
            return
        self._chapter_order = order
        current_chapter_id = ""
        if hasattr(self, "_current_selected_chapter_id"):
            current_chapter_id = self._current_selected_chapter_id()
        self._set_reorder_summary_label(
            self._format_chapter_reorder_summary(previous_order, order, current_chapter_id),
            active=True,
        )
        if self._result is None:
            self._persist_roughcut_state()
            return
        self._restored_selected_chapter_id = current_chapter_id
        self._result = self._result_with_user_edits(self._result)
        self._populate_result()
        self._persist_roughcut_state()

    def _prepare_thumbnail_for_row(self, row: int) -> None:
        if row < 0:
            return
        chapter = self._chapter_for_row(row)
        media_path = self._media_path()
        if chapter is None or not media_path:
            return
        midpoint = (float(chapter.start) + float(chapter.end)) / 2.0
        cache_dir = default_thumbnail_cache_dir(self._project_path())
        result = ensure_thumbnail(media_path, midpoint, cache_dir=cache_dir, width=360)
        if result.status in {"created", "cached"} and result.path:
            self.preview_thumb_lbl.setText(f"썸네일\n{midpoint:.1f}s")
        elif result.status not in {"missing_source", "missing"}:
            self._append_roughcut_log(f"썸네일 fallback: {result.reason}", "warning")

    def _thumbnail_lookup_for_result(self, result) -> dict[str, str]:
        if result is None:
            return {}
        media_path = str(self._media_path() or "")
        if not media_path:
            return {}
        if media_path != self._chapter_thumbnail_lookup_media_path:
            self._chapter_thumbnail_lookup_media_path = media_path
            self._chapter_thumbnail_lookup_cache = {}
        cache_dir = default_thumbnail_cache_dir(self._project_path())
        lookup = dict(self._chapter_thumbnail_lookup_cache)
        for chapter in tuple(getattr(result, "chapters", ()) or ()):
            chapter_id = str(getattr(chapter, "chapter_id", "") or "")
            if not chapter_id or chapter_id in lookup:
                continue
            midpoint = (float(chapter.start) + float(chapter.end)) / 2.0
            thumb = ensure_thumbnail(media_path, midpoint, cache_dir=cache_dir, width=320)
            if thumb.status in {"created", "cached"} and thumb.path:
                lookup[chapter_id] = str(thumb.path)
        self._chapter_thumbnail_lookup_cache = lookup
        return dict(lookup)

    def automation_runtime_snapshot(self) -> dict:
        visible_ids = [
            chapter_id
            for row, chapter_id in enumerate(list(getattr(self, "_row_chapter_ids", []) or []))
            if not self.table.isRowHidden(row)
        ]
        current_segment_ids = self._current_segment_ids()
        candidate_ids = [
            str(candidate.get("candidate_id") or "")
            for candidate in list(getattr(self, "_roughcut_candidates", []) or [])
            if str(candidate.get("candidate_id") or "")
        ]
        material_storyboard = self._roughcut_material_preview_state_payload()
        return {
            "has_result": bool(self._result is not None),
            "selected_candidate_id": str(getattr(self, "_selected_candidate_id", "") or ""),
            "candidate_count": len(candidate_ids),
            "candidate_ids": candidate_ids,
            "selected_chapter_id": str(self._current_selected_chapter_id() or ""),
            "selected_segment_id": self._segment_id_for_chapter_id(self._current_selected_chapter_id()),
            "selected_chapter_title": str(getattr(self, "preview_title_lbl", None).text() if hasattr(self, "preview_title_lbl") else ""),
            "candidate_state": str(getattr(self, "candidate_state_lbl", None).text() if hasattr(self, "candidate_state_lbl") else ""),
            "filter_value": self._current_safety_filter_value(),
            "filter_summary": str(getattr(self, "filter_summary_lbl", None).text() if hasattr(self, "filter_summary_lbl") else ""),
            "selection_summary": str(getattr(self, "selection_summary_lbl", None).text() if hasattr(self, "selection_summary_lbl") else ""),
            "order_summary": self._current_order_summary(),
            "reorder_summary": str(getattr(self, "reorder_summary_lbl", None).text() if hasattr(self, "reorder_summary_lbl") else ""),
            "sequence_preview_active": bool(getattr(self, "_sequence_preview_active", False)),
            "visible_row_count": len(visible_ids),
            "total_row_count": len(list(getattr(self, "_row_chapter_ids", []) or [])),
            "visible_chapter_ids": visible_ids,
            "visible_segment_ids": current_segment_ids,
            "chapter_order": list(getattr(self, "_row_chapter_ids", []) or []),
            "segment_order": current_segment_ids,
            "chapter_order_state": list(getattr(self, "_chapter_order", []) or []),
            "video_host_attached": bool(getattr(self, "_attached_video_frame", None) is not None),
            "video_placeholder_visible": bool(getattr(self, "video_host_placeholder", None).isVisible() if hasattr(self, "video_host_placeholder") else False),
            "video_box_visible": bool(getattr(self, "video_box", None).isVisible() if hasattr(self, "video_box") else False),
            "video_box_status": str(getattr(getattr(self, "roughcut_video_state_lbl", None), "text", lambda: "")() or ""),
            "video_box_subtitle_text": str(getattr(getattr(self, "roughcut_subtitle_preview_lbl", None), "text", lambda: "")() or ""),
            "video_box_style": dict(getattr(self, "_roughcut_export_style", {}) or {}),
            "player_menu_visible": bool(getattr(self, "player_menu_frame", None).isVisible() if hasattr(self, "player_menu_frame") else False),
            "material_preview_storyboard": material_storyboard,
        }

    def automation_select_candidate(self, *, candidate_id: str = "", index: int | None = None) -> dict:
        candidates = list(getattr(self, "_roughcut_candidates", []) or [])
        target_id = str(candidate_id or "")
        if index is not None:
            row_value = int(index)
            if row_value < 0 or row_value >= len(candidates):
                raise ValueError("roughcut_candidate_index_out_of_range")
            target_id = str(candidates[row_value].get("candidate_id") or "")
        if not target_id:
            raise ValueError("roughcut_candidate_missing")
        candidate = self._candidate_by_id(target_id) if hasattr(self, "_candidate_by_id") else None
        if candidate is None:
            raise ValueError("roughcut_candidate_not_found")
        if target_id != str(getattr(self, "_selected_candidate_id", "") or ""):
            self._apply_candidate_payload(candidate, persist=True)
        else:
            self._sync_candidate_state_label(candidate)
            self._refresh_candidate_preview_frames()
        return self.automation_runtime_snapshot()

    def automation_select_chapter(self, *, chapter_id: str = "", row: int | None = None, autoplay: bool = False) -> dict:
        if self._result is None:
            raise ValueError("roughcut_result_missing")
        target_id = str(chapter_id or "")
        if row is not None:
            row_value = int(row)
            rows = list(getattr(self, "_row_chapter_ids", []) or [])
            if row_value < 0 or row_value >= len(rows):
                raise ValueError("roughcut_row_out_of_range")
            target_id = str(rows[row_value] or "")
        if not target_id:
            raise ValueError("roughcut_chapter_missing")
        if not self._select_chapter_id_in_table(target_id, autoplay=autoplay):
            raise ValueError("roughcut_chapter_not_found")
        return self.automation_runtime_snapshot()

    def automation_move_selected_chapter(self, delta: int) -> dict:
        if self._result is None:
            raise ValueError("roughcut_result_missing")
        order = list(getattr(self, "_row_chapter_ids", []) or [])
        if not order:
            raise ValueError("roughcut_chapter_missing")
        selected_id = str(self._current_selected_chapter_id() or "")
        if not selected_id or selected_id not in order:
            raise ValueError("roughcut_selection_missing")
        current_index = order.index(selected_id)
        target_index = max(0, min(len(order) - 1, current_index + int(delta)))
        if target_index == current_index:
            snapshot = self.automation_runtime_snapshot()
            snapshot["changed"] = False
            return snapshot
        moving_id = order.pop(current_index)
        order.insert(target_index, moving_id)
        self._on_major_chapter_order_changed(tuple(order))
        self._select_chapter_id_in_table(moving_id, autoplay=False)
        snapshot = self.automation_runtime_snapshot()
        snapshot["changed"] = True
        snapshot["selected_chapter_id"] = moving_id
        snapshot["target_index"] = target_index
        return snapshot

    def automation_move_selected_segment(self, delta: int) -> dict:
        if self._result is None:
            raise ValueError("roughcut_result_missing")
        selected_chapter_id = str(self._current_selected_chapter_id() or "")
        selected_segment_id = self._segment_id_for_chapter_id(selected_chapter_id)
        order = self._current_segment_ids()
        if not selected_segment_id or selected_segment_id not in order:
            raise ValueError("roughcut_segment_selection_missing")
        current_index = order.index(selected_segment_id)
        target_index = max(0, min(len(order) - 1, current_index + int(delta)))
        if target_index == current_index:
            snapshot = self.automation_runtime_snapshot()
            snapshot["changed"] = False
            snapshot["selected_segment_id"] = selected_segment_id
            return snapshot
        moving_id = order.pop(current_index)
        order.insert(target_index, moving_id)
        self._on_major_segment_order_changed(tuple(order))
        self._select_chapter_id_in_table(selected_chapter_id, autoplay=False)
        snapshot = self.automation_runtime_snapshot()
        snapshot["changed"] = True
        snapshot["selected_segment_id"] = moving_id
        snapshot["target_index"] = target_index
        return snapshot

    def automation_set_safety_filter(self, value: str) -> dict:
        combo = getattr(self, "safety_filter_combo", None)
        if combo is None:
            raise ValueError("roughcut_filter_unavailable")
        target = str(value or "").strip()
        index = combo.findText(target)
        if index < 0:
            raise ValueError("roughcut_filter_invalid")
        combo.setCurrentIndex(index)
        return self.automation_runtime_snapshot()

    def automation_start_preview_sequence(self) -> dict:
        if not self._start_ordered_preview_sequence():
            raise ValueError("roughcut_sequence_unavailable")
        return self.automation_runtime_snapshot()

    def _current_segment_ids(self) -> list[str]:
        result = getattr(self, "_result", None)
        if result is None:
            return []
        segment_ids: list[str] = []
        for index, segment in enumerate(tuple(getattr(result, "segments", ()) or ()), start=1):
            segment_id = str(getattr(segment, "segment_id", "") or getattr(segment, "major_id", "") or f"segment_{index:04d}")
            if segment_id:
                segment_ids.append(segment_id)
        return segment_ids

    def _segment_id_for_chapter_id(self, chapter_id: str) -> str:
        chapter_id = str(chapter_id or "")
        result = getattr(self, "_result", None)
        if not chapter_id or result is None:
            return ""
        for index, segment in enumerate(tuple(getattr(result, "segments", ()) or ()), start=1):
            segment_id = str(getattr(segment, "segment_id", "") or getattr(segment, "major_id", "") or f"segment_{index:04d}")
            for minor in tuple(getattr(segment, "minor_groups", ()) or ()):
                chapter_ids = [str(item or "") for item in tuple(getattr(minor, "chapter_ids", ()) or ()) if str(item or "")]
                if chapter_id in chapter_ids:
                    return segment_id
        return ""

    def _save_roughcut_export_style(self, payload: dict) -> None:
        self._roughcut_export_style = dict(DEFAULT_ROUGHCUT_EXPORT_STYLE)
        self._roughcut_export_style.update(payload or {})
        self._roughcut_export_style_overridden = True
        self._apply_roughcut_video_subtitle_style()
        self._append_roughcut_log("러프컷 export style을 프로젝트 상태에 저장했습니다.", "done")
        self._persist_roughcut_state()

    def _refresh_title_suggestions(self) -> None:
        if self._result is None:
            self._set_roughcut_status("분석 대기")
            return
        self._set_roughcut_status("제목 생성", 70)
        self._append_roughcut_log("러프컷 제목 후보를 새로 구성합니다.")
        suggestions = build_title_suggestions(
            self._result,
            settings=self._roughcut_settings_payload(),
        )
        self._result = replace(self._result, title_suggestions=tuple(suggestions))
        self.title_panel.set_suggestions(suggestions)
        self._persist_roughcut_state()
        self._set_roughcut_status("분석 완료", 100)

    def _build_bottom_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._build_control_panel())
        return panel

    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("QWidget { background: transparent; border: none; }")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.selection_status_section = self._build_collapsible_section_group(
            "현재 상태",
            "정렬 상태, 필터, 선택 요약은 필요할 때만 펼칩니다.",
            checked=False,
        )
        self.selection_status_section.content_layout.addWidget(self._build_toolbar_row())
        self.selection_status_group = self.selection_status_section.frame
        lay.addWidget(self.selection_status_section.frame)

        self.selection_edit_group = self._build_section_group(
            "선택 카드 편집",
            "미리보기 재생, 구간 이동, 컷 조정과 수정 상태를 다루는 구역입니다.",
        )
        selection_edit_layout = self.selection_edit_group.layout()
        selection_edit_layout.addWidget(self._build_preview_row())
        selection_edit_layout.addWidget(self._build_detail_panel())
        lay.addWidget(self.selection_edit_group)
        return panel

    def _build_player_menu_frame(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #10161A; border: 1px solid #2D3942; border-radius: 8px; }")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(9, 8, 9, 8)
        lay.setSpacing(6)

        title = QLabel("핵심 메뉴")
        title.setStyleSheet(label_style("text", 11, bold=True))
        hint = QLabel("상시 노출은 재생과 선택 카드 편집에 두고, 나머지 작업은 접어 둡니다.")
        hint.setWordWrap(True)
        hint.setStyleSheet(label_style("muted", 9))
        lay.addWidget(title)
        lay.addWidget(hint)

        self.player_candidate_state_lbl = self._toolbar_badge("후보 없음")
        self.player_candidate_state_lbl.hide()
        self.player_filter_lbl = self._toolbar_badge("표시 0 / 전체 0")
        self.player_filter_lbl.hide()
        self.player_order_lbl = self._toolbar_badge("순서 대기")
        self.player_order_lbl.setMinimumWidth(126)
        self.player_order_lbl.hide()
        self.player_selection_lbl = self._toolbar_badge("선택 대기")
        self.player_selection_lbl.setMinimumWidth(116)
        self.player_selection_lbl.hide()
        self.player_reorder_lbl = self._toolbar_badge("재정렬 없음")
        self.player_reorder_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.player_reorder_lbl.setMinimumWidth(180)
        self.player_reorder_lbl.hide()

        summary_box = QFrame()
        summary_box.setStyleSheet("QFrame { background: #0C1216; border: 1px solid #243038; border-radius: 7px; }")
        summary_lay = QVBoxLayout(summary_box)
        summary_lay.setContentsMargins(8, 6, 8, 6)
        summary_lay.setSpacing(3)
        self.player_context_summary_lbl = QLabel("후보 없음 · 표시 0 / 전체 0")
        self.player_context_summary_lbl.setWordWrap(True)
        self.player_context_summary_lbl.setStyleSheet(label_style("muted", 9, bold=True))
        self.player_focus_summary_lbl = QLabel("순서 대기 · 선택 대기")
        self.player_focus_summary_lbl.setWordWrap(True)
        self.player_focus_summary_lbl.setStyleSheet(label_style("text", 10, bold=True))
        self.player_reorder_summary_visible_lbl = QLabel("재정렬 없음")
        self.player_reorder_summary_visible_lbl.setWordWrap(True)
        self.player_reorder_summary_visible_lbl.setStyleSheet(label_style("muted", 9))
        summary_lay.addWidget(self.player_context_summary_lbl)
        summary_lay.addWidget(self.player_focus_summary_lbl)
        summary_lay.addWidget(self.player_reorder_summary_visible_lbl)
        lay.addWidget(summary_box)

        self.player_core_section = self._build_collapsible_section_group(
            "AI 작업",
            "분석, 검증, 렌더는 자주 누르지 않으므로 접어 둡니다.",
            checked=False,
        )
        self.player_core_group = self.player_core_section.frame
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        self.btn_side_refresh = self._panel_button("분석", "refresh", kind="primary")
        self.btn_side_refresh.clicked.connect(self.run_main_action)
        self.btn_side_refresh.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_verify = self._panel_button("검증", "check")
        self.btn_side_verify.clicked.connect(self._dry_run_render_plan)
        self.btn_side_verify.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_render = self._panel_button("렌더", "play", kind="primary")
        self.btn_side_render.clicked.connect(self._execute_render_plan)
        self.btn_side_render.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for button in (self.btn_side_refresh, self.btn_side_verify, self.btn_side_render):
            action_row.addWidget(button)
        self.player_core_section.content_layout.addLayout(action_row)
        lay.addWidget(self.player_core_section.frame)

        self.player_media_group = self._build_section_group("재생", "선택 구간 이동과 순서 재생만 상시로 둡니다.")
        playback_row = QHBoxLayout()
        playback_row.setContentsMargins(0, 0, 0, 0)
        playback_row.setSpacing(6)
        self.btn_side_prev = self._panel_button("이전", "prev")
        self.btn_side_prev.clicked.connect(lambda: self._move_preview_row(-1, autoplay=True))
        self.btn_side_prev.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_play = self._panel_button("순서 재생", "play", kind="primary")
        self.btn_side_play.clicked.connect(self._start_ordered_preview_sequence)
        self.btn_side_play.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_next = self._panel_button("다음", "next")
        self.btn_side_next.clicked.connect(lambda: self._move_preview_row(1, autoplay=True))
        self.btn_side_next.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for button in (self.btn_side_prev, self.btn_side_play, self.btn_side_next):
            playback_row.addWidget(button)
        self.player_media_group.layout().addLayout(playback_row)
        lay.addWidget(self.player_media_group)

        self.player_filter_group = self._build_collapsible_section_group(
            "후보 / 필터",
            "후보 기준과 safety filter는 자주 바뀌지 않아서 접을 수 있게 둡니다.",
            checked=False,
        )
        candidate_info = QLabel("현재 후보 기준과 safety filter를 여기서 조정합니다.")
        candidate_info.setWordWrap(True)
        candidate_info.setStyleSheet(label_style("muted", 9))
        self.player_filter_group.content_layout.addWidget(candidate_info)
        candidate_badge_row = QHBoxLayout()
        candidate_badge_row.setContentsMargins(0, 0, 0, 0)
        candidate_badge_row.setSpacing(6)
        self.player_candidate_panel_lbl = QLabel("후보 없음")
        self.player_candidate_panel_lbl.setStyleSheet(self._toolbar_badge_style("#A9B0B7", "#2D3942"))
        self.player_candidate_panel_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_filter_panel_lbl = QLabel("표시 0 / 전체 0")
        self.player_filter_panel_lbl.setStyleSheet(self._toolbar_badge_style("#A9B0B7", "#2D3942"))
        self.player_filter_panel_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        candidate_badge_row.addWidget(self.player_candidate_panel_lbl, stretch=1)
        candidate_badge_row.addWidget(self.player_filter_panel_lbl, stretch=1)
        self.player_filter_group.content_layout.addLayout(candidate_badge_row)
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)
        filter_label = QLabel("Safety filter")
        filter_label.setStyleSheet(label_style("muted", 9, bold=True))
        filter_row.addWidget(filter_label)
        filter_row.addWidget(self.safety_filter_combo, stretch=1)
        self.player_filter_group.content_layout.addLayout(filter_row)
        lay.addWidget(self.player_filter_group.frame)

        self.player_export_section = self._build_collapsible_section_group(
            "내보내기",
            "SRT, EDL, 가이드는 마지막 단계라 접어 둡니다.",
            checked=False,
        )
        self.player_export_group = self.player_export_section.frame
        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 0, 0, 0)
        export_row.setSpacing(6)
        self.btn_side_save_srt = self._panel_button("SRT", "subtitle")
        self.btn_side_save_srt.clicked.connect(self._save_srt)
        self.btn_side_save_edl = self._panel_button("EDL", "file")
        self.btn_side_save_edl.clicked.connect(self._save_edl)
        self.btn_side_save_guide = self._panel_button("가이드", "help")
        self.btn_side_save_guide.clicked.connect(self._save_guide)
        self.export_menu_btn = QToolButton()
        self.export_menu_btn.setText("내보내기")
        self.export_menu_btn.setIcon(line_icon("file", "#FFFFFF", 16))
        self.export_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.export_menu_btn.setStyleSheet(button_style("toolbar", font_size="11px", padding="6px 10px"))
        self.export_menu_btn.setMinimumHeight(32)
        export_menu = self.export_menu_btn.menu()
        if export_menu is None:
            from PyQt6.QtWidgets import QMenu
            export_menu = QMenu(self.export_menu_btn)
            self.export_menu_btn.setMenu(export_menu)
        export_menu.clear()
        for label, handler in (("SRT 저장", self._save_srt), ("EDL 저장", self._save_edl), ("가이드 저장", self._save_guide)):
            action = QAction(label, self.export_menu_btn)
            action.triggered.connect(handler)
            export_menu.addAction(action)
        export_row.addWidget(self.export_menu_btn, stretch=1)
        self.player_export_section.content_layout.addLayout(export_row)
        lay.addWidget(self.player_export_section.frame)

        # Keep legacy attribute names wired for export/runtime helpers.
        self.btn_render_dry_run = self.btn_side_verify
        self.btn_render_execute = self.btn_side_render
        self.btn_refresh = self.btn_side_refresh
        self.btn_render_retry = QPushButton("복구")
        self.btn_render_retry.setVisible(False)
        self.btn_render_retry.setEnabled(False)
        self._refresh_player_runtime_summary()
        return frame

    def _build_section_group(self, title: str, hint: str = "") -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #0C1216; border: 1px solid #243038; border-radius: 7px; }")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 7, 8, 7)
        lay.setSpacing(5)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(label_style("text", 10, bold=True))
        lay.addWidget(title_lbl)
        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet(label_style("muted", 9))
            lay.addWidget(hint_lbl)
        return frame

    def _build_collapsible_section_group(self, title: str, hint: str = "", *, checked: bool = False):
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #0C1216; border: 1px solid #243038; border-radius: 7px; }")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 7, 8, 7)
        outer.setSpacing(5)

        toggle = QPushButton(title)
        toggle.setCheckable(True)
        toggle.setChecked(bool(checked))
        toggle.setStyleSheet(button_style("toolbar", font_size="10px", padding="5px 8px"))
        outer.addWidget(toggle)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(5)
        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet(label_style("muted", 9))
            content_lay.addWidget(hint_lbl)
        content.setVisible(bool(checked))
        toggle.toggled.connect(content.setVisible)
        outer.addWidget(content)
        return SimpleNamespace(frame=frame, toggle=toggle, content=content, content_layout=content_lay)

    def _build_toolbar_row(self) -> QWidget:
        top = QWidget()
        top.setStyleSheet("background: transparent; border: none;")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        self.title_lbl = QLabel("러프컷")
        self.title_lbl.setStyleSheet(label_style("text", 15, bold=True))
        self.source_lbl = QLabel("대기 중")
        self.source_lbl.setStyleSheet(label_style("muted", 10))
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.source_lbl)
        row1.addLayout(title_box, stretch=1)

        self.candidate_combo = QComboBox()
        self.candidate_combo.setMinimumWidth(170)
        self.candidate_combo.setFixedHeight(32)
        self.candidate_combo.setToolTip("프로젝트에 저장된 러프컷 후보")
        self.candidate_combo.setStyleSheet(
            "QComboBox { background: #10161A; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: 700; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
        )
        self.candidate_combo.currentIndexChanged.connect(self._on_candidate_combo_changed)
        self.candidate_combo.hide()
        self.candidate_state_lbl = self._toolbar_badge("후보 없음")
        row1.addWidget(self.candidate_state_lbl)

        self.render_status_lbl = QLabel("렌더 대기")
        self.render_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.render_status_lbl.setMinimumWidth(70)
        self.render_status_lbl.setStyleSheet(
            "QLabel { background: #10161A; color: #A9B0B7; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 6px 8px; font-size: 10px; font-weight: 700; }"
        )
        row1.addWidget(self.render_status_lbl)
        top_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)
        self.metric_labels = []
        for label in ("챕터", "EDL", "하이라이트", "검토", "출력"):
            row2.addWidget(self._metric_chip(label))

        self.filter_summary_lbl = self._toolbar_badge("표시 0 / 전체 0")
        row2.addWidget(self.filter_summary_lbl)
        self.selection_summary_lbl = self._toolbar_badge("선택 대기")
        self.selection_summary_lbl.setMinimumWidth(150)
        row2.addWidget(self.selection_summary_lbl, stretch=1)
        top_lay.addLayout(row2)
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(6)
        self.reorder_summary_lbl = self._toolbar_badge("재정렬 없음")
        self.reorder_summary_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row3.addWidget(self.reorder_summary_lbl, stretch=1)
        top_lay.addLayout(row3)

        return top

    def _build_safety_filter_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.addItems(["전체", "ideal", "acceptable", "risky"])
        combo.setFixedHeight(32)
        combo.setMinimumWidth(104)
        combo.setStyleSheet(
            "QComboBox { background: #10161A; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: 700; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
        )
        combo.currentTextChanged.connect(self._apply_safety_filter)
        return combo

    def _metric_chip(self, title: str) -> QWidget:
        box = QFrame()
        box.setStyleSheet(
            "QFrame { background: #151C20; border: 1px solid #2D3942; border-radius: 6px; }"
        )
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        box.setMinimumWidth(86)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(5)
        name = QLabel(title)
        name.setStyleSheet(label_style("muted", 9, bold=True))
        value = QLabel("-")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value.setStyleSheet(label_style("text", 11, bold=True))
        lay.addWidget(name)
        lay.addWidget(value, stretch=1)
        self.metric_labels.append(value)
        return box

    def _toolbar_badge(self, text: str) -> QLabel:
        label = QLabel(str(text or ""))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(84)
        label.setStyleSheet(self._toolbar_badge_style("#A9B0B7", "#2D3942"))
        return label

    def _toolbar_badge_style(self, color: str, border: str) -> str:
        return (
            "QLabel { background: #10161A; "
            f"color: {color}; border: 1px solid {border}; "
            "border-radius: 6px; padding: 6px 8px; font-size: 10px; font-weight: 700; }"
        )

    def _set_candidate_state_label(self, mode: str) -> None:
        mapping = {
            "current": ("현재 자막 기준", "#9AF0B0", "#2B5A3A"),
            "stale": ("저장된 자막 기준", "#FFD38A", "#6E5330"),
            "none": ("후보 없음", "#A9B0B7", "#2D3942"),
        }
        text, color, border = mapping.get(mode, mapping["none"])
        for label_name in ("candidate_state_lbl", "player_candidate_state_lbl"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(text)
            label.setStyleSheet(self._toolbar_badge_style(color, border))
        panel_label = getattr(self, "player_candidate_panel_lbl", None)
        if panel_label is not None:
            panel_label.setText(text)
            panel_label.setStyleSheet(self._toolbar_badge_style(color, border))
        self._refresh_player_runtime_summary()

    def _set_filter_summary_label(self, visible: int, total: int) -> None:
        text = f"표시 {max(0, int(visible))} / 전체 {max(0, int(total))}"
        for label_name in ("filter_summary_lbl", "player_filter_lbl"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(text)
        panel_label = getattr(self, "player_filter_panel_lbl", None)
        if panel_label is not None:
            panel_label.setText(text)
        self._refresh_player_runtime_summary()

    def _set_selection_summary_label(self, text: str, active: bool = False) -> None:
        color = "#D7EBFF" if active else "#A9B0B7"
        border = "#24527A" if active else "#2D3942"
        for label_name in ("selection_summary_lbl", "player_selection_lbl"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(str(text or "선택 대기"))
            label.setStyleSheet(self._toolbar_badge_style(color, border))
        self._refresh_player_runtime_summary()

    def _set_player_order_summary_label(self, text: str) -> None:
        label = getattr(self, "player_order_lbl", None)
        if label is None:
            return
        label.setText(str(text or "순서 대기"))
        self._refresh_player_runtime_summary()

    def _set_reorder_summary_label(self, text: str, active: bool = False) -> None:
        message = str(text or "재정렬 없음")
        self._recent_reorder_summary = message
        color = "#D9FFE3" if active else "#A9B0B7"
        border = "#2B5A3A" if active else "#2D3942"
        for label_name in ("reorder_summary_lbl", "player_reorder_lbl"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(message)
            label.setStyleSheet(self._toolbar_badge_style(color, border))
        self._refresh_player_runtime_summary()

    def _refresh_player_runtime_summary(self) -> None:
        context_label = getattr(self, "player_context_summary_lbl", None)
        focus_label = getattr(self, "player_focus_summary_lbl", None)
        reorder_label = getattr(self, "player_reorder_summary_visible_lbl", None)
        candidate = str(getattr(getattr(self, "player_candidate_state_lbl", None), "text", lambda: "")() or "후보 없음")
        filter_text = str(getattr(getattr(self, "player_filter_lbl", None), "text", lambda: "")() or "표시 0 / 전체 0")
        order_text = str(getattr(getattr(self, "player_order_lbl", None), "text", lambda: "")() or "순서 대기")
        selection_text = str(getattr(getattr(self, "player_selection_lbl", None), "text", lambda: "")() or "선택 대기")
        reorder_text = str(getattr(getattr(self, "player_reorder_lbl", None), "text", lambda: "")() or "재정렬 없음")
        if context_label is not None:
            context_label.setText(f"{candidate} · {filter_text}")
        if focus_label is not None:
            focus_label.setText(f"{order_text} · {selection_text}")
        if reorder_label is not None:
            reorder_label.setText(reorder_text)

    def _format_segment_reorder_summary(self, previous_order: list[str], current_order: list[str]) -> str:
        order = [str(segment_id or "") for segment_id in list(current_order or []) if str(segment_id or "")]
        if not order:
            return "재정렬 없음"
        if order == [str(segment_id or "") for segment_id in list(previous_order or []) if str(segment_id or "")]:
            return self._recent_reorder_summary or "재정렬 없음"
        return f"카드 재정렬 · {' > '.join(order[:4])}"

    def _format_chapter_reorder_summary(self, previous_order: list[str], current_order: list[str], selected_chapter_id: str) -> str:
        order = [str(chapter_id or "") for chapter_id in list(current_order or []) if str(chapter_id or "")]
        if not order:
            return "재정렬 없음"
        previous = [str(chapter_id or "") for chapter_id in list(previous_order or []) if str(chapter_id or "")]
        if order == previous:
            return self._recent_reorder_summary or "재정렬 없음"
        selected_id = str(selected_chapter_id or "")
        focus_id = selected_id if selected_id in order else order[0]
        focus_index = order.index(focus_id) if focus_id in order else 0
        start = max(0, focus_index - 1)
        end = min(len(order), start + 4)
        window = order[start:end]
        return f"챕터 재정렬 · {' > '.join(window)}"

    def _current_order_summary(self) -> str:
        order = list(getattr(self, "_segment_order", []) or []) or self._current_segment_ids()
        selected_segment_id = self._segment_id_for_chapter_id(self._current_selected_chapter_id())
        if not order or not selected_segment_id or selected_segment_id not in order:
            return "순서 대기"
        current_index = order.index(selected_segment_id) + 1
        return f"카드 {current_index}/{len(order)} · {' > '.join(order[:5])}"

    def _build_preview_row(self) -> QWidget:
        preview = QWidget()
        preview.setStyleSheet("background: transparent; border: none;")
        preview_lay = QVBoxLayout(preview)
        preview_lay.setContentsMargins(0, 0, 0, 0)
        preview_lay.setSpacing(6)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(8)

        thumb = QFrame()
        thumb.setFixedSize(78, 44)
        thumb.setStyleSheet("QFrame { background: #0A0F12; border: 1px solid #2D3942; border-radius: 6px; }")
        thumb_lay = QVBoxLayout(thumb)
        thumb_lay.setContentsMargins(4, 4, 4, 4)
        self.preview_thumb_lbl = QLabel("대표\n프레임")
        self.preview_thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_thumb_lbl.setStyleSheet(label_style("muted", 10, bold=True))
        thumb_lay.addWidget(self.preview_thumb_lbl)
        content_row.addWidget(thumb)

        preview_text_box = QVBoxLayout()
        preview_text_box.setContentsMargins(0, 0, 0, 0)
        preview_text_box.setSpacing(2)
        self.preview_title_lbl = QLabel("세그먼트 선택 대기")
        self.preview_title_lbl.setStyleSheet(label_style("text", 12, bold=True))
        self.preview_time_lbl = QLabel("-")
        self.preview_time_lbl.setStyleSheet(label_style("muted", 10))
        self.preview_summary_lbl = QLabel("러프컷 행을 선택하면 해당 구간만 재생할 수 있습니다.")
        self.preview_summary_lbl.setStyleSheet(label_style("muted", 10))
        self.preview_summary_lbl.setWordWrap(True)
        preview_text_box.addWidget(self.preview_title_lbl)
        preview_text_box.addWidget(self.preview_time_lbl)
        preview_text_box.addWidget(self.preview_summary_lbl)
        content_row.addLayout(preview_text_box, stretch=2)

        detail_box = QVBoxLayout()
        detail_box.setContentsMargins(0, 0, 0, 0)
        detail_box.setSpacing(3)
        detail_row = QHBoxLayout()
        detail_row.setContentsMargins(0, 0, 0, 0)
        detail_row.setSpacing(4)
        self.preview_action_lbl = self._detail_badge("판단", "-")
        self.preview_safety_lbl = self._detail_badge("안전", "-")
        self.preview_trim_lbl = self._detail_badge("Trim", "-")
        self.preview_role_lbl = self._detail_badge("Role", "-")
        self.preview_source_lbl = self._detail_badge("Clip", "-")
        for item in (
            self.preview_action_lbl,
            self.preview_safety_lbl,
            self.preview_trim_lbl,
            self.preview_role_lbl,
            self.preview_source_lbl,
        ):
            detail_row.addWidget(item)
        detail_box.addLayout(detail_row)
        self.preview_reason_lbl = QLabel("컷 근거 대기")
        self.preview_reason_lbl.setWordWrap(True)
        self.preview_reason_lbl.setStyleSheet(label_style("muted", 10))
        detail_box.addWidget(self.preview_reason_lbl)
        content_row.addLayout(detail_box, stretch=2)

        preview_lay.addLayout(content_row)

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(6)

        self.btn_prev_candidate = self._panel_button("이전", "prev")
        self.btn_prev_candidate.clicked.connect(lambda: self._move_preview_row(-1, autoplay=True))
        controls_row.addWidget(self.btn_prev_candidate)

        self.btn_next_candidate = self._panel_button("다음", "next")
        self.btn_next_candidate.clicked.connect(lambda: self._move_preview_row(1, autoplay=True))
        controls_row.addWidget(self.btn_next_candidate)

        self.btn_preview_loop = self._panel_button("반복", "refresh")
        self.btn_preview_loop.setCheckable(True)
        self.btn_preview_loop.toggled.connect(self._set_preview_loop_enabled)
        self.btn_preview_loop.setStyleSheet(
            button_style("toolbar", font_size="11px", padding="6px 9px")
            + " QPushButton:checked { background: #1F3A56; border: 1px solid #007AFF; color: #FFFFFF; }"
        )
        controls_row.addWidget(self.btn_preview_loop)

        self.btn_preview_play = self._panel_button("구간 재생", "play", kind="primary")
        self.btn_preview_play.clicked.connect(lambda: self._play_preview(self._preview_row, muted=False))
        controls_row.addWidget(self.btn_preview_play, stretch=1)
        self.btn_preview_stop = self._panel_button("정지", "stop")
        self.btn_preview_stop.clicked.connect(self._stop_preview)
        controls_row.addWidget(self.btn_preview_stop)
        preview_lay.addLayout(controls_row)
        return preview

    def _panel_button(self, text: str, icon_name: str, *, kind: str = "toolbar") -> QPushButton:
        btn = QPushButton(text)
        icon_color = "#FFFFFF" if kind == "primary" else COLORS["muted"]
        btn.setIcon(line_icon(icon_name, icon_color, 16))
        btn.setStyleSheet(button_style(kind, font_size="11px", padding="6px 9px"))
        btn.setMinimumHeight(32)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return btn

    def _roughcut_video_control_button(
        self,
        text: str,
        icon_name: str,
        *,
        kind: str = "toolbar",
        width: int = _ROUGHCUT_VIDEO_CONTROL_WIDTH,
    ) -> QPushButton:
        btn = self._panel_button(text, icon_name, kind=kind)
        btn.setText("")
        btn.setToolTip(text)
        btn.setAccessibleName(text)
        icon_color = "#FFFFFF" if kind == "primary" else COLORS["muted"]
        btn.setIcon(line_icon(icon_name, icon_color, 11))
        btn.setIconSize(QSize(11, 11))
        if kind == "primary":
            btn.setStyleSheet(
                "QPushButton { "
                f"background: {COLORS['primary']}; color: #FFFFFF; border: none; "
                "border-radius: 6px; padding: 0 5px; font-size: 10px; font-weight: 700; "
                f"min-height: {_ROUGHCUT_VIDEO_CONTROL_HEIGHT}px; max-height: {_ROUGHCUT_VIDEO_CONTROL_HEIGHT}px; "
                f"min-width: {int(width)}px; max-width: {int(width)}px; "
                "} "
                f"QPushButton:hover {{ background: {COLORS['primary_hover']}; }} "
                "QPushButton:pressed { background: #0057B8; border: 1px solid #74A9FF; padding-top: 1px; }"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { "
                f"background: {COLORS['control']}; color: {COLORS['text']}; "
                f"border: 1px solid {COLORS['separator']}; "
                "border-radius: 6px; padding: 0 5px; font-size: 10px; "
                f"min-height: {_ROUGHCUT_VIDEO_CONTROL_HEIGHT}px; max-height: {_ROUGHCUT_VIDEO_CONTROL_HEIGHT}px; "
                f"min-width: {int(width)}px; max-width: {int(width)}px; "
                "} "
                f"QPushButton:hover {{ background: {COLORS['control_hover']}; }} "
                f"QPushButton:pressed {{ background: #182026; border-color: {COLORS['primary']}; padding-top: 1px; }}"
            )
        btn.setFixedSize(int(width), _ROUGHCUT_VIDEO_CONTROL_HEIGHT)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return btn

    def _detail_badge(self, title: str, value: str) -> QLabel:
        label = QLabel(f"{title}: {value}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(82)
        label.setStyleSheet(
            "QLabel { background: #10161A; color: #DCE3EA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 4px 6px; font-size: 10px; font-weight: 700; }"
        )
        return label

    def _set_preview_loop_enabled(self, enabled: bool) -> None:
        self._preview_loop_enabled = bool(enabled)

    def _visible_preview_rows(self) -> list[int]:
        if not hasattr(self, "table"):
            return []
        return [row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]

    def _move_preview_row(self, delta: int, autoplay: bool = False) -> None:
        visible_rows = self._visible_preview_rows()
        if not visible_rows:
            return
        row = self._preview_row if self._preview_row >= 0 else self.table.currentRow()
        if row not in visible_rows:
            row = visible_rows[0]
        else:
            idx = visible_rows.index(row)
            idx = max(0, min(len(visible_rows) - 1, idx + int(delta)))
            row = visible_rows[idx]
        self.table.selectRow(row)
        self._preview_row_data(row)
        if autoplay:
            self._play_preview(row, muted=False)

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(TABLE_COLUMNS))
        table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        table.setMouseTracking(True)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)
        table.setStyleSheet(
            f"QTableWidget {{ background: {COLORS['sidebar']}; color: {COLORS['text']}; border: 1px solid {COLORS['separator']}; "
            f"gridline-color: {COLORS['separator']}; font-size: 11px; alternate-background-color: {COLORS['surface']}; }} "
            f"QHeaderView::section {{ background: {COLORS['surface_alt']}; color: {COLORS['muted']}; border: 1px solid {COLORS['separator']}; "
            "padding: 6px; font-weight: bold; } "
            f"QTableWidget::item {{ border-bottom: 1px solid {COLORS['separator']}; padding: 4px; }} "
            "QTableWidget::item:selected { background: #1F3A56; color: #FFFFFF; }"
        )
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStretchLastSection(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setColumnWidth(0, 122)
        table.setColumnWidth(1, 88)
        table.setColumnWidth(3, 170)
        table.setColumnWidth(4, 128)
        table.setColumnWidth(8, 116)
        table.itemChanged.connect(self._on_table_item_changed)
        table.itemEntered.connect(self._on_table_item_entered)
        table.cellClicked.connect(self._on_table_cell_clicked)
        table.itemSelectionChanged.connect(self._on_table_selection_changed)
        return table
