from __future__ import annotations

import gc
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDateTime, QObject, QTimer, pyqtSignal

from core.personalization.lora_models import TrainingQueueItem, iso_now, stable_hash
from core.personalization.lora_optimizer import optimize_prompts_for_media, optimize_settings_for_media
from core.personalization.lora_retention import prune_low_value_personalization_data
from core.personalization.lora_rule_learning import learn_rules_from_truth_table, load_truth_table_rows
from core.personalization.lora_storage import (
    clear_training_queue,
    load_training_queue,
    refresh_unified_lora_data_bundle,
    refresh_lora_personalization_manifest,
    save_training_queue,
    store_paths,
    upsert_training_queue_items,
)
from core.personalization.lora_store_common import read_jsonl
from core.personalization.lora_vector_retriever import build_lora_retrieval_index
from core.personalization.subtitle_pattern_index import save_subtitle_pattern_index
from core.runtime.multi_process import manual_lora_runtime_settings
from core.runtime.logger import get_logger
from core.personalization.stt1_whisper_adapter_runner import save_stt1_whisper_adapter_training_plan
from core.personalization.text_lora_runner import (
    save_text_lora_training_plan,
    save_voice_lora_profile_manifest,
    save_voice_lora_training_plan,
)
from core.personalization.deferred_editor_learning import (
    DEFERRED_EDITOR_LEARNING_JOB_TYPE,
    run_deferred_editor_learning_job,
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
HARD_CASE_SUBTITLE_POLICY_JOB_TYPE = "hard_case_subtitle_policy"
QUEUE_JOB_TYPE_LABELS = {
    "analyze_truth_table": "truth 분석",
    "build_text_training_plan": "text 학습계획",
    "build_voice_profiles": "목소리 프로필",
    "build_stt1_whisper_adapter": "STT1 어댑터",
    "build_subtitle_pattern_index": "자막 패턴 인덱스",
    "build_retrieval_index": "검색 인덱스",
    "optimize_settings": "설정 최적화",
    "optimize_prompts": "프롬프트 최적화",
    DEFERRED_EDITOR_LEARNING_JOB_TYPE: "에디터 저장 학습",
    HARD_CASE_SUBTITLE_POLICY_JOB_TYPE: "하드케이스 자막 정책",
}
LOW_RESOURCE_POLL_INTERVAL_MS = 30_000
LOW_RESOURCE_IDLE_WINDOW_MS = 600_000
LOW_RESOURCE_COOLDOWN_MS = 600_000
LOW_RESOURCE_INDEX_REFRESH_INTERVAL_SEC = 1_800.0
LOW_RESOURCE_PROGRESS_SAVE_INTERVAL_SEC = 3.0
LOW_RESOURCE_PROGRESS_BUCKET_STEP = 25
MANUAL_PROGRESS_BUCKET_STEP = 10
LOW_RESOURCE_INDEX_DEFERRED_REASON = "low_resource_index_refresh_deferred"
LOW_RESOURCE_TO_HEAVY_IDLE_MS = 900_000
AUDIO_EXTRACTION_JOB_TYPES = {"build_voice_profiles", "build_stt1_whisper_adapter"}
FOREGROUND_ACTIVITY_HOLD_MS = 600_000


def _cancel_requested(cancel_callback) -> bool:
    if not callable(cancel_callback):
        return False
    try:
        return bool(cancel_callback())
    except Exception:
        return False


def _cancelled_training_result(reason: str = "cancelled") -> dict[str, Any]:
    return {"status": "waiting", "score": None, "result": {"reason": str(reason or "cancelled"), "cancelled": True}}


def _cleanup_lora_training_runtime(
    reason: str = "idle_training_stop",
    *,
    include_gpu: bool = True,
) -> dict[str, Any]:
    """Release LoRA/audio runtime caches after an idle-training interruption."""
    actions: list[str] = []
    for module_name, func_name, kwargs in (
        ("core.personalization.lora_vector_retriever", "clear_lora_retrieval_caches", {}),
        ("core.audio.runtime_cleanup", "clear_audio_model_memory_caches", {"include_gpu": include_gpu}),
        (
            "core.runtime.memory_manager",
            "trim_runtime_memory_caches",
            {"stage": "personalization_stop", "include_gpu": include_gpu},
        ),
    ):
        try:
            module = __import__(module_name, fromlist=[func_name])
            func = getattr(module, func_name, None)
            if not callable(func):
                continue
            result = func(**kwargs)
            actions.append(f"{module_name}.{func_name}")
            if isinstance(result, dict):
                actions.extend(str(action) for action in list(result.get("actions") or []) if action)
        except Exception:
            continue
    try:
        gc.collect()
        actions.append("gc.collect")
    except Exception:
        pass
    return {"reason": str(reason or "idle_training_stop"), "actions": actions}


def _queue_status_label(status: Any) -> str:
    text = str(status or "waiting")
    return QUEUE_STATUS_LABELS.get(text, text)


def _queue_job_type_label(job_type: Any) -> str:
    text = str(job_type or "-")
    return QUEUE_JOB_TYPE_LABELS.get(text, text)


def format_training_queue_status_summary(payload_or_items: Any) -> str:
    if isinstance(payload_or_items, dict):
        queue_items = list(payload_or_items.get("items") or [])
    else:
        queue_items = list(payload_or_items or [])
    queue_counts: dict[str, int] = {}
    for item in queue_items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "waiting")
        queue_counts[status] = int(queue_counts.get(status, 0) or 0) + 1
    return " · ".join(
        f"{_queue_status_label(key)} {value}개"
        for key, value in sorted(queue_counts.items())
    ) or "대기 작업 없음"


def _training_mode_label(job: dict[str, Any], *, low_resource: bool = False) -> str:
    payload = dict((job or {}).get("payload") or {})
    if bool(payload.get("manual_full_training")):
        return "Full"
    return "저전력 자동" if low_resource else "수동"


