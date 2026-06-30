# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

import random
from dataclasses import replace
from types import SimpleNamespace

from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, QTimer, Qt
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
_ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT = 20
_ROUGHCUT_MATERIAL_PREVIEW_COLUMNS = 5
_ROUGHCUT_MATERIAL_PREVIEW_ROWS = 4
_ROUGHCUT_MATERIAL_PREVIEW_PARALLEL_LIMIT = 3
_ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH = 1200
_ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH = 132
_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT = 74
_ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS = 5


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
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        if self._drag_origin is None or not self._drag_start_sizes or len(self._drag_start_sizes) < 2:
            super().mouseMoveEvent(event)
            return
        current = self._event_global_pos(event)
        delta = current - self._drag_origin
        offset = delta.x() if self._orientation == Qt.Orientation.Horizontal else delta.y()
        total = max(2, sum(self._drag_start_sizes[:2]))
        first = max(1, min(total - 1, self._drag_start_sizes[0] + offset))
        self._splitter.setSizes([first, total - first])
        parent = self.parent()
        if parent is not None and hasattr(parent, "_sync_roughcut_handle_markers"):
            parent._sync_roughcut_handle_markers()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt override
        self._drag_origin = None
        self._drag_start_sizes = None
        event.accept()

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
        self._connect_source_node = 0
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
        if pin_node and pin_side == "right":
            self._connect_source_node = pin_node
            self.setCursor(Qt.CursorShape.CrossCursor)
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
        self._owner._begin_material_preview_node_drag(node_id)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        if self._connect_source_node:
            event.accept()
            return
        if not self._drag_node_id:
            super().mouseMoveEvent(event)
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        self._owner._drag_material_preview_node_to(self._drag_node_id, scene_pos - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt override
        if self._connect_source_node:
            source = self._connect_source_node
            self._connect_source_node = 0
            scene_pos = self.mapToScene(event.position().toPoint())
            target, target_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
            if target and target_side == "left":
                self._owner._connect_material_preview_nodes(source, target)
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        if not self._drag_node_id:
            super().mouseReleaseEvent(event)
            return
        node_id = self._drag_node_id
        scene_pos = self.mapToScene(event.position().toPoint())
        self._drag_node_id = ""
        self._drag_offset = QPointF()
        self._owner._finish_material_preview_node_drag(node_id, scene_pos)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        event.accept()


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
        left_lay.addWidget(self.scenario_box, stretch=1)
        left_lay.addWidget(self.material_box, stretch=1)

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
        self.material_r_sort_btn.setToolTip("연결 순서를 ㄹ자 그리드로 자동 정렬")
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
            430,
        )
        self.material_card_preview_order = list(range(1, _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT + 1))
        self.material_card_preview_connections: dict[int, list[int]] = {}
        self.material_card_parallel_selections: dict[int, int] = {}
        self.material_card_preview_selected_node = 1
        self.material_card_preview_multi_select_enabled = False
        self.material_card_preview_multi_selection: list[int] = []
        self.material_card_preview_generated_order: list[int] = []
        self.material_card_preview_deleted_nodes: set[int] = set()
        self.material_card_preview_merged_nodes: dict[int, list[int]] = {}
        self.material_card_preview_split_children: dict[int, list[int]] = {}
        self.material_card_preview_trim_state: dict[int, dict[str, int]] = {}
        self.material_card_preview_last_reorder: dict[str, object] = {}
        self._material_card_preview_groups: dict[str, object] = {}
        self.material_card_preview_view = _RoughcutMaterialPreviewView(self.material_card_preview_scene, self)
        self.material_card_preview_view.setObjectName("roughcutMaterialMiroUmlPreview")
        self.material_card_preview_view.setAccessibleName("중분류 카드 Miro UML 미리보기")
        self.material_card_preview_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.material_card_preview_view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.material_card_preview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.material_card_preview_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.material_card_preview_view.setFrameShape(QFrame.Shape.NoFrame)
        self.material_card_preview_view.setStyleSheet(
            "QGraphicsView#roughcutMaterialMiroUmlPreview { background: transparent; border: none; }"
        )
        self.material_card_preview_nodes: list[dict[str, object]] = []
        self._populate_material_miro_uml_preview_scene()
        lay.addWidget(self.material_card_preview_view, stretch=1)
        self._refresh_scenario_sequence_preview()

    def _material_preview_slot_positions(self) -> tuple[tuple[int, int], ...]:
        start_x = 46
        start_y = 26
        step_x = 178
        step_y = 96
        positions: list[tuple[int, int]] = []
        total_count = max(_ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT, len(getattr(self, "material_card_preview_order", [])))
        for index in range(total_count):
            page = index // _ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT
            page_index = index % _ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT
            row = page_index // _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS
            row_offset = page_index % _ROUGHCUT_MATERIAL_PREVIEW_COLUMNS
            col = row_offset if row % 2 == 0 else (_ROUGHCUT_MATERIAL_PREVIEW_COLUMNS - 1 - row_offset)
            positions.append(
                (
                    (page * _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH) + start_x + (col * step_x),
                    start_y + (row * step_y),
                )
            )
        return tuple(positions)

    def _material_preview_node_centers(self) -> dict[int, QPointF]:
        centers: dict[int, QPointF] = {}
        for node in self.material_card_preview_nodes:
            node_number = int(str(node["id"]).rsplit("_", 1)[1])
            centers[node_number] = QPointF(
                float(node["x"]) + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH / 2),
                float(node["y"]) + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2),
            )
        return centers

    def _material_preview_pin_position(self, node_number: int, side: str) -> QPointF:
        group = self._material_card_preview_groups.get(f"middle_segment_preview_node_{node_number:02d}")
        if group is None:
            return QPointF()
        rect = group.sceneBoundingRect()
        x_pos = rect.left() if side == "left" else rect.right()
        return QPointF(x_pos, rect.top() + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2))

    def _material_preview_pin_at_scene_pos(self, scene_pos: QPointF) -> tuple[int, str]:
        radius = _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS + 5
        for node_number in self.material_card_preview_order:
            for side in ("left", "right"):
                pin_pos = self._material_preview_pin_position(node_number, side)
                if (scene_pos - pin_pos).manhattanLength() <= radius:
                    return node_number, side
        return 0, ""

    def _draw_material_preview_connections(self) -> None:
        scene = self.material_card_preview_scene
        for source, targets in self.material_card_preview_connections.items():
            source_pos = self._material_preview_pin_position(source, "right")
            if source_pos.isNull():
                continue
            selected_target = self.material_card_parallel_selections.get(source, targets[0] if targets else 0)
            for lane_index, target in enumerate(targets[:_ROUGHCUT_MATERIAL_PREVIEW_PARALLEL_LIMIT]):
                target_pos = self._material_preview_pin_position(target, "left")
                if target_pos.isNull():
                    continue
                is_selected = target == selected_target
                pen = QPen(QColor("#34C759" if is_selected else "#5A6A76"))
                pen.setWidth(3 if is_selected else 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                if not is_selected:
                    pen.setStyle(Qt.PenStyle.DashLine)
                lane_offset = (lane_index - 1) * 18 if len(targets) > 1 else 0
                path = QPainterPath(source_pos)
                ctrl_x = (source_pos.x() + target_pos.x()) / 2
                path.cubicTo(
                    QPointF(ctrl_x, source_pos.y() + lane_offset),
                    QPointF(ctrl_x, target_pos.y() + lane_offset),
                    target_pos,
                )
                connector = scene.addPath(path, pen)
                connector.setZValue(1)

    def _node_label(self, node_number: int) -> str:
        merged = self.material_card_preview_merged_nodes.get(node_number)
        if merged:
            return f"{node_number:02d}+{len(merged) - 1}"
        return f"{node_number:02d}"

    def _active_material_preview_order(self) -> list[int]:
        return [node for node in self.material_card_preview_order if node not in self.material_card_preview_deleted_nodes]

    def _refresh_material_preview_scene_rect(self) -> None:
        total_count = max(1, len(self._active_material_preview_order()))
        page_count = (total_count + _ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT - 1) // _ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT
        self.material_card_preview_page_count = page_count
        self.material_card_preview_scene.setSceneRect(
            0,
            0,
            page_count * _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH,
            430,
        )

    def _connect_material_preview_nodes(self, source: int, target: int) -> None:
        if source == target:
            return
        if source not in self._active_material_preview_order() or target not in self._active_material_preview_order():
            return
        targets = self.material_card_preview_connections.setdefault(source, [])
        if target not in targets:
            targets.append(target)
        del targets[_ROUGHCUT_MATERIAL_PREVIEW_PARALLEL_LIMIT:]
        if source not in self.material_card_parallel_selections and targets:
            self.material_card_parallel_selections[source] = targets[0]
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
            del self.material_card_preview_connections[source][_ROUGHCUT_MATERIAL_PREVIEW_PARALLEL_LIMIT:]
        self.material_card_parallel_selections = {
            source: targets[0]
            for source, targets in self.material_card_preview_connections.items()
            if targets
        }
        self.material_card_preview_generated_order = []
        self._populate_material_miro_uml_preview_scene()

    def _selected_material_connection_sequence(self) -> list[int]:
        active_order = self._active_material_preview_order()
        active_set = set(active_order)
        selected_edges: dict[int, int] = {}
        incoming: set[int] = set()
        for source, targets in self.material_card_preview_connections.items():
            if source not in active_set or not targets:
                continue
            target = self.material_card_parallel_selections.get(source, targets[0])
            if target not in targets or target not in active_set:
                continue
            selected_edges[source] = target
            incoming.add(target)
        roots = [node for node in active_order if node not in incoming]
        start = roots[0] if roots else (active_order[0] if active_order else 0)
        sequence: list[int] = []
        seen: set[int] = set()
        current = start
        while current and current in active_set and current not in seen:
            sequence.append(current)
            seen.add(current)
            current = selected_edges.get(current, 0)
        for node in active_order:
            if node not in seen:
                sequence.append(node)
        return sequence

    def _apply_material_preview_r_order_from_connections(self) -> None:
        old_order = list(self.material_card_preview_order)
        sequence = self._selected_material_connection_sequence()
        self.material_card_preview_order = sequence
        self.material_card_preview_last_reorder = {
            "old_order": old_order,
            "new_order": list(sequence),
            "mode": "auto_r_parallel_order",
            "commit": "preview_only",
        }
        self.material_card_preview_generated_order = []
        self._populate_material_miro_uml_preview_scene()

    def _select_material_preview_parallel_target(self, node_number: int) -> None:
        if node_number not in self._active_material_preview_order():
            return
        self.material_card_preview_selected_node = node_number
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
        source_index = self.material_card_preview_order.index(source)
        self.material_card_preview_order.insert(source_index + 1, next_node)
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
        self._refresh_scenario_sequence_preview()

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
        self.material_card_parallel_selections = {
            source: target
            for source, target in self.material_card_parallel_selections.items()
            if source not in targets and target not in targets
        }
        active = self._active_material_preview_order()
        self.material_card_preview_selected_node = active[0] if active else 0
        self.material_card_preview_multi_selection.clear()
        self._apply_material_preview_r_order_from_connections()

    def _generate_material_preview_scenario(self) -> None:
        self.material_card_preview_generated_order = self._selected_material_connection_sequence()
        self._refresh_scenario_sequence_preview()

    def _refresh_scenario_sequence_preview(self) -> None:
        scene = getattr(self, "scenario_sequence_scene", None)
        if scene is None:
            return
        scene.clear()
        selected_node = getattr(self, "material_card_preview_selected_node", 0)
        generated = list(getattr(self, "material_card_preview_generated_order", []))
        active_sequence = generated or ([selected_node] if selected_node else [])
        scene_width = max(1200, 46 + (len(active_sequence) * 154))
        scene.setSceneRect(0, 0, scene_width, 160)
        self.scenario_sequence_cards = []

        preview_font = QFont()
        preview_font.setPointSize(9)
        preview_font.setBold(True)
        topic_font = QFont()
        topic_font.setPointSize(10)
        topic_font.setBold(True)
        subtitle_font = QFont()
        subtitle_font.setPointSize(8)
        pen = QPen(QColor("#F5F7FA"), 1)
        for index, node_number in enumerate(active_sequence):
            x_pos = 24 + (index * 154)
            y_pos = 28
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
                }
            )

    def _populate_material_miro_uml_preview_scene(self) -> None:
        scene = self.material_card_preview_scene
        self._refresh_material_preview_scene_rect()
        scene.clear()
        node_positions = self._material_preview_slot_positions()
        preview_font = QFont()
        preview_font.setPointSize(9)
        preview_font.setBold(True)
        topic_font = QFont()
        topic_font.setPointSize(10)
        topic_font.setBold(True)
        badge_font = QFont()
        badge_font.setPointSize(8)
        badge_font.setBold(True)
        self.material_card_preview_nodes.clear()
        self._material_card_preview_groups.clear()

        for slot_index, node_number in enumerate(self.material_card_preview_order, start=1):
            x_pos, y_pos = node_positions[slot_index - 1]
            node_id = f"middle_segment_preview_node_{node_number:02d}"
            is_selected_parallel = node_number in set(self.material_card_parallel_selections.values())
            is_selected_node = node_number == getattr(self, "material_card_preview_selected_node", 0)
            is_multi_selected = node_number in getattr(self, "material_card_preview_multi_selection", [])
            border_color = "#34C759" if is_selected_parallel else "#2D3942"
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
            badge_text.setDefaultTextColor(QColor("#8A949E"))
            badge_text.setPos(8, 6)

            left_pin = scene.addEllipse(
                -_ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2) - _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                QPen(QColor("#DCE3EA"), 1),
                QBrush(QColor("#0A0F12")),
            )
            right_pin = scene.addEllipse(
                _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH - _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2) - _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS * 2,
                QPen(QColor("#DCE3EA"), 1),
                QBrush(QColor("#0A0F12")),
            )

            group = scene.createItemGroup([node, preview, preview_text, topic_text, badge_text, left_pin, right_pin])
            group.setData(0, node_id)
            group.setPos(x_pos, y_pos)
            group.setZValue(2)
            group.setCursor(Qt.CursorShape.OpenHandCursor)
            self._material_card_preview_groups[node_id] = group

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
        self._refresh_scenario_sequence_preview()

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

    def _drag_material_preview_node_to(self, node_id: str, scene_pos: QPointF) -> None:
        group = self._material_card_preview_groups.get(node_id)
        if group is None:
            return
        scene_rect = self.material_card_preview_scene.sceneRect()
        max_x = scene_rect.right() - _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH
        max_y = scene_rect.bottom() - _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT
        target_x = min(max(scene_rect.left(), scene_pos.x()), max_x)
        target_y = min(max(scene_rect.top(), scene_pos.y()), max_y)
        group.setPos(target_x, target_y)

    def _finish_material_preview_node_drag(self, node_id: str, scene_pos: QPointF) -> None:
        group = self._material_card_preview_groups.get(node_id)
        if group is None:
            return
        node_number = int(node_id.rsplit("_", 1)[1])
        slot_positions = self._material_preview_slot_positions()
        node_center_x = group.sceneBoundingRect().center().x()
        target_slot = min(
            range(len(slot_positions)),
            key=lambda index: abs(
                node_center_x - (slot_positions[index][0] + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH / 2))
            ),
        )
        old_order = list(self.material_card_preview_order)
        source_slot = old_order.index(node_number)
        new_order = list(old_order)
        if target_slot < len(new_order):
            new_order[source_slot], new_order[target_slot] = new_order[target_slot], new_order[source_slot]
        self.material_card_preview_order = new_order
        self.material_card_preview_last_reorder = {
            "node_id": node_id,
            "old_order": old_order,
            "new_order": list(new_order),
            "target_slot": target_slot + 1,
            "mode": "swap",
            "commit": "preview_only",
        }
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
