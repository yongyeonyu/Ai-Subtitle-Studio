from __future__ import annotations

import importlib.util
import json
import hashlib
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.personalization.text_lora_dataset import (
    TEXT_LORA_CORPUS_MANIFEST_PATH,
    TEXT_LORA_CORPUS_PATH,
    TEXT_LORA_DATASET_DIR,
    VOICE_LORA_BRIDGE_PATH,
)


TEXT_LORA_TRAINING_PLAN_PATH = TEXT_LORA_DATASET_DIR / "text_lora_training_plan.json"
VOICE_LORA_PROFILE_MANIFEST_PATH = TEXT_LORA_DATASET_DIR / "voice_lora_profile_manifest.json"
VOICE_LORA_TRAINING_PLAN_PATH = TEXT_LORA_DATASET_DIR / "voice_lora_training_plan.json"
VOICE_LORA_DATASET_MANIFEST_PATH = TEXT_LORA_DATASET_DIR / "voice_lora_dataset_manifest.json"
VOICE_LORA_CLIPS_DIR = TEXT_LORA_DATASET_DIR / "trained_adapters" / "personal_voice_lora" / "clips"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_slug(value: Any, fallback: str = "unknown") -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(value or "").strip())
    text = "_".join(part for part in text.split("_") if part)
    return text[:64] or fallback


def _voice_row_times(row: dict[str, Any]) -> tuple[float, float, float]:
    start = row.get("start_sec")
    end = row.get("end_sec")
    duration = row.get("duration_sec")
    try:
        start_sec = float(start)
    except Exception:
        fps = float(row.get("fps", 30.0) or 30.0)
        start_sec = float(row.get("start_frame", 0) or 0) / max(1.0, fps)
    try:
        end_sec = float(end)
    except Exception:
        fps = float(row.get("fps", 30.0) or 30.0)
        end_sec = float(row.get("end_frame", 0) or 0) / max(1.0, fps)
    try:
        duration_sec = float(duration)
    except Exception:
        duration_sec = max(0.0, end_sec - start_sec)
    if duration_sec <= 0:
        duration_sec = max(0.0, end_sec - start_sec)
    end_sec = max(end_sec, start_sec + duration_sec)
    return round(start_sec, 3), round(end_sec, 3), round(duration_sec, 3)


def _voice_lora_signature(row: dict[str, Any]) -> str:
    start_sec, end_sec, _duration_sec = _voice_row_times(row)
    return _stable_hash(
        {
            "clip_path": str(row.get("clip_path") or ""),
            "speaker": str(row.get("speaker") or "unknown"),
            "start_sec": start_sec,
            "end_sec": end_sec,
            "text": str(row.get("text") or "").strip(),
        }
    )[:24]


def _voice_clip_command(
    *,
    source_path: str,
    output_path: str,
    start_sec: float,
    duration_sec: float,
    sample_rate: int,
) -> list[str]:
    return [
        ffmpeg_binary(),
        "-y",
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        f"{float(start_sec):.3f}",
        "-i",
        source_path,
        "-t",
        f"{float(duration_sec):.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(int(sample_rate)),
        "-acodec",
        "pcm_s16le",
        output_path,
    ]


def _item_audio_path(item: dict[str, Any]) -> Path | None:
    raw = str(item.get("audio_path") or "").strip()
    return Path(raw) if raw else None


