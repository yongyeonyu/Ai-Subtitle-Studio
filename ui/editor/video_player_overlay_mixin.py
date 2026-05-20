from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF


class VideoPlayerOverlayMixin:
    """Subtitle/video overlay layout and paint ownership for the player widget."""

    def _displayed_video_rect(self, bounds):
        aspect = max(0.01, float(getattr(self, "_display_aspect", 16 / 9) or (16 / 9)))
        bw = max(1, int(bounds.width()))
        bh = max(1, int(bounds.height()))
        box_aspect = bw / max(1, bh)
        if box_aspect > aspect:
            target_h = bh
            target_w = int(round(target_h * aspect))
            x = int((bw - target_w) / 2)
            y = 0
        else:
            target_w = bw
            target_h = int(round(target_w / aspect))
            x = 0
            y = 0
        return QRectF(x, y, max(1, target_w), max(1, target_h)).toRect()

    def _source_video_rect(self, bounds):
        aspect = max(0.01, float(getattr(self, "_source_aspect", 16 / 9) or (16 / 9)))
        bw = max(1, int(bounds.width()))
        bh = max(1, int(bounds.height()))
        box_aspect = bw / max(1, bh)
        if box_aspect > aspect:
            h = bh
            w = int(h * aspect)
            x = int((bw - w) / 2)
            y = 0
        else:
            w = bw
            h = int(w / aspect)
            x = 0
            y = 0
        return QRectF(x, y, max(1, w), max(1, h)).toRect()

    def _scene_subtitle_item(self):
        return getattr(getattr(self, "video_widget", None), "subtitle_item", None)

    def _subtitle_overlay_parent(self):
        item = self._scene_subtitle_item()
        if item is not None:
            return self.video_container
        return getattr(self, "video_widget", None) or self.video_container

    def _map_overlay_rect_to_parent(self, rect, parent):
        if parent is None or parent is self.video_container:
            return rect
        try:
            top_left = parent.mapFrom(self.video_container, rect.topLeft())
            return QRect(top_left, rect.size())
        except Exception:
            try:
                return parent.rect()
            except Exception:
                return rect

    def _set_overlay_widget_geometry(self, widget, parent, rect):
        if widget is None:
            return False
        changed = False
        try:
            if widget.parentWidget() is not parent:
                widget.setParent(parent)
                changed = True
        except Exception:
            return False
        try:
            if widget.geometry() != rect:
                widget.setGeometry(rect)
                changed = True
        except Exception:
            return False
        return changed

    def _layout_video_overlay(self):
        if not hasattr(self, "video_container"):
            return
        rect = self.video_container.rect()
        self.video_stack.setGeometry(rect)
        video_rect = self._displayed_video_rect(rect)
        overlay_parent = self._subtitle_overlay_parent()
        overlay_rect = self._map_overlay_rect_to_parent(video_rect, overlay_parent)
        try:
            self._set_overlay_widget_geometry(self.sub_label, overlay_parent, overlay_rect)
        except Exception:
            self._set_overlay_widget_geometry(self.sub_label, self.video_container, rect)
        self.sub_label.raise_()
        quick_overlay = getattr(self, "quick_subtitle_overlay", None)
        if quick_overlay is not None:
            try:
                self._set_overlay_widget_geometry(quick_overlay, overlay_parent, overlay_rect)
                quick_overlay.raise_()
            except Exception:
                pass
        item = self._scene_subtitle_item()
        if item is not None:
            item.set_rect(QRectF(video_rect))
        try:
            self.video_widget.set_video_display_rect(QRectF(video_rect))
        except Exception:
            pass

    def _set_subtitle_overlay_text(self, text: str):
        text = str(text or "")
        quick_overlay = getattr(self, "quick_subtitle_overlay", None)
        try:
            if self.sub_label.text() != text:
                self.sub_label.setText(text)
            self.sub_label.setVisible(bool(text) and quick_overlay is None)
            if text and quick_overlay is None:
                self.sub_label.raise_()
        except Exception:
            pass
        item = self._scene_subtitle_item()
        # macOS video surfaces can composite above QGraphicsScene items, so the QWidget label is the visible fallback.
        if item is not None:
            item.set_text("")
        if quick_overlay is not None:
            quick_overlay.set_text(text)
        elif item is None and hasattr(self, "sub_label"):
            try:
                self.sub_label.setVisible(bool(text))
                self.sub_label.raise_()
            except Exception:
                pass

    def _set_subtitle_overlay_style(self, style: dict | None):
        try:
            self.sub_label.set_export_style(style or {})
        except Exception:
            pass
        quick_overlay = getattr(self, "quick_subtitle_overlay", None)
        item = self._scene_subtitle_item()
        if item is not None and quick_overlay is None:
            item.set_export_style(style or {})
        if quick_overlay is not None:
            quick_overlay.set_export_style(style or {})
