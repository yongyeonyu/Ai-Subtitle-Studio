# Version: 02.03.00
# Phase: PHASE1-B
"""
ui/settings_dialog.py
하위 호환용 re-export. 기존 코드의 import 경로를 유지합니다.
실제 구현은 각 파일에 있습니다:
  ui/settings_ai.py        → SettingsDialog        (⚙️ AI)
  ui/settings_advanced.py  → AdvancedSettingsDialog (🛠️ 상세설정)
  ui/settings_speaker.py   → SpeakerDialog          (🗣️ 화자)
  ui/settings_gap.py       → GapSettingsDialog       (⏱️ 간격)
  ui/settings_export.py    → ExportDialog            (📤 비디오)
  ui/settings_common.py    → 공통 상수/유틸
"""
from ui.settings.settings_ai       import SettingsDialog
from ui.settings.settings_advanced import AdvancedSettingsDialog
from ui.settings.settings_speaker  import SpeakerDialog
from ui.settings.settings_gap      import GapSettingsDialog
from ui.settings.settings_export   import ExportDialog

__all__ = [
    "SettingsDialog",
    "AdvancedSettingsDialog",
    "SpeakerDialog",
    "GapSettingsDialog",
    "ExportDialog",
]
