import os
import tempfile
import sys
from core.subtitle_existing import find_media_for_srt
from core.personalization.ground_truth_import import MEDIA_EXTENSIONS
from ui.project.multiclip_panel import MEDIA_FILTER
from ui.project.project_panel import PROJECT_MEDIA_FILTER

def test_lrf_extensions_in_constants():
    # Verify constants contain .lrf and .LRF
    assert ".lrf" in MEDIA_EXTENSIONS
    assert "*.lrf" in MEDIA_FILTER
    assert "*.LRF" in MEDIA_FILTER
    assert "*.lrf" in PROJECT_MEDIA_FILTER
    assert "*.LRF" in PROJECT_MEDIA_FILTER

def test_find_media_for_srt_supports_lrf():
    with tempfile.TemporaryDirectory() as tmpdir:
        srt_path = os.path.join(tmpdir, "video.srt")
        lrf_path = os.path.join(tmpdir, "video.lrf")

        # Test lowercase .lrf
        with open(srt_path, "w") as f:
            f.write("")
        with open(lrf_path, "w") as f:
            f.write("")

        found = find_media_for_srt(srt_path)
        assert found.lower() == lrf_path.lower()
        assert os.path.exists(found)

def test_folder_dialog_placeholder_thumbnail():
    from PyQt6.QtWidgets import QApplication, QTreeWidgetItem
    from ui.dialogs.folder_dialog import FolderDialog

    # Initialize QApplication if not already running
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    dialog = FolderDialog("/tmp")
    item = QTreeWidgetItem()

    # Check lowercase .lrf
    dialog._set_placeholder_thumbnail(item, "test.lrf")
    assert item.text(dialog.thumb_col) == "🎞"

    # Check uppercase .LRF
    dialog._set_placeholder_thumbnail(item, "test.LRF")
    assert item.text(dialog.thumb_col) == "🎞"
