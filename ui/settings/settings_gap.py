# Version: 03.00.20
# Phase: PHASE2
"""
ui/settings_gap.py  ─  ⏱️ 자막 간격/분할 설정
[v01.00.10 수정사항]
- 파라미터 폼 영역을 QScrollArea로 감싸 화면 높이 초과 방지
- 최대 화면 높이 제한 (화면의 92%)
- 폼 row 간격 축소 (verticalSpacing=3)
"""
import json
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QSlider, QFrame, QMessageBox, QToolTip
)
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt
from core.project.data_manager import save_settings, save_default_settings
from ui.settings.settings_common import DEFAULT_ADV_SETTINGS, CUSTOM_DEFAULTS_FILE, _create_bottom_buttons
from ui.style import button_style, label_style, settings_dialog_stylesheet


from ui.settings.gap_simulator import GapSimulatorWidget

class GapSettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("자막 간격 시뮬레이터")
        self.setMinimumWidth(1180)
        # [v01.00.10] 화면 넘침 방지: 최대 높이를 현재 화면의 90%로 제한
        from PyQt6.QtWidgets import QApplication as _QApp, QScrollArea
        screen_h = _QApp.primaryScreen().availableGeometry().height()
        self.setMaximumHeight(int(screen_h * 0.92))
        
        self.setStyleSheet(settings_dialog_stylesheet())
        self.result = dict(settings)
        self.sliders_info = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        
        h1 = QHBoxLayout(); h1.addWidget(QLabel("<b style='font-size: 15px;'>실시간 AI 엔진 시뮬레이터</b>")); h1.addStretch(); layout.addLayout(h1)
        self.simulator = GapSimulatorWidget(); layout.addWidget(self.simulator)
        sep0 = QFrame(); sep0.setFixedHeight(1); sep0.setStyleSheet("background-color: #24313A; margin: 6px 0;"); layout.addWidget(sep0)

        # [v01.00.10] 파라미터 폼 전체를 QScrollArea로 감싸 화면 넘침 방지
        scroll_container = QWidget()
        scroll_layout = QVBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(4)

        two_col_layout = QHBoxLayout()
        two_col_layout.setSpacing(12)
        left_col = QVBoxLayout()
        left_col.setSpacing(2)
        right_col = QVBoxLayout()
        right_col.setSpacing(2)
        right_col.setContentsMargins(8, 0, 0, 0)
        
        # ==========================================
        # 👈 [왼쪽 단] 파라미터 튜닝 + 분할/삭제
        # ==========================================
        h2 = QHBoxLayout(); h2.addWidget(QLabel("<b style='font-size: 14px; color: #34C759;'>파라미터 튜닝</b>")); h2.addStretch(); left_col.addLayout(h2)
        form1 = QFormLayout()
        form1.setVerticalSpacing(3)
        form1.setHorizontalSpacing(8)
        
        self.slider_cont = QSlider(Qt.Orientation.Horizontal); self.slider_cont.setRange(0, 50)
        cur_cont = int(self.result.get("continuous_threshold", 2.0) * 10); self.slider_cont.setValue(cur_cont)
        self.lbl_cont = QLabel(f"{cur_cont/10.0:.1f} 초")
        form1.addRow("연속자막 기준:", self._create_slider_row(self.slider_cont, self.lbl_cont, "continuous_threshold", 10.0, lambda v: f"{v:.1f} 초", 
            "<b>[설명]</b> 두 자막 사이의 무음 구간이 이 시간보다 짧으면 '연속된 대화'로 판정하여 간격을 조절합니다.<br><br>"
            "[+] 넓게: 멀리 떨어진 자막도 연속으로 묶여 당기기/미루기가 적용됩니다.<br>"
            "[-] 좁게: 아주 짧은 간격의 자막에만 간격 조절이 빡빡하게 적용됩니다."))
        
        self.slider_push = QSlider(Qt.Orientation.Horizontal); self.slider_push.setRange(0, 100)
        cur_push = int(self.result.get("gap_push_rate", 0.7) * 100); self.slider_push.setValue(cur_push)
        self.lbl_push = QLabel(f"{cur_push} %")
        form1.addRow("자막간격 조정:", self._create_slider_row(self.slider_push, self.lbl_push, "gap_push_rate", 100.0, lambda v: f"{int(v*100)} %", 
            "<b>[설명]</b> 무음 구간을 앞/뒤 자막 중 어느 쪽이 더 많이 차지할지 비율을 결정합니다.<br><br>"
            "[+] 높음: 앞 자막이 화면에 길게 유지되며(미루기), 뒷 자막은 제시간에 뜹니다.<br>"
            "[-] 낮음: 앞 자막이 일찍 끝나고, 뒷 자막이 빈 공간을 채우며 일찍 뜹니다(당기기)."))

        self.slider_single = QSlider(Qt.Orientation.Horizontal); self.slider_single.setRange(0, 20)
        cur_single = int(self.result.get("single_subtitle_end", 0.2) * 10); self.slider_single.setValue(cur_single)
        self.lbl_single = QLabel(f"{cur_single/10.0:.1f} 초")
        form1.addRow("단일자막 유지:", self._create_slider_row(self.slider_single, self.lbl_single, "single_subtitle_end", 10.0, lambda v: f"{v:.1f} 초", 
            "<b>[설명]</b> 연속 판정이 끊어졌을 때, 자막이 화면에 단독으로 머무는 꼬리 시간입니다.<br><br>"
            "[+] 길게: 말이 끝난 후에도 자막이 화면에 오랫동안 남아 여유가 생깁니다.<br>"
            "[-] 짧게: 단독 자막이 오디오가 끝나자마자 칼같이 바로 사라집니다."))

        left_col.addLayout(form1)
        sep1 = QFrame(); sep1.setFixedHeight(1); sep1.setStyleSheet("background-color: #24313A; margin: 8px 0;"); left_col.addWidget(sep1)

        h3 = QHBoxLayout(); h3.addWidget(QLabel("<b style='font-size: 14px; color: #34C759;'>자막 분할 및 삭제 기준</b>")); h3.addStretch(); left_col.addLayout(h3)
        form3 = QFormLayout()

        self.slider_split = QSlider(Qt.Orientation.Horizontal); self.slider_split.setRange(5, 50)
        cur_split = int(self.result.get("split_length_threshold", 10)); self.slider_split.setValue(cur_split)
        self.lbl_split = QLabel(f"{cur_split} 자")
        form3.addRow("분할 기준 글자 수:", self._create_slider_row(self.slider_split, self.lbl_split, "split_length_threshold", 1.0, lambda v: f"{int(v)} 자", 
            "<b>[설명]</b> AI가 문장을 나눌 때 목표로 하는 한 줄당 글자 수 기준입니다.<br><br>"
            "[+] 길게: 한 줄에 들어가는 글자가 많아져 자막의 호흡이 길어집니다.<br>"
            "[-] 짧게: 자막이 짧은 단어 위주로 화면에 잘게 쪼개져 표시됩니다."))
        
        self.slider_min_dur = QSlider(Qt.Orientation.Horizontal); self.slider_min_dur.setRange(0, 10)
        cur_min_dur = int(self.result.get("sub_min_duration", 0.3) * 10); self.slider_min_dur.setValue(cur_min_dur)
        self.lbl_min_dur = QLabel(f"{cur_min_dur/10.0:.1f} 초")
        form3.addRow("초단문 무시 (삭제):", self._create_slider_row(self.slider_min_dur, self.lbl_min_dur, "sub_min_duration", 10.0, lambda v: f"{v:.1f} 초", 
            "<b>[설명]</b> 헛기침이나 노이즈 파편 자막을 원천적으로 삭제하는 기준 시간입니다.<br><br>"
            "[+] 길게: 웬만한 노이즈는 다 지워지나, '네', '아' 같은 정상 대답도 삭제될 수 있습니다.<br>"
            "[-] 짧게: 짧은 감탄사나 작은 숨소리도 전부 화면에 표시됩니다."))
        
        self.slider_cps = QSlider(Qt.Orientation.Horizontal); self.slider_cps.setRange(5, 30)
        cur_cps = int(self.result.get("sub_max_cps", 12)); self.slider_cps.setValue(cur_cps)
        self.lbl_cps = QLabel(f"{cur_cps} 자/초")
        form3.addRow("최대 발음 속도 (CPS):", self._create_slider_row(self.slider_cps, self.lbl_cps, "sub_max_cps", 1.0, lambda v: f"{int(v)} 자/초", 
            "<b>[설명]</b> 1초에 뱉을 수 있는 물리적 최대 글자 수입니다.<br><br>"
            "[+] 관대하게: 기계적인 환각(랩하듯 쏟아내는 오류)이 안 지워지고 그대로 표시됩니다.<br>"
            "[-] 엄격하게: 말이 조금만 빨라도 환각으로 간주해 억울하게 삭제될 수 있습니다."))

        self.slider_max_dur = QSlider(Qt.Orientation.Horizontal); self.slider_max_dur.setRange(10, 120)
        cur_max_dur = int(self.result.get("sub_max_duration", 6.0) * 10); self.slider_max_dur.setValue(cur_max_dur)
        self.lbl_max_dur = QLabel(f"{cur_max_dur/10.0:.1f} 초")
        form3.addRow("최대 자막 길이:", self._create_slider_row(self.slider_max_dur, self.lbl_max_dur, "sub_max_duration", 10.0, lambda v: f"{v:.1f} 초",
            "<b>[설명]</b> 한 자막이 화면에 유지되는 최대 목표 시간입니다.<br><br>"
            "[+] 길게: 호흡이 긴 문장을 한 자막에 더 오래 유지합니다.<br>"
            "[-] 짧게: 긴 문장을 word timestamp 기준으로 더 자주 나눕니다."))

        self.slider_dedup = QSlider(Qt.Orientation.Horizontal); self.slider_dedup.setRange(1, 20)
        cur_dedup = int(self.result.get("sub_dedup_window", 0.5) * 10); self.slider_dedup.setValue(cur_dedup)
        self.lbl_dedup = QLabel(f"{cur_dedup/10.0:.1f} 초")
        form3.addRow("말더듬 환각 제거:", self._create_slider_row(self.slider_dedup, self.lbl_dedup, "sub_dedup_window", 10.0, lambda v: f"{v:.1f} 초", 
            "<b>[설명]</b> 같은 단어가 이 시간 내에 반복되면 앵무새 오류로 보고 잘라냅니다.<br><br>"
            "[+] 넓게: 비슷한 단어가 연달아 나올 때 정상 문장도 삭제될 위험이 커집니다.<br>"
            "[-] 좁게: 진짜로 더듬은 말이 자연스럽게 화면에 그대로 표시됩니다."))

        self.slider_gap_break = QSlider(Qt.Orientation.Horizontal); self.slider_gap_break.setRange(5, 50)
        cur_gap_break = int(self.result.get("sub_gap_break_sec", 1.5) * 10); self.slider_gap_break.setValue(cur_gap_break)
        self.lbl_gap_break = QLabel(f"{cur_gap_break/10.0:.1f} 초")
        form3.addRow("강제 줄바꿈 무음:", self._create_slider_row(self.slider_gap_break, self.lbl_gap_break, "sub_gap_break_sec", 10.0, lambda v: f"{v:.1f} 초", 
            "<b>[설명]</b> 대사 중간이라도 이 시간만큼 조용하면 앞뒤 문맥 무시하고 강제로 줄바꿈합니다.<br><br>"
            "[+] 길게: 호흡이 긴 대사라도 끊기지 않고 한 줄에 자연스럽게 합쳐집니다.<br>"
            "[-] 짧게: 오디오가 살짝만 비어도 자막이 잘게 파편화되어 분리됩니다."))

        left_col.addLayout(form3); left_col.addStretch()

        h4 = QHBoxLayout(); h4.addWidget(QLabel("<b style='font-size: 14px; color: #34C759;'>적용 안내</b>")); h4.addStretch(); right_col.addLayout(h4)
        info = QLabel(
            "이 메뉴는 최종 자막 생성에서 실제로 쓰는 간격/분할 값만 남겼습니다.<br>"
            "텍스트 LoRA와 컷 경계 스냅을 우선 적용한 뒤, 여기의 간격/분할 기준이 마지막으로 반영됩니다."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #A9B0B7; line-height: 1.45; padding: 8px 10px;")
        right_col.addWidget(info)
        right_col.addStretch()

        two_col_layout.addLayout(left_col)
        v_sep = QFrame(); v_sep.setFrameShape(QFrame.Shape.VLine); v_sep.setStyleSheet("background-color: #24313A; margin: 0 8px;")
        two_col_layout.addWidget(v_sep)
        two_col_layout.addLayout(right_col)

        scroll_layout.addLayout(two_col_layout)

        # QScrollArea로 감싸기
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_container)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(scroll_area, stretch=1)

        layout.addLayout(_create_bottom_buttons(self, self._on_ok, self._on_reset, self._on_save, save_def_callback=self._on_save_default))

        # 모든 슬라이더를 시뮬레이터 갱신에 연결
        for s in [
            self.slider_cont,
            self.slider_push,
            self.slider_single,
            self.slider_min_dur,
            self.slider_dedup,
            self.slider_gap_break,
            self.slider_cps,
            self.slider_split,
            self.slider_max_dur,
        ]:
            s.valueChanged.connect(self._update_simulator)
        
        self._update_simulator()

    def _update_simulator(self, *args):
        self.simulator.cont_thresh = self.slider_cont.value() / 10.0
        self.simulator.push_rate = self.slider_push.value() / 100.0
        self.simulator.pull_rate = 1.0 - self.simulator.push_rate
        self.simulator.single_ext = self.slider_single.value() / 10.0
        self.simulator.split_len = self.slider_split.value()
        self.simulator.min_dur = self.slider_min_dur.value() / 10.0
        self.simulator.dedup_win = self.slider_dedup.value() / 10.0
        self.simulator.gap_break = self.slider_gap_break.value() / 10.0
        self.simulator.max_cps = self.slider_cps.value()
        self.simulator.max_dur = self.slider_max_dur.value() / 10.0
        self.simulator.update()

    def _create_slider_row(self, slider: QSlider, label: QLabel, key: str, multiplier: float, format_func, tip: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        
        # 💡 [수정] 마우스를 올렸을 때(Hover) 즉각적인 툴팁이 뜨도록 커스텀 라벨 적용
        class HoverLabel(QLabel):
            def __init__(self, tip_text):
                super().__init__("?")
                self.tip = tip_text
                self.setStyleSheet("color: #7A8792; font-size: 12px; font-weight: 700; background: transparent; margin-right: 3px;")
                self.setCursor(Qt.CursorShape.WhatsThisCursor)
                
            def enterEvent(self, event):
                QToolTip.showText(QCursor.pos(), self.tip, self)
                super().enterEvent(event)
                
            def leaveEvent(self, event):
                QToolTip.hideText()
                super().leaveEvent(event)

        help_icon = HoverLabel(tip)
        layout.addWidget(help_icon)
        
        # -, + 버튼 스타일 및 로직
        btn_style = button_style("toolbar", font_size="12px", padding="2px 6px") + " QPushButton { min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; }"
        
        btn_m = QPushButton("-")
        btn_m.setStyleSheet(btn_style)
        btn_m.clicked.connect(lambda: slider.setValue(slider.value() - 1))
        
        btn_p = QPushButton("+")
        btn_p.setStyleSheet(btn_style)
        btn_p.clicked.connect(lambda: slider.setValue(slider.value() + 1))
        
        layout.addWidget(btn_m)
        layout.addWidget(slider)
        layout.addWidget(btn_p)
        
        label.setMinimumWidth(55)
        layout.addWidget(label)
        
        self.sliders_info.append((slider, key, multiplier))
        slider.valueChanged.connect(lambda v: label.setText(format_func(v / multiplier)))
        
        return layout

    def _on_reset(self):
        for s, k, m in self.sliders_info:
            d = DEFAULT_ADV_SETTINGS.get(k)
            if d is not None: s.setValue(int(d * m))

    def _collect_data(self):
        self.result["continuous_threshold"] = self.slider_cont.value() / 10.0
        self.result["gap_push_rate"] = self.slider_push.value() / 100.0
        self.result["single_subtitle_end"] = self.slider_single.value() / 10.0
        self.result["split_length_threshold"] = int(self.slider_split.value())
        self.result["sub_min_duration"] = self.slider_min_dur.value() / 10.0
        self.result["sub_max_duration"] = self.slider_max_dur.value() / 10.0
        self.result["sub_max_cps"] = int(self.slider_cps.value())
        self.result["sub_dedup_window"] = self.slider_dedup.value() / 10.0
        self.result["sub_gap_break_sec"] = self.slider_gap_break.value() / 10.0

    def _on_save(self): self._collect_data(); save_settings(self.result); self.accept()
    def _on_save_default(self): self._collect_data(); save_default_settings(self.result); QMessageBox.information(self, "완료", "기본값 저장 완료!")
    def _on_ok(self): self._collect_data(); self.accept()