def _refresh_voice_lora_audio_readiness(plan: dict[str, Any]) -> dict[str, Any]:
    items = list(plan.get("items") or [])
    by_speaker: dict[str, dict[str, float | int]] = defaultdict(lambda: {"items": 0, "sec": 0.0})
    stored_audio_items = 0
    stored_audio_sec = 0.0
    for item in items:
        audio_path = _item_audio_path(item)
        audio_ready = bool(audio_path is not None and audio_path.exists())
        item["audio_ready"] = audio_ready
        item["audio_exists"] = audio_ready
        speaker = str(item.get("speaker") or "unknown")
        duration_sec = float(item.get("duration_sec", 0.0) or 0.0)
        if audio_ready:
            stored_audio_items += 1
            stored_audio_sec += duration_sec
            by_speaker[speaker]["items"] = int(by_speaker[speaker]["items"]) + 1
            by_speaker[speaker]["sec"] = float(by_speaker[speaker]["sec"]) + duration_sec

    stats = dict(plan.get("stats") or {})
    thresholds = dict(plan.get("thresholds") or {})
    min_ready_segments = int(thresholds.get("min_ready_segments", 20) or 20)
    min_ready_total_sec = float(thresholds.get("min_ready_total_sec", 80.0) or 80.0)
    speaker_profiles = []
    for profile in list(stats.get("speaker_profiles") or []):
        profile = dict(profile or {})
        speaker = str(profile.get("speaker") or "unknown")
        audio_stats = by_speaker.get(speaker, {"items": 0, "sec": 0.0})
        audio_items = int(audio_stats.get("items", 0) or 0)
        audio_sec = float(audio_stats.get("sec", 0.0) or 0.0)
        profile["stored_audio_items"] = audio_items
        profile["stored_audio_sec"] = round(audio_sec, 3)
        profile["audio_dataset_ready_for_voice_lora"] = bool(
            audio_items >= min_ready_segments and audio_sec >= min_ready_total_sec
        )
        speaker_profiles.append(profile)

    stats["speaker_profiles"] = speaker_profiles
    stats["stored_audio_items"] = stored_audio_items
    stats["missing_audio_items"] = max(0, len(items) - stored_audio_items)
    stats["stored_audio_sec"] = round(stored_audio_sec, 3)
    stats["audio_dataset_ready_speakers"] = sum(
        1 for profile in speaker_profiles if bool(profile.get("audio_dataset_ready_for_voice_lora"))
    )
    plan["stats"] = stats
    return stats


def build_text_lora_training_plan(
    *,
    corpus_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    base_model: str = "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit",
    adapter_name: str = "personal_text_lora",
    epochs: int = 3,
    learning_rate: float = 1e-4,
    lora_rank: int = 8,
    micro_batch_size: int = 1,
) -> dict[str, Any]:
    corpus_target = Path(corpus_path) if corpus_path else TEXT_LORA_CORPUS_PATH
    out_dir = Path(output_dir) if output_dir else (TEXT_LORA_DATASET_DIR / "trained_adapters" / adapter_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_jsonl(corpus_target)
    usable_rows = [row for row in rows if str(row.get("task", "") or "") == "text_correction"]
    sources = defaultdict(int)
    speakers = defaultdict(int)
    for row in usable_rows:
        sources[str(row.get("source", "") or "unknown")] += 1
        meta = row.get("meta", {}) if isinstance(row.get("meta"), dict) else {}
        speaker = str(meta.get("speaker", "") or "")
        if speaker:
            speakers[speaker] += 1

    backend = "mlx_lm_lora" if _module_exists("mlx_lm") else "unavailable"
    command = []
    if backend == "mlx_lm_lora":
        command = [
            "python3",
            "-m",
            "mlx_lm.lora",
            "--model",
            base_model,
            "--train",
            "--data",
            str(corpus_target),
            "--iters",
            str(max(100, len(usable_rows) * max(1, int(epochs)))),
            "--learning-rate",
            str(learning_rate),
            "--batch-size",
            str(max(1, int(micro_batch_size))),
            "--lora-layers",
            str(max(4, int(lora_rank))),
            "--adapter-path",
            str(out_dir),
        ]

    plan = {
        "schema": "ai_subtitle_studio.text_lora_training_plan.v1",
        "created_at": _now(),
        "platform": "mac",
        "backend": backend,
        "base_model": base_model,
        "adapter_name": adapter_name,
        "output_dir": str(out_dir),
        "corpus_path": str(corpus_target),
        "corpus_manifest_path": str(TEXT_LORA_CORPUS_MANIFEST_PATH),
        "stats": {
            "total_rows": len(rows),
            "usable_text_rows": len(usable_rows),
            "source_breakdown": dict(sorted(sources.items())),
            "speaker_breakdown": dict(sorted(speakers.items())),
            "pattern_first_storage": True,
        },
        "hyperparams": {
            "epochs": int(epochs),
            "learning_rate": float(learning_rate),
            "lora_rank": int(lora_rank),
            "micro_batch_size": int(micro_batch_size),
        },
        "command": command,
        "training_objective": {
            "task": "subtitle_qa_correction",
            "input": "STT 후보 또는 교정 전 자막",
            "output": "검수 완료 최종 자막",
            "rules": [
                "원문 발화의 단어, 순서, 의미, 구어체를 보존한다",
                "띄어쓰기, 명백한 오탈자, 최소 문장부호만 교정한다",
                "없는 말, 설명, 요약, 문어체 변환을 학습하지 않는다",
                "고유명사, 숫자, 영어 표기는 확실하지 않으면 원문을 유지한다",
                "wrong_answer_memory 문구는 STT 환각/오답으로 보고 사용을 피한다",
            ],
        },
        "notes": [
            "mac first subtitle QA text LoRA training scaffold",
            "uses accumulated STT candidate -> final subtitle corpus",
            "preserves spoken style while learning conservative subtitle review corrections",
            "runtime personalization now prefers compact subtitle pattern indexes before text LoRA",
        ],
    }
    return plan


def save_text_lora_training_plan(*, plan_path: str | Path | None = None, **kwargs) -> dict[str, Any]:
    plan = build_text_lora_training_plan(**kwargs)
    target = Path(plan_path) if plan_path else TEXT_LORA_TRAINING_PLAN_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "plan_path": str(target),
        "backend": str(plan.get("backend", "") or ""),
        "usable_rows": int(((plan.get("stats") or {}).get("usable_text_rows", 0)) or 0),
        "output_dir": str(plan.get("output_dir", "") or ""),
    }


