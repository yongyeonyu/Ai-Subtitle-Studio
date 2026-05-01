# Version: 03.03.01
# Phase: PHASE2
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable

from core.llm.openai_provider import is_openai_model, resolve_openai_model
from core.llm.secure_keys import get_api_key
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
    subtitles_from_dicts,
)
from .roughcut_settings import merge_roughcut_settings
from .subtitle_retimer import format_srt, retime_subtitles_for_edl


EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID = "editor_realtime_roughcut_draft"

DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT = """너는 자막 생성 중 실시간 러프컷 초안을 만드는 편집 보조자다.
자막을 시간순으로 읽고 큰 흐름이 바뀌는 지점만 중분류 A/B/C/D로 나눈다.
중분류만 만든다.
소분류는 새로 만들지 말고 각 중분류에 포함된 자막 row가 자동으로 소분류가 된다.
중분류는 가능하면 최소 5개 이상의 자막 row를 포함한다.
경계가 불확실하면 이전 중분류를 provisional로 두고 다음 입력에서 재검토한다.
응답은 반드시 JSON object로만 반환한다."""


def is_fast_recognition_mode(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    return str(settings.get("stt_quality_preset", "") or "").strip().lower() == "fast"


def editor_roughcut_draft_enabled(settings: dict[str, Any] | None) -> bool:
    merged = merge_roughcut_settings(settings or {})
    return bool(merged.get("editor_roughcut_draft_enabled", False)) and not is_fast_recognition_mode(settings)


def build_editor_roughcut_draft_prompt(
    segments: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
) -> str:
    merged = merge_roughcut_settings(settings or {})
    prompt = str(merged.get("editor_roughcut_draft_prompt") or "").strip() or DEFAULT_EDITOR_ROUGHCUT_DRAFT_PROMPT
    body = {
        "prompt_id": "editor_realtime_roughcut_draft_v1",
        "language": "ko",
        "editor_instructions": prompt,
        "output_contract": {
            "json_only": True,
            "schema": {
                "major_segments": [
                    {
                        "major_id": "A",
                        "title": "중분류 제목",
                        "summary": "짧은 요약",
                        "start_subtitle_id": 0,
                        "end_subtitle_id": 4,
                        "tags": ["선택 태그"],
                        "confidence": 0.0,
                        "status": "provisional",
                    }
                ]
            },
        },
        "subtitle_rows": _subtitle_prompt_rows(segments),
    }
    return json.dumps(body, ensure_ascii=False, indent=2)


def run_editor_roughcut_llm_draft(
    segments: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
    timeout: int = 45,
) -> dict[str, Any] | None:
    settings = settings or {}
    model = str(settings.get("selected_model", "") or "").strip()
    if not model or "사용 안함" in model:
        return None
    prompt = build_editor_roughcut_draft_prompt(segments, settings=settings)
    try:
        if "Gemini" in model:
            return _call_gemini_json(model, prompt)
        if is_openai_model(model):
            return _call_openai_json(model, prompt, timeout=timeout)
        return _call_ollama_json(model, prompt, timeout=timeout)
    except Exception as exc:
        try:
            from logger import get_logger

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
) -> RoughCutResult:
    settings = merge_roughcut_settings(settings or {})
    subtitles = _normalize_subtitles(subtitle_segments)
    if not subtitles:
        return RoughCutResult(
            warnings=("no_subtitle_segments",),
            draft_state=RoughCutDraftState(draft_id=EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID, status="idle"),
            schema_version="roughcut_result.v2",
        )

    groups = _major_groups_from_llm_payload(llm_payload, subtitles)
    if not groups:
        groups = _local_major_groups_from_subtitles(subtitles, settings=settings)

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
        start = min(item.start for item in items)
        end = max(item.end for item in items)
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
                    narrative_function="editor_realtime_subtitle",
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
                narrative_function="editor_realtime_major",
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
                reason="editor_realtime_draft",
                source_start=start,
                source_end=end,
                output_order=major_index,
                safety="acceptable",
                confidence=_confidence(group),
            )
        )

    edl = build_edl_segments(source_path, decisions, majors)
    guide = build_markdown_guide(chapters, decisions, edl)
    duration = media_duration if media_duration is not None else max((item.end for item in subtitles), default=0.0)
    summary = f"에디터 실시간 초안: 중분류 {len(majors)}개, 자막 {len(subtitles)}개, 길이 {duration:.1f}초"
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
            notes="editor_realtime_draft",
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
        "name": "에디터 실시간 초안",
        "created_at": now,
        "updated_at": now,
        "schema": "ai_subtitle_studio.roughcut_candidate.v2",
        "schema_version": "roughcut_candidate.v2",
        "source": "editor_realtime_draft",
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
        if str(item.get("candidate_id") or "") == EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID:
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
            "updated_from": "editor_realtime_draft",
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
    return list(subtitles_from_dicts(tuple(item for item in source if isinstance(item, dict))))


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


def _local_major_groups_from_subtitles(subtitles: list[SubtitleSegment], *, settings: dict[str, Any]) -> list[dict[str, Any]]:
    min_count = max(1, int(settings.get("roughcut_major_min_subtitle_count", 5) or 5))
    max_count = max(min_count, int(settings.get("editor_roughcut_draft_max_subtitle_count", max(8, min_count * 2)) or max(8, min_count * 2)))
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
            metadata={"source": source_path, "source_kind": "editor_realtime_draft"},
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


def _call_ollama_json(model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "keep_alive": -1,
            "options": {"temperature": 0.2, "num_predict": 1024},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json", "Connection": "keep-alive"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = json.loads(resp.read().decode("utf-8")).get("response", "")
    return _parse_json_object(text)


def _call_openai_json(model: str, prompt: str, *, timeout: int) -> dict[str, Any] | None:
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
    if index < len(alphabet):
        return alphabet[index]
    return f"M{index + 1}"


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
    "editor_roughcut_draft_enabled",
    "is_fast_recognition_mode",
    "merge_editor_roughcut_draft_state",
    "run_editor_roughcut_llm_draft",
]
