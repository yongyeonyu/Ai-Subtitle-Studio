# Version: 03.01.04
# Phase: PHASE2
"""Project sidebar shell widget."""

import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget

from ui.style import named_panel_style
from ui.gpu_rendering import scenegraph_enabled


class ProjectSidebarWidget(QWidget):
    """Left project sidebar container with shared panel styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectSidebarPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(204)
        self.setMaximumWidth(218)
        self.setStyleSheet(named_panel_style("ProjectSidebarPanel", "sidebar", radius=0))
        self._quick_shell = self._create_quick_shell()

    def _create_quick_shell(self):
        if not scenegraph_enabled("project"):
            return None
        qml_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "qml", "project_sidebar_shell.qml"))
        if not os.path.exists(qml_path):
            return None
        try:
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        try:
            shell = QQuickWidget(self)
            shell.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            shell.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            shell.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            shell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            shell.setClearColor(QColor(0, 0, 0, 0))
            shell.setSource(QUrl.fromLocalFile(qml_path))
            if shell.status() == QQuickWidget.Status.Error:
                shell.deleteLater()
                return None
            root = shell.rootObject()
            if root is not None:
                root.setProperty("panelTitle", "Project")
                root.setProperty("accentText", "QML SceneGraph")
            shell.setGeometry(self.rect())
            shell.show()
            shell.lower()
            return shell
        except Exception:
            return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        shell = getattr(self, "_quick_shell", None)
        if shell is not None:
            shell.setGeometry(self.rect())
            shell.lower()
