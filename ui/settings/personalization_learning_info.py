from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout

from core.personalization.lora_storage import (
    LORA_PERSONALIZATION_DIR,
    load_unified_lora_data_bundle,
    refresh_lora_personalization_manifest,
    store_paths,
)
from core.personalization.lora_vector_retriever import lora_retrieval_index_summary
from core.personalization.text_lora_dataset import (
    MULTIMODAL_LORA_CONTEXT_PATH,
    TEXT_LORA_CORPUS_MANIFEST_PATH,
    TEXT_LORA_CORPUS_PATH,
    TEXT_LORA_DATASET_PATH,
    TEXT_LORA_MANIFEST_PATH,
)
from core.personalization.text_lora_runner import (
    TEXT_LORA_TRAINING_PLAN_PATH,
    VOICE_LORA_DATASET_MANIFEST_PATH,
    VOICE_LORA_PROFILE_MANIFEST_PATH,
    VOICE_LORA_TRAINING_PLAN_PATH,
)
from core.personalization.stt1_whisper_adapter_runner import (
    STT1_WHISPER_ADAPTER_DATASET_MANIFEST_PATH,
    STT1_WHISPER_ADAPTER_DATASET_PATH,
    STT1_WHISPER_ADAPTER_RUNTIME_MANIFEST_PATH,
    STT1_WHISPER_ADAPTER_TRAINING_PLAN_PATH,
)
from ui.style import button_style, settings_dialog_stylesheet


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


def _compact_button_style(kind: str = "toolbar") -> str:
    if kind == "primary":
        return button_style("primary", font_size="11px", padding="4px 10px") + " QPushButton { min-height: 24px; max-height: 28px; }"
    if kind == "danger":
        return button_style("danger", font_size="10px", padding="3px 8px") + " QPushButton { min-height: 22px; max-height: 26px; }"
    return button_style("toolbar", font_size="10px", padding="3px 8px") + " QPushButton { min-height: 22px; max-height: 26px; }"


def _queue_status_label(status: Any) -> str:
    text = str(status or "waiting")
    return QUEUE_STATUS_LABELS.get(text, text)


def _queue_job_type_label(job_type: Any) -> str:
    text = str(job_type or "-")
    return QUEUE_JOB_TYPE_LABELS.get(text, text)


def lora_learning_help_text() -> str:
    return "\n".join(
        [
            "개인화 학습 고급 메뉴 설명",
            "",
            "기본 사용법",
            "   영상/오디오와 SRT를 함께 넣고 '학습 시작'을 누르면 pair 가져오기, truth table 생성, 규칙 재학습, 코퍼스 갱신, 낮은 점수 정리, LoRA ZIP 갱신을 자동으로 실행합니다.",
            "",
            "학습 제외 규칙",
            "   (), [], {} 안에 있는 자막은 사용자가 추가한 설명으로 간주해 모든 자막 학습 텍스트와 목소리 bridge에서 제외합니다.",
            "",
            "LLM/ChatGPT/Gemini 활용 가능 지점",
            "   LLM은 LoRA adapter 바이너리 자체를 직접 검증하기보다는, 학습 근거 JSON을 보고 '이 규칙이 타당한가', '프롬프트가 더 좋아질 수 있는가', '애매한 괄호/줄바꿈 판단이 있는가'를 검토하는 데 유용합니다.",
            "",
            "수동 검토 워크플로우",
            "   'LLM 검토 JSON 내보내기'로 요청 JSON을 만든 뒤 ChatGPT/Gemini에 붙여 넣고, 반드시 JSON만 반환하게 합니다. 반환된 JSON을 'LLM 결과 JSON 가져오기'로 반영하면 검토된 split/line-break rule, prompt trial, setting 추천이 저장소에 병합됩니다.",
            "",
            "진화형 데이터 정리",
            "   새 개인화 학습이 완료되면 낮은 점수 trial과 낮은 빈도/낮은 confidence 규칙을 조금씩 정리합니다. 작은 데이터셋은 보호하고, 충분히 쌓인 뒤부터 오래되고 낮은 점수인 항목을 먼저 밀어냅니다.",
            "",
            "통합 LoRA 데이터 파일",
            "   lora_data_bundle.zip 하나가 사용자가 관리하는 대표 학습 파일입니다. 내부 JSON/JSONL shard는 빠른 append와 UI 확인을 위한 cache이며, ZIP 파일에서 다시 만들 수 있습니다.",
            "",
            "STT1 Whisper adapter 준비",
            "   ground truth pair와 context를 이용해 STT1 전용 Whisper adapter dataset/plan/runtime manifest를 따로 만듭니다. 검색형 LoRA는 그대로 유지하고, 준비된 adapter 산출물이 있을 때만 STT1 모델로 자동 연결합니다.",
            "",
            "목소리 LoRA 준비",
            "   영상 자막 구간의 화자, 프레임, 텍스트를 이용해 voice_lora_bridge와 voice_lora_training_plan을 만들고, 필요하면 구간별 WAV 음성 클립도 저장합니다. 실제 음성 LoRA는 텍스트 LoRA와 별도 adapter이며, 내 목소리처럼 사용 허가된 화자 음성만 학습 대상으로 삼아야 합니다.",
            "",
            "주의: JSON에는 자막 텍스트와 로컬 파일 경로가 들어갈 수 있습니다. 외부 채팅 서비스에 붙여 넣기 전에 민감한 내용은 제거해 주세요.",
        ]
    )