def _queue_waiting_position(jobs: list[dict[str, Any]], job_id: str) -> tuple[int, int]:
    waiting_jobs = [dict(item) for item in list(jobs or []) if str(item.get("status") or "") == "waiting"]
    total = len(waiting_jobs)
    for index, item in enumerate(waiting_jobs, start=1):
        if str(item.get("job_id") or "") == str(job_id):
            return index, total
    return 1 if total else 0, total


def _media_log_label(value: Any, *, max_len: int = 96) -> str:
    text = str(value or "global").strip() or "global"
    if len(text) <= max_len:
        return text
    return f"...{text[-max_len:]}"


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
            job_type="build_subtitle_pattern_index",
            priority=30,
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_retrieval_index",
            priority=40,
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


def _truth_media_pairs(store_dir: str | Path | None = None) -> list[dict[str, Any]]:
    rows = load_truth_table_rows(store_dir)
    pairs_by_media_id: dict[str, dict[str, Any]] = {}
    for row in list(rows or []):
        media_id = str(row.get("media_id") or "").strip()
        if not media_id:
            continue
        current = pairs_by_media_id.setdefault(
            media_id,
            {
                "media_id": media_id,
                "media_path": str(row.get("media_path") or ""),
                "subtitle_path": str(row.get("subtitle_path") or ""),
            },
        )
        if not current.get("media_path") and row.get("media_path"):
            current["media_path"] = str(row.get("media_path") or "")
        if not current.get("subtitle_path") and row.get("subtitle_path"):
            current["subtitle_path"] = str(row.get("subtitle_path") or "")
    return list(pairs_by_media_id.values())


def _manual_full_training_jobs(
    imported_pairs: list[dict[str, Any]] | None = None,
    *,
    store_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    pairs_by_media_id: dict[str, dict[str, Any]] = {}
    for pair in [*_truth_media_pairs(store_dir), *list(imported_pairs or [])]:
        media_id = str(pair.get("media_id") or stable_hash({"media_path": pair.get("media_path", "")})[:16])
        if not media_id:
            continue
        pairs_by_media_id[media_id] = {
            "media_id": media_id,
            "media_path": str(pair.get("media_path") or ""),
            "subtitle_path": str(pair.get("subtitle_path") or ""),
        }

    jobs: list[dict[str, Any]] = [
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="analyze_truth_table",
            priority=10,
            payload={"manual_full_training": True},
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_text_training_plan",
            priority=20,
            payload={"manual_full_training": True},
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_voice_profiles",
            priority=25,
            payload={"manual_full_training": True, "extract_audio": True},
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_stt1_whisper_adapter",
            priority=28,
            payload={"manual_full_training": True, "extract_audio": True},
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_subtitle_pattern_index",
            priority=30,
            payload={"manual_full_training": True, "force": True},
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_retrieval_index",
            priority=40,
            payload={"manual_full_training": True, "force": True},
        ).to_record(),
    ]
    for index, pair in enumerate(pairs_by_media_id.values(), start=1):
        media_id = str(pair.get("media_id") or "")
        media_path = str(pair.get("media_path") or "")
        subtitle_path = str(pair.get("subtitle_path") or "")
        jobs.append(
            TrainingQueueItem(
                media_id=media_id,
                media_path=media_path,
                subtitle_path=subtitle_path,
                job_type="optimize_settings",
                priority=100 + index,
                payload={"manual_full_training": True},
            ).to_record()
        )
        jobs.append(
            TrainingQueueItem(
                media_id=media_id,
                media_path=media_path,
                subtitle_path=subtitle_path,
                job_type="optimize_prompts",
                priority=200 + index,
                payload={"manual_full_training": True},
            ).to_record()
        )
    return jobs


