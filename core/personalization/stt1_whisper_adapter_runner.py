from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.personalization.lora_models import iso_now, stable_hash
from core.personalization.lora_retrieval_utils import classification_summary
from core.personalization.lora_store_common import (
    STT1_WHISPER_ADAPTER_DATASET_MANIFEST_PATH,
    STT1_WHISPER_ADAPTER_DATASET_PATH,
    STT1_WHISPER_ADAPTER_RUNTIME_MANIFEST_PATH,
    STT1_WHISPER_ADAPTER_TRAINING_PLAN_PATH,
    store_paths,
    write_json,
    write_jsonl,
)
from core.personalization.lora_rule_learning import load_truth_table_rows
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime.multi_process import runtime_parallel_worker_plan


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
        with target.open("r", encoding="utf-8") as handle:
            for line in handle:
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_slug(value: Any, fallback: str = "unknown") -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(value or "").strip())
    text = "_".join(part for part in text.split("_") if part)
    return text[:80] or fallback


def _normalize_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def _path_key(value: Any) -> str:
    return _normalize_path(value).casefold()


def _clip_audio_command(
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


def _voice_bridge_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in list(rows or []):
        media_id = str(row.get("media_id") or "").strip()
        clip_path = str(row.get("clip_path") or row.get("media_path") or "").strip()
        if media_id:
            grouped[f"media_id:{media_id}"].append(dict(row))
        if clip_path:
            grouped[f"clip_path:{_path_key(clip_path)}"].append(dict(row))
    return dict(grouped)


def _multimodal_context_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in list(rows or []):
        media_id = str(row.get("media_id") or "").strip()
        media_path = str(row.get("media_path") or row.get("clip_path") or "").strip()
        if media_id:
            grouped[f"media_id:{media_id}"].append(dict(row))
        if media_path:
            grouped[f"media_path:{_path_key(media_path)}"].append(dict(row))
    return dict(grouped)


def _voice_match_score(truth_row: dict[str, Any], voice_row: dict[str, Any]) -> tuple[float, float]:
    target_segment = str(truth_row.get("segment_id") or "").strip()
    candidate_segment = str(voice_row.get("segment_id") or "").strip()
    start_sec = _safe_float(truth_row.get("start_sec"), 0.0)
    end_sec = _safe_float(truth_row.get("end_sec"), start_sec)
    candidate_start = _safe_float(voice_row.get("start_sec"), 0.0)
    candidate_end = _safe_float(voice_row.get("end_sec"), candidate_start)
    overlap = max(0.0, min(end_sec, candidate_end) - max(start_sec, candidate_start))
    union = max(end_sec, candidate_end) - min(start_sec, candidate_start)
    overlap_ratio = (overlap / union) if union > 0 else 0.0
    delta = abs(start_sec - candidate_start) + abs(end_sec - candidate_end)
    score = (1000.0 if target_segment and target_segment == candidate_segment else 0.0) + (overlap_ratio * 100.0) - delta
    return score, overlap_ratio


def _match_voice_row(truth_row: dict[str, Any], voice_index: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    media_id = str(truth_row.get("media_id") or "").strip()
    media_path = str(truth_row.get("media_path") or "").strip()
    candidates = [
        *list(voice_index.get(f"media_id:{media_id}", [])),
        *list(voice_index.get(f"clip_path:{_path_key(media_path)}", [])),
    ]
    if not candidates:
        return {}
    best: dict[str, Any] = {}
    best_score = float("-inf")
    best_overlap = -1.0
    seen: set[str] = set()
    for row in candidates:
        signature = str(row.get("dedupe_hash") or row.get("signature") or stable_hash(row))
        if signature in seen:
            continue
        seen.add(signature)
        score, overlap_ratio = _voice_match_score(truth_row, row)
        if score > best_score or (score == best_score and overlap_ratio > best_overlap):
            best = dict(row)
            best_score = score
            best_overlap = overlap_ratio
    return best if best_overlap >= 0.35 or best_score >= 999.0 else {}


def _match_context_row(truth_row: dict[str, Any], context_index: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    media_id = str(truth_row.get("media_id") or "").strip()
    media_path = str(truth_row.get("media_path") or "").strip()
    candidates = list(context_index.get(f"media_id:{media_id}", [])) or list(context_index.get(f"media_path:{_path_key(media_path)}", []))
    if not candidates:
        return {}
    return dict(sorted(candidates, key=lambda item: str(item.get("created_at") or item.get("updated_at") or ""), reverse=True)[0])


def _candidate_context_summary(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "selected_source": str(data.get("selected_source") or ""),
        "candidate_count": _safe_int(data.get("candidate_count"), 0),
        "candidate_disagreement_ratio": round(_safe_float(data.get("candidate_disagreement_ratio"), 0.0), 4),
    }


def _training_tags(summary: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("scene", "topic", "mic_type", "noise_level"):
        value = str(summary.get(key) or "").strip()
        if value:
            tags.append(f"{key}:{value}")
    for key in ("noise_sources", "training_focus"):
        for value in list(summary.get(key) or []):
            text = str(value or "").strip()
            if text:
                tags.append(f"{key}:{text}")
    seen: set[str] = set()
    deduped: list[str] = []
    for item in tags:
        marker = item.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped[:20]


def _train_weight(
    *,
    transcript: str,
    duration_sec: float,
    source_exists: bool,
    candidate_summary: dict[str, Any],
    context_summary: dict[str, Any],
    excluded_text: str = "",
) -> float:
    score = 0.72
    char_count = len(transcript.replace("\n", "").strip())
    if 4 <= char_count <= 42:
        score += 0.08
    if 1.0 <= duration_sec <= 9.5:
        score += 0.1
    if source_exists:
        score += 0.08
    if excluded_text:
        score += 0.04
    if str(context_summary.get("noise_level") or "") == "high":
        score += 0.04
    if str(context_summary.get("scene") or "") in {"car", "outdoor"}:
        score += 0.03
    if _safe_int(candidate_summary.get("candidate_count"), 0) >= 2:
        score += 0.03
    if _safe_float(candidate_summary.get("candidate_disagreement_ratio"), 0.0) >= 0.12:
        score += 0.04
    return round(max(0.45, min(1.25, score)), 4)


def _runtime_artifact_status(path: Path, *, required_all: tuple[str, ...] = (), required_any: tuple[str, ...] = ()) -> dict[str, Any]:
    exists = path.exists()
    ready = exists
    if exists and required_all:
        ready = all((path / name).exists() for name in required_all)
    if ready and required_any:
        ready = any((path / name).exists() for name in required_any)
    return {
        "path": str(path),
        "exists": bool(exists),
        "ready": bool(ready),
        "required_all": list(required_all),
        "required_any": list(required_any),
    }


def build_stt1_whisper_adapter_training_plan(
    *,
    truth_table_path: str | Path,
    voice_bridge_path: str | Path,
    multimodal_context_path: str | Path,
    output_dir: str | Path,
    dataset_path: str | Path,
    dataset_manifest_path: str | Path,
    runtime_manifest_path: str | Path,
    adapter_name: str = "personal_stt1_whisper_adapter",
    base_model: str = "openai/whisper-large-v3",
    sample_rate: int = 16000,
    min_segment_sec: float = 0.6,
    max_segment_sec: float = 15.0,
    min_transcript_chars: int = 2,
    min_runtime_rows: int = 24,
    min_runtime_audio_items: int = 12,
    min_runtime_retrieval_score: float = 28.0,
    epochs: int = 3,
    learning_rate: float = 1e-4,
    lora_rank: int = 16,
    batch_size: int = 4,
    gradient_accumulation_steps: int = 4,
) -> dict[str, Any]:
    truth_rows = load_truth_table_rows(Path(truth_table_path).parent)
    voice_rows = _read_jsonl(voice_bridge_path)
    context_rows = _read_jsonl(multimodal_context_path)
    voice_index = _voice_bridge_index(voice_rows)
    context_index = _multimodal_context_index(context_rows)

    out_dir = Path(output_dir)
    clips_dir = out_dir / "clips"
    adapter_dir = out_dir / "adapter"
    merged_transformers_dir = out_dir / "merged_transformers"
    ctranslate2_dir = out_dir / "ctranslate2"
    items: list[dict[str, Any]] = []
    skipped = Counter()
    facet_counts: dict[str, Counter[str]] = {
        "scene": Counter(),
        "topic": Counter(),
        "mic_type": Counter(),
        "noise_level": Counter(),
    }
    list_facet_counts: dict[str, Counter[str]] = {
        "noise_sources": Counter(),
        "training_focus": Counter(),
    }

    for truth_row in list(truth_rows or []):
        transcript = str(truth_row.get("speech_training_text") or "").strip()
        if len(transcript.replace("\n", "")) < int(min_transcript_chars):
            skipped["short_transcript"] += 1
            continue
        start_sec = _safe_float(truth_row.get("start_sec"), 0.0)
        end_sec = _safe_float(truth_row.get("end_sec"), start_sec)
        duration_sec = max(0.0, _safe_float(truth_row.get("duration_sec"), end_sec - start_sec))
        if duration_sec < float(min_segment_sec):
            skipped["too_short"] += 1
            continue
        if duration_sec > float(max_segment_sec):
            skipped["too_long"] += 1
            continue

        voice_match = _match_voice_row(truth_row, voice_index)
        context_match = dict(voice_match.get("context_classification") or {}) and voice_match or _match_context_row(truth_row, context_index)
        context_classification = dict(context_match.get("context_classification") or {})
        context_summary = classification_summary(context_classification)
        candidate_payload = dict(voice_match.get("candidate_context") or {})
        candidate_summary = _candidate_context_summary(candidate_payload)
        source_media_path = str(voice_match.get("clip_path") or truth_row.get("media_path") or "").strip()
        if not source_media_path:
            skipped["missing_source_media_path"] += 1
            continue
        media_slug = _safe_slug(Path(source_media_path).stem or truth_row.get("media_id") or "media", fallback="media")
        signature = stable_hash(
            {
                "media_id": truth_row.get("media_id"),
                "segment_id": truth_row.get("segment_id"),
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
                "transcript": transcript,
            }
        )[:24]
        audio_path = clips_dir / media_slug / f"{signature}.wav"
        source_exists = Path(source_media_path).exists()
        speaker = str(
            voice_match.get("speaker")
            or truth_row.get("speaker_or_voice_hint")
            or context_match.get("speaker")
            or "unknown"
        ).strip() or "unknown"
        extraction_command = _clip_audio_command(
            source_path=source_media_path,
            output_path=str(audio_path),
            start_sec=start_sec,
            duration_sec=duration_sec,
            sample_rate=sample_rate,
        )
        tags = _training_tags(context_summary)
        item = {
            "schema": "ai_subtitle_studio.stt1_whisper_adapter_training_item.v1",
            "signature": signature,
            "media_id": str(truth_row.get("media_id") or ""),
            "media_path": str(truth_row.get("media_path") or ""),
            "subtitle_path": str(truth_row.get("subtitle_path") or ""),
            "segment_id": str(truth_row.get("segment_id") or ""),
            "source_media_path": source_media_path,
            "source_exists": source_exists,
            "audio_path": str(audio_path),
            "audio_exists": audio_path.exists(),
            "audio_ready": audio_path.exists(),
            "start_sec": round(start_sec, 3),
            "end_sec": round(end_sec, 3),
            "duration_sec": round(duration_sec, 3),
            "transcript_text": transcript,
            "weak_input_text": str(voice_match.get("input_text") or voice_match.get("text") or "").strip(),
            "selected_source": str(
                voice_match.get("selected_source")
                or candidate_payload.get("selected_source")
                or "ground_truth_srt"
            ).strip(),
            "speaker": speaker,
            "fps": round(_safe_float(voice_match.get("fps") or truth_row.get("media_fps"), 30.0), 3),
            "start_frame": _safe_int(voice_match.get("start_frame"), int(round(start_sec * max(1.0, _safe_float(voice_match.get("fps"), 30.0))))),
            "end_frame": _safe_int(voice_match.get("end_frame"), int(round(end_sec * max(1.0, _safe_float(voice_match.get("fps"), 30.0))))),
            "line_break_pattern": str(truth_row.get("line_break_pattern") or ""),
            "punctuation_pattern": str(truth_row.get("punctuation_pattern") or ""),
            "excluded_parenthetical_text": str(truth_row.get("excluded_parenthetical_text") or ""),
            "cps": round(_safe_float(truth_row.get("cps"), 0.0), 3),
            "char_count": _safe_int(truth_row.get("char_count"), len(transcript.replace("\n", ""))),
            "candidate_context_summary": candidate_summary,
            "candidate_context": candidate_payload,
            "context_classification": context_classification,
            "classification_summary": context_summary,
            "training_tags": tags,
            "train_weight": _train_weight(
                transcript=transcript,
                duration_sec=duration_sec,
                source_exists=source_exists,
                candidate_summary=candidate_summary,
                context_summary=context_summary,
                excluded_text=str(truth_row.get("excluded_parenthetical_text") or ""),
            ),
            "extraction_command": extraction_command,
        }
        items.append(item)
        for facet_key in facet_counts:
            value = str(context_summary.get(facet_key) or "").strip()
            if value:
                facet_counts[facet_key][value] += 1
        for facet_key in list_facet_counts:
            for value in list(context_summary.get(facet_key) or []):
                text = str(value or "").strip()
                if text:
                    list_facet_counts[facet_key][text] += 1

    backend = "dataset_plan_only"
    if all(_module_exists(name) for name in ("torch", "transformers", "peft", "datasets")):
        backend = "transformers_peft_whisper_lora"

    usable_rows = len(items)
    source_existing_items = sum(1 for item in items if bool(item.get("source_exists")))
    audio_ready_items = sum(1 for item in items if bool(item.get("audio_ready")))
    total_sec = round(sum(_safe_float(item.get("duration_sec"), 0.0) for item in items), 3)
    avg_sec = round(total_sec / usable_rows, 3) if usable_rows else 0.0
    avg_cps = round(sum(_safe_float(item.get("cps"), 0.0) for item in items) / usable_rows, 3) if usable_rows else 0.0

    plan = {
        "schema": "ai_subtitle_studio.stt1_whisper_adapter_training_plan.v1",
        "created_at": _now(),
        "backend": backend,
        "adapter_name": adapter_name,
        "base_model": base_model,
        "truth_table_path": str(truth_table_path),
        "voice_bridge_path": str(voice_bridge_path),
        "multimodal_context_path": str(multimodal_context_path),
        "dataset_path": str(dataset_path),
        "dataset_manifest_path": str(dataset_manifest_path),
        "runtime_manifest_path": str(runtime_manifest_path),
        "output_dir": str(out_dir),
        "artifacts": {
            "clips_dir": str(clips_dir),
            "adapter_dir": str(adapter_dir),
            "merged_transformers_dir": str(merged_transformers_dir),
            "ctranslate2_dir": str(ctranslate2_dir),
        },
        "thresholds": {
            "min_segment_sec": float(min_segment_sec),
            "max_segment_sec": float(max_segment_sec),
            "min_transcript_chars": int(min_transcript_chars),
            "min_runtime_rows": int(min_runtime_rows),
            "min_runtime_audio_items": int(min_runtime_audio_items),
            "min_runtime_retrieval_score": float(min_runtime_retrieval_score),
        },
        "hyperparams": {
            "epochs": int(epochs),
            "learning_rate": float(learning_rate),
            "lora_rank": int(lora_rank),
            "batch_size": int(batch_size),
            "gradient_accumulation_steps": int(gradient_accumulation_steps),
        },
        "stats": {
            "truth_rows": len(list(truth_rows or [])),
            "voice_bridge_rows": len(list(voice_rows or [])),
            "context_rows": len(list(context_rows or [])),
            "usable_training_rows": usable_rows,
            "source_existing_items": source_existing_items,
            "audio_ready_items": audio_ready_items,
            "avg_duration_sec": avg_sec,
            "avg_cps": avg_cps,
            "total_audio_sec": total_sec,
            "skipped": dict(sorted(skipped.items())),
            "facet_summary": {
                **{key: dict(counter.most_common(8)) for key, counter in facet_counts.items()},
                **{key: dict(counter.most_common(12)) for key, counter in list_facet_counts.items()},
            },
        },
        "items": items,
        "training_objective": {
            "task": "stt1_whisper_adapter_personalization",
            "input": "short transcript-aligned audio clips",
            "output": "STT1 Whisper adapter that improves first-pass subtitle transcription",
            "rules": [
                "Use only transcript text with (), [], {} already removed from spoken subtitle training text.",
                "Prioritize exact ground-truth timing and text over aggressive augmentation.",
                "Keep scene, mic, noise, and topic facets for later runtime retrieval and scoring.",
                "Runtime should combine this adapter with retrieval-based personalization instead of replacing it.",
            ],
        },
        "offline_training_recipe": {
            "prepare_audio_step": [
                "Generate missing mono WAV clips at 16kHz from source media by using each item's extraction_command.",
            ],
            "fine_tune_step": [
                "Load base Whisper in Transformers, apply PEFT LoRA/adapter tuning, and train on transcript_text.",
                "Merge the adapter into a runtime model after validation.",
            ],
            "runtime_step": [
                "Place merged HF model in merged_transformers_dir for macOS transformers runtime,",
                "or convert to CTranslate2 under ctranslate2_dir for faster-whisper runtime.",
            ],
        },
        "notes": [
            "This pipeline prepares STT1-only Whisper adapter data from ground-truth pairs and multimodal context.",
            "The current app keeps retrieval-based LoRA for prompt/settings correction and adds STT1 adapter only when a runtime-ready model exists.",
        ],
    }
    return plan


def _build_stt1_dataset_manifest(
    plan: dict[str, Any],
    *,
    dataset_path: Path,
    extraction_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stats = dict(plan.get("stats") or {})
    return {
        "schema": "ai_subtitle_studio.stt1_whisper_adapter_dataset_manifest.v1",
        "created_at": _now(),
        "dataset_path": str(dataset_path),
        "plan_path": str(plan.get("plan_path") or ""),
        "runtime_manifest_path": str(plan.get("runtime_manifest_path") or ""),
        "output_dir": str(plan.get("output_dir") or ""),
        "base_model": str(plan.get("base_model") or ""),
        "stats": stats,
        "training_tags_preview": list(
            {
                tag
                for item in list(plan.get("items") or [])[:24]
                for tag in list(item.get("training_tags") or [])
            }
        )[:24],
        "extraction": dict(extraction_result or {}),
        "notes": [
            "Ground-truth audio/text pairs prepared for STT1 Whisper adapter training.",
            "Dataset rows already exclude editorial bracket text from spoken transcript targets.",
        ],
    }


def _build_stt1_runtime_manifest(
    plan: dict[str, Any],
    *,
    extraction_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifacts = dict(plan.get("artifacts") or {})
    merged_transformers_dir = Path(str(artifacts.get("merged_transformers_dir") or ""))
    ctranslate2_dir = Path(str(artifacts.get("ctranslate2_dir") or ""))
    adapter_dir = Path(str(artifacts.get("adapter_dir") or ""))
    merged_status = _runtime_artifact_status(
        merged_transformers_dir,
        required_all=("config.json",),
        required_any=("generation_config.json", "preprocessor_config.json", "tokenizer_config.json", "tokenizer.json"),
    )
    ctranslate2_status = _runtime_artifact_status(
        ctranslate2_dir,
        required_all=("config.json",),
        required_any=("model.bin", "model.safetensors"),
    )
    adapter_status = _runtime_artifact_status(
        adapter_dir,
        required_all=("adapter_config.json",),
        required_any=("adapter_model.safetensors", "adapter_model.bin"),
    )
    stats = dict(plan.get("stats") or {})
    thresholds = dict(plan.get("thresholds") or {})
    runtime_candidates = {
        "mac": {
            "backend": "transformers-whisper",
            "selected_whisper_model": merged_status["path"] if bool(merged_status.get("ready")) else "",
            "ready": bool(merged_status.get("ready")),
        },
        "windows": {
            "backend": "faster-whisper",
            "selected_whisper_model": ctranslate2_status["path"] if bool(ctranslate2_status.get("ready")) else "",
            "ready": bool(ctranslate2_status.get("ready")),
        },
        "portable": {
            "backend": "transformers-whisper" if bool(merged_status.get("ready")) else ("faster-whisper" if bool(ctranslate2_status.get("ready")) else ""),
            "selected_whisper_model": (
                merged_status["path"]
                if bool(merged_status.get("ready"))
                else (ctranslate2_status["path"] if bool(ctranslate2_status.get("ready")) else "")
            ),
            "ready": bool(merged_status.get("ready") or ctranslate2_status.get("ready")),
        },
    }
    runtime_ready = any(bool(item.get("ready")) for item in runtime_candidates.values())
    return {
        "schema": "ai_subtitle_studio.stt1_whisper_adapter_runtime_manifest.v1",
        "updated_at": iso_now(),
        "adapter_name": str(plan.get("adapter_name") or ""),
        "base_model": str(plan.get("base_model") or ""),
        "dataset_path": str(plan.get("dataset_path") or ""),
        "dataset_manifest_path": str(plan.get("dataset_manifest_path") or ""),
        "plan_path": str(plan.get("plan_path") or ""),
        "output_dir": str(plan.get("output_dir") or ""),
        "dataset_stats": stats,
        "artifacts": {
            "adapter": adapter_status,
            "merged_transformers": merged_status,
            "ctranslate2": ctranslate2_status,
        },
        "runtime_candidates": runtime_candidates,
        "runtime_ready": runtime_ready,
        "activation_policy": {
            "minimum_truth_rows": _safe_int(thresholds.get("min_runtime_rows"), 24),
            "minimum_audio_ready_items": _safe_int(thresholds.get("min_runtime_audio_items"), 12),
            "minimum_retrieval_score": _safe_float(thresholds.get("min_runtime_retrieval_score"), 28.0),
            "allow_global_fallback": True,
        },
        "extraction": dict(extraction_result or {}),
        "notes": [
            "Runtime activation is gated by retrieval support plus a ready local STT1 adapter artifact.",
            "merged_transformers_dir is preferred on macOS; ctranslate2_dir is preferred on faster-whisper runtime.",
        ],
    }


def _extract_stt1_adapter_audio(
    items: list[dict[str, Any]],
    *,
    timeout_sec: float = 45.0,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
    resource_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extracted = 0
    already_ready = 0
    skipped = 0
    cancelled = False
    errors: list[dict[str, Any]] = []
    total = len(items)
    processed = 0
    pending_items: list[dict[str, Any]] = []

    def emit_progress(processed: int) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(
                {
                    "kind": "stt1_whisper_audio",
                    "stage": "stt1_whisper_audio_extraction",
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

    for item in items:
        if cancel_callback is not None and bool(cancel_callback()):
            cancelled = True
            break
        output_path = _item_audio_path(item)
        if output_path is not None and output_path.exists():
            item["audio_ready"] = True
            item["audio_exists"] = True
            item["audio_status"] = "already_ready"
            already_ready += 1
            processed += 1
            continue
        if not bool(item.get("source_exists")):
            item["audio_ready"] = False
            item["audio_status"] = "missing_source_media"
            skipped += 1
            processed += 1
            continue
        command = list(item.get("extraction_command") or [])
        if not command or output_path is None:
            item["audio_ready"] = False
            item["audio_status"] = "missing_extraction_command"
            skipped += 1
            processed += 1
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pending_items.append(item)

    if processed:
        emit_progress(processed)
    if cancelled or not pending_items:
        emit_progress(processed)
        return {
            "extracted": extracted,
            "already_ready": already_ready,
            "skipped": skipped,
            "errors": errors,
            "cancelled": cancelled,
        }

    worker_settings = dict(resource_settings or {})
    reserve_task = "manual_lora" if bool(worker_settings.get("runtime_manual_lora_full_speed")) else "lora"
    max_workers, _scheduler = runtime_parallel_worker_plan(
        settings=worker_settings,
        task="lora",
        workload=len(pending_items),
        minimum=1,
        reserve_task=reserve_task,
    )
    ffmpeg_single_thread = max_workers > 1
    state_lock = threading.Lock()

    def run_one(item: dict[str, Any]) -> dict[str, Any]:
        output_path = _item_audio_path(item)
        if output_path is None:
            return {"status": "missing_extraction_command", "item": item}
        if cancel_callback is not None and bool(cancel_callback()):
            return {"status": "cancelled", "item": item, "audio_path": str(output_path)}
        command = list(item.get("extraction_command") or [])
        if ffmpeg_single_thread and command and "-threads" not in command:
            command = [command[0], "-threads", "1", *command[1:]]
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
            return {"status": "error", "item": item, "audio_path": str(output_path), "error": str(exc)}
        if completed.returncode == 0 and output_path.exists():
            return {"status": "extracted", "item": item, "audio_path": str(output_path)}
        return {
            "status": "failed",
            "item": item,
            "audio_path": str(output_path),
            "returncode": int(completed.returncode),
            "stderr": (completed.stderr or "")[-500:],
        }

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="stt1-lora-extract") as executor:
        futures: dict[Any, dict[str, Any]] = {}
        next_index = 0
        while next_index < len(pending_items) and len(futures) < max_workers:
            pending = pending_items[next_index]
            futures[executor.submit(run_one, pending)] = pending
            next_index += 1
        while futures:
            done, _pending = wait(tuple(futures.keys()), return_when=FIRST_COMPLETED)
            for future in done:
                item = futures.pop(future, None)
                try:
                    outcome = dict(future.result() or {})
                except Exception as exc:
                    outcome = {
                        "status": "error",
                        "item": item or {},
                        "audio_path": str(_item_audio_path(item or {}) or ""),
                        "error": str(exc),
                    }
                status = str(outcome.get("status") or "")
                target = outcome.get("item") or item or {}
                with state_lock:
                    if status == "extracted":
                        target["audio_ready"] = True
                        target["audio_exists"] = True
                        target["audio_status"] = "extracted"
                        extracted += 1
                    elif status == "cancelled":
                        cancelled = True
                    elif status == "error":
                        target["audio_ready"] = False
                        target["audio_status"] = "error"
                        target["extraction_error"] = str(outcome.get("error") or "")
                        errors.append({"audio_path": str(outcome.get("audio_path") or ""), "error": str(outcome.get("error") or "")})
                    else:
                        target["audio_ready"] = False
                        target["audio_status"] = "failed"
                        errors.append(
                            {
                                "audio_path": str(outcome.get("audio_path") or ""),
                                "returncode": int(outcome.get("returncode", 1) or 1),
                                "stderr": str(outcome.get("stderr") or ""),
                            }
                        )
                    processed += 1
                if cancel_callback is not None and bool(cancel_callback()):
                    cancelled = True
                if not cancelled and next_index < len(pending_items):
                    pending = pending_items[next_index]
                    futures[executor.submit(run_one, pending)] = pending
                    next_index += 1
                if processed == total or processed % 25 == 0:
                    emit_progress(processed)
    emit_progress(processed)
    return {
        "extracted": extracted,
        "already_ready": already_ready,
        "skipped": skipped,
        "errors": errors,
        "cancelled": cancelled,
    }


def save_stt1_whisper_adapter_training_plan(
    *,
    store_dir: str | Path | None = None,
    truth_table_path: str | Path | None = None,
    voice_bridge_path: str | Path | None = None,
    multimodal_context_path: str | Path | None = None,
    dataset_path: str | Path | None = None,
    dataset_manifest_path: str | Path | None = None,
    plan_path: str | Path | None = None,
    runtime_manifest_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    extract_audio: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
    resource_settings: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    paths = store_paths(store_dir)
    truth_target = Path(truth_table_path) if truth_table_path else paths["truth_table"]
    voice_target = Path(voice_bridge_path) if voice_bridge_path else paths["voice_lora_bridge"]
    context_target = Path(multimodal_context_path) if multimodal_context_path else paths["multimodal_lora_context"]
    dataset_target = Path(dataset_path) if dataset_path else paths["stt1_whisper_adapter_dataset"]
    dataset_manifest_target = Path(dataset_manifest_path) if dataset_manifest_path else paths["stt1_whisper_adapter_dataset_manifest"]
    plan_target = Path(plan_path) if plan_path else paths["stt1_whisper_adapter_training_plan"]
    runtime_manifest_target = Path(runtime_manifest_path) if runtime_manifest_path else paths["stt1_whisper_adapter_runtime_manifest"]
    output_target = Path(output_dir) if output_dir else (paths["trained_adapters"] / "personal_stt1_whisper_adapter")
    output_target.mkdir(parents=True, exist_ok=True)
    dataset_target.parent.mkdir(parents=True, exist_ok=True)
    dataset_manifest_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_manifest_target.parent.mkdir(parents=True, exist_ok=True)

    plan = build_stt1_whisper_adapter_training_plan(
        truth_table_path=truth_target,
        voice_bridge_path=voice_target,
        multimodal_context_path=context_target,
        output_dir=output_target,
        dataset_path=dataset_target,
        dataset_manifest_path=dataset_manifest_target,
        runtime_manifest_path=runtime_manifest_target,
        **kwargs,
    )
    extraction_result = {"extracted": 0, "already_ready": 0, "skipped": 0, "errors": [], "cancelled": False}
    if extract_audio:
        extraction_result = _extract_stt1_adapter_audio(
            list(plan.get("items") or []),
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
            resource_settings=resource_settings,
        )
    plan["plan_path"] = str(plan_target)
    plan["dataset_path"] = str(dataset_target)
    plan["dataset_manifest_path"] = str(dataset_manifest_target)
    plan["runtime_manifest_path"] = str(runtime_manifest_target)
    plan["output_dir"] = str(output_target)
    plan_stats = dict(plan.get("stats") or {})
    plan_stats["audio_ready_items"] = sum(1 for item in list(plan.get("items") or []) if bool(item.get("audio_ready")))
    plan["stats"] = plan_stats
    if extract_audio:
        plan["last_audio_materialization"] = {"created_at": _now(), **dict(extraction_result)}

    dataset_rows = [
        {
            key: value
            for key, value in dict(item).items()
            if key not in {"extraction_command"}
        }
        for item in list(plan.get("items") or [])
    ]
    dataset_manifest = _build_stt1_dataset_manifest(plan, dataset_path=dataset_target, extraction_result=extraction_result)
    runtime_manifest = _build_stt1_runtime_manifest(plan, extraction_result=extraction_result)

    write_jsonl(dataset_target, dataset_rows)
    write_json(plan_target, plan)
    write_json(dataset_manifest_target, dataset_manifest)
    write_json(runtime_manifest_target, runtime_manifest)

    stats = dict(plan.get("stats") or {})
    runtime_candidates = dict(runtime_manifest.get("runtime_candidates") or {})
    runtime_model = ""
    for key in ("mac", "windows", "portable"):
        candidate = dict(runtime_candidates.get(key) or {})
        runtime_model = str(candidate.get("selected_whisper_model") or "").strip()
        if runtime_model:
            break

    return {
        "plan_path": str(plan_target),
        "dataset_path": str(dataset_target),
        "dataset_manifest_path": str(dataset_manifest_target),
        "runtime_manifest_path": str(runtime_manifest_target),
        "backend": str(plan.get("backend") or ""),
        "usable_rows": int(stats.get("usable_training_rows", 0) or 0),
        "source_existing_items": int(stats.get("source_existing_items", 0) or 0),
        "audio_ready_items": int(stats.get("audio_ready_items", 0) or 0),
        "extracted_clips": int(extraction_result.get("extracted", 0) or 0),
        "already_ready_clips": int(extraction_result.get("already_ready", 0) or 0),
        "extraction_skipped": int(extraction_result.get("skipped", 0) or 0),
        "extraction_errors": int(len(list(extraction_result.get("errors") or []))),
        "cancelled": bool(extraction_result.get("cancelled")),
        "runtime_ready": bool(runtime_manifest.get("runtime_ready")),
        "runtime_model": runtime_model,
        "output_dir": str(output_target),
    }


__all__ = [
    "STT1_WHISPER_ADAPTER_DATASET_MANIFEST_PATH",
    "STT1_WHISPER_ADAPTER_DATASET_PATH",
    "STT1_WHISPER_ADAPTER_RUNTIME_MANIFEST_PATH",
    "STT1_WHISPER_ADAPTER_TRAINING_PLAN_PATH",
    "build_stt1_whisper_adapter_training_plan",
    "save_stt1_whisper_adapter_training_plan",
]