def _read_json_payload(path: str | Path, default: Any | None = None) -> Any:
    target = Path(path)
    fallback = {} if default is None else default
    if not target.exists():
        return fallback
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _jsonl_count_and_tail(path: str | Path, *, limit: int = 24) -> dict[str, Any]:
    target = Path(path)
    rows: deque[dict[str, Any]] = deque(maxlen=max(0, int(limit)))
    total = 0
    if not target.exists():
        return {"count": 0, "rows": []}
    try:
        with target.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                total += 1
                try:
                    payload = json.loads(line)
                except Exception:
                    payload = {"_raw": preview_text(line, 180)}
                if isinstance(payload, dict):
                    rows.append(payload)
                else:
                    rows.append({"value": payload})
    except Exception:
        return {"count": total, "rows": list(rows)}
    return {"count": total, "rows": list(rows)}


def preview_text(value: Any, limit: int = 120) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _short_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    if text.startswith("smb://"):
        parts = [part for part in text.split("/") if part and part != "smb:"]
        if len(parts) >= 2:
            return "/".join(parts[-2:])
        return text
    path = Path(text)
    parent_name = path.parent.name
    if parent_name:
        return f"{parent_name}/{path.name}"
    return path.name or text


def _format_epoch(epoch: float | int | None) -> str:
    if not epoch:
        return "-"
    try:
        return datetime.fromtimestamp(float(epoch)).isoformat(timespec="seconds")
    except Exception:
        return "-"


def _file_info(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"exists": False, "mtime_epoch": 0.0, "mtime": "-", "size_bytes": 0, "path": str(target)}
    try:
        stat = target.stat()
    except OSError:
        return {"exists": True, "mtime_epoch": 0.0, "mtime": "-", "size_bytes": 0, "path": str(target)}
    return {
        "exists": True,
        "mtime_epoch": float(stat.st_mtime),
        "mtime": _format_epoch(stat.st_mtime),
        "size_bytes": int(stat.st_size),
        "path": str(target),
    }


def format_bytes(value: Any) -> str:
    try:
        size = float(value or 0)
    except Exception:
        return "0 B"
    units = ("B", "KB", "MB", "GB")
    unit = units[0]
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            break
        size /= 1024.0
    if unit == "B":
        return f"{int(size)} B"
    return f"{size:.1f} {unit}"