def build_voice_lora_profile_manifest(
    *,
    bridge_path: str | Path | None = None,
) -> dict[str, Any]:
    bridge_target = Path(bridge_path) if bridge_path else VOICE_LORA_BRIDGE_PATH
    rows = _read_jsonl(bridge_target)
    by_speaker: dict[str, dict[str, Any]] = {}
    for row in rows:
        speaker = str(row.get("speaker", "") or "unknown")
        _start_sec, _end_sec, duration_sec = _voice_row_times(row)
        item = by_speaker.setdefault(
            speaker,
            {
                "speaker": speaker,
                "segments": 0,
                "total_frames": 0,
                "total_sec": 0.0,
                "clips": set(),
                "projects": set(),
                "texts": 0,
            },
        )
        item["segments"] += 1
        item["total_frames"] += int(row.get("duration_frames", 0) or 0)
        item["total_sec"] += float(duration_sec)
        clip_path = str(row.get("clip_path", "") or "")
        project_path = str(row.get("project_path", "") or "")
        if clip_path:
            item["clips"].add(clip_path)
        if project_path:
            item["projects"].add(project_path)
        if str(row.get("text", "") or "").strip():
            item["texts"] += 1

    speakers = []
    for speaker, item in sorted(by_speaker.items()):
        speakers.append(
            {
                "speaker": speaker,
                "segments": int(item["segments"]),
                "total_frames": int(item["total_frames"]),
                "total_sec": round(float(item["total_sec"]), 3),
                "clip_count": len(item["clips"]),
                "project_count": len(item["projects"]),
                "text_count": int(item["texts"]),
                "ready_for_voice_lora": bool(item["segments"] >= 20 and float(item["total_sec"]) >= 80.0),
            }
        )

    manifest = {
        "schema": "ai_subtitle_studio.voice_lora_profile_manifest.v1",
        "created_at": _now(),
        "bridge_path": str(bridge_target),
        "training_plan_path": str(VOICE_LORA_TRAINING_PLAN_PATH),
        "speaker_profiles": speakers,
        "notes": [
            "frame/speaker based voice lora bridge summary",
            "used to decide when enough per-speaker data exists",
            "voice LoRA uses audio clips + transcript pairs and is separate from text correction LoRA",
        ],
    }
    return manifest


