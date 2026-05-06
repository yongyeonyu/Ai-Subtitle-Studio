"""Stable editor render slots.

These frames keep the editor's major surfaces in predictable layout slots while
the child widgets change state during generation, playback, and post-processing.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QWidget

from ui.gpu_rendering import gpu_backend_name, gpu_runtime_enabled, gpu_widgets_enabled


class StableRenderFrame(QFrame):
    """A fixed-role container that owns one major editor surface."""

    def __init__(
        self,
        object_name: str,
        *,
        render_feature: str,
        min_width: int = 1,
        min_height: int = 1,
        parent: QWidget | None = None,
        fixed_height: bool = False,
    ):
        super().__init__(parent)
        self._stable_size = QSize(max(1, int(min_width)), max(1, int(min_height)))
        self._fixed_height = bool(fixed_height)
        self.render_feature = str(render_feature or "general").strip().lower() or "general"
        self.setObjectName(str(object_name or "StableRenderFrame"))
        self.setProperty("renderFeature", self.render_feature)
        self.refresh_render_policy()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(self._stable_size)
        vertical_policy = QSizePolicy.Policy.Fixed if self._fixed_height else QSizePolicy.Policy.Expanding
        self.setSizePolicy(QSizePolicy.Policy.Expanding, vertical_policy)
        if self._fixed_height:
            self.setFixedHeight(self._stable_size.height())

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

    def refresh_render_policy(self) -> None:
        self.setProperty("renderBackend", gpu_backend_name(self.render_feature))
        self.setProperty("renderRuntimeGpuEnabled", gpu_runtime_enabled(self.render_feature))
        self.setProperty("renderOpenGLWidgetsEnabled", gpu_widgets_enabled(self.render_feature))

    def add_content(self, widget: QWidget, *, stretch: int = 1) -> QWidget:
        widget.setParent(self)
        self.content_layout.addWidget(widget, stretch=max(0, int(stretch)))
        return widget

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(
            max(self._stable_size.width(), hint.width()),
            max(self._stable_size.height(), hint.height()),
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(self._stable_size)


__all__ = ["StableRenderFrame"]
