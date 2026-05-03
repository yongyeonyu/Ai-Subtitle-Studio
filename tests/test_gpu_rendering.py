# Version: 03.07.01
# Phase: PHASE2
import os
import unittest
from unittest.mock import patch


class GpuRenderingSafetyTests(unittest.TestCase):
    def test_opengl_widgets_are_default_on(self):
        from ui.gpu_rendering import gpu_backend_name, gpu_widgets_enabled

        with patch.dict(os.environ, {"AI_SUBTITLE_GPU_RENDERING": "1"}, clear=True):
            self.assertTrue(gpu_widgets_enabled())
            self.assertEqual(gpu_backend_name(), "opengl-widget")

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

    def test_qt_global_opengl_setup_is_default_on(self):
        from core.performance import configure_qt_gpu_rendering_before_app

        with patch.dict(os.environ, {"AI_SUBTITLE_GPU_RENDERING": "1"}, clear=True):
            configure_qt_gpu_rendering_before_app()
            self.assertEqual(os.environ.get("QT_OPENGL"), "desktop")
            self.assertEqual(os.environ.get("QSG_RHI_BACKEND"), "opengl")


if __name__ == "__main__":
    unittest.main()
