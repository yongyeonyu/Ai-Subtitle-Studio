from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

from core.runtime import config
from core.personalization.text_lora_dataset import (
    TEXT_LORA_DATASET_PATH,
    TEXT_LORA_DATASET_DIR,
    TEXT_LORA_MANIFEST_PATH,
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

        self.btn_refresh = QPushButton("현황")
        self.btn_refresh.setStyleSheet(button_style("toolbar"))
        self.btn_refresh.clicked.connect(self._refresh_summary)
        layout.addWidget(self.btn_refresh)

        self.btn_update = QPushButton("업데이트")
        self.btn_update.setStyleSheet(button_style("primary"))
        self.btn_update.clicked.connect(self._update_personalization_assets)
        layout.addWidget(self.btn_update)

        self.btn_delete = QPushButton("삭제")
        self.btn_delete.setStyleSheet(button_style("danger"))
        self.btn_delete.clicked.connect(self._delete_personalization_assets)
        layout.addWidget(self.btn_delete)

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
                    f"교정사전 {int(stats.get('legacy_corrections', 0) or 0)}개 · "
                    f"교정 memory {int(stats.get('correction_memory', 0) or 0)}개 · "
                    f"오답 memory {int(stats.get('wrong_answer_memory', 0) or 0)}개",
                    f"프로젝트 자막 pair {int(stats.get('project_segment_pairs', 0) or 0)}개 · "
                    f"스캔 프로젝트 {int(stats.get('project_files_scanned', 0) or 0)}개",
                    f"제외 항목 short/long/low-delta: "
                    f"{int(stats.get('project_pairs_filtered_short_input', 0) or 0) + int(stats.get('project_pairs_filtered_short_output', 0) or 0)}/"
                    f"{int(stats.get('project_pairs_filtered_too_long', 0) or 0)}/"
                    f"{int(stats.get('project_pairs_filtered_low_delta', 0) or 0)}개",
                ]
            )
        )
        self.path_label.setText(
            "\n".join(
                [
                    f"출력 폴더: {TEXT_LORA_DATASET_DIR}",
                    f"업데이트 대상: {TEXT_LORA_DATASET_PATH.name}, {TEXT_LORA_CORPUS_PATH.name}, "
                    f"{VOICE_LORA_BRIDGE_PATH.name}, {TEXT_LORA_TRAINING_PLAN_PATH.name}, {VOICE_LORA_PROFILE_MANIFEST_PATH.name}",
                ]
            )
        )

    def _update_personalization_assets(self):
        current_segments, current_project_path = self._current_editor_segments()
        export_result = export_text_lora_dataset(
            current_segments=current_segments,
            current_project_path=current_project_path,
        )
        accumulate_result = accumulate_personalization_dataset(
            current_segments=current_segments,
            current_project_path=current_project_path,
            trigger="dialog_update",
        )
        plan_result = save_text_lora_training_plan()
        voice_result = save_voice_lora_profile_manifest()
        self._refresh_summary()
        QMessageBox.information(
            self,
            "완료",
            "\n".join(
                [
                    "개인화 데이터 업데이트 완료",
                    f"학습 데이터셋: {int((export_result.get('stats') or {}).get('total_items', 0) or 0)}개",
                    f"코퍼스 누적: 텍스트 {int(accumulate_result.get('appended_rows', 0) or 0)}개 / 음성 {int(accumulate_result.get('voice_bridge_rows', 0) or 0)}개",
                    f"학습 프레임 사용 가능 row: {int(plan_result.get('usable_rows', 0) or 0)}개",
                    f"음성 프로필 수: {int(voice_result.get('speaker_profiles', 0) or 0)}개",
                ]
            ),
        )

    def _delete_personalization_assets(self):
        reply = QMessageBox.question(
            self,
            "삭제 확인",
            "개인화 학습 산출물만 삭제합니다.\n교정사전/교정 memory/오답 memory 원본은 삭제하지 않습니다.\n계속하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        for path in (
            TEXT_LORA_DATASET_PATH,
            TEXT_LORA_MANIFEST_PATH,
            TEXT_LORA_CORPUS_PATH,
            TEXT_LORA_CORPUS_MANIFEST_PATH,
            VOICE_LORA_BRIDGE_PATH,
            TEXT_LORA_TRAINING_PLAN_PATH,
            VOICE_LORA_PROFILE_MANIFEST_PATH,
        ):
            target = Path(path)
            try:
                if target.exists():
                    target.unlink()
                    deleted += 1
            except Exception:
                continue

        self._refresh_summary()
        QMessageBox.information(self, "완료", f"개인화 학습 산출물 {deleted}개를 삭제했습니다.")

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
