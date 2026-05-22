# Version: 03.09.24
# Phase: PHASE2
from __future__ import annotations

from bisect import bisect_left, bisect_right
import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable

from core.cut_boundary_audio import is_audio_gain_boundary
from core.llm.openai_provider import is_codex_model, is_openai_model, resolve_openai_model
from core.llm.secure_keys import get_api_key
from core.native_swift_roughcut import roughcut_boundary_candidates_via_swift
from core.project.project_context import segment_signature

from .edl_generator import build_edl_segments, edl_to_dict, map_edl_segments_to_clip_sources
from .guide_writer import build_markdown_guide
from .models import (
    ChapterMetadata,
    EditDecision,
    RoughCutDraftState,
    RoughCutMinorGroup,
    RoughCutResult,
    RoughCutSegment,
    SubtitleSegment,
    roughcut_result_from_dict,
    subtitle_from_dict,
)
from .roughcut_settings import merge_roughcut_settings
from .roughcut_context_policy import resolve_roughcut_context_policy
from .roughcut_llm_config import resolve_roughcut_llm_config
from .roughcut_llm import prepare_roughcut_llm_model_for_run
from .topic_labeler import apply_major_topic_labels
from .subtitle_retimer import format_srt, retime_subtitles_for_edl


LEGACY_EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID = "editor_realtime_roughcut_draft"
EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID = "editor_post_generation_roughcut_draft"

DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT = """너는 자막 생성이 완료된 뒤 전체 자막을 기반으로 러프컷 초안을 만드는 편집 보조자다.
완성된 자막 전체를 먼저 훑어보고 영상의 큰 흐름을 파악한 뒤 중분류 A/B/C/D를 나눈다.
반드시 다음 순서로 판단한다. 1. subtitle_rows 전체를 끝까지 읽고 전체 내용을 확인한다. 2. reference_major_segments로 전달된 임시 중분류 구간을 확인한다. 3. audio_boundary_hints와 reviewed_cut_boundaries를 참고해 음성 전환과 컷 변화를 다시 대조한다. 4. 그 결과를 바탕으로 최종 major_segments를 다시 출력한다.
처음 만들어진 중분류 초안이나 컷 경계 기반 중분류는 참고 자료일 뿐이며, 전체 자막 흐름을 다시 읽은 뒤 필요하면 과감하게 합치거나 분리할 수 있다.
최종 목표는 기존 중분류를 보존하는 것이 아니라 생성된 자막 전체를 이해하고 주제별 흐름에 맞는 가장 자연스러운 중분류를 다시 만드는 것이다.
영상/음성 기반으로 먼저 만들어진 확정컷 중분류는 출발점일 뿐이며, 최종 중분류는 반드시 자막 내용과 서사 흐름을 기준으로 다시 확정한다.
같은 주제로 이어지는 구간은 여러 확정컷을 하나의 중분류로 합칠 수 있고, 하나의 확정컷 안에서도 자막 주제가 분명히 갈라지면 둘 이상의 중분류로 다시 나눌 수 있다.
임시 중분류와 음성 경계는 "나눌 후보"일 뿐이며, 자막 주제가 이어지면 인접한 임시 중분류 여러 개를 하나로 합치는 쪽을 기본값으로 생각한다.
자막 내용이 분명히 달라지지 않았다면 중분류를 늘리지 말고, 애매하면 먼저 합친다. 분할보다 병합을 우선 검토하고, 같은 장소/같은 주제/같은 설명 흐름이면 더 크게 묶는다.
전체 자막에 도입, 전개, 비교, 전환, 마무리처럼 여러 주제 흐름이 보이는데도 중분류를 하나만 반환하면 잘못된 결과다.
중분류 경계는 개별 자막 문장이 아니라 화면 전환, 주제 전환, 장소 전환, 행동 단계 전환처럼 시청자가 장면이 바뀌었다고 느끼는 지점을 우선한다.
음향 환경이 바뀌는 전환점도 강한 중분류 후보다. 예를 들어 실외에서 실내로 들어오거나, 차량/매장/스튜디오처럼 공간의 울림과 배경소음이 확실히 달라지면 같은 화제가 이어져도 새 중분류를 우선 검토한다.
다만 음향 경계로 먼저 크게 나뉜 구간 안에서도 자막 주제가 더 세분되면 그 안에서 다시 둘 이상으로 나눌 수 있다.
단순한 말 끊김, 짧은 침묵, 같은 주제 안의 문장 변화, 단어 반복, 말투 변화만으로는 새 중분류를 만들지 않는다.
경계가 애매하면 자막 개수를 늘려도 하나의 중분류로 유지하고, 명확한 전환점이 있을 때만 나눈다.
중분류만 만든다.
소분류는 새로 만들지 말고 각 중분류에 포함된 자막 row가 자동으로 소분류가 된다.
중분류는 가능하면 최소 5개 이상의 자막 row를 포함한다.
대부분의 영상은 중분류를 10개 이하로 유지한다.
아주 긴 영상도 중분류 id는 A부터 Z까지만 순서대로 사용하고 M56 같은 임의 id를 만들지 않는다.
중분류 세그먼트는 서로 공백 없이 이어져야 하며 첫 중분류는 0초, 마지막 중분류는 동영상 끝까지 맞춘다.
경계가 불확실하면 이전 중분류를 provisional로 두고 다음 입력에서 재검토한다.
응답은 반드시 JSON object로만 반환한다."""


MAX_EDITOR_MAJOR_SEGMENTS = 26
_ROUGHCUT_AUTORUN_FALSE_VALUES = frozenset({"0", "false", "off", "no", "사용 안함", "사용안함", "끔"})