def _record_time(row: dict[str, Any]) -> str:
    for key in ("captured_at", "updated_at", "created_at", "completed_at", "started_at"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "-"


def _duration_label(row: dict[str, Any]) -> str:
    try:
        start = float(row.get("start_sec", row.get("start", 0.0)) or 0.0)
        end = float(row.get("end_sec", row.get("end", start)) or start)
    except Exception:
        return "-"
    if end <= start:
        return f"{start:.2f}s"
    return f"{start:.2f}-{end:.2f}s"


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"[{title}]", *(lines or ["표시할 항목이 없습니다."]), ""]


def _format_truth_rows(rows: list[dict[str, Any]], *, limit: int = 18) -> list[str]:
    output: list[str] = []
    for row in rows[-limit:]:
        media = _short_path(row.get("media_path") or row.get("project_path") or row.get("clip_path"))
        segment = str(row.get("segment_id") or row.get("segment_index") or "-")
        text = row.get("speech_training_text") or row.get("output") or row.get("text") or row.get("kept_text")
        raw_text = row.get("raw_ground_truth_text") or row.get("input")
        output.append(f"- {_record_time(row)} · {media} · {segment} · {_duration_label(row)}")
        output.append(f"  학습 텍스트: {preview_text(text, 150) or '-'}")
        if raw_text and preview_text(raw_text, 150) != preview_text(text, 150):
            output.append(f"  원본/입력: {preview_text(raw_text, 150)}")
    return output


def _format_voice_rows(rows: list[dict[str, Any]], *, limit: int = 18) -> list[str]:
    output: list[str] = []
    for row in rows[-limit:]:
        clip = _short_path(row.get("clip_path") or row.get("media_path") or row.get("project_path"))
        speaker = str(row.get("speaker") or "unknown")
        text = row.get("text") or row.get("transcript_text") or row.get("speech_training_text") or row.get("input_text")
        output.append(f"- {_record_time(row)} · {clip} · speaker={speaker} · {_duration_label(row)}")
        output.append(f"  voice text: {preview_text(text, 150) or '-'}")
    return output


def _format_excluded_rows(rows: list[dict[str, Any]], *, limit: int = 18) -> list[str]:
    output: list[str] = []
    for row in rows[-limit:]:
        media = _short_path(row.get("media_path") or row.get("subtitle_path"))
        output.append(f"- {_record_time(row)} · {media} · {row.get('segment_id') or '-'}")
        output.append(f"  제외: {preview_text(row.get('excluded_text'), 130) or '-'}")
        output.append(f"  학습 유지: {preview_text(row.get('kept_text'), 130) or '-'}")
        output.append(f"  원본: {preview_text(row.get('original_text'), 150) or '-'}")
    return output


def _format_trial_rows(rows: list[dict[str, Any]], *, limit: int = 12) -> list[str]:
    output: list[str] = []
    for row in rows[-limit:]:
        score = row.get("score", row.get("quality_score", "-"))
        label = row.get("trial_id") or row.get("job_id") or row.get("source") or row.get("task") or "-"
        output.append(f"- {_record_time(row)} · {label} · score={score}")
        preview = row.get("prompt") or row.get("setting") or row.get("summary") or row.get("last_error") or row.get("output")
        if preview:
            output.append(f"  내용: {preview_text(preview, 150)}")
    return output


