from __future__ import annotations

import json
import hashlib
import uuid
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from typing import Any

from core.personalization.ground_truth_import import extract_parenthetical_segments
from core.personalization.lora_context_classifier import classify_lora_context
from core.personalization.lora_models import TrainingQueueItem, stable_hash
from core.personalization.lora_storage import LORA_PERSONALIZATION_DIR, refresh_unified_lora_data_bundle, upsert_training_queue_items
from core.project.data_manager import CORRECTION_FILE
from core.project.project_manager import PROJECTS_DIR, load_project
from core.project.project_context import project_segments_to_editor
from core.frame_time import normalize_fps, sec_to_frame
from core.subtitle_quality.correction_memory import load_correction_memory
from core.subtitle_quality.wrong_answer_memory import load_wrong_answer_memory


TEXT_LORA_DATASET_DIR = Path(LORA_PERSONALIZATION_DIR)
TEXT_LORA_DATASET_PATH = TEXT_LORA_DATASET_DIR / "text_lora_dataset.jsonl"
TEXT_LORA_MANIFEST_PATH = TEXT_LORA_DATASET_DIR / "text_lora_manifest.json"
TEXT_LORA_CORPUS_PATH = TEXT_LORA_DATASET_DIR / "text_lora_corpus.jsonl"
TEXT_LORA_CORPUS_MANIFEST_PATH = TEXT_LORA_DATASET_DIR / "text_lora_corpus_manifest.json"
VOICE_LORA_BRIDGE_PATH = TEXT_LORA_DATASET_DIR / "voice_lora_bridge.jsonl"
MULTIMODAL_LORA_CONTEXT_PATH = TEXT_LORA_DATASET_DIR / "multimodal_lora_context.jsonl"
TEXT_LORA_QUALITY_PROFILE = {
    "project_pair_min_input_chars": 4,
    "project_pair_min_output_chars": 4,
    "project_pair_max_chars": 120,
    "project_pair_min_delta_ratio": 0.08,
    "training_goal": "subtitle_qa_correction",
    "preserve_speech_style": True,
    "avoid_invention": True,
}
TEXT_LORA_SUBTITLE_QA_INSTRUCTION = (
    "STT 후보를 최종 자막으로 검수한다. 원문 발화의 단어, 순서, 의미, 구어체를 보존하고 "
    "띄어쓰기, 명백한 오탈자, 최소 문장부호만 교정한다. 없는 말, 설명, 요약, 문어체 변환, "
    "고유명사/숫자 추측 교정을 하지 않는다."
)
TEXT_LORA_HALLUCINATION_INSTRUCTION = (
    "자막 검수 중 확인된 STT 환각/오답 문구를 제거하거나 사용하지 않도록 학습한다. "
    "확실하지 않은 내용은 새 문장으로 보강하지 않는다."
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_text(text: Any) -> str:
    return " ".join(str(text or "").strip().split())


def _json_safe(value: Any, *, max_depth: int = 6) -> Any:
    if max_depth <= 0:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item, max_depth=max_depth - 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, max_depth=max_depth - 1) for item in list(value)]
    return str(value)


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _speech_training_text(text: Any) -> str:
    """Remove user-added editorial notes before any subtitle learning row is built."""
    extracted = extract_parenthetical_segments(str(text or ""))
    return _normalize_text(extracted.get("speech_training_text"))


def _iter_project_paths(project_root: str | Path | None = None) -> list[Path]:
    root = Path(project_root) if project_root else Path(PROJECTS_DIR)
    if not root.exists():
        return []
    paths = sorted(root.rglob("*.json"), key=lambda p: str(p))
    return [path for path in paths if path.is_file()]


def _selected_candidate_input(seg: dict[str, Any]) -> tuple[str, str]:
    selected_source = str(
        seg.get("stt_selected_source")
        or seg.get("stt_ensemble_llm_selected_source")
        or seg.get("stt_ensemble_source")
        or ""
    ).strip().upper()
    candidates = list(seg.get("stt_candidates") or [])
    if not selected_source:
        return "", ""
    for candidate in candidates:
        if str(candidate.get("source", "") or "").strip().upper() != selected_source:
            continue
        text = _speech_training_text(candidate.get("text"))
        if text:
            return selected_source, text
    return selected_source, ""


