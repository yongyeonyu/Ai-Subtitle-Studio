from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.personalization.ground_truth_import import (
    import_ground_truth_pairs,
    pair_ground_truth_assets,
    resolve_ambiguous_matches,
)
from core.personalization.idle_trainer import enqueue_default_training_jobs
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
    refresh_lora_personalization_manifest,
    store_paths,
)
from core.personalization.text_lora_dataset import (
    TEXT_LORA_CORPUS_MANIFEST_PATH,
    TEXT_LORA_CORPUS_PATH,
    TEXT_LORA_DATASET_DIR,
    TEXT_LORA_DATASET_PATH,
    TEXT_LORA_MANIFEST_PATH,
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
from core.runtime import config
from ui.style import button_style, settings_dialog_stylesheet


class PersonalizationLearningDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("개인화 학습")
        self.setMinimumWidth(760)
        self.setMinimumHeight(720)
        self.setStyleSheet(settings_dialog_stylesheet())
        self._staged_inputs: list[str] = []
        self._paired_assets: list[dict] = []
        self._ambiguous_assets: list[dict] = []
        self._pending_queue_batch_active = False
        self._pending_queue_batch_started = 0
        self._pending_queue_batch_limit = 64
        self._pending_queue_batch_timer = QTimer(self)
        self._pending_queue_batch_timer.setSingleShot(True)
        self._pending_queue_batch_timer.timeout.connect(self._drain_pending_jobs_step)

        initialize_lora_personalization_store()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("<b style='font-size:15px;'>PHASE3 LoRA / Ground-Truth 학습</b>")
        layout.addWidget(title)

        subtitle = QLabel(
            "ground-truth 미디어/SRT pair를 가져오고, truth table · learned rules · setting/prompt trial · idle training queue를 관리합니다."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        if not config.IS_MAC:
            warn = QLabel("현재 학습 실행 흐름은 macOS 우선 구축 기준입니다.")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        import_row = QHBoxLayout()
        import_row.setSpacing(8)
        self.btn_add_media = QPushButton("비디오/오디오 추가")
        self.btn_add_media.setStyleSheet(button_style("toolbar"))
        self.btn_add_media.clicked.connect(self._add_media_files)
        import_row.addWidget(self.btn_add_media)

        self.btn_add_subtitles = QPushButton("SRT 추가")
        self.btn_add_subtitles.setStyleSheet(button_style("toolbar"))
        self.btn_add_subtitles.clicked.connect(self._add_subtitle_files)
        import_row.addWidget(self.btn_add_subtitles)

        self.btn_add_folder = QPushButton("폴더 추가")
        self.btn_add_folder.setStyleSheet(button_style("toolbar"))
        self.btn_add_folder.clicked.connect(self._add_folder)
        import_row.addWidget(self.btn_add_folder)

        self.btn_import_pairs = QPushButton("pair 가져오기")
        self.btn_import_pairs.setStyleSheet(button_style("primary"))
        self.btn_import_pairs.clicked.connect(self._import_ground_truth_pairs)
        import_row.addWidget(self.btn_import_pairs)
        layout.addLayout(import_row)

        list_title = QLabel("<b>pair 미리보기</b>")
        layout.addWidget(list_title)
        self.pair_list = QListWidget()
        self.pair_list.setMinimumHeight(180)
        layout.addWidget(self.pair_list)

        self.queue_summary_label = QLabel("")
        self.queue_summary_label.setWordWrap(True)
        layout.addWidget(self.queue_summary_label)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.btn_refresh = QPushButton("현황")
        self.btn_refresh.setStyleSheet(button_style("toolbar"))
        self.btn_refresh.clicked.connect(self._refresh_summary)
        action_row.addWidget(self.btn_refresh)

        self.btn_update = QPushButton("기존 자막 코퍼스 업데이트")
        self.btn_update.setStyleSheet(button_style("primary"))
        self.btn_update.clicked.connect(self._update_personalization_assets)
        action_row.addWidget(self.btn_update)

        self.btn_run_queue = QPushButton("대기 작업 즉시 실행")
        self.btn_run_queue.setStyleSheet(button_style("primary"))
        self.btn_run_queue.clicked.connect(self._run_pending_jobs_now)
        action_row.addWidget(self.btn_run_queue)
        layout.addLayout(action_row)

        queue_row = QHBoxLayout()
        queue_row.setSpacing(8)
        self.btn_pause = QPushButton("대기 pause")
        self.btn_pause.setStyleSheet(button_style("toolbar"))
        self.btn_pause.clicked.connect(self._pause_pending_jobs)
        queue_row.addWidget(self.btn_pause)

        self.btn_resume = QPushButton("대기 resume")
        self.btn_resume.setStyleSheet(button_style("toolbar"))
        self.btn_resume.clicked.connect(self._resume_pending_jobs)
        queue_row.addWidget(self.btn_resume)

        self.btn_clear_queue = QPushButton("대기 clear")
        self.btn_clear_queue.setStyleSheet(button_style("danger"))
        self.btn_clear_queue.clicked.connect(self._clear_pending_jobs)
        queue_row.addWidget(self.btn_clear_queue)

        self.btn_delete = QPushButton("개인화 산출물 삭제")
        self.btn_delete.setStyleSheet(button_style("danger"))
        self.btn_delete.clicked.connect(self._delete_personalization_assets)
        queue_row.addWidget(self.btn_delete)
        layout.addLayout(queue_row)

        rule_row = QHBoxLayout()
        rule_row.setSpacing(8)
        self.btn_learn_rules = QPushButton("규칙 재학습")
        self.btn_learn_rules.setStyleSheet(button_style("toolbar"))
        self.btn_learn_rules.clicked.connect(self._learn_rules_now)
        rule_row.addWidget(self.btn_learn_rules)

        self.btn_apply_rules = QPushButton("split rules 반영")
        self.btn_apply_rules.setStyleSheet(button_style("toolbar"))
        self.btn_apply_rules.clicked.connect(self._apply_split_rules_now)
        rule_row.addWidget(self.btn_apply_rules)

        self.btn_close = QPushButton("닫기")
        self.btn_close.setStyleSheet(button_style("toolbar"))
        self.btn_close.clicked.connect(self.accept)
        rule_row.addWidget(self.btn_close)
        layout.addLayout(rule_row)

        inspect_title = QLabel("<b>inspection</b>")
        layout.addWidget(inspect_title)
        self.inspect_box = QPlainTextEdit()
        self.inspect_box.setReadOnly(True)
        self.inspect_box.setMinimumHeight(180)
        layout.addWidget(self.inspect_box, stretch=1)

        self._refresh_pair_preview()
        self._refresh_summary()

    def _store_paths(self):
        return store_paths(LORA_PERSONALIZATION_DIR)

    def _refresh_summary(self):
        current_segments, current_project_path = self._current_editor_segments()
        payload = build_text_lora_dataset(
            current_segments=current_segments,
            current_project_path=current_project_path,
        )
        legacy_stats = payload.get("stats", {}) or {}
        manifest = refresh_lora_personalization_manifest()
        counts = dict(manifest.get("counts") or {})
        queue_payload = load_training_queue()
        queue_items = list(queue_payload.get("items") or [])
        queue_counts: dict[str, int] = {}
        for item in queue_items:
            status = str(item.get("status") or "waiting")
            queue_counts[status] = int(queue_counts.get(status, 0) or 0) + 1

        self.summary_label.setText(
            "\n".join(
                [
                    f"기존 코퍼스: 총 {int(legacy_stats.get('total_items', 0) or 0)}개 "
                    f"(교정사전 {int(legacy_stats.get('legacy_corrections', 0) or 0)} / correction memory {int(legacy_stats.get('correction_memory', 0) or 0)} / wrong memory {int(legacy_stats.get('wrong_answer_memory', 0) or 0)})",
                    f"truth table {counts.get('truth_table_rows', 0)}행 · excluded parenthetical {counts.get('excluded_parenthetical_rows', 0)}행 · "
                    f"setting trials {counts.get('setting_trial_rows', 0)}개 · prompt trials {counts.get('prompt_trial_rows', 0)}개",
                    f"learned split rules {counts.get('learned_split_rules', 0)}개 · learned line break rules {counts.get('learned_line_break_rules', 0)}개 · "
                    f"queue {counts.get('queue_items', 0)}개 · dedupe {counts.get('dedupe_entry_count', 0)}개",
                ]
            )
        )

        self.path_label.setText(
            "\n".join(
                [
                    f"기존 text LoRA 경로: {TEXT_LORA_DATASET_DIR}",
                    f"PHASE3 저장소: {manifest.get('store_dir', LORA_PERSONALIZATION_DIR)}",
                    f"현재 staged 입력: {len(self._staged_inputs)}개 / pair {len(self._paired_assets)}개",
                ]
            )
        )

        queue_summary = " · ".join(f"{key} {value}개" for key, value in sorted(queue_counts.items())) or "대기 작업 없음"
        self.queue_summary_label.setText(f"queue 상태: {queue_summary}")

        review = build_split_rule_update_review()
        self.inspect_box.setPlainText(
            "\n".join(
                [
                    f"[Current Project] {current_project_path or '-'}",
                    f"[Queue] {queue_summary}",
                    f"[Split Rule Review] needs_update={review.get('needs_update')} / top_n={review.get('top_n')}",
                    f"current: {', '.join(review.get('current_rules', [])[:8])}",
                    f"proposed: {', '.join(review.get('proposed_rules', [])[:8])}",
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

    def _trainer(self):
        owner = self.parent()
        return getattr(owner, "_personalization_idle_trainer", None) if owner is not None else None

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

    def _add_media_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "비디오/오디오 파일 선택",
            "",
            "Media Files (*.mp4 *.mov *.mkv *.avi *.wav *.mp3 *.m4a *.aac *.flac *.ogg);;All Files (*)",
        )
        self._staged_inputs.extend(str(path) for path in files if path)
        self._refresh_pair_preview()
        self._refresh_summary()

    def _add_subtitle_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "SRT 파일 선택",
            "",
            "Subtitle Files (*.srt);;All Files (*)",
        )
        self._staged_inputs.extend(str(path) for path in files if path)
        self._refresh_pair_preview()
        self._refresh_summary()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택", "")
        if folder:
            self._staged_inputs.append(str(folder))
            self._refresh_pair_preview()
            self._refresh_summary()

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
            f"truth table {import_result.get('truth_rows', 0)}행 · excluded {import_result.get('excluded_rows', 0)}행 · skipped {import_result.get('skipped_rows', 0)}행",
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
        self._refresh_summary()
        QMessageBox.information(
            self,
            "완료",
            "\n".join(
                [
                    "기존 text LoRA 코퍼스 업데이트 완료",
                    f"학습 데이터셋: {int((export_result.get('stats') or {}).get('total_items', 0) or 0)}개",
                    f"코퍼스 누적: 텍스트 {int(accumulate_result.get('appended_rows', 0) or 0)}개 / 음성 {int(accumulate_result.get('voice_bridge_rows', 0) or 0)}개",
                    f"학습 프레임 row: {int(plan_result.get('usable_rows', 0) or 0)}개 / 음성 프로필 수: {int(voice_result.get('speaker_profiles', 0) or 0)}개",
                ]
            ),
        )

    def _run_pending_jobs_now(self):
        if self._pending_queue_batch_active:
            QMessageBox.information(self, "안내", "이미 대기 작업을 백그라운드 실행 중입니다.")
            return
        trainer = self._trainer()
        if trainer is None:
            QMessageBox.information(self, "안내", "개인화 학습 트레이너를 찾을 수 없습니다.")
            return
        self._pending_queue_batch_active = True
        self._pending_queue_batch_started = 0
        self.btn_run_queue.setEnabled(False)
        self.btn_run_queue.setText("대기 작업 실행 중...")
        self._drain_pending_jobs_step()

    def _drain_pending_jobs_step(self):
        if not self._pending_queue_batch_active:
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
        self._pending_queue_batch_timer.stop()
        self.btn_run_queue.setEnabled(True)
        self.btn_run_queue.setText("대기 작업 즉시 실행")
        self._refresh_summary()
        started = int(self._pending_queue_batch_started or 0)
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

        store = self._store_paths()
        try:
            for path in store["trained_adapters"].rglob("*"):
                if path.is_file():
                    path.unlink()
                    deleted += 1
            for key, path in store.items():
                if key in {"root", "trained_adapters"}:
                    continue
                if path.exists():
                    path.unlink()
                    deleted += 1
        except Exception:
            pass

        initialize_lora_personalization_store()
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
