# Version: 03.14.13
# Phase: PHASE1-B
"""
ui/project/multiclip_panel.py
Multi-clip sorting editor
"""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from core.runtime import config
from core.path_manager import get_last_folder
from core.settings import load_settings, save_settings
from core.audio.stt_quality_presets import (
    STT_QUALITY_PRESET_ORDER,
    apply_stt_quality_preset,
    load_stt_quality_presets,
    normalize_stt_quality_key,
    stt_quality_label,
)
from ui.project.multiclip_cards import AddCard, ClipCard, ClipContainer


MEDIA_FILTER = "Media Files (*.mp4 *.mov *.MOV *.MP4 *.wav *.m4a *.m2a *.mp3 *.aac *.lrf)"


class MultiClipEditor(QDialog):
    def __init__(self, file_paths, parent=None, reorder_only=False, show_multiclip=True):
        super().__init__(parent)

        self.setWindowTitle("멀티 클립 정렬")
        self.setMinimumWidth(1050)
        self.setStyleSheet(
            """
            QDialog { background-color: #121212; color: #FFFFFF; }
            QLabel { color: #FFFFFF; background: transparent; }
            """
        )

        self.sorted_files = sorted(file_paths, key=lambda p: os.path.basename(p).lower())
        self.cards = []
        self.selected_mode = "multiclip"
        self._reorder_only = reorder_only
        self._show_multiclip_btn = show_multiclip
        self._add_card = None
        self.stt_quality_preset = normalize_stt_quality_key(load_settings().get("stt_quality_preset", "precise"))

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()

        self.header_lbl = QLabel(
            f"<b style='font-size: 15px;'>멀티 클립 정렬</b>  —  {len(self.sorted_files)}개 클립  |  드래그로 순서 변경"
        )
        header.addWidget(self.header_lbl)
        header.addStretch()

        quality_lbl = QLabel("자막품질")
        quality_lbl.setStyleSheet("color:#C8D1D8; font-size:12px; font-weight:700;")
        header.addWidget(quality_lbl)
        self.combo_subtitle_quality = QComboBox()
        for key in STT_QUALITY_PRESET_ORDER:
            preset = load_stt_quality_presets().get(key, {})
            self.combo_subtitle_quality.addItem(str(preset.get("label") or stt_quality_label(key)), key)
        self.combo_subtitle_quality.setFixedWidth(92)
        self.combo_subtitle_quality.setToolTip("멀티클립에 적용할 자막품질 프리셋")
        self.combo_subtitle_quality.setStyleSheet(
            "QComboBox { background:#172028; color:#F5F7FA; border:1px solid #2A3943; "
            "border-radius:4px; padding:4px 18px 4px 8px; font-weight:700; } "
            "QComboBox::drop-down { border:none; width:16px; } "
            "QAbstractItemView { background:#172028; color:#F5F7FA; selection-background-color:#1A84FF; }"
        )
        self._sync_subtitle_quality_combo()
        self.combo_subtitle_quality.currentIndexChanged.connect(self._on_subtitle_quality_changed)
        header.addWidget(self.combo_subtitle_quality)

        btn_name = QPushButton("이름순")
        btn_name.setStyleSheet(
            "background:#333; color:#FFF; padding:6px 14px; border-radius:4px; font-weight:bold;"
        )
        btn_name.clicked.connect(self._sort_by_name)

        btn_date = QPushButton("날짜순")
        btn_date.setStyleSheet(
            "background:#333; color:#FFF; padding:6px 14px; border-radius:4px; font-weight:bold;"
        )
        btn_date.clicked.connect(self._sort_by_date)

        header.addWidget(btn_name)
        header.addWidget(btn_date)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(240)
        self.scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #333; background: #1a1a1a; border-radius: 6px; }"
        )

        self.container = ClipContainer(self)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        if not self._reorder_only:
            current_settings = self._resolve_pipeline_settings()
            current_title = QLabel("현재 적용될 설정")
            current_title.setStyleSheet("color:#C8D1D8; font-size:12px; font-weight:700; margin-top:4px;")
            layout.addWidget(current_title)

            self.current_settings_lbl = QLabel(self._pipeline_summary_text(current_settings))
            self.current_settings_lbl.setWordWrap(True)
            self.current_settings_lbl.setTextFormat(Qt.TextFormat.RichText)
            self.current_settings_lbl.setStyleSheet(
                "background:#172028; border:1px solid #2A3943; border-radius:6px; "
                "padding:10px 12px; color:#D7E0E8; font-size:11px;"
            )
            layout.addWidget(self.current_settings_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet(
            "background:#444; color:#FFF; padding:8px 24px; font-weight:bold; border-radius:4px;"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        if self._reorder_only:
            btn_ok = QPushButton("확인")
            btn_ok.setStyleSheet(
                "background:#4AFF80; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;"
            )
            btn_ok.clicked.connect(self.accept)
            btn_layout.addWidget(btn_ok)
        else:
            btn_multiclip = QPushButton("멀티클립 편집")
            btn_multiclip.setStyleSheet(
                "background:#4FC3F7; color:#000; padding:8px 24px; font-weight:bold; border-radius:4px;"
            )
            btn_multiclip.clicked.connect(self._accept_multiclip)

            btn_layout.addWidget(btn_multiclip)

        layout.addLayout(btn_layout)
        self._rebuild_cards()

    def _resolve_pipeline_settings(self) -> dict:
        parent = self.parent()
        if parent is not None:
            settings = getattr(parent, "settings", None)
            if isinstance(settings, dict) and settings:
                return apply_stt_quality_preset(dict(settings), self.stt_quality_preset)
        try:
            return apply_stt_quality_preset(dict(load_settings()), self.stt_quality_preset)
        except Exception:
            return {}

    def _sync_subtitle_quality_combo(self):
        key = normalize_stt_quality_key(self.stt_quality_preset)
        self.combo_subtitle_quality.blockSignals(True)
        for idx in range(self.combo_subtitle_quality.count()):
            if self.combo_subtitle_quality.itemData(idx) == key:
                self.combo_subtitle_quality.setCurrentIndex(idx)
                break
        self.combo_subtitle_quality.blockSignals(False)

    def _on_subtitle_quality_changed(self, *args):
        self.stt_quality_preset = normalize_stt_quality_key(self.combo_subtitle_quality.currentData() or "precise")
        settings = apply_stt_quality_preset(load_settings(), self.stt_quality_preset)
        save_settings(settings)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_apply_ai_settings"):
            parent._apply_ai_settings(settings)
        if hasattr(self, "current_settings_lbl"):
            self.current_settings_lbl.setText(self._pipeline_summary_text(settings))

    def _display_model_name(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return "미사용"
        text = text.replace("mlx-community/", "").replace("-mlx", "")
        if "/" in text:
            text = text.split("/")[-1]
        return text

    def _cut_boundary_label(self, settings: dict) -> str:
        level = str(
            settings.get(
                "cut_boundary_level",
                settings.get("scan_cut_boundary_level", "medium"),
            )
            or "medium"
        ).strip().lower()
        if level == "high":
            level = "medium"
        return {"off": "사용안함", "low": "낮음", "medium": "중간"}.get(level, "중간")

    def _pipeline_summary_text(self, settings: dict) -> str:
        audio_model = {
            "deepfilter": "DeepFilter",
            "rnnoise": "RNNoise",
            "resemble_enhance": "Resemble",
            "clearvoice": "ClearVoice",
            "none": "미사용",
        }.get(str(settings.get("selected_audio_ai", "none") or "none"), "미사용")
        vad_model = {
            "silero": "Silero",
            "ten_vad": "TEN VAD",
            "webrtc": "WebRTC",
            "pyannote": "Pyannote",
            "none": "미사용",
        }.get(str(settings.get("selected_vad", "none") or "none"), "미사용")
        stt1 = self._display_model_name(settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", "")))
        stt2 = "미사용"
        if bool(settings.get("stt_ensemble_enabled")):
            stt2 = self._display_model_name(settings.get("selected_whisper_model_secondary", ""))
        subtitle_llm = self._display_model_name(settings.get("selected_model", ""))
        return (
            f"자막품질 <b>{stt_quality_label(settings.get('stt_quality_preset'))}</b>  |  "
            f"오토 오디오 <b>클립 시작 시 자동 결정</b>  |  "
            f"컷 경계 <b>{self._cut_boundary_label(settings)}</b><br>"
            f"현재 음성 <b>{audio_model}</b>  |  STT1 <b>{stt1}</b>  |  "
            f"STT2 <b>{stt2}</b>  |  VAD <b>{vad_model}</b>  |  자막 LLM <b>{subtitle_llm}</b>"
        )

    def _remove_clip(self, idx):
        if idx < 0 or idx >= len(self.sorted_files):
            return
        self.sorted_files.pop(idx)
        self._rebuild_cards()

    def _rebuild_cards(self):
        existing = {card.file_path: card for card in self.cards}

        while self.container.layout.count():
            self.container.layout.takeAt(0)

        new_cards = []
        for i, file_path in enumerate(self.sorted_files):
            if file_path in existing:
                card = existing.pop(file_path)
                card.index = i + 1
                card.update()
            else:
                card = ClipCard(file_path, i + 1, self.container)
                card.remove_clicked.connect(self._remove_clip)

            new_cards.append(card)
            self.container.layout.addWidget(card)

        for card in existing.values():
            card.deleteLater()

        self.cards = new_cards

        if self._add_card:
            self._add_card.deleteLater()

        self._add_card = AddCard(self.container)
        self._add_card.clicked.connect(self._on_add_clip)
        self.container.layout.addWidget(self._add_card)
        self.container.layout.addStretch()

        self.header_lbl.setText(
            f"<b style='font-size: 15px;'>멀티 클립 정렬</b>  —  {len(self.sorted_files)}개 클립  |  드래그로 순서 변경"
        )

    def _on_add_clip(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "클립 추가",
            get_last_folder() or os.path.expanduser("~"),
            MEDIA_FILTER,
        )
        if not paths:
            return

        for path in paths:
            if path not in self.sorted_files:
                self.sorted_files.append(path)

        self._rebuild_cards()

    def _sort_by_name(self):
        self.sorted_files.sort(key=lambda p: os.path.basename(p).lower())
        self._rebuild_cards()

    def _sort_by_date(self):
        self.sorted_files.sort(key=lambda p: os.path.getmtime(p))
        self._rebuild_cards()

    def _accept_multiclip(self):
        self.selected_mode = "multiclip"
        self.accept()
