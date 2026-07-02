from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QKeySequence, QTransform
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView


class RoughcutCanvasView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, owner=None, canvas_name: str = "canvas"):
        super().__init__(scene)
        self._owner = owner
        self._canvas_name = canvas_name
        self._canvas_zoom = 1.0
        self._canvas_min_zoom = 0.4
        self._canvas_max_zoom = 2.5
        self._space_pan_active = False
        self._canvas_panning = False
        self._canvas_pan_last_pos = QPoint()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    @property
    def canvas_zoom(self) -> float:
        return self._canvas_zoom

    def set_canvas_zoom(self, zoom: float) -> None:
        clamped = max(self._canvas_min_zoom, min(self._canvas_max_zoom, float(zoom)))
        if abs(clamped - self._canvas_zoom) < 0.0001:
            return
        self._canvas_zoom = clamped
        transform = QTransform()
        transform.scale(clamped, clamped)
        self.setTransform(transform)
        callback = getattr(self._owner, "_on_roughcut_canvas_zoom_changed", None)
        if callable(callback):
            callback(self._canvas_name, clamped)

    def zoom_in(self) -> None:
        self.set_canvas_zoom(self._canvas_zoom * 1.15)

    def zoom_out(self) -> None:
        self.set_canvas_zoom(self._canvas_zoom / 1.15)

    def reset_zoom(self) -> None:
        self.set_canvas_zoom(1.0)

    def fit_canvas(self) -> None:
        scene_rect = self.sceneRect()
        if scene_rect.isNull() or scene_rect.width() <= 0 or scene_rect.height() <= 0:
            self.reset_zoom()
            return
        previous_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)
        zoom = float(self.transform().m11())
        clamped = max(self._canvas_min_zoom, min(self._canvas_max_zoom, zoom))
        if abs(zoom - clamped) > 0.0001:
            transform = QTransform()
            transform.scale(clamped, clamped)
            self.setTransform(transform)
        self._canvas_zoom = clamped
        callback = getattr(self._owner, "_on_roughcut_canvas_zoom_changed", None)
        if callable(callback):
            callback(self._canvas_name, self._canvas_zoom)
        self.setTransformationAnchor(previous_anchor)

    def wheelEvent(self, event):  # noqa: N802 - Qt override
        modifiers = event.modifiers()
        if (
            modifiers & Qt.KeyboardModifier.MetaModifier
            or modifiers & Qt.KeyboardModifier.ControlModifier
        ):
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta:
                self.set_canvas_zoom(self._canvas_zoom * (1.12 if delta > 0 else 1 / 1.12))
                event.accept()
                return
        super().wheelEvent(event)

    def _begin_canvas_pan_from_event(self, event) -> bool:
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_pan_active
        ):
            self._canvas_panning = True
            self._canvas_pan_last_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return True
        return False

    def _continue_canvas_pan_from_event(self, event) -> bool:
        if not self._canvas_panning:
            return False
        current_pos = event.position().toPoint()
        delta = current_pos - self._canvas_pan_last_pos
        self._canvas_pan_last_pos = current_pos
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        event.accept()
        return True

    def _end_canvas_pan_from_event(self, event) -> bool:
        if not self._canvas_panning:
            return False
        self._canvas_panning = False
        self._canvas_pan_last_pos = QPoint()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        event.accept()
        return True

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        if self._begin_canvas_pan_from_event(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        if self._continue_canvas_pan_from_event(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt override
        if self._end_canvas_pan_from_event(event):
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan_active = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pan_active = False
            if not self._canvas_panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)


class RoughcutStoryboardView(RoughcutCanvasView):
    def __init__(self, scene: QGraphicsScene, owner):
        super().__init__(scene, owner, "material")
        self._drag_node_id = ""
        self._drag_offset = QPointF()
        self._drag_press_scene_pos = QPointF()
        self._drag_started = False
        self._drag_insert_shift = False
        self._connect_source_node = 0
        self._connect_source_side = "right"
        self._connect_started_on_press = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        if self._begin_canvas_pan_from_event(event):
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MouseButton.RightButton:
            source, target = self._owner._material_preview_connection_at_scene_pos(scene_pos)
            if source and target:
                self._owner._delete_material_preview_connection(source, target)
                if self._connect_source_node:
                    self._connect_source_node = 0
                    self._owner._clear_material_preview_routing_mode(refresh=False)
                event.accept()
                return
            if self._connect_source_node:
                self._connect_source_node = 0
                self._owner._clear_material_preview_routing_mode()
                self.setCursor(Qt.CursorShape.OpenHandCursor)
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
        story_row = self._owner._material_preview_story_plus_at_scene_pos(scene_pos)
        if story_row is not None:
            self._owner._create_material_preview_story_card(story_row)
            event.accept()
            return
        if self._connect_source_node:
            pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos, magnet=True)
            if pin_node and pin_side == "left" and not (
                pin_node == self._connect_source_node and pin_side == self._connect_source_side
            ):
                self._owner._connect_material_preview_nodes(
                    self._connect_source_node,
                    pin_node,
                    source_side=self._connect_source_side,
                    target_side=pin_side,
                    clear_routing_before_refresh=True,
                )
                self._connect_source_node = 0
                self._connect_source_side = "right"
                self._connect_started_on_press = False
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
            self._connect_source_node = 0
            self._connect_source_side = "right"
            self._connect_started_on_press = False
            self._owner._clear_material_preview_routing_mode()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
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
        self._drag_press_scene_pos = QPointF(scene_pos)
        self._drag_started = False
        self._drag_insert_shift = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        if self._continue_canvas_pan_from_event(event):
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._connect_source_node:
            pin_node, pin_side = self._owner._material_preview_pin_at_scene_pos(scene_pos, magnet=True)
            if pin_side != "left":
                pin_node, pin_side = 0, ""
            cursor_pos = self._owner._material_preview_pin_position(pin_node, pin_side) if pin_node else scene_pos
            self._owner._set_material_preview_connect_cursor(cursor_pos)
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
        if self._end_canvas_pan_from_event(event):
            return
        if self._connect_source_node:
            source = self._connect_source_node
            scene_pos = self.mapToScene(event.position().toPoint())
            target, target_side = self._owner._material_preview_pin_at_scene_pos(scene_pos, magnet=True)
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
        drag_started = self._drag_started
        insert_shift = self._drag_insert_shift
        self._drag_node_id = ""
        self._drag_offset = QPointF()
        self._drag_press_scene_pos = QPointF()
        self._drag_started = False
        self._drag_insert_shift = False
        if drag_started:
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


__all__ = ["RoughcutCanvasView", "RoughcutStoryboardView"]
