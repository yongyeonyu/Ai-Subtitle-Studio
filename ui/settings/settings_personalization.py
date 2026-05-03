from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

import config
from core.personalization.text_lora_dataset import (
    TEXT_LORA_DATASET_DIR,
    TEXT_LORA_CORPUS_PATH,
    TEXT_LORA_CORPUS_MANIFEST_PATH,
    VOICE_LORA_BRIDGE_PATH,
    accumulate_personalization_dataset,
    build_text_lora_dataset,
    export_text_lora_dataset,
)
from core.personalization.text_lora_runner import (
    TEXT_LORA_TRAINING_PLAN_PATH,
    VOICE_LORA_PROFILE_MANIFEST_PATH,
    save_text_lora_training_plan,
    save_voice_lora_profile_manifest,
)
from ui.style import button_style, settings_dialog_stylesheet


class PersonalizationLearningDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("개인화 학습")
        self.setMinimumWidth(560)
        self.setStyleSheet(settings_dialog_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("<b style='font-size:15px;'>텍스트 LoRA 준비 단계</b>")
        layout.addWidget(title)

        if not config.IS_MAC:
            warn = QLabel("현재 이 메뉴는 macOS 우선 구축 단계입니다.")
            layout.addWidget(warn)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.btn_refresh = QPushButton("현황 새로고침")
        self.btn_refresh.setStyleSheet(button_style("toolbar"))
        self.btn_refresh.clicked.connect(self._refresh_summary)
        layout.addWidget(self.btn_refresh)

        self.btn_export = QPushButton("텍스트 LoRA 데이터셋 내보내기")
        self.btn_export.setStyleSheet(button_style("primary"))
        self.btn_export.clicked.connect(self._export_dataset)
        layout.addWidget(self.btn_export)

        self.btn_accumulate = QPushButton("개인화 코퍼스 누적")
        self.btn_accumulate.setStyleSheet(button_style("toolbar"))
        self.btn_accumulate.clicked.connect(self._accumulate_now)
        layout.addWidget(self.btn_accumulate)

        self.btn_plan = QPushButton("맥 텍스트 LoRA 학습 프레임 생성")
        self.btn_plan.setStyleSheet(button_style("toolbar"))
        self.btn_plan.clicked.connect(self._build_training_plan)
        layout.addWidget(self.btn_plan)

        self.btn_voice_manifest = QPushButton("음성 LoRA 연계 Manifest 생성")
        self.btn_voice_manifest.setStyleSheet(button_style("toolbar"))
        self.btn_voice_manifest.clicked.connect(self._build_voice_manifest)
        layout.addWidget(self.btn_voice_manifest)

        self.btn_close = QPushButton("닫기")
        self.btn_close.setStyleSheet(button_style("toolbar"))
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)

        self._refresh_summary()

    def _refresh_summary(self):
        current_segments, current_project_path = self._current_editor_segments()
        payload = build_text_lora_dataset(
            current_segments=current_segments,
            current_project_path=current_project_path,
        )
        stats = payload.get("stats", {}) or {}
        self.summary_label.setText(
            "\n".join(
                [
                    f"총 학습 항목: {int(stats.get('total_items', 0) or 0)}개",
                    f"- 교정사전: {int(stats.get('legacy_corrections', 0) or 0)}개",
                    f"- 교정 memory: {int(stats.get('correction_memory', 0) or 0)}개",
                    f"- 오답 memory: {int(stats.get('wrong_answer_memory', 0) or 0)}개",
                    f"- 프로젝트 STT→최종 pair: {int(stats.get('project_segment_pairs', 0) or 0)}개",
                    f"- 스캔 프로젝트 수: {int(stats.get('project_files_scanned', 0) or 0)}개",
                    f"- 제외(short/long/low-delta): "
                    f"{int(stats.get('project_pairs_filtered_short_input', 0) or 0) + int(stats.get('project_pairs_filtered_short_output', 0) or 0)}/"
                    f"{int(stats.get('project_pairs_filtered_too_long', 0) or 0)}/"
                    f"{int(stats.get('project_pairs_filtered_low_delta', 0) or 0)}개",
                ]
            )
        )
        self.path_label.setText(f"출력 폴더: {TEXT_LORA_DATASET_DIR}")
        self.path_label.setText(
            "\n".join(
                [
                    f"출력 폴더: {TEXT_LORA_DATASET_DIR}",
                    f"자동 누적 코퍼스: {TEXT_LORA_CORPUS_PATH}",
                    f"음성 LoRA 브리지: {VOICE_LORA_BRIDGE_PATH}",
                    f"학습 프레임: {TEXT_LORA_TRAINING_PLAN_PATH}",
                    f"음성 Manifest: {VOICE_LORA_PROFILE_MANIFEST_PATH}",
                ]
            )
        )

    def _export_dataset(self):
        current_segments, current_project_path = self._current_editor_segments()
        result = export_text_lora_dataset(
            current_segments=current_segments,
            current_project_path=current_project_path,
        )
        self._refresh_summary()
        QMessageBox.information(
            self,
            "완료",
            "\n".join(
                [
                    "텍스트 LoRA 데이터셋 내보내기 완료",
                    f"JSONL: {result['dataset_path']}",
                    f"Manifest: {result['manifest_path']}",
                    f"총 항목: {int((result.get('stats') or {}).get('total_items', 0) or 0)}개",
                ]
            ),
        )

    def _build_training_plan(self):
        result = save_text_lora_training_plan()
        QMessageBox.information(
            self,
            "완료",
            "\n".join(
                [
                    "맥 텍스트 LoRA 학습 프레임 생성 완료",
                    f"Backend: {result['backend']}",
                    f"사용 가능 row: {int(result['usable_rows'])}개",
                    f"Plan: {result['plan_path']}",
                    f"Output: {result['output_dir']}",
                ]
            ),
        )

    def _build_voice_manifest(self):
        result = save_voice_lora_profile_manifest()
        QMessageBox.information(
            self,
            "완료",
            "\n".join(
                [
                    "음성 LoRA 연계 Manifest 생성 완료",
                    f"화자 프로필 수: {int(result['speaker_profiles'])}개",
                    f"Manifest: {result['manifest_path']}",
                ]
            ),
        )

    def _accumulate_now(self):
        current_segments, current_project_path = self._current_editor_segments()
        result = accumulate_personalization_dataset(
            current_segments=current_segments,
            current_project_path=current_project_path,
            trigger="dialog_manual_accumulate",
        )
        self._refresh_summary()
        QMessageBox.information(
            self,
            "완료",
            "\n".join(
                [
                    "개인화 코퍼스 누적 완료",
                    f"텍스트 추가: {int(result.get('appended_rows', 0) or 0)}개",
                    f"음성 브리지 추가: {int(result.get('voice_bridge_rows', 0) or 0)}개",
                    f"Manifest: {TEXT_LORA_CORPUS_MANIFEST_PATH}",
                ]
            ),
        )

    def _current_editor_segments(self):
        owner = self.parent()
        editor = None
        if owner is not None and hasattr(owner, "_active_editor"):
            try:
                editor = owner._active_editor()
            except Exception:
                editor = None
        if editor is None or not hasattr(editor, "_get_current_segments"):
            return [], str(getattr(owner, "_current_project_path", "") or "")
        try:
            segments = [dict(seg) for seg in list(editor._get_current_segments() or []) if not seg.get("is_gap")]
        except Exception:
            segments = []
        project_path = str(getattr(owner, "_current_project_path", "") or "")
        return segments, project_path