def build_voice_lora_training_plan(
    *,
    bridge_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    adapter_name: str = "personal_voice_lora",
    base_model: str = "voice-clone-compatible-base",
    sample_rate: int = 24000,
    min_segment_sec: float = 0.8,
    max_segment_sec: float = 12.0,
    min_ready_segments: int = 20,
    min_ready_total_sec: float = 80.0,
) -> dict[str, Any]:
    bridge_target = Path(bridge_path) if bridge_path else VOICE_LORA_BRIDGE_PATH
    out_dir = Path(output_dir) if output_dir else (TEXT_LORA_DATASET_DIR / "trained_adapters" / adapter_name)
    clips_dir = out_dir / "clips"
    rows = _read_jsonl(bridge_target)
    items: list[dict[str, Any]] = []
    skipped = defaultdict(int)
    speaker_stats: dict[str, dict[str, Any]] = {}

    for row in rows:
        text = str(row.get("text") or "").strip()
        clip_path = str(row.get("clip_path") or "").strip()
        speaker = str(row.get("speaker") or "unknown").strip() or "unknown"
        start_sec, end_sec, duration_sec = _voice_row_times(row)
        if not text:
            skipped["missing_text"] += 1
            continue
        if not clip_path:
            skipped["missing_clip_path"] += 1
            continue
        if duration_sec < float(min_segment_sec):
            skipped["too_short"] += 1
            continue
        if duration_sec > float(max_segment_sec):
            skipped["too_long"] += 1
            continue

        signature = _voice_lora_signature(row)
        speaker_slug = _safe_slug(speaker)
        audio_path = clips_dir / speaker_slug / f"{signature}.wav"
        audio_exists = audio_path.exists()
        command = _voice_clip_command(
            source_path=clip_path,
            output_path=str(audio_path),
            start_sec=start_sec,
            duration_sec=duration_sec,
            sample_rate=sample_rate,
        )
        source_exists = Path(clip_path).exists()
        item = {
            "schema": "ai_subtitle_studio.voice_lora_training_item.v1",
            "signature": signature,
            "speaker": speaker,
            "speaker_slug": speaker_slug,
            "text": text,
            "source_media_path": clip_path,
            "source_exists": source_exists,
            "audio_path": str(audio_path),
            "audio_exists": audio_exists,
            "audio_ready": audio_exists,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "duration_sec": duration_sec,
            "fps": float(row.get("fps", 30.0) or 30.0),
            "start_frame": int(row.get("start_frame", 0) or 0),
            "end_frame": int(row.get("end_frame", 0) or 0),
            "project_path": str(row.get("project_path") or ""),
            "extraction_command": command,
        }
        items.append(item)
        stats = speaker_stats.setdefault(
            speaker,
            {
                "speaker": speaker,
                "items": 0,
                "source_existing_items": 0,
                "total_sec": 0.0,
                "clip_count": set(),
            },
        )
        stats["items"] += 1
        stats["source_existing_items"] += 1 if source_exists else 0
        stats["total_sec"] += duration_sec
        stats["clip_count"].add(clip_path)

    speaker_profiles: list[dict[str, Any]] = []
    for speaker, stats in sorted(speaker_stats.items()):
        total_sec = float(stats["total_sec"])
        item_count = int(stats["items"])
        existing_count = int(stats["source_existing_items"])
        speaker_profiles.append(
            {
                "speaker": speaker,
                "items": item_count,
                "source_existing_items": existing_count,
                "total_sec": round(total_sec, 3),
                "clip_count": len(stats["clip_count"]),
                "ready_for_voice_lora": bool(item_count >= int(min_ready_segments) and total_sec >= float(min_ready_total_sec)),
            }
        )

    backend_candidates = []
    if _module_exists("TTS"):
        backend_candidates.append("coqui_xtts_dataset_ready")
    if _module_exists("torch"):
        backend_candidates.append("torch_voice_finetune_possible")
    backend = backend_candidates[0] if backend_candidates else "dataset_plan_only"
    plan = {
        "schema": "ai_subtitle_studio.voice_lora_training_plan.v1",
        "created_at": _now(),
        "backend": backend,
        "base_model": base_model,
        "adapter_name": adapter_name,
        "bridge_path": str(bridge_target),
        "output_dir": str(out_dir),
        "clips_dir": str(clips_dir),
        "sample_rate": int(sample_rate),
        "thresholds": {
            "min_segment_sec": float(min_segment_sec),
            "max_segment_sec": float(max_segment_sec),
            "min_ready_segments": int(min_ready_segments),
            "min_ready_total_sec": float(min_ready_total_sec),
        },
        "stats": {
            "bridge_rows": len(rows),
            "usable_voice_items": len(items),
            "skipped": dict(sorted(skipped.items())),
            "speaker_profiles": speaker_profiles,
        },
        "items": items,
        "training_objective": {
            "task": "voice_identity_conditioning",
            "input": "speaker audio clip + transcript text",
            "output": "speaker-conditioned voice adapter dataset",
            "rules": [
                "학습에는 본인 또는 사용 허가를 받은 화자의 음성만 사용한다",
                "자막 텍스트와 실제 발화가 맞는 짧은 구간을 우선 사용한다",
                "배경음/겹침 발화/침묵 구간은 낮은 품질 데이터로 본다",
                "텍스트 LoRA와 음성 LoRA는 별도 adapter로 관리한다",
            ],
        },
        "notes": [
            "This plan prepares voice LoRA / voice-clone fine-tuning data from video segments.",
            "ffmpeg extraction commands are stored per item and saved WAV clips become the training dataset.",
            "Actual voice LoRA backend depends on the installed voice model toolkit.",
        ],
    }
    _refresh_voice_lora_audio_readiness(plan)
    return plan


