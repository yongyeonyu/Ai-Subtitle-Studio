import unittest
from unittest.mock import patch

from PyQt6.QtCore import QPoint

from ui.editor.editor_speaker_ops import EditorSpeakerOpsMixin


class _SpeakerMenuHarness(EditorSpeakerOpsMixin):
    def __init__(self):
        self.settings = {
            "spk1_id": "00",
            "spk1_name": "진행자",
            "spk2_id": "01",
            "spk2_name": "직원",
            "spk2_enabled": True,
        }
        self.changed: list[tuple[int, str]] = []

    def _change_speaker_for_line(self, line_num: int, new_spk_id: str):
        self.changed.append((line_num, new_spk_id))


class EditorSpeakerOpsTests(unittest.TestCase):
    @patch(
        "ui.editor.editor_speaker_ops.current_speaker_settings",
        return_value={
            "spk1_id": "00",
            "spk1_name": "진행자",
            "spk2_id": "01",
            "spk2_name": "직원",
            "spk2_enabled": True,
        },
    )
    @patch(
        "ui.editor.editor_speaker_ops.visible_speaker_slots",
        return_value=[
            {"id": "00", "name": "진행자", "color": "#FFFFFF"},
            {"id": "01", "name": "직원", "color": "#FFD60A"},
            {"id": "02", "name": "손님", "color": "#00FFFF"},
        ],
    )
    @patch("ui.editor.editor_speaker_ops.show_context_menu", return_value=None)
    def test_menu_normalizes_internal_speaker_prefix_and_hides_current_speaker(
        self,
        show_menu,
        _visible_slots,
        _current_settings,
    ):
        harness = _SpeakerMenuHarness()

        harness._show_speaker_circle_menu(7, "SPEAKER_00", QPoint(0, 0))

        _owner, _pos, items = show_menu.call_args.args
        self.assertEqual([item["id"] for item in items], ["01", "02"])


if __name__ == "__main__":
    unittest.main()