def _format_multimodal_context_rows(rows: list[dict[str, Any]], *, limit: int = 12) -> list[str]:
    output: list[str] = []
    for row in rows[-limit:]:
        task = row.get("task") or "-"
        source = row.get("source") or "-"
        media = _short_path(row.get("media_path") or row.get("clip_path") or row.get("project_path"))
        output.append(f"- {_record_time(row)} · {task} · {source} · {media}")
        classification = dict(row.get("context_classification") or {})
        if classification:
            scene = dict(classification.get("scene_environment") or {}).get("label", "-")
            topic = dict(classification.get("topic") or {}).get("primary", "-")
            mic = dict(classification.get("microphone_environment") or {})
            output.append(
                f"  분류: 환경={scene} · 주제={topic} · mic={mic.get('mic_type', '-')} · noise={mic.get('noise_level', '-')}"
            )
            noise_sources = ", ".join(str(item) for item in list(mic.get("noise_sources") or [])[:5])
            if noise_sources:
                output.append(f"  노이즈: {noise_sources}")
        if row.get("final_subtitle_text") or row.get("input_text"):
            output.append(f"  입력: {preview_text(row.get('input_text'), 110) or '-'}")
            output.append(f"  최종: {preview_text(row.get('final_subtitle_text'), 110) or '-'}")
        subtitle_profile = dict(row.get("subtitle_profile") or {})
        if subtitle_profile:
            reading = dict(subtitle_profile.get("reading_speed") or {})
            output.append(
                f"  자막: speech {subtitle_profile.get('speech_segments', 0)}개 · avg CPS {reading.get('avg_cps', 0)} · max CPS {reading.get('max_cps', 0)}"
            )
        candidate_context = dict(row.get("candidate_context") or {})
        if candidate_context:
            output.append(
                f"  STT 후보: {candidate_context.get('candidate_count', 0)}개 · 선택 {candidate_context.get('selected_source', '-')}"
            )
    return output