def _extract_voice_lora_clips(
    items: list[dict[str, Any]],
    *,
    timeout_sec: float = 30.0,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    extracted = 0
    already_ready = 0
    skipped = 0
    cancelled = False
    errors: list[dict[str, Any]] = []
    total = len(items)

    def emit_progress(processed: int) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(
                {
                    "processed": int(processed),
                    "total": int(total),
                    "extracted": int(extracted),
                    "already_ready": int(already_ready),
                    "skipped": int(skipped),
                    "errors": int(len(errors)),
                    "cancelled": bool(cancelled),
                }
            )
        except Exception:
            return

    for index, item in enumerate(items, start=1):
        try:
            if cancel_callback is not None and bool(cancel_callback()):
                cancelled = True
                break
            output_path = _item_audio_path(item)
            if output_path is not None and output_path.exists():
                item["audio_ready"] = True
                item["audio_exists"] = True
                item["audio_status"] = "already_ready"
                already_ready += 1
                continue
            if not bool(item.get("source_exists")):
                item["audio_ready"] = False
                item["audio_status"] = "missing_source_media"
                skipped += 1
                continue
            command = list(item.get("extraction_command") or [])
            if not command or not output_path:
                item["audio_ready"] = False
                item["audio_status"] = "missing_extraction_command"
                skipped += 1
                continue
            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=max(1.0, float(timeout_sec)),
                    **hidden_subprocess_kwargs(),
                )
            except Exception as exc:
                item["audio_ready"] = False
                item["audio_status"] = "error"
                item["extraction_error"] = str(exc)
                errors.append({"audio_path": str(output_path), "error": str(exc)})
                continue
            if completed.returncode == 0 and output_path.exists():
                item["audio_ready"] = True
                item["audio_exists"] = True
                item["audio_status"] = "extracted"
                item["audio_extracted"] = True
                extracted += 1
            else:
                item["audio_ready"] = False
                item["audio_status"] = "failed"
                errors.append(
                    {
                        "audio_path": str(output_path),
                        "returncode": completed.returncode,
                        "stderr": (completed.stderr or "")[-500:],
                    }
                )
        finally:
            if index == total or index % 25 == 0:
                emit_progress(index)
    return {"extracted": extracted, "already_ready": already_ready, "skipped": skipped, "errors": errors, "cancelled": cancelled}


