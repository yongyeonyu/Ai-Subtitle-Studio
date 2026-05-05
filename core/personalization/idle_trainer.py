from __future__ import annotations

import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDateTime, QObject, QTimer

from core.personalization.lora_models import TrainingQueueItem, iso_now, stable_hash
from core.personalization.lora_optimizer import optimize_prompts_for_media, optimize_settings_for_media
from core.personalization.lora_retention import prune_low_value_personalization_data
from core.personalization.lora_rule_learning import learn_rules_from_truth_table, load_truth_table_rows
from core.personalization.lora_storage import (
    clear_training_queue,
    load_training_queue,
    refresh_lora_personalization_manifest,
    save_training_queue,
    store_paths,
    upsert_training_queue_items,
)
from core.personalization.lora_vector_retriever import build_lora_retrieval_index
from core.runtime.logger import get_logger
from core.personalization.text_lora_runner import (
    save_text_lora_training_plan,
    save_voice_lora_profile_manifest,
    save_voice_lora_training_plan,
)


def _group_truth_rows_by_media(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in list(rows or []):
        media_id = str(row.get("media_id") or "")
        if media_id:
            grouped[media_id].append(dict(row))
    return dict(grouped)


def enqueue_default_training_jobs(
    imported_pairs: list[dict[str, Any]],
    *,
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = [
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="analyze_truth_table",
            priority=10,
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_text_training_plan",
            priority=20,
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_voice_profiles",
            priority=30,
        ).to_record(),
    ]
    for index, pair in enumerate(list(imported_pairs or []), start=1):
        media_id = str(pair.get("media_id") or stable_hash({"media_path": pair.get("media_path", "")})[:16])
        media_path = str(pair.get("media_path") or "")
        subtitle_path = str(pair.get("subtitle_path") or "")
        jobs.append(
            TrainingQueueItem(
                media_id=media_id,
                media_path=media_path,
                subtitle_path=subtitle_path,
                job_type="optimize_settings",
                priority=100 + index,
            ).to_record()
        )
        jobs.append(
            TrainingQueueItem(
                media_id=media_id,
                media_path=media_path,
                subtitle_path=subtitle_path,
                job_type="optimize_prompts",
                priority=200 + index,
            ).to_record()
        )
    payload = upsert_training_queue_items(jobs, store_dir)
    refresh_lora_personalization_manifest(store_dir)
    return payload


def _update_job(queue_payload: dict[str, Any], job_id: str, **changes) -> dict[str, Any]:
    items = []
    for item in list(queue_payload.get("items") or []):
        if str(item.get("job_id") or "") == str(job_id):
            updated = dict(item)
            updated.update(changes)
            updated["updated_at"] = str(changes.get("updated_at") or iso_now())
            items.append(updated)
        else:
            items.append(dict(item))
    return {"schema": queue_payload.get("schema"), "updated_at": queue_payload.get("updated_at"), "items": items}


def _checkpoint_payload(job: dict[str, Any], stage: str, **details) -> dict[str, Any]:
    payload = dict(job.get("payload") or {})
    checkpoint = {
        "stage": str(stage or ""),
        "updated_at": iso_now(),
        **dict(details or {}),
    }
    history = [dict(item) for item in list(payload.get("checkpoint_history") or []) if isinstance(item, dict)]
    history.append(checkpoint)
    payload["checkpoint"] = checkpoint
    payload["checkpoint_history"] = history[-12:]
    return payload


def _job_from_payload(payload: dict[str, Any], job_id: str) -> dict[str, Any]:
    for item in list(payload.get("items") or []):
        if str(item.get("job_id") or "") == str(job_id):
            return dict(item)
    return {}


def _save_queue_payload(payload: dict[str, Any], store_dir: str | Path | None = None) -> dict[str, Any]:
    return save_training_queue(list(payload.get("items") or []), store_dir)


def recover_interrupted_training_jobs(
    store_dir: str | Path | None = None,
    *,
    reason: str = "startup",
) -> dict[str, Any]:
    payload = load_training_queue(store_dir)
    items: list[dict[str, Any]] = []
    recovered: list[dict[str, Any]] = []
    now = iso_now()
    for item in list(payload.get("items") or []):
        updated = dict(item)
        if str(updated.get("status") or "") == "in_progress":
            updated["status"] = "waiting"
            updated["progress"] = 0.0
            updated["updated_at"] = now
            updated["last_error"] = f"interrupted_{reason}: active worker was not found, queued again"
            updated["payload"] = _checkpoint_payload(
                updated,
                "recovered_after_interruption",
                reason=str(reason),
                previous_status="in_progress",
                resumable=True,
            )
            recovered.append(
                {
                    "job_id": str(updated.get("job_id") or ""),
                    "job_type": str(updated.get("job_type") or ""),
                    "media_path": str(updated.get("media_path") or ""),
                }
            )
        items.append(updated)
    if not recovered:
        return {"recovered": 0, "items": []}
    save_training_queue(items, store_dir)
    return {"recovered": len(recovered), "items": recovered}


def run_training_job(
    job: dict[str, Any],
    *,
    store_dir: str | Path | None = None,
    progress_callback=None,
    cancel_callback=None,
) -> dict[str, Any]:
    job_type = str(job.get("job_type") or "").strip()
    media_id = str(job.get("media_id") or "").strip()
    rows = load_truth_table_rows(store_dir)
    grouped_rows = _group_truth_rows_by_media(rows)
    paths = store_paths(store_dir)
    store_root = paths["root"]

    if job_type == "analyze_truth_table":
        result = learn_rules_from_truth_table(store_dir)
        return {"status": "complete", "score": None, "result": result}
    if job_type == "build_text_training_plan":
        result = save_text_lora_training_plan(
            corpus_path=store_root / "text_lora_corpus.jsonl",
            plan_path=store_root / "text_lora_training_plan.json",
            output_dir=paths["trained_adapters"] / "personal_text_lora",
        )
        return {"status": "complete", "score": float(result.get("usable_rows", 0) or 0), "result": result}
    if job_type == "build_voice_profiles":
        job_payload = dict(job.get("payload") or {})
        extract_audio = bool(job_payload.get("extract_audio"))
        profile_result = save_voice_lora_profile_manifest(
            bridge_path=store_root / "voice_lora_bridge.jsonl",
            manifest_path=store_root / "voice_lora_profile_manifest.json",
        )
        plan_result = save_voice_lora_training_plan(
            bridge_path=store_root / "voice_lora_bridge.jsonl",
            plan_path=store_root / "voice_lora_training_plan.json",
            dataset_manifest_path=store_root / "voice_lora_dataset_manifest.json",
            extract_audio=extract_audio,
            progress_callback=progress_callback if extract_audio else None,
            cancel_callback=cancel_callback,
        )
        result = {"profile": profile_result, "training_plan": plan_result}
        if bool(plan_result.get("cancelled")):
            result["reason"] = "cancelled"
            return {"status": "waiting", "score": None, "result": result}
        usable = int(plan_result.get("usable_voice_rows", 0) or 0)
        stored = int(plan_result.get("stored_audio_items", 0) or 0)
        errors = int(plan_result.get("extraction_errors", 0) or 0)
        skipped = int(plan_result.get("extraction_skipped", 0) or 0)
        status = "complete"
        if extract_audio and usable > 0 and stored < usable and (errors > 0 or skipped > 0):
            status = "failed" if stored == 0 else "partial"
            result["reason"] = (
                f"voice_audio_extraction_incomplete: stored {stored}/{usable}, "
                f"errors {errors}, skipped {skipped}"
            )
        if not extract_audio:
            result["reason"] = "audio_extraction_deferred"
        return {"status": status, "score": float((stored if extract_audio else usable) if usable else 0), "result": result}
    if job_type == "optimize_settings":
        media_rows = grouped_rows.get(media_id, [])
        if not media_rows:
            return {"status": "skipped", "score": None, "result": {"reason": "missing_truth_rows"}}
        result = optimize_settings_for_media(
            media_id,
            media_rows,
            media_path=str(job.get("media_path") or ""),
            subtitle_path=str(job.get("subtitle_path") or ""),
            store_dir=str(store_dir) if store_dir else None,
        )
        return {"status": "complete", "score": float(result.get("best_score", 0.0) or 0.0), "result": result}
    if job_type == "optimize_prompts":
        media_rows = grouped_rows.get(media_id, [])
        if not media_rows:
            return {"status": "skipped", "score": None, "result": {"reason": "missing_truth_rows"}}
        result = optimize_prompts_for_media(
            media_id,
            media_rows,
            media_path=str(job.get("media_path") or ""),
            subtitle_path=str(job.get("subtitle_path") or ""),
            store_dir=str(store_dir) if store_dir else None,
        )
        return {"status": "complete", "score": float(result.get("best_score", 0.0) or 0.0), "result": result}
    return {"status": "failed", "score": None, "result": {"reason": f"unsupported_job_type:{job_type}"}}


def run_training_queue_once(
    store_dir: str | Path | None = None,
    *,
    cancel_callback=None,
) -> dict[str, Any]:
    payload = load_training_queue(store_dir)
    jobs = sorted(
        list(payload.get("items") or []),
        key=lambda item: (str(item.get("status") or "") != "waiting", int(item.get("priority", 9999) or 9999)),
    )
    target = next((item for item in jobs if str(item.get("status") or "") == "waiting"), None)
    if target is None:
        return {"processed": False, "reason": "no_pending_job"}

    job_id = str(target.get("job_id") or "")
    job_type = str(target.get("job_type") or "")
    media_label = str(target.get("media_path") or target.get("media_id") or "global")
    get_logger().log(f"🧠 [개인화 학습] 시작: {job_type} / {media_label}")
    payload = load_training_queue(store_dir)
    payload = _update_job(
        payload,
        job_id,
        status="in_progress",
        progress=0.1,
        last_error="",
        attempts=int(target.get("attempts", 0) or 0) + 1,
        payload=_checkpoint_payload(
            target,
            "started",
            job_type=job_type,
            media_path=media_label,
            resumable=True,
        ),
    )
    _save_queue_payload(payload, store_dir)

    def save_progress(update: dict[str, Any]) -> None:
        processed = int(update.get("processed", 0) or 0)
        total = int(update.get("total", 0) or 0)
        if total <= 0:
            return
        progress = 0.1 + min(0.85, max(0.0, processed / total) * 0.85)
        message = (
            f"voice clip extraction {processed}/{total} "
            f"(new {int(update.get('extracted', 0) or 0)}, "
            f"ready {int(update.get('already_ready', 0) or 0)}, "
            f"skipped {int(update.get('skipped', 0) or 0)}, "
            f"errors {int(update.get('errors', 0) or 0)})"
        )
        progress_payload = load_training_queue(store_dir)
        current_job = _job_from_payload(progress_payload, job_id) or target
        progress_payload = _update_job(
            progress_payload,
            job_id,
            status="in_progress",
            progress=round(progress, 4),
            last_error=message,
            payload=_checkpoint_payload(
                current_job,
                "voice_clip_extraction",
                processed=processed,
                total=total,
                extracted=int(update.get("extracted", 0) or 0),
                already_ready=int(update.get("already_ready", 0) or 0),
                skipped=int(update.get("skipped", 0) or 0),
                errors=int(update.get("errors", 0) or 0),
                resumable=True,
            ),
        )
        _save_queue_payload(progress_payload, store_dir)

    try:
        outcome = run_training_job(
            target,
            store_dir=store_dir,
            progress_callback=save_progress,
            cancel_callback=cancel_callback,
        )
        payload = load_training_queue(store_dir)
        outcome_status = str(outcome.get("status") or "complete")
        outcome_reason = str((outcome.get("result") or {}).get("reason") or "")
        current_job = _job_from_payload(payload, job_id) or target
        checkpoint_stage = "completed" if outcome_status == "complete" else ("paused_for_resume" if outcome_status == "waiting" else outcome_status)
        checkpoint_progress = float(current_job.get("progress", 0.0) or 0.0)
        payload = _update_job(
            payload,
            job_id,
            status=outcome_status,
            progress=1.0 if outcome_status in {"complete", "partial"} else checkpoint_progress,
            score=outcome.get("score"),
            last_error="" if outcome_status == "complete" else outcome_reason,
            payload=_checkpoint_payload(
                current_job,
                checkpoint_stage,
                job_type=job_type,
                status=outcome_status,
                reason=outcome_reason,
                score=outcome.get("score"),
                resumable=outcome_status in {"waiting", "failed"},
            ),
        )
        _save_queue_payload(payload, store_dir)
        prune_result: dict[str, Any] = {}
        if outcome_status == "complete":
            appended_counts: dict[str, int] = {}
            result_payload = dict(outcome.get("result") or {})
            if job_type == "optimize_settings":
                appended_counts["setting_trials"] = int(result_payload.get("trial_count", 0) or 0)
            elif job_type == "optimize_prompts":
                appended_counts["prompt_trials"] = int(result_payload.get("trial_count", 0) or 0)
            try:
                prune_result = prune_low_value_personalization_data(
                    store_dir=store_dir,
                    trigger=f"training_job:{job_type}",
                    appended_counts=appended_counts,
                )
                outcome["retention"] = prune_result
            except Exception as prune_exc:
                get_logger().log(f"⚠️ [개인화 학습] 낮은 점수 정리 실패: {prune_exc}")
            try:
                retrieval_index = build_lora_retrieval_index(store_dir)
                outcome["retrieval_index"] = {
                    "doc_count": int(retrieval_index.get("doc_count", 0) or 0),
                    "updated_at": retrieval_index.get("updated_at"),
                }
            except Exception as index_exc:
                get_logger().log(f"⚠️ [개인화 학습] LoRA 검색 인덱스 갱신 실패: {index_exc}")
        refresh_lora_personalization_manifest(store_dir)
        summary_bits = [f"status={outcome.get('status', 'complete')}"]
        if outcome.get("score") is not None:
            summary_bits.append(f"score={float(outcome.get('score') or 0.0):.2f}")
        if int(prune_result.get("total_removed", 0) or 0) > 0:
            summary_bits.append(f"pruned={int(prune_result.get('total_removed', 0) or 0)}")
        reason = str((outcome.get("result") or {}).get("best_reason") or (outcome.get("result") or {}).get("reason") or "").strip()
        if reason:
            summary_bits.append(reason)
        get_logger().log(f"🧠 [개인화 학습] 완료: {job_type} / {' | '.join(summary_bits)}")
        return {"processed": True, "job_id": job_id, "outcome": outcome}
    except Exception as exc:
        payload = load_training_queue(store_dir)
        current_job = _job_from_payload(payload, job_id) or target
        payload = _update_job(
            payload,
            job_id,
            status="failed",
            progress=float(current_job.get("progress", 0.0) or 0.0),
            last_error=str(exc),
            payload=_checkpoint_payload(
                current_job,
                "failed",
                job_type=job_type,
                reason=str(exc),
                resumable=True,
            ),
        )
        _save_queue_payload(payload, store_dir)
        refresh_lora_personalization_manifest(store_dir)
        get_logger().log(f"⚠️ [개인화 학습] 실패: {job_type} / {exc}")
        return {"processed": True, "job_id": job_id, "outcome": {"status": "failed", "result": {"reason": str(exc)}}}


class PersonalizationIdleTrainer(QObject):
    def __init__(self, owner, *, store_dir: str | Path | None = None):
        super().__init__(owner)
        self.owner = owner
        self.store_dir = str(store_dir) if store_dir else None
        self.idle_window_ms = 60_000
        self.last_user_activity_ms = QDateTime.currentMSecsSinceEpoch()
        self._worker_thread: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._running_job_id = ""
        self._last_run_result: dict[str, Any] = {}
        recover_interrupted_training_jobs(self.store_dir, reason="trainer_startup")
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2_500)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

    def note_user_activity(self) -> None:
        self.last_user_activity_ms = QDateTime.currentMSecsSinceEpoch()

    def queue_summary(self) -> dict[str, int]:
        counts = defaultdict(int)
        payload = load_training_queue(self.store_dir)
        for item in list(payload.get("items") or []):
            counts[str(item.get("status") or "waiting")] += 1
        return dict(counts)

    def has_pending_jobs(self) -> bool:
        payload = load_training_queue(self.store_dir)
        return any(str(item.get("status") or "") == "waiting" for item in list(payload.get("items") or []))

    def is_busy(self) -> bool:
        thread = self._worker_thread
        return bool(thread is not None and thread.is_alive())

    def last_run_result(self) -> dict[str, Any]:
        return dict(self._last_run_result or {})

    def _learning_context(self) -> str:
        stack = getattr(self.owner, "stack", None)
        try:
            if stack is not None and int(stack.currentIndex()) == 0:
                return "home"
        except Exception:
            pass
        mode = str(getattr(self.owner, "_current_work_mode", "") or "").strip().lower()
        if mode:
            return mode
        return "editor"

    def _context_allows_auto_training(self) -> bool:
        return self._learning_context() in {"home", "editor"}

    def _process_next_job_once(self) -> dict[str, Any]:
        result = run_training_queue_once(self.store_dir, cancel_callback=self._stop_requested.is_set)
        self._last_run_result = dict(result or {})
        return result

    def run_pending_now(self) -> dict[str, Any]:
        if self.is_busy():
            return {"started": False, "reason": "busy"}
        result = self._process_next_job_once()
        return {"started": bool(result.get("processed")), "result": result}

    def _background_run_once(self) -> None:
        self._process_next_job_once()

    def start_background_run(self) -> dict[str, Any]:
        with self._worker_lock:
            if self.is_busy():
                return {"started": False, "reason": "busy"}
            if not self.has_pending_jobs():
                return {"started": False, "reason": "no_pending_job"}
            self._stop_requested.clear()
            self._worker_thread = threading.Thread(
                target=self._background_run_once,
                daemon=True,
                name="personalization-idle-trainer",
            )
            self._worker_thread.start()
            return {"started": True, "reason": "background"}

    def shutdown(self, *, timeout_sec: float = 3.0) -> dict[str, Any]:
        self._poll_timer.stop()
        self._stop_requested.set()
        thread = self._worker_thread
        alive = bool(thread is not None and thread.is_alive())
        if alive:
            try:
                thread.join(timeout=max(0.0, float(timeout_sec)))
            except RuntimeError:
                pass
        still_alive = bool(thread is not None and thread.is_alive())
        if still_alive:
            return {"stopped": False, "busy": True}
        recover_interrupted_training_jobs(self.store_dir, reason="shutdown")
        return {"stopped": True, "busy": False}

    def pause_pending_jobs(self) -> dict[str, Any]:
        payload = load_training_queue(self.store_dir)
        items = []
        for item in list(payload.get("items") or []):
            updated = dict(item)
            if str(updated.get("status") or "") == "waiting":
                updated["status"] = "paused"
            items.append(updated)
        return save_training_queue(items, self.store_dir)

    def resume_pending_jobs(self) -> dict[str, Any]:
        payload = load_training_queue(self.store_dir)
        items = []
        for item in list(payload.get("items") or []):
            updated = dict(item)
            if str(updated.get("status") or "") == "paused":
                updated["status"] = "waiting"
            items.append(updated)
        return save_training_queue(items, self.store_dir)

    def clear_pending_jobs(self, *, keep_completed: bool = True) -> dict[str, Any]:
        return clear_training_queue(self.store_dir, keep_completed=keep_completed)

    def _owner_busy(self) -> bool:
        backend = getattr(self.owner, "backend", None)
        if backend is not None and bool(getattr(backend, "_active", False)):
            return True
        if hasattr(self.owner, "_is_editor_actively_editing") and self.owner._is_editor_actively_editing():
            return True
        if bool(getattr(self.owner, "_auto_processing_active", False)):
            return True
        return False

    def _owner_idle(self) -> bool:
        if self._owner_busy():
            return False
        if not self._context_allows_auto_training():
            return False
        return (QDateTime.currentMSecsSinceEpoch() - int(self.last_user_activity_ms or 0)) >= int(self.idle_window_ms)

    def _poll(self) -> None:
        if self.is_busy():
            return
        if not self._owner_idle():
            return
        self.start_background_run()


__all__ = [
    "PersonalizationIdleTrainer",
    "enqueue_default_training_jobs",
    "recover_interrupted_training_jobs",
    "run_training_job",
    "run_training_queue_once",
]
