from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from core.personalization.llm_review_exchange import (
    LLM_REVIEW_RESULT_SCHEMA,
    export_llm_review_request,
    import_llm_review_result_file,
)
from core.personalization.lora_retention import prune_low_value_personalization_data
from core.personalization.lora_storage import (
    initialize_lora_personalization_store,
    refresh_unified_lora_data_bundle,
    reset_lora_personalization_store,
    restore_lora_personalization_store_from_bundle,
)
from core.personalization.lora_vector_retriever import build_lora_retrieval_index
from core.personalization.text_lora_dataset import (
    TEXT_LORA_CORPUS_MANIFEST_PATH,
    TEXT_LORA_CORPUS_PATH,
    TEXT_LORA_DATASET_PATH,
    TEXT_LORA_MANIFEST_PATH,
    VOICE_LORA_BRIDGE_PATH,
)
from core.personalization.text_lora_runner import (
    TEXT_LORA_TRAINING_PLAN_PATH,
    VOICE_LORA_DATASET_MANIFEST_PATH,
    VOICE_LORA_PROFILE_MANIFEST_PATH,
    VOICE_LORA_TRAINING_PLAN_PATH,
    save_voice_lora_profile_manifest,
    save_voice_lora_training_plan,
)
from ui.settings.personalization_learning_info import format_bytes as _format_bytes


class VoiceLoraDatasetWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = threading.Event()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def run(self) -> None:
        try:
            profile_result = save_voice_lora_profile_manifest()
            plan_result = save_voice_lora_training_plan(
                extract_audio=True,
                cancel_callback=self._stop_requested.is_set,
            )
            index_result = build_lora_retrieval_index()
            bundle_result = refresh_unified_lora_data_bundle(force=True)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        if bool(plan_result.get("cancelled")):
            self.failed.emit("목소리 LoRA 데이터 생성이 중단되어 대기 상태로 남겼습니다.")
            return
        self.completed.emit(
            {
                "profile": profile_result,
                "plan": plan_result,
                "index": index_result,
                "bundle": bundle_result,
            }
        )