def save_voice_lora_training_plan(
    *,
    plan_path: str | Path | None = None,
    dataset_manifest_path: str | Path | None = None,
    extract_audio: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
    **kwargs,
) -> dict[str, Any]:
    plan = build_voice_lora_training_plan(**kwargs)
    target = Path(plan_path) if plan_path else VOICE_LORA_TRAINING_PLAN_PATH
    manifest_target = Path(dataset_manifest_path) if dataset_manifest_path else VOICE_LORA_DATASET_MANIFEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest_target.parent.mkdir(parents=True, exist_ok=True)
    extraction_result = {"extracted": 0, "already_ready": 0, "skipped": 0, "errors": []}
    if extract_audio:
        extraction_result = _extract_voice_lora_clips(
            list(plan.get("items") or []),
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
        )
        plan["last_extraction"] = {"created_at": _now(), **extraction_result}
    _refresh_voice_lora_audio_readiness(plan)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_stats = dict(plan.get("stats") or {})
    dataset_manifest = {
        "schema": "ai_subtitle_studio.voice_lora_dataset_manifest.v1",
        "created_at": _now(),
        "plan_path": str(target),
        "bridge_path": str(plan.get("bridge_path") or ""),
        "clips_dir": str(plan.get("clips_dir") or ""),
        "stats": plan_stats,
        "speaker_profiles": list(plan_stats.get("speaker_profiles") or []),
        "extraction": extraction_result,
        "notes": [
            "voice LoRA dataset manifest generated from video segment bridge",
            "contains transcript-aligned saved WAV clips for speaker voice adaptation",
        ],
    }
    manifest_target.write_text(json.dumps(dataset_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "plan_path": str(target),
        "dataset_manifest_path": str(manifest_target),
        "backend": str(plan.get("backend") or ""),
        "usable_voice_rows": int(plan_stats.get("usable_voice_items", 0) or 0),
        "speaker_profiles": int(len(list(plan_stats.get("speaker_profiles") or []))),
        "extracted_clips": int(extraction_result.get("extracted", 0) or 0),
        "already_ready_clips": int(extraction_result.get("already_ready", 0) or 0),
        "extraction_skipped": int(extraction_result.get("skipped", 0) or 0),
        "stored_audio_items": int(plan_stats.get("stored_audio_items", 0) or 0),
        "audio_dataset_ready_speakers": int(plan_stats.get("audio_dataset_ready_speakers", 0) or 0),
        "extraction_errors": int(len(list(extraction_result.get("errors") or []))),
        "cancelled": bool(extraction_result.get("cancelled")),
        "output_dir": str(plan.get("output_dir") or ""),
    }


def save_voice_lora_profile_manifest(*, manifest_path: str | Path | None = None, **kwargs) -> dict[str, Any]:
    manifest = build_voice_lora_profile_manifest(**kwargs)
    target = Path(manifest_path) if manifest_path else VOICE_LORA_PROFILE_MANIFEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "manifest_path": str(target),
        "speaker_profiles": int(len(list(manifest.get("speaker_profiles") or []))),
    }


__all__ = [
    "TEXT_LORA_TRAINING_PLAN_PATH",
    "VOICE_LORA_DATASET_MANIFEST_PATH",
    "VOICE_LORA_CLIPS_DIR",
    "VOICE_LORA_PROFILE_MANIFEST_PATH",
    "VOICE_LORA_TRAINING_PLAN_PATH",
    "build_text_lora_training_plan",
    "save_text_lora_training_plan",
    "build_voice_lora_profile_manifest",
    "build_voice_lora_training_plan",
    "save_voice_lora_profile_manifest",
    "save_voice_lora_training_plan",
]