def enqueue_full_training_jobs(
    imported_pairs: list[dict[str, Any]] | None = None,
    *,
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Queue a manual full LoRA refresh, re-running matching completed jobs too."""
    jobs = _manual_full_training_jobs(imported_pairs, store_dir=store_dir)
    payload = load_training_queue(store_dir)
    current_items = list(payload.get("items") or [])
    by_job_id = {
        str(item.get("job_id") or ""): dict(item)
        for item in current_items
        if str(item.get("job_id") or "")
    }
    ordered_job_ids = [str(item.get("job_id") or "") for item in current_items if str(item.get("job_id") or "")]
    now = iso_now()
    requeued = 0
    for job in jobs:
        job_id = str(job.get("job_id") or "")
        if not job_id:
            continue
        existing = dict(by_job_id.get(job_id) or {})
        if job_id not in by_job_id:
            ordered_job_ids.append(job_id)
        merged = dict(job)
        if existing:
            merged["created_at"] = str(existing.get("created_at") or merged.get("created_at") or now)
            merged["attempts"] = int(existing.get("attempts", 0) or 0)
        merged.update(
            {
                "status": "waiting",
                "progress": 0.0,
                "score": None,
                "last_error": "manual_full_training_requeued" if existing else "",
                "updated_at": now,
            }
        )
        payload_data = dict(merged.get("payload") or {})
        payload_data["manual_full_training_queued_at"] = now
        merged["payload"] = payload_data
        by_job_id[job_id] = merged
        requeued += 1

    merged_items = [by_job_id[job_id] for job_id in ordered_job_ids if job_id in by_job_id]
    saved = save_training_queue(merged_items, store_dir)
    saved["manual_full_training"] = {
        "queued_jobs": len(jobs),
        "requeued_jobs": requeued,
        "truth_media_count": max(0, (len(jobs) - 5) // 2),
    }
    refresh_lora_personalization_manifest(store_dir)
    get_logger().log(
        "🧠 [LoRA Full 학습] 큐 준비: "
        f"전체 {len(jobs)}개 · 재학습 {requeued}개 · 미디어 {saved['manual_full_training']['truth_media_count']}개"
    )
    return saved


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


def _save_queue_payload(
    payload: dict[str, Any],
    store_dir: str | Path | None = None,
    *,
    refresh_manifest: bool = True,
) -> dict[str, Any]:
    return save_training_queue(
        list(payload.get("items") or []),
        store_dir,
        refresh_manifest=refresh_manifest,
    )


def _lora_index_refresh_due(
    store_dir: str | Path | None = None,
    *,
    min_interval_sec: float = LOW_RESOURCE_INDEX_REFRESH_INTERVAL_SEC,
) -> bool:
    """Throttle retrieval-index rebuilds during low-resource idle learning."""
    try:
        index_path = store_paths(store_dir)["lora_retrieval_index"]
    except Exception:
        return True
    if not index_path.exists():
        return True
    try:
        age_sec = time.time() - float(index_path.stat().st_mtime)
    except Exception:
        return True
    return age_sec >= max(0.0, float(min_interval_sec or 0.0))


def _low_resource_job_copy(job: dict[str, Any]) -> dict[str, Any]:
    """Downgrade expensive queued work when it resumes as idle background learning."""
    adjusted = dict(job or {})
    job_type = str(adjusted.get("job_type") or "")
    payload = dict(adjusted.get("payload") or {})
    if bool(payload.get("manual_full_training")):
        payload["manual_full_training"] = False
        payload["resumed_as_low_resource_idle"] = True
    if job_type in AUDIO_EXTRACTION_JOB_TYPES and bool(payload.get("extract_audio")):
        payload["extract_audio"] = False
        payload["audio_extraction_deferred"] = True
    if job_type == "build_retrieval_index":
        payload["force"] = False
    adjusted["payload"] = payload
    return adjusted


def _legacy_unsupported_hard_case_error(item: dict[str, Any]) -> bool:
    if str(item.get("job_type") or "") != HARD_CASE_SUBTITLE_POLICY_JOB_TYPE:
        return False
    text_parts = [str(item.get("last_error") or "")]
    payload = dict(item.get("payload") or {})
    checkpoint = dict(payload.get("checkpoint") or {})
    text_parts.append(str(checkpoint.get("reason") or ""))
    text_parts.append(str(checkpoint.get("stage") or ""))
    return any(f"unsupported_job_type:{HARD_CASE_SUBTITLE_POLICY_JOB_TYPE}" in part for part in text_parts)


def _hard_case_event_exists(job: dict[str, Any], store_dir: str | Path | None = None) -> tuple[bool, str]:
    payload = dict(job.get("payload") or {})
    event_id = str(payload.get("event_id") or "").strip()
    if not event_id:
        return False, "missing_event_id"
    try:
        rows = read_jsonl(store_paths(store_dir)["deep_policy_events"])
    except Exception:
        rows = []
    for row in rows:
        if str(row.get("event_id") or "") == event_id:
            return True, event_id
    return False, event_id


def _run_hard_case_subtitle_policy_job(
    job: dict[str, Any],
    *,
    store_dir: str | Path | None = None,
    cancel_callback=None,
) -> dict[str, Any]:
    if _cancel_requested(cancel_callback):
        return _cancelled_training_result()
    found, event_id_or_reason = _hard_case_event_exists(job, store_dir)
    if not found:
        return {
            "status": "skipped",
            "score": None,
            "result": {
                "reason": f"hard_case_event_missing:{event_id_or_reason}",
                "event_id": "" if event_id_or_reason == "missing_event_id" else event_id_or_reason,
            },
        }

    payload = dict(job.get("payload") or {})
    get_logger().log(
        "🧠 [LoRA 학습] 하드케이스 자막 정책: "
        f"{event_id_or_reason} 이벤트를 패턴 인덱스에 반영 중"
    )
    pattern_result = save_subtitle_pattern_index(store_dir, force=True)
    if _cancel_requested(cancel_callback):
        return _cancelled_training_result()
    return {
        "status": "complete",
        "score": float(pattern_result.get("pattern_count", 0) or 0),
        "result": {
            "reason": "hard_case_policy_indexed",
            "event_id": event_id_or_reason,
            "hard_case_reasons": list(payload.get("hard_case_reasons") or []),
            "subtitle_pattern_index": pattern_result,
        },
    }


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
        elif str(updated.get("status") or "") == "failed" and _legacy_unsupported_hard_case_error(updated):
            updated["status"] = "waiting"
            updated["progress"] = 0.0
            updated["updated_at"] = now
            updated["last_error"] = f"recovered_{reason}: hard case job type is now supported"
            updated["payload"] = _checkpoint_payload(
                updated,
                "recovered_after_unsupported_job_type",
                reason=str(reason),
                previous_status="failed",
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
    job_payload = dict(job.get("payload") or {})
    manual_full_training = bool(job_payload.get("manual_full_training"))
    resource_settings = manual_lora_runtime_settings() if manual_full_training else None
    if _cancel_requested(cancel_callback):
        return _cancelled_training_result()
    rows = load_truth_table_rows(store_dir)
    grouped_rows = _group_truth_rows_by_media(rows)
    paths = store_paths(store_dir)
    job_label = _queue_job_type_label(job_type)
    media_label = _media_log_label(job.get("media_path") or media_id or "global")

    if job_type == DEFERRED_EDITOR_LEARNING_JOB_TYPE:
        get_logger().log(f"🧠 [LoRA 학습] {job_label}: 저장된 에디터 자막을 Home-idle에서 반영 중")
        return run_deferred_editor_learning_job(job, store_dir=store_dir, cancel_callback=cancel_callback)
    if job_type == HARD_CASE_SUBTITLE_POLICY_JOB_TYPE:
        return _run_hard_case_subtitle_policy_job(
            job,
            store_dir=store_dir,
            cancel_callback=cancel_callback,
        )
    if job_type == "analyze_truth_table":
        get_logger().log(f"🧠 [LoRA 학습] {job_label}: truth table 규칙 분석 중")
        result = learn_rules_from_truth_table(store_dir)
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
        return {"status": "complete", "score": None, "result": result}
    if job_type == "build_text_training_plan":
        get_logger().log(f"🧠 [LoRA 학습] {job_label}: text LoRA 학습계획 생성 중")
        result = save_text_lora_training_plan(
            corpus_path=paths["text_lora_corpus"],
            plan_path=paths["text_lora_training_plan"],
            output_dir=paths["trained_adapters"] / "personal_text_lora",
        )
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
        return {"status": "complete", "score": float(result.get("usable_rows", 0) or 0), "result": result}
    if job_type == "build_voice_profiles":
        extract_audio = bool(job_payload.get("extract_audio"))
        if resource_settings is not None:
            get_logger().log(
                "🧠 [LoRA Full 학습] 풀가동: "
                f"CPU {int(resource_settings.get('runtime_native_threads', 1) or 1)}코어 사용 · "
                "종료 반응용 1코어 예약 · GPU/NPU 가속 우선"
            )
        get_logger().log(
            f"🧠 [LoRA 학습] {job_label}: 목소리 프로필"
            f"{' + WAV 클립' if extract_audio else ''} 생성 중"
        )
        profile_result = save_voice_lora_profile_manifest(
            bridge_path=paths["voice_lora_bridge"],
            manifest_path=paths["voice_lora_profile_manifest"],
        )
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
        plan_result = save_voice_lora_training_plan(
            bridge_path=paths["voice_lora_bridge"],
            plan_path=paths["voice_lora_training_plan"],
            dataset_manifest_path=paths["voice_lora_dataset_manifest"],
            extract_audio=extract_audio,
            progress_callback=progress_callback if extract_audio else None,
            cancel_callback=cancel_callback,
            resource_settings=resource_settings,
        )
        result = {"profile": profile_result, "training_plan": plan_result}
        if bool(plan_result.get("cancelled")):
            result["reason"] = "cancelled"
            return {"status": "waiting", "score": None, "result": result}
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
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
    if job_type == "build_stt1_whisper_adapter":
        if not rows:
            return {"status": "skipped", "score": None, "result": {"reason": "missing_truth_rows"}}
        extract_audio = bool(job_payload.get("extract_audio"))
        if resource_settings is not None:
            get_logger().log(
                "🧠 [LoRA Full 학습] 풀가동: "
                f"CPU {int(resource_settings.get('runtime_native_threads', 1) or 1)}코어 사용 · "
                "종료 반응용 1코어 예약 · GPU/NPU 가속 우선"
            )
        get_logger().log(
            f"🧠 [LoRA 학습] {job_label}: STT1 Whisper adapter"
            f"{' + WAV 클립' if extract_audio else ''} 준비 중"
        )
        result = save_stt1_whisper_adapter_training_plan(
            store_dir=store_dir,
            truth_table_path=paths["truth_table"],
            voice_bridge_path=paths["voice_lora_bridge"],
            multimodal_context_path=paths["multimodal_lora_context"],
            dataset_path=paths["stt1_whisper_adapter_dataset"],
            dataset_manifest_path=paths["stt1_whisper_adapter_dataset_manifest"],
            plan_path=paths["stt1_whisper_adapter_training_plan"],
            runtime_manifest_path=paths["stt1_whisper_adapter_runtime_manifest"],
            output_dir=paths["trained_adapters"] / "personal_stt1_whisper_adapter",
            extract_audio=extract_audio,
            progress_callback=progress_callback if extract_audio else None,
            cancel_callback=cancel_callback,
            resource_settings=resource_settings,
        )
        if bool(result.get("cancelled")):
            return {"status": "waiting", "score": None, "result": {"reason": "cancelled", **result}}
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
        usable = int(result.get("usable_rows", 0) or 0)
        ready = int(result.get("audio_ready_items", 0) or 0)
        errors = int(result.get("extraction_errors", 0) or 0)
        skipped = int(result.get("extraction_skipped", 0) or 0)
        status = "complete"
        reason = ""
        if extract_audio and usable > 0 and ready < usable and (errors > 0 or skipped > 0):
            status = "failed" if ready == 0 else "partial"
            reason = (
                f"stt1_adapter_audio_incomplete: ready {ready}/{usable}, "
                f"errors {errors}, skipped {skipped}"
            )
        elif not extract_audio:
            reason = "audio_extraction_deferred"
        elif bool(result.get("runtime_ready")):
            reason = f"runtime_ready:{str(result.get('runtime_model') or '').strip()}"
        return {
            "status": status,
            "score": float(ready if extract_audio else usable),
            "result": {**result, "reason": reason},
        }
    if job_type == "build_retrieval_index":
        job_payload = dict(job.get("payload") or {})
        force = bool(job_payload.get("force", True))
        get_logger().log(f"🧠 [LoRA 학습] {job_label}: 벡터 검색 인덱스와 ZIP 갱신 중")
        pattern_result = save_subtitle_pattern_index(store_dir, force=force)
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
        index_result = build_lora_retrieval_index(store_dir, force=force)
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
        bundle_result = refresh_unified_lora_data_bundle(store_dir, force=force)
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
        result = {
            "subtitle_pattern_index": pattern_result,
            "retrieval_index": index_result,
            "bundle": bundle_result,
            "doc_count": int(index_result.get("doc_count", 0) or 0),
            "pattern_count": int(pattern_result.get("pattern_count", 0) or 0),
            "record_count": int(bundle_result.get("record_count", 0) or 0),
        }
        return {"status": "complete", "score": float(result["doc_count"]), "result": result}
    if job_type == "build_subtitle_pattern_index":
        job_payload = dict(job.get("payload") or {})
        force = bool(job_payload.get("force", True))
        get_logger().log(f"🧠 [LoRA 학습] {job_label}: 원문 없는 자막 패턴 인덱스 생성 중")
        result = save_subtitle_pattern_index(store_dir, force=force)
        if _cancel_requested(cancel_callback):
            return _cancelled_training_result()
        return {"status": "complete", "score": float(result.get("pattern_count", 0) or 0), "result": result}
    if job_type == "optimize_settings":
        media_rows = grouped_rows.get(media_id, [])
        if not media_rows:
            return {"status": "skipped", "score": None, "result": {"reason": "missing_truth_rows"}}
        get_logger().log(f"🧠 [LoRA 학습] {job_label}: {media_label} · truth {len(media_rows)}행으로 설정 점수화 중")
        result = optimize_settings_for_media(
            media_id,
            media_rows,
            media_path=str(job.get("media_path") or ""),
            subtitle_path=str(job.get("subtitle_path") or ""),
            store_dir=str(store_dir) if store_dir else None,
            cancel_callback=cancel_callback,
        )
        if bool(result.get("cancelled")) or _cancel_requested(cancel_callback):
            return _cancelled_training_result(str(result.get("reason") or "cancelled"))
        return {"status": "complete", "score": float(result.get("best_score", 0.0) or 0.0), "result": result}
    if job_type == "optimize_prompts":
        media_rows = grouped_rows.get(media_id, [])
        if not media_rows:
            return {"status": "skipped", "score": None, "result": {"reason": "missing_truth_rows"}}
        get_logger().log(f"🧠 [LoRA 학습] {job_label}: {media_label} · truth {len(media_rows)}행으로 프롬프트 점수화 중")
        result = optimize_prompts_for_media(
            media_id,
            media_rows,
            media_path=str(job.get("media_path") or ""),
            subtitle_path=str(job.get("subtitle_path") or ""),
            store_dir=str(store_dir) if store_dir else None,
            cancel_callback=cancel_callback,
        )
        if bool(result.get("cancelled")) or _cancel_requested(cancel_callback):
            return _cancelled_training_result(str(result.get("reason") or "cancelled"))
        return {"status": "complete", "score": float(result.get("best_score", 0.0) or 0.0), "result": result}
    return {"status": "failed", "score": None, "result": {"reason": f"unsupported_job_type:{job_type}"}}


def run_training_queue_once(
    store_dir: str | Path | None = None,
    *,
    cancel_callback=None,
    low_resource: bool = False,
) -> dict[str, Any]:
    if callable(cancel_callback):
        try:
            if cancel_callback():
                return {"processed": False, "reason": "cancelled_before_start"}
        except Exception:
            pass
    payload = load_training_queue(store_dir)
    jobs = sorted(
        list(payload.get("items") or []),
        key=lambda item: (str(item.get("status") or "") != "waiting", int(item.get("priority", 9999) or 9999)),
    )
    target = next((item for item in jobs if str(item.get("status") or "") == "waiting"), None)
    if target is None:
        return {"processed": False, "reason": "no_pending_job"}
    if low_resource:
        target = _low_resource_job_copy(target)

    job_id = str(target.get("job_id") or "")
    job_type = str(target.get("job_type") or "")
    media_label = _media_log_label(target.get("media_path") or target.get("media_id") or "global")
    position, waiting_total = _queue_waiting_position(jobs, job_id)
    mode_label = _training_mode_label(target, low_resource=low_resource)
    get_logger().log(
        f"🧠 [LoRA 학습] 시작: {mode_label} · {position}/{waiting_total} · "
        f"{_queue_job_type_label(job_type)} · {media_label}"
    )
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
    _save_queue_payload(payload, store_dir, refresh_manifest=not low_resource)

    if callable(cancel_callback):
        try:
            if cancel_callback():
                payload = load_training_queue(store_dir)
                current_job = _job_from_payload(payload, job_id) or target
                payload = _update_job(
                    payload,
                    job_id,
                    status="waiting",
                    progress=float(current_job.get("progress", 0.0) or 0.0),
                    last_error="paused_for_foreground_activity",
                    payload=_checkpoint_payload(
                        current_job,
                        "paused_for_foreground_activity",
                        job_type=job_type,
                        resumable=True,
                    ),
                )
                _save_queue_payload(payload, store_dir, refresh_manifest=not low_resource)
                get_logger().log(f"⏸️ [LoRA 학습] 일시정지: {mode_label} · {_queue_job_type_label(job_type)}")
                return {"processed": False, "job_id": job_id, "reason": "cancelled_before_job_run"}
        except Exception:
            pass

    progress_buckets: dict[str, int] = {}
    progress_save_times: dict[str, float] = {}

    def save_progress(update: dict[str, Any]) -> None:
        if _cancel_requested(cancel_callback):
            return
        processed = int(update.get("processed", 0) or 0)
        total = int(update.get("total", 0) or 0)
        if total <= 0:
            return
        progress_kind = str(update.get("kind") or "voice_lora_audio").strip() or "voice_lora_audio"
        progress_stage = str(update.get("stage") or "voice_clip_extraction").strip() or "voice_clip_extraction"
        progress_label = "STT1 음성 클립" if progress_kind == "stt1_whisper_audio" else "목소리 클립"
        progress = 0.1 + min(0.85, max(0.0, processed / total) * 0.85)
        message = (
            f"{progress_label} {processed}/{total} "
            f"(new {int(update.get('extracted', 0) or 0)}, "
            f"ready {int(update.get('already_ready', 0) or 0)}, "
            f"skipped {int(update.get('skipped', 0) or 0)}, "
            f"errors {int(update.get('errors', 0) or 0)})"
        )
        pct = int(min(100, max(0, round((processed / total) * 100))))
        bucket_step = LOW_RESOURCE_PROGRESS_BUCKET_STEP if low_resource else MANUAL_PROGRESS_BUCKET_STEP
        bucket = 100 if processed >= total else (pct // max(1, bucket_step)) * max(1, bucket_step)
        bucket_key = f"{progress_kind}:{job_id}"
        previous_bucket = int(progress_buckets.get(bucket_key, -1))
        bucket_changed = bucket != previous_bucket
        now_mono = time.monotonic()
        last_save_at = float(progress_save_times.get(bucket_key, 0.0) or 0.0)
        save_due = (now_mono - last_save_at) >= LOW_RESOURCE_PROGRESS_SAVE_INTERVAL_SEC
        if low_resource and not bucket_changed and not save_due and processed < total:
            return
        progress_save_times[bucket_key] = now_mono
        if bucket_changed:
            progress_buckets[bucket_key] = bucket
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
                progress_stage,
                processed=processed,
                total=total,
                extracted=int(update.get("extracted", 0) or 0),
                already_ready=int(update.get("already_ready", 0) or 0),
                skipped=int(update.get("skipped", 0) or 0),
                errors=int(update.get("errors", 0) or 0),
                resumable=True,
            ),
        )
        _save_queue_payload(progress_payload, store_dir, refresh_manifest=not low_resource)
        if bucket_changed:
            get_logger().log(
                f"🧠 [LoRA 학습] 진행: {progress_label} "
                f"{processed}/{total} ({pct}%) · 새 {int(update.get('extracted', 0) or 0)} · "
                f"준비됨 {int(update.get('already_ready', 0) or 0)} · 건너뜀 {int(update.get('skipped', 0) or 0)} · "
                f"오류 {int(update.get('errors', 0) or 0)}"
            )

    try:
        if low_resource and job_type == "build_retrieval_index":
            outcome = {
                "status": "skipped",
                "score": None,
                "result": {"reason": LOW_RESOURCE_INDEX_DEFERRED_REASON},
            }
            get_logger().log("🧠 [LoRA 학습] 검색 인덱스/ZIP 갱신 생략: 저전력 자동에서는 수동/Full 학습 때 처리")
        else:
            outcome = run_training_job(
                target,
                store_dir=store_dir,
                progress_callback=save_progress,
                cancel_callback=cancel_callback,
            )
        cancelled_after_job = _cancel_requested(cancel_callback)
        if cancelled_after_job:
            outcome = _cancelled_training_result("paused_for_foreground_activity")
        payload = load_training_queue(store_dir)
        outcome_status = str(outcome.get("status") or "complete")
        outcome_reason = str((outcome.get("result") or {}).get("reason") or "")
        outcome_cancelled = bool((outcome.get("result") or {}).get("cancelled")) or cancelled_after_job
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
        _save_queue_payload(payload, store_dir, refresh_manifest=not low_resource)
        prune_result: dict[str, Any] = {}
        if outcome_status == "complete":
            appended_counts: dict[str, int] = {}
            result_payload = dict(outcome.get("result") or {})
            if job_type == "optimize_settings":
                appended_counts["setting_trials"] = int(result_payload.get("trial_count", 0) or 0)
            elif job_type == "optimize_prompts":
                appended_counts["prompt_trials"] = int(result_payload.get("trial_count", 0) or 0)
            if not low_resource:
                try:
                    prune_result = prune_low_value_personalization_data(
                        store_dir=store_dir,
                        trigger=f"training_job:{job_type}",
                        appended_counts=appended_counts,
                    )
                    outcome["retention"] = prune_result
                except Exception as prune_exc:
                    get_logger().log(f"⚠️ [개인화 학습] 낮은 점수 정리 실패: {prune_exc}")
            else:
                outcome["retention"] = {"skipped": True, "reason": "low_resource_idle"}
            try:
                if low_resource:
                    outcome["retrieval_index"] = {
                        "skipped": True,
                        "reason": LOW_RESOURCE_INDEX_DEFERRED_REASON,
                    }
                    get_logger().log("🧠 [LoRA 학습] 검색 인덱스 갱신 생략: 저전력 자동")
                elif _lora_index_refresh_due(store_dir):
                    get_logger().log("🧠 [LoRA 학습] 검색 인덱스 갱신 중")
                    retrieval_index = build_lora_retrieval_index(store_dir)
                    outcome["retrieval_index"] = {
                        "doc_count": int(retrieval_index.get("doc_count", 0) or 0),
                        "updated_at": retrieval_index.get("updated_at"),
                    }
                    get_logger().log(
                        f"🧠 [LoRA 학습] 검색 인덱스 갱신 완료: {int(retrieval_index.get('doc_count', 0) or 0)}개 기억"
                    )
                else:
                    outcome["retrieval_index"] = {"skipped": True, "reason": "low_resource_cooldown"}
                    get_logger().log("🧠 [LoRA 학습] 검색 인덱스 갱신 생략: 쿨다운")
            except Exception as index_exc:
                get_logger().log(f"⚠️ [개인화 학습] LoRA 검색 인덱스 갱신 실패: {index_exc}")
        if not outcome_cancelled:
            refresh_lora_personalization_manifest(store_dir, refresh_bundle=not low_resource)
        else:
            _cleanup_lora_training_runtime("training_cancelled", include_gpu=True)
            get_logger().log(f"⏸️ [LoRA 학습] 일시정지: {mode_label} · {_queue_job_type_label(job_type)}")
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
        _save_queue_payload(payload, store_dir, refresh_manifest=not low_resource)
        refresh_lora_personalization_manifest(store_dir, refresh_bundle=not low_resource)
        get_logger().log(f"⚠️ [개인화 학습] 실패: {job_type} / {exc}")
        return {"processed": True, "job_id": job_id, "outcome": {"status": "failed", "result": {"reason": str(exc)}}}


class PersonalizationIdleTrainer(QObject):
    _learning_status_signal = pyqtSignal()

    def __init__(self, owner, *, store_dir: str | Path | None = None):
        super().__init__(owner)
        self.owner = owner
        self.store_dir = str(store_dir) if store_dir else None
        self.idle_window_ms = LOW_RESOURCE_IDLE_WINDOW_MS
        self.cooldown_ms = LOW_RESOURCE_COOLDOWN_MS
        self.last_user_activity_ms = QDateTime.currentMSecsSinceEpoch()
        self._worker_thread: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._running_job_id = ""
        self._last_run_result: dict[str, Any] = {}
        self._last_job_finished_ms = 0
        self._suspended_until_ms = 0
        self._suspend_reason = ""
        self._last_auto_learning_status_log = ""
        self._current_learning_mode = ""
        self._current_low_resource = True
        self._last_stop_cleanup_at = 0.0
        self._learning_status_signal.connect(self._notify_learning_status_changed_on_main)
        recover_interrupted_training_jobs(self.store_dir, reason="trainer_startup")
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(LOW_RESOURCE_POLL_INTERVAL_MS)
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

    def _stop_pending_for_ui(self) -> bool:
        return bool(self._stop_requested.is_set() and str(self._suspend_reason or "").strip())

    def learning_status(self) -> dict[str, Any]:
        stop_pending = self._stop_pending_for_ui()
        busy = (self.is_busy() or bool(self._current_learning_mode)) and not stop_pending
        mode = str(self._current_learning_mode or ("lite" if self._current_low_resource else "heavy"))
        if not busy:
            mode = ""
        return {
            "active": busy,
            "mode": mode,
            "low_resource": bool(self._current_low_resource),
            "blink_interval_ms": 1000 if mode == "lite" else 100,
            "tooltip": (
                "Lite learning is running. Mouse or keyboard input stops learning."
                if mode == "lite"
                else (
                    "Heavy learning is running. Mouse or keyboard input stops learning."
                    if mode == "heavy"
                    else "Learning is idle."
                )
            ),
        }

    def last_run_result(self) -> dict[str, Any]:
        return dict(self._last_run_result or {})

    def _notify_learning_status_changed_on_main(self) -> None:
        refresher = getattr(self.owner, "_refresh_saved_status_label", None)
        if callable(refresher):
            try:
                refresher()
            except Exception:
                pass

    def _notify_learning_status_changed(self) -> None:
        self._learning_status_signal.emit()

    def _cleanup_after_stop(
        self,
        reason: str,
        *,
        include_gpu: bool = True,
        throttle_sec: float = 0.35,
    ) -> dict[str, Any]:
        now = time.monotonic()
        try:
            throttle = max(0.0, float(throttle_sec))
        except Exception:
            throttle = 0.35
        if throttle > 0.0 and (now - float(self._last_stop_cleanup_at or 0.0)) < throttle:
            return {"skipped": True, "reason": "cleanup_throttled"}
        self._last_stop_cleanup_at = now
        return _cleanup_lora_training_runtime(reason, include_gpu=include_gpu)

    def _log_auto_learning_status(self, context: str) -> None:
        summary = format_training_queue_status_summary(load_training_queue(self.store_dir))
        suffix = f" ({context})" if context else ""
        message = f"🧠 [개인화 학습] 자동 학습 상태: {summary}{suffix}"
        if message == self._last_auto_learning_status_log:
            return
        self._last_auto_learning_status_log = message
        get_logger().log(message)

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
        return self._learning_context() == "home"

    def _process_next_job_once(self, *, low_resource: bool = True) -> dict[str, Any]:
        result = run_training_queue_once(
            self.store_dir,
            cancel_callback=self._stop_requested.is_set,
            low_resource=low_resource,
        )
        self._last_run_result = dict(result or {})
        return result

    def run_pending_now(self, *, low_resource: bool = False) -> dict[str, Any]:
        if self.is_busy():
            return {"started": False, "reason": "busy"}
        self._stop_requested.clear()
        self._current_low_resource = bool(low_resource)
        self._current_learning_mode = "lite" if low_resource else "heavy"
        self._notify_learning_status_changed()
        try:
            result = self._process_next_job_once(low_resource=low_resource)
            return {"started": bool(result.get("processed")), "result": result}
        finally:
            self._current_learning_mode = ""
            self._cleanup_after_stop("manual_training_complete", include_gpu=True, throttle_sec=0.0)
            self._notify_learning_status_changed()

    def _background_run_once(self, *, low_resource: bool = True, continuous: bool = False) -> None:
        try:
            self._current_low_resource = bool(low_resource)
            self._current_learning_mode = "lite" if low_resource else "heavy"
            self._notify_learning_status_changed()
            while True:
                result = self._process_next_job_once(low_resource=low_resource)
                if not bool((result or {}).get("processed")):
                    break
                if not continuous or self._stop_requested.is_set() or not self.has_pending_jobs():
                    break
        finally:
            self._last_job_finished_ms = QDateTime.currentMSecsSinceEpoch()
            self._log_auto_learning_status("백그라운드 완료")
            self._current_learning_mode = ""
            self._cleanup_after_stop("background_training_complete", include_gpu=True, throttle_sec=0.0)
            self._notify_learning_status_changed()

    def start_background_run(self, *, low_resource: bool = True, continuous: bool = False) -> dict[str, Any]:
        with self._worker_lock:
            if self.is_busy():
                return {"started": False, "reason": "busy"}
            if not self.has_pending_jobs():
                return {"started": False, "reason": "no_pending_job"}
            self._log_auto_learning_status("백그라운드 시작")
            self._stop_requested.clear()
            self._worker_thread = threading.Thread(
                target=self._background_run_once,
                kwargs={"low_resource": low_resource, "continuous": continuous},
                daemon=True,
                name="personalization-idle-trainer",
            )
            self._worker_thread.start()
            self._notify_learning_status_changed()
            return {"started": True, "reason": "background", "continuous": bool(continuous)}

    def suspend_for_foreground_activity(
        self,
        *,
        reason: str = "foreground_activity",
        hold_ms: int | float | None = None,
    ) -> dict[str, Any]:
        now = QDateTime.currentMSecsSinceEpoch()
        try:
            hold = int(hold_ms if hold_ms is not None else self.idle_window_ms)
        except Exception:
            hold = int(self.idle_window_ms)
        was_busy = self.is_busy() or bool(self._current_learning_mode)
        self.note_user_activity()
        self._suspended_until_ms = max(int(self._suspended_until_ms or 0), now + max(0, hold))
        self._suspend_reason = str(reason or "foreground_activity")
        self._stop_requested.set()
        self._current_learning_mode = ""
        if was_busy:
            self._cleanup_after_stop(self._suspend_reason, include_gpu=True)
        self._notify_learning_status_changed()
        return {
            "suspended": True,
            "busy": self.is_busy(),
            "was_busy": was_busy,
            "until_ms": int(self._suspended_until_ms or 0),
            "reason": self._suspend_reason,
        }

    def request_immediate_stop(
        self,
        *,
        reason: str = "user_input_interrupt",
        hold_ms: int | float | None = 0,
        join_timeout_sec: float = 0.03,
    ) -> dict[str, Any]:
        result = self.suspend_for_foreground_activity(reason=reason, hold_ms=hold_ms)
        thread = self._worker_thread
        joined = False
        if thread is not None and thread.is_alive():
            try:
                thread.join(timeout=max(0.0, float(join_timeout_sec)))
            except (RuntimeError, TypeError, ValueError):
                pass
        if thread is not None and not thread.is_alive():
            joined = True
            recover_interrupted_training_jobs(self.store_dir, reason=reason)
            self._current_learning_mode = ""
            self._last_job_finished_ms = QDateTime.currentMSecsSinceEpoch()
            self._cleanup_after_stop(reason, include_gpu=True, throttle_sec=0.0)
            self._notify_learning_status_changed()
        elif bool(result.get("was_busy")):
            self._cleanup_after_stop(reason, include_gpu=True)
        return {
            **result,
            "stop_requested": True,
            "joined": joined,
        }

    def shutdown(self, *, timeout_sec: float = 3.0) -> dict[str, Any]:
        self._poll_timer.stop()
        self._stop_requested.set()
        self._suspend_reason = "shutdown"
        self._current_learning_mode = ""
        self._cleanup_after_stop("shutdown", include_gpu=True, throttle_sec=0.0)
        thread = self._worker_thread
        alive = bool(thread is not None and thread.is_alive())
        if alive:
            try:
                thread.join(timeout=max(0.0, float(timeout_sec)))
            except RuntimeError:
                pass
        still_alive = bool(thread is not None and thread.is_alive())
        if still_alive:
            self._current_learning_mode = ""
            self._last_job_finished_ms = QDateTime.currentMSecsSinceEpoch()
            self._notify_learning_status_changed()
            return {"stopped": False, "busy": True}
        recover_interrupted_training_jobs(self.store_dir, reason="shutdown")
        self._current_learning_mode = ""
        self._last_job_finished_ms = QDateTime.currentMSecsSinceEpoch()
        self._notify_learning_status_changed()
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
        now = QDateTime.currentMSecsSinceEpoch()
        if int(getattr(self.owner, "_lora_foreground_busy_until_ms", 0) or 0) > now:
            return True
        backend = getattr(self.owner, "backend", None)
        if backend is not None and bool(getattr(backend, "_active", False)):
            return True
        if getattr(self.owner, "_editor_widget", None) is not None and self._learning_context() != "home":
            return True
        if hasattr(self.owner, "_is_editor_actively_editing") and self.owner._is_editor_actively_editing():
            return True
        if bool(getattr(self.owner, "_auto_processing_active", False)):
            return True
        for manager_name in ("_cloud_sync_manager", "_nas_sync_manager"):
            manager = getattr(self.owner, manager_name, None)
            if manager is None:
                continue
            if bool(getattr(manager, "_in_flight", None)) or bool(getattr(manager, "_folder_jobs", None)):
                return True
        return False

    def _owner_idle(self) -> bool:
        now = QDateTime.currentMSecsSinceEpoch()
        if int(self._suspended_until_ms or 0) > now:
            return False
        if self._owner_busy():
            return False
        if not self._context_allows_auto_training():
            return False
        if int(self._last_job_finished_ms or 0) > 0 and (now - int(self._last_job_finished_ms or 0)) < int(self.cooldown_ms):
            return False
        return (now - int(self.last_user_activity_ms or 0)) >= int(self.idle_window_ms)

    def _auto_learning_low_resource(self) -> bool:
        now = QDateTime.currentMSecsSinceEpoch()
        idle_for = now - int(self.last_user_activity_ms or 0)
        return idle_for < int(self.idle_window_ms + LOW_RESOURCE_TO_HEAVY_IDLE_MS)

    def _poll(self) -> None:
        if self.is_busy():
            return
        if not self._owner_idle():
            return
        self.start_background_run(low_resource=self._auto_learning_low_resource())


__all__ = [
    "PersonalizationIdleTrainer",
    "enqueue_default_training_jobs",
    "enqueue_full_training_jobs",
    "format_training_queue_status_summary",
    "recover_interrupted_training_jobs",
    "run_training_job",
    "run_training_queue_once",
]
