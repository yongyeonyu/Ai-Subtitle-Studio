# Version: 03.01.25
# Phase: PHASE2
"""
ui/settings_advanced.py  ─  🛠️ 오디오 & Whisper 엔진 상세 튜닝 다이얼로그
"""
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QSlider, QToolTip, QTabWidget,
    QWidget, QTextEdit, QCheckBox, QMessageBox, QComboBox
)
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt, QTimer
import config
from core.project.data_manager import save_settings, save_default_settings
from ui.settings.settings_common import DEFAULT_ADV_SETTINGS, CUSTOM_DEFAULTS_FILE, _create_bottom_buttons
from ui.style import button_style, label_style, settings_dialog_stylesheet
from core.audio.audio_presets import load_audio_presets, apply_audio_preset

class AdvancedSettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):

        super().__init__(parent)
        self.setWindowTitle("🛠️ 오디오 & Whisper 엔진 상세 튜닝")

        self.setMinimumWidth(800)
        self.setMinimumHeight(650)
        
        self.setStyleSheet(settings_dialog_stylesheet())
        self.result = dict(settings)
        self.audio_presets = load_audio_presets()
        current_preset = self.result.get("audio_preset", "")
        if current_preset in self.audio_presets:
            self.result = apply_audio_preset(self.result, current_preset)
        self.sliders_info = [] 

        layout = QVBoxLayout(self)
        preset_layout = QHBoxLayout()
        preset_lbl = QLabel("오디오 프리셋:")
        preset_lbl.setStyleSheet(label_style("accent", 13, bold=True))
        self.combo_audio_preset = QComboBox()
        self.combo_audio_preset.addItem("직접 설정", "")
        for name, preset in self.audio_presets.items():
            desc = preset.get("description", "")
            self.combo_audio_preset.addItem(f"{name} - {desc}" if desc else name, name)
        if current_preset:
            for _i in range(self.combo_audio_preset.count()):
                if self.combo_audio_preset.itemData(_i) == current_preset:
                    self.combo_audio_preset.setCurrentIndex(_i)
                    break
        preset_layout.addWidget(preset_lbl)
        preset_layout.addWidget(self.combo_audio_preset, stretch=1)
        layout.addLayout(preset_layout)
        self.combo_audio_preset.currentIndexChanged.connect(self._on_audio_preset_changed)
        self.tabs = QTabWidget()
        
        # 탭 1: Silero
        tab_silero = QWidget(); form_silero = QFormLayout(tab_silero)
        self._add_slider(form_silero, "vad_threshold", "VAD 민감도 (Threshold):", 
                         "<nobr>💡 소리를 목소리로 판단하는 확신도입니다.<br>➕ : 깐깐하게 목소리만 잡음 (기본값: {default})<br>➖ : 작은 소음도 목소리로 인식</nobr>", 
                         10, 90, DEFAULT_ADV_SETTINGS['vad_threshold'], 100, "{:.2f}")
        self._add_slider(form_silero, "vad_min_speech", "최소 음성 길이 (초):", 
                         "<nobr>💡 이 시간보다 짧은 소리는 잡음으로 보고 무시합니다.<br>➕ : 기침이나 짧은 잡음 제거 (기본값: {default})<br>➖ : 짧은 단어도 살림</nobr>", 
                         5, 100, DEFAULT_ADV_SETTINGS['vad_min_speech'], 100, "{:.2f} 초")
        self._add_slider(form_silero, "vad_min_silence", "무음 판단 간격 (초):", 
                         "<nobr>💡 말 사이 공백이 이보다 짧으면 한 문장으로 합칩니다.<br>➕ : 문장이 길게 유지됨 (기본값: {default})<br>➖ : 단어 단위로 쪼개짐</nobr>", 
                         5, 100, DEFAULT_ADV_SETTINGS['vad_min_silence'], 10, "{:.1f} 초")
        self._add_slider(form_silero, "vad_speech_pad", "음성 앞뒤 여유 (초):", 
                         "<nobr>💡 감지된 목소리 앞뒤에 붙일 여유 시간입니다.<br>➕ : 말이 잘리는 현상 방지 (기본값: {default})<br>➖ : 칼같이 자름</nobr>", 
                         0, 50, DEFAULT_ADV_SETTINGS['vad_speech_pad'], 100, "{:.2f} 초")
        self._add_slider(form_silero, "vad_window_size", "VAD 분석 단위 (Window Size):", 
                         "<nobr>💡 오디오를 분석하는 샘플 크기입니다.<br>➕ : 더 넓은 문맥 파악, 정확도 약간 상승(속도 저하)<br>➖ : 빠른 처리 (기본값: {default})</nobr>", 
                         256, 2048, DEFAULT_ADV_SETTINGS['vad_window_size'], 1, "{} 샘플")
        self.tabs.addTab(tab_silero, "Silero")

        # 탭 2: Demucs
        tab_dm = QWidget(); form_dm = QFormLayout(tab_dm)
        self._add_slider(form_dm, "dm_vol", "전체 볼륨 펌핑 (배수):", 
                         "<nobr>💡 Demucs 추출 후 깨끗해진 목소리의 최종 볼륨을 증폭합니다.<br>➕ : 숨소리까지 커지지만 너무 높으면 소리가 깨질 수 있음 (기본값: {default})<br>➖ : 전체 소리가 작아짐</nobr>", 
                         10, 50, DEFAULT_ADV_SETTINGS['dm_vol'], 10, "{:.1f} 배")
        self._add_slider(form_dm, "dm_shifts", "음원 분리 정밀도 (Shifts):", 
                         "<nobr>💡 오프셋을 주어 여러 번 분리 후 평균을 냅니다.<br>➕ : 품질이 향상되나 시간이 크게 늘어남 (기본값: {default})<br>➖ : 빠르나 노이즈가 남을 수 있음</nobr>", 
                         0, 10, DEFAULT_ADV_SETTINGS['dm_shifts'], 1, "{} 회")
        self._add_slider(form_dm, "dm_overlap", "분할 구간 겹침 (Overlap):", 
                         "<nobr>💡 오디오를 자를 때 겹치는 비율입니다.<br>➕ : 경계선이 자연스러워지나 속도 저하 (기본값: {default})<br>➖ : 빠르지만 경계선 틱 노이즈 발생 가능</nobr>", 
                         10, 90, DEFAULT_ADV_SETTINGS['dm_overlap'], 100, "{:.2f}")
        self._add_slider(form_dm, "dm_segments", "분할 처리 단위 (Segment 초):", 
                         "<nobr>💡 한 번에 메모리에 올릴 오디오 길이입니다.<br>➕ : 메모리를 많이 먹지만 분리 품질 상승 (기본값: {default})<br>➖ : 메모리 절약, 품질 소폭 하락</nobr>", 
                         10, 100, DEFAULT_ADV_SETTINGS['dm_segments'], 1, "{} 초")
        self._add_slider(form_dm, "w_dm_no_speech", "무음 건너뛰기 문턱:", 
                         "<nobr>💡 Whisper가 무음(잡음)으로 판단하여 번역을 포기하는 기준점입니다.<br>➕ : 발음이 살짝만 흐려도 통째로 건너뛰어 대사가 증발함 (기본값: {default})<br>➖ : 아주 작은 소음도 억지로 번역하려 들어 환각이 늘어남</nobr>", 
                         0, 100, DEFAULT_ADV_SETTINGS['w_dm_no_speech'], 100, "{:.2f}")
        self._add_slider(form_dm, "w_dm_logprob", "자신감 문턱 (Logprob):", 
                         "<nobr>💡 AI가 자신의 번역에 확신이 없을 때 출력할지 결정합니다.<br>➕ : 확실한 말만 출력해 듬성듬성 공백이 생김 (기본값: {default})<br>➖ : 틀린 말이라도 일단 다 뱉어냄</nobr>", 
                         -30, 0, DEFAULT_ADV_SETTINGS['w_dm_logprob'], 10, "{:.1f}")
        self._add_slider(form_dm, "w_dm_comp", "반복 환각 차단 수치:", 
                         "<nobr>💡 무의미한 글자 반복을 허용하는 수치입니다.<br>➕ : 반복을 관대하게 허용하여 텍스트가 잘려나가지 않음 (기본값: {default})<br>➖ : 조금만 반복돼도 환각으로 보고 통째로 삭제함</nobr>", 
                         10, 30, DEFAULT_ADV_SETTINGS['w_dm_comp'], 10, "{:.1f}")
        self._add_slider(form_dm, "w_dm_temp_max", "창의성/유추 (Max Temp):", 
                         "<nobr>💡 소음 때문에 발음이 뭉개졌을 때 앞뒤 문맥으로 때려맞추는 상상력입니다.<br>➕ : 그럴듯한 문장으로 지어내어 맥락을 이어감 (기본값: {default})<br>➖ : 들리는 대로만 정직하게 적어 오타가 늘어남</nobr>", 
                         0, 10, DEFAULT_ADV_SETTINGS['w_dm_temp_max'], 10, "{:.1f}")
        self.tabs.addTab(tab_dm, "Demucs")

        # 탭 3: DeepFilter
        tab_df = QWidget(); form_df = QFormLayout(tab_df)
        self._add_slider(form_df, "df_hp", "하이패스 (저음 컷 Hz):", 
                         "<nobr>💡 지정된 주파수(Hz) 미만의 저음을 물리적으로 잘라냅니다.<br>➕ : 저음이 다 잘려 목소리가 앵앵거리게(전화기처럼) 얇아짐 (기본값: {default})<br>➖ : 웅웅거리는 노면/바람 소리가 그대로 남음</nobr>", 
                         20, 300, DEFAULT_ADV_SETTINGS['df_hp'], 1, "{} Hz")
        self._add_slider(form_df, "df_eq_g", "보컬 EQ (3kHz) 증폭:", 
                         "<nobr>💡 목소리의 딕션(자음)을 담당하는 3kHz 대역을 강제 증폭합니다.<br>➕ : 발음이 귀에 꽂히듯 선명해지지만 쇳소리가 심해질 수 있음 (기본값: {default})<br>➖ : 소리가 먹먹하고 답답해짐</nobr>", 
                         0, 15, DEFAULT_ADV_SETTINGS['df_eq_g'], 1, "{} dB")
        self._add_slider(form_df, "df_comp_th", "작은 소리 증폭 기준:", 
                         "<nobr>💡 이 기준점보다 작은 소리를 멱살잡고 끌어올립니다.<br>➕ : 큰 소리만 정상적으로 들림 (기본값: {default})<br>➖ : 개미만한 속삭임까지 다 커짐</nobr>", 
                         -50, -10, DEFAULT_ADV_SETTINGS['df_comp_th'], 1, "{} dB")
        self._add_slider(form_df, "df_vol", "전체 볼륨 펌핑 (배수):", 
                         "<nobr>💡 DeepFilterNet 추출 후 깨끗해진 목소리의 최종 볼륨을 증폭합니다.<br>➕ : 숨소리까지 커지지만 너무 높으면 소리가 깨질 수 있음 (기본값: {default})<br>➖ : 전체 소리가 작아짐</nobr>", 
                         10, 50, DEFAULT_ADV_SETTINGS['df_vol'], 10, "{:.1f} 배")
        self._add_slider(form_df, "df_atten_lim", "최대 노이즈 억제량 (Atten Limit):", 
                         "<nobr>💡 노이즈를 억제할 수 있는 최대 한계치입니다.<br>➕ : 거의 모든 배경음을 죽여 진공 상태처럼 만듦 (기본값: {default})<br>➖ : 자연스러운 배경음을 어느 정도 살려둠</nobr>", 
                         10, 100, DEFAULT_ADV_SETTINGS['df_atten_lim'], 1, "{} dB")
        self._add_slider(form_df, "w_df_no_speech", "무음 건너뛰기 문턱:", 
                         "<nobr>💡 Whisper 무음 판단 기준입니다.<br>➕ : 발음이 살짝만 흐려도 통째로 건너뛰어 대사가 증발함 (기본값: {default})<br>➖ : 아주 작은 소음도 억지로 번역하려 들어 환각이 늘어남</nobr>", 
                         0, 100, DEFAULT_ADV_SETTINGS['w_df_no_speech'], 100, "{:.2f}")
        self._add_slider(form_df, "w_df_logprob", "자신감 문턱 (Logprob):", 
                         "<nobr>💡 AI가 번역에 확신이 없을 때 출력할지 결정합니다.<br>➕ : 확실한 말만 출력해 듬성듬성 공백이 생김 (기본값: {default})<br>➖ : 틀린 말이라도 일단 다 뱉어냄</nobr>", 
                         -30, 0, DEFAULT_ADV_SETTINGS['w_df_logprob'], 10, "{:.1f}")
        self._add_slider(form_df, "w_df_comp", "반복 환각 차단 수치:", 
                         "<nobr>💡 무의미한 글자 반복을 허용하는 수치입니다.<br>➕ : 반복을 관대하게 허용하여 텍스트가 안 잘림 (기본값: {default})<br>➖ : 조금만 반복돼도 환각으로 보고 통째로 삭제함</nobr>", 
                         10, 30, DEFAULT_ADV_SETTINGS['w_df_comp'], 10, "{:.1f}")
        self._add_slider(form_df, "w_df_temp_max", "창의성/유추 (Max Temp):", 
                         "<nobr>💡 소음 속 문맥 유추 상상력입니다.<br>➕ : 그럴듯한 문장으로 억지로 지어내려 함 (기본값: {default})<br>➖ : 들리는 대로만 정직하게 적어 오타가 빈발함</nobr>", 
                         0, 10, DEFAULT_ADV_SETTINGS['w_df_temp_max'], 10, "{:.1f}")
        self.tabs.addTab(tab_df, "DeepFilter")

        # 탭 4: Whisper 전용 설정
        tab_whisper = QWidget(); form_whisper = QFormLayout(tab_whisper)
        self._add_slider(form_whisper, "w_beam_size", "탐색 가짓수 (Beam Size):", 
                         "<nobr>💡 AI가 문장을 유추할 때 동시에 고려하는 경우의 수입니다.<br>➕ : 더 정확한 문맥을 찾지만 속도가 느려짐 (기본값: {default})<br>➖ : 유력한 하나만 빠르게 탐색</nobr>", 
                         1, 10, DEFAULT_ADV_SETTINGS['w_beam_size'], 1, "{} 개")
        self._add_slider(form_whisper, "w_patience", "탐색 끈기 (Patience):", 
                         "<nobr>💡 최적의 결과를 찾기 위해 탐색을 계속 유지하는 정도입니다.<br>➕ : 인내심을 갖고 끝까지 탐색함 (기본값: {default})<br>➖ : 적당히 그럴듯하면 바로 확정</nobr>", 
                         0, 20, DEFAULT_ADV_SETTINGS['w_patience'], 10, "{:.1f}")
        self._add_slider(form_whisper, "w_length_penalty", "길이 보정 (Length Penalty):", 
                         "<nobr>💡 자막 길이에 대한 페널티/보상 수치입니다.<br>➕ : 더 긴 문장을 생성하려고 노력함 (기본값: {default})<br>➖ : 짧고 간결한 문장을 선호함</nobr>", 
                         -20, 20, DEFAULT_ADV_SETTINGS['w_length_penalty'], 10, "{:.1f}")
        self._add_slider(form_whisper, "ff_chunk", "분할 시간 (-segment_time 초):", 
                         "<nobr>💡 오디오를 자를 단위 시간입니다.<br>너무 길면 메모리를 과도하게 사용하고, 짧으면 파일 수가 많아집니다. (기본값: {default})</nobr>", 
                         10, 60, DEFAULT_ADV_SETTINGS['ff_chunk'], 1, "{} 초")
        self._add_slider(form_whisper, "w_none_no_speech", "무음 건너뛰기 문턱:", 
                         "<nobr>💡 Whisper가 무음(잡음)으로 판단하여 번역을 포기하는 기준점입니다.<br>➕ : 조금만 발음이 흐려도 건너뛰어 대사가 누락됨 (기본값: {default})<br>➖ : 소음을 억지로 번역하려 들어 환각 텍스트가 늘어남</nobr>", 
                         0, 100, DEFAULT_ADV_SETTINGS['w_none_no_speech'], 100, "{:.2f}")
        self._add_slider(form_whisper, "w_none_logprob", "자신감 문턱 (Logprob):", 
                         "<nobr>💡 AI가 번역에 확신이 없을 때 출력할지 결정합니다.<br>➕ : 확실한 말만 출력해 듬성듬성 공백이 생김 (기본값: {default})<br>➖ : 틀린 말이라도 일단 다 뱉어냄</nobr>", 
                         -30, 0, DEFAULT_ADV_SETTINGS['w_none_logprob'], 10, "{:.1f}")
        self._add_slider(form_whisper, "w_none_comp", "반복 환각 차단 수치:", 
                         "<nobr>💡 무의미한 글자 반복을 허용하는 수치입니다.<br>➕ : 반복을 관대하게 허용하여 텍스트가 안 잘림 (기본값: {default})<br>➖ : 조금만 반복돼도 환각으로 보고 통째로 삭제함</nobr>", 
                         10, 30, DEFAULT_ADV_SETTINGS['w_none_comp'], 10, "{:.1f}")
        self._add_slider(form_whisper, "w_none_temp_max", "창의성/유추 (Max Temp):", 
                         "<nobr>💡 발음이 뭉개졌을 때 앞뒤 문맥으로 유추하는 상상력입니다.<br>➕ : 그럴듯한 문장으로 억지로 지어내려 함 (기본값: {default})<br>➖ : 들리는 대로만 정직하게 적어 오타가 빈발함</nobr>", 
                         0, 10, DEFAULT_ADV_SETTINGS['w_none_temp_max'], 10, "{:.1f}")
        self.tabs.addTab(tab_whisper, "Whisper")

        # 탭 5: ffmpeg
        tab_ff = QWidget(); form_ff = QFormLayout(tab_ff)
        self._add_slider(form_ff, "ff_threads", "작업 스레드 (-threads):", 
                         "<nobr>💡 오디오 변환 시 사용할 CPU 스레드 수입니다.<br>0은 시스템이 자동으로 스레드를 할당함을 의미합니다. (기본값: {default})</nobr>", 
                         0, 16, DEFAULT_ADV_SETTINGS['ff_threads'], 1, "{} 개")
        self._add_slider(form_ff, "ff_ac", "오디오 채널 (-ac):", 
                         "<nobr>💡 오디오 채널 수입니다.<br>1은 모노, 2는 스테레오입니다. Whisper는 모노(1)를 권장합니다. (기본값: {default})</nobr>", 
                         1, 2, DEFAULT_ADV_SETTINGS['ff_ac'], 1, "{} 채널")
        self._add_slider(form_ff, "ff_ar", "샘플레이트 (-ar Hz):", 
                         "<nobr>💡 추출할 오디오의 주파수입니다.<br>Whisper 표준인 16000Hz를 강력히 권장합니다. (기본값: {default})</nobr>", 
                         8000, 48000, DEFAULT_ADV_SETTINGS['ff_ar'], 1, "{} Hz")
        self._add_slider(form_ff, "ff_hp", "저음 컷 (highpass Hz):", 
                         "<nobr>💡 지정된 주파수 미만의 저음을 물리적으로 잘라냅니다.<br>웅웅거리는 노이즈를 제거하는 필터입니다. (기본값: {default})</nobr>", 
                         0, 500, DEFAULT_ADV_SETTINGS['ff_hp'], 1, "{} Hz")
        self._add_slider(form_ff, "ff_lp", "고음 컷 (lowpass Hz):", 
                         "<nobr>💡 지정된 주파수 이상의 고음을 잘라냅니다.<br>날카로운 노이즈를 제거하는 필터입니다. (기본값: {default})</nobr>", 
                         1000, 8000, DEFAULT_ADV_SETTINGS['ff_lp'], 1, "{} Hz")
        self._add_slider(form_ff, "ff_nf", "노이즈 감소 (afftdn nf dB):", 
                         "<nobr>💡 배경 화이트 노이즈를 감소시키는 강도(음수)입니다.<br>숫자가 작을수록 노이즈를 더 강력하게 제거합니다. (기본값: {default})</nobr>", 
                         -50, 0, DEFAULT_ADV_SETTINGS['ff_nf'], 1, "{} dB")
        self._add_slider(form_ff, "ff_dynaudnorm_m", "동적 볼륨 최대 증폭 (Max Amp):", 
                         "<nobr>💡 소리가 작을 때 끌어올릴 수 있는 최대 배수입니다.<br>➕ : 아무리 작은 소리도 끝까지 증폭시킴 (기본값: {default})<br>➖ : 지나친 펌핑 방지</nobr>", 
                         1, 50, DEFAULT_ADV_SETTINGS['ff_dynaudnorm_m'], 1, "{:.1f} 배")
        self._add_slider(form_ff, "ff_dynaudnorm_p", "동적 볼륨 피크 한계 (Peak Limit):", 
                         "<nobr>💡 소리를 키울 때 허용되는 최대 진폭입니다.<br>➕ : 소리가 깨지기 직전까지 키움 (기본값: {default})<br>➖ : 안전하게 여유 공간(헤드룸)을 남김</nobr>", 
                         50, 100, DEFAULT_ADV_SETTINGS['ff_dynaudnorm_p'], 100, "{:.2f}")
        self._add_slider(form_ff, "ff_treble_boost", "고음 선명도 (Treble Boost):", 
                         "<nobr>💡 딕션 강화를 위해 고음역대(5kHz 이상)를 증폭합니다.<br>➕ : 치찰음이 강조되어 발음이 선명해짐 (기본값: {default})<br>➖ : 거슬릴 경우 고음 감소</nobr>", 
                         -10, 20, DEFAULT_ADV_SETTINGS['ff_treble_boost'], 1, "{} dB")
        self._add_slider(form_ff, "none_comp_th", "작은 소리 증폭 기준 (기본 필터):", 
                         "<nobr>💡 이 기준점보다 작은 소리를 멱살잡고 끌어올립니다.<br>➕ : 목소리가 작을 때 증폭이 원활하게 안 됨 (기본값: {default})<br>➖ : 아주 작은 화이트 노이즈(스으으 소리)까지 다 커짐</nobr>", 
                         -50, -10, DEFAULT_ADV_SETTINGS['none_comp_th'], 1, "{} dB")
        self._add_slider(form_ff, "none_vol", "전체 볼륨 펌핑 (기본 필터 배수):", 
                         "<nobr>💡 최종 오디오 볼륨을 무식하게 증폭합니다.<br>➕ : 주변 소음도 같이 엄청나게 커져 AI가 혼란스러워함 (기본값: {default})<br>➖ : 소리가 작아 인식률이 떨어질 수 있음</nobr>", 
                         10, 50, DEFAULT_ADV_SETTINGS['none_vol'], 10, "{:.1f} 배")
        self.tabs.addTab(tab_ff, "ffmpeg")

        # 탭 6: LLM 프롬프트를 2단으로 분리
        tab_llm = QWidget(); layout_llm = QVBoxLayout(tab_llm)
        
        lbl_sys = QLabel("<b>[시스템 설정]</b> (config.py 및 내부 시스템 강제 룰 - 수정 불가)")
        lbl_sys.setStyleSheet(label_style("accent", 13, bold=True) + "padding-top: 5px;")
        layout_llm.addWidget(lbl_sys)
        
        edit_sys_prompt = QTextEdit()
        edit_sys_prompt.setReadOnly(True)
        edit_sys_prompt.setStyleSheet("color: #8E98A1;")
        
        # 💡 config.py 내용만 깔끔하게 불러오도록 찌꺼기 텍스트 삭제
        sys_text = getattr(config, "DEFAULT_LLM_PROMPT", "")
        edit_sys_prompt.setPlainText(sys_text.strip())
        layout_llm.addWidget(edit_sys_prompt, stretch=5)
        
        lbl_user = QLabel("<b>[사용자 설정]</b> (이곳에 추가로 지시할 스타일을 입력하세요)")
        lbl_user.setStyleSheet(label_style("accent", 13, bold=True) + "padding-top: 10px;")
        layout_llm.addWidget(lbl_user)
        
        self.edit_user_prompt = QTextEdit()
        fallback_prompt = self.result.get("user_prompt", self.result.get("llm_prompt", ""))
        self.edit_user_prompt.setPlainText(fallback_prompt)
        self.edit_user_prompt.setPlaceholderText("예: 이번 영상은 제주도 브이로그니까 '다낭' 대신 '제주' 관련 고유명사를 유지해줘.")
        layout_llm.addWidget(self.edit_user_prompt, stretch=5)
        
        btn_save_llm_default = QPushButton("프롬프트 저장")
        btn_save_llm_default.setStyleSheet(button_style("toolbar"))
        def save_llm_default():
            DEFAULT_ADV_SETTINGS["user_prompt"] = self.edit_user_prompt.toPlainText()
            try:
                with open(CUSTOM_DEFAULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_ADV_SETTINGS, f, indent=4, ensure_ascii=False)
                btn_save_llm_default.setText("✓ 프롬프트 저장 완료")
                btn_save_llm_default.setStyleSheet(button_style("primary"))
                QTimer.singleShot(1500, lambda: [
                    btn_save_llm_default.setText("프롬프트 저장"),
                    btn_save_llm_default.setStyleSheet(button_style("toolbar"))
                ])
            except Exception:
                pass
        btn_save_llm_default.clicked.connect(save_llm_default)
        layout_llm.addWidget(btn_save_llm_default)
        
        self.tabs.addTab(tab_llm, "LLM 프롬프트")

        # 탭 7: 자막 품질 검사
        tab_quality = QWidget(); form_quality = QFormLayout(tab_quality)
        self.chk_subtitle_quality_enabled = QCheckBox("검사 기능 사용")
        self.chk_subtitle_quality_enabled.setChecked(bool(self.result.get("subtitle_quality_enabled", False)))
        self.chk_subtitle_quality_enabled.setStyleSheet(label_style("text", 12))
        form_quality.addRow("자막 품질 검사:", self.chk_subtitle_quality_enabled)

        self.chk_subtitle_quality_auto_check = QCheckBox("자막 생성 후 자동 검사")
        self.chk_subtitle_quality_auto_check.setChecked(bool(self.result.get("subtitle_quality_auto_check_after_generate", False)))
        self.chk_subtitle_quality_auto_check.setStyleSheet(label_style("text", 12))
        form_quality.addRow("자동 검사:", self.chk_subtitle_quality_auto_check)

        self.chk_subtitle_quality_auto_correct = QCheckBox("자동 교정 허용")
        self.chk_subtitle_quality_auto_correct.setChecked(bool(self.result.get("subtitle_quality_auto_correct_enabled", False)))
        self.chk_subtitle_quality_auto_correct.setStyleSheet(label_style("text", 12))
        form_quality.addRow("자동 교정:", self.chk_subtitle_quality_auto_correct)

        self.chk_correction_memory_enabled = QCheckBox("사용자 교정 memory 사용")
        self.chk_correction_memory_enabled.setChecked(bool(self.result.get("correction_memory_enabled", True)))
        self.chk_correction_memory_enabled.setStyleSheet(label_style("text", 12))
        form_quality.addRow("교정 memory:", self.chk_correction_memory_enabled)

        self.chk_wrong_answer_memory_enabled = QCheckBox("오답 memory 사용")
        self.chk_wrong_answer_memory_enabled.setChecked(bool(self.result.get("wrong_answer_memory_enabled", True)))
        self.chk_wrong_answer_memory_enabled.setStyleSheet(label_style("text", 12))
        form_quality.addRow("오답 memory:", self.chk_wrong_answer_memory_enabled)

        self._add_slider(
            form_quality,
            "review_auto_correct_apply_threshold",
            "자동 적용 최소 점수:",
            "<nobr>💡 자동 교정 후보가 이 점수 이상일 때만 적용합니다. 기본값: {default}</nobr>",
            70,
            100,
            DEFAULT_ADV_SETTINGS["review_auto_correct_apply_threshold"],
            1,
            "{} 점",
            show_disable=False,
        )
        self._add_slider(
            form_quality,
            "review_recheck_buffer_sec",
            "재검사 앞뒤 버퍼:",
            "<nobr>💡 낮은 점수 구간 재검사 후보를 만들 때 앞뒤로 포함할 시간입니다. 기본값: {default}</nobr>",
            5,
            30,
            DEFAULT_ADV_SETTINGS.get("review_recheck_buffer_sec", 1.2),
            10,
            "{:.1f} 초",
            show_disable=False,
        )
        self.tabs.addTab(tab_quality, "자막 품질")

        # 탭 8: 시스템
        tab_sys = QWidget(); form_sys = QFormLayout(tab_sys)

        self._add_slider(form_sys, "io_workers", "오디오 파일 복사 병렬 워커:", 
                         "<nobr>💡 안정적인 파일 처리를 위한 CPU 워커 수입니다.<br>➕ : 처리 속도가 빨라지나 램/CPU 점유율이 높아짐 (기본값: {default})<br>➖ : 프로그램 뻗는 현상 방지</nobr>", 
                         1, 16, DEFAULT_ADV_SETTINGS['io_workers'], 1, "{} 개", show_disable=False)
                         
        self._add_slider(form_sys, "llm_threads", "LLM 처리 스레드:", 
                         "<nobr>💡 로컬 LLM에서 사용할 동시 처리 스레드 수입니다.<br>➕ : 교정 속도가 빨라지나 메모리를 더 차지합니다. (기본값: {default})</nobr>", 
                         1, 16, DEFAULT_ADV_SETTINGS['llm_threads'], 1, "{} 개", show_disable=False)
        self.tabs.addTab(tab_sys, "시스템")

        layout.addWidget(self.tabs)
        
        self.chk_disable_all = QCheckBox("🎙️ 오디오 상세 설정 전체 '사용 안 함'")
        self.chk_disable_all.setStyleSheet(label_style("text", 13, bold=True) + "padding-bottom: 5px;")
        
        def toggle_all_disable():
            is_checked = self.chk_disable_all.isChecked()
            for slider, key, multiplier, chk_disable in self.sliders_info:
                if key not in ["io_workers", "llm_threads"] and chk_disable is not None: 
                    chk_disable.setChecked(is_checked)
                    
        self.chk_disable_all.stateChanged.connect(toggle_all_disable)
        
        chk_layout = QHBoxLayout()
        chk_layout.addStretch()  
        chk_layout.addWidget(self.chk_disable_all)
        layout.addLayout(chk_layout)
        # 💡 [교정] save_def_callback이 포함된 새 코드를 함수 안으로 옮겼습니다.
        layout.addLayout(_create_bottom_buttons(self, self._on_ok, self._on_reset, self._on_save, save_def_callback=self._on_save_default))

                
    def _on_audio_preset_changed(self, *args):
        preset_name = self.combo_audio_preset.currentData()
        if not preset_name:
            self.result["audio_preset"] = ""
            return
        self.result = apply_audio_preset(self.result, preset_name)
        for slider, key, multiplier, chk_disable in self.sliders_info:
            if key in self.result:
                try:
                    slider.setValue(int(float(self.result[key]) * multiplier))
                except Exception:
                    pass
            if chk_disable is not None and f"{key}_disabled" in self.result:
                chk_disable.setChecked(bool(self.result.get(f"{key}_disabled", False)))

    def _add_slider(self, form, key, title, tip_template, min_val, max_val, default_actual, multiplier, format_str, show_disable=True):
        h_layout = QHBoxLayout()
        
        cur_default_actual = DEFAULT_ADV_SETTINGS.get(key, default_actual)
        cur_default_str = format_str.format(cur_default_actual)
        help_icon = self._create_help_icon(tip_template.format(default=cur_default_str))
        h_layout.addWidget(help_icon)
        
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        
        cur_actual = self.result.get(key, cur_default_actual)
        cur_slider_val = int(cur_actual * multiplier)
        slider.setValue(cur_slider_val)
        
        label = QLabel(format_str.format(cur_slider_val / multiplier))
        label.setMinimumWidth(55)
        
        def on_change(v, lbl=label, fmt=format_str, m=multiplier, k=key):
            actual_v = v / m
            lbl.setText(fmt.format(actual_v))
            self.result[k] = actual_v

        slider.valueChanged.connect(on_change)
        
        btn_minus = QPushButton("-")
        btn_plus = QPushButton("+")
        btn_style = button_style("toolbar", font_size="12px", padding="2px 6px") + " QPushButton { min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; }"
        btn_minus.setStyleSheet(btn_style); btn_plus.setStyleSheet(btn_style)
        btn_minus.clicked.connect(lambda: slider.setValue(slider.value() - 1))
        btn_plus.clicked.connect(lambda: slider.setValue(slider.value() + 1))
        
        h_layout.addWidget(btn_minus)
        h_layout.addWidget(slider)
        h_layout.addWidget(btn_plus)
        h_layout.addWidget(label)
        
        chk_disable_ref = None
        
        if show_disable:
            chk_disable = QCheckBox("사용 안 함")
            chk_disable.setStyleSheet(label_style("muted", 11) + "margin-left: 5px; margin-right: 5px;")
            
            def toggle_disable():
                is_disabled = chk_disable.isChecked()
                slider.setVisible(not is_disabled)
                btn_minus.setVisible(not is_disabled)
                btn_plus.setVisible(not is_disabled)
                label.setVisible(not is_disabled)
                self.result[f"{key}_disabled"] = is_disabled

            chk_disable.stateChanged.connect(lambda state: toggle_disable())
            is_disabled_init = self.result.get(f"{key}_disabled", False)
            chk_disable.setChecked(is_disabled_init)
            toggle_disable()
            
            h_layout.addWidget(chk_disable)
            chk_disable_ref = chk_disable

        btn_set_default = QPushButton("기본값 저장")
        btn_set_default.setStyleSheet(button_style("toolbar", font_size="11px", padding="2px 6px"))
        
        def set_as_default():
            current_val = slider.value() / multiplier
            DEFAULT_ADV_SETTINGS[key] = current_val
            
            try:
                with open(CUSTOM_DEFAULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_ADV_SETTINGS, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
                
            new_default_str = format_str.format(current_val)
            help_icon.tip = tip_template.format(default=new_default_str)
            
            btn_set_default.setText("✓ 저장됨")
            btn_set_default.setStyleSheet(button_style("primary", font_size="11px", padding="2px 6px"))
            QTimer.singleShot(1500, lambda: [
                btn_set_default.setText("기본값 저장"),
                btn_set_default.setStyleSheet(button_style("toolbar", font_size="11px", padding="2px 6px"))
            ])
            
        btn_set_default.clicked.connect(set_as_default)
        h_layout.addWidget(btn_set_default)
        
        form.addRow(title, h_layout)
        self.sliders_info.append((slider, key, multiplier, chk_disable_ref))

    def _create_help_icon(self, tooltip_text):
        class HoverLabel(QLabel):
            def __init__(self, tip):
                super().__init__("❓")
                self.tip = tip
                self.setStyleSheet("""
                    QLabel { font-size: 14px; background: transparent; margin-right: 5px; }
                    QToolTip { background-color: #000000; color: #FFFFFF; border: 1px solid #666666; padding: 8px; font-size: 13px; white-space: nowrap; }
                """)
                self.setCursor(Qt.CursorShape.WhatsThisCursor)

            def enterEvent(self, event):
                QToolTip.showText(QCursor.pos(), self.tip, self)
                super().enterEvent(event)

            def leaveEvent(self, event):
                QToolTip.hideText()
                super().leaveEvent(event)

        return HoverLabel(tooltip_text)

    def _on_reset(self):
        for slider, key, multiplier, chk_disable in self.sliders_info:
            cur_default = DEFAULT_ADV_SETTINGS.get(key)
            if cur_default is not None:
                slider.setValue(int(cur_default * multiplier))
            if chk_disable:
                chk_disable.setChecked(False) 

    def _on_save(self):
        # [크PD] sliders_info에서 값 수집 후 저장
        for slider, key, multiplier, chk_disable in self.sliders_info:
            actual_v = slider.value() / multiplier
            self.result[key] = actual_v
            if chk_disable:
                self.result[f"{key}_disabled"] = chk_disable.isChecked()
        self.result["user_prompt"] = self.edit_user_prompt.toPlainText()
        self.result["audio_preset"] = self.combo_audio_preset.currentData() or ""
        self._collect_quality_settings()
        if "hf_token" in self.result: del self.result["hf_token"]
        if "llm_prompt" in self.result: del self.result["llm_prompt"]
        save_settings(self.result)
        self.accept()

    def _on_save_default(self):
        # 💡 [완성] 프롬프트까지 포함하여 전체 설정을 기본값으로 저장합니다.
        self.result["user_prompt"] = self.edit_user_prompt.toPlainText()
        self.result["audio_preset"] = self.combo_audio_preset.currentData() or ""
        self._collect_quality_settings()
        
        # 찌꺼기 데이터 정리
        if "hf_token" in self.result: del self.result["hf_token"]
        if "llm_prompt" in self.result: del self.result["llm_prompt"]
        
        save_default_settings(self.result)
        QMessageBox.information(self, "완료", "현재 오디오/엔진 설정을 시스템 기본값으로 저장했습니다.")
    def _on_ok(self):
        self.result["user_prompt"] = self.edit_user_prompt.toPlainText()
        self.result["audio_preset"] = self.combo_audio_preset.currentData() or ""
        self._collect_quality_settings()
        
        if "hf_token" in self.result:
            del self.result["hf_token"]
            
        if "llm_prompt" in self.result:
            del self.result["llm_prompt"]
        self.accept()

    def _collect_quality_settings(self):
        self.result["subtitle_quality_enabled"] = bool(self.chk_subtitle_quality_enabled.isChecked())
        self.result["subtitle_quality_auto_check_after_generate"] = bool(self.chk_subtitle_quality_auto_check.isChecked())
        self.result["subtitle_quality_auto_correct_enabled"] = bool(self.chk_subtitle_quality_auto_correct.isChecked())
        self.result["correction_memory_enabled"] = bool(self.chk_correction_memory_enabled.isChecked())
        self.result["wrong_answer_memory_enabled"] = bool(self.chk_wrong_answer_memory_enabled.isChecked())
