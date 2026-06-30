from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView


class RoughcutStoryboardView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, owner):
        super().__init__(scene)
        self._owner = owner
        self._drag_node_id = ""
        self._drag_offset = QPointF()
        self._drag_press_scene_pos = QPointF()
        self._drag_started = False
        self._connect_source_node = 0
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
                    self._drag_press_scene_pos = QPointF(scene_pos)
                    self._drag_started = True
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
                self._owner._connect_material_preview_nodes(self._connect_source_node, pin_node)
                self._connect_source_node = 0
                self._owner._clear_material_preview_routing_mode()
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                event.accept()
                return
            if pin_node and pin_side == "right":
                self._connect_source_node = pin_node
                self._owner._set_material_preview_connect_source(pin_node)
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
        pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
        if pin_node and pin_side == "right":
            self._connect_source_node = pin_node
            self._owner._set_material_preview_connect_source(pin_node)
            self._owner._set_material_preview_connect_cursor(scene_pos)
            self._owner._set_material_preview_hover_pin(pin_node, pin_side)
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
        self._drag_press_scene_pos = QPointF(scene_pos)
        self._drag_started = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._connect_source_node:
            self._owner._set_material_preview_connect_cursor(scene_pos)
            pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
            if pin_side != "left":
                pin_node, pin_side = 0, ""
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
        if not self._drag_started:
            if (scene_pos - self._drag_press_scene_pos).manhattanLength() < 6:
                event.accept()
                return
            self._drag_started = True
            self._owner._begin_material_preview_node_drag(self._drag_node_id)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._owner._drag_material_preview_node_to(self._drag_node_id, scene_pos - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt override
        if self._connect_source_node:
            source = self._connect_source_node
            scene_pos = self.mapToScene(event.position().toPoint())
            target, target_side = self._owner._material_preview_pin_at_scene_pos(scene_pos)
            if target and target_side == "left":
                self._owner._connect_material_preview_nodes(source, target)
                self._connect_source_node = 0
                self._owner._clear_material_preview_routing_mode()
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
        drag_started = self._drag_started
        self._drag_node_id = ""
        self._drag_offset = QPointF()
        self._drag_press_scene_pos = QPointF()
        self._drag_started = False
        if drag_started:
            self._owner._finish_material_preview_node_drag(node_id, scene_pos)
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


__all__ = ["RoughcutStoryboardView"]