def _candidate_context(seg: dict[str, Any], selected_source: str) -> dict[str, Any]:
    candidates = []
    selected_index = -1
    for index, candidate in enumerate(list(seg.get("stt_candidates") or [])):
        if not isinstance(candidate, dict):
            continue
        source = str(candidate.get("source") or "").strip().upper()
        text = _speech_training_text(candidate.get("text"))
        if source and source == selected_source:
            selected_index = index
        candidates.append(
            {
                "source": source,
                "text": text,
                "raw_text": str(candidate.get("text") or "").strip(),
                "confidence": _json_safe(candidate.get("confidence", candidate.get("confidence_score"))),
                "score": _json_safe(candidate.get("score")),
                "avg_logprob": _json_safe(candidate.get("avg_logprob")),
                "no_speech_prob": _json_safe(candidate.get("no_speech_prob")),
                "compression_ratio": _json_safe(candidate.get("compression_ratio")),
            }
        )
    texts = [str(item.get("text") or "") for item in candidates if str(item.get("text") or "")]
    disagreement = 0.0
    if len(texts) >= 2:
        base = texts[0]
        disagreement = max(_delta_ratio(base, text) for text in texts[1:])
    return {
        "selected_source": selected_source,
        "selected_index": selected_index,
        "candidate_count": len(candidates),
        "candidate_sources": [str(item.get("source") or "") for item in candidates if str(item.get("source") or "")],
        "candidate_disagreement_ratio": round(float(disagreement), 4),
        "candidates": candidates,
    }