def _format_rule_items(payload: dict[str, Any], *, limit: int = 20) -> list[str]:
    items = [dict(item) for item in list((payload or {}).get("items") or []) if isinstance(item, dict)]
    items.sort(
        key=lambda item: (
            int(item.get("frequency", 0) or 0),
            float(item.get("confidence", 0.0) or 0.0),
            str(item.get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    output: list[str] = []
    for index, item in enumerate(items[:limit], start=1):
        text = item.get("rule_text") or item.get("normalized_text") or item.get("rule_id") or "-"
        frequency = int(item.get("frequency", 0) or 0)
        confidence = float(item.get("confidence", 0.0) or 0.0)
        output.append(f"{index}. {text} · 빈도 {frequency} · 신뢰도 {confidence:.3f}")
        examples = [preview_text(example, 52) for example in list(item.get("examples") or [])[:3]]
        if examples:
            output.append(f"   예시: {' / '.join(examples)}")
    return output


def _queue_detail_lines(queue_payload: dict[str, Any], *, limit: int = 18) -> list[str]:
    items = [dict(item) for item in list((queue_payload or {}).get("items") or []) if isinstance(item, dict)]
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "waiting")
        counts[status] = int(counts.get(status, 0) or 0) + 1
    output = [f"총 작업: {len(items)}개"]
    output.append("상태: " + (" · ".join(f"{_queue_status_label(key)} {value}개" for key, value in sorted(counts.items())) or "없음"))
    recent = sorted(items, key=_record_time, reverse=True)[:limit]
    for item in recent:
        progress = item.get("progress", "-")
        job_type = item.get("job_type") or item.get("task") or "-"
        output.append(f"- {_record_time(item)} · {_queue_job_type_label(job_type)} · {_queue_status_label(item.get('status'))} · progress={progress}")
        checkpoint = dict((dict(item.get("payload") or {}).get("checkpoint") or {}))
        if checkpoint:
            stage = str(checkpoint.get("stage") or "-")
            updated_at = str(checkpoint.get("updated_at") or "-")
            processed = checkpoint.get("processed")
            total = checkpoint.get("total")
            if processed is not None and total is not None:
                output.append(f"  checkpoint: {stage} · {processed}/{total} · {updated_at}")
            else:
                output.append(f"  checkpoint: {stage} · {updated_at}")
        if item.get("last_error"):
            output.append(f"  메모: {preview_text(item.get('last_error'), 150)}")
    return output


def build_learning_info_payload() -> dict[str, str]:
    manifest = refresh_lora_personalization_manifest()
    paths = store_paths(LORA_PERSONALIZATION_DIR)
    text_corpus_manifest = _read_json_payload(TEXT_LORA_CORPUS_MANIFEST_PATH, {})
    text_training_plan = _read_json_payload(TEXT_LORA_TRAINING_PLAN_PATH, {})
    voice_profile_manifest = _read_json_payload(VOICE_LORA_PROFILE_MANIFEST_PATH, {})
    voice_training_plan = _read_json_payload(VOICE_LORA_TRAINING_PLAN_PATH, {})
    voice_dataset_manifest = _read_json_payload(VOICE_LORA_DATASET_MANIFEST_PATH, {})
    split_rules = _read_json_payload(paths["learned_split_rules"], {})
    line_break_rules = _read_json_payload(paths["learned_line_break_rules"], {})
    best_settings = _read_json_payload(paths["best_settings"], {})
    queue_payload = _read_json_payload(paths["training_queue"], {})
    retention_policy = _read_json_payload(paths["retention_policy"], {})
    bundle_payload = load_unified_lora_data_bundle()
    retrieval_summary = lora_retrieval_index_summary()
    llm_request = _read_json_payload(paths["llm_review_request"], {})
    llm_result = _read_json_payload(paths["llm_review_result"], {})

    jsonl_sources = {
        "truth_table": paths["truth_table"],
        "excluded_parentheticals": paths["excluded_parentheticals"],
        "setting_trials": paths["setting_trials"],
        "prompt_trials": paths["prompt_trials"],
        "retention_history": paths["retention_history"],
        "voice_lora_bridge": paths["voice_lora_bridge"],
        "stt1_whisper_adapter_dataset": STT1_WHISPER_ADAPTER_DATASET_PATH,
        "text_lora_dataset": TEXT_LORA_DATASET_PATH,
        "text_lora_corpus": TEXT_LORA_CORPUS_PATH,
        "audio_preset_lora": paths["root"] / "audio_preset_lora.jsonl",
        "multimodal_lora_context": paths["multimodal_lora_context"],
    }
    jsonl = {key: _jsonl_count_and_tail(path) for key, path in jsonl_sources.items()}

    file_sources = {
        "manifest": paths["manifest"],
        "truth_table": paths["truth_table"],
        "excluded_parentheticals": paths["excluded_parentheticals"],
        "text_lora_dataset": TEXT_LORA_DATASET_PATH,
        "text_lora_manifest": TEXT_LORA_MANIFEST_PATH,
        "text_lora_corpus": TEXT_LORA_CORPUS_PATH,
        "text_lora_corpus_manifest": TEXT_LORA_CORPUS_MANIFEST_PATH,
        "text_lora_training_plan": TEXT_LORA_TRAINING_PLAN_PATH,
        "voice_lora_bridge": paths["voice_lora_bridge"],
        "voice_lora_profile_manifest": VOICE_LORA_PROFILE_MANIFEST_PATH,
        "voice_lora_training_plan": VOICE_LORA_TRAINING_PLAN_PATH,
        "voice_lora_dataset_manifest": VOICE_LORA_DATASET_MANIFEST_PATH,
        "stt1_whisper_adapter_dataset": STT1_WHISPER_ADAPTER_DATASET_PATH,
        "stt1_whisper_adapter_dataset_manifest": STT1_WHISPER_ADAPTER_DATASET_MANIFEST_PATH,
        "stt1_whisper_adapter_training_plan": STT1_WHISPER_ADAPTER_TRAINING_PLAN_PATH,
        "stt1_whisper_adapter_runtime_manifest": STT1_WHISPER_ADAPTER_RUNTIME_MANIFEST_PATH,
        "learned_split_rules": paths["learned_split_rules"],
        "learned_line_break_rules": paths["learned_line_break_rules"],
        "setting_trials": paths["setting_trials"],
        "prompt_trials": paths["prompt_trials"],
        "training_queue": paths["training_queue"],
        "best_settings": paths["best_settings"],
        "retention_policy": paths["retention_policy"],
        "retention_history": paths["retention_history"],
        "llm_review_request": paths["llm_review_request"],
        "llm_review_result": paths["llm_review_result"],
        "unified_lora_data": paths["unified_lora_data"],
        "lora_retrieval_index": paths["lora_retrieval_index"],
        "audio_preset_lora": paths["root"] / "audio_preset_lora.jsonl",
        "multimodal_lora_context": MULTIMODAL_LORA_CONTEXT_PATH,
    }
    labels = {
        "manifest": "전체 manifest",
        "truth_table": "ground truth 자막",
        "excluded_parentheticals": "설명 자막 제외 기록",
        "text_lora_dataset": "text LoRA dataset",
        "text_lora_manifest": "text LoRA manifest",
        "text_lora_corpus": "누적 text corpus",
        "text_lora_corpus_manifest": "누적 corpus manifest",
        "text_lora_training_plan": "text 학습 계획",
        "voice_lora_bridge": "목소리 bridge",
        "voice_lora_profile_manifest": "목소리 profile",
        "voice_lora_training_plan": "목소리 학습 계획",
        "voice_lora_dataset_manifest": "목소리 dataset manifest",
        "stt1_whisper_adapter_dataset": "STT1 adapter dataset",
        "stt1_whisper_adapter_dataset_manifest": "STT1 adapter dataset manifest",
        "stt1_whisper_adapter_training_plan": "STT1 adapter 학습 계획",
        "stt1_whisper_adapter_runtime_manifest": "STT1 adapter runtime manifest",
        "learned_split_rules": "split 규칙",
        "learned_line_break_rules": "줄바꿈 규칙",
        "setting_trials": "setting trial",
        "prompt_trials": "prompt trial",
        "training_queue": "대기 작업",
        "best_settings": "추천 설정",
        "retention_policy": "정리 정책",
        "retention_history": "정리 기록",
        "llm_review_request": "LLM 검토 요청",
        "llm_review_result": "LLM 검토 결과",
        "unified_lora_data": "LoRA ZIP 학습 파일",
        "lora_retrieval_index": "LoRA 검색 인덱스",
        "audio_preset_lora": "audio preset LoRA",
        "multimodal_lora_context": "영상/음성/자막 context",
    }
    file_rows = []
    for key, path in file_sources.items():
        info = _file_info(path)
        info["key"] = key
        info["label"] = labels.get(key, key)
        if key in jsonl:
            info["rows"] = int(jsonl[key].get("count", 0) or 0)
        file_rows.append(info)
    file_rows.sort(key=lambda row: float(row.get("mtime_epoch", 0.0) or 0.0), reverse=True)
    data_rows = [row for row in file_rows if row.get("key") not in {"manifest", "unified_lora_data"} and row.get("exists")]
    latest_data = data_rows[0] if data_rows else {}
    latest_any = file_rows[0] if file_rows else {}

    counts = dict(manifest.get("counts") or {})
    voice_stats = dict((voice_training_plan or {}).get("stats") or {})
    text_stats = dict((text_training_plan or {}).get("stats") or {})
    corpus_stats = dict((text_corpus_manifest or {}).get("stats") or {})
    speaker_profiles = list((voice_profile_manifest or {}).get("speaker_profiles") or [])

    summary_lines = [
        "이 화면은 현재 저장된 LoRA 개인화 학습 근거를 읽기 전용으로 보여줍니다.",
        "영상/SRT pair에서 나온 ground truth, 괄호 설명 제외 기록, text/voice LoRA seed, learned rules, queue 상태를 함께 확인할 수 있습니다.",
        "",
        "[최신 상태]",
        f"- 최근 학습 데이터 변경: {latest_data.get('label', '-')} · {latest_data.get('mtime', '-')}",
        f"- 정보 화면 갱신: {latest_any.get('mtime', '-')}",
        f"- manifest updated_at: {manifest.get('updated_at', '-')}",
        f"- LoRA ZIP updated_at: {bundle_payload.get('updated_at', '-')}",
        "",
        "[학습 규모]",
        f"- ground truth: {counts.get('truth_table_rows', 0)}행",
        f"- 학습 제외 설명 자막: {counts.get('excluded_parenthetical_rows', 0)}행",
        f"- split/line-break 규칙: {counts.get('learned_split_rules', 0)}개 / {counts.get('learned_line_break_rules', 0)}개",
        f"- text dataset/corpus: {jsonl['text_lora_dataset']['count']}행 / {jsonl['text_lora_corpus']['count']}행",
        f"- 영상/음성/자막 context: {jsonl['multimodal_lora_context']['count']}행",
        f"- 검색 인덱스: {retrieval_summary.get('doc_count', 0)}개 기억 · {retrieval_summary.get('hash_dim', 0)}차원 · BM25 {retrieval_summary.get('bm25_terms', 0)}토큰",
        f"- 검색 점수 모델: {retrieval_summary.get('score_model', '-')}",
        f"- 목소리 bridge/학습 item: {counts.get('voice_lora_bridge_rows', 0)}구간 / {counts.get('voice_lora_training_items', 0)}개",
        f"- 준비된 음성 클립: {counts.get('voice_lora_stored_audio_items', 0)}개",
        f"- STT1 adapter dataset/item: {counts.get('stt1_whisper_adapter_dataset_rows', 0)}행 / {counts.get('stt1_whisper_adapter_training_items', 0)}개",
        f"- STT1 adapter runtime ready: {'예' if int(counts.get('stt1_whisper_adapter_runtime_ready', 0) or 0) > 0 else '아니오'}",
        f"- 대기 작업: {counts.get('queue_items', 0)}개",
        "",
        "[저장 위치]",
        f"- 루트: {paths['root']}",
        f"- LoRA ZIP 학습 파일: {paths['unified_lora_data']}",
        f"- LoRA 검색 인덱스: {paths['lora_retrieval_index']}",
    ]

    update_lines = ["[파일별 최신 업데이트]"]
    for row in file_rows:
        status = "있음" if row.get("exists") else "없음"
        rows_suffix = f" · {row.get('rows')}행" if "rows" in row else ""
        update_lines.append(f"- {row.get('label')} · {status} · {row.get('mtime')} · {format_bytes(row.get('size_bytes'))}{rows_suffix}")
        update_lines.append(f"  {row.get('path')}")
    update_lines.extend(["", *_section("대기 작업", _queue_detail_lines(queue_payload))])
    update_lines.extend(
        _section(
            "학습 계획",
            [
                f"text backend: {text_training_plan.get('backend', '-')}",
                f"text stats: {json.dumps(text_stats or corpus_stats, ensure_ascii=False)}",
                f"voice backend: {voice_training_plan.get('backend', '-')}",
                f"voice stats: {json.dumps(voice_stats, ensure_ascii=False)}",
                f"voice profiles: {len(speaker_profiles)}명",
                f"voice dataset manifest updated_at: {voice_dataset_manifest.get('updated_at', '-')}",
            ],
        )
    )

    learning_lines: list[str] = []
    learning_lines.extend(_section("최근 ground truth 자막", _format_truth_rows(list(jsonl["truth_table"].get("rows") or []))))
    learning_lines.extend(
        _section(
            "최근 text LoRA dataset/corpus",
            _format_truth_rows(list(jsonl["text_lora_dataset"].get("rows") or []))
            + _format_truth_rows(list(jsonl["text_lora_corpus"].get("rows") or [])),
        )
    )
    learning_lines.extend(_section("최근 목소리 LoRA bridge", _format_voice_rows(list(jsonl["voice_lora_bridge"].get("rows") or []))))
    learning_lines.extend(_section("최근 STT1 adapter dataset", _format_voice_rows(list(jsonl["stt1_whisper_adapter_dataset"].get("rows") or []))))
    learning_lines.extend(
        _section("최근 영상/음성/자막 context", _format_multimodal_context_rows(list(jsonl["multimodal_lora_context"].get("rows") or [])))
    )
    learning_lines.extend(_section("학습된 split 규칙 Top", _format_rule_items(split_rules)))
    learning_lines.extend(_section("학습된 줄바꿈 규칙 Top", _format_rule_items(line_break_rules)))

    review_lines: list[str] = []
    review_lines.extend(_section("괄호/대괄호/중괄호 설명 제외 기록", _format_excluded_rows(list(jsonl["excluded_parentheticals"].get("rows") or []))))
    review_lines.extend(
        _section(
            "setting/prompt trial 최근 기록",
            _format_trial_rows(list(jsonl["setting_trials"].get("rows") or []))
            + _format_trial_rows(list(jsonl["prompt_trials"].get("rows") or [])),
        )
    )
    review_lines.extend(
        _section(
            "정리/검토 상태",
            [
                f"retention enabled: {retention_policy.get('enabled', '-')}",
                f"retention strategy: {retention_policy.get('strategy', '-')}",
                f"retention history rows: {jsonl['retention_history']['count']}행",
                f"best settings updated_at: {best_settings.get('updated_at', '-')}",
                f"retrieval index updated_at: {retrieval_summary.get('updated_at', '-')}",
                f"retrieval index docs: {retrieval_summary.get('doc_count', 0)}개 / kinds: {json.dumps(retrieval_summary.get('kind_counts', {}), ensure_ascii=False)}",
                f"LLM request schema: {llm_request.get('schema', '-')}",
                f"LLM result schema: {llm_result.get('schema', '-')}",
            ],
        )
    )

    header = (
        f"최근 학습 데이터: {latest_data.get('label', '-')} · {latest_data.get('mtime', '-')}  |  "
        f"truth {counts.get('truth_table_rows', 0)}행 · voice {counts.get('voice_lora_bridge_rows', 0)}구간 · "
        f"stt1 {counts.get('stt1_whisper_adapter_training_items', 0)}개"
    )
    return {
        "header": header,
        "summary": "\n".join(summary_lines).strip(),
        "updates": "\n".join(update_lines).strip(),
        "learning": "\n".join(learning_lines).strip(),
        "review": "\n".join(review_lines).strip(),
    }


class PersonalizationLearningInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LoRA 학습 정보")
        self.setMinimumWidth(720)
        self.setMinimumHeight(560)
        self.setStyleSheet(settings_dialog_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("<b style='font-size:15px;'>LoRA 학습 정보</b>")
        layout.addWidget(title)

        self.header_label = QLabel("")
        self.header_label.setWordWrap(True)
        layout.addWidget(self.header_label)

        self.tabs = QTabWidget()
        self.summary_box = self._make_text_box()
        self.updates_box = self._make_text_box()
        self.learning_box = self._make_text_box()
        self.review_box = self._make_text_box()
        self.tabs.addTab(self.summary_box, "요약")
        self.tabs.addTab(self.updates_box, "최근 업데이트")
        self.tabs.addTab(self.learning_box, "학습 내용")
        self.tabs.addTab(self.review_box, "제외/검토")
        layout.addWidget(self.tabs, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        self.btn_refresh = QPushButton("새로고침")
        self.btn_refresh.setStyleSheet(_compact_button_style("toolbar"))
        self.btn_refresh.clicked.connect(self._refresh_info)
        bottom_row.addWidget(self.btn_refresh)

        self.btn_close = QPushButton("닫기")
        self.btn_close.setStyleSheet(_compact_button_style("toolbar"))
        self.btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(self.btn_close)
        layout.addLayout(bottom_row)

        self._refresh_info()

    def _make_text_box(self) -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        box.setMinimumHeight(360)
        return box

    def _refresh_info(self) -> None:
        try:
            payload = build_learning_info_payload()
        except Exception as exc:
            message = f"LoRA 학습 정보를 읽는 중 오류가 발생했습니다.\n{exc}"
            self.header_label.setText("학습 정보를 불러오지 못했습니다.")
            self.summary_box.setPlainText(message)
            self.updates_box.setPlainText(message)
            self.learning_box.setPlainText(message)
            self.review_box.setPlainText(message)
            return

        self.header_label.setText(str(payload.get("header") or ""))
        self.summary_box.setPlainText(str(payload.get("summary") or ""))
        self.updates_box.setPlainText(str(payload.get("updates") or ""))
        self.learning_box.setPlainText(str(payload.get("learning") or ""))
        self.review_box.setPlainText(str(payload.get("review") or ""))