class PersonalizationLearningActionsMixin:
    def _export_llm_review_json(self):
        default_path = str(self._store_paths().get("llm_review_request", "llm_review_request.json"))
        path, _ = QFileDialog.getSaveFileName(
            self,
            "LLM 검토 요청 JSON 저장",
            default_path,
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            result = export_llm_review_request(output_path=path)
        except Exception as exc:
            QMessageBox.warning(self, "LLM 검토 JSON 저장 오류", str(exc))
            return
        self._refresh_summary()
        QMessageBox.information(
            self,
            "LLM 검토 JSON 저장 완료",
            "\n".join(
                [
                    f"저장 위치: {result.get('path', path)}",
                    f"review_id: {result.get('review_id', '')}",
                    "",
                    "사용 방법:",
                    "1. 이 JSON 전체를 ChatGPT/Gemini에 붙여 넣습니다.",
                    f"2. 반환은 반드시 schema={LLM_REVIEW_RESULT_SCHEMA} JSON 하나만 받습니다.",
                    "3. 반환 JSON을 'LLM 결과 JSON 가져오기'로 다시 불러옵니다.",
                    "",
                    "민감한 자막/경로가 있으면 외부 채팅에 입력하기 전에 JSON에서 제거해 주세요.",
                ]
            ),
        )

    def _import_llm_review_json(self):
        default_path = str(self._store_paths().get("llm_review_result", "llm_review_result.json"))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "LLM 결과 JSON 선택",
            default_path,
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            result = import_llm_review_result_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "LLM 결과 JSON 오류", str(exc))
            return
        self._refresh_summary()
        QMessageBox.information(
            self,
            "LLM 결과 반영 완료",
            "\n".join(
                [
                    f"split rule 추가: {int(result.get('inserted_split_rules', 0) or 0)}개",
                    f"line-break rule 추가: {int(result.get('inserted_line_break_rules', 0) or 0)}개",
                    f"prompt trial 추가: {int(result.get('appended_prompt_trials', 0) or 0)}개",
                    f"setting 추천 반영: {'예' if result.get('settings_updated') else '아니오'}",
                    f"저장 위치: {result.get('result_path', '')}",
                ]
            ),
        )

    def _prune_low_value_now(self):
        try:
            result = prune_low_value_personalization_data(trigger="manual_settings_dialog")
        except Exception as exc:
            QMessageBox.warning(self, "낮은 점수 정리 오류", str(exc))
            return
        self._refresh_summary()
        removed = dict(result.get("removed") or {})
        if removed:
            details = " · ".join(f"{key} {value}개" for key, value in sorted(removed.items()))
        else:
            details = "정리할 낮은 점수 항목이 없습니다. 작은 데이터셋은 보호됩니다."
        QMessageBox.information(
            self,
            "낮은 점수 정리 완료",
            "\n".join(
                [
                    f"총 정리: {int(result.get('total_removed', 0) or 0)}개",
                    details,
                ]
            ),
        )

    def _refresh_unified_lora_data_now(self):
        try:
            index_result = build_lora_retrieval_index(force=True)
            result = refresh_unified_lora_data_bundle(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "LoRA ZIP 갱신 오류", str(exc))
            return
        self._refresh_summary()
        QMessageBox.information(
            self,
            "LoRA ZIP 갱신 완료",
            "\n".join(
                [
                    f"저장 위치: {result.get('path', '')}",
                    f"학습 record: {int(result.get('record_count', 0) or 0)}개",
                    f"검색 인덱스: {int(index_result.get('doc_count', 0) or 0)}개 기억",
                    f"파일 크기: {int(result.get('size_bytes', 0) or 0)} bytes",
                    "이 ZIP 파일 하나로 개인화 학습 데이터를 백업/이동할 수 있습니다.",
                ]
            ),
        )

    def _import_unified_lora_data_now(self):
        default_path = str(self._store_paths().get("unified_lora_data", "lora_data_bundle.zip"))
        path, _ = QFileDialog.getOpenFileName(
            self,
            "LoRA ZIP 학습 파일 선택",
            default_path,
            "LoRA Learning Bundle (*.zip *.json);;All Files (*)",
        )
        if not path:
            return
        reply = QMessageBox.question(
            self,
            "LoRA ZIP 학습 파일 불러오기",
            "\n".join(
                [
                    "선택한 lora_data_bundle.zip에서 내부 학습 cache를 다시 만듭니다.",
                    "예전 lora_data_bundle.json도 호환 불러오기를 지원합니다.",
                    "현재 개인화 학습 shard는 이 파일 내용으로 교체됩니다.",
                    "계속하시겠습니까?",
                ]
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            result = restore_lora_personalization_store_from_bundle(path)
            index_result = build_lora_retrieval_index(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "LoRA ZIP 불러오기 오류", str(exc))
            return
        self._refresh_pair_preview()
        self._refresh_summary()
        counts = dict(result.get("restored_jsonl_counts") or {})
        QMessageBox.information(
            self,
            "LoRA ZIP 불러오기 완료",
            "\n".join(
                [
                    f"불러온 파일: {result.get('source_path', path)}",
                    f"대표 파일: {result.get('target_path', '')}",
                    f"학습 record: {int(result.get('record_count', 0) or 0)}개",
                    f"검색 인덱스: {int(index_result.get('doc_count', 0) or 0)}개 기억",
                    f"복원한 산출물 파일: {int(result.get('restored_attachment_files', 0) or 0)}개",
                    f"truth {counts.get('truth_table', 0)}행 · text corpus {counts.get('text_lora_corpus', 0)}행 · voice {counts.get('voice_lora_bridge', 0)}구간",
                ]
            ),
        )

    def _build_voice_lora_dataset_now(self):
        if self._voice_lora_worker is not None and self._voice_lora_worker.isRunning():
            QMessageBox.information(self, "안내", "목소리 LoRA 데이터 생성이 이미 백그라운드에서 실행 중입니다.")
            return
        worker = VoiceLoraDatasetWorker(self)
        worker.completed.connect(self._voice_lora_dataset_done)
        worker.failed.connect(self._voice_lora_dataset_failed)
        worker.finished.connect(self._voice_lora_dataset_worker_finished)
        worker.finished.connect(worker.deleteLater)
        self._voice_lora_worker = worker
        if self.btn_build_voice_lora is not None:
            self.btn_build_voice_lora.setEnabled(False)
            self.btn_build_voice_lora.setText("생성 중...")
        self.queue_summary_label.setText("목소리 LoRA WAV 클립을 백그라운드에서 저장 중입니다.")
        worker.start()

    def _voice_lora_dataset_done(self, payload):
        profile_result = dict((payload or {}).get("profile") or {})
        plan_result = dict((payload or {}).get("plan") or {})
        self._refresh_summary()
        usable = int(plan_result.get("usable_voice_rows", 0) or 0)
        stored = int(plan_result.get("stored_audio_items", 0) or 0)
        errors = int(plan_result.get("extraction_errors", 0) or 0)
        skipped = int(plan_result.get("extraction_skipped", 0) or 0)
        message_lines = [
            f"화자 프로필: {int(profile_result.get('speaker_profiles', 0) or 0)}명",
            f"학습 item: {usable}개",
            f"새로 저장한 WAV: {int(plan_result.get('extracted_clips', 0) or 0)}개 / 기존 WAV: {int(plan_result.get('already_ready_clips', 0) or 0)}개",
            f"저장된 음성 item: {stored}개 / 준비 완료 화자: {int(plan_result.get('audio_dataset_ready_speakers', 0) or 0)}명",
            f"추출 오류: {errors}개 / 건너뜀: {skipped}개",
            f"backend: {plan_result.get('backend', '')}",
            f"plan: {plan_result.get('plan_path', '')}",
            "실제 음성 adapter 학습은 저장된 WAV + transcript manifest를 voice backend에 연결해 실행합니다.",
        ]
        message_box = QMessageBox.warning if usable > 0 and stored < usable and (errors > 0 or skipped > 0) else QMessageBox.information
        message_box(
            self,
            "목소리 LoRA 데이터 생성 완료",
            "\n".join(message_lines),
        )

    def _voice_lora_dataset_failed(self, message: str):
        self._refresh_summary()
        QMessageBox.warning(self, "목소리 LoRA 데이터 생성 오류", str(message or "알 수 없는 오류"))

    def _voice_lora_dataset_worker_finished(self):
        self._voice_lora_worker = None
        if self.btn_build_voice_lora is not None:
            self.btn_build_voice_lora.setEnabled(True)
            self.btn_build_voice_lora.setText("목소리 데이터")

    def closeEvent(self, event):
        if self._voice_lora_worker is not None and self._voice_lora_worker.isRunning():
            try:
                self._voice_lora_worker.request_stop()
                if self._voice_lora_worker.wait(2500):
                    super().closeEvent(event)
                    return
            except Exception:
                pass
            QMessageBox.information(self, "안내", "목소리 LoRA 데이터 생성을 중단하는 중입니다. 현재 음성 클립 처리가 끝난 뒤 창을 닫을 수 있습니다.")
            event.ignore()
            return
        super().closeEvent(event)

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
            VOICE_LORA_TRAINING_PLAN_PATH,
            VOICE_LORA_DATASET_MANIFEST_PATH,
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
                if path.is_dir():
                    continue
                if path.exists():
                    path.unlink()
                    deleted += 1
        except Exception:
            pass

        initialize_lora_personalization_store()
        self._refresh_summary()
        QMessageBox.information(self, "완료", f"개인화 학습 산출물 {deleted}개를 삭제했습니다.")

    def _reset_lora_learning_store_now(self):
        if self._voice_lora_worker is not None and self._voice_lora_worker.isRunning():
            QMessageBox.information(self, "안내", "목소리 LoRA 데이터 생성이 끝나거나 중단된 뒤 전체 초기화를 실행할 수 있습니다.")
            return
        trainer = self._trainer()
        if trainer is not None and hasattr(trainer, "shutdown"):
            try:
                shutdown_result = trainer.shutdown(timeout_sec=3.0)
            except Exception as exc:
                QMessageBox.warning(self, "전체 초기화 오류", f"백그라운드 개인화 작업을 중단하지 못했습니다.\n{exc}")
                return
            if bool(shutdown_result.get("busy")):
                QMessageBox.information(self, "안내", "백그라운드 개인화 작업이 아직 종료 중입니다. 잠시 후 다시 시도해 주세요.")
                return

        reply = QMessageBox.question(
            self,
            "LoRA 학습 전체 초기화",
            "\n".join(
                [
                    "LoRA 개인화 학습 데이터를 모두 삭제하고 빈 상태로 다시 시작합니다.",
                    "삭제 대상: lora_data_bundle.zip, truth table, learned rules, queue, text/voice LoRA cache, voice clips, trained adapter 산출물",
                    "원본 영상/SRT 파일과 교정사전 원본은 삭제하지 않습니다.",
                    "계속하시겠습니까?",
                ]
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        confirm_text, ok = QInputDialog.getText(
            self,
            "초기화 확인",
            "정말 처음부터 다시 학습하려면 아래에 '초기화'를 입력해 주세요.",
        )
        if not ok or str(confirm_text or "").strip() != "초기화":
            QMessageBox.information(self, "취소", "전체 초기화를 취소했습니다.")
            return

        try:
            result = reset_lora_personalization_store()
        except Exception as exc:
            QMessageBox.warning(self, "전체 초기화 오류", str(exc))
            return

        self._staged_inputs.clear()
        self._paired_assets.clear()
        self._ambiguous_assets.clear()
        self._refresh_pair_preview()
        self._refresh_summary()
        QMessageBox.information(
            self,
            "LoRA 학습 전체 초기화 완료",
            "\n".join(
                [
                    f"삭제 파일: {int(result.get('deleted_files', 0) or 0)}개",
                    f"삭제 폴더: {int(result.get('deleted_dirs', 0) or 0)}개",
                    f"삭제 용량: {_format_bytes(result.get('deleted_bytes', 0))}",
                    "빈 LoRA 학습 저장소를 다시 만들었습니다. 이제 영상/SRT pair를 넣고 처음부터 학습할 수 있습니다.",
                ]
            ),
        )
