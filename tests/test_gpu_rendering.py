# Version: 03.14.31
# Phase: PHASE2
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class GpuRenderingSafetyTests(unittest.TestCase):
    def test_phase3_qml_migration_assets_exist(self):
        root = Path(__file__).resolve().parents[1]
        required = {
            "ui/editor/subtitle_text_editor.qml": ("locked", "visibleLines", "contentLeft"),
            "ui/editor/video_subtitle_overlay.qml": ("subtitleText", "styleData", "fontPx"),
            "ui/qml/app_action_bar.qml": ("actions", "actionTriggered", "compact"),
            "ui/qml/app_tab_bar.qml": ("tabItems", "currentIndex", "tabTriggered"),
            "ui/qml/home_sidebar_nav.qml": ("menuItems", "actionTriggered", "badge"),
            "ui/qml/project_sidebar_shell.qml": ("panelTitle", "accentText"),
            "ui/qml/settings_panel_header.qml": ("titleText", "subtitleText", "badgeText"),
        }
        for rel_path, markers in required.items():
            qml_path = root / rel_path
            self.assertTrue(qml_path.exists(), rel_path)
            text = qml_path.read_text(encoding="utf-8")
            for marker in markers:
                self.assertIn(marker, text)

    def test_opengl_widgets_are_default_off(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(gpu_widgets_enabled())
            self.assertEqual(gpu_backend_name(), "qwidget")
            self.assertFalse(gpu_widgets_enabled("timeline"))
            self.assertEqual(gpu_backend_name("timeline"), "qwidget")

    def test_real_app_defaults_enable_all_ui_gpu(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_runtime_enabled, gpu_widgets_enabled, scenegraph_enabled
        from core.runtime import config

        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.gpu_rendering._running_under_pytest", return_value=False):
            self.assertTrue(gpu_runtime_enabled())
            if config.IS_MAC:
                self.assertFalse(gpu_widgets_enabled())
                self.assertTrue(scenegraph_enabled("timeline"))
                self.assertEqual(gpu_backend_name("timeline"), "metal-scenegraph")
            else:
                self.assertTrue(gpu_widgets_enabled())
                self.assertEqual(gpu_backend_name(), "opengl-widget")
                self.assertTrue(gpu_widgets_enabled("video"))
                self.assertEqual(gpu_backend_name("video"), "opengl-widget")

    def test_opengl_widgets_require_explicit_opt_in(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled
        from core.runtime import config

        with patch.dict(
            os.environ,
            {
                "AI_SUBTITLE_GPU_RENDERING": "1",
                "AI_SUBTITLE_EXPERIMENTAL_OPENGL_WIDGETS": "1",
            },
            clear=True,
        ):
            if config.IS_MAC:
                self.assertFalse(gpu_widgets_enabled())
                self.assertEqual(gpu_backend_name("timeline"), "qwidget")
            else:
                self.assertTrue(gpu_widgets_enabled())
                self.assertEqual(gpu_backend_name(), "opengl-widget")

    def test_settings_can_enable_gpu_by_frame(self):
        from ui.gpu_rendering import gpu_runtime_enabled, gpu_widgets_enabled, scenegraph_enabled
        from core.runtime import config

        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.gpu_rendering._running_under_pytest", return_value=False), \
             patch(
                 "ui.gpu_rendering._render_settings",
                 return_value={
                     "editor_rendering_gpu_scope": "frame",
                     "editor_rendering_gpu_frames": ["timeline"],
                 },
             ):
            self.assertTrue(gpu_runtime_enabled("timeline"))
            if config.IS_MAC:
                self.assertFalse(gpu_widgets_enabled("timeline"))
                self.assertTrue(scenegraph_enabled("timeline"))
            else:
                self.assertTrue(gpu_widgets_enabled("timeline"))
            self.assertFalse(gpu_runtime_enabled("editor"))

    def test_settings_can_enable_gpu_for_all_frames_without_opengl_widgets(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_runtime_enabled, gpu_widgets_enabled

        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.gpu_rendering._running_under_pytest", return_value=False), \
             patch(
                 "ui.gpu_rendering._render_settings",
                 return_value={
                     "editor_rendering_gpu_scope": "all",
                     "editor_rendering_opengl_widgets_enabled": False,
                 },
            ):
            self.assertTrue(gpu_runtime_enabled("editor"))
            self.assertTrue(gpu_runtime_enabled("video"))
            self.assertFalse(gpu_widgets_enabled("editor"))
            self.assertTrue(gpu_backend_name("timeline").endswith("-scenegraph"))

    def test_timeline_widgets_use_explicit_gpu_rendering_without_global_experimental_flag(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled

        with patch.dict(
            os.environ,
            {
                "AI_SUBTITLE_GPU_RENDERING": "1",
                "AI_SUBTITLE_TIMELINE_GPU_RENDERING": "1",
                "AI_SUBTITLE_OPENGL_WIDGETS": "0",
            },
            clear=True,
        ):
            self.assertFalse(gpu_widgets_enabled())
            self.assertFalse(gpu_widgets_enabled("timeline"))
            self.assertEqual(gpu_backend_name("timeline"), "qwidget")

    def test_general_gpu_widgets_are_enabled_when_runtime_is_explicit(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled
        from core.runtime import config

        with patch.dict(os.environ, {"AI_SUBTITLE_GPU_RENDERING": "1"}, clear=True):
            if config.IS_MAC:
                self.assertFalse(gpu_widgets_enabled())
            else:
                self.assertTrue(gpu_widgets_enabled())
                self.assertEqual(gpu_backend_name(), "opengl-widget")

    def test_timeline_gpu_rendering_can_be_disabled_explicitly(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled

        with patch.dict(os.environ, {"AI_SUBTITLE_TIMELINE_GPU_RENDERING": "0"}, clear=True):
            self.assertFalse(gpu_widgets_enabled("timeline"))
            self.assertEqual(gpu_backend_name("timeline"), "qwidget")

    def test_timeline_gpu_rendering_is_test_safe_unless_explicit(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled
        from core.runtime import config

        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "tests/test_ui.py::test"}, clear=True):
            self.assertFalse(gpu_widgets_enabled("timeline"))
            self.assertEqual(gpu_backend_name("timeline"), "qwidget")
        with patch.dict(
            os.environ,
            {
                "PYTEST_CURRENT_TEST": "tests/test_ui.py::test",
                "AI_SUBTITLE_TIMELINE_GPU_RENDERING": "1",
            },
            clear=True,
        ):
            if config.IS_MAC:
                self.assertFalse(gpu_widgets_enabled("timeline"))
                self.assertEqual(gpu_backend_name("timeline"), "qwidget")
            else:
                self.assertTrue(gpu_widgets_enabled("timeline"))
                self.assertEqual(gpu_backend_name("timeline"), "opengl-widget")

    def test_metal_backend_disables_opengl_widgets_but_keeps_scenegraph(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled, scenegraph_enabled

        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.gpu_rendering._running_under_pytest", return_value=False), \
             patch("ui.gpu_rendering._qt_gpu_backend", return_value="metal"), \
             patch(
                 "ui.gpu_rendering._render_settings",
                 return_value={
                     "editor_rendering_gpu_scope": "all",
                     "editor_rendering_opengl_widgets_enabled": True,
                     "editor_rendering_scenegraph_enabled": True,
                 },
             ):
            self.assertFalse(gpu_widgets_enabled("timeline"))
            self.assertTrue(scenegraph_enabled("timeline"))
            self.assertEqual(gpu_backend_name("timeline"), "metal-scenegraph")

    def test_opengl_partial_update_defaults_on(self):
        from ui.gpu_rendering import opengl_partial_update_enabled

        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(opengl_partial_update_enabled("timeline"))
        with patch.dict(os.environ, {"AI_SUBTITLE_TIMELINE_OPENGL_PARTIAL_UPDATE": "0"}, clear=True):
            self.assertFalse(opengl_partial_update_enabled("timeline"))

    def test_scenegraph_requires_gpu_runtime_and_is_test_safe(self):
        from ui.gpu_rendering import scenegraph_enabled

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(scenegraph_enabled("timeline"))
        with patch.dict(
            os.environ,
            {
                "AI_SUBTITLE_TIMELINE_GPU_RENDERING": "1",
                "AI_SUBTITLE_TIMELINE_SCENEGRAPH": "1",
            },
            clear=True,
        ):
            self.assertTrue(scenegraph_enabled("timeline"))

    def test_scenegraph_can_follow_settings_when_gpu_runtime_uses_qwidget_canvas(self):
        from ui.gpu_rendering import scenegraph_enabled

        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.gpu_rendering._running_under_pytest", return_value=False), \
             patch(
                 "ui.gpu_rendering._render_settings",
                 return_value={
                     "editor_rendering_gpu_scope": "all",
                     "editor_rendering_opengl_widgets_enabled": False,
                 },
             ):
            self.assertTrue(scenegraph_enabled("timeline"))

    def test_scenegraph_can_be_disabled_explicitly_in_settings(self):
        from ui.gpu_rendering import scenegraph_enabled

        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.gpu_rendering._running_under_pytest", return_value=False), \
             patch(
                 "ui.gpu_rendering._render_settings",
                 return_value={
                     "editor_rendering_gpu_scope": "all",
                     "editor_rendering_opengl_widgets_enabled": False,
                     "editor_rendering_scenegraph_enabled": False,
                 },
             ):
            self.assertFalse(scenegraph_enabled("timeline"))

    def test_opengl_widgets_disabled_offscreen_even_when_requested(self):
        from ui.gpu_rendering import gpu_widgets_enabled

        with patch.dict(
            os.environ,
            {
                "QT_QPA_PLATFORM": "offscreen",
                "AI_SUBTITLE_GPU_RENDERING": "1",
                "AI_SUBTITLE_EXPERIMENTAL_OPENGL_WIDGETS": "1",
            },
            clear=True,
        ):
            self.assertFalse(gpu_widgets_enabled())

    def test_qt_global_opengl_setup_follows_all_ui_gpu_defaults(self):
        from core.performance import configure_qt_gpu_rendering_before_app
        from core.runtime import config

        with patch.dict(os.environ, {}, clear=True):
            configure_qt_gpu_rendering_before_app()
            if config.IS_MAC:
                self.assertIsNone(os.environ.get("QT_OPENGL"))
                self.assertEqual(os.environ.get("QSG_RHI_BACKEND"), "metal")
                self.assertIsNone(os.environ.get("QT_QUICK_BACKEND"))
            else:
                self.assertIsNone(os.environ.get("QT_OPENGL"))
                self.assertIsNone(os.environ.get("QSG_RHI_BACKEND"))

    def test_qt_global_opengl_setup_requires_explicit_opt_in(self):
        from core.performance import configure_qt_gpu_rendering_before_app

        with patch.dict(
            os.environ,
            {
                "AI_SUBTITLE_GPU_RENDERING": "1",
                "AI_SUBTITLE_FORCE_QT_OPENGL": "1",
            },
            clear=True,
        ):
            configure_qt_gpu_rendering_before_app()
            self.assertEqual(os.environ.get("QT_OPENGL"), "desktop")
            self.assertEqual(os.environ.get("QSG_RHI_BACKEND"), "opengl")

    def test_qt_global_opengl_setup_can_use_all_frame_settings(self):
        from core.performance import configure_qt_gpu_rendering_before_app
        from core.runtime import config

        with patch.dict(os.environ, {}, clear=True), \
             patch("core.performance._qt_gpu_rendering_settings_request", return_value=(True, False, "auto")):
            configure_qt_gpu_rendering_before_app()
            if config.IS_MAC:
                self.assertIsNone(os.environ.get("QT_OPENGL"))
                self.assertEqual(os.environ.get("QSG_RHI_BACKEND"), "metal")
                self.assertIsNone(os.environ.get("QT_QUICK_BACKEND"))
            else:
                self.assertIsNone(os.environ.get("QT_OPENGL"))
                self.assertIsNone(os.environ.get("QSG_RHI_BACKEND"))

    def test_qt_global_gpu_backend_can_force_metal_on_mac(self):
        from core.performance import configure_qt_gpu_rendering_before_app

        with patch.dict(os.environ, {}, clear=True), \
             patch("core.performance.platform.system", return_value="Darwin"), \
             patch("core.performance._qt_gpu_rendering_settings_request", return_value=(True, False, "metal")):
            configure_qt_gpu_rendering_before_app()
            self.assertIsNone(os.environ.get("QT_OPENGL"))
            self.assertEqual(os.environ.get("QSG_RHI_BACKEND"), "metal")
            self.assertIsNone(os.environ.get("QT_QUICK_BACKEND"))

    def test_qt_global_gpu_backend_clears_legacy_hardware_quick_backend(self):
        from core.performance import configure_qt_gpu_rendering_before_app

        with patch.dict(
            os.environ,
            {
                "AI_SUBTITLE_GPU_RENDERING": "1",
                "QSG_RHI_BACKEND": "metal",
                "QT_QUICK_BACKEND": "hardware",
            },
            clear=True,
        ), \
             patch("core.performance.platform.system", return_value="Darwin"), \
             patch("core.performance._qt_gpu_rendering_settings_request", return_value=(True, False, "metal")):
            configure_qt_gpu_rendering_before_app()
            self.assertEqual(os.environ.get("QSG_RHI_BACKEND"), "metal")
            self.assertIsNone(os.environ.get("QT_QUICK_BACKEND"))

    def test_mac_editor_text_surface_is_gpu_safe_by_default(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled, scenegraph_enabled

        with patch.dict(os.environ, {}, clear=True), \
             patch("ui.gpu_rendering._running_under_pytest", return_value=False), \
             patch("ui.gpu_rendering.config.IS_MAC", True):
            self.assertFalse(gpu_widgets_enabled("editor"))
            self.assertTrue(scenegraph_enabled("editor"))
            self.assertEqual(gpu_backend_name("editor"), "metal-scenegraph")
            self.assertFalse(gpu_widgets_enabled("video"))
            self.assertEqual(gpu_backend_name("video"), "metal-scenegraph")


if __name__ == "__main__":
    unittest.main()
