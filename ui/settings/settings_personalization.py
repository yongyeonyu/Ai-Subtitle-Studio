from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.personalization.ground_truth_import import (
    import_ground_truth_pairs,
    pair_ground_truth_assets,
    resolve_ambiguous_matches,
)
from core.personalization.idle_trainer import (
    enqueue_default_training_jobs,
    enqueue_full_training_jobs,
    format_training_queue_status_summary,
    recover_interrupted_training_jobs,
)
from core.personalization.lora_rule_learning import (
    apply_split_rule_update_review,
    build_split_rule_update_review,
    learn_rules_from_truth_table,
)
from core.personalization.lora_storage import (
    LORA_PERSONALIZATION_DIR,
    clear_training_queue,
    initialize_lora_personalization_store,
    load_training_queue,
    refresh_unified_lora_data_bundle,
    store_paths,
)
from core.personalization.lora_store_bundle import refresh_lora_personalization_manifest  # noqa: F401
from core.personalization.lora_store_common import read_json
from core.personalization.lora_vector_retriever import build_lora_retrieval_index
from core.personalization.text_lora_dataset import (
    accumulate_personalization_dataset,
    build_text_lora_dataset,  # noqa: F401
    export_text_lora_dataset,
)
from core.personalization.text_lora_runner import (
    save_text_lora_training_plan,
    save_voice_lora_profile_manifest,
    save_voice_lora_training_plan,
)
from core.personalization.stt1_whisper_adapter_runner import save_stt1_whisper_adapter_training_plan
from ui.settings.personalization_learning_actions import (
    PersonalizationLearningActionsMixin,
    VoiceLoraDatasetWorker,
)
from ui.settings.personalization_learning_info import (
    PersonalizationLearningInfoDialog,
    preview_text as _preview_text,
)
from ui.settings.tablet_dialog import apply_tablet_dialog_profile
from ui.style import COLORS, settings_button_style, settings_dialog_stylesheet


def _compact_button_style(kind: str = "toolbar") -> str:
    if kind == "primary":
        return settings_button_style("primary", font_size="13px", min_width=108, min_height=42)
    if kind == "danger":
        return settings_button_style("danger", font_size="12px", min_width=108, min_height=42)
    return settings_button_style("toolbar", font_size="12px", min_width=96, min_height=42)


def _learning_dialog_stylesheet() -> str:
    accent = COLORS["accent"]
    primary = COLORS["primary"]
    surface = COLORS["surface"]
    surface_alt = COLORS["surface_alt"]
    separator = COLORS["separator"]
    text = COLORS["text"]
    muted = COLORS["muted"]
    return (
        f"#personalizationLearningDialog {{ background: {COLORS['bg']}; }}"
        "#personalizationHeroCard {"
        "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #122028, stop:1 #0F171B);"
        f"border: 1px solid {separator}; border-radius: 16px;"
        "}"
        "#personalizationHeroEyebrow {"
        f"color: {accent}; font-size: 11px; font-weight: 800; letter-spacing: 1px;"
        "}"
        "#personalizationHeroTitle {"
        f"color: {text}; font-size: 28px; font-weight: 900;"
        "}"
        "#personalizationHeroSubtitle {"
        f"color: #D7E1E8; font-size: 14px; font-weight: 600;"
        "}"
        "#personalizationRuleHint {"
        f"color: #AFC1CD; font-size: 12px; font-weight: 700;"
        "}"
        "#personalizationInfoPill {"
        "background: rgba(52, 199, 89, 0.12);"
        f"border: 1px solid rgba(52, 199, 89, 0.45); color: #DDF9E5;"
        "border-radius: 10px; padding: 7px 12px; font-size: 12px; font-weight: 800;"
        "}"
        "#personalizationSectionCard, #personalizationStatusCard, #personalizationManageCard {"
        f"background: {surface}; border: 1px solid {separator}; border-radius: 16px;"
        "}"
        "#personalizationSectionTitle {"
        f"color: {text}; font-size: 17px; font-weight: 900;"
        "}"
        "#personalizationSectionHint {"
        f"color: {muted}; font-size: 12px; font-weight: 700;"
        "}"
        "#personalizationDropZone {"
        f"background: {surface_alt}; border: 1px dashed #4E6675; border-radius: 16px;"
        "}"
        "#personalizationDropZone QLabel { background: transparent; }"
        "#personalizationDropTitle {"
        f"color: {text}; font-size: 17px; font-weight: 900;"
        "}"
        "#personalizationDropHint {"
        f"color: #AFC1CD; font-size: 13px; font-weight: 700;"
        "}"
        "#personalizationPairList {"
        f"background: #0E1519; border: 1px solid #27353E; border-radius: 14px;"
        "padding: 8px; outline: 0;"
        "}"
        "#personalizationPairList::item {"
        "padding: 8px 10px; border-radius: 10px; margin: 2px 0;"
        f"color: {text};"
        "}"
        "#personalizationPairList::item:selected {"
        "background: rgba(0, 122, 255, 0.16);"
        f"border: 1px solid {primary};"
        "}"
        "#personalizationQueueLabel {"
        "background: rgba(0, 122, 255, 0.10);"
        f"border: 1px solid rgba(0, 122, 255, 0.32); color: #DCEBFF;"
        "border-radius: 12px; padding: 12px 14px; font-size: 13px; font-weight: 700;"
        "}"
        "#personalizationSummaryLabel {"
        f"color: #F1F6FA; font-size: 13px; font-weight: 700;"
        "}"
        "#personalizationPathLabel {"
        f"color: #AFC1CD; font-size: 12px; font-weight: 700;"
        "}"
        "#personalizationAutoNote {"
        f"color: {muted}; font-size: 12px; font-weight: 700;"
        "}"
    )


QUEUE_STATUS_LABELS = {
    "waiting": "대기",
    "in_progress": "실행중",
    "complete": "완료",
    "partial": "부분완료",
    "failed": "실패",
    "skipped": "건너뜀",
    "paused": "일시정지",
}
QUEUE_JOB_TYPE_LABELS = {
    "analyze_truth_table": "truth 분석",
    "build_text_training_plan": "text 학습계획",
    "build_voice_profiles": "목소리 프로필",
    "build_stt1_whisper_adapter": "STT1 어댑터",
    "build_retrieval_index": "검색 인덱스",
    "optimize_settings": "설정 최적화",
    "optimize_prompts": "프롬프트 최적화",
}


