# Version: 03.09.11
# Phase: PHASE2
import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QListView, QWidget

from core.project.nle_snapshot import build_concat_render_plan_from_snapshot
from core.roughcut import build_concat_render_plan
from core.roughcut.models import (
    ChapterMetadata,
    EDLSegment,
    EditDecision,
    RoughCutMinorGroup,
    RoughCutResult,
    RoughCutSegment,
    RoughCutTitleSuggestion,
)
from core.roughcut.storyboard_graph import STORYBOARD_ROW_LABELS, STORYBOARD_ROW_ROLE_NAMES
from core.video_codec import roughcut_render_mode
from ui.main.app_command_bridge import execute_app_command
from ui.roughcut.roughcut_widget import (
    _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT,
    _ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT,
    _ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH,
    _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH,
    _ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS,
    _ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT,
    RoughcutWidget,
)
from ui.settings.settings_gap import GapSettingsDialog
from ui.settings.settings_advanced import AdvancedSettingsDialog
from ui.settings.settings_ai import SettingsDialog
from ui.editor.editor_project_open_native import load_stitched_cut_boundaries_for_srt_open


class RoughcutUiV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_roughcut_page_shows_frame_only_boxes_while_legacy_controls_stay_hidden(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1280, 720)
            widget.show()
            self.app.processEvents()

            for name in ("scenario_box", "material_box", "video_box", "settings_box"):
                box = widget.findChild(QWidget, name)
                self.assertIsNotNone(box)
                self.assertTrue(box.isVisible())

            self.assertFalse(widget.candidate_preview_frame.isVisible())
            self.assertFalse(widget.major_panel.isVisible())
            self.assertFalse(widget.video_bridge_frame.isVisible())
            self.assertFalse(widget.player_menu_frame.isVisible())
            self.assertFalse(widget.bottom_tabs.isVisible())
            self.assertTrue(hasattr(widget, "table"))
            self.assertTrue(hasattr(widget, "export_menu_btn"))
            self.assertIn("border: none", widget.roughcut_frame.styleSheet())
            self.assertIn("border: none", widget.roughcut_side_frame.styleSheet())
            self.assertEqual(widget.roughcut_side_frame.maximumWidth(), 468)
            self.assertTrue(widget.material_card_preview_view.isVisible())
            self.assertEqual(widget.material_card_preview_view.accessibleName(), "중분류 카드 Miro UML 미리보기")
            self.assertEqual(widget.material_card_preview_order, list(range(1, 31)))
            self.assertEqual(len(widget.material_card_preview_nodes), _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT)
            self.assertEqual(widget.material_card_preview_page_count, 1)
            self.assertEqual(widget.material_card_preview_scene.sceneRect().width(), _ROUGHCUT_MATERIAL_PREVIEW_PAGE_WIDTH)
            self.assertGreaterEqual(_ROUGHCUT_MATERIAL_PREVIEW_PIN_RADIUS, 8)
            self.assertEqual(
                len(widget.material_card_preview_nodes[:_ROUGHCUT_MATERIAL_PREVIEW_VISIBLE_COUNT]),
                _ROUGHCUT_MATERIAL_PREVIEW_NODE_COUNT,
            )
            self.assertEqual(widget.material_card_preview_grid_slots[1], (0, 0))
            self.assertEqual(widget.material_card_preview_grid_slots[2], (1, 0))
            self.assertEqual(widget.material_card_preview_grid_slots[3], (2, 0))
            self.assertEqual(widget.material_card_preview_grid_slots[6], (5, 0))
            self.assertEqual(
                {node["y"] for node in widget.material_card_preview_nodes[:21]},
                {26, 122, 218, 314, 410, 506},
            )
            self.assertEqual(
                [node["x"] for node in widget.material_card_preview_nodes[:10]],
                [106, 106, 106, 106, 106, 106, 294, 294, 294, 294],
            )
            self.assertEqual(widget.material_card_preview_nodes[21]["x"], 670)
            self.assertEqual(widget.material_card_preview_nodes[21]["y"], 314)
            lane_items = [
                item for item in widget.material_card_preview_scene.items()
                if str(item.data(0)).startswith("middle_segment_storyboard_lane_")
            ]
            self.assertEqual(len(lane_items), 6)
            for index, node in enumerate(widget.material_card_preview_nodes, start=1):
                self.assertEqual(node["id"], f"middle_segment_preview_node_{index:02d}")
                self.assertLessEqual(node["width"], 132)
                self.assertLessEqual(node["height"], 92)
                self.assertEqual(node["labels"], ("미리보기", "중분류 주제"))
            self.assertTrue(widget.scenario_sequence_view.isVisible())
            self.assertEqual(widget.scenario_generate_btn.text(), "시나리오생성")
            self.assertEqual(widget.material_random_connect_btn.text(), "랜덤 연결")
            self.assertEqual(widget.material_r_sort_btn.text(), "자동정렬")
            self.assertEqual(widget.material_multi_select_btn.text(), "멀티선택")
            self.assertEqual(widget.material_merge_btn.text(), "합치기")
            self.assertEqual(widget.material_split_btn.text(), "분할")
            self.assertEqual(widget.material_delete_btn.text(), "삭제")
            scene_text = "\n".join(
                item.toPlainText()
                for item in widget.material_card_preview_scene.items()
                if hasattr(item, "toPlainText")
            )
            self.assertIn("미리보기", scene_text)
            self.assertIn("중분류 주제", scene_text)
            self.assertNotIn("태그", scene_text)
            self.assertNotIn("자막 줄바꿈 영역", scene_text)
            self.assertNotIn("상태 / NLE Sync", scene_text)
            self.assertIn("#2D3942", widget.video_box.styleSheet())
            self.assertNotIn("#FFD60A", widget.video_box.styleSheet())
            self.assertTrue(widget.video_host.isVisible())
            self.assertEqual(widget.video_host.minimumHeight(), 173)
            self.assertGreaterEqual(widget.video_box.height(), 320)
            self.assertTrue(widget.roughcut_player_seek_slider.isVisible())
            self.assertTrue(widget.btn_roughcut_video_play.isVisible())
            for video_button, tooltip in (
                (widget.btn_roughcut_video_prev, "이전"),
                (widget.btn_roughcut_video_play, "재생"),
                (widget.btn_roughcut_video_stop, "정지"),
                (widget.btn_roughcut_video_next, "다음"),
            ):
                self.assertEqual(video_button.text(), "")
                self.assertEqual(video_button.toolTip(), tooltip)
                self.assertLessEqual(video_button.width(), 48)
                self.assertLessEqual(video_button.height(), 30)
            self.assertFalse(widget.roughcut_video_title_lbl.isVisible())
            self.assertFalse(widget.roughcut_video_state_lbl.isVisible())
            self.assertEqual(widget.roughcut_video_title_lbl.text(), "비디오")
            self.assertEqual(widget.roughcut_video_state_lbl.text(), "대기")

            width_handle = widget.roughcut_frame_splitter.handle(1)
            left_height_handle = widget.left_frame_splitter.handle(1)
            height_handle = widget.right_frame_splitter.handle(1)
            self.assertEqual(width_handle.objectName(), "roughcut_width_resize_handle")
            self.assertEqual(left_height_handle.objectName(), "roughcut_left_height_resize_handle")
            self.assertEqual(height_handle.objectName(), "roughcut_height_resize_handle")
            self.assertEqual(getattr(width_handle, "_marker", ""), "ㅓ")
            self.assertEqual(getattr(left_height_handle, "_marker", ""), "ㅓ")
            self.assertEqual(getattr(height_handle, "_marker", ""), "ㅏ")
            self.assertIs(getattr(width_handle, "_marker_anchor", None), widget.material_box)
            self.assertEqual(getattr(width_handle, "_marker_anchor_edge", ""), "top")
            self.assertIs(getattr(height_handle, "_marker_anchor", None), width_handle)
            self.assertEqual(width_handle.sizeHint().width(), 6)
            self.assertEqual(width_handle.sizeHint().height(), 6)
            self.assertEqual(height_handle.sizeHint().width(), 6)
            self.assertEqual(height_handle.sizeHint().height(), 6)

            width_marker = widget.findChild(QWidget, "roughcut_width_resize_handle_visual")
            height_marker = widget.findChild(QWidget, "roughcut_height_resize_handle_visual")
            self.assertIsNotNone(width_marker)
            self.assertIsNotNone(height_marker)
            self.assertTrue(width_marker.isVisible())
            self.assertTrue(height_marker.isVisible())
            self.assertEqual(width_marker.size().width(), 30)
            self.assertEqual(width_marker.size().height(), 30)
            self.assertEqual(height_marker.size().width(), 30)
            self.assertEqual(height_marker.size().height(), 30)
            widget._sync_roughcut_handle_markers()
            self.app.processEvents()
            material_right_x = widget.material_box.mapTo(widget, QPoint(widget.material_box.width(), 0)).x()
            settings_top_left = widget.settings_box.mapTo(widget, QPoint(0, 0))
            video_bottom_y = widget.video_box.mapTo(widget, QPoint(0, widget.video_box.height())).y()
            width_marker_stem_x = width_marker.x() + 24
            height_marker_stem_x = height_marker.x() + 6
            height_marker_stem_y = height_marker.y() + 15
            center_between_video_and_settings = (video_bottom_y + settings_top_left.y()) // 2
            self.assertLessEqual(abs(width_marker_stem_x - material_right_x), 2)
            self.assertLessEqual(abs(height_marker_stem_x - settings_top_left.x()), 2)
            self.assertLessEqual(abs(height_marker_stem_y - center_between_video_and_settings), 2)
            self.assertGreater(height_marker_stem_x, width_marker_stem_x)
            left_gap = widget.material_box.y() - (widget.scenario_box.y() + widget.scenario_box.height())
            right_gap = widget.settings_box.y() - (widget.video_box.y() + widget.video_box.height())
            self.assertEqual(left_gap, right_gap)

            before_width_marker_drag = list(widget.roughcut_frame_splitter.sizes())
            before_left_height_drag = list(widget.left_frame_splitter.sizes())
            width_marker_center = width_marker.rect().center()
            QTest.mousePress(width_marker, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, width_marker_center)
            QTest.mouseMove(width_marker, width_marker_center + QPoint(-80, 80), delay=1)
            self.app.processEvents()
            QTest.mouseRelease(
                width_marker,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                width_marker_center + QPoint(-80, 80),
            )
            self.assertNotEqual(widget.roughcut_frame_splitter.sizes(), before_width_marker_drag)
            self.assertNotEqual(widget.left_frame_splitter.sizes(), before_left_height_drag)

            before_height_marker_drag = list(widget.right_frame_splitter.sizes())
            height_marker_center = height_marker.rect().center()
            QTest.mousePress(height_marker, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, height_marker_center)
            QTest.mouseMove(height_marker, height_marker_center + QPoint(0, 80), delay=1)
            self.app.processEvents()
            QTest.mouseRelease(
                height_marker,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                height_marker_center + QPoint(0, 80),
            )
            self.assertNotEqual(widget.right_frame_splitter.sizes(), before_height_marker_drag)

            widget.roughcut_frame_splitter.setSizes([900, 320])
            widget.right_frame_splitter.setSizes([180, 420])
            self.app.processEvents()
            self.assertEqual(len(widget.roughcut_frame_splitter.sizes()), 2)
            self.assertEqual(len(widget.right_frame_splitter.sizes()), 2)
            self.assertGreater(widget.roughcut_frame_splitter.sizes()[1], 0)
            self.assertGreater(widget.right_frame_splitter.sizes()[0], 0)
        finally:
            widget.close()

    def test_material_preview_nodes_support_drag_drop_order_change_without_nle_commit(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            view = widget.material_card_preview_view
            first_node = widget._material_card_preview_groups["middle_segment_preview_node_01"]
            start = view.mapFromScene(first_node.sceneBoundingRect().center())
            last_slot_x, last_slot_y = widget._material_preview_slot_positions()[4]
            end_scene = QPointF(
                last_slot_x + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_WIDTH / 2),
                last_slot_y + (_ROUGHCUT_MATERIAL_PREVIEW_NODE_HEIGHT / 2),
            )
            end = view.mapFromScene(end_scene)

            QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(view.viewport(), end, delay=1)
            self.app.processEvents()
            self.assertGreater(widget.material_card_preview_drag_shadow_slot, 0)
            self.assertIsNotNone(widget.material_card_preview_drag_shadow_rect)
            QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
            self.app.processEvents()

            self.assertEqual(widget.material_card_preview_grid_slots[1], (4, 0))
            self.assertEqual(widget.material_card_preview_last_reorder["target_grid"], {"row": 4, "col": 0})
            self.assertEqual(widget.material_card_preview_last_reorder["mode"], "grid_insert_shift")
            self.assertEqual(widget.material_card_preview_last_reorder["commit"], "preview_only")
            self.assertEqual(widget.material_card_preview_drag_shadow_slot, 0)
            self.assertIsNone(widget.material_card_preview_drag_shadow_rect)
            self.assertIn("middle_segment_preview_node_01", {node["id"] for node in widget.material_card_preview_nodes[:6]})
        finally:
            widget.close()

    def test_material_preview_pin_hover_connect_stack_and_right_click_delete(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            view = widget.material_card_preview_view
            view.centerOn(widget._material_preview_pin_position(1, "right"))
            self.app.processEvents()
            view.horizontalScrollBar().setValue(0)
            self.app.processEvents()
            start = view.mapFromScene(widget._material_preview_pin_position(1, "right"))
            target = view.mapFromScene(widget._material_preview_pin_position(2, "left"))
            QTest.mouseMove(view.viewport(), start)
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_hover_pin, (1, "right"))
            QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            self.app.processEvents()
            target = view.mapFromScene(widget._material_preview_pin_position(2, "left"))
            QTest.mouseMove(view.viewport(), target, delay=1)
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_hover_pin, (2, "left"))
            self.assertFalse(widget.material_card_preview_connection_shadow_path.isEmpty())
            QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, target)
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_connections[1], [2])
            self.assertTrue(widget.material_card_preview_connection_shadow_path.isEmpty())
            self.assertEqual(widget._material_preview_pin_role_color(1, "right"), "#34C759")
            self.assertEqual(widget._material_preview_pin_role_color(2, "left"), "#34C759")

            widget._connect_material_preview_nodes(1, 3)
            widget._connect_material_preview_nodes(1, 4)
            self.app.processEvents()
            node_positions = {
                int(str(node["id"]).rsplit("_", 1)[1]): (node["x"], node["y"])
                for node in widget.material_card_preview_nodes
            }
            parallel_positions = [node_positions[node] for node in (2, 3, 4)]
            self.assertEqual({pos[0] for pos in parallel_positions}, {294})
            self.assertEqual({pos[1] for pos in parallel_positions}, {26, 122, 218})
            self.assertEqual(widget.material_card_preview_connection_roles[(1, 2)], "main")
            self.assertEqual(widget.material_card_preview_connection_roles[(1, 3)], "sub1")
            self.assertEqual(widget.material_card_preview_connection_roles[(1, 4)], "sub2")

            path = widget.material_card_preview_connection_paths[(1, 2)]
            hover_scene_pos = path.pointAtPercent(0.5)
            self.assertEqual(widget._material_preview_connection_at_scene_pos(hover_scene_pos), (1, 2))
            for expected_role in STORYBOARD_ROW_ROLE_NAMES[1:]:
                widget._cycle_material_preview_connection_role(1, 2)
                self.assertEqual(widget.material_card_preview_connection_roles[(1, 2)], expected_role)
            widget._cycle_material_preview_connection_role(1, 2)
            self.assertEqual(widget.material_card_preview_connection_roles[(1, 2)], "main")
            widget._set_material_preview_hover_connection(1, 2)
            hover_colors = [
                item.pen().color().name().lower()
                for item in widget.material_card_preview_scene.items()
                if hasattr(item, "pen") and item.pen().color().name().lower() == "#00c8ff"
            ]
            self.assertTrue(hover_colors)

            right_click_pos = view.mapFromScene(hover_scene_pos)
            QTest.mouseClick(
                view.viewport(),
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                right_click_pos,
            )
            self.app.processEvents()
            self.assertNotIn(2, widget.material_card_preview_connections[1])
            self.assertNotIn((1, 2), widget.material_card_preview_connection_paths)
        finally:
            widget.close()

    def test_material_preview_click_routing_mode_uses_dimming_red_follow_line_and_hover_target(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            view = widget.material_card_preview_view
            view.centerOn(widget._material_preview_pin_position(1, "right"))
            self.app.processEvents()
            source_pos = view.mapFromScene(widget._material_preview_pin_position(1, "right"))

            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, source_pos)
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_connect_source, 1)
            self.assertEqual(widget._material_preview_pin_role_color(1, "right"), "#34C759")

            target_pos = view.mapFromScene(widget._material_preview_pin_position(2, "left"))
            QTest.mouseMove(view.viewport(), target_pos, delay=1)
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_hover_pin, (2, "left"))
            shadow_items = [
                item
                for item in widget.material_card_preview_scene.items()
                if item.data(0) == "middle_segment_preview_connection_shadow"
            ]
            self.assertTrue(shadow_items)
            self.assertEqual(shadow_items[0].pen().color().name().lower(), "#ff3b30")
            self.assertAlmostEqual(shadow_items[0].opacity(), 0.5)

            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, target_pos)
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_connect_source, 0)
            self.assertEqual(widget.material_card_preview_connections[1], [2])
            self.assertEqual(widget._material_preview_pin_role_color(2, "left"), "#34C759")
        finally:
            widget.close()

    def test_material_preview_partial_connections_shadow_detour_and_auto_sort(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            widget._connect_material_preview_nodes(7, 3)
            widget._connect_material_preview_nodes(10, 11)
            self.app.processEvents()
            for source_node, target_node in ((7, 3), (10, 11)):
                source_row, source_col = widget.material_card_preview_grid_slots[source_node]
                target_row, target_col = widget.material_card_preview_grid_slots[target_node]
                self.assertEqual(target_col, source_col + 1)
            self.assertEqual(widget.material_card_preview_grid_slots[3][0], 0)
            self.assertEqual(widget.material_card_preview_grid_slots[11][0], 3)

            shadow_rect = widget._material_preview_shadow_rect_for_insert_slot(1, 1)
            widget.material_card_preview_drag_shadow_rect = shadow_rect
            source = widget._material_preview_pin_position(1, "right")
            target = QPointF(shadow_rect.right() + 120, shadow_rect.center().y())
            path = widget._material_preview_connection_path(source, target, source_node=1)
            self.assertFalse(widget._material_preview_path_intersects_rect(path, shadow_rect))

            widget._connect_material_preview_nodes(1, 4)
            widget._connect_material_preview_nodes(4, 7)
            self.app.processEvents()
            for (source_node, target_node), routed_path in widget.material_card_preview_connection_paths.items():
                blockers = widget._material_preview_blocking_rects(source_node, target_node)
                self.assertFalse(widget._material_preview_path_intersects_any_rect(routed_path, blockers))

            widget._draw_material_preview_line_jumps(
                [
                    {
                        "points": [QPointF(10, 50), QPointF(100, 50)],
                        "color": QColor("#34C759"),
                        "width": 3,
                        "opacity": 1.0,
                    },
                    {
                        "points": [QPointF(50, 10), QPointF(50, 100)],
                        "color": QColor("#0A84FF"),
                        "width": 2,
                        "opacity": 0.5,
                    },
                ]
            )
            self.assertTrue(
                any(
                    item.data(0) == "middle_segment_preview_connection_jump_bridge"
                    for item in widget.material_card_preview_scene.items()
                )
            )
            self.assertTrue(
                any(
                    item.data(0) == "middle_segment_preview_connection_jump_mask"
                    for item in widget.material_card_preview_scene.items()
                )
            )
        finally:
            widget.close()

    def test_material_preview_multiselect_copy_paste_preserves_source_color_and_grid_insert(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            widget.material_multi_select_btn.click()
            widget._select_material_preview_parallel_target(1)
            widget._select_material_preview_parallel_target(2)
            widget._copy_material_preview_selection()
            self.assertEqual(widget.material_card_preview_clipboard, [1, 2])

            widget._paste_material_preview_clipboard()
            self.app.processEvents()
            pasted = widget.material_card_preview_last_reorder["pasted_nodes"]
            self.assertEqual(len(pasted), 2)
            self.assertEqual(widget.material_card_preview_source_nodes[pasted[0]], 1)
            self.assertEqual(widget.material_card_preview_source_nodes[pasted[1]], 2)
            self.assertEqual(
                widget._material_preview_source_color(pasted[0]),
                widget._material_preview_source_color(1),
            )
            self.assertEqual(
                widget._material_preview_source_color(pasted[1]),
                widget._material_preview_source_color(2),
            )
            self.assertEqual(widget.material_card_preview_last_reorder["mode"], "copy_paste_grid_insert")
        finally:
            widget.close()

    def test_material_preview_right_drag_copies_card_before_drop(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            widget.material_card_preview_trim_state[1] = {"left": 2, "right": -1}
            widget._populate_material_miro_uml_preview_scene()
            view = widget.material_card_preview_view
            source_group = widget._material_card_preview_groups["middle_segment_preview_node_01"]
            view.centerOn(source_group.sceneBoundingRect().center())
            self.app.processEvents()
            start = view.mapFromScene(source_group.sceneBoundingRect().center())
            end_scene = QPointF(
                source_group.sceneBoundingRect().center().x() + 240,
                source_group.sceneBoundingRect().center().y() + 96,
            )
            end = view.mapFromScene(end_scene)

            QTest.mousePress(view.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, start)
            self.app.processEvents()
            copied_node = widget.material_card_preview_selected_node
            self.assertNotEqual(copied_node, 1)
            self.assertEqual(widget.material_card_preview_source_nodes[copied_node], 1)
            self.assertEqual(widget.material_card_preview_trim_state[copied_node], {"left": 2, "right": -1})
            self.assertEqual(widget.material_card_preview_last_reorder["mode"], "right_drag_copy_grid_insert")

            QTest.mouseMove(view.viewport(), end, delay=1)
            QTest.mouseRelease(view.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, end)
            self.app.processEvents()

            self.assertIn(copied_node, widget.material_card_preview_order)
            self.assertEqual(widget.material_card_preview_source_nodes[copied_node], 1)
            self.assertEqual(
                widget._material_preview_source_color(copied_node),
                widget._material_preview_source_color(1),
            )
            self.assertEqual(widget.material_card_preview_last_reorder["mode"], "grid_insert_shift")
        finally:
            widget.close()

    def test_material_preview_left_click_selects_card_without_reorder_and_shows_detail_layer(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            before_order = list(widget.material_card_preview_order)
            before_slots = dict(widget.material_card_preview_grid_slots)
            view = widget.material_card_preview_view
            group = widget._material_card_preview_groups["middle_segment_preview_node_02"]
            view.centerOn(group.sceneBoundingRect().center())
            self.app.processEvents()
            click_pos = view.mapFromScene(group.sceneBoundingRect().center())

            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, click_pos)
            self.app.processEvents()

            self.assertEqual(widget.material_card_preview_selected_node, 2)
            self.assertEqual(widget.material_card_preview_order, before_order)
            self.assertEqual(widget.material_card_preview_grid_slots, before_slots)
            self.assertEqual(widget.scenario_sequence_layer, "card_detail")
            self.assertEqual(widget.scenario_sequence_detail["node"], 2)
            self.assertEqual(widget.scenario_sequence_cards[0]["layer"], "card_detail")
            scene_text = "\n".join(
                item.toPlainText()
                for item in widget.scenario_sequence_scene.items()
                if hasattr(item, "toPlainText")
            )
            self.assertIn("카드 02 상세", scene_text)
            self.assertIn("선택 카드 상세", scene_text)
            self.assertIn("시나리오생성 버튼", scene_text)

            widget.scenario_generate_btn.click()
            self.app.processEvents()
            self.assertEqual(widget.scenario_sequence_layer, "sequence")
            self.assertTrue(widget.material_card_preview_generated_order)
        finally:
            widget.close()

    def test_material_preview_unlimited_outputs_and_single_input_auto_copy(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            for target in range(2, 10):
                widget._connect_material_preview_nodes(1, target)
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_connections[1], list(range(2, 10)))
            self.assertEqual(widget.material_card_preview_connection_roles[(1, 7)], "sub5")
            self.assertEqual(widget.material_card_preview_connection_roles[(1, 8)], "sub5")
            self.assertEqual(widget.material_card_preview_connection_roles[(1, 9)], "sub5")

            widget.material_card_preview_trim_state[2] = {"left": 2, "right": 3}
            widget._connect_material_preview_nodes(3, 2)
            self.app.processEvents()
            copied_target = widget.material_card_preview_last_auto_copy["connected_target"]
            self.assertNotEqual(copied_target, 2)
            self.assertGreaterEqual(copied_target, 31)
            self.assertIn(copied_target, widget.material_card_preview_order)
            self.assertEqual(widget.material_card_preview_connections[3], [copied_target])
            self.assertEqual(widget._material_preview_incoming_sources(2), [1])
            self.assertEqual(widget._material_preview_incoming_sources(copied_target), [3])
            self.assertEqual(widget.material_card_preview_source_nodes[copied_target], 2)
            self.assertEqual(widget.material_card_preview_trim_state[copied_target], {"left": 2, "right": 3})
            self.assertEqual(widget.material_card_preview_last_auto_copy["mode"], "single_input_auto_copy")
        finally:
            widget.close()

    def test_material_preview_connection_sort_animates_card_movement(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            node_id = "middle_segment_preview_node_02"
            before_pos = QPointF(widget._material_card_preview_groups[node_id].pos())
            widget._connect_material_preview_nodes(1, 2)
            self.app.processEvents()

            self.assertEqual(widget.material_card_preview_grid_slots[2], (0, 1))
            self.assertEqual(widget.material_card_preview_last_animation["mode"], "smooth_grid_sort")
            self.assertGreater(widget.material_card_preview_last_animation["move_count"], 0)
            self.assertTrue(widget._material_card_preview_animations)
            self.assertEqual(QPointF(widget._material_card_preview_groups[node_id].pos()), before_pos)

            QTest.qWait(widget.material_card_preview_last_animation["duration_ms"] + 80)
            self.app.processEvents()
            final_pos = QPointF(widget._material_card_preview_groups[node_id].pos())
            self.assertEqual(final_pos, QPointF(294, 26))
        finally:
            widget.close()

    def test_scenario_sequence_row_summaries_update_after_trim(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            self.assertEqual([summary["label"] for summary in widget.scenario_sequence_summaries], list(STORYBOARD_ROW_LABELS))
            main_before = widget.scenario_sequence_summaries[0]["duration_sec"]
            self.assertEqual(main_before, 50.0)
            widget.material_card_preview_selected_node = 1
            widget._adjust_material_preview_trim("right", 2)
            self.app.processEvents()
            main_after = widget.scenario_sequence_summaries[0]["duration_sec"]
            self.assertEqual(main_after, 52.0)
            scene_text = "\n".join(
                item.toPlainText()
                for item in widget.scenario_sequence_scene.items()
                if hasattr(item, "toPlainText")
            )
            self.assertIn("메인 52.0s", scene_text)
        finally:
            widget.close()

    def test_material_preview_random_connections_auto_sort_parallel_and_scenario_generation(self):
        widget = RoughcutWidget()
        try:
            widget.resize(1600, 900)
            widget.show()
            self.app.processEvents()

            widget.material_random_connect_btn.click()
            self.app.processEvents()
            self.assertTrue(widget.material_card_preview_connections)
            self.assertGreaterEqual(
                max(len(targets) for targets in widget.material_card_preview_connections.values()),
                3,
            )
            widget.material_r_sort_btn.click()
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_last_reorder["mode"], "auto_r_parallel_order")
            self.assertEqual(widget.material_card_preview_last_reorder["commit"], "preview_only")
            self.assertEqual(len(widget.material_card_preview_order), 30)
            node_positions = {
                int(str(node["id"]).rsplit("_", 1)[1]): (node["x"], node["y"])
                for node in widget.material_card_preview_nodes
            }
            self.assertTrue(all(y in {26, 122, 218, 314, 410, 506} for _x, y in node_positions.values()))

            sequence = widget._selected_material_connection_sequence()
            widget.scenario_generate_btn.click()
            self.app.processEvents()
            self.assertEqual(widget.material_card_preview_generated_order, sequence)
            self.assertEqual([card["node"] for card in widget.scenario_sequence_cards], sequence)

            source_with_parallel = next(
                source
                for source, targets in widget.material_card_preview_connections.items()
                if len(targets) > 1
            )
            parallel_target = widget.material_card_preview_connections[source_with_parallel][1]
            widget._select_material_preview_parallel_target(parallel_target)
            self.assertEqual(widget.material_card_parallel_selections[source_with_parallel], parallel_target)

            widget.material_multi_select_btn.click()
            widget._select_material_preview_parallel_target(widget.material_card_preview_order[0])
            widget._select_material_preview_parallel_target(widget.material_card_preview_order[1])
            self.assertEqual(widget.material_card_preview_multi_selection[:2], widget.material_card_preview_order[:2])
            widget.material_merge_btn.click()
            self.app.processEvents()
            self.assertIn(widget.material_card_preview_order[0], widget.material_card_preview_merged_nodes)
        finally:
            widget.close()

    def test_major_log_and_title_panels_render_without_removing_legacy_table(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="차량 외부 리뷰",
                        major_id="A",
                        tags=("외부", "타이어"),
                        minor_groups=(
                            RoughCutMinorGroup(
                                "A1",
                                "A",
                                "A1",
                                "외부 디자인",
                                0.0,
                                4.0,
                                chapter_ids=("chapter_0001",),
                                confidence=0.9,
                                status="confirmed",
                            ),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                title_suggestions=(
                    RoughCutTitleSuggestion("title_001", "EV6 외부 디자인 총정리", 0.9, expected_reach="높음"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._populate_result()

            self.assertTrue(hasattr(widget, "roughcut_frame"))
            self.assertEqual(widget.bottom_tabs.tabs.count(), 4)
            self.assertEqual(
                [widget.bottom_tabs.tabs.tabText(index) for index in range(widget.bottom_tabs.tabs.count())],
                ["챕터", "자막 세그먼트", "EDL", "로그"],
            )
            self.assertEqual(widget.table.rowCount(), 1)
            self.assertIn("chapter_0001", widget.major_panel._minor_buttons)
            self.assertEqual(widget.major_panel.summary_lbl.text(), "LLM 카드 1 / 세그먼트 1 / 검토 0")
            self.assertEqual(widget.major_panel.selection_lbl.text(), "선택 chapter_0001")
            self.assertIn("썸네일", widget.major_panel._preview_buttons["chapter_0001"].text())
            self.assertEqual(widget.major_panel.card_list.flow(), QListView.Flow.LeftToRight)
            self.assertEqual(widget.player_menu_frame.layout().itemAt(0).widget().text(), "핵심 메뉴")
            self.assertEqual(widget.player_core_section.toggle.text(), "AI 작업")
            self.assertFalse(widget.player_core_section.content.isVisible())
            self.assertEqual(widget.player_media_group.layout().itemAt(0).widget().text(), "재생")
            self.assertEqual(widget.player_export_section.toggle.text(), "내보내기")
            self.assertFalse(widget.player_export_section.content.isVisible())
            self.assertEqual(widget.export_menu_btn.text(), "내보내기")
            self.assertEqual(widget.bottom_tabs.section_title_lbl.text(), "보조 참조")
            self.assertFalse(widget.selection_status_section.content.isVisible())
            self.assertEqual(widget.title_panel._suggestions[0].title, "EV6 외부 디자인 총정리")
            self.assertIn("분석 완료", widget.log_panel.status_lbl.text())
            self.assertIn("chapter_0001", widget.bottom_tabs.edl_text.toPlainText())
            self.assertEqual(widget.filter_summary_lbl.text(), "표시 1 / 전체 1")
            self.assertEqual(widget.candidate_state_lbl.text(), "후보 없음")
            self.assertEqual(widget.selection_summary_lbl.text(), "선택 chapter_0001 · 확정")
            self.assertEqual(widget.player_order_lbl.text(), "카드 1/1 · major_A")
            self.assertEqual(widget.player_context_summary_lbl.text(), "후보 없음 · 표시 1 / 전체 1")
            self.assertEqual(widget.player_focus_summary_lbl.text(), "카드 1/1 · major_A · 선택 chapter_0001 · 확정")
            self.assertEqual(widget.player_reorder_summary_visible_lbl.text(), "재정렬 없음")
            self.assertEqual(widget.detail_edit_state_lbl.text(), "수정 상태: 자동 초안")
            self.assertFalse(widget.btn_revert_user_edit.isEnabled())
            self.assertEqual(widget.detail_delta_lbl.text(), "Δ In +0.00s / Δ Out +0.00s")
            self.assertEqual(widget.candidate_preview_filter_combo.count(), 2)
            self.assertEqual(widget.candidate_preview_filter_combo.itemText(0), "전체 후보")
            self.assertEqual(widget.candidate_preview_filter_combo.itemText(1), "LLM 결과만")

            widget.style_panel.set_style({"transition": "fade", "font_size": 50})
            widget._save_roughcut_export_style(widget.style_panel.style_payload())
            payload = widget._current_candidate_payload(widget._result)
            self.assertEqual(payload["roughcut_export_style"]["transition"], "fade")
            self.assertEqual(payload["roughcut_export_style"]["font_size"], 50)

            widget.cut_trim_start_spin.setValue(0.5)
            widget.cut_trim_end_spin.setValue(3.5)
            self.assertEqual(widget.detail_delta_lbl.text(), "Δ In +0.50s / Δ Out -0.50s")
            self.assertIn("#34C759", widget.detail_delta_lbl.styleSheet())
        finally:
            widget.close()

    def test_thumbnail_lookup_for_result_uses_cached_chapter_frames(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="외부 디자인", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._media_path = lambda: "/tmp/source.mp4"
            widget._project_path = lambda: "/tmp/test.aissproj"
            with patch("ui.roughcut.roughcut_widget.ensure_thumbnail") as ensure_thumbnail:
                ensure_thumbnail.return_value = SimpleNamespace(status="cached", path="/tmp/thumb.png", reason="")
                lookup = widget._thumbnail_lookup_for_result(widget._result)
                self.assertEqual(lookup["chapter_0001"], "/tmp/thumb.png")
                ensure_thumbnail.assert_called_once()
                second = widget._thumbnail_lookup_for_result(widget._result)
                self.assertEqual(second["chapter_0001"], "/tmp/thumb.png")
                ensure_thumbnail.assert_called_once()
        finally:
            widget.close()

    def test_minor_card_shows_subtitle_segment_count_and_snippet(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(
                result,
                editor_segments=[
                    {"start": 0.0, "end": 1.8, "text": "첫 번째 자막 세그먼트"},
                    {"start": 1.8, "end": 3.9, "text": "두 번째 자막 세그먼트"},
                ],
            )

            minor_list = widget.major_panel._minor_lists["major_A"]
            row_widget = minor_list.itemWidget(minor_list.item(0))
            badge = row_widget.findChild(QLabel, "roughcutSubtitleCountBadge")
            snippet = row_widget.findChild(QLabel, "roughcutSubtitleSnippetLabel")

            self.assertIsNotNone(badge)
            self.assertIsNotNone(snippet)
            self.assertEqual(badge.text(), "자막 2")
            self.assertIn("첫 번째 자막 세그먼트", snippet.text())
        finally:
            widget.close()

    def test_thumbnail_button_emits_preview_request_for_minor_row(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(result, editor_segments=[{"start": 0.0, "end": 2.0, "text": "첫 장면"}])

            events: list[tuple[str, bool]] = []
            widget.major_panel.previewRequested.connect(lambda chapter_id, hover: events.append((chapter_id, hover)))

            button = widget.major_panel._preview_buttons["chapter_0001"]
            button.click()

            self.assertEqual(events, [("chapter_0001", False)])
            self.assertEqual(button.objectName(), "roughcutMinorThumbnailButton")
            self.assertGreaterEqual(button.width(), 56)
            self.assertGreaterEqual(button.height(), 28)
        finally:
            widget.close()

    def test_drag_handles_exist_for_major_and_minor_cards(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(result, editor_segments=[{"start": 0.0, "end": 2.0, "text": "첫 장면"}])

            major_item = widget.major_panel.card_list.item(0)
            major_card = widget.major_panel.card_list.itemWidget(major_item)
            major_handle = major_card.findChild(QLabel, "roughcutMajorDragHandle")
            self.assertIsNotNone(major_handle)
            self.assertIn("순서 변경", major_handle.toolTip())

            minor_list = widget.major_panel._minor_lists["major_A"]
            minor_row = minor_list.itemWidget(minor_list.item(0))
            minor_handle = minor_row.findChild(QLabel, "roughcutMinorDragHandle")
            self.assertIsNotNone(minor_handle)
            self.assertIn("순서 변경", minor_handle.toolTip())
        finally:
            widget.close()

    def test_drag_surfaces_emit_major_and_minor_reorder_requests(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(result, editor_segments=[{"start": 0.0, "end": 2.0, "text": "첫 장면"}])

            major_item = widget.major_panel.card_list.item(0)
            major_card = widget.major_panel.card_list.itemWidget(major_item)
            major_surface = major_card if major_card.objectName() == "roughcutMajorCardSurface" else major_card.findChild(QWidget, "roughcutMajorCardSurface")
            major_calls: list[tuple[str, int]] = []
            original_major = widget.major_panel._move_segment_by_drag_delta
            widget.major_panel._move_segment_by_drag_delta = lambda sid, delta: major_calls.append((sid, delta))

            minor_list = widget.major_panel._minor_lists["major_A"]
            minor_row = minor_list.itemWidget(minor_list.item(0))
            minor_surface = minor_row if minor_row.objectName() == "roughcutMinorRowSurface" else minor_row.findChild(QWidget, "roughcutMinorRowSurface")
            minor_calls: list[tuple[str, str, int]] = []
            original_minor = widget.major_panel._move_chapter_by_drag_delta
            widget.major_panel._move_chapter_by_drag_delta = lambda sid, cid, delta: minor_calls.append((sid, cid, delta))

            try:
                self.assertIsNotNone(major_surface)
                self.assertIsNotNone(minor_surface)
                major_surface.dragDelta.emit(80)
                minor_surface.dragDelta.emit(40)
            finally:
                widget.major_panel._move_segment_by_drag_delta = original_major
                widget.major_panel._move_chapter_by_drag_delta = original_minor

            self.assertEqual(major_calls, [("major_A", 80)])
            self.assertEqual(minor_calls, [("major_A", "chapter_0001", 40)])
        finally:
            widget.close()

    def test_drag_surfaces_request_native_major_and_minor_drag_start(self):
        widget = RoughcutWidget()
        try:
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="외부 디자인",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                ),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget.major_panel.set_result(result, editor_segments=[{"start": 0.0, "end": 2.0, "text": "첫 장면"}])

            major_item = widget.major_panel.card_list.item(0)
            major_card = widget.major_panel.card_list.itemWidget(major_item)
            major_surface = major_card if major_card.objectName() == "roughcutMajorCardSurface" else major_card.findChild(QWidget, "roughcutMajorCardSurface")
            major_handle = major_card.findChild(QLabel, "roughcutMajorDragHandle")

            minor_list = widget.major_panel._minor_lists["major_A"]
            minor_row = minor_list.itemWidget(minor_list.item(0))
            minor_surface = minor_row if minor_row.objectName() == "roughcutMinorRowSurface" else minor_row.findChild(QWidget, "roughcutMinorRowSurface")
            minor_handle = minor_row.findChild(QLabel, "roughcutMinorDragHandle")

            major_calls: list[str] = []
            minor_calls: list[tuple[str, str]] = []
            original_major = widget.major_panel.card_list.start_drag_for_segment
            original_minor = widget.major_panel._start_minor_drag
            widget.major_panel.card_list.start_drag_for_segment = lambda sid: major_calls.append(sid)
            widget.major_panel._start_minor_drag = lambda sid, cid: minor_calls.append((sid, cid))
            try:
                self.assertIsNotNone(major_surface)
                self.assertIsNotNone(major_handle)
                self.assertIsNotNone(minor_surface)
                self.assertIsNotNone(minor_handle)
                major_surface.dragRequested.emit()
                major_handle.dragRequested.emit()
                minor_surface.dragRequested.emit()
                minor_handle.dragRequested.emit()
            finally:
                widget.major_panel.card_list.start_drag_for_segment = original_major
                widget.major_panel._start_minor_drag = original_minor

            self.assertEqual(major_calls, ["major_A", "major_A"])
            self.assertEqual(minor_calls, [("major_A", "chapter_0001"), ("major_A", "chapter_0001")])
        finally:
            widget.close()

    def test_unselected_major_cards_stay_compact_while_selected_card_expands(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 카드",
                        major_id="A",
                        summary="첫 카드 요약",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        8.0,
                        16.0,
                        title="둘째 카드",
                        major_id="B",
                        summary="둘째 카드 요약",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "셋째 장면", 8.0, 12.0, chapter_ids=("chapter_0003",)),
                            RoughCutMinorGroup("B2", "B", "B2", "넷째 장면", 12.0, 16.0, chapter_ids=("chapter_0004",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                    ChapterMetadata("chapter_0003", "셋째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                    ChapterMetadata("chapter_0004", "넷째 장면", 12.0, 16.0, major_id="B", minor_code="B2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                    EditDecision("chapter_0003", "keep", source_start=8.0, source_end=12.0),
                    EditDecision("chapter_0004", "keep", source_start=12.0, source_end=16.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0003", 8.0, 12.0, 8.0, 12.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0004", 12.0, 16.0, 12.0, 16.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()
            active = widget.major_panel._segment_cards["major_A"]
            inactive = widget.major_panel._segment_cards["major_B"]

            self.assertFalse(active["summary"].isHidden())
            self.assertTrue(inactive["summary"].isHidden())
            self.assertGreater(active["minor_list"].count(), 1)
            self.assertGreaterEqual(active["minor_list"].maximumHeight(), 58)
            self.assertGreater(active["minor_list"].maximumHeight(), inactive["minor_list"].maximumHeight())
            self.assertEqual(widget.player_order_lbl.text(), "카드 1/2 · major_A > major_B")

            widget._select_chapter_id_from_major_panel("chapter_0003")
            self.assertTrue(active["summary"].isHidden())
            self.assertFalse(inactive["summary"].isHidden())
            self.assertGreaterEqual(inactive["minor_list"].maximumHeight(), 58)
            self.assertGreater(inactive["minor_list"].maximumHeight(), active["minor_list"].maximumHeight())
            self.assertEqual(widget.player_order_lbl.text(), "카드 2/2 · major_A > major_B")
        finally:
            widget.close()

    def test_five_major_cards_keep_compact_card_budget(self):
        widget = RoughcutWidget()
        try:
            segments = []
            chapters = []
            edit_decisions = []
            edl_segments = []
            for index, major_id in enumerate(("A", "B", "C", "D", "E"), start=1):
                chapter_id = f"chapter_{index:04d}"
                start = float((index - 1) * 4)
                end = start + 4.0
                segments.append(
                    RoughCutSegment(
                        f"major_{major_id}",
                        start,
                        end,
                        title=f"{major_id} 카드",
                        major_id=major_id,
                        summary=f"{major_id} 카드 요약",
                        minor_groups=(
                            RoughCutMinorGroup(f"{major_id}1", major_id, f"{major_id}1", f"{major_id} 장면", start, end, chapter_ids=(chapter_id,)),
                        ),
                    )
                )
                chapters.append(ChapterMetadata(chapter_id, f"{major_id} 장면", start, end, major_id=major_id, minor_code=f"{major_id}1"))
                edit_decisions.append(EditDecision(chapter_id, "keep", source_start=start, source_end=end))
                edl_segments.append(EDLSegment("/tmp/source.mp4", chapter_id, start, end, start, end))

            widget._result = RoughCutResult(
                segments=tuple(segments),
                chapters=tuple(chapters),
                edit_decisions=tuple(edit_decisions),
                edl_segments=tuple(edl_segments),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()

            heights = []
            widths = []
            for segment_id in ("major_A", "major_B", "major_C", "major_D", "major_E"):
                item = widget.major_panel._segment_items[segment_id]
                heights.append(item.sizeHint().height())
                widths.append(item.sizeHint().width())
            self.assertEqual(widget.major_panel.card_list.flow(), QListView.Flow.LeftToRight)
            self.assertLessEqual(max(heights), 140)
            self.assertGreaterEqual(min(heights), 92)
            self.assertGreaterEqual(min(widths), 280)
            self.assertGreater(min(widths), max(heights))
            self.assertEqual(widget.major_panel._segment_cards["major_A"]["minor_list"].maximumHeight(), 36)
        finally:
            widget.close()

    def test_selected_major_card_expands_to_show_multiple_minor_rows(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        12.0,
                        title="첫 카드",
                        major_id="A",
                        summary="첫 카드 요약",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                            RoughCutMinorGroup("A3", "A", "A3", "셋째 장면", 8.0, 12.0, chapter_ids=("chapter_0003",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                    ChapterMetadata("chapter_0003", "셋째 장면", 8.0, 12.0, major_id="A", minor_code="A3"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                    EditDecision("chapter_0003", "keep", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0003", 8.0, 12.0, 8.0, 12.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()

            active = widget.major_panel._segment_cards["major_A"]
            item = widget.major_panel._segment_items["major_A"]

            self.assertGreaterEqual(active["minor_list"].maximumHeight(), 84)
            self.assertGreaterEqual(item.sizeHint().height(), 180)
            self.assertGreaterEqual(item.sizeHint().width(), 340)
        finally:
            widget.close()

    def test_major_card_reorder_updates_table_and_edl_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        8.0,
                        16.0,
                        title="둘째 장면",
                        major_id="B",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "둘째 장면", 8.0, 12.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 8.0, 12.0, 4.0, 8.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()
            widget._on_major_segment_order_changed(("major_B", "major_A"))

            self.assertEqual(widget._segment_order, ["major_B", "major_A"])
            self.assertEqual(widget.table.item(0, 3).text(), "둘째 장면")
            self.assertEqual(widget._result.chapters[0].chapter_id, "chapter_0002")
            self.assertEqual(widget._result.edl_segments[0].chapter_id, "chapter_0002")
        finally:
            widget.close()

    def test_ordered_preview_sequence_follows_visible_row_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        8.0,
                        16.0,
                        title="둘째 장면",
                        major_id="B",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "둘째 장면", 8.0, 12.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 8.0, 12.0, 4.0, 8.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._populate_result()
            played_rows: list[int] = []

            def _fake_play(row, muted=False, hover=False, update_preview_data=True):
                played_rows.append(int(row))
                widget._preview_row = int(row)

            widget._play_preview = _fake_play
            started = widget._start_ordered_preview_sequence()
            self.assertTrue(started)
            self.assertTrue(widget._sequence_preview_active)
            self.assertEqual(played_rows, [0])

            advanced = widget._advance_ordered_preview_sequence()
            self.assertTrue(advanced)
            self.assertEqual(played_rows, [0, 1])
            self.assertEqual(widget.player_order_lbl.text(), "카드 2/2 · major_A > major_B")
        finally:
            widget.close()

    def test_automation_move_selected_segment_updates_segment_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        8.0,
                        16.0,
                        title="둘째 장면",
                        major_id="B",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "둘째 장면", 8.0, 12.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 8.0, 12.0, 4.0, 8.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()
            widget.automation_select_chapter(chapter_id="chapter_0002")
            result = widget.automation_move_selected_segment(-1)

            self.assertTrue(result["changed"])
            self.assertEqual(result["selected_segment_id"], "major_B")
            self.assertEqual(result["segment_order"], ["major_B", "major_A"])
            self.assertEqual(widget._result.chapters[0].chapter_id, "chapter_0002")
        finally:
            widget.close()

    def test_minor_card_reorder_updates_chapter_and_edl_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._populate_result()
            widget._on_major_chapter_order_changed(("chapter_0002", "chapter_0001"))

            self.assertEqual(widget._chapter_order, ["chapter_0002", "chapter_0001"])
            self.assertEqual(widget.table.item(0, 3).text(), "둘째 장면")
            self.assertEqual(widget._result.chapters[0].chapter_id, "chapter_0002")
            self.assertEqual(widget._result.edl_segments[0].chapter_id, "chapter_0002")
            self.assertEqual(widget.reorder_summary_lbl.text(), "챕터 재정렬 · chapter_0002 > chapter_0001")
            self.assertEqual(widget.player_reorder_lbl.text(), "챕터 재정렬 · chapter_0002 > chapter_0001")
        finally:
            widget.close()

    def test_minor_card_reorder_changes_exported_srt_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._editor_segments = lambda: [
                {"start": 0.0, "end": 4.0, "text": "첫 자막", "speaker": "00"},
                {"start": 4.0, "end": 8.0, "text": "둘째 자막", "speaker": "00"},
            ]
            widget._populate_result()
            widget._on_major_chapter_order_changed(("chapter_0002", "chapter_0001"))

            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "roughcut_reordered.srt")
                result = widget.export_roughcut_srt_to_path(path)
                self.assertTrue(os.path.exists(result["path"]))
                text = open(path, "r", encoding="utf-8").read()

            self.assertLess(text.find("둘째 자막"), text.find("첫 자막"))
        finally:
            widget.close()

    def test_major_card_reorder_changes_exported_srt_order(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        4.0,
                        title="첫 카드",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 카드", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                        ),
                    ),
                    RoughCutSegment(
                        "major_B",
                        4.0,
                        8.0,
                        title="둘째 카드",
                        major_id="B",
                        minor_groups=(
                            RoughCutMinorGroup("B1", "B", "B1", "둘째 카드", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 카드", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 카드", 4.0, 8.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            widget._editor_segments = lambda: [
                {"start": 0.0, "end": 4.0, "text": "첫 카드 자막", "speaker": "00"},
                {"start": 4.0, "end": 8.0, "text": "둘째 카드 자막", "speaker": "00"},
            ]
            widget._populate_result()
            widget.automation_select_chapter(chapter_id="chapter_0002")
            widget.automation_move_selected_segment(-1)

            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "roughcut_segment_reordered.srt")
                result = widget.export_roughcut_srt_to_path(path)
                self.assertTrue(os.path.exists(result["path"]))
                text = open(path, "r", encoding="utf-8").read()

            self.assertLess(text.find("둘째 카드 자막"), text.find("첫 카드 자막"))
        finally:
            widget.close()

    def test_exported_roughcut_srt_writes_exact_join_sidecars_for_reopen(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._editor_segments = lambda: [
                {"start": 0.0, "end": 4.0, "text": "첫 자막", "speaker": "00"},
                {"start": 4.0, "end": 8.0, "text": "둘째 자막", "speaker": "00"},
            ]

            with tempfile.TemporaryDirectory() as tmp:
                target = os.path.join(tmp, "clip_roughcut.srt")
                export = widget.export_roughcut_srt_to_path(target)
                render_plan_path = Path(export["render_plan_path"])
                edl_path = Path(export["edl_path"])
                export_exists = os.path.exists(export["path"])
                render_plan_exists = render_plan_path.exists()
                edl_exists = edl_path.exists()
                render_payload = json.loads(render_plan_path.read_text(encoding="utf-8"))
                edl_payload = json.loads(edl_path.read_text(encoding="utf-8"))
                stitched_rows, stitched_sidecar_path = load_stitched_cut_boundaries_for_srt_open(target)

            self.assertTrue(export_exists)
            self.assertEqual(export["stitched_cut_boundary_count"], 1)
            self.assertTrue(render_plan_exists)
            self.assertTrue(edl_exists)
            self.assertEqual(render_payload["edl"]["schema"], "ai_subtitle_studio.roughcut.edl.v1")
            self.assertIn("subtitle_burnin_command", render_payload)
            self.assertEqual(render_payload["render_mode"], render_payload["render_plan"]["render_mode"])
            self.assertEqual(render_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual(render_payload["render_plan"]["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual(edl_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual([row["timeline_sec"] for row in stitched_rows], [4.0])
            self.assertEqual(Path(stitched_sidecar_path).name, "clip_roughcut_edl.json")
        finally:
            widget.close()

    def test_rendered_roughcut_video_writes_exact_join_sidecars_for_reopen(self):
        widget = RoughcutWidget()
        try:
            widget._active_editor = lambda: SimpleNamespace(media_path="/tmp/source.mov")
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "clip_roughcut.mov"
                plan = widget._build_render_plan_for_srt_target(output.with_suffix(".srt"), widget._result)
                sidecars = widget._write_exact_join_sidecars_for_rendered_video(output, plan, widget._result)
                render_plan_path = Path(sidecars["render_plan_path"])
                edl_path = Path(sidecars["edl_path"])
                render_plan_exists = render_plan_path.exists()
                edl_exists = edl_path.exists()
                render_payload = json.loads(render_plan_path.read_text(encoding="utf-8"))
                edl_payload = json.loads(edl_path.read_text(encoding="utf-8"))
                stitched_rows, stitched_sidecar_path = load_stitched_cut_boundaries_for_srt_open(
                    str(output.with_suffix(".srt")),
                    str(output),
                )

            self.assertEqual(sidecars["stitched_cut_boundary_count"], 1)
            self.assertTrue(render_plan_exists)
            self.assertTrue(edl_exists)
            self.assertEqual(render_payload["edl"]["schema"], "ai_subtitle_studio.roughcut.edl.v1")
            self.assertIn("subtitle_burnin_command", render_payload)
            self.assertEqual(render_payload["render_mode"], render_payload["render_plan"]["render_mode"])
            self.assertEqual(render_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual(edl_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertEqual([row["timeline_sec"] for row in stitched_rows], [4.0])
            self.assertEqual(Path(stitched_sidecar_path).name, "clip_roughcut_edl.json")
        finally:
            widget.close()

    def test_render_plan_builders_route_through_nle_snapshot_adapter_with_legacy_parity(self):
        widget = RoughcutWidget()
        try:
            widget._active_editor = lambda: SimpleNamespace(media_path="/tmp/source.mov")
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            with tempfile.TemporaryDirectory() as tmp, patch(
                "ui.roughcut.roughcut_export.build_concat_render_plan_from_snapshot",
                wraps=build_concat_render_plan_from_snapshot,
            ) as nle_adapter:
                temp_dir = Path(tempfile.gettempdir()) / "ai_subtitle_studio_roughcut"
                srt_target = Path(tmp) / "clip_roughcut.srt"
                srt_plan = widget._build_render_plan_for_srt_target(srt_target, result)
                legacy_srt_plan = build_concat_render_plan(
                    result.edl_segments,
                    srt_target.with_suffix(".mov"),
                    temp_dir,
                    render_mode=roughcut_render_mode(),
                )

                video_target = Path(tmp) / "manual_render.mov"
                video_plan = widget._build_render_plan_for_video_target(video_target, result)
                legacy_video_plan = build_concat_render_plan(
                    result.edl_segments,
                    video_target,
                    temp_dir,
                    render_mode=roughcut_render_mode(),
                )

            self.assertEqual(nle_adapter.call_count, 2)
            self.assertEqual(srt_plan.output_path, legacy_srt_plan.output_path)
            self.assertEqual(srt_plan.extract_commands, legacy_srt_plan.extract_commands)
            self.assertEqual(srt_plan.concat_command, legacy_srt_plan.concat_command)
            self.assertEqual(srt_plan.segment_manifest, legacy_srt_plan.segment_manifest)
            self.assertEqual(srt_plan.stitched_cut_boundaries, legacy_srt_plan.stitched_cut_boundaries)
            self.assertEqual(video_plan.output_path, legacy_video_plan.output_path)
            self.assertEqual(video_plan.extract_commands, legacy_video_plan.extract_commands)
            self.assertEqual(video_plan.concat_command, legacy_video_plan.concat_command)
            self.assertEqual(video_plan.segment_manifest, legacy_video_plan.segment_manifest)
            self.assertEqual(video_plan.stitched_cut_boundaries, legacy_video_plan.stitched_cut_boundaries)
        finally:
            widget.close()

    def test_saved_candidate_render_plan_uses_nle_snapshot_adapter_with_legacy_parity(self):
        widget = RoughcutWidget()
        try:
            widget._active_editor = lambda: SimpleNamespace(media_path="/tmp/source.mov")
            widget._source_signature = "fixture-signature"
            result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )

            with patch(
                "ui.roughcut.roughcut_export.build_concat_render_plan_from_snapshot",
                wraps=build_concat_render_plan_from_snapshot,
            ) as nle_adapter:
                payload = widget._current_candidate_payload(result)

            render_plan = payload["outputs"]["render_plan"]
            legacy_plan = build_concat_render_plan(
                result.edl_segments,
                Path("/tmp/source_roughcut.mov"),
                Path(tempfile.gettempdir()) / "ai_subtitle_studio_roughcut",
                render_mode=roughcut_render_mode(),
            )
            self.assertEqual(nle_adapter.call_count, 1)
            self.assertEqual(render_plan["output_path"], legacy_plan.output_path)
            self.assertEqual(render_plan["extract_commands"], legacy_plan.extract_commands)
            self.assertEqual(render_plan["concat_command"], legacy_plan.concat_command)
            self.assertEqual(render_plan["segment_manifest"], legacy_plan.segment_manifest)
            self.assertEqual(render_plan["stitched_cut_boundaries"], legacy_plan.stitched_cut_boundaries)
        finally:
            widget.close()

    def test_automation_render_video_to_path_starts_worker_for_requested_target(self):
        widget = RoughcutWidget()
        try:
            widget._active_editor = lambda: SimpleNamespace(media_path="/tmp/source.mov")
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            started = []

            def fake_start(plan, dry_run=False):
                started.append((plan, dry_run))

            widget._start_render_worker = fake_start
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "automation_render.mov"
                data = widget.automation_start_render_video_to_path(str(output))

            self.assertEqual(len(started), 1)
            self.assertFalse(started[0][1])
            self.assertEqual(started[0][0].output_path, data["path"])
            self.assertEqual(Path(data["path"]).name, "automation_render.mov")
            self.assertEqual(Path(data["render_plan_path"]).name, "automation_render_render_plan.json")
            self.assertEqual(Path(data["edl_path"]).name, "automation_render_edl.json")
            self.assertEqual(data["stitched_cut_boundary_count"], 1)
        finally:
            widget.close()

    def test_app_command_roughcut_export_and_render_use_nle_snapshot_route(self):
        widget = RoughcutWidget()
        try:
            editor = SimpleNamespace(media_path="/tmp/source.mov")
            owner = SimpleNamespace(
                _roughcut_widget=widget,
                _current_project_path="",
                _multiclip_files=[],
                _multiclip_boundaries=[],
                _active_editor=lambda: editor,
                isMinimized=lambda: False,
                show=lambda: None,
                raise_=lambda: None,
                activateWindow=lambda: None,
            )
            widget.owner = owner
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment(
                        "major_A",
                        0.0,
                        8.0,
                        title="첫 장면",
                        major_id="A",
                        minor_groups=(
                            RoughCutMinorGroup("A1", "A", "A1", "첫 장면", 0.0, 4.0, chapter_ids=("chapter_0001",)),
                            RoughCutMinorGroup("A2", "A", "A2", "둘째 장면", 4.0, 8.0, chapter_ids=("chapter_0002",)),
                        ),
                    ),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._editor_segments = lambda: [
                {"start": 0.0, "end": 4.0, "text": "첫 자막", "speaker": "00"},
                {"start": 4.0, "end": 8.0, "text": "둘째 자막", "speaker": "00"},
            ]
            started = []
            widget._start_render_worker = lambda plan, dry_run=False: started.append((plan, dry_run))

            with tempfile.TemporaryDirectory() as tmp, patch(
                "ui.roughcut.roughcut_export.build_concat_render_plan_from_snapshot",
                wraps=build_concat_render_plan_from_snapshot,
            ) as nle_adapter:
                export_path = Path(tmp) / "bridge_roughcut.srt"
                export_result = execute_app_command(owner, {"command": "roughcut-export-srt", "path": str(export_path)})
                render_path = Path(tmp) / "bridge_render.mov"
                render_result = execute_app_command(owner, {"command": "roughcut-render-video", "path": str(render_path)})
                export_render_plan = Path(export_result["data"]["render_plan_path"])
                export_edl = Path(export_result["data"]["edl_path"])
                export_render_plan_exists = export_render_plan.exists()
                export_edl_exists = export_edl.exists()
                render_payload = json.loads(export_render_plan.read_text(encoding="utf-8"))

            self.assertTrue(export_result["ok"])
            self.assertEqual(export_result["message"], "roughcut_srt_exported")
            self.assertEqual(export_result["data"]["subtitle_count"], 2)
            self.assertTrue(export_render_plan_exists)
            self.assertTrue(export_edl_exists)
            self.assertEqual(render_payload["edl"]["schema"], "ai_subtitle_studio.roughcut.edl.v1")
            self.assertEqual(render_payload["stitched_cut_boundaries"][0]["timeline_sec"], 4.0)
            self.assertTrue(render_result["ok"])
            self.assertTrue(render_result["queued"])
            self.assertEqual(render_result["message"], "roughcut_render_started")
            self.assertEqual(render_result["data"]["path"], str(render_path))
            self.assertEqual(render_result["data"]["stitched_cut_boundary_count"], 1)
            self.assertEqual(render_result["data"]["extract_command_count"], len(started[0][0].extract_commands))
            self.assertEqual(render_result["data"]["concat_command_count"], 1)
            self.assertEqual(len(started), 1)
            self.assertFalse(started[0][1])
            self.assertEqual(started[0][0].output_path, str(render_path))
            self.assertEqual(nle_adapter.call_count, 2)
        finally:
            widget.close()

    def test_attach_and_release_editor_video_frame_uses_external_host(self):
        widget = RoughcutWidget()
        frame = QWidget()

        class _FakeVideoPlayer:
            def restore_after_navigation(self):
                return None

        class _FakeEditor:
            def __init__(self, owned_frame):
                self._owned_frame = owned_frame
                self.video_player = _FakeVideoPlayer()
                self.detached = 0
                self.restored = 0

            def detach_video_frame_for_external_host(self):
                self.detached += 1
                return self._owned_frame

            def restore_video_frame_from_external_host(self, restored_frame=None):
                self.restored += 1
                self._owned_frame = restored_frame or self._owned_frame

        editor = _FakeEditor(frame)
        try:
            self.assertTrue(widget.attach_editor_video_frame(editor))
            self.assertEqual(widget._attached_video_editor, editor)
            self.assertEqual(widget._attached_video_frame, frame)
            self.assertEqual(widget.video_host_layout.indexOf(frame), 0)
            self.assertFalse(widget.video_host_placeholder.isVisible())
            widget.release_editor_video_frame()
            self.assertEqual(editor.restored, 1)
            self.assertIsNone(widget._attached_video_editor)
            self.assertIsNone(widget._attached_video_frame)
            self.assertGreaterEqual(widget.video_host_layout.indexOf(widget.video_host_placeholder), 0)
        finally:
            widget.close()

    def test_video_box_shows_editor_subtitles_and_applies_style_to_attached_player(self):
        widget = RoughcutWidget()
        frame = QWidget()

        class _FakeMediaPlayer:
            def __init__(self):
                self._position = 0
                self.playing = False

            def setPosition(self, value):
                self._position = int(value)

            def position(self):
                return self._position

            def play(self):
                self.playing = True

            def pause(self):
                self.playing = False

        class _FakeVideoPlayer:
            def __init__(self):
                self.media_player = _FakeMediaPlayer()
                self.current_time = 0.0
                self.applied_styles = []
                self.seek_calls = []
                self.sub_label = SimpleNamespace(_export_style={"font": "Editor Font", "size": 52, "align": "center"})

            def restore_after_navigation(self):
                return None

            def apply_export_subtitle_style(self, style):
                payload = dict(style or {})
                self.sub_label._export_style = payload
                self.applied_styles.append(payload)

            def seek_direct(self, sec):
                self.seek_calls.append(float(sec))
                self.current_time = float(sec)
                self.media_player.setPosition(int(float(sec) * 1000.0))

        class _FakeEditor:
            def __init__(self, owned_frame):
                self._owned_frame = owned_frame
                self.video_player = _FakeVideoPlayer()

            def detach_video_frame_for_external_host(self):
                return self._owned_frame

            def restore_video_frame_from_external_host(self, restored_frame=None):
                self._owned_frame = restored_frame or self._owned_frame

        editor = _FakeEditor(frame)
        widget.owner = SimpleNamespace(_active_editor=lambda: editor)
        widget._editor_segments = lambda: [
            {"start": 0.0, "end": 4.0, "text": "에디터 생성 자막", "speaker": "00"},
        ]
        try:
            self.assertTrue(widget.attach_editor_video_frame(editor))
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 4.0, title="첫 장면", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._populate_result()

            self.assertIn("에디터 생성 자막", widget.roughcut_subtitle_preview_lbl.text())
            self.assertEqual(editor.video_player.applied_styles[-1]["font"], "Editor Font")
            self.assertEqual(editor.video_player.applied_styles[-1]["size"], 52)
            self.assertIn("Editor Font", widget.roughcut_video_style_lbl.text())
            self.assertIn("52", widget.roughcut_video_style_lbl.text())
            widget._save_roughcut_export_style(
                {
                    "font_family": "Apple SD Gothic Neo",
                    "font_size": 64,
                    "position": "top_center",
                }
            )

            self.assertEqual(editor.video_player.applied_styles[-1]["font_size"], 64)
            self.assertEqual(editor.video_player.applied_styles[-1]["font_family"], "Apple SD Gothic Neo")
            self.assertIn("Apple SD Gothic Neo", widget.roughcut_video_style_lbl.text())
            self.assertIn("64", widget.roughcut_video_style_lbl.text())
        finally:
            widget.close()

    def test_video_box_playback_has_low_command_delay_and_height_handle_resizes_while_playing(self):
        widget = RoughcutWidget()
        frame = QWidget()

        class _FakeMediaPlayer:
            def __init__(self):
                self._position = 0
                self.playing = False

            def setPosition(self, value):
                self._position = int(value)

            def position(self):
                return self._position

            def play(self):
                self.playing = True

            def pause(self):
                self.playing = False

        class _FakeVideoPlayer:
            def __init__(self):
                self.media_player = _FakeMediaPlayer()
                self.current_time = 0.0

            def restore_after_navigation(self):
                return None

            def apply_export_subtitle_style(self, _style):
                return None

            def seek_direct(self, sec):
                self.current_time = float(sec)
                self.media_player.setPosition(int(float(sec) * 1000.0))

        class _FakeEditor:
            def __init__(self, owned_frame):
                self._owned_frame = owned_frame
                self.video_player = _FakeVideoPlayer()

            def detach_video_frame_for_external_host(self):
                return self._owned_frame

            def restore_video_frame_from_external_host(self, restored_frame=None):
                self._owned_frame = restored_frame or self._owned_frame

        editor = _FakeEditor(frame)
        widget.owner = SimpleNamespace(_active_editor=lambda: editor)
        widget._editor_segments = lambda: [
            {"start": 0.0, "end": 4.0, "text": "첫 자막", "speaker": "00"},
            {"start": 4.0, "end": 8.0, "text": "둘째 자막", "speaker": "00"},
        ]
        try:
            widget.resize(1280, 760)
            widget.show()
            self.app.processEvents()
            self.assertTrue(widget.attach_editor_video_frame(editor))
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="첫 장면", major_id="A"),),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 4.0, 8.0, major_id="A", minor_code="A2"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "keep", source_start=4.0, source_end=8.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mov", "chapter_0001", 0.0, 4.0, 0.0, 4.0, chapter_id="chapter_0001"),
                    EDLSegment("/tmp/source.mov", "chapter_0002", 4.0, 8.0, 4.0, 8.0, chapter_id="chapter_0002"),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._populate_result()

            started = time.perf_counter()
            self.assertTrue(widget._start_roughcut_video_playback())
            playback_delay_ms = (time.perf_counter() - started) * 1000.0
            self.assertLess(playback_delay_ms, 35.0)
            self.assertTrue(editor.video_player.media_player.playing)
            self.assertEqual(widget.roughcut_video_state_lbl.text(), "재생 중")

            events = []
            splitter = widget.right_frame_splitter
            handle = splitter.handle(1)
            before = list(splitter.sizes())

            def _on_moved(pos, index):
                events.append((int(pos), int(index), list(splitter.sizes())))

            splitter.splitterMoved.connect(_on_moved)
            center = handle.rect().center()
            QTest.mousePress(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
            QTest.qWait(5)
            QTest.mouseMove(handle, center + QPoint(0, 80), delay=1)
            self.app.processEvents()
            during = list(splitter.sizes())
            QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center + QPoint(0, 80))
            splitter.splitterMoved.disconnect(_on_moved)

            self.assertTrue(events)
            self.assertNotEqual(during, before)
            self.assertTrue(editor.video_player.media_player.playing)
        finally:
            widget.close()

    def test_detail_panel_surfaces_user_edit_summary(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="외부 디자인", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._user_edits = {
                "chapter_0001": {
                    "title": "외관 오프닝",
                    "trim_start": 0.2,
                    "trim_end": 3.8,
                    "status": "사용자 수정됨",
                }
            }

            widget._populate_result()

            self.assertEqual(widget.detail_edit_state_lbl.text(), "수정 상태: 사용자 수정됨 · 제목 / 컷 조정")
            self.assertIn("#FFD60A", widget.detail_edit_state_lbl.styleSheet())
            self.assertTrue(widget.btn_revert_user_edit.isEnabled())
        finally:
            widget.close()

    def test_revert_button_restores_auto_draft_state(self):
        widget = RoughcutWidget()
        try:
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="외부 디자인", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "외부 디자인", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            widget._user_edits = {
                "chapter_0001": {
                    "title": "외관 오프닝",
                    "trim_start": 0.2,
                    "trim_end": 3.8,
                    "status": "사용자 수정됨",
                }
            }

            widget._populate_result()
            widget._revert_user_edit()

            self.assertEqual(widget._user_edits, {})
            self.assertEqual(widget.detail_edit_state_lbl.text(), "수정 상태: 자동 초안")
            self.assertFalse(widget.btn_revert_user_edit.isEnabled())
        finally:
            widget.close()

    def test_candidate_state_and_filter_badges_follow_selection(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = RoughCutResult(
                segments=(
                    RoughCutSegment("major_A", 0.0, 8.0, title="첫 장면", major_id="A"),
                    RoughCutSegment("major_B", 8.0, 16.0, title="둘째 장면", major_id="B"),
                ),
                chapters=(
                    ChapterMetadata("chapter_0001", "첫 장면", 0.0, 4.0, major_id="A", minor_code="A1"),
                    ChapterMetadata("chapter_0002", "둘째 장면", 8.0, 12.0, major_id="B", minor_code="B1"),
                ),
                edit_decisions=(
                    EditDecision("chapter_0001", "keep", safety="ideal", source_start=0.0, source_end=4.0),
                    EditDecision("chapter_0002", "trim", safety="risky", source_start=8.0, source_end=12.0),
                ),
                edl_segments=(
                    EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),
                    EDLSegment("/tmp/source.mp4", "chapter_0002", 8.0, 12.0, 4.0, 8.0),
                ),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            current = widget._roughcut_state_payload()
            current["candidate_id"] = "candidate_current"
            current["source_signature"] = "sig-current"
            current["name"] = "현재 후보"

            previous = dict(current)
            previous["candidate_id"] = "candidate_old"
            previous["source_signature"] = "sig-previous"
            previous["name"] = "이전 후보"

            widget._roughcut_candidates = [previous, current]
            widget._selected_candidate_id = "candidate_current"
            with patch.object(widget, "_current_editor_signature", return_value="sig-current"):
                widget._populate_result()
                widget._refresh_candidate_combo()

                self.assertEqual(widget.candidate_state_lbl.text(), "현재 자막 기준")
                self.assertEqual(widget.filter_summary_lbl.text(), "표시 2 / 전체 2")
                self.assertEqual(widget.major_panel.summary_lbl.text(), "LLM 카드 2 / 세그먼트 0 / 검토 0")
                self.assertEqual(widget.selection_summary_lbl.text(), "선택 chapter_0001 · 확정")
                self.assertFalse(widget.candidate_combo.isVisible())
                self.assertEqual(len(widget._candidate_preview_buttons), 2)
                self.assertIn("현재 후보", widget._candidate_preview_buttons[1].text())
                self.assertIn("major_A", widget._candidate_preview_buttons[0].text())
                self.assertLess(widget._candidate_preview_buttons[0].maximumWidth(), widget._candidate_preview_buttons[0].minimumHeight())
                self.assertLessEqual(widget._candidate_preview_buttons[0].maximumWidth(), 142)
                self.assertGreaterEqual(widget._candidate_preview_buttons[0].minimumHeight(), 300)

                widget.safety_filter_combo.setCurrentText("risky")
                self.assertEqual(widget.filter_summary_lbl.text(), "표시 1 / 전체 2")
                self.assertEqual(widget.selection_summary_lbl.text(), "선택 chapter_0002 · 검토 필요")

                widget._apply_candidate_payload(previous, persist=False)
                self.assertEqual(widget.candidate_state_lbl.text(), "저장된 자막 기준")
        finally:
            widget.close()

    def test_candidate_preview_frames_limit_to_three_and_apply_selection(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="A 장면", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "A 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", safety="ideal", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            current = widget._roughcut_state_payload()
            candidates = []
            for index, title in enumerate(("첫 후보", "둘째 후보", "셋째 후보", "넷째 후보"), start=1):
                candidate = dict(current)
                candidate["candidate_id"] = f"candidate_{index}"
                candidate["name"] = title
                candidate["source_signature"] = "sig-current" if index == 1 else f"sig-{index}"
                candidate["segments"] = [{
                    "segment_id": f"major_{index}",
                    "major_id": chr(64 + index),
                    "title": title,
                    "start": 0.0,
                    "end": 3.0,
                    "minor_groups": (),
                    "tags": (),
                }]
                candidate["chapters"] = [{
                    "chapter_id": f"chapter_{index:04d}",
                    "title": title,
                    "summary": title,
                    "start": 0.0,
                    "end": 3.0,
                    "major_id": chr(64 + index),
                    "minor_code": f"{chr(64 + index)}1",
                    "tags": (),
                }]
                candidate["edit_decisions"] = [{
                    "segment_id": f"chapter_{index:04d}",
                    "action": "keep",
                    "source_start": 0.0,
                    "source_end": 3.0,
                    "safety": "ideal",
                }]
                candidate["edl_segments"] = [{
                    "source_path": "/tmp/source.mp4",
                    "segment_id": f"chapter_{index:04d}",
                    "source_start": 0.0,
                    "source_end": 3.0,
                    "output_start": 0.0,
                    "output_end": 3.0,
                    "action": "keep",
                    "chapter_id": f"chapter_{index:04d}",
                    "clip_index": 0,
                }]
                candidates.append(candidate)
            widget._roughcut_candidates = candidates
            widget._selected_candidate_id = "candidate_1"

            with patch.object(widget, "_current_editor_signature", return_value="sig-current"):
                widget._refresh_candidate_combo()
                self.assertEqual(len(widget._candidate_preview_buttons), 3)
                self.assertNotIn("넷째 후보", "\n".join(button.text() for button in widget._candidate_preview_buttons))
                self.assertLess(widget._candidate_preview_buttons[0].maximumWidth(), widget._candidate_preview_buttons[0].minimumHeight())
                self.assertLessEqual(widget._candidate_preview_buttons[0].maximumWidth(), 142)
                self.assertGreaterEqual(widget._candidate_preview_buttons[0].minimumHeight(), 300)
                widget._on_candidate_frame_clicked("candidate_2")
                self.assertEqual(widget._selected_candidate_id, "candidate_2")
        finally:
            widget.close()

    def test_candidate_preview_toggle_applies_selection(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="A 장면", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "A 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", safety="ideal", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            current = widget._roughcut_state_payload()
            current["candidate_id"] = "candidate_1"
            current["name"] = "첫 후보"
            current["source_signature"] = "sig-current"
            previous = dict(current)
            previous["candidate_id"] = "candidate_2"
            previous["name"] = "둘째 후보"
            previous["source_signature"] = "sig-previous"
            widget._roughcut_candidates = [current, previous]
            widget._selected_candidate_id = "candidate_1"

            with patch.object(widget, "_current_editor_signature", return_value="sig-current"):
                widget._refresh_candidate_combo()
                widget._candidate_preview_buttons[1].setChecked(True)
                self.assertEqual(widget._selected_candidate_id, "candidate_2")
                self.assertEqual(widget.candidate_state_lbl.text(), "저장된 자막 기준")
        finally:
            widget.close()

    def test_candidate_preview_filter_shows_only_llm_candidates(self):
        widget = RoughcutWidget()
        try:
            widget._source_signature = "sig-current"
            widget._result = RoughCutResult(
                segments=(RoughCutSegment("major_A", 0.0, 8.0, title="A 장면", major_id="A"),),
                chapters=(ChapterMetadata("chapter_0001", "A 장면", 0.0, 4.0, major_id="A", minor_code="A1"),),
                edit_decisions=(EditDecision("chapter_0001", "keep", safety="ideal", source_start=0.0, source_end=4.0),),
                edl_segments=(EDLSegment("/tmp/source.mp4", "chapter_0001", 0.0, 4.0, 0.0, 4.0),),
                guide_markdown="# guide",
                schema_version="roughcut_result.v2",
            )
            llm_candidate = widget._roughcut_state_payload()
            llm_candidate["candidate_id"] = "editor_post_generation_roughcut_draft"
            llm_candidate["name"] = "LLM 초안"
            llm_candidate["candidate_origin"] = "llm"

            local_candidate = dict(llm_candidate)
            local_candidate["candidate_id"] = "candidate_local"
            local_candidate["name"] = "로컬 초안"
            local_candidate["candidate_origin"] = "local"

            placeholder_candidate = dict(llm_candidate)
            placeholder_candidate["candidate_id"] = "cut_boundary_topicless"
            placeholder_candidate["name"] = "임시 후보"
            placeholder_candidate["candidate_origin"] = "placeholder"

            widget._roughcut_candidates = [local_candidate, llm_candidate, placeholder_candidate]
            widget._selected_candidate_id = "editor_post_generation_roughcut_draft"

            with patch.object(widget, "_current_editor_signature", return_value="sig-current"):
                widget._refresh_candidate_combo()
                self.assertEqual(len(widget._candidate_preview_buttons), 3)
                self.assertIn("실제 LLM", widget._candidate_preview_buttons[1].text())

                widget.candidate_preview_filter_combo.setCurrentIndex(1)
                self.assertEqual(widget._candidate_preview_filter, "llm")
                self.assertEqual(len(widget._candidate_preview_buttons), 1)
                self.assertIn("LLM 초안", widget._candidate_preview_buttons[0].text())
                self.assertIn("실제 LLM", widget._candidate_preview_buttons[0].text())
        finally:
            widget.close()

    def test_settings_dialog_collects_roughcut_llm_without_plain_api_keys(self):
        dialog = SettingsDialog({
            "selected_model": "base-model",
            "selected_llm_provider": "ollama",
            "editor_roughcut_draft_enabled": True,
            "editor_roughcut_draft_prompt": "editor roughcut draft prompt",
            "llm_threads": 5,
            "subtitle_quality_enabled": True,
            "review_auto_correct_apply_threshold": 94,
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "openai",
            "roughcut_llm_model": "gpt-roughcut",
            "roughcut_llm_prompt": "roughcut prompt",
            "roughcut_llm_threads": 3,
        })
        try:
            self.assertFalse(hasattr(dialog, "tabs"))
            labels = [label.text().replace("&", "") for label in dialog.findChildren(QLabel)]
            self.assertNotIn("Mode", labels)
            self.assertNotIn("Mode:", labels)
            self.assertIsNone(dialog.combo_stt_quality_preset.parent())
            self.assertEqual(dialog.combo_stt_quality_preset.currentData(), "auto")
            collected = dialog._collect_settings()
            self.assertTrue(collected["settings_simplified_ui_enabled"])
            self.assertTrue(collected["subtitle_bundle_autopilot_enabled"])
            self.assertEqual(collected["user_prompt"], "")
            self.assertFalse(hasattr(dialog, "chk_editor_roughcut_draft_enabled"))
            self.assertTrue(collected["editor_roughcut_draft_enabled"])
            self.assertEqual(collected["editor_roughcut_draft_prompt"], "")
            self.assertEqual(collected["llm_threads"], 5)
            self.assertTrue(collected["llm_threads_auto_enabled"])
            self.assertTrue(collected["llm_workers_auto_enabled"])
            self.assertFalse(collected["subtitle_quality_enabled"])
            self.assertEqual(collected["review_auto_correct_apply_threshold"], 94)
            self.assertFalse(collected["roughcut_llm_enabled"])
            self.assertFalse(collected["roughcut_llm_use_override"])
            self.assertEqual(collected["roughcut_llm_provider"], "none")
            self.assertEqual(collected["roughcut_llm_model"], "사용 안함")
            self.assertEqual(collected["roughcut_llm_prompt"], "")
            self.assertEqual(collected["roughcut_llm_threads"], 3)
            self.assertTrue(collected["roughcut_llm_threads_auto_enabled"])
            self.assertTrue(collected["roughcut_llm_rows_auto_enabled"])
            self.assertTrue(collected["roughcut_llm_rows_lora_enabled"])
            self.assertFalse(hasattr(dialog, "spin_roughcut_context_rows"))
            self.assertFalse(hasattr(dialog, "spin_roughcut_chunk_rows"))
            self.assertFalse(hasattr(dialog, "spin_roughcut_lookahead_rows"))
            self.assertNotIn("google_api_key", collected)
            self.assertNotIn("openai_api_key", collected)
            self.assertNotIn("huggingface_token", collected)
        finally:
            dialog.close()

    def test_collect_roughcut_llm_settings_enables_post_generation_autorun(self):
        dialog = SettingsDialog(
            {
                "selected_model": "base-model",
                "selected_llm_provider": "ollama",
                "editor_roughcut_draft_enabled": True,
            }
        )
        try:
            dialog.chk_roughcut_llm_enabled.setChecked(True)
            dialog.chk_roughcut_llm_override.setChecked(True)
            dialog._set_combo_data(dialog.combo_roughcut_llm_provider, "openai")
            dialog.input_roughcut_llm_model.setText("gpt-roughcut")

            collected = dialog._collect_roughcut_llm_settings()

            self.assertTrue(collected["roughcut_llm_enabled"])
            self.assertTrue(collected["roughcut_run_after_subtitle_generation"])
        finally:
            dialog.close()

    def test_collect_roughcut_llm_settings_disables_post_generation_autorun_when_llm_is_off(self):
        dialog = SettingsDialog(
            {
                "selected_model": "base-model",
                "selected_llm_provider": "ollama",
                "editor_roughcut_draft_enabled": True,
            }
        )
        try:
            dialog.chk_roughcut_llm_enabled.setChecked(False)
            dialog.chk_roughcut_llm_override.setChecked(False)
            dialog._set_combo_data(dialog.combo_roughcut_llm_provider, "none")
            dialog.input_roughcut_llm_model.setText("사용 안함")

            collected = dialog._collect_roughcut_llm_settings()

            self.assertFalse(collected["roughcut_llm_enabled"])
            self.assertFalse(collected["roughcut_run_after_subtitle_generation"])
        finally:
            dialog.close()

    def test_ai_tab_exposes_api_tokens_and_model_download_controls(self):
        dialog = SettingsDialog({})
        try:
            self.assertIsNotNone(dialog.findChild(QLineEdit, "GoogleApiKeyInput"))
            self.assertIsNotNone(dialog.findChild(QLineEdit, "OpenAiApiKeyInput"))
            self.assertIsNotNone(dialog.findChild(QLineEdit, "HuggingFaceTokenInput"))
            self.assertIsNotNone(dialog.findChild(QWidget, "AiModelDownloadPanel"))

            labels = {label.text() for label in dialog.findChildren(QLabel)}
            self.assertIn("Google API Key:", labels)
            self.assertIn("OpenAI API Key:", labels)
            self.assertIn("Hugging Face Token:", labels)
            self.assertIn("모델 관리:", labels)
            self.assertIn("설치 가능한 LLM:", labels)
            self.assertIn("필수/STT 모델:", labels)
            self.assertNotIn("STT1 Whisper 모델:", labels)
            self.assertNotIn("자막 품질 검사:", labels)
            self.assertNotIn("텍스트 LoRA 보조:", labels)
        finally:
            dialog.close()

    def test_settings_dialog_hides_manual_llm_thread_control(self):
        dialog = SettingsDialog({"llm_workers": 6})
        try:
            self.assertFalse(hasattr(dialog, "spin_editor_llm_threads"))
            collected = dialog._collect_settings()
            self.assertTrue(collected["llm_threads_auto_enabled"])
        finally:
            dialog.close()

    def test_auto_settings_mode_uses_same_quality_presets_and_syncs_auto_scopes(self):
        with patch(
            "ui.settings.settings_ai.load_path_settings",
            return_value={
                "auto_start_mode": "quality",
                "icloud_stt_quality_preset": "fast",
                "nas_stt_quality_preset": "balanced",
            },
        ), patch("ui.settings.settings_ai.save_path_settings") as save_mock:
            dialog = SettingsDialog({})
            try:
                labels = [dialog.combo_auto_start_mode.itemText(i) for i in range(dialog.combo_auto_start_mode.count())]
                values = [dialog.combo_auto_start_mode.itemData(i) for i in range(dialog.combo_auto_start_mode.count())]
                self.assertEqual(labels, ["Fast", "Auto", "High", "STT"])
                self.assertEqual(values, ["fast", "balanced", "precise", "stt"])
                self.assertEqual(dialog.combo_auto_start_mode.currentData(), "precise")

                self.assertFalse(hasattr(dialog, "combo_simple_operation_mode"))
                collected = dialog._collect_settings()

                self.assertEqual(collected["auto_start_mode"], "balanced")
                self.assertEqual(collected["simple_operation_mode"], "auto")
                self.assertFalse(collected["operation_mode_choices_visible"])
                saved = save_mock.call_args.args[0]
                self.assertEqual(saved["auto_start_mode"], "balanced")
                self.assertEqual(saved["icloud_stt_quality_preset"], "fast")
                self.assertEqual(saved["nas_stt_quality_preset"], "balanced")
            finally:
                dialog.close()

    def test_gap_dialog_hides_manual_sliders_behind_simple_mode(self):
        dialog = GapSettingsDialog({"settings_simplified_ui_enabled": True, "simple_operation_mode": "precise"})
        try:
            self.assertFalse(hasattr(dialog, "chk_show_manual_gap_settings"))
            self.assertFalse(dialog._manual_gap_scroll_area.isHidden())
            dialog._collect_data()
            self.assertIn("continuous_threshold", dialog.result)
            self.assertIn("split_length_threshold", dialog.result)
        finally:
            dialog.close()

    def test_fast_preset_disables_editor_roughcut_draft_option(self):
        dialog = SettingsDialog({"editor_roughcut_draft_enabled": True, "stt_quality_preset": "fast"})
        try:
            self.assertFalse(hasattr(dialog, "chk_editor_roughcut_draft_enabled"))
            collected = dialog._collect_settings()
            self.assertTrue(collected["editor_roughcut_draft_enabled"])
            self.assertEqual(collected["editor_roughcut_draft_prompt"], "")
        finally:
            dialog.close()

    def test_advanced_settings_no_longer_shows_llm_prompt_or_quality_tabs(self):
        dialog = AdvancedSettingsDialog({})
        try:
            tab_names = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
            self.assertIn("시스템", tab_names)
            self.assertNotIn("Silero", tab_names)
            self.assertNotIn("DeepFilter", tab_names)
            self.assertNotIn("Whisper", tab_names)
            self.assertNotIn("ffmpeg", tab_names)
            self.assertNotIn("LLM 프롬프트", tab_names)
            self.assertNotIn("자막 품질", tab_names)
            self.assertFalse(hasattr(dialog, "edit_user_prompt"))
            self.assertFalse(hasattr(dialog, "chk_subtitle_quality_enabled"))
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