def _extract_known_context_fields(seg: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key in (
        "quality",
        "audio_profile",
        "audio_strategy",
        "audio_strategy_label",
        "audio_tune_reason",
        "audio_tune_settings",
        "vad",
        "vad_segments",
        "words",
        "word_timestamps",
    ):
        value = seg.get(key)
        if value not in (None, "", [], {}):
            context[key] = _json_safe(value)
    return context


def _segment_context_signature(row: dict[str, Any]) -> str:
    raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _segment_fps(seg: dict[str, Any], default: float = 30.0) -> float:
    frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
    for key in (
        "timeline_frame_rate",
        "frame_rate",
        "source_frame_rate",
    ):
        value = seg.get(key, frame_range.get(key))
        try:
            return normalize_fps(float(value or 0.0) or default)
        except Exception:
            continue
    return normalize_fps(default)


def _segment_frame_bounds(seg: dict[str, Any], default_fps: float = 30.0) -> tuple[int, int, float]:
    fps = _segment_fps(seg, default_fps)
    frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
    start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
    end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
    if start_frame is None:
        start_frame = sec_to_frame(float(seg.get("start", seg.get("timeline_start", 0.0)) or 0.0), fps)
    if end_frame is None:
        end_frame = sec_to_frame(float(seg.get("end", seg.get("timeline_end", seg.get("start", 0.0))) or 0.0), fps)
    start_frame = max(0, int(start_frame))
    end_frame = max(start_frame, int(end_frame))
    return start_frame, end_frame, fps


def _delta_ratio(src: str, dst: str) -> float:
    src = _normalize_text(src)
    dst = _normalize_text(dst)
    if not src and not dst:
        return 0.0
    return 1.0 - float(SequenceMatcher(None, src, dst).ratio())


def _project_pair_quality(src: str, dst: str) -> tuple[bool, str, float]:
    src = _normalize_text(src)
    dst = _normalize_text(dst)
    if len(src) < int(TEXT_LORA_QUALITY_PROFILE["project_pair_min_input_chars"]):
        return False, "short_input", 0.0
    if len(dst) < int(TEXT_LORA_QUALITY_PROFILE["project_pair_min_output_chars"]):
        return False, "short_output", 0.0
    if len(src) > int(TEXT_LORA_QUALITY_PROFILE["project_pair_max_chars"]) or len(dst) > int(TEXT_LORA_QUALITY_PROFILE["project_pair_max_chars"]):
        return False, "too_long", 0.0
    delta = _delta_ratio(src, dst)
    if delta < float(TEXT_LORA_QUALITY_PROFILE["project_pair_min_delta_ratio"]):
        return False, "low_delta", delta
    return True, "accepted", delta


def _segment_rows_for_lora(
    segments: list[dict[str, Any]] | None,
    *,
    project_path: str = "",
    project_name: str = "",
    source_tag: str = "project_segment_pair",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    voice_rows: list[dict[str, Any]] = []
    context_rows: list[dict[str, Any]] = []
    filtered = {"short_input": 0, "short_output": 0, "too_long": 0, "low_delta": 0, "editorial_only": 0}
    for index, seg in enumerate(segments or [], start=1):
        if not isinstance(seg, dict):
            continue
        raw_output = _normalize_text(seg.get("text"))
        output = _speech_training_text(seg.get("text"))
        if not output:
            if raw_output:
                filtered["editorial_only"] = int(filtered.get("editorial_only", 0) or 0) + 1
            continue
        selected_source, input_text = _selected_candidate_input(seg)
        if not input_text or input_text == output:
            continue
        accepted, reason, delta = _project_pair_quality(input_text, output)
        start_frame, end_frame, fps = _segment_frame_bounds(seg)
        candidate_context = _candidate_context(seg, selected_source)
        speaker = str(seg.get("speaker", seg.get("spk", "")) or "")
        clip_path = str(seg.get("_clip_file", seg.get("clip_file", "")) or "")
        clip_idx = seg.get("_clip_idx", seg.get("clip_idx"))
        start_sec = float(seg.get("start", 0.0) or 0.0)
        end_sec = float(seg.get("end", start_sec) or start_sec)
        duration_sec = max(0.0, end_sec - start_sec)
        selected_index = int(candidate_context.get("selected_index", -1) or -1)
        candidate_rows = list(candidate_context.get("candidates") or [])
        selected_raw_input = ""
        if 0 <= selected_index < len(candidate_rows):
            selected_raw_input = str(candidate_rows[selected_index].get("raw_text") or "")
        generation_context = _extract_known_context_fields(seg)
        context_classification = classify_lora_context(
            texts=[raw_output, output, input_text, selected_raw_input],
            file_hints=[project_name, project_path, clip_path],
            audio_profile=dict(generation_context.get("audio_profile") or {}),
            generation_context=generation_context,
            subtitle_profile={
                "speech_segments": 1,
                "excluded_parenthetical_ratio": 1.0 if raw_output != output or selected_raw_input != input_text else 0.0,
                "reading_speed": {
                    "avg_cps": round(len(output.replace("\n", "")) / duration_sec, 3) if duration_sec > 0 else 0.0,
                    "max_cps": round(len(output.replace("\n", "")) / duration_sec, 3) if duration_sec > 0 else 0.0,
                },
            },
        )
        voice_rows.append(
            {
                "schema": "ai_subtitle_studio.voice_lora_bridge.v1",
                "task": "voice_text_alignment_seed",
                "source": source_tag,
                "project_path": project_path,
                "project_name": project_name,
                "segment_index": index,
                "text": output,
                "speaker": speaker,
                "clip_path": clip_path,
                "clip_idx": clip_idx,
                "start_sec": round(start_sec, 3),
                "end_sec": round(end_sec, 3),
                "duration_sec": round(duration_sec, 3),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "fps": fps,
                "duration_frames": max(0, end_frame - start_frame),
                "selected_source": selected_source,
                "input_text": input_text,
                "candidate_context": candidate_context,
                "generation_context": generation_context,
                "context_classification": context_classification,
            }
        )
        context_row = {
            "schema": "ai_subtitle_studio.multimodal_lora_context.v1",
            "task": "editor_segment_generation_context",
            "source": source_tag,
            "project_path": project_path,
            "project_name": project_name,
            "segment_index": index,
            "clip_path": clip_path,
            "clip_idx": clip_idx,
            "speaker": speaker,
            "start_sec": round(start_sec, 3),
            "end_sec": round(end_sec, 3),
            "duration_sec": round(duration_sec, 3),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "fps": fps,
            "input_text": input_text,
            "final_subtitle_text": output,
            "delta_ratio": round(float(delta), 4),
            "accepted_for_text_lora": bool(accepted),
            "filter_reason": reason,
            "candidate_context": candidate_context,
            "generation_context": generation_context,
            "context_classification": context_classification,
            "excluded_parenthetical_policy": {
                "remove_from_learning_text": ["()", "[]", "{}"],
                "input_raw": selected_raw_input,
                "output_raw": raw_output,
            },
        }
        context_row["signature"] = _segment_context_signature(
            {
                "task": context_row["task"],
                "source": context_row["source"],
                "project_path": project_path,
                "segment_index": index,
                "clip_path": clip_path,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "input_text": input_text,
                "final_subtitle_text": output,
            }
        )
        context_rows.append(context_row)
        if not accepted:
            filtered[reason] = int(filtered.get(reason, 0) or 0) + 1
            continue
        rows.append(
            {
                "task": "text_correction",
                "source": source_tag,
                "input": input_text,
                "output": output,
                "instruction": TEXT_LORA_SUBTITLE_QA_INSTRUCTION,
                "meta": {
                    "project_path": project_path,
                    "project_name": project_name,
                    "segment_index": index,
                    "selected_source": selected_source,
                    "candidate_context": candidate_context,
                    "start": start_sec,
                    "end": end_sec,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "fps": fps,
                    "speaker": speaker,
                    "clip_path": clip_path,
                    "clip_idx": clip_idx,
                    "duration_sec": round(duration_sec, 3),
                    "duration_frames": max(0, end_frame - start_frame),
                    "delta_ratio": round(float(delta), 4),
                    "char_delta": abs(len(output) - len(input_text)),
                    "generation_context": generation_context,
                    "context_classification": context_classification,
                },
            }
        )
    return {"rows": rows, "voice_rows": voice_rows, "context_rows": context_rows, "filtered": filtered}


def load_project_segment_pairs(
    *,
    project_paths: list[str | Path] | None = None,
    project_root: str | Path | None = None,
    project_payloads: list[dict[str, Any]] | None = None,
    current_segments: list[dict[str, Any]] | None = None,
    current_project_path: str = "",
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    voice_items: list[dict[str, Any]] = []
    context_items: list[dict[str, Any]] = []
    files_scanned = 0
    filtered_counts = {"short_input": 0, "short_output": 0, "too_long": 0, "low_delta": 0, "editorial_only": 0}

    if current_segments:
        result = _segment_rows_for_lora(
            current_segments,
            project_path=current_project_path,
            project_name=Path(current_project_path).name if current_project_path else "current_editor",
            source_tag="current_editor_segment_pair",
        )
        items.extend(result["rows"])
        voice_items.extend(result.get("voice_rows") or [])
        context_items.extend(result.get("context_rows") or [])
        for key, value in dict(result.get("filtered") or {}).items():
            filtered_counts[key] = int(filtered_counts.get(key, 0) or 0) + int(value or 0)

    for payload in project_payloads or []:
        if not isinstance(payload, dict):
            continue
        files_scanned += 1
        segments = project_segments_to_editor(payload)
        result = _segment_rows_for_lora(
            segments,
            project_path=str(payload.get("_project_path", "") or ""),
            project_name=str(payload.get("project_name", "") or ""),
            source_tag="project_segment_pair",
        )
        items.extend(result["rows"])
        voice_items.extend(result.get("voice_rows") or [])
        context_items.extend(result.get("context_rows") or [])
        for key, value in dict(result.get("filtered") or {}).items():
            filtered_counts[key] = int(filtered_counts.get(key, 0) or 0) + int(value or 0)

    auto_paths: list[Path] = []
    if project_paths is not None:
        auto_paths = [Path(p) for p in project_paths]
    elif not project_payloads:
        auto_paths = _iter_project_paths(project_root)
    paths = auto_paths
    for path in paths:
        try:
            payload = load_project(str(path))
        except Exception:
            continue
        files_scanned += 1
        segments = project_segments_to_editor(payload)
        result = _segment_rows_for_lora(
            segments,
            project_path=str(path),
            project_name=str(payload.get("project_name", "") or path.stem),
            source_tag="project_segment_pair",
        )
        items.extend(result["rows"])
        voice_items.extend(result.get("voice_rows") or [])
        context_items.extend(result.get("context_rows") or [])
        for key, value in dict(result.get("filtered") or {}).items():
            filtered_counts[key] = int(filtered_counts.get(key, 0) or 0) + int(value or 0)

    return {
        "files_scanned": files_scanned,
        "items": items,
        "voice_items": voice_items,
        "context_items": context_items,
        "filtered": filtered_counts,
    }


def load_legacy_corrections(path: str | Path | None = None) -> dict[str, str]:
    target = Path(path) if path else Path(CORRECTION_FILE)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, str] = {}
    for original, corrected in data.items():
        src = _speech_training_text(original)
        dst = _speech_training_text(corrected)
        if src and dst and src != dst:
            cleaned[src] = dst
    return dict(sorted(cleaned.items(), key=lambda item: len(item[0]), reverse=True))


def build_text_lora_dataset(
    *,
    corrections_path: str | Path | None = None,
    correction_memory_path: str | Path | None = None,
    wrong_answer_memory_path: str | Path | None = None,
    project_paths: list[str | Path] | None = None,
    project_root: str | Path | None = None,
    project_payloads: list[dict[str, Any]] | None = None,
    current_segments: list[dict[str, Any]] | None = None,
    current_project_path: str = "",
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    stats = {
        "legacy_corrections": 0,
        "correction_memory": 0,
        "wrong_answer_memory": 0,
        "project_segment_pairs": 0,
        "project_files_scanned": 0,
        "voice_bridge_items": 0,
        "multimodal_context_items": 0,
    }

    for original, corrected in load_legacy_corrections(corrections_path).items():
        key = ("legacy_correction", original, corrected)
        if key in seen:
            continue
        seen.add(key)
        stats["legacy_corrections"] += 1
        items.append(
            {
                "task": "text_correction",
                "source": "legacy_correction",
                "input": original,
                "output": corrected,
                "instruction": TEXT_LORA_SUBTITLE_QA_INSTRUCTION,
                "meta": {
                    "priority": "high",
                    "weight": 1.0,
                    "delta_ratio": round(_delta_ratio(original, corrected), 4),
                },
            }
        )

    for row in load_correction_memory(correction_memory_path).get("items", []):
        if not isinstance(row, dict):
            continue
        original = _speech_training_text(row.get("original"))
        corrected = _speech_training_text(row.get("corrected"))
        if not original or not corrected or original == corrected:
            continue
        key = ("correction_memory", original, corrected)
        if key in seen:
            continue
        seen.add(key)
        stats["correction_memory"] += 1
        items.append(
            {
                "task": "text_correction",
                "source": "correction_memory",
                "input": original,
                "output": corrected,
                "instruction": TEXT_LORA_SUBTITLE_QA_INSTRUCTION,
                "meta": {
                    "type": str(row.get("type") or "typo"),
                    "confidence": float(row.get("confidence", 0.0) or 0.0),
                    "count": int(row.get("count", 1) or 1),
                    "context": str(row.get("context") or ""),
                    "weight": round(
                        min(2.5, 1.0 + (float(row.get("confidence", 0.0) or 0.0) * 0.8) + (min(int(row.get("count", 1) or 1), 5) * 0.12)),
                        3,
                    ),
                    "delta_ratio": round(_delta_ratio(original, corrected), 4),
                },
            }
        )

    for row in load_wrong_answer_memory(wrong_answer_memory_path).get("items", []):
        if not isinstance(row, dict):
            continue
        phrase = _speech_training_text(row.get("phrase"))
        if not phrase:
            continue
        key = ("wrong_answer_memory", phrase, "")
        if key in seen:
            continue
        seen.add(key)
        stats["wrong_answer_memory"] += 1
        items.append(
            {
                "task": "remove_hallucination",
                "source": "wrong_answer_memory",
                "input": phrase,
                "output": "",
                "instruction": TEXT_LORA_HALLUCINATION_INSTRUCTION,
                "meta": {
                    "count": int(row.get("count", 1) or 1),
                    "context": str(row.get("context") or ""),
                    "weight": round(min(2.0, 1.0 + (min(int(row.get("count", 1) or 1), 5) * 0.15)), 3),
                },
            }
        )

    project_pairs = load_project_segment_pairs(
        project_paths=project_paths,
        project_root=project_root,
        project_payloads=project_payloads,
        current_segments=current_segments,
        current_project_path=current_project_path,
    )
    stats["project_files_scanned"] = int(project_pairs.get("files_scanned", 0) or 0)
    project_filtered = dict(project_pairs.get("filtered") or {})
    stats["project_pairs_filtered_short_input"] = int(project_filtered.get("short_input", 0) or 0)
    stats["project_pairs_filtered_short_output"] = int(project_filtered.get("short_output", 0) or 0)
    stats["project_pairs_filtered_too_long"] = int(project_filtered.get("too_long", 0) or 0)
    stats["project_pairs_filtered_low_delta"] = int(project_filtered.get("low_delta", 0) or 0)
    stats["project_pairs_filtered_editorial_only"] = int(project_filtered.get("editorial_only", 0) or 0)
    for row in project_pairs.get("items", []):
        original = _normalize_text(row.get("input"))
        corrected = _normalize_text(row.get("output"))
        if not original or not corrected or original == corrected:
            continue
        key = ("project_segment_pair", original, corrected)
        if key in seen:
            continue
        seen.add(key)
        stats["project_segment_pairs"] += 1
        items.append(row)
    stats["voice_bridge_items"] = int(len(project_pairs.get("voice_items") or []))
    stats["multimodal_context_items"] = int(len(project_pairs.get("context_items") or []))

    items.sort(
        key=lambda item: (
            0 if item["task"] == "text_correction" else 1,
            -len(str(item.get("input", "") or "")),
            str(item.get("source", "")),
        )
    )
    return {
        "schema": "ai_subtitle_studio.text_lora_dataset.v1",
        "created_at": _now(),
        "quality_profile": dict(TEXT_LORA_QUALITY_PROFILE),
        "stats": {
            **stats,
            "total_items": len(items),
        },
        "items": items,
        "voice_items": list(project_pairs.get("voice_items") or []),
        "context_items": list(project_pairs.get("context_items") or []),
    }


def export_text_lora_dataset(
    *,
    dataset_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    corrections_path: str | Path | None = None,
    correction_memory_path: str | Path | None = None,
    wrong_answer_memory_path: str | Path | None = None,
    project_paths: list[str | Path] | None = None,
    project_root: str | Path | None = None,
    project_payloads: list[dict[str, Any]] | None = None,
    current_segments: list[dict[str, Any]] | None = None,
    current_project_path: str = "",
) -> dict[str, Any]:
    payload = build_text_lora_dataset(
        corrections_path=corrections_path,
        correction_memory_path=correction_memory_path,
        wrong_answer_memory_path=wrong_answer_memory_path,
        project_paths=project_paths,
        project_root=project_root,
        project_payloads=project_payloads,
        current_segments=current_segments,
        current_project_path=current_project_path,
    )
    dataset_target = Path(dataset_path) if dataset_path else TEXT_LORA_DATASET_PATH
    manifest_target = Path(manifest_path) if manifest_path else TEXT_LORA_MANIFEST_PATH
    _write_jsonl_atomic(dataset_target, list(payload["items"]))

    manifest = {
        "schema": payload["schema"],
        "created_at": payload["created_at"],
        "dataset_path": str(dataset_target),
        "quality_profile": dict(payload.get("quality_profile") or TEXT_LORA_QUALITY_PROFILE),
        "stats": dict(payload["stats"]),
        "notes": [
            "legacy_correction + correction_memory + wrong_answer_memory 흡수",
            "프로젝트 STT 선택 결과 -> 최종 자막 pair 흡수",
            "() / [] / {} 안의 사용자 설명 자막은 학습 텍스트와 음성 bridge에서 제외",
            "짧은 pair / 변화량 낮은 pair / 과도하게 긴 pair는 자동 제외",
            "LoRA 학습 전 텍스트 개인화 코퍼스",
        ],
    }
    _write_json_atomic(manifest_target, manifest)
    return {
        "dataset_path": str(dataset_target),
        "manifest_path": str(manifest_target),
        "stats": dict(payload["stats"]),
    }


def _dataset_row_signature(row: dict[str, Any]) -> str:
    payload = {
        "task": row.get("task"),
        "source": row.get("source"),
        "input": _normalize_text(row.get("input")),
        "output": _normalize_text(row.get("output")),
        "selected_source": str(((row.get("meta") or {}).get("selected_source", "")) or ""),
        "project_name": str(((row.get("meta") or {}).get("project_name", "")) or ""),
        "speaker": str(((row.get("meta") or {}).get("speaker", "")) or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _voice_bridge_signature(row: dict[str, Any]) -> str:
    payload = {
        "project_path": str(row.get("project_path", "") or ""),
        "clip_path": str(row.get("clip_path", "") or ""),
        "segment_index": int(row.get("segment_index", 0) or 0),
        "start_frame": int(row.get("start_frame", 0) or 0),
        "end_frame": int(row.get("end_frame", 0) or 0),
        "text": _normalize_text(row.get("text")),
        "speaker": str(row.get("speaker", "") or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_existing_signatures(path: Path, *, key_name: str = "signature") -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                sig = str(row.get(key_name, "") or "")
                if sig:
                    seen.add(sig)
    except Exception:
        return set()
    return seen


def _enqueue_auto_maintenance_jobs(
    *,
    trigger: str,
    text_total_rows: int,
    voice_bridge_total_rows: int,
    multimodal_context_total_rows: int,
    appended_rows: int,
    voice_bridge_rows: int,
    multimodal_context_rows: int,
) -> dict[str, Any]:
    changed_rows = int(appended_rows or 0) + int(voice_bridge_rows or 0) + int(multimodal_context_rows or 0)
    if changed_rows <= 0:
        return {"queued": False, "reason": "no_new_rows", "items": 0}
    batch_id = stable_hash(
        {
            "trigger": str(trigger or ""),
            "text_total_rows": int(text_total_rows or 0),
            "voice_bridge_total_rows": int(voice_bridge_total_rows or 0),
            "multimodal_context_total_rows": int(multimodal_context_total_rows or 0),
        }
    )[:12]
    payload = {
        "auto_maintenance": True,
        "trigger": str(trigger or ""),
        "batch_id": batch_id,
        "text_total_rows": int(text_total_rows or 0),
        "voice_bridge_total_rows": int(voice_bridge_total_rows or 0),
        "multimodal_context_total_rows": int(multimodal_context_total_rows or 0),
        "new_rows": {
            "text": int(appended_rows or 0),
            "voice": int(voice_bridge_rows or 0),
            "context": int(multimodal_context_rows or 0),
        },
    }
    jobs = [
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="analyze_truth_table",
            job_id=f"auto-rules-{batch_id}",
            priority=15,
            payload=payload,
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_text_training_plan",
            job_id=f"auto-text-{batch_id}",
            priority=25,
            payload=payload,
        ).to_record(),
        TrainingQueueItem(
            media_id="global",
            media_path="",
            subtitle_path="",
            job_type="build_voice_profiles",
            job_id=f"auto-voice-{batch_id}",
            priority=35,
            payload=payload,
        ).to_record(),
    ]
    result = upsert_training_queue_items(jobs, TEXT_LORA_DATASET_DIR)
    return {"queued": True, "batch_id": batch_id, "items": len(list(result.get("items") or []))}


def accumulate_personalization_dataset(
    *,
    current_segments: list[dict[str, Any]] | None = None,
    current_project_path: str = "",
    trigger: str = "manual",
) -> dict[str, Any]:
    payload = build_text_lora_dataset(
        project_paths=[],
        current_segments=current_segments,
        current_project_path=current_project_path,
    )
    corpus_path = TEXT_LORA_CORPUS_PATH
    bridge_path = VOICE_LORA_BRIDGE_PATH
    context_path = MULTIMODAL_LORA_CONTEXT_PATH
    manifest_path = TEXT_LORA_CORPUS_MANIFEST_PATH
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    bridge_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.parent.mkdir(parents=True, exist_ok=True)

    existing_dataset = _load_existing_signatures(corpus_path)
    existing_voice = _load_existing_signatures(bridge_path)
    existing_context = _load_existing_signatures(context_path)
    appended = 0
    voice_appended = 0
    context_appended = 0

    with corpus_path.open("a", encoding="utf-8") as f:
        for row in list(payload.get("items") or []):
            if str(row.get("source", "")).startswith(("legacy_", "correction_memory", "wrong_answer_memory")):
                continue
            sig = _dataset_row_signature(row)
            if sig in existing_dataset:
                continue
            existing_dataset.add(sig)
            row = dict(row)
            row["schema"] = "ai_subtitle_studio.text_lora_corpus.v1"
            row["signature"] = sig
            row["captured_at"] = _now()
            row["trigger"] = trigger
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            appended += 1

    with bridge_path.open("a", encoding="utf-8") as f:
        for row in list(payload.get("voice_items") or []):
            sig = _voice_bridge_signature(row)
            if sig in existing_voice:
                continue
            existing_voice.add(sig)
            row = dict(row)
            row["signature"] = sig
            row["captured_at"] = _now()
            row["trigger"] = trigger
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            voice_appended += 1

    with context_path.open("a", encoding="utf-8") as f:
        for row in list(payload.get("context_items") or []):
            sig = str(row.get("signature") or _segment_context_signature(row))
            if sig in existing_context:
                continue
            existing_context.add(sig)
            row = dict(_json_safe(row))
            row["signature"] = sig
            row["captured_at"] = _now()
            row["trigger"] = trigger
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            context_appended += 1

    manifest = {
        "schema": "ai_subtitle_studio.personalization_corpus_manifest.v1",
        "updated_at": _now(),
        "text_corpus_path": str(corpus_path),
        "voice_bridge_path": str(bridge_path),
        "multimodal_context_path": str(context_path),
        "last_trigger": trigger,
        "text_total_rows": len(existing_dataset),
        "voice_bridge_total_rows": len(existing_voice),
        "multimodal_context_total_rows": len(existing_context),
        "last_appended_rows": appended,
        "last_voice_bridge_rows": voice_appended,
        "last_multimodal_context_rows": context_appended,
        "notes": [
            "텍스트 LoRA 실사용 코퍼스 자동 누적",
            "목표: STT 후보를 최종 자막으로 검수하는 subtitle QA 교정 LoRA",
            "원문 발화/구어체/고유명사를 보존하고 띄어쓰기·명백한 오탈자·최소 문장부호만 학습",
            "생성 결과 STT 선택본 -> 최종 자막 pair 저장",
            "() / [] / {} 안의 사용자 설명 자막 제외",
            "추후 음성 LoRA 연결용 frame/text/speaker bridge 포함",
            "STT 후보/품질/오디오/VAD/타이밍 context는 multimodal_lora_context에 함께 누적",
        ],
    }
    _write_json_atomic(manifest_path, manifest)
    try:
        refresh_unified_lora_data_bundle(TEXT_LORA_DATASET_DIR, force=True)
    except Exception:
        pass
    maintenance_result = _enqueue_auto_maintenance_jobs(
        trigger=trigger,
        text_total_rows=len(existing_dataset),
        voice_bridge_total_rows=len(existing_voice),
        multimodal_context_total_rows=len(existing_context),
        appended_rows=appended,
        voice_bridge_rows=voice_appended,
        multimodal_context_rows=context_appended,
    )
    return {
        "corpus_path": str(corpus_path),
        "voice_bridge_path": str(bridge_path),
        "manifest_path": str(manifest_path),
        "appended_rows": appended,
        "voice_bridge_rows": voice_appended,
        "multimodal_context_rows": context_appended,
        "total_rows": len(existing_dataset),
        "voice_bridge_total_rows": len(existing_voice),
        "multimodal_context_total_rows": len(existing_context),
        "auto_maintenance": maintenance_result,
    }


__all__ = [
    "TEXT_LORA_DATASET_DIR",
    "TEXT_LORA_DATASET_PATH",
    "TEXT_LORA_MANIFEST_PATH",
    "TEXT_LORA_CORPUS_PATH",
    "TEXT_LORA_CORPUS_MANIFEST_PATH",
    "MULTIMODAL_LORA_CONTEXT_PATH",
    "VOICE_LORA_BRIDGE_PATH",
    "accumulate_personalization_dataset",
    "build_text_lora_dataset",
    "export_text_lora_dataset",
    "load_legacy_corrections",
    "load_project_segment_pairs",
]
