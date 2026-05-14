import unittest
from unittest.mock import patch

from ui.editor.editor_pipeline_safety import EditorPipelineSafetyMixin


class _Safety(EditorPipelineSafetyMixin):
    def __init__(self, should_fail=False):
        self._should_fail = should_fail
        self.value = None

    def window(self):
        if self._should_fail:
            raise RuntimeError("gone")
        return self


class _Timer:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.stopped = False

    def stop(self):
        if self.should_fail:
            raise RuntimeError("stop failed")
        self.stopped = True


class EditorPipelineSafetyTests(unittest.TestCase):
    def test_pipeline_window_returns_none_on_runtime_error(self):
        self.assertIsNone(_Safety(should_fail=True)._pipeline_window())

    def test_pipeline_best_effort_returns_default_and_logs(self):
        helper = _Safety()
        with patch("ui.editor.editor_pipeline_safety.get_logger") as logger:
            result = helper._pipeline_best_effort(lambda: (_ for _ in ()).throw(ValueError("boom")), label="테스트", default=7)
        self.assertEqual(result, 7)
        logger().log.assert_called_once()

    def test_pipeline_helpers_mutate_timer_collection_and_attrs(self):
        helper = _Safety()
        helper.items = [1, 2]
        timer = _Timer()

        self.assertTrue(helper._pipeline_stop_timer(timer, label="timer"))
        self.assertTrue(timer.stopped)
        self.assertTrue(helper._pipeline_clear_attr("items", label="items"))
        self.assertEqual(helper.items, [])
        self.assertTrue(helper._pipeline_set_attr("value", 3, label="value"))
        self.assertEqual(helper.value, 3)


if __name__ == "__main__":
    unittest.main()