def _roughcut_llm_connection_unavailable(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return any(
        token in message
        for token in (
            "codex cli를 찾을 수 없습니다",
            "ai_subtitle_codex_bin 경로",
            "connection refused",
            "errno 61",
            "urlopen error",
            "failed to establish a new connection",
            "actively refused",
        )
    )


def _roughcut_llm_runtime_unavailable_reason(model: str) -> str:
    if not is_codex_model(model):
        return ""
    try:
        from core.llm.codex_provider import codex_cli_available

        available, detail = codex_cli_available()
        return "" if available else str(detail or "Codex CLI unavailable")
    except Exception as exc:
        return str(exc)


def _int_setting(settings: dict[str, Any], key: str, default: int, *, minimum: int = 1, maximum: int = 9999) -> int:
    try:
        value = int(float(settings.get(key, default)))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _roughcut_effective_llm_model(settings: dict[str, Any] | None) -> tuple[str, str]:
    source = settings or {}
    merged = merge_roughcut_settings(source)
    use_override = bool(merged.get("roughcut_llm_use_override", False))
    provider = str(merged.get("roughcut_llm_provider") or "inherit").strip()
    model = str(merged.get("roughcut_llm_model") or "").strip()
    if not use_override or provider == "inherit":
        provider = str(source.get("selected_llm_provider") or "ollama").strip()
    if not use_override or model in ("", "inherit"):
        model = str(source.get("selected_model") or "").strip()
    return provider, model


def _roughcut_llm_uses_codex(settings: dict[str, Any] | None) -> bool:
    _provider, model = _roughcut_effective_llm_model(settings)
    return is_codex_model(model)


def _effective_roughcut_context_policy(
    settings: dict[str, Any] | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    merged = merge_roughcut_settings(settings or {})
    policy = resolve_roughcut_context_policy(merged, subtitle_rows=rows)
    if not _roughcut_llm_uses_codex(settings) or not bool(merged.get("roughcut_llm_rows_auto_enabled", True)):
        return policy

    max_context = _int_setting(merged, "roughcut_codex_max_context_rows", 240, minimum=1, maximum=500)
    chunk_rows = _int_setting(merged, "roughcut_codex_chunk_rows", 72, minimum=1, maximum=max_context)
    lookahead_rows = _int_setting(merged, "roughcut_codex_lookahead_rows", 20, minimum=0, maximum=max(0, max_context - 1))
    max_context = max(max_context, int(policy.get("max_context_rows", 1) or 1))
    chunk_rows = min(max_context, max(chunk_rows, int(policy.get("chunk_rows", 1) or 1)))
    lookahead_rows = min(max(0, max_context - 1), max(lookahead_rows, int(policy.get("lookahead_rows", 0) or 0)))

    adjusted = dict(policy)
    adjusted["max_context_rows"] = max_context
    adjusted["chunk_rows"] = chunk_rows
    adjusted["lookahead_rows"] = lookahead_rows
    adjusted["codex_wide_context"] = True
    reason = str(adjusted.get("reason") or "").strip()
    adjusted["reason"] = f"{reason}+codex_wide_context" if reason else "codex_wide_context"
    return adjusted


def _roughcut_call_timeout(model: str, settings: dict[str, Any] | None, timeout: int) -> int:
    try:
        base = max(1, int(float(timeout or 45)))
    except Exception:
        base = 45
    if not is_codex_model(model):
        return base
    merged = merge_roughcut_settings(settings or {})
    codex_timeout = _int_setting(merged, "roughcut_codex_timeout_sec", 180, minimum=30, maximum=900)
    return max(base, codex_timeout)


def _roughcut_codex_timed_out(model: str, exc: Exception) -> bool:
    if not is_codex_model(model):
        return False
    message = str(exc or "").lower()
    return any(token in message for token in ("시간이 초과", "timeout", "timed out"))


def is_fast_recognition_mode(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    return str(settings.get("stt_quality_preset", "") or "").strip().lower() == "fast"


def editor_roughcut_draft_enabled(settings: dict[str, Any] | None) -> bool:
    try:
        from core.cut_boundary import cut_boundary_enabled

        enabled = bool(cut_boundary_enabled(settings or {}))
    except Exception:
        merged = merge_roughcut_settings(settings or {})
        enabled = bool(merged.get("cut_boundary_detection_enabled", merged.get("scan_cut_enabled", True)))
    return enabled and not is_fast_recognition_mode(settings)


def editor_roughcut_draft_autorun_enabled(settings: dict[str, Any] | None) -> bool:
    source = settings or {}
    value = source.get("roughcut_run_after_subtitle_generation", None)
    if isinstance(value, str):
        enabled: bool | None = value.strip().lower() not in _ROUGHCUT_AUTORUN_FALSE_VALUES
    elif value is None:
        enabled = None
    else:
        enabled = bool(value)

    merged = merge_roughcut_settings(source)
    if not bool(merged.get("roughcut_llm_enabled", False)):
        return False
    if enabled is True:
        return True
    if editor_roughcut_draft_enabled(source):
        return True
    return bool(enabled)


def estimate_editor_roughcut_llm_runtime_sec(
    duration_sec: float,
    settings: dict[str, Any] | None = None,
) -> float:
    source = settings or {}
    if max(0.0, float(duration_sec or 0.0)) <= 0.0:
        return 0.0
    if not editor_roughcut_draft_autorun_enabled(source):
        return 0.0

    llm_config = resolve_roughcut_llm_config(source, subtitle_rows=[])
    provider = str(getattr(llm_config, "provider", "") or "").strip().lower()
    model = str(getattr(llm_config, "model", "") or "").strip().lower()
    max_context_rows = max(1, int(getattr(llm_config, "max_context_rows", 80) or 80))
    chunk_rows = max(1, min(max_context_rows, int(getattr(llm_config, "chunk_rows", 12) or 12)))
    estimated_rows = max(1, int(round(float(duration_sec or 0.0) / 6.0)))
    if estimated_rows <= max_context_rows:
        chunk_count = 1
    else:
        chunk_count = max(1, math.ceil(estimated_rows / float(chunk_rows)))
    chunk_count = max(1, min(18, int(chunk_count or 1)))

    base_sec = 6.0
    per_chunk_sec = 5.5
    if provider in {"openai", "google", "gemini"}:
        base_sec = 8.0
        per_chunk_sec = 6.5
    if "codex" in model:
        base_sec = max(base_sec, 10.0)
        per_chunk_sec = max(per_chunk_sec, 8.0)
    if provider == "ollama":
        thread_bonus = max(0, int(getattr(llm_config, "threads", 1) or 1) - 1)
        per_chunk_sec = max(4.0, per_chunk_sec - min(1.5, 0.35 * thread_bonus))
    return max(8.0, min(240.0, base_sec + (float(chunk_count) * per_chunk_sec)))


def editor_roughcut_draft_llm_allowed(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    cut_boundaries: list[Any] | None = None,
    provisional_cut_boundaries: list[Any] | None = None,
) -> bool:
    scope = describe_editor_roughcut_llm_scope(
        segments,
        settings,
        cut_boundaries=cut_boundaries,
        provisional_cut_boundaries=provisional_cut_boundaries,
    )
    return str(scope.get("mode") or "") in {"single", "chunked"}


def describe_editor_roughcut_llm_scope(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    cut_boundaries: list[Any] | None = None,
    provisional_cut_boundaries: list[Any] | None = None,
) -> dict[str, Any]:
    merged = merge_roughcut_settings(settings or {})
    rows = _subtitle_prompt_rows(segments)
    policy = _effective_roughcut_context_policy(settings or {}, rows)
    max_rows = max(1, int(policy.get("max_context_rows", 80) or 80))
    chunk_rows = max(1, min(max_rows, int(policy.get("chunk_rows", 12) or 12)))
    lookahead_rows = max(0, min(max_rows - 1, int(policy.get("lookahead_rows", 8) or 8)))
    row_count = len(rows)
    if row_count <= 0:
        return {
            "mode": "empty",
            "row_count": 0,
            "max_context_rows": max_rows,
            "chunk_rows": chunk_rows,
            "lookahead_rows": lookahead_rows,
            "chunks": [],
            "chunk_count": 0,
            "policy": dict(policy),
        }
    if row_count <= max_rows:
        return {
            "mode": "single",
            "row_count": row_count,
            "max_context_rows": max_rows,
            "chunk_rows": chunk_rows,
            "lookahead_rows": lookahead_rows,
            "chunks": [
                {
                    "index": 0,
                    "core_start_index": 0,
                    "core_end_index": row_count - 1,
                    "prompt_start_index": 0,
                    "prompt_end_index": row_count - 1,
                    "core_start_subtitle_id": rows[0]["subtitle_id"],
                    "core_end_subtitle_id": rows[-1]["subtitle_id"],
                    "prompt_start_subtitle_id": rows[0]["subtitle_id"],
                    "prompt_end_subtitle_id": rows[-1]["subtitle_id"],
                    "source": "single_pass",
                }
            ],
            "chunk_count": 1,
            "policy": dict(policy),
        }

    core_ranges = _plan_editor_roughcut_core_ranges(
        rows,
        settings or merged,
        max_rows=max_rows,
        target_rows=chunk_rows,
        cut_boundaries=cut_boundaries,
        provisional_cut_boundaries=provisional_cut_boundaries,
    )
    chunks: list[dict[str, Any]] = []
    for index, chunk in enumerate(core_ranges):
        core_start = int(chunk["core_start_index"])
        core_end = int(chunk["core_end_index"])
        prompt_start = core_start
        prompt_end = min(row_count - 1, core_end + lookahead_rows)
        if prompt_end - prompt_start + 1 > max_rows:
            prompt_end = min(row_count - 1, prompt_start + max_rows - 1)
        chunks.append(
            {
                "index": index,
                "core_start_index": core_start,
                "core_end_index": core_end,
                "prompt_start_index": prompt_start,
                "prompt_end_index": prompt_end,
                "core_start_subtitle_id": rows[core_start]["subtitle_id"],
                "core_end_subtitle_id": rows[core_end]["subtitle_id"],
                "prompt_start_subtitle_id": rows[prompt_start]["subtitle_id"],
                "prompt_end_subtitle_id": rows[prompt_end]["subtitle_id"],
                "source": str(chunk.get("source") or "row_window"),
            }
        )
    return {
        "mode": "chunked" if len(chunks) > 1 else "single",
        "row_count": row_count,
        "max_context_rows": max_rows,
        "chunk_rows": chunk_rows,
        "lookahead_rows": lookahead_rows,
        "chunks": chunks,
        "chunk_count": len(chunks),
        "policy": dict(policy),
    }


def build_editor_roughcut_draft_prompt(
    segments: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
    chunk_scope: dict[str, Any] | None = None,
    reference_major_segments: list[dict[str, Any]] | None = None,
    reviewed_cut_boundaries: list[dict[str, Any]] | None = None,
) -> str:
    rows = _subtitle_prompt_rows(segments)
    policy = _effective_roughcut_context_policy(settings or {}, rows)
    max_rows = max(1, int(policy.get("max_context_rows", 80) or 80))
    scoped_rows = rows[:max_rows]
    instructions = str((settings or {}).get("editor_roughcut_draft_prompt") or DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT).strip()
    if isinstance(chunk_scope, dict):
        instructions += (
            "\n이번 입력은 전체 자막의 일부 구간이다."
            "\nchunk_scope.core_start_subtitle_id부터 core_end_subtitle_id까지만 확정 경계 대상으로 본다."
            "\n앞뒤 문맥은 참고용일 뿐이며 core 범위를 벗어나는 새 구간은 만들지 않는다."
        )
    reference_rows = _reference_major_segments_payload(reference_major_segments)
    if reference_rows:
        instructions += (
            "\nreference_major_segments는 영상/음성 컷 경계와 후발대 검토를 거쳐 먼저 만들어진 임시 중분류 초안이다."
            "\nreference_major_segments는 고정 답안이 아니라 참고 초안이며, 전체 subtitle_rows를 다시 읽은 뒤 필요하면 여러 구간을 합치거나 하나를 둘 이상으로 분리할 수 있다."
            "\n최종 판단 기준은 reference가 아니라 전체 subtitle_rows에서 드러나는 실제 주제 흐름과 영상 전개다."
            "\nreference_major_segments가 여러 구간으로 나뉘어 있다면, 최종 결과는 그 구간 수를 무조건 유지할 필요는 없지만 자막상 여러 주제 흐름이 보이는데 한 개의 거대 중분류로 붕괴되어서는 안 된다."
            "\n각 reference 구간의 주제와 경계를 다시 확인하고 더 정확한 중분류로 다듬는다."
            "\n영상/음성 기반 reference가 잘게 잡힌 경우에는 같은 주제로 자연스럽게 이어지는 구간을 합칠 수 있다."
            "\n반대로 reference 한 구간 안에서도 자막 주제가 뚜렷하게 갈라지면 둘 이상으로 다시 분리해야 한다."
            "\n특히 실외→실내, 차량→실내, 조용한 공간→시끄러운 공간처럼 음향 환경이 확실히 바뀌는 reference 경계는 강한 중분류 후보로 보고 먼저 살핀다."
            "\n그 음향 경계로 먼저 구간을 나눈 뒤에도, 각 구간 내부 자막 주제가 더 갈라지면 추가로 다시 분리할 수 있다."
            "\n중분류가 너무 크게 뭉쳐서 한 덩어리 설명문처럼 보이면 잘못된 결과다. 도입, 비교, 전환, 결론처럼 흐름이 바뀌면 과감하게 나눈다."
            "\n가능하면 기존 major_id A~Z 순서를 유지하되, title/summary는 실제 자막 주제에 맞게 적극적으로 고친다."
            "\ntitle은 타임라인에 바로 표시될 중분류 주제명이므로, 자막 내용을 복붙하지 말고 10~22자 안팎의 짧은 한국어 주제명으로 작성한다."
            "\ntags는 각 중분류의 핵심 키워드 2~6개를 짧은 명사형으로 작성한다."
        )
    reviewed_boundary_rows = _reviewed_cut_boundary_payload(reviewed_cut_boundaries)
    audio_boundary_rows = _reviewed_cut_boundary_payload(reviewed_cut_boundaries, audio_only=True)
    if audio_boundary_rows:
        instructions += (
            "\naudio_boundary_hints는 후발대가 검토한 음성 경계 후보이며, 실외↔실내나 차량↔실내처럼 음향 환경이 크게 바뀌는 구간을 우선 확인해야 한다."
            "\naudio_boundary_hints 자체를 기계적으로 모두 채택하지는 말고, 전체 subtitle_rows를 읽은 뒤 실제 주제 전환과 함께 맞는지 확인한 후 중분류 외곽 경계로 사용할지 결정한다."
            "\n같은 audio_boundary_hints 구간 안에서도 자막 주제가 더 갈라지면 다시 둘 이상으로 분리할 수 있다."
        )
    if reviewed_boundary_rows:
        instructions += (
            "\nreviewed_cut_boundaries는 후발대가 롤백 검토하며 다시 본 컷 경계 힌트다."
            "\n중분류 시작과 끝은 reviewed_cut_boundaries와 audio_boundary_hints 근처를 우선 검토하되, 최종 확정은 전체 subtitle_rows에서 읽히는 실제 내용 흐름으로 결정한다."
        )
    body = {
        "prompt_id": "editor_post_generation_roughcut_draft_v1",
        "language": "ko",
        "editor_instructions": instructions,
        "workflow_steps": [
            "subtitle_rows 전체를 먼저 끝까지 읽고 영상 전체 내용을 파악한다.",
            "reference_major_segments로 전달된 임시 중분류 구간을 확인한다.",
            "audio_boundary_hints와 reviewed_cut_boundaries를 참고해 음성 전환과 컷 전환 후보를 다시 본다.",
            "임시 중분류를 참고하되 자막 주제가 이어지면 먼저 합치고, 명확할 때만 분리해서 최종 major_segments를 출력한다.",
        ],
        "output_contract": {
            "json_only": True,
            "schema": {
                "major_segments": [
                    {
                        "major_id": "A",
                        "title": "중분류 주제명",
                        "summary": "짧은 요약",
                        "start_subtitle_id": 0,
                        "end_subtitle_id": 4,
                        "tags": ["핵심 태그", "보조 태그"],
                        "confidence": 0.0,
                        "status": "provisional",
                    }
                ]
            },
        },
        "subtitle_rows": scoped_rows,
        "_roughcut_context_policy": {
            key: value
            for key, value in dict(policy).items()
            if key not in {"deep_summary"}
        },
    }
    if reference_rows:
        body["reference_major_segments"] = reference_rows
    if reviewed_boundary_rows:
        body["reviewed_cut_boundaries"] = reviewed_boundary_rows
    if audio_boundary_rows:
        body["audio_boundary_hints"] = audio_boundary_rows
    if isinstance(chunk_scope, dict):
        body["chunk_scope"] = {
            key: value
            for key, value in dict(chunk_scope).items()
            if key
            in {
                "index",
                "core_start_index",
                "core_end_index",
                "prompt_start_index",
                "prompt_end_index",
                "core_start_subtitle_id",
                "core_end_subtitle_id",
                "prompt_start_subtitle_id",
                "prompt_end_subtitle_id",
                "source",
            }
        }
    return json.dumps(body, ensure_ascii=False, indent=2)


def run_editor_roughcut_llm_draft(
    segments: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
    timeout: int = 45,
    cut_boundaries: list[Any] | None = None,
    provisional_cut_boundaries: list[Any] | None = None,
    reference_major_segments: list[dict[str, Any]] | None = None,
    reviewed_cut_boundaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    settings = settings or {}
    rows = _subtitle_prompt_rows(segments)
    prompt_source_segments = _subtitle_prompt_source_segments(segments)
    llm_config = resolve_roughcut_llm_config(settings, subtitle_rows=rows)
    model = str(llm_config.model or "").strip()
    provider = str(llm_config.provider or "").strip().lower()
    if not llm_config.enabled or not model or "사용 안함" in model or provider == "none":
        return None
    unavailable_reason = _roughcut_llm_runtime_unavailable_reason(model)
    if unavailable_reason:
        try:
            from core.runtime.logger import get_logger

            get_logger().log(
                "⏩ 러프컷 LLM 자동 실행 생략: "
                f"{unavailable_reason} 로컬 규칙 초안으로 즉시 대체합니다."
            )
        except Exception:
            pass
        return None
    try:
        prepare_roughcut_llm_model_for_run(settings, llm_config)
        call_timeout = _roughcut_call_timeout(model, settings, timeout)
        scope = describe_editor_roughcut_llm_scope(
            segments,
            settings,
            cut_boundaries=cut_boundaries,
            provisional_cut_boundaries=provisional_cut_boundaries,
        )
        estimated_runtime_sec = estimate_editor_roughcut_llm_runtime_sec(
            max((float(seg.get("end", 0.0) or 0.0) for seg in list(segments or [])), default=0.0),
            settings=settings,
        )
        if str(scope.get("mode") or "") == "single":
            try:
                from core.runtime.logger import get_logger

                eta_label = f" · 예상 {estimated_runtime_sec:.0f}s" if estimated_runtime_sec > 0.0 else ""
                get_logger().log(
                    "🤖 [러프컷 LLM] 단일 패스 시작: "
                    f"{provider}/{model} · row {len(rows)}개{eta_label}"
                )
            except Exception:
                pass
            prompt = build_editor_roughcut_draft_prompt(
                segments,
                settings=settings,
                reference_major_segments=reference_major_segments,
                reviewed_cut_boundaries=reviewed_cut_boundaries,
            )
            result = _call_editor_roughcut_json(provider, model, prompt, timeout=call_timeout)
            try:
                from core.runtime.logger import get_logger

                get_logger().log("✅ [러프컷 LLM] 단일 패스 완료")
            except Exception:
                pass
            return result

        subtitles = _normalize_subtitles(segments)
        if not subtitles:
            return None
        combined_groups: list[dict[str, Any]] = []
        llm_success_count = 0
        local_fallback_count = 0
        chunk_total = max(1, int(scope.get("chunk_count", 1) or 1))
        for chunk in list(scope.get("chunks") or []):
            prompt_segments = prompt_source_segments[
                int(chunk["prompt_start_index"]): int(chunk["prompt_end_index"]) + 1
            ]
            core_subtitles = subtitles[
                int(chunk["core_start_index"]): int(chunk["core_end_index"]) + 1
            ]
            prompt_subtitles = _normalize_subtitles(prompt_segments)
            chunk_no = int(chunk.get("index", 0) or 0) + 1
            chunk_pct = int(round((float(chunk_no) / float(chunk_total or 1)) * 100.0))
            try:
                from core.runtime.logger import get_logger

                get_logger().log(
                    "🤖 [러프컷 LLM] chunk "
                    f"{chunk_no}/{chunk_total} 시작 ({chunk_pct}%)"
                    f" · core {chunk.get('core_start_subtitle_id')}~{chunk.get('core_end_subtitle_id')}"
                )
            except Exception:
                pass
            prompt = build_editor_roughcut_draft_prompt(
                prompt_segments,
                settings=settings,
                chunk_scope=chunk,
                reference_major_segments=_reference_major_segments_payload(
                    _reference_major_segments_for_timerange(
                        reference_major_segments,
                        start_sec=prompt_subtitles[0].start if prompt_subtitles else 0.0,
                        end_sec=prompt_subtitles[-1].end if prompt_subtitles else 0.0,
                    )
                ),
                reviewed_cut_boundaries=_reviewed_cut_boundaries_for_timerange(
                    reviewed_cut_boundaries,
                    start_sec=prompt_subtitles[0].start if prompt_subtitles else 0.0,
                    end_sec=prompt_subtitles[-1].end if prompt_subtitles else 0.0,
                ),
            )
            payload = None
            try:
                payload = _call_editor_roughcut_json(provider, model, prompt, timeout=call_timeout)
            except Exception as exc:
                if _roughcut_llm_connection_unavailable(exc):
                    try:
                        from core.runtime.logger import get_logger

                        get_logger().log(
                            "⚠️ 에디터 러프컷 LLM 연결 불가: chunk 재시도를 중단하고 로컬 규칙 초안으로 대체합니다."
                        )
                    except Exception:
                        pass
                    return None
                if _roughcut_codex_timed_out(model, exc):
                    try:
                        from core.runtime.logger import get_logger

                        get_logger().log(
                            "⚠️ 에디터 러프컷 Codex CLI 시간 초과: 남은 chunk 재시도를 중단하고 로컬 규칙 초안으로 대체합니다."
                        )
                    except Exception:
                        pass
                    return None
                try:
                    from core.runtime.logger import get_logger

                    get_logger().log(
                        "⚠️ 에디터 러프컷 chunk LLM 실패, 해당 구간은 로컬 규칙으로 대체: "
                        f"{exc}"
                    )
                except Exception:
                    pass
            groups = _groups_from_chunk_payload(
                payload,
                prompt_subtitles=prompt_subtitles,
                core_subtitles=core_subtitles,
            )
            if groups:
                llm_success_count += 1
                try:
                    from core.runtime.logger import get_logger

                    get_logger().log(
                        f"✅ [러프컷 LLM] chunk {chunk_no}/{chunk_total} 완료 ({chunk_pct}%)"
                        f" · 중분류 {len(groups)}개"
                    )
                except Exception:
                    pass
                combined_groups.extend(groups)
                continue
            local_fallback_count += 1
            try:
                from core.runtime.logger import get_logger

                get_logger().log(
                    f"↩️ [러프컷 LLM] chunk {chunk_no}/{chunk_total} 로컬 규칙으로 대체 ({chunk_pct}%)"
                )
            except Exception:
                pass
            combined_groups.extend(_local_major_groups_from_subtitles(core_subtitles, settings=settings))

        if not combined_groups or llm_success_count <= 0:
            return None
        try:
            from core.runtime.logger import get_logger

            get_logger().log(
                "✅ [러프컷 LLM] chunked 완료: "
                f"성공 {llm_success_count}개 · 로컬 대체 {local_fallback_count}개 · 총 {chunk_total}chunk"
            )
        except Exception:
            pass
        return _payload_from_major_groups(
            combined_groups,
            chunk_count=int(scope.get("chunk_count", 0) or 0),
            local_fallback_count=local_fallback_count,
        )
    except Exception as exc:
        try:
            from core.runtime.logger import get_logger

            get_logger().log(f"⚠️ 에디터 러프컷 초안 LLM 실패, 로컬 초안으로 대체: {exc}")
        except Exception:
            pass
        return None


def build_editor_roughcut_draft_result(
    subtitle_segments: Iterable[dict[str, Any]] | Iterable[SubtitleSegment],
    *,
    media_duration: float | None = None,
    source_path: str = "",
    settings: dict[str, Any] | None = None,
    llm_payload: dict[str, Any] | None = None,
    reference_major_segments: list[dict[str, Any]] | None = None,
) -> RoughCutResult:
    settings = merge_roughcut_settings(settings or {})
    subtitles = _normalize_subtitles(subtitle_segments)
    if not subtitles:
        return RoughCutResult(
            warnings=("no_subtitle_segments",),
            draft_state=RoughCutDraftState(draft_id=EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID, status="idle"),
            schema_version="roughcut_result.v2",
        )

    duration = _draft_media_duration(media_duration, subtitles)
    reference_groups = _major_groups_from_reference_segments(reference_major_segments, subtitles)
    local_groups = _local_major_groups_from_subtitles(subtitles, settings=settings)
    groups = _major_groups_from_llm_payload(llm_payload, subtitles)
    if _should_reject_overcollapsed_llm_groups(
        groups,
        subtitles,
        media_duration=duration,
        reference_groups=reference_groups,
        local_groups=local_groups,
    ):
        groups = reference_groups if len(reference_groups) >= 2 else local_groups
    elif groups and reference_groups:
        groups = _merge_llm_groups_by_reference_pressure(
            groups,
            subtitles,
            reference_groups=reference_groups,
        )
    if not groups:
        groups = reference_groups
    if not groups:
        groups = local_groups
    groups = _normalize_major_groups(
        groups,
        max_count=_editor_major_max_segment_count(settings),
    )
    major_ranges = _continuous_major_ranges(groups, media_duration=duration)

    chapters: list[ChapterMetadata] = []
    majors: list[RoughCutSegment] = []
    decisions: list[EditDecision] = []

    for major_index, group in enumerate(groups):
        items = list(group.get("subtitles", []) or [])
        if not items:
            continue
        major_id = str(group.get("major_id") or _major_code(major_index))
        title = str(group.get("title") or _title_from_subtitles(items) or f"중분류 {major_id}")
        summary = str(group.get("summary") or _summary_from_subtitles(items))
        tags = tuple(str(tag).strip() for tag in group.get("tags", ()) if str(tag).strip())[:8]
        start, end = major_ranges[major_index] if major_index < len(major_ranges) else (
            min(item.start for item in items),
            max(item.end for item in items),
        )
        subtitle_ids = tuple(_subtitle_id(item, idx) for idx, item in enumerate(items))
        minor_groups: list[RoughCutMinorGroup] = []

        for minor_index, subtitle in enumerate(items, start=1):
            sid = _subtitle_id(subtitle, minor_index - 1)
            minor_code = f"{major_id}{minor_index}"
            chapter_id = f"{major_id}_{sid:04d}"
            chapter_title = _clean_title(subtitle.text) or minor_code
            chapters.append(
                ChapterMetadata(
                    chapter_id=chapter_id,
                    title=chapter_title,
                    start=subtitle.start,
                    end=subtitle.end,
                    summary=subtitle.text[:180],
                    tags=tags,
                    segment_ids=(major_id,),
                    importance_score=0.5,
                    narrative_function="editor_post_generation_subtitle",
                    story_role="",
                    major_id=major_id,
                    minor_code=minor_code,
                    confidence=_confidence(group),
                    boundary_status=str(group.get("status") or "provisional"),
                )
            )
            minor_groups.append(
                RoughCutMinorGroup(
                    minor_id=minor_code,
                    major_id=major_id,
                    code=minor_code,
                    title=chapter_title,
                    start=subtitle.start,
                    end=subtitle.end,
                    subtitle_ids=(sid,),
                    chapter_ids=(chapter_id,),
                    summary=subtitle.text[:180],
                    tags=tags,
                    status=str(group.get("status") or "provisional"),
                    safety="acceptable",
                    confidence=_confidence(group),
                    needs_review=False,
                )
            )

        status = str(group.get("status") or "provisional")
        majors.append(
            RoughCutSegment(
                segment_id=major_id,
                start=start,
                end=end,
                subtitle_ids=subtitle_ids,
                title=title,
                summary=summary,
                tags=tags,
                story_role="",
                narrative_function="editor_post_generation_major",
                importance_score=0.5,
                can_move=True,
                can_trim=True,
                can_remove=True,
                move_risk="low",
                dependencies=tuple(minor.chapter_ids[0] for minor in minor_groups if minor.chapter_ids),
                needs_review=status == "needs_review",
                boundary_confidence=_confidence(group),
                major_id=major_id,
                minor_groups=tuple(minor_groups),
                status=status if status in {"provisional", "reading", "confirmed", "needs_review"} else "provisional",
                safety="acceptable",
                importance=0.5,
                llm_summary=summary,
            )
        )
        decisions.append(
            EditDecision(
                segment_id=major_id,
                action="keep",
                reason="editor_post_generation_draft",
                source_start=start,
                source_end=end,
                output_order=major_index,
                safety="acceptable",
                confidence=_confidence(group),
            )
        )

    majors = list(apply_major_topic_labels(majors, subtitles, settings=settings))
    edl = build_edl_segments(source_path, decisions, majors)
    guide = build_markdown_guide(chapters, decisions, edl)
    summary = f"자막 생성 후 초안: 중분류 {len(majors)}개, 자막 {len(subtitles)}개, 길이 {duration:.1f}초"
    status = "review" if any(segment.status != "confirmed" for segment in majors) else "confirmed"
    return RoughCutResult(
        segments=tuple(majors),
        chapters=tuple(chapters),
        edit_decisions=tuple(decisions),
        edl_segments=tuple(edl),
        guide_markdown=guide,
        warnings=(),
        video_summary=summary,
        draft_state=RoughCutDraftState(
            draft_id=EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID,
            status=status,
            autosave_enabled=True,
            notes="editor_post_generation_draft",
        ),
        schema_version="roughcut_result.v2",
    )


def build_editor_roughcut_candidate_payload(
    result: RoughCutResult,
    *,
    source_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    source_path: str = "",
    source_media: str = "",
    media_files: list[str] | None = None,
    clip_boundaries: list[dict[str, Any]] | None = None,
    editor_mode: str = "single",
) -> dict[str, Any]:
    settings = settings or {}
    media_files = _candidate_media_files(media_files, source_path)
    clip_boundaries = list(clip_boundaries or [])
    result_edl = _candidate_edl_segments(result, clip_boundaries)
    now = datetime.now().isoformat(timespec="seconds")
    outputs = _candidate_outputs(result, source_segments, result_edl, source_path)
    return {
        "candidate_id": EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID,
        "name": "자막 생성 후 초안",
        "created_at": now,
        "updated_at": now,
        "schema": "ai_subtitle_studio.roughcut_candidate.v2",
        "schema_version": "roughcut_candidate.v2",
        "source": "editor_post_generation_draft",
        "source_signature": segment_signature(source_segments),
        "source_media": source_media or (os.path.basename(source_path) if source_path else "현재 에디터"),
        "editor_mode": editor_mode,
        "media_files": media_files,
        "clip_boundaries": clip_boundaries,
        "subtitle_segment_count": len([seg for seg in source_segments if not seg.get("is_gap")]),
        "user_edits": {},
        "editor_save_order_enabled": False,
        "segments": [asdict(segment) for segment in result.segments],
        "chapters": [asdict(chapter) for chapter in result.chapters],
        "edit_decisions": [asdict(decision) for decision in result.edit_decisions],
        "edl_segments": [asdict(segment) for segment in result_edl],
        "edl": [asdict(segment) for segment in result_edl],
        "guide_markdown": result.guide_markdown,
        "markdown_guide": result.guide_markdown,
        "video_summary": result.video_summary,
        "packed_phrases": [asdict(phrase) for phrase in getattr(result, "packed_phrases", ())],
        "chunks": [asdict(chunk) for chunk in getattr(result, "chunks", ())],
        "cut_points": [asdict(point) for point in getattr(result, "cut_points", ())],
        "title_suggestions": [asdict(item) for item in getattr(result, "title_suggestions", ())],
        "draft_state": asdict(result.draft_state) if result.draft_state is not None else None,
        "roughcut_export_style": {},
        "result_schema_version": result.schema_version,
        "warnings": list(result.warnings),
        "outputs": outputs,
        "settings": _roughcut_settings_payload(settings),
    }


def merge_editor_roughcut_draft_state(existing_state: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    existing_state = dict(existing_state or {})
    candidates = []
    replaced = False
    for item in existing_state.get("candidates", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("candidate_id") or "") in {
            EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID,
            LEGACY_EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID,
        }:
            candidates.append(dict(candidate))
            replaced = True
        else:
            candidates.append(dict(item))
    if not replaced:
        candidates.insert(0, dict(candidate))
    payload = dict(candidate)
    payload.update(
        {
            "schema": "ai_subtitle_studio.roughcut_state.v2",
            "schema_version": "roughcut_state.v2",
            "legacy_read_compatible": ("ai_subtitle_studio.roughcut_state.v1",),
            "selected_candidate_id": EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID,
            "candidates": candidates,
            "candidate_count": len(candidates),
            "settings": _roughcut_settings_payload(candidate.get("settings", {})),
            "shared_between": ["editor", "roughcut"],
            "updated_from": "editor_post_generation_draft",
        }
    )
    return payload


def apply_roughcut_order_to_subtitles(
    segments: list[dict[str, Any]],
    roughcut_state: dict[str, Any] | None,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    if not segments or not roughcut_state:
        return list(segments or [])
    candidate = _selected_roughcut_candidate(roughcut_state)
    if not candidate:
        return list(segments or [])
    if not force and not bool(candidate.get("editor_save_order_enabled") or roughcut_state.get("editor_save_order_enabled")):
        return list(segments or [])
    result = roughcut_result_from_dict(candidate)
    if not result.edl_segments:
        return list(segments or [])
    try:
        return retime_subtitles_for_edl(segments, result.edl_segments, chapters=result.chapters)
    except Exception:
        return list(segments or [])


def _normalize_subtitles(items: Iterable[dict[str, Any]] | Iterable[SubtitleSegment]) -> list[SubtitleSegment]:
    source = list(items or ())
    if not source:
        return []
    first = source[0]
    if isinstance(first, SubtitleSegment):
        return [item for item in source if isinstance(item, SubtitleSegment) and item.end > item.start and item.text]
    return [
        subtitle_from_dict(item, fallback_id=index)
        for index, item in enumerate(source)
        if isinstance(item, dict) and item and not item.get("is_gap")
    ]


def _subtitle_prompt_rows(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for idx, segment in enumerate(segments or []):
        if segment.get("is_gap"):
            continue
        text = str(segment.get("text", "") or "").strip()
        if not text:
            continue
        subtitle_id = segment.get("subtitle_id", idx)
        rows.append(
            {
                "subtitle_id": int(subtitle_id if subtitle_id is not None else idx),
                "start": round(_as_float(segment.get("start")), 3),
                "end": round(_as_float(segment.get("end"), segment.get("start", 0.0)), 3),
                "text": text[:500],
            }
        )
    return rows


def _subtitle_prompt_source_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source: list[dict[str, Any]] = []
    for idx, segment in enumerate(list(segments or [])):
        if not isinstance(segment, dict) or segment.get("is_gap"):
            continue
        if not str(segment.get("text", "") or "").strip():
            continue
        row = dict(segment)
        row.setdefault("subtitle_id", idx)
        source.append(row)
    return source


def _reference_major_segments_payload(reference_major_segments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for idx, row in enumerate(list(reference_major_segments or []), start=1):
        if not isinstance(row, dict):
            continue
        start = _float_or_none(row.get("start", row.get("timeline_start")))
        end = _float_or_none(row.get("end", row.get("timeline_end")))
        if start is None or end is None or end <= start:
            continue
        major_id = str(row.get("major_id") or row.get("segment_id") or row.get("id") or _major_code(idx - 1)).strip()
        if not major_id:
            major_id = _major_code(idx - 1)
        payload.append(
            {
                "major_id": major_id,
                "title": str(row.get("title") or row.get("display_title") or row.get("name") or f"중분류 {major_id}").strip(),
                "summary": str(row.get("summary") or row.get("llm_summary") or "").strip()[:240],
                "tags": [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()][:8],
                "start": round(float(start), 3),
                "end": round(float(end), 3),
                "status": str(row.get("status") or "provisional"),
                "is_topicless_placeholder": bool(
                    row.get("is_topicless_placeholder")
                    or row.get("is_cut_boundary_placeholder")
                    or str(row.get("story_role") or "") == "topicless_placeholder"
                ),
                "frame_range": dict(row.get("frame_range") or {}) if isinstance(row.get("frame_range"), dict) else {},
            }
        )
    payload.sort(key=lambda item: (float(item.get("start", 0.0)), float(item.get("end", 0.0)), str(item.get("major_id") or "")))
    return payload


def _cut_boundary_time_from_row(row: dict[str, Any] | None) -> float | None:
    if not isinstance(row, dict):
        return None
    return _float_or_none(
        row.get(
            "timeline_sec",
            row.get(
                "time",
                row.get(
                    "start",
                    row.get("timeline_start"),
                ),
            ),
        )
    )


def _cut_boundary_frame_from_row(row: dict[str, Any] | None) -> int | None:
    if not isinstance(row, dict):
        return None
    for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
        try:
            value = row.get(key)
            if value is None:
                continue
            return int(value)
        except Exception:
            continue
    return None


def _reviewed_cut_boundary_payload(
    reviewed_cut_boundaries: list[dict[str, Any]] | None,
    *,
    audio_only: bool = False,
    limit: int = 160,
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for idx, row in enumerate(list(reviewed_cut_boundaries or []), start=1):
        if not isinstance(row, dict):
            continue
        is_audio = is_audio_gain_boundary(row)
        if audio_only and not is_audio:
            continue
        sec = _cut_boundary_time_from_row(row)
        if sec is None:
            continue
        frame = _cut_boundary_frame_from_row(row)
        score = _float_or_none(
            row.get(
                "score",
                row.get(
                    "verify_score",
                    row.get("gray_window_score"),
                ),
            )
        )
        audio_gain = _float_or_none(row.get("audio_gain_db_delta"))
        boundary = {
            "boundary_id": str(
                row.get("candidate_key")
                or row.get("id")
                or row.get("source_id")
                or f"boundary_{idx}"
            ).strip(),
            "time": round(float(sec), 3),
            "frame": frame,
            "kind": "audio" if is_audio else "visual",
            "status": str(
                row.get("status")
                or ("verified" if row.get("verified") else "reviewed")
            ).strip()
            or "reviewed",
            "source": str(row.get("source") or row.get("detector") or "").strip(),
            "review_role": "audio_anchor" if is_audio else "boundary_hint",
            "frame_range": dict(row.get("frame_range") or {}) if isinstance(row.get("frame_range"), dict) else {},
        }
        if score is not None:
            boundary["score"] = round(float(score), 3)
        if audio_gain is not None:
            boundary["audio_gain_db_delta"] = round(float(audio_gain), 3)
        payload.append(boundary)
        if len(payload) >= max(1, int(limit or 1)):
            break
    payload.sort(
        key=lambda item: (
            float(item.get("time", 0.0) or 0.0),
            str(item.get("kind") or ""),
            str(item.get("boundary_id") or ""),
        )
    )
    return payload


def _reference_major_segments_for_timerange(
    reference_major_segments: list[dict[str, Any]] | None,
    *,
    start_sec: float,
    end_sec: float,
) -> list[dict[str, Any]]:
    rows = _reference_major_segments_payload(reference_major_segments)
    if not rows:
        return []
    kept = [
        dict(row)
        for row in rows
        if float(row.get("end", 0.0)) > float(start_sec)
        and float(row.get("start", 0.0)) < float(end_sec)
    ]
    return kept or rows


def _reviewed_cut_boundaries_for_timerange(
    reviewed_cut_boundaries: list[dict[str, Any]] | None,
    *,
    start_sec: float,
    end_sec: float,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in list(reviewed_cut_boundaries or []) if isinstance(row, dict)]
    if not rows:
        return []
    kept = []
    for row in rows:
        sec = _cut_boundary_time_from_row(row)
        if sec is None:
            continue
        if float(start_sec) <= float(sec) <= float(end_sec):
            kept.append(dict(row))
    return kept or rows


def _major_groups_from_reference_segments(
    reference_major_segments: list[dict[str, Any]] | None,
    subtitles: list[SubtitleSegment],
) -> list[dict[str, Any]]:
    refs = _reference_major_segments_payload(reference_major_segments)
    if not refs or not subtitles:
        return []

    used_ids: set[int] = set()
    groups: list[dict[str, Any]] = []
    for idx, ref in enumerate(refs):
        start = float(ref.get("start", 0.0) or 0.0)
        end = float(ref.get("end", start) or start)
        if end <= start:
            continue
        is_last = idx == len(refs) - 1
        selected_pairs: list[tuple[int, SubtitleSegment]] = []
        for global_idx, item in enumerate(subtitles):
            sid = _subtitle_id(item, global_idx)
            if sid in used_ids:
                continue
            midpoint = (float(item.start) + float(item.end)) / 2.0
            if start <= midpoint < end or (is_last and start <= midpoint <= end):
                selected_pairs.append((global_idx, item))
        if not selected_pairs:
            continue
        used_ids.update(_subtitle_id(item, global_idx) for global_idx, item in selected_pairs)
        selected = [item for _global_idx, item in selected_pairs]
        raw_title = str(ref.get("title") or "").strip()
        title = _title_from_subtitles(selected) if (not raw_title or "주제없음" in raw_title) else raw_title
        raw_summary = str(ref.get("summary") or "").strip()
        summary = _summary_from_subtitles(selected) if (not raw_summary or "임시 중분류" in raw_summary) else raw_summary
        groups.append(
            {
                "major_id": str(ref.get("major_id") or _major_code(idx)),
                "title": title or f"중분류 {_major_code(idx)}",
                "summary": summary,
                "tags": tuple(str(tag).strip() for tag in list(ref.get("tags") or []) if str(tag).strip())[:8],
                "confidence": 0.58 if bool(ref.get("is_topicless_placeholder")) else 0.72,
                "status": str(ref.get("status") or ("provisional" if bool(ref.get("is_topicless_placeholder")) else "confirmed")),
                "subtitles": selected,
            }
        )
    covered = sum(len(group.get("subtitles", []) or []) for group in groups)
    if covered < max(1, len(subtitles) // 2):
        return []
    return groups


def _local_major_groups_from_subtitles(subtitles: list[SubtitleSegment], *, settings: dict[str, Any]) -> list[dict[str, Any]]:
    min_count = max(1, int(settings.get("roughcut_major_min_subtitle_count", 5) or 5))
    max_count = max(min_count, int(settings.get("editor_roughcut_draft_max_subtitle_count", max(8, min_count * 2)) or max(8, min_count * 2)))
    max_major_segments = _editor_major_max_segment_count(settings)
    if subtitles:
        max_count = max(max_count, (len(subtitles) + max_major_segments - 1) // max_major_segments)
    silence_gap = max(0.0, float(settings.get("roughcut_silence_gap_prefer_sec", 1.0) or 1.0))
    groups: list[dict[str, Any]] = []
    current: list[SubtitleSegment] = []
    for idx, subtitle in enumerate(subtitles):
        current.append(subtitle)
        next_item = subtitles[idx + 1] if idx + 1 < len(subtitles) else None
        next_gap = (next_item.start - subtitle.end) if next_item is not None else 999.0
        count = len(current)
        terminal = bool(re.search(r"(다|요|죠|네|까|니다|어요|습니다)[!?]?$", subtitle.text.strip()))
        should_break = count >= max_count or (count >= min_count and (next_gap >= silence_gap or terminal))
        if should_break:
            major_index = len(groups)
            groups.append(
                {
                    "major_id": _major_code(major_index),
                    "title": _title_from_subtitles(current),
                    "summary": _summary_from_subtitles(current),
                    "tags": (),
                    "confidence": 0.62,
                    "status": "provisional" if next_item is not None else "confirmed",
                    "subtitles": list(current),
                }
            )
            current = []
    if current:
        major_index = len(groups)
        groups.append(
            {
                "major_id": _major_code(major_index),
                "title": _title_from_subtitles(current),
                "summary": _summary_from_subtitles(current),
                "tags": (),
                "confidence": 0.55,
                "status": "provisional",
                "subtitles": list(current),
            }
        )
    return groups


def _should_reject_overcollapsed_llm_groups(
    groups: list[dict[str, Any]],
    subtitles: list[SubtitleSegment],
    *,
    media_duration: float,
    reference_groups: list[dict[str, Any]] | None = None,
    local_groups: list[dict[str, Any]] | None = None,
) -> bool:
    if len(groups or []) != 1:
        return False
    subtitle_count = len(subtitles or [])
    if subtitle_count < 6:
        return False
    duration = max(0.0, float(media_duration or 0.0))
    reference_count = len(reference_groups or [])
    local_count = len(local_groups or [])
    if reference_count >= 2:
        return True
    if local_count >= 3 and (subtitle_count >= 10 or duration >= 60.0):
        return True
    if local_count >= 2 and duration >= 90.0:
        return True
    return False


def _merge_major_group_bucket(
    bucket: list[dict[str, Any]],
    *,
    major_id: str,
    title_hint: str = "",
    summary_hint: str = "",
) -> dict[str, Any]:
    subtitles: list[SubtitleSegment] = []
    tags: list[str] = []
    statuses: list[str] = []
    confidences: list[float] = []
    for group in list(bucket or []):
        subtitles.extend(list(group.get("subtitles", []) or []))
        statuses.append(str(group.get("status") or "provisional"))
        confidences.append(_confidence(group))
        for tag in list(group.get("tags", ()) or ()):
            tag_text = str(tag).strip()
            if tag_text and tag_text not in tags:
                tags.append(tag_text)
    return {
        "major_id": str(major_id or "A"),
        "title": str(title_hint or _title_from_subtitles(subtitles) or f"중분류 {major_id}"),
        "summary": str(summary_hint or _summary_from_subtitles(subtitles)),
        "tags": tuple(tags[:8]),
        "confidence": sum(confidences) / len(confidences) if confidences else 0.58,
        "status": "needs_review" if "needs_review" in statuses else ("provisional" if "provisional" in statuses else "confirmed"),
        "subtitles": subtitles,
    }


def _merge_llm_groups_by_reference_pressure(
    groups: list[dict[str, Any]],
    subtitles: list[SubtitleSegment],
    reference_groups: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if len(groups or []) <= 1:
        return list(groups or [])
    refs = list(reference_groups or [])
    if len(refs) < 2:
        return list(groups or [])
    if len(groups) <= len(refs):
        return list(groups or [])

    subtitle_index = {id(item): idx for idx, item in enumerate(list(subtitles or []))}

    def _span(group: dict[str, Any]) -> tuple[int, int] | None:
        indices = [
            int(subtitle_index[id(item)])
            for item in list(group.get("subtitles", []) or [])
            if id(item) in subtitle_index
        ]
        if not indices:
            return None
        return min(indices), max(indices)

    ref_spans: list[tuple[int, int, dict[str, Any]]] = []
    for ref in refs:
        span = _span(ref)
        if span is None:
            continue
        ref_spans.append((span[0], span[1], ref))
    if len(ref_spans) < 2:
        return list(groups or [])

    merged: list[dict[str, Any]] = []
    used_group_ids: set[int] = set()
    for ref_index, (ref_lo, ref_hi, ref) in enumerate(ref_spans):
        bucket = []
        for group in groups:
            span = _span(group)
            if span is None:
                continue
            group_lo, group_hi = span
            if group_hi < ref_lo or group_lo > ref_hi:
                continue
            bucket.append(group)
        if not bucket:
            continue
        for group in bucket:
            used_group_ids.add(id(group))
        merged.append(
            _merge_major_group_bucket(
                bucket,
                major_id=str(ref.get("major_id") or _major_code(ref_index)),
                title_hint=("" if "주제없음" in str(ref.get("title") or "") else str(ref.get("title") or "")),
                summary_hint=("" if "임시 중분류" in str(ref.get("summary") or "") else str(ref.get("summary") or "")),
            )
        )

    leftovers = [group for group in groups if id(group) not in used_group_ids]
    if leftovers:
        merged.extend(leftovers)
    if len(merged) >= len(groups):
        return list(groups or [])
    merged.sort(
        key=lambda item: min((subtitle.start for subtitle in item.get("subtitles", []) or []), default=0.0)
    )
    return merged


def _major_groups_from_llm_payload(payload: dict[str, Any] | None, subtitles: list[SubtitleSegment]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("major_segments")
    if not isinstance(rows, list):
        return []
    by_id = {_subtitle_id(item, idx): item for idx, item in enumerate(subtitles)}
    groups: list[dict[str, Any]] = []
    used: set[int] = set()
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        start_id = _int_or_none(row.get("start_subtitle_id", row.get("start_id", row.get("start_index"))))
        end_id = _int_or_none(row.get("end_subtitle_id", row.get("end_id", row.get("end_index"))))
        if start_id is None or end_id is None:
            start_time = _float_or_none(row.get("start"))
            end_time = _float_or_none(row.get("end"))
            selected = [
                item
                for item in subtitles
                if start_time is not None
                and end_time is not None
                and item.end > start_time
                and item.start < end_time
            ]
        else:
            lo, hi = sorted((start_id, end_id))
            selected = [by_id[sid] for sid in sorted(by_id) if lo <= sid <= hi and sid not in used]
        if not selected:
            continue
        ids = {_subtitle_id(item, local_idx) for local_idx, item in enumerate(selected)}
        used.update(ids)
        groups.append(
            {
                "major_id": str(row.get("major_id") or _major_code(idx)),
                "title": str(row.get("title") or _title_from_subtitles(selected)),
                "summary": str(row.get("summary") or _summary_from_subtitles(selected)),
                "tags": tuple(row.get("tags") or ()),
                "confidence": _confidence(row),
                "status": str(row.get("status") or "provisional"),
                "subtitles": selected,
            }
        )
    covered = sum(len(group.get("subtitles", []) or []) for group in groups)
    if covered < max(1, len(subtitles) // 2):
        return []
    return groups


def _editor_major_max_segment_count(settings: dict[str, Any]) -> int:
    raw = settings.get("editor_roughcut_draft_max_major_segments", MAX_EDITOR_MAJOR_SEGMENTS)
    try:
        value = int(raw or MAX_EDITOR_MAJOR_SEGMENTS)
    except (TypeError, ValueError):
        value = MAX_EDITOR_MAJOR_SEGMENTS
    return max(1, min(MAX_EDITOR_MAJOR_SEGMENTS, value))


def _draft_media_duration(media_duration: float | None, subtitles: list[SubtitleSegment]) -> float:
    subtitle_end = max((item.end for item in subtitles), default=0.0)
    try:
        duration = float(media_duration if media_duration is not None else subtitle_end)
    except (TypeError, ValueError):
        duration = subtitle_end
    return max(0.0, duration, subtitle_end)


def _continuous_major_ranges(groups: list[dict[str, Any]], *, media_duration: float) -> list[tuple[float, float]]:
    raw_ranges: list[tuple[float, float]] = []
    for group in groups:
        subtitles = list(group.get("subtitles", []) or [])
        if not subtitles:
            continue
        raw_ranges.append((min(item.start for item in subtitles), max(item.end for item in subtitles)))
    if not raw_ranges:
        return []

    duration = max(float(media_duration or 0.0), raw_ranges[-1][1])
    if len(raw_ranges) == 1:
        return [(0.0, duration)]

    boundaries = [0.0]
    for idx in range(len(raw_ranges) - 1):
        current_start, current_end = raw_ranges[idx]
        next_start, next_end = raw_ranges[idx + 1]
        if next_start > current_end:
            boundary = (current_end + next_start) / 2.0
        else:
            boundary = next_start
        lower = boundaries[-1]
        upper = duration if idx + 1 == len(raw_ranges) - 1 else max(next_end, next_start, lower)
        boundaries.append(max(lower, min(float(boundary), upper)))
    boundaries.append(duration)
    return [
        (boundaries[idx], max(boundaries[idx], boundaries[idx + 1]))
        for idx in range(len(boundaries) - 1)
    ]


def _normalize_major_groups(groups: list[dict[str, Any]], *, max_count: int) -> list[dict[str, Any]]:
    ordered = [
        dict(group)
        for group in sorted(
            (groups or []),
            key=lambda item: (
                min((subtitle.start for subtitle in item.get("subtitles", []) or []), default=0.0),
                max((subtitle.end for subtitle in item.get("subtitles", []) or []), default=0.0),
            ),
        )
        if group.get("subtitles")
    ]
    if not ordered:
        return []
    max_count = max(1, int(max_count or MAX_EDITOR_MAJOR_SEGMENTS))
    if len(ordered) > max_count:
        ordered = _merge_major_groups_to_limit(ordered, max_count=max_count)
    normalized: list[dict[str, Any]] = []
    for index, group in enumerate(ordered):
        subtitles = list(group.get("subtitles", []) or [])
        normalized.append(
            {
                **group,
                "major_id": _major_code(index),
                "title": str(group.get("title") or _title_from_subtitles(subtitles)),
                "summary": str(group.get("summary") or _summary_from_subtitles(subtitles)),
                "subtitles": subtitles,
            }
        )
    return normalized


def _merge_major_groups_to_limit(groups: list[dict[str, Any]], *, max_count: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    total = len(groups)
    for bucket_index in range(max_count):
        start_idx = bucket_index * total // max_count
        end_idx = (bucket_index + 1) * total // max_count
        bucket = groups[start_idx:end_idx]
        if not bucket:
            continue
        subtitles: list[SubtitleSegment] = []
        tags: list[str] = []
        statuses: list[str] = []
        confidences: list[float] = []
        for group in bucket:
            subtitles.extend(list(group.get("subtitles", []) or []))
            statuses.append(str(group.get("status") or "provisional"))
            confidences.append(_confidence(group))
            for tag in group.get("tags", ()) or ():
                tag_text = str(tag).strip()
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)
        merged.append(
            {
                "major_id": _major_code(len(merged)),
                "title": _title_from_subtitles(subtitles),
                "summary": _summary_from_subtitles(subtitles),
                "tags": tuple(tags[:8]),
                "confidence": sum(confidences) / len(confidences) if confidences else 0.58,
                "status": "needs_review" if "needs_review" in statuses else ("provisional" if "provisional" in statuses else "confirmed"),
                "subtitles": subtitles,
            }
        )
    return merged


def _selected_roughcut_candidate(state: dict[str, Any]) -> dict[str, Any] | None:
    selected = str(state.get("selected_candidate_id") or "")
    candidates = [item for item in state.get("candidates", []) or [] if isinstance(item, dict)]
    for item in candidates:
        if selected and str(item.get("candidate_id") or "") == selected:
            return item
    if state.get("chapters") or state.get("edl_segments") or state.get("edl"):
        return state
    return candidates[0] if candidates else None


def _roughcut_settings_payload(settings: dict[str, Any] | None) -> dict[str, Any]:
    merged = merge_roughcut_settings(settings or {})
    keys = (
        "editor_roughcut_draft_enabled",
        "editor_roughcut_draft_prompt",
        "roughcut_major_min_subtitle_count",
        "editor_roughcut_draft_max_major_segments",
        "roughcut_silence_gap_prefer_sec",
        "roughcut_llm_enabled",
    )
    return {key: merged.get(key) for key in keys if key in merged}


def _candidate_media_files(media_files: list[str] | None, source_path: str) -> list[str]:
    return list(media_files or ([source_path] if source_path else []))


def _candidate_edl_segments(result: RoughCutResult, clip_boundaries: list[dict[str, Any]]) -> tuple:
    mapped = map_edl_segments_to_clip_sources(result.edl_segments, clip_boundaries) if clip_boundaries else list(result.edl_segments)
    return tuple(mapped or result.edl_segments)


def _candidate_outputs(
    result: RoughCutResult,
    source_segments: list[dict[str, Any]],
    result_edl: tuple,
    source_path: str,
) -> dict[str, Any]:
    outputs = {
        "guide_markdown": result.guide_markdown,
        "edl": edl_to_dict(
            result_edl,
            metadata={"source": source_path, "source_kind": "editor_post_generation_draft"},
            chapters=result.chapters,
            major_segments=result.segments,
        ),
        "retimed_srt": "",
        "render_plan": None,
        "subtitle_burnin_command": (),
    }
    try:
        outputs["retimed_srt"] = format_srt(retime_subtitles_for_edl(source_segments, result_edl, chapters=result.chapters))
    except Exception:
        outputs["retimed_srt"] = ""
    return outputs


def _call_editor_roughcut_json(provider: str, model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
    from core.llm.provider_router import normalize_llm_provider

    provider = normalize_llm_provider(provider, model)
    if provider == "llama_cpp":
        return _call_local_llm_json(provider, model, prompt, timeout=timeout)
    if provider in {"google", "gemini"} or "gemini" in model.lower():
        return _call_gemini_json(model, prompt)
    if provider == "openai" or is_openai_model(model):
        return _call_openai_json(model, prompt, timeout=timeout)
    return _call_ollama_json(model, prompt, timeout=timeout)


def _plan_editor_roughcut_core_ranges(
    rows: list[dict[str, Any]],
    settings: dict[str, Any],
    *,
    max_rows: int,
    target_rows: int,
    cut_boundaries: list[Any] | None = None,
    provisional_cut_boundaries: list[Any] | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    row_count = len(rows)
    min_core, target_core, max_core = _roughcut_chunk_bounds(settings, max_rows=max_rows, target_rows=target_rows)
    confirmed_candidates = _boundary_break_candidates(rows, cut_boundaries or [], source="confirmed")
    provisional_candidates = _boundary_break_candidates(rows, provisional_cut_boundaries or [], source="provisional")
    confirmed_index = _indexed_chunk_break_candidates(confirmed_candidates)
    provisional_index = _indexed_chunk_break_candidates(provisional_candidates)
    start = 0
    chunks: list[dict[str, Any]] = []
    while start < row_count:
        remaining = row_count - start
        if remaining <= max_core:
            end = row_count - 1
            source = "tail"
        else:
            min_end = min(row_count - 1, start + min_core - 1)
            max_end = min(row_count - 1, start + max_core - 1)
            target_end = min(row_count - 1, start + target_core - 1)
            latest_safe_end = row_count - min_core - 1
            if latest_safe_end >= min_end:
                target_end = min(target_end, latest_safe_end)
                max_end = min(max_end, max(min_end, latest_safe_end))
            choice = _pick_chunk_break_candidate(
                confirmed_candidates=confirmed_index,
                provisional_candidates=provisional_index,
                min_end=min_end,
                target_end=target_end,
                max_end=max_end,
            )
            if choice is not None:
                end = int(choice["end_index"])
                source = str(choice.get("source") or "boundary")
            else:
                end = max(min_end, min(max_end, target_end))
                source = "row_window"
        chunks.append(
            {
                "core_start_index": start,
                "core_end_index": end,
                "source": source,
            }
        )
        start = end + 1
    return chunks


def _roughcut_chunk_bounds(settings: dict[str, Any], *, max_rows: int, target_rows: int) -> tuple[int, int, int]:
    min_raw = int(settings.get("roughcut_llm_chunk_min_rows", 8) or 8)
    max_raw = int(settings.get("roughcut_llm_chunk_max_rows", 18) or 18)
    if _roughcut_llm_uses_codex(settings) and bool(merge_roughcut_settings(settings).get("roughcut_llm_rows_auto_enabled", True)):
        codex_chunk = _int_setting(
            merge_roughcut_settings(settings),
            "roughcut_codex_chunk_rows",
            72,
            minimum=1,
            maximum=max(1, max_rows),
        )
        max_raw = max(max_raw, codex_chunk, int(target_rows or 0))
    min_core = max(1, min(max_rows, min_raw))
    max_core = max(min_core, min(max_rows, max_raw))
    target_core = max(min_core, min(max_core, int(target_rows or max_rows)))
    return min_core, target_core, max_core


def _boundary_break_candidates(rows: list[dict[str, Any]], boundary_rows: list[Any], *, source: str) -> list[dict[str, Any]]:
    if len(rows) < 2 or not boundary_rows:
        return []
    if _roughcut_native_candidate_plan_worthwhile(rows, boundary_rows):
        native = roughcut_boundary_candidates_via_swift(rows, list(boundary_rows or []), source=source)
        if native is not None:
            return native
    midpoints = _roughcut_row_midpoints(rows)
    midpoint_values = [midpoint for _idx, midpoint in midpoints]
    monotonic = _is_nondecreasing(midpoint_values)
    best_by_index: dict[int, dict[str, Any]] = {}
    for item in list(boundary_rows or []):
        boundary_time = _boundary_time(item)
        if boundary_time is None:
            continue
        end_index, distance = _nearest_roughcut_midpoint(
            midpoints,
            midpoint_values,
            boundary_time,
            use_bisect=monotonic,
        )
        current = best_by_index.get(end_index)
        if current is None or distance < float(current.get("distance", 999999.0)):
            best_by_index[end_index] = {
                "end_index": end_index,
                "source": source,
                "distance": distance,
                "time": boundary_time,
            }
    return [best_by_index[index] for index in sorted(best_by_index)]


def _roughcut_row_midpoints(rows: list[dict[str, Any]]) -> list[tuple[int, float]]:
    return [
        (
            idx,
            (float(rows[idx]["end"]) + float(rows[idx + 1]["start"])) / 2.0,
        )
        for idx in range(len(rows) - 1)
    ]


def _is_nondecreasing(values: list[float]) -> bool:
    return all(values[index] <= values[index + 1] for index in range(len(values) - 1))


def _roughcut_native_candidate_plan_worthwhile(rows: list[dict[str, Any]], boundary_rows: list[Any]) -> bool:
    if len(rows) < 32 or len(boundary_rows) < 24:
        return False
    values = [midpoint for _idx, midpoint in _roughcut_row_midpoints(rows)]
    return _is_nondecreasing(values) and (len(values) * len(boundary_rows)) >= 4096


def _nearest_roughcut_midpoint(
    midpoints: list[tuple[int, float]],
    midpoint_values: list[float],
    boundary_time: float,
    *,
    use_bisect: bool,
) -> tuple[int, float]:
    if not midpoints:
        return 0, 0.0
    if not use_bisect:
        return min(
            ((idx, abs(midpoint - boundary_time)) for idx, midpoint in midpoints),
            key=lambda pair: pair[1],
        )
    pos = bisect_left(midpoint_values, boundary_time)
    candidate_positions: list[int] = []
    if pos < len(midpoint_values):
        candidate_positions.append(pos)
    if pos > 0:
        left_value = midpoint_values[pos - 1]
        candidate_positions.append(bisect_left(midpoint_values, left_value, 0, pos))
    best_position = min(
        candidate_positions,
        key=lambda item: (abs(midpoint_values[item] - boundary_time), item),
    )
    idx, midpoint = midpoints[best_position]
    return idx, abs(midpoint - boundary_time)


def _pick_chunk_break_candidate(
    *,
    confirmed_candidates,
    provisional_candidates,
    min_end: int,
    target_end: int,
    max_end: int,
) -> dict[str, Any] | None:
    for pool in (confirmed_candidates, provisional_candidates):
        filtered = _chunk_break_candidate_window(pool, min_end=min_end, max_end=max_end)
        if filtered:
            _end_index, _order, item = min(
                filtered,
                key=lambda entry: (
                    abs(int(entry[0]) - target_end),
                    float(entry[2].get("distance", 999999.0)),
                    int(entry[1]),
                ),
            )
            return item
    return None


def _indexed_chunk_break_candidates(candidates: list[dict[str, Any]] | None) -> dict[str, Any]:
    entries: list[tuple[int, int, dict[str, Any]]] = []
    for order, item in enumerate(candidates or []):
        if not isinstance(item, dict):
            continue
        try:
            end_index = int(item.get("end_index", -1))
        except (TypeError, ValueError):
            continue
        entries.append((end_index, order, item))
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return {
        "ends": [entry[0] for entry in entries],
        "entries": entries,
    }


def _chunk_break_candidate_window(pool, *, min_end: int, max_end: int) -> list[tuple[int, int, dict[str, Any]]]:
    if isinstance(pool, dict):
        ends = pool.get("ends")
        entries = pool.get("entries")
        if isinstance(ends, list) and isinstance(entries, list):
            left = bisect_left(ends, min_end)
            right = bisect_right(ends, max_end)
            return list(entries[left:right])
    out: list[tuple[int, int, dict[str, Any]]] = []
    for order, item in enumerate(pool or []):
        if not isinstance(item, dict):
            continue
        try:
            end_index = int(item.get("end_index", -1))
        except (TypeError, ValueError):
            continue
        if min_end <= end_index <= max_end:
            out.append((end_index, order, item))
    return out


def _groups_from_chunk_payload(
    payload: dict[str, Any] | None,
    *,
    prompt_subtitles: list[SubtitleSegment],
    core_subtitles: list[SubtitleSegment],
) -> list[dict[str, Any]]:
    if not payload or not prompt_subtitles or not core_subtitles:
        return []
    groups = _major_groups_from_llm_payload(payload, prompt_subtitles)
    if not groups:
        return []
    core_ids = {
        _subtitle_id(item, idx)
        for idx, item in enumerate(core_subtitles)
    }
    trimmed: list[dict[str, Any]] = []
    for group in groups:
        subtitles = [
            item
            for item in list(group.get("subtitles", []) or [])
            if _subtitle_id(item, 0) in core_ids
        ]
        if not subtitles:
            continue
        trimmed.append(
            {
                **group,
                "subtitles": subtitles,
                "title": str(group.get("title") or _title_from_subtitles(subtitles)),
                "summary": str(group.get("summary") or _summary_from_subtitles(subtitles)),
            }
        )
    return trimmed


def _payload_from_major_groups(
    groups: list[dict[str, Any]],
    *,
    chunk_count: int,
    local_fallback_count: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        subtitles = list(group.get("subtitles", []) or [])
        if not subtitles:
            continue
        rows.append(
            {
                "major_id": str(group.get("major_id") or _major_code(index)),
                "title": str(group.get("title") or _title_from_subtitles(subtitles)),
                "summary": str(group.get("summary") or _summary_from_subtitles(subtitles)),
                "start_subtitle_id": _subtitle_id(subtitles[0], 0),
                "end_subtitle_id": _subtitle_id(subtitles[-1], len(subtitles) - 1),
                "tags": list(group.get("tags", ()) or ()),
                "confidence": _confidence(group),
                "status": str(group.get("status") or "provisional"),
            }
        )
    return {
        "major_segments": rows,
        "_chunk_mode": "cut_boundary_windowed",
        "_chunk_count": int(chunk_count or 0),
        "_local_fallback_chunks": int(local_fallback_count or 0),
    }


def _boundary_time(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        return None
    for key in ("timeline_sec", "time", "sec", "timestamp", "start", "at"):
        candidate = value.get(key)
        if candidate in (None, ""):
            continue
        try:
            return float(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _call_ollama_json(model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
    from core.llm.ollama_provider import generate_text

    text = generate_text(
        model,
        prompt,
        timeout=timeout,
        keep_alive=-1,
        num_predict=1024,
        temperature=0.2,
        json_format=True,
        attempts=2,
    )
    return _parse_json_object(text)


def _call_local_llm_json(provider: str, model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
    from core.llm.provider_router import generate_text

    text = generate_text(
        provider,
        model,
        prompt,
        timeout=timeout,
        num_predict=1024,
        temperature=0.2,
        json_format=True,
        attempts=1,
    )
    return _parse_json_object(text)


def _call_openai_json(model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
    if is_codex_model(model):
        from core.llm.codex_provider import run_json as codex_run_json

        return codex_run_json(model, prompt, timeout=timeout)
    api_key = get_api_key("openai")
    if not api_key:
        return None
    body = json.dumps(
        {
            "model": resolve_openai_model(model),
            "input": prompt,
            "text": {"format": {"type": "json_object"}},
            "reasoning": {"effort": "none"},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"OpenAI API 오류 {exc.code}: {detail}") from exc
    return _parse_json_object(_extract_openai_text(payload))


def _call_gemini_json(model: str, prompt: str) -> dict[str, Any] | None:
    api_key = get_api_key("google")
    if not api_key:
        return None
    from google import genai
    from google.genai import types

    gemini_model = "gemini-2.5-pro" if "Pro" in model else "gemini-2.5-flash"
    response = genai.Client(api_key=api_key).models.generate_content(
        model=gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    return _parse_json_object(response.text or "")


def _parse_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    parsed = json.loads(text or "{}")
    return parsed if isinstance(parsed, dict) else None


def _extract_openai_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _subtitle_id(subtitle: SubtitleSegment, fallback: int) -> int:
    try:
        return int(subtitle.subtitle_id if subtitle.subtitle_id is not None else fallback)
    except Exception:
        return int(fallback)


def _major_code(index: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    index = max(0, min(int(index or 0), len(alphabet) - 1))
    return alphabet[index]


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:36]


def _title_from_subtitles(items: list[SubtitleSegment]) -> str:
    return _clean_title(" ".join(item.text for item in items[:2]))


def _summary_from_subtitles(items: list[SubtitleSegment]) -> str:
    return re.sub(r"\s+", " ", " ".join(item.text for item in items[:5])).strip()[:240]


def _confidence(row: dict[str, Any]) -> float:
    return max(0.0, min(1.0, _as_float(row.get("confidence"), 0.58)))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT",
    "EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID",
    "apply_roughcut_order_to_subtitles",
    "build_editor_roughcut_candidate_payload",
    "build_editor_roughcut_draft_prompt",
    "build_editor_roughcut_draft_result",
    "describe_editor_roughcut_llm_scope",
    "editor_roughcut_draft_autorun_enabled",
    "editor_roughcut_draft_enabled",
    "editor_roughcut_draft_llm_allowed",
    "estimate_editor_roughcut_llm_runtime_sec",
    "is_fast_recognition_mode",
    "merge_editor_roughcut_draft_state",
    "run_editor_roughcut_llm_draft",
]