def _queue_status_label(status: Any) -> str:
    text = str(status or "waiting")
    return QUEUE_STATUS_LABELS.get(text, text)


def _queue_job_type_label(job_type: Any) -> str:
    text = str(job_type or "-")
    return QUEUE_JOB_TYPE_LABELS.get(text, text)


class PersonalizationLearningDialog(PersonalizationLearningActionsMixin, QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("개인화 학습")
        self.setObjectName("personalizationLearningDialog")
        self.setMinimumWidth(760)
        self.setMinimumHeight(620)
        apply_tablet_dialog_profile(self)
        self.setStyleSheet(settings_dialog_stylesheet() + _learning_dialog_stylesheet())
        self.setAcceptDrops(True)
        self._staged_inputs: list[str] = []
        self._paired_assets: list[dict] = []
        self._ambiguous_assets: list[dict] = []
        self._pending_queue_batch_active = False
        self._pending_queue_batch_silent = False
        self._pending_queue_batch_started = 0
        self._pending_queue_batch_limit = 64
        self._pending_queue_batch_manual_full = False
        self._pending_queue_batch_stop_requested = False
        self._pending_queue_batch_timer = QTimer(self)
        self._pending_queue_batch_timer.setSingleShot(True)
        self._pending_queue_batch_timer.timeout.connect(self._drain_pending_jobs_step)
        self._summary_refresh_timer = QTimer(self)
        self._summary_refresh_timer.setInterval(80)
        self._summary_refresh_timer.timeout.connect(self._poll_summary_refresh)
        self._summary_refresh_thread: threading.Thread | None = None
        self._summary_refresh_result: dict | None = None
        self._voice_lora_worker: VoiceLoraDatasetWorker | None = None
        self._personalization_store_initialized = False
        owner = self.parent()
        if owner is not None and hasattr(owner, "_register_personalization_learning_dialog"):
            try:
                owner._register_personalization_learning_dialog(self)
                self.destroyed.connect(lambda *_: owner._unregister_personalization_learning_dialog(self))
            except Exception:
                pass

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        body_scroll.setWidget(body)
        layout.addWidget(body_scroll, 1)

        hero_card = QFrame()
        hero_card.setObjectName("personalizationHeroCard")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(18, 16, 18, 16)
        hero_layout.setSpacing(10)

        hero_eyebrow = QLabel("PERSONALIZATION LAB")
        hero_eyebrow.setObjectName("personalizationHeroEyebrow")
        hero_layout.addWidget(hero_eyebrow)

        title = QLabel("개인화 학습")
        title.setObjectName("personalizationHeroTitle")
        hero_layout.addWidget(title)

        subtitle = QLabel(
            "영상과 SRT를 함께 넣으면 자막 스타일, 자주 고치는 표현, 줄바꿈 규칙, STT 보정 패턴을 자동으로 정리합니다."
        )
        subtitle.setObjectName("personalizationHeroSubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(subtitle)

        rule_hint = QLabel("학습 규칙: (), [], {} 안의 설명 자막은 학습 데이터에서 자동 제외합니다.")
        rule_hint.setObjectName("personalizationRuleHint")
        rule_hint.setWordWrap(True)
        hero_layout.addWidget(rule_hint)

        info_pill = QLabel("영상과 SRT를 한 번에 넣어도 자동 pair를 찾아 학습 큐를 구성합니다.")
        info_pill.setObjectName("personalizationInfoPill")
        info_pill.setWordWrap(True)
        hero_layout.addWidget(info_pill)
        body_layout.addWidget(hero_card)

        ingest_card = QFrame()
        ingest_card.setObjectName("personalizationSectionCard")
        ingest_layout = QVBoxLayout(ingest_card)
        ingest_layout.setContentsMargins(16, 16, 16, 16)
        ingest_layout.setSpacing(12)

        ingest_title = QLabel("입력")
        ingest_title.setObjectName("personalizationSectionTitle")
        ingest_layout.addWidget(ingest_title)

        ingest_hint = QLabel("파일이나 폴더를 추가하면 영상과 자막을 묶어서 바로 학습 대기열에 올립니다.")
        ingest_hint.setObjectName("personalizationSectionHint")
        ingest_hint.setWordWrap(True)
        ingest_layout.addWidget(ingest_hint)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("personalizationDropZone")
        self.drop_zone.setMinimumHeight(132)
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(18, 18, 18, 18)
        drop_layout.setSpacing(8)
        drop_title = QLabel("영상 + SRT 끌어다 놓기")
        drop_title.setObjectName("personalizationDropTitle")
        drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(drop_title)
        drop_hint = QLabel("여러 파일이나 폴더를 한 번에 넣어도 자동으로 pair를 찾습니다.")
        drop_hint.setObjectName("personalizationDropHint")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setWordWrap(True)
        drop_layout.addWidget(drop_hint)
        ingest_layout.addWidget(self.drop_zone)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        self.btn_add_learning_files = QPushButton("파일 추가")
        self.btn_add_learning_files.setStyleSheet(_compact_button_style("toolbar"))
        self.btn_add_learning_files.clicked.connect(self._add_learning_files)
        quick_row.addWidget(self.btn_add_learning_files, 1)

        self.btn_add_learning_folder = QPushButton("폴더 추가")
        self.btn_add_learning_folder.setStyleSheet(_compact_button_style("toolbar"))
        self.btn_add_learning_folder.clicked.connect(self._add_folder)
        quick_row.addWidget(self.btn_add_learning_folder, 1)

        self.btn_start_auto_learning = QPushButton("학습 시작")
        self.btn_start_auto_learning.setStyleSheet(_compact_button_style("primary"))
        self.btn_start_auto_learning.clicked.connect(self._start_full_learning)
        quick_row.addWidget(self.btn_start_auto_learning, 1)

        self.btn_stop_full_learning = QPushButton("학습 종료")
        self.btn_stop_full_learning.setStyleSheet(_compact_button_style("toolbar"))
        self.btn_stop_full_learning.clicked.connect(self._stop_full_learning)
        self.btn_stop_full_learning.setEnabled(False)
        quick_row.addWidget(self.btn_stop_full_learning, 1)
        ingest_layout.addLayout(quick_row)
        body_layout.addWidget(ingest_card)

        status_card = QFrame()
        status_card.setObjectName("personalizationStatusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setSpacing(12)

        list_title = QLabel("자동 pair 확인")
        list_title.setObjectName("personalizationSectionTitle")
        status_layout.addWidget(list_title)
        self.pair_list = QListWidget()
        self.pair_list.setObjectName("personalizationPairList")
        self.pair_list.setMinimumHeight(160)
        self.pair_list.setMaximumHeight(240)
        self.pair_list.setAlternatingRowColors(False)
        status_layout.addWidget(self.pair_list, stretch=1)

        self.queue_summary_label = QLabel("")
        self.queue_summary_label.setObjectName("personalizationQueueLabel")
        self.queue_summary_label.setWordWrap(True)
        status_layout.addWidget(self.queue_summary_label)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("personalizationSummaryLabel")
        self.summary_label.setWordWrap(True)
        status_layout.addWidget(self.summary_label)

        self.path_label = QLabel("")
        self.path_label.setObjectName("personalizationPathLabel")
        self.path_label.setWordWrap(True)
        status_layout.addWidget(self.path_label)

        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        info_row.addStretch(1)
        self.btn_learning_info = QPushButton("학습 정보")
        self.btn_learning_info.setStyleSheet(_compact_button_style("primary"))
        self.btn_learning_info.clicked.connect(self._open_learning_info)
        info_row.addWidget(self.btn_learning_info)
        status_layout.addLayout(info_row)
        body_layout.addWidget(status_card)

        manage_card = QFrame()
        manage_card.setObjectName("personalizationManageCard")
        manage_layout = QVBoxLayout(manage_card)
        manage_layout.setContentsMargins(16, 16, 16, 16)
        manage_layout.setSpacing(12)

        manage_title = QLabel("관리")
        manage_title.setObjectName("personalizationSectionTitle")
        manage_layout.addWidget(manage_title)

        manage_hint = QLabel("백업 불러오기, 삭제 예정 데이터 정리, 전체 학습 재시작을 여기서 관리합니다.")
        manage_hint.setObjectName("personalizationSectionHint")
        manage_hint.setWordWrap(True)
        manage_layout.addWidget(manage_hint)

        manage_row = QHBoxLayout()
        manage_row.setSpacing(8)

        self.btn_import_unified_lora = QPushButton("LoRA 백업 불러오기")
        self.btn_import_unified_lora.setStyleSheet(_compact_button_style("toolbar"))
        self.btn_import_unified_lora.clicked.connect(self._import_unified_lora_data_now)
        manage_row.addWidget(self.btn_import_unified_lora, 1)

        self.btn_delete_pending_lora = QPushButton("삭제예정 LoRA 비우기")
        self.btn_delete_pending_lora.setStyleSheet(_compact_button_style("danger"))
        self.btn_delete_pending_lora.clicked.connect(self._delete_pending_lora_data_now)
        manage_row.addWidget(self.btn_delete_pending_lora, 1)

        self.btn_reset_all = QPushButton("처음부터 다시 학습")
        self.btn_reset_all.setStyleSheet(_compact_button_style("danger"))
        self.btn_reset_all.clicked.connect(self._reset_lora_learning_store_now)
        manage_row.addWidget(self.btn_reset_all, 1)
        manage_layout.addLayout(manage_row)

        self.auto_note = QLabel(
            "평소에는 홈/편집 대기 시간에 조용히 자동 학습합니다. '학습 시작'은 전체 큐를 즉시 다시 돌리고, '학습 종료'는 수동 학습을 멈춘 뒤 백그라운드 자동 학습으로 돌립니다."
        )
        self.auto_note.setObjectName("personalizationAutoNote")
        self.auto_note.setWordWrap(True)
        manage_layout.addWidget(self.auto_note)
        body_layout.addWidget(manage_card)

        self.advanced_scroll = None
        self.inspect_box = None
        self.btn_run_queue = None
        self.btn_build_voice_lora = None

        body_layout.addStretch(1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        self.btn_close = QPushButton("닫기")
        self.btn_close.setStyleSheet(_compact_button_style("toolbar"))
        self.btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(self.btn_close)
        layout.addLayout(bottom_row)

        self._refresh_pair_preview()
        self._set_summary_loading()
        QTimer.singleShot(80, self._refresh_summary_deferred)

    def _store_paths(self):
        return store_paths(LORA_PERSONALIZATION_DIR)

    def _manifest_fast(self) -> dict:
        try:
            manifest = read_json(self._store_paths().get("manifest"), {})
        except Exception:
            manifest = {}
        return manifest if isinstance(manifest, dict) else {}

    def _set_summary_loading(self):
        self.summary_label.setText("학습 데이터: 불러오는 중...")
        self.path_label.setText(
            f"가져온 입력 {len(self._staged_inputs)}개 · 자동 pair {len(self._paired_assets)}개 · 확인 필요 {len(self._ambiguous_assets)}개"
        )
        self.queue_summary_label.setText("자동 학습 상태: 확인 중...")

    def _ensure_personalization_store(self):
        if self._personalization_store_initialized:
            return None
        manifest = initialize_lora_personalization_store()
        self._personalization_store_initialized = True
        return manifest

    def _refresh_summary_deferred(self):
        if not self.isVisible():
            return
        self._start_summary_refresh_async()

    def _summary_snapshot(
        self,
        *,
        current_segments: list[dict],
        current_project_path: str,
        trainer_busy: bool,
        include_inspect: bool,
    ) -> dict:
        manifest = self._manifest_fast()
        counts = dict(manifest.get("counts") or {})
        queue_payload = load_training_queue()
        queue_items = list(queue_payload.get("items") or [])
        queue_counts: dict[str, int] = {}
        waiting_type_counts: dict[str, int] = {}
        running_lines: list[str] = []
        for item in queue_items:
            status = str(item.get("status") or "waiting")
            queue_counts[status] = int(queue_counts.get(status, 0) or 0) + 1
            if status == "waiting":
                job_type = str(item.get("job_type") or "")
                waiting_type_counts[job_type] = int(waiting_type_counts.get(job_type, 0) or 0) + 1
            if status == "in_progress":
                progress = max(0.0, min(1.0, float(item.get("progress", 0.0) or 0.0)))
                detail = _preview_text(item.get("last_error"), 82)
                line = f"{_queue_job_type_label(item.get('job_type'))} {progress * 100:.0f}%"
                if detail:
                    line += f" · {detail}"
                running_lines.append(line)

        queue_summary = format_training_queue_status_summary(queue_items)
        waiting_summary = " · ".join(
            f"{_queue_job_type_label(key)} {value}개"
            for key, value in sorted(waiting_type_counts.items(), key=lambda item: (_queue_job_type_label(item[0]), item[0]))
        )
        queue_lines = [f"자동 학습 상태: {queue_summary}"]
        if running_lines:
            queue_lines.append("실행중: " + " · ".join(running_lines[:2]))
        if waiting_summary:
            queue_lines.append(f"다음 자동 처리: {waiting_summary}")

        inspect_text = ""
        if include_inspect:
            review = build_split_rule_update_review()
            paths = self._store_paths()
            inspect_text = "\n".join(
                [
                    f"[Current Project] {current_project_path or '-'}",
                    f"[Queue] {queue_summary}",
                    f"[Split Rule Review] needs_update={review.get('needs_update')} / top_n={review.get('top_n')}",
                    f"current: {', '.join(review.get('current_rules', [])[:8])}",
                    f"proposed: {', '.join(review.get('proposed_rules', [])[:8])}",
                    f"[LLM Review] request={paths.get('llm_review_request')} / result={paths.get('llm_review_result')}",
                    "[Retention] 새 학습 후 낮은 점수 trial과 낮은 빈도 rule을 점진 정리합니다.",
                    f"[LoRA ZIP Files] 상={paths.get('unified_lora_data')} / 중={paths.get('lora_data_medium')} / 하={paths.get('lora_data_low')} / 삭제예정={paths.get('lora_data_pending_delete')}",
                    f"[LoRA Retrieval Index] {paths.get('lora_retrieval_index')}",
                    f"[Voice LoRA] {paths.get('voice_lora_training_plan')}",
                ]
            )

        return {
            "ok": True,
            "summary_text": (
                "학습 데이터: "
                f"truth {counts.get('truth_table_rows', 0)}행 · "
                f"설명 제외 {counts.get('excluded_parenthetical_rows', 0)}행 · "
                f"규칙 {counts.get('learned_split_rules', 0)}개/{counts.get('learned_line_break_rules', 0)}개 · "
                f"context {counts.get('multimodal_lora_context_rows', 0)}행 · "
                f"목소리 {counts.get('voice_lora_bridge_rows', 0)}구간 · "
                f"STT1 adapter {counts.get('stt1_whisper_adapter_training_items', 0)}개 · "
                f"코퍼스 {int(counts.get('text_lora_corpus_rows', counts.get('text_lora_dataset_rows', 0)) or 0)}개"
            ),
            "path_text": (
                f"가져온 입력 {len(self._staged_inputs)}개 · "
                f"자동 pair {len(self._paired_assets)}개 · "
                f"확인 필요 {len(self._ambiguous_assets)}개"
            ),
            "queue_text": "\n".join(queue_lines),
            "inspect_text": inspect_text,
        }

    def _apply_summary_snapshot(self, snapshot: dict):
        if not isinstance(snapshot, dict):
            return
        if not bool(snapshot.get("ok", False)):
            detail = str(snapshot.get("error") or "알 수 없는 오류")
            self.summary_label.setText(f"학습 데이터: 불러오기 실패 · {detail}")
            self.queue_summary_label.setText("자동 학습 상태: 확인 실패")
            return
        self._personalization_store_initialized = True
        self.summary_label.setText(str(snapshot.get("summary_text") or ""))
        self.path_label.setText(str(snapshot.get("path_text") or ""))
        self.queue_summary_label.setText(str(snapshot.get("queue_text") or ""))
        if self.inspect_box is not None and snapshot.get("inspect_text"):
            self.inspect_box.setPlainText(str(snapshot.get("inspect_text") or ""))

    def _start_summary_refresh_async(self):
        if self._summary_refresh_thread is not None and self._summary_refresh_thread.is_alive():
            return
        trainer = self._trainer()
        trainer_busy = bool(hasattr(trainer, "is_busy") and trainer.is_busy()) if trainer is not None else False
        current_segments, current_project_path = self._current_editor_segments()
        current_segments = [dict(seg) for seg in list(current_segments or []) if isinstance(seg, dict)]
        include_inspect = self.inspect_box is not None
        self._summary_refresh_result = None

        def _worker():
            try:
                self._summary_refresh_result = self._summary_snapshot(
                    current_segments=current_segments,
                    current_project_path=current_project_path,
                    trainer_busy=trainer_busy,
                    include_inspect=include_inspect,
                )
            except Exception as exc:
                self._summary_refresh_result = {"ok": False, "error": str(exc)}

        self._summary_refresh_thread = threading.Thread(
            target=_worker,
            name="personalization-summary-refresh",
            daemon=True,
        )
        self._summary_refresh_thread.start()
        self._summary_refresh_timer.start()

    def _poll_summary_refresh(self):
        thread = self._summary_refresh_thread
        if thread is not None and thread.is_alive() and self._summary_refresh_result is None:
            return
        self._summary_refresh_timer.stop()
        result = self._summary_refresh_result
        self._summary_refresh_result = None
        if result is not None and self.isVisible():
            self._apply_summary_snapshot(result)

    def _refresh_summary(self):
        current_segments, current_project_path = self._current_editor_segments()
        manifest = self._manifest_fast()
        counts = dict(manifest.get("counts") or {})
        queue_payload = load_training_queue()
        queue_items = list(queue_payload.get("items") or [])
        queue_counts: dict[str, int] = {}
        waiting_type_counts: dict[str, int] = {}
        running_lines: list[str] = []
        for item in queue_items:
            status = str(item.get("status") or "waiting")
            queue_counts[status] = int(queue_counts.get(status, 0) or 0) + 1
            if status == "waiting":
                job_type = str(item.get("job_type") or "")
                waiting_type_counts[job_type] = int(waiting_type_counts.get(job_type, 0) or 0) + 1
            if status == "in_progress":
                progress = max(0.0, min(1.0, float(item.get("progress", 0.0) or 0.0)))
                detail = _preview_text(item.get("last_error"), 82)
                line = f"{_queue_job_type_label(item.get('job_type'))} {progress * 100:.0f}%"
                if detail:
                    line += f" · {detail}"
                running_lines.append(line)

        self.summary_label.setText(
            "학습 데이터: "
            f"truth {counts.get('truth_table_rows', 0)}행 · "
            f"설명 제외 {counts.get('excluded_parenthetical_rows', 0)}행 · "
            f"규칙 {counts.get('learned_split_rules', 0)}개/{counts.get('learned_line_break_rules', 0)}개 · "
            f"context {counts.get('multimodal_lora_context_rows', 0)}행 · "
            f"목소리 {counts.get('voice_lora_bridge_rows', 0)}구간 · "
            f"STT1 adapter {counts.get('stt1_whisper_adapter_training_items', 0)}개 · "
            f"코퍼스 {int(counts.get('text_lora_corpus_rows', counts.get('text_lora_dataset_rows', 0)) or 0)}개"
        )

        self.path_label.setText(
            f"가져온 입력 {len(self._staged_inputs)}개 · 자동 pair {len(self._paired_assets)}개 · 확인 필요 {len(self._ambiguous_assets)}개"
        )

        queue_summary = format_training_queue_status_summary(queue_items)
        waiting_summary = " · ".join(
            f"{_queue_job_type_label(key)} {value}개"
            for key, value in sorted(waiting_type_counts.items(), key=lambda item: (_queue_job_type_label(item[0]), item[0]))
        )
        queue_lines = [f"자동 학습 상태: {queue_summary}"]
        if running_lines:
            queue_lines.append("실행중: " + " · ".join(running_lines[:2]))
        if waiting_summary:
            queue_lines.append(f"다음 자동 처리: {waiting_summary}")
        self.queue_summary_label.setText("\n".join(queue_lines))

        if self.inspect_box is not None:
            review = build_split_rule_update_review()
            self.inspect_box.setPlainText(
                "\n".join(
                    [
                        f"[Current Project] {current_project_path or '-'}",
                        f"[Queue] {queue_summary}",
                        f"[Split Rule Review] needs_update={review.get('needs_update')} / top_n={review.get('top_n')}",
                        f"current: {', '.join(review.get('current_rules', [])[:8])}",
                        f"proposed: {', '.join(review.get('proposed_rules', [])[:8])}",
                        f"[LLM Review] request={self._store_paths().get('llm_review_request')} / result={self._store_paths().get('llm_review_result')}",
                        "[Retention] 새 학습 후 낮은 점수 trial과 낮은 빈도 rule을 점진 정리합니다.",
                        f"[LoRA ZIP Files] 상={self._store_paths().get('unified_lora_data')} / 중={self._store_paths().get('lora_data_medium')} / 하={self._store_paths().get('lora_data_low')} / 삭제예정={self._store_paths().get('lora_data_pending_delete')}",
                        f"[LoRA Retrieval Index] {self._store_paths().get('lora_retrieval_index')}",
                        f"[Voice LoRA] {self._store_paths().get('voice_lora_training_plan')}",
                    ]
                )
            )

    def _refresh_pair_preview(self):
        self.pair_list.clear()
        result = pair_ground_truth_assets(self._staged_inputs)
        self._paired_assets = list(result.get("pairs") or [])
        self._ambiguous_assets = list(result.get("ambiguous_matches") or [])
        for item in self._paired_assets:
            self.pair_list.addItem(
                f"[{item.get('match_type', 'pair')}] {Path(str(item.get('media_path', ''))).name}  ->  {Path(str(item.get('subtitle_path', ''))).name}"
            )
        for path in list(result.get("unmatched_media_paths") or []):
            self.pair_list.addItem(f"[unmatched media] {Path(path).name}")
        for path in list(result.get("unmatched_subtitle_paths") or []):
            self.pair_list.addItem(f"[unmatched subtitle] {Path(path).name}")
        for item in self._ambiguous_assets:
            self.pair_list.addItem(
                f"[ambiguous {item.get('match_type', '')}] {Path(str(item.get('media_path', ''))).name} -> {len(list(item.get('subtitle_candidates') or []))}개 후보"
            )

    def _stage_inputs(self, paths: list[str | Path]):
        existing = {str(Path(path)) for path in self._staged_inputs}
        for path in list(paths or []):
            text = str(path or "").strip()
            if not text:
                continue
            normalized = str(Path(text))
            if normalized in existing:
                continue
            self._staged_inputs.append(normalized)
            existing.add(normalized)
        self._refresh_pair_preview()
        self._refresh_summary()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = list(event.mimeData().urls()) if event.mimeData().hasUrls() else []
        paths = [url.toLocalFile() for url in urls if url.toLocalFile()]
        if paths:
            self._stage_inputs(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _toggle_advanced_settings(self):
        if self.advanced_scroll is None:
            return
        visible = not self.advanced_scroll.isVisible()
        self.advanced_scroll.setVisible(visible)
        self.btn_toggle_advanced.setText("고급 설정 닫기" if visible else "고급 설정 열기")

    def _open_learning_info(self):
        dialog = PersonalizationLearningInfoDialog(self)
        dialog.exec()

    def _trainer(self):
        owner = self.parent()
        return getattr(owner, "_personalization_idle_trainer", None) if owner is not None else None

    def _request_stop_for_user_input(self) -> bool:
        if not self._pending_queue_batch_active:
            return False
        self._pending_queue_batch_stop_requested = True
        self._finish_pending_job_batch("user_input_interrupt")
        return True

    def _prompt_subtitle_choice_for_ambiguous(self, media_path: str, candidates: list[str], match_type: str) -> str | None:
        labels = ["건너뛰기"]
        label_to_path = {"건너뛰기": ""}
        for candidate in list(candidates or []):
            path_text = str(candidate or "")
            label = f"{Path(path_text).name}  [{path_text}]"
            labels.append(label)
            label_to_path[label] = path_text

        selected, ok = QInputDialog.getItem(
            self,
            "pair 선택",
            "\n".join(
                [
                    f"미디어: {Path(str(media_path or '')).name}",
                    f"매칭 방식: {match_type}",
                    "사용할 SRT를 선택해 주세요.",
                ]
            ),
            labels,
            0,
            False,
        )
        if not ok:
            return None
        chosen = str(label_to_path.get(str(selected), "") or "")
        return chosen or None

    def _resolve_pairs_for_import(self) -> dict:
        result = pair_ground_truth_assets(self._staged_inputs)
        selected_pairs = list(result.get("pairs") or [])
        resolved = resolve_ambiguous_matches(
            list(result.get("ambiguous_matches") or []),
            self._prompt_subtitle_choice_for_ambiguous,
        )
        selected_pairs.extend(list(resolved.get("pairs") or []))
        return {
            "pairs": selected_pairs,
            "unresolved": list(resolved.get("unresolved") or []),
            "pairing": result,
        }

    def _add_learning_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "영상/오디오/SRT 파일 선택",
            "",
            "Learning Files (*.mp4 *.mov *.mkv *.avi *.wav *.mp3 *.m4a *.aac *.flac *.ogg *.srt);;All Files (*)",
        )
        self._stage_inputs([str(path) for path in files if path])

    def _add_media_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "비디오/오디오 파일 선택",
            "",
            "Media Files (*.mp4 *.mov *.mkv *.avi *.wav *.mp3 *.m4a *.aac *.flac *.ogg);;All Files (*)",
        )
        self._stage_inputs([str(path) for path in files if path])

    def _add_subtitle_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "SRT 파일 선택",
            "",
            "Subtitle Files (*.srt);;All Files (*)",
        )
        self._stage_inputs([str(path) for path in files if path])

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택", "")
        if folder:
            self._stage_inputs([str(folder)])

    def _begin_pending_job_batch(self, *, silent: bool = False) -> bool:
        if self._pending_queue_batch_active:
            return False
        trainer = self._trainer()
        if trainer is None:
            return False
        if hasattr(trainer, "is_busy") and trainer.is_busy():
            return False
        self._pending_queue_batch_active = True
        self._pending_queue_batch_silent = bool(silent)
        self._pending_queue_batch_started = 0
        self._pending_queue_batch_stop_requested = False
        if self.btn_run_queue is not None:
            self.btn_run_queue.setEnabled(False)
            self.btn_run_queue.setText("실행 중...")
        if self._pending_queue_batch_manual_full:
            self._set_full_learning_buttons_active(True)
        self._drain_pending_jobs_step()
        return True

    def _start_auto_learning(self):
        resolved = self._resolve_pairs_for_import()
        selected_pairs = list(resolved.get("pairs") or [])
        unresolved = list(resolved.get("unresolved") or [])
        if not selected_pairs:
            QMessageBox.information(self, "안내", "학습할 영상/SRT pair가 없습니다. 영상과 SRT를 함께 추가해 주세요.")
            return

        self.btn_start_auto_learning.setEnabled(False)
        self.btn_start_auto_learning.setText("등록 중...")
        try:
            import_result = import_ground_truth_pairs(selected_pairs)
            jobs = enqueue_default_training_jobs(selected_pairs)
            current_segments, current_project_path = self._current_editor_segments()
            accumulate_result = accumulate_personalization_dataset(
                current_segments=current_segments,
                current_project_path=current_project_path,
                trigger="auto_pair_learning",
            )
            index_result = build_lora_retrieval_index(force=True)
            bundle_result = refresh_unified_lora_data_bundle(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "개인화 학습 오류", str(exc))
            return
        finally:
            self.btn_start_auto_learning.setEnabled(True)
            self.btn_start_auto_learning.setText("자동 학습 등록")

        self._refresh_pair_preview()
        self._refresh_summary()
        lines = [
            f"pair {import_result.get('imported_pairs', 0)}개를 자동 학습에 등록했습니다.",
            f"truth {import_result.get('truth_rows', 0)}행 · 설명 제외 {import_result.get('excluded_rows', 0)}행 · voice seed {import_result.get('voice_bridge_rows', 0)}개 · context {import_result.get('multimodal_context_rows', 0)}개",
            f"현재 편집 데이터 누적: text {int(accumulate_result.get('appended_rows', 0) or 0)}개 · voice {int(accumulate_result.get('voice_bridge_rows', 0) or 0)}개 · context {int(accumulate_result.get('multimodal_context_rows', 0) or 0)}개",
            f"검색 인덱스: {int(index_result.get('doc_count', 0) or 0)}개 기억 · LoRA ZIP 버킷 {int(bundle_result.get('record_count', 0) or 0)}개",
            f"자동 처리 대기: {len(list(jobs.get('items') or []))}개",
            "이후 규칙 재학습, 설정/프롬프트 최적화, 낮은 점수 정리, ZIP/검색 인덱스 갱신은 홈/편집 화면에서 앱이 한가할 때 이어서 처리됩니다.",
        ]
        if unresolved:
            lines.append(f"확인이 필요한 ambiguous pair {len(unresolved)}개는 제외했습니다.")
        QMessageBox.information(self, "자동 학습 등록 완료", "\n".join(lines))

    def _set_full_learning_buttons_active(self, active: bool):
        self.btn_start_auto_learning.setEnabled(not active)
        self.btn_start_auto_learning.setText("학습 중..." if active else "학습 시작")
        if self.btn_stop_full_learning is not None:
            self.btn_stop_full_learning.setEnabled(bool(active))

    def _start_full_learning(self):
        if self._pending_queue_batch_active:
            QMessageBox.information(self, "안내", "이미 Full 학습을 실행 중입니다.")
            return
        trainer = self._trainer()
        if trainer is None:
            QMessageBox.information(self, "안내", "개인화 학습 트레이너를 찾을 수 없습니다.")
            return
        if hasattr(trainer, "is_busy") and trainer.is_busy():
            QMessageBox.information(self, "안내", "이미 백그라운드 학습이 실행 중입니다. 잠시 후 다시 시작해 주세요.")
            return

        self.btn_start_auto_learning.setEnabled(False)
        self.btn_start_auto_learning.setText("준비 중...")
        try:
            resolved = self._resolve_pairs_for_import()
            selected_pairs = list(resolved.get("pairs") or [])
            unresolved = list(resolved.get("unresolved") or [])
            import_result = {"imported_pairs": 0, "truth_rows": 0, "excluded_rows": 0}
            if selected_pairs:
                import_result = import_ground_truth_pairs(selected_pairs)
            current_segments, current_project_path = self._current_editor_segments()
            accumulate_result = accumulate_personalization_dataset(
                current_segments=current_segments,
                current_project_path=current_project_path,
                trigger="manual_full_learning",
            )
            recover_interrupted_training_jobs(reason="manual_full_learning_start")
            queue_payload = enqueue_full_training_jobs(selected_pairs)
            waiting_count = sum(
                1
                for item in list(queue_payload.get("items") or [])
                if str(item.get("status") or "") == "waiting"
            )
        except Exception as exc:
            self.btn_start_auto_learning.setEnabled(True)
            self.btn_start_auto_learning.setText("학습 시작")
            QMessageBox.warning(self, "Full 학습 시작 오류", str(exc))
            return

        if waiting_count <= 0:
            self.btn_start_auto_learning.setEnabled(True)
            self.btn_start_auto_learning.setText("학습 시작")
            self._refresh_summary()
            QMessageBox.information(self, "안내", "실행할 학습 데이터가 없습니다. 영상/SRT pair를 먼저 추가해 주세요.")
            return

        self._pending_queue_batch_limit = max(1, waiting_count)
        self._pending_queue_batch_manual_full = True
        self._pending_queue_batch_stop_requested = False
        started = self._begin_pending_job_batch(silent=True)
        self._refresh_summary()
        if not started:
            self._pending_queue_batch_manual_full = False
            self.btn_start_auto_learning.setEnabled(True)
            self.btn_start_auto_learning.setText("학습 시작")
            QMessageBox.information(self, "안내", "Full 학습을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return

        self._set_full_learning_buttons_active(True)
        lines = [
            f"Full 학습 실행 중: 대기 작업 {waiting_count}개",
            f"새 pair {int(import_result.get('imported_pairs', 0) or 0)}개 · truth {int(import_result.get('truth_rows', 0) or 0)}행 · 현재 편집 누적 {int(accumulate_result.get('appended_rows', 0) or 0)}개",
            "학습 종료를 누르면 현재 작업에 중지 신호를 보내고, 남은 작업은 이후 idle 백그라운드 학습으로 이어집니다.",
        ]
        if unresolved:
            lines.append(f"확인이 필요한 ambiguous pair {len(unresolved)}개는 제외했습니다.")
        self.queue_summary_label.setText("\n".join(lines))

    def _stop_full_learning(self):
        if not self._pending_queue_batch_active:
            self._set_full_learning_buttons_active(False)
            self.queue_summary_label.setText("Full 학습은 실행 중이 아닙니다. 자동 백그라운드 학습 상태로 대기합니다.")
            return
        self._pending_queue_batch_stop_requested = True
        trainer = self._trainer()
        if trainer is not None and hasattr(trainer, "suspend_for_foreground_activity"):
            try:
                trainer.suspend_for_foreground_activity(reason="manual_full_training_stop", hold_ms=0)
            except Exception:
                pass
        self._finish_pending_job_batch("manual_stop")

    def _import_ground_truth_pairs(self):
        resolved = self._resolve_pairs_for_import()
        selected_pairs = list(resolved.get("pairs") or [])
        unresolved = list(resolved.get("unresolved") or [])
        if not selected_pairs:
            QMessageBox.information(self, "안내", "가져올 media/subtitle pair가 없습니다.")
            return
        import_result = import_ground_truth_pairs(selected_pairs)
        jobs = enqueue_default_training_jobs(selected_pairs)
        self._refresh_pair_preview()
        self._refresh_summary()
        lines = [
            f"pair {import_result.get('imported_pairs', 0)}개 가져오기 완료",
            f"truth table {import_result.get('truth_rows', 0)}행 · 설명 제외 {import_result.get('excluded_rows', 0)}행 · voice seed {import_result.get('voice_bridge_rows', 0)}개 · context {import_result.get('multimodal_context_rows', 0)}개 · skipped {import_result.get('skipped_rows', 0)}행",
            f"training queue 총 {len(list(jobs.get('items') or []))}개 작업 등록",
        ]
        if unresolved:
            lines.append(f"사용자 선택 없이 남긴 ambiguous pair {len(unresolved)}개")
        QMessageBox.information(
            self,
            "완료",
            "\n".join(lines),
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
        voice_plan_result = save_voice_lora_training_plan()
        stt1_plan_result = save_stt1_whisper_adapter_training_plan()
        self._refresh_summary()
        QMessageBox.information(
            self,
            "완료",
            "\n".join(
                [
                    "기존 text LoRA 코퍼스 업데이트 완료",
                    f"학습 데이터셋: {int((export_result.get('stats') or {}).get('total_items', 0) or 0)}개",
                    f"코퍼스 누적: 텍스트 {int(accumulate_result.get('appended_rows', 0) or 0)}개 / 음성 {int(accumulate_result.get('voice_bridge_rows', 0) or 0)}개 / context {int(accumulate_result.get('multimodal_context_rows', 0) or 0)}개",
                    f"학습 프레임 row: {int(plan_result.get('usable_rows', 0) or 0)}개 / 음성 프로필 수: {int(voice_result.get('speaker_profiles', 0) or 0)}개",
                    f"목소리 LoRA item: {int(voice_plan_result.get('usable_voice_rows', 0) or 0)}개 / 저장 WAV {int(voice_plan_result.get('stored_audio_items', 0) or 0)}개 / backend: {voice_plan_result.get('backend', '')}",
                    f"STT1 adapter item: {int(stt1_plan_result.get('usable_rows', 0) or 0)}개 / 준비 WAV {int(stt1_plan_result.get('audio_ready_items', 0) or 0)}개 / runtime ready: {'예' if bool(stt1_plan_result.get('runtime_ready')) else '아니오'}",
                ]
            ),
        )

    def _run_pending_jobs_now(self):
        if self._pending_queue_batch_active:
            QMessageBox.information(self, "안내", "이미 대기 작업을 백그라운드 실행 중입니다.")
            return
        self._pending_queue_batch_manual_full = False
        trainer = self._trainer()
        if trainer is None:
            QMessageBox.information(self, "안내", "개인화 학습 트레이너를 찾을 수 없습니다.")
            return
        self._pending_queue_batch_active = True
        self._pending_queue_batch_silent = False
        self._pending_queue_batch_started = 0
        self._pending_queue_batch_stop_requested = False
        if self.btn_run_queue is not None:
            self.btn_run_queue.setEnabled(False)
            self.btn_run_queue.setText("실행 중...")
        self._drain_pending_jobs_step()

    def _drain_pending_jobs_step(self):
        if not self._pending_queue_batch_active:
            return
        if self._pending_queue_batch_stop_requested:
            self._finish_pending_job_batch("manual_stop")
            return
        trainer = self._trainer()
        if trainer is None:
            self._finish_pending_job_batch("trainer_unavailable")
            return
        if hasattr(trainer, "is_busy") and trainer.is_busy():
            self._pending_queue_batch_timer.start(150)
            return
        if self._pending_queue_batch_started >= int(self._pending_queue_batch_limit):
            self._finish_pending_job_batch("limit_reached")
            return
        if hasattr(trainer, "start_background_run"):
            try:
                result = trainer.start_background_run(
                    low_resource=not self._pending_queue_batch_manual_full,
                    continuous=self._pending_queue_batch_manual_full,
                )
            except TypeError:
                result = trainer.start_background_run()
        else:
            result = {"started": False, "reason": "trainer_unavailable"}
        if not bool(result.get("started")):
            self._finish_pending_job_batch(str(result.get("reason") or "no_pending_job"))
            return
        self._pending_queue_batch_started += 1
        self._refresh_summary()
        self._pending_queue_batch_timer.start(150)

    def _finish_pending_job_batch(self, reason: str):
        self._pending_queue_batch_active = False
        silent = bool(self._pending_queue_batch_silent)
        manual_full = bool(self._pending_queue_batch_manual_full)
        self._pending_queue_batch_silent = False
        self._pending_queue_batch_manual_full = False
        self._pending_queue_batch_stop_requested = False
        self._pending_queue_batch_timer.stop()
        if self.btn_run_queue is not None:
            self.btn_run_queue.setEnabled(True)
            self.btn_run_queue.setText("대기 실행")
        self._set_full_learning_buttons_active(False)
        self._refresh_summary()
        started = int(self._pending_queue_batch_started or 0)
        trainer = self._trainer()
        queue_summary = trainer.queue_summary() if trainer is not None and hasattr(trainer, "queue_summary") else {}
        waiting_count = int(queue_summary.get("waiting", 0) or 0)
        complete_count = int(queue_summary.get("complete", 0) or 0)
        if reason == "manual_stop":
            self.queue_summary_label.setText(
                f"Full 학습 종료: 완료 {complete_count}개 · 남음 {waiting_count}개. 남은 작업은 idle 상태에서 백그라운드로 이어집니다."
            )
            return
        if reason == "user_input_interrupt":
            self.queue_summary_label.setText(
                "사용자 입력이 감지되어 LoRA 학습 중지 신호를 보냈습니다. 남은 작업은 다시 idle 상태가 되면 이어집니다."
            )
            return
        if silent:
            label = "Full 학습" if manual_full else "대기 작업 자동 실행"
            if manual_full:
                self.queue_summary_label.setText(f"{label}: 완료 {complete_count}개 · 남음 {waiting_count}개")
            else:
                self.queue_summary_label.setText(f"{label}: {started}개 처리")
            return
        if reason == "no_pending_job" and started == 0:
            message = "실행할 대기 작업이 없습니다."
        elif reason == "limit_reached":
            message = f"대기 작업 {started}개를 백그라운드 실행했고, 남은 작업은 이후 다시 실행할 수 있습니다."
        elif reason == "trainer_unavailable":
            message = "개인화 학습 트레이너를 찾을 수 없습니다."
        else:
            message = f"대기 작업 {started}개를 백그라운드 실행했습니다."
        QMessageBox.information(self, "실행", message)

    def _pause_pending_jobs(self):
        owner = self.parent()
        if owner is not None and hasattr(owner, "_pause_personalization_idle_jobs"):
            owner._pause_personalization_idle_jobs()
        self._refresh_summary()

    def _resume_pending_jobs(self):
        owner = self.parent()
        if owner is not None and hasattr(owner, "_resume_personalization_idle_jobs"):
            owner._resume_personalization_idle_jobs()
        self._refresh_summary()

    def _clear_pending_jobs(self):
        owner = self.parent()
        if owner is not None and hasattr(owner, "_clear_personalization_idle_jobs"):
            owner._clear_personalization_idle_jobs(keep_completed=True)
        else:
            clear_training_queue(keep_completed=True)
        self._refresh_summary()

    def _learn_rules_now(self):
        result = learn_rules_from_truth_table()
        self._refresh_summary()
        QMessageBox.information(
            self,
            "규칙 재학습 완료",
            f"split rules {result.get('split_rule_count', 0)}개 / line-break rules {result.get('line_break_rule_count', 0)}개",
        )

    def _apply_split_rules_now(self):
        review = build_split_rule_update_review()
        if not list(review.get("proposed_rules") or []):
            QMessageBox.information(self, "안내", "반영할 learned split rule이 없습니다.")
            return
        reply = QMessageBox.question(
            self,
            "split rules 반영",
            "\n".join(
                [
                    "ground-truth에서 학습한 상위 split rules를 config.py 기본값에 반영합니다.",
                    f"현재: {', '.join(review.get('current_rules', [])[:8])}",
                    f"제안: {', '.join(review.get('proposed_rules', [])[:8])}",
                    "계속하시겠습니까?",
                ]
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = apply_split_rule_update_review()
        self._refresh_summary()
        QMessageBox.information(
            self,
            "반영 완료",
            f"split rules {result.get('rule_count', 0)}개 반영\nbackup: {result.get('backup_path', '')}",
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
