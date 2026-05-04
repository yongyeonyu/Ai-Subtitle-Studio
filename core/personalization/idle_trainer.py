from __future__ import annotations

import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDateTime, QObject, QTimer

from core.personalization.lora_models import TrainingQueueItem, stable_hash
from core.personalization.lora_optimizer import optimize_prompts_for_media, optimize_settings_for_media
from core.personalization.lora_rule_learning import learn_rules_from_truth_table, load_truth_table_rows
from core.personalization.lora_storage import (
    clear_training_queue,
    load_training_queue,
    refresh_lora_personalization_manifest,
    save_training_queue,
    store_paths,
    upsert_training_queue_items,
)
from core.runtime.logger import get_logger
from core.personalization.text_lora_runner import save_text_lora_training_plan, save_voice_lora_profile_manifest


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


def _update_job(payload: dict[str, Any], job_id: str, **changes) -> dict[str, Any]:
    items = []
    for item in list(payload.get("items") or []):
        if str(item.get("job_id") or "") == str(job_id):
            updated = dict(item)
            updated.update(changes)
            items.append(updated)
        else:
            items.append(dict(item))
    return {"schema": payload.get("schema"), "updated_at": payload.get("updated_at"), "items": items}


def _save_queue_payload(payload: dict[str, Any], store_dir: str | Path | None = None) -> dict[str, Any]:
    return save_training_queue(list(payload.get("items") or []), store_dir)


def run_training_job(
    job: dict[str, Any],
    *,
    store_dir: str | Path | None = None,
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
        result = save_voice_lora_profile_manifest(
            bridge_path=store_root / "voice_lora_bridge.jsonl",
            manifest_path=store_root / "voice_lora_profile_manifest.json",
        )
        return {"status": "complete", "score": float(result.get("speaker_profiles", 0) or 0), "result": result}
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


def run_training_queue_once(store_dir: str | Path | None = None) -> dict[str, Any]:
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
    payload = _update_job(payload, job_id, status="in_progress", progress=0.1, last_error="", attempts=int(target.get("attempts", 0) or 0) + 1)
    _save_queue_payload(payload, store_dir)
    try:
        outcome = run_training_job(target, store_dir=store_dir)
        payload = load_training_queue(store_dir)
        payload = _update_job(
            payload,
            job_id,
            status=str(outcome.get("status") or "complete"),
            progress=1.0 if str(outcome.get("status") or "") == "complete" else 0.0,
            score=outcome.get("score"),
            last_error="" if str(outcome.get("status") or "") != "failed" else str((outcome.get("result") or {}).get("reason") or ""),
        )
        _save_queue_payload(payload, store_dir)
        refresh_lora_personalization_manifest(store_dir)
        summary_bits = [f"status={outcome.get('status', 'complete')}"]
        if outcome.get("score") is not None:
            summary_bits.append(f"score={float(outcome.get('score') or 0.0):.2f}")
        reason = str((outcome.get("result") or {}).get("best_reason") or (outcome.get("result") or {}).get("reason") or "").strip()
        if reason:
            summary_bits.append(reason)
        get_logger().log(f"🧠 [개인화 학습] 완료: {job_type} / {' | '.join(summary_bits)}")
        return {"processed": True, "job_id": job_id, "outcome": outcome}
    except Exception as exc:
        payload = load_training_queue(store_dir)
        payload = _update_job(payload, job_id, status="failed", progress=0.0, last_error=str(exc))
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
        self._running_job_id = ""
        self._last_run_result: dict[str, Any] = {}
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

    def _process_next_job_once(self) -> dict[str, Any]:
        result = run_training_queue_once(self.store_dir)
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
            self._worker_thread = threading.Thread(
                target=self._background_run_once,
                daemon=True,
                name="personalization-idle-trainer",
            )
            self._worker_thread.start()
            return {"started": True, "reason": "background"}

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
    "run_training_job",
    "run_training_queue_once",
]
