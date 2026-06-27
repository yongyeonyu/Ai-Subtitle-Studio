# Version: 03.14.29
# Phase: PHASE2
"""
core/subtitle_engine.py  ─ 자막 최적화 + SRT 저장 
[개선] LLM 프롬프트를 사용자 역할지정(user_settings)과 시스템 하드코딩(포맷 유지)으로 분리하여 안전하게 병합
[버그수정] LLM '사용 안함' 선택 시 Ollama 서버 연결 시도를 원천 차단하여 에러 및 앱 먹통 완벽 해결
[수정] [시스템 설정] + [사용자 설정] + [JSON 룰]을 완벽히 병합하여 엔진으로 전송
[수정] SRT 내보내기 시 하이픈(-) 유무 상관없이 화자 색상 태그 완벽 적용 완료
[추가] 일반/화자 자막 분리 생성 및 "자막백업" 폴더 내 날짜+순번 자동 채번 백업 기능 완비
[복구] 불필요한 초강력 시간태그 삭제 알고리즘 제거 (에디터 네비게이션 태그 오해 해소)
"""
import difflib
import json
import re
import threading
import time

from core.llm.secure_keys import get_api_key
from core.llm.gemini_provider import split_text as gemini_split_text
from core.llm.openai_provider import is_codex_model, is_openai_model, split_text as openai_split_text
from core.audio.stt_lattice import select_stt_lattice_text
from core.engine.llm_correction_guard import assess_llm_rewrite_policy
from core.engine.llm_candidate_policy import (
    _lora_line_break_patterns as _llm_lora_line_break_patterns,
    build_llm_candidate_options,
    validate_candidate_locked_chunks,
)
from core.engine.subtitle_macro_chunks import (
    build_llm_macro_groups as _build_llm_macro_groups,
    llm_macro_groups_require_provider_call as _llm_macro_groups_require_provider_call,
    llm_macro_chunk_enabled as _llm_macro_chunk_enabled,
    process_llm_macro_groups as _process_llm_macro_groups,
)
from core.engine.subtitle_native_word_split import native_builtin_word_groups as _native_builtin_word_groups
from core.engine.subtitle_text_policy import (
    clean_subtitle_text as _clean,
    enforce_final_subtitle_text_policy as _enforce_final_subtitle_text_policy,
    normalize_subtitle_text_lines as _normalize_subtitle_text_lines,
    split_visible_len as _split_visible_len,
    strip_stt_control_tokens as _strip_stt_control_tokens,
)
from core.engine.subtitle_segment_filter import (
    configure_segment_filter as _configure_segment_filter,
)
from core.engine.subtitle_accuracy_pipeline import (
    append_accuracy_decision,
    annotate_subtitle_auto_review,
    annotate_subtitle_completion_report,
    annotate_subtitle_context_consistency,
    annotate_subtitle_lora_style_consistency,
    annotate_subtitle_stage_confidence,
    describe_llm_verifier_decision,
    llm_gate_decision,
    llm_minimize_decision,
    repair_subtitle_context_consistency,
    rollback_decision,
    select_best_subtitle_output,
    subtitle_accuracy_metrics,
    verify_llm_chunks_for_subtitle,
)
from core.engine.subtitle_uncertainty import annotate_uncertainty_first_segments
from core.subtitle_quality.timestamp_regrouper import merge_short_segments_by_gap, regroup_by_word_timestamps
from core.personalization.deep_subtitle_policy import (
    adjust_subtitle_timing as deep_adjust_subtitle_timing,
    rerank_subtitle_candidates,
    select_stt_candidate as deep_select_stt_candidate,
    smooth_subtitle_sequence,
)
from core.personalization.deep_policy_learning import record_deep_policy_events_for_segments
from core.personalization.deep_runtime_adaptation import adapt_runtime_settings_from_deep_events
from core.personalization.editor_truth_memory import apply_recent_editor_truth_patterns
from core.personalization.lora_models import line_break_pattern_for_text
from core.personalization.runtime_lora_context import build_runtime_lora_prompt, runtime_lora_enabled
from core.personalization.subtitle_lora_runtime import (
    attach_segment_lora_settings,
    merge_segment_lora_settings,
)
from core.engine.subtitle_prompts import _build_llm_prompt
from core.engine.subtitle_settings import (
    _effective_llm_workers as _effective_llm_workers_impl,
    _get_user_settings,
    _quality_conservative_enabled,
    _resolve_runtime_llm_model,
    _setting_float,
    _setting_int,
    get_local_dataset_corrections,
    get_selected_llm,
)
from core.engine.subtitle_timing import (
    align_stt_candidates_to_subtitle_segments,
    adjust_timing,
    apply_final_gap_settings,
)
from core.engine.subtitle_context_refiner import refine_high_contextual_boundaries
from core.native_swift_subtitle_llm_context import (
    build_subtitle_llm_context_packs_via_swift,
    evaluate_subtitle_llm_context_gate_via_swift,
)
from core.subtitle_quality.quality_pipeline import run_subtitle_quality_pipeline
from core.subtitle_quality.vad_alignment_checker import (
    apply_vad_stt_timing_consensus,
    prioritize_vad_voice_starts,
)
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.runtime.logger import get_logger
from core.runtime.multi_process import runtime_parallel_worker_plan
from core.utils import load_subtitle_rules

_S = _get_user_settings() # 설정 데이터 스냅샷 로드

# ━━━ 📋 [UI 설정 연동 변수] 숫자를 직접 적지 않고 설정값에서 실시간으로 가져옵니다 ━━━
_EXAONE_WORKERS  = _setting_int(_S, "llm_threads", 6, fallback_key="llm_workers")  # (AI -> 에디터 LLM 처리 스레드)
_LOCAL_OLLAMA_WORKER_CAP = _setting_int(_S, "local_ollama_llm_max_workers", 2)
_GAP_BREAK_SEC   = _setting_float(_S, "sub_gap_break_sec", 1.5) # (간격 -> 문장 분리 간격)
_MIN_DURATION    = _setting_float(_S, "sub_min_duration", 0.3)  # (간격 -> 최소 자막 유지 시간)
_MAX_DURATION    = _setting_float(_S, "sub_max_duration", 6.0)  # (간격 -> 최대 자막 유지 시간)
_MAX_CPS         = _setting_int(_S, "sub_max_cps", 12)          # (간격 -> 최대 발음 속도 CPS)
_DEDUP_WINDOW    = _setting_float(_S, "sub_dedup_window", 0.5)  # (간격 -> 중복 자막 방어 범위)


from core.engine.subtitle_final_integrity import (
    _apply_final_sequence_cleanup,
    _best_stt_anchor_for_final_row,
    _final_transcript_integrity_guard,
    _restore_final_stt_anchor_drift,
    _restore_final_stt_slot_order_drift,
    _restore_missing_final_stt_anchor_rows,
    _source_stt_anchor_rows,
)
from core.engine.subtitle_llm_runtime import (
    _ENFORCE_RATIO,
    _LLM_SKIP_DUR,
    _accuracy_graph_enabled,
    _annotate_auto_review,
    _annotate_completion_report,
    _annotate_context_consistency,
    _annotate_stage_confidence,
    _append_accuracy_decision_for_settings,
    _apply_llm_confidence_gate,
    _attach_context_repair_policy,
    _attach_llm_context_windows,
    _attach_output_selector_policy,
    _clean_llm_output_chunks,
    _compact_output_selector_decision,
    _current_context_text_from_pack,
    _deep_rerank_chunks,
    _effective_llm_workers,
    _is_local_llm_connection_error,
    _llm_context_pack_for_rows,
    _local_ollama_ready,
    _log_accuracy_metrics,
    _mark_local_llm_unavailable,
    _profile_from_settings,
    _segment_llm_context_pack,
    _setting_bool,
    _short_log_text_preview,
    _verify_llm_chunks,
    ask_exaone_to_split,
    ask_openai_to_split,
    ensure_ollama_server,
    is_natural_break,
    ollama_split_text,
    restart_ollama_server,
    warmup_ollama_model,
)



from core.engine.subtitle_lora_packaging import (
    _apply_lora_card_packaging,
    _apply_lora_style_micro_merge,
    _bool_setting,
    _canonical_speaker_id,
    _clear_split_timing_projection_fields,
    _expand_non_speaker_multiline_segments,
    _find_matching_stt_candidate_for_decision,
    _is_speaker_split_multiline_segment,
    _segment_has_multi_speaker_linebreak_permission,
    _speaker_values_from_row,
    _stt_decision_speaker_fields,
    _stt_text_has_speaker_marker,
    _subtitle_text_lines,
)
from core.engine.subtitle_stt_candidate_helpers import _stt_selection_metadata




def _context_repair_output_variant(segments: list[dict], vad_segments: list[dict] | None, settings: dict | None) -> list[dict]:
    repaired, decision = repair_subtitle_context_consistency(segments, settings or {})
    if not decision.get("applied"):
        return []
    get_logger().log(
        "[자막문맥-자동복구] "
        f"반복 삭제 {decision.get('dropped_repeats', 0)}개, "
        f"부분중복 삭제 {decision.get('dropped_shadow_duplicates', 0)}개, "
        f"겹침 보정 {decision.get('shifted_starts', 0)}개 "
        f"(score {decision.get('before_score')}→{decision.get('after_score')})"
    )
    repaired = _self_review_subtitle_quality(repaired, vad_segments or [], settings or {})
    repaired = _annotate_context_consistency(repaired, settings or {})
    return _attach_context_repair_policy(repaired, decision, settings or {})


def _source_output_variant(segments: list[dict], vad_segments: list[dict] | None, settings: dict | None) -> list[dict]:
    source = [
        dict(seg)
        for seg in list(segments or [])
        if isinstance(seg, dict) and str(seg.get("text", "") or "").strip()
    ]
    if not source:
        return []
    source = adjust_timing(source)
    source = apply_final_gap_settings(source, settings or {}, force=True)
    source = align_stt_candidates_to_subtitle_segments(source)
    source = _apply_lora_style_micro_merge(source, vad_segments or [], settings or {}, stage="source")
    source = _self_review_subtitle_quality(source, vad_segments or [], settings or {})
    return _annotate_context_consistency(source, settings or {})




def _apply_output_variant_selector(
    optimized: list[dict],
    source_segments: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    settings = dict(settings or {})
    enabled = settings.get("subtitle_output_selector_enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
    if not enabled:
        return optimized
    repaired = _context_repair_output_variant(optimized, vad_segments or [], settings)
    source = _source_output_variant(source_segments, vad_segments, settings)
    variants = [
        {"name": f"{stage}_optimized", "segments": [dict(seg) for seg in list(optimized or []) if isinstance(seg, dict)]},
    ]
    if repaired:
        variants.append({"name": f"{stage}_context_repaired", "segments": repaired})
    if source:
        variants.append({"name": f"{stage}_source_gap_only", "segments": source})
    selected, decision = select_best_subtitle_output(variants, settings)
    decision = _compact_output_selector_decision(decision, stage=stage)
    selected = _apply_lora_style_micro_merge(selected, vad_segments or [], settings, stage=f"{stage}_selected")
    selected = apply_final_gap_settings(selected, settings, force=True)
    selected_index = int(decision.get("selected_index", 0) if decision.get("selected_index") is not None else 0)
    selected_score = decision.get("selected_score")
    if selected_index > 0:
        get_logger().log(
            "[자막출력-딥러닝선택] "
            f"{decision.get('selected_name')} 후보가 더 안전해서 최종 결과로 선택 "
            f"(score={selected_score})"
        )
    elif decision.get("selected_name"):
        get_logger().log(
            "[자막출력-딥러닝선택] "
            f"{decision.get('selected_name')} 후보 유지 "
            f"(score={selected_score})"
        )
    return _attach_output_selector_policy(selected, decision, settings, stage=stage)


def _self_review_subtitle_quality(
    segments: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
) -> list[dict]:
    settings = dict(settings or {})
    value = settings.get("runtime_quality_self_review_enabled", True)
    if isinstance(value, str):
        enabled = value.strip().lower() not in {"0", "false", "off", "no", "끔"}
    else:
        enabled = bool(value)
    if not enabled or not segments:
        return segments
    try:
        result = run_subtitle_quality_pipeline(
            [dict(seg) for seg in segments],
            vad_segments=list(vad_segments or []),
            settings=settings,
            auto_correct=False,
        )
    except Exception as exc:
        get_logger().log(f"[자막품질-자가진단] 실패: {exc}")
        return segments
    summary = result.summary
    get_logger().log(
        "[자막품질-자가진단] "
        f"score={summary.overall_score}, "
        f"green/yellow/red/gray={summary.green_count}/{summary.yellow_count}/{summary.red_count}/{summary.gray_count}, "
        f"review={summary.needs_review_count}"
    )
    rows = [dict(seg) for seg in result.segments]
    if rows:
        rows[0]["subtitle_quality_self_review_summary"] = {
            "schema": "ai_subtitle_studio.subtitle_quality_summary.v1",
            "task": "subtitle_quality_self_review_summary",
            "overall_score": summary.overall_score,
            "green_count": int(summary.green_count or 0),
            "yellow_count": int(summary.yellow_count or 0),
            "red_count": int(summary.red_count or 0),
            "gray_count": int(summary.gray_count or 0),
            "needs_review_count": int(summary.needs_review_count or 0),
            "auto_corrected_count": int(summary.auto_corrected_count or 0),
            "before_score": summary.before_score,
            "after_score": summary.after_score,
        }
    return rows


def _apply_final_vad_voice_start_priority(
    segments: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    settings = dict(settings or {})
    if not segments:
        return segments
    if not _setting_bool(settings, "vad_post_stt_align_enabled", True):
        return segments
    adjusted = segments
    default_edge_pad = _setting_float(settings, "vad_post_stt_edge_pad_sec", 0.04)
    edge_pad = max(0.0, _setting_float(settings, "vad_voice_start_priority_edge_pad_sec", default_edge_pad))
    min_overlap = max(0.0, _setting_float(settings, "vad_voice_start_priority_min_overlap_sec", 0.04))
    min_gap = max(0.0, _setting_float(settings, "vad_voice_start_priority_min_gap_sec", 0.02))
    if vad_segments and _setting_bool(settings, "vad_voice_start_priority_enabled", True):
        default_pull = max(1.25, _setting_float(settings, "vad_post_stt_max_shift_sec", 0.7))
        max_pull = max(0.0, _setting_float(settings, "vad_voice_start_priority_max_pull_sec", default_pull))
        max_stt_lead = max(0.0, _setting_float(settings, "vad_voice_start_priority_max_stt_lead_sec", 0.12))
        adjusted, changed = prioritize_vad_voice_starts(
            adjusted,
            vad_segments,
            max_pull_sec=max_pull,
            edge_pad_sec=edge_pad,
            min_overlap_sec=min_overlap,
            min_gap_sec=min_gap,
            max_stt_lead_sec=max_stt_lead,
        )
        if changed:
            get_logger().log(
                f"[VAD-시작우선] {stage}: 최종 자막 시작점 {changed}개를 VAD 음성 시작 기준으로 보정"
            )
            adjusted = align_stt_candidates_to_subtitle_segments(adjusted)
    if _setting_bool(settings, "vad_stt_timing_consensus_enabled", True):
        start_tol = max(0.0, _setting_float(settings, "vad_stt_timing_consensus_start_tolerance_sec", 0.35))
        end_tol = max(0.0, _setting_float(settings, "vad_stt_timing_consensus_end_tolerance_sec", 0.45))
        duration_tol = max(0.0, _setting_float(settings, "vad_stt_timing_consensus_duration_tolerance_sec", 0.45))
        max_gap = max(0.0, _setting_float(settings, "vad_stt_timing_consensus_max_vad_gap_sec", 0.65))
        adjusted, consensus_changed = apply_vad_stt_timing_consensus(
            adjusted,
            vad_segments,
            start_tolerance_sec=start_tol,
            end_tolerance_sec=end_tol,
            duration_tolerance_sec=duration_tol,
            max_vad_gap_sec=max_gap,
            edge_pad_sec=edge_pad,
            min_gap_sec=min_gap,
        )
        if consensus_changed:
            get_logger().log(
                f"[VAD/STT-컨센서스] {stage}: VAD/STT1/STT2 중 2개 이상이 일치한 자막 "
                f"{consensus_changed}개를 해당 시간으로 고정"
            )
            adjusted = align_stt_candidates_to_subtitle_segments(adjusted)
    return adjusted


from core.engine.subtitle_stt_candidate_selection import (
    _apply_stt_candidate_decision,
    _attach_lora_and_deep_timing,
    _best_scored_stt_candidate,
    _candidate_decision_from_raw_stt,
    _llm_model_disabled,
    _parse_stt_candidate_llm_label,
    _raw_stt_candidates,
    _restore_no_llm_raw_stt_text,
    _sanitize,
    _select_raw_stt_candidate_when_current_is_unbacked,
    _select_stt_candidate_fast,
    _select_stt_candidate_text,
    _select_stt_candidate_without_llm,
    _should_run_stt_candidate_llm_judge,
    _stt_candidate_risk_flags,
    _stt_current_candidate_score,
    _stt_decision_matches_raw_candidate,
)




def _has_explicit_lora_runtime_context(seg: dict | None) -> bool:
    """Avoid leaking the user's global LoRA store into bare unit-test segments."""
    if not isinstance(seg, dict):
        return False
    direct_keys = (
        "media_path",
        "_media_path",
        "media_id",
        "_media_id",
        "source_path",
        "_source_path",
        "clip_file",
        "_clip_file",
        "file",
        "path",
    )
    if any(seg.get(key) for key in direct_keys):
        return True
    metadata = seg.get("asr_metadata")
    if isinstance(metadata, dict) and any(metadata.get(key) for key in direct_keys):
        return True
    return bool(seg.get("_lora_segment_settings") or seg.get("_lora_generation_profile"))


def _segment_lora_runtime(
    seg: dict,
    runtime_settings: dict | None,
    rules: dict,
    explicit_threshold: int | None = None,
) -> tuple[dict, dict]:
    base_settings = dict(runtime_settings or _S)
    if runtime_settings is None and not _has_explicit_lora_runtime_context(seg):
        base_settings["editor_lora_runtime_enabled"] = False
        base_settings["subtitle_quality_auto_correct_enabled"] = False
        base_settings["lora_pattern_autobuild_enabled"] = False
    settings, lora_meta = merge_segment_lora_settings(seg, base_settings, rules=rules)
    if runtime_settings is None and explicit_threshold is not None and "split_length_threshold" not in lora_meta:
        settings = dict(settings)
        settings["split_length_threshold"] = explicit_threshold
    return settings, lora_meta


def _smooth_deep_sequence(segments: list[dict], settings: dict | None) -> list[dict]:
    smoothed, summary = smooth_subtitle_sequence(segments, settings or {})
    if summary:
        get_logger().log(
            "[딥러닝-시퀀스] "
            f"앞뒤 자막 보정 {summary.get('changed_segments', 0)}개, "
            f"hard-case {summary.get('hard_cases', 0)}개"
        )
    return smoothed


def _record_deep_policy_learning(segments: list[dict], settings: dict | None) -> None:
    try:
        result = record_deep_policy_events_for_segments(segments, settings or {})
    except Exception as exc:
        get_logger().log(f"[딥러닝-학습로그] 저장 실패: {exc}")
        return
    appended = int((result or {}).get("appended_rows", 0) or 0)
    if appended > 0:
        get_logger().log(f"[딥러닝-학습로그] 정책 결정 {appended}건 저장")


def _annotate_stt_candidate_context(segments: list[dict], window: int = 2) -> list[dict]:
    if not segments:
        return []
    annotated = [dict(seg) for seg in segments]

    def _context_text(seg: dict) -> str:
        candidates = [
            str(c.get("text", "") or "").strip()
            for c in list(seg.get("stt_candidates") or [])
            if str(c.get("text", "") or "").strip()
        ]
        if candidates:
            return " / ".join(candidates[:2])
        return str(seg.get("text", "") or "").strip()

    for idx, seg in enumerate(annotated):
        if len([c for c in list(seg.get("stt_candidates") or []) if str(c.get("text", "") or "").strip()]) < 2:
            continue
        prev_items = []
        for prev in annotated[max(0, idx - window):idx]:
            text = _context_text(prev)
            if text:
                prev_items.append(text)
        next_items = []
        for nxt in annotated[idx + 1:idx + 1 + window]:
            text = _context_text(nxt)
            if text:
                next_items.append(text)
        seg["stt_ensemble_context_prev"] = " | ".join(prev_items)
        seg["stt_ensemble_context_next"] = " | ".join(next_items)
    return annotated


def _chunk_timing_match_text(value: object) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(value or "")).lower()


def _word_text_for_chunk_timing(word: dict) -> str:
    return str(word.get("word", word.get("text", "")) or "").strip()


def _word_time_bounds(word: dict) -> tuple[float, float] | None:
    try:
        start = float(word.get("start"))
        end = float(word.get("end"))
    except (TypeError, ValueError):
        return None
    if end <= start:
        return None
    return start, end


def _chunk_words_text(words: list[dict]) -> str:
    parts = [_word_text_for_chunk_timing(word) for word in words if _word_text_for_chunk_timing(word)]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _guard_llm_chunk_text_with_stt_words(final_text: str, chunk_words: list[dict]) -> tuple[str, dict | None]:
    stt_text = _chunk_words_text(chunk_words)
    if not stt_text:
        return final_text, None
    final_key = _chunk_timing_match_text(final_text)
    stt_key = _chunk_timing_match_text(stt_text)
    if not final_key or not stt_key:
        return final_text, None
    ratio = difflib.SequenceMatcher(None, final_key, stt_key).ratio()
    if final_key == stt_key or ratio >= 0.78:
        return final_text, None
    if (final_key in stt_key or stt_key in final_key) and min(len(final_key), len(stt_key)) / max(len(final_key), len(stt_key)) >= 0.45:
        return final_text, None
    return stt_text, {
        "task": "llm_stt_text_guard",
        "reason": "llm_chunk_diverged_from_matched_stt_words",
        "llm_text": str(final_text or "")[:80],
        "stt_text": stt_text[:80],
        "similarity": round(float(ratio), 3),
    }


def _segment_has_stt_timing_anchor(seg: dict | None) -> bool:
    if not isinstance(seg, dict):
        return False
    if any(
        key in seg and seg.get(key) not in (None, "")
        for key in (
            "_stt_original_candidate_start",
            "_stt_original_candidate_end",
            "original_start",
            "original_end",
        )
    ):
        return True
    for key in ("stt_selected_source", "stt_ensemble_source", "stt_preview_source", "stt_source"):
        source = str(seg.get(key) or "").strip().upper().split("_", 1)[0]
        if source in {"STT1", "STT2"}:
            return True
    for candidate in list(seg.get("stt_candidates") or []):
        if not isinstance(candidate, dict):
            continue
        source = str(
            candidate.get("source")
            or candidate.get("stt_selected_source")
            or candidate.get("stt_preview_source")
            or candidate.get("stt_source")
            or ""
        ).strip().upper().split("_", 1)[0]
        if source in {"STT1", "STT2"} and str(candidate.get("text", "") or "").strip():
            return True
    return False


def _llm_text_only_timing_lock_enabled(seg: dict, settings: dict | None) -> bool:
    return _setting_bool(settings or {}, "subtitle_llm_text_only_timing_lock_enabled", True) and _segment_has_stt_timing_anchor(seg)


def _locked_llm_text_only_row(
    seg: dict,
    *,
    source_text: str,
    chunks: list[str] | tuple[str, ...] | None,
    corrections: dict | None,
    speaker: str,
    segment_lora: dict | None,
    segment_settings: dict | None,
    stage: str,
) -> dict:
    joined = " ".join(
        _clean(str(chunk), corrections)
        for chunk in list(chunks or [])
        if _clean(str(chunk), corrections)
    ).strip()
    fallback_text = _clean(source_text, corrections)
    final_text = joined or fallback_text
    row = {**seg, "text": final_text, "speaker": speaker}

    policy = {
        "task": "llm_text_only_timing_lock",
        "stage": stage,
        "preserved_count": True,
        "preserved_timing": True,
        "input_chunks": len(list(chunks or [])),
        "source_start": round(float(seg.get("start", 0.0) or 0.0), 3),
        "source_end": round(float(seg.get("end", seg.get("start", 0.0)) or 0.0), 3),
    }
    lora_meta = dict(segment_lora or {})
    rewrite_policy = assess_llm_rewrite_policy(source_text, [final_text])
    if rewrite_policy.get("changed"):
        lora_meta["_llm_rewrite_policy"] = rewrite_policy
    lora_meta["_llm_text_only_timing_lock_policy"] = policy

    locked_start = row.get("start")
    locked_end = row.get("end")
    locked_timeline_start = row.get("timeline_start")
    attached = _attach_lora_and_deep_timing(row, lora_meta, segment_settings)
    if locked_start is not None:
        attached["start"] = locked_start
    if locked_end is not None:
        attached["end"] = locked_end
    if locked_timeline_start is not None:
        attached["timeline_start"] = locked_timeline_start
    attached["_llm_text_only_timing_lock_policy"] = policy
    return attached


def _match_chunk_words_to_stt_timing(
    words: list[dict],
    chunk_text: str,
    cursor: int,
) -> dict | None:
    target = _chunk_timing_match_text(chunk_text)
    if not target or not words:
        return None

    best: dict | None = None
    max_window_words = 14
    max_extra_chars = max(4, min(12, len(target)))
    start_range = range(max(0, cursor), len(words))
    for start_idx in start_range:
        acc = ""
        last_idx = start_idx
        for end_idx in range(start_idx, min(len(words), start_idx + max_window_words)):
            token = _chunk_timing_match_text(_word_text_for_chunk_timing(words[end_idx]))
            if not token:
                continue
            acc += token
            last_idx = end_idx
            ratio = difflib.SequenceMatcher(None, target, acc).ratio()
            length_delta = abs(len(acc) - len(target)) / max(1, len(target))
            cursor_gap = max(0, start_idx - cursor)
            relation_bonus = 0.0
            if acc == target:
                relation_bonus = 0.30
            elif target in acc or acc in target:
                relation_bonus = 0.12
            score = ratio + relation_bonus - min(0.22, length_delta * 0.12) - min(0.18, cursor_gap * 0.018)
            candidate = {
                "score": score,
                "ratio": ratio,
                "start_idx": start_idx,
                "end_idx": last_idx + 1,
                "acc": acc,
                "relation": "exact" if acc == target else ("contains" if target in acc or acc in target else "fuzzy"),
            }
            if (
                best is None
                or candidate["score"] > best["score"]
                or (
                    abs(candidate["score"] - best["score"]) < 0.001
                    and abs(len(acc) - len(target)) < abs(len(best["acc"]) - len(target))
                )
            ):
                best = candidate
            if acc == target:
                break
            if len(acc) > len(target) + max_extra_chars and target not in acc and ratio < 0.65:
                break

    if not best:
        return None
    if best["ratio"] < 0.72 and not (best["relation"] in {"exact", "contains"} and best["ratio"] >= 0.55):
        return None

    chunk_words = [dict(word) for word in words[best["start_idx"]:best["end_idx"]]]
    bounds = [_word_time_bounds(word) for word in chunk_words]
    bounds = [bound for bound in bounds if bound is not None]
    if not chunk_words or not bounds:
        return None
    start = min(bound[0] for bound in bounds)
    end = max(bound[1] for bound in bounds)
    if end <= start:
        return None
    return {
        "start": start,
        "end": end,
        "words": chunk_words,
        "next_cursor": int(best["end_idx"]),
        "policy": {
            "task": "stt_chunk_word_timing_match",
            "target": target[:80],
            "matched": best["acc"][:80],
            "source_start_index": int(best["start_idx"]),
            "source_end_index": int(best["end_idx"]),
            "previous_cursor": int(cursor),
            "ratio": round(float(best["ratio"]), 3),
            "relation": best["relation"],
        },
    }


def _fallback_consume_chunk_words(
    words: list[dict],
    chunk_text: str,
    cursor: int,
    cur_start: float,
) -> dict:
    chunk_clean = _chunk_timing_match_text(chunk_text) or re.sub(r"\s+", "", str(chunk_text or ""))
    t_start = None
    t_end = None
    matched = 0
    chunk_words = []
    w_idx = cursor
    while w_idx < len(words) and matched < len(chunk_clean):
        word = words[w_idx]
        wc = _chunk_timing_match_text(_word_text_for_chunk_timing(word))
        bounds = _word_time_bounds(word)
        if bounds is not None:
            if t_start is None:
                t_start = bounds[0]
            t_end = bounds[1]
        matched += len(wc)
        chunk_words.append(word)
        w_idx += 1
    if t_start is None:
        t_start = cur_start
    if t_end is None or t_end <= t_start:
        t_end = t_start + 0.1
    return {
        "start": float(t_start),
        "end": float(t_end),
        "words": chunk_words,
        "next_cursor": w_idx,
        "policy": None,
    }


def _process_one(args: tuple) -> list[dict]:
    if len(args) == 9:
        seg, rules, threshold, corrections, model, user_prompt, api_key, conservative, runtime_settings = args
    elif len(args) == 8:
        seg, rules, threshold, corrections, model, user_prompt, api_key, conservative = args
        runtime_settings = None
    elif len(args) == 7:
        seg, rules, threshold, corrections, model, user_prompt, api_key = args
        conservative = False
        runtime_settings = None
    else:
        seg, rules, threshold, corrections, model, user_prompt = args
        api_key = ""
        conservative = False
        runtime_settings = None
    llm_disabled = _llm_model_disabled(model)

    spk  = seg.get("speaker", "SPEAKER_00")
    raw_text = str(seg.get("text", "") or "")
    text = _strip_stt_control_tokens(raw_text).strip()
    if not text:
        return []
    if text != raw_text.strip():
        seg = {**seg, "text": text}

    # 💡 [추가] duration 정의
    duration = seg.get("end", 0) - seg.get("start", 0)

    segment_settings, segment_lora = _segment_lora_runtime({**seg, "text": text}, runtime_settings, rules, threshold)

    candidate_selected = False
    if seg.get("stt_candidates") and duration >= 0.35:
        candidate_settings = {**dict(segment_settings or {}), **dict(runtime_settings or _get_user_settings() or {})}
        selected_decision = _select_stt_candidate_text(seg, model, user_prompt, api_key, candidate_settings, rules)
        if selected_decision:
            candidate_selected = True
            seg, _applied = _apply_stt_candidate_decision(seg, selected_decision)
            text = str(seg.get("text", "") or "").strip()
            spk = seg.get("speaker", spk)
            segment_settings, segment_lora = _segment_lora_runtime({**seg, "text": text}, runtime_settings, rules, threshold)

    threshold = _setting_int(segment_settings, "split_length_threshold", threshold)
    gap_break_sec = _setting_float(segment_settings, "sub_gap_break_sec", _GAP_BREAK_SEC)

    # 💡 [환각 방지] 너무 짧은 자막은 LLM 교정을 생략합니다.
    if duration < _LLM_SKIP_DUR or len(text.replace(" ", "")) <= (threshold - 5) or (
        candidate_selected and len(text.replace(" ", "").replace("\n", "")) <= threshold
    ):
        return [_attach_lora_and_deep_timing({**seg, "text": _clean(text, corrections)}, segment_lora, segment_settings)]

    words = seg.get("words", [])
    if not words:
        tokens = text.split()
        dur    = max(0.1, seg.get("end", 1.0) - seg.get("start", 0.0))
        step   = dur / max(1, len(tokens))
        words  = [{"word": t, "start": seg["start"] + i * step,
                   "end": seg["start"] + (i + 1) * step, "speaker": spk}
                  for i, t in enumerate(tokens)]
    else:
        for w in words:
            w.setdefault("speaker", spk)

    # 💡 [핵심] 1.0초 미만의 짧은 자막은 LLM에게 교정을 맡기지 않습니다. 
    # AI가 짧은 단어를 보고 문맥을 상상해서 소설을 쓰는 것을 원천 차단합니다.
    if duration < 1.0 or len(text.replace(" ", "")) <= threshold - 5:
        return [_attach_lora_and_deep_timing({**seg, "text": _clean(text, corrections)}, segment_lora, segment_settings)]
    # [수정] LLM 호출 분기 부분
    should_call_llm = False
    candidate_options: list[dict] | None = None
    context_pack = _segment_llm_context_pack(seg)
    if llm_disabled:
        chunks = None
    else:
        should_call_llm, segment_lora = _apply_llm_confidence_gate(seg, text, threshold, duration, segment_settings, segment_lora)
        if not should_call_llm:
            chunks = None
        else:
            candidate_options = build_llm_candidate_options(text, threshold, rules, segment_settings)
            if "Gemini" in model:
                chunks = ask_gemini_to_split(
                    text,
                    threshold,
                    rules,
                    model,
                    user_prompt,
                    api_key,
                    conservative=conservative,
                    settings=segment_settings,
                    candidate_options=candidate_options,
                    context_pack=context_pack,
                )
            elif is_openai_model(model):
                chunks = ask_openai_to_split(
                    text,
                    threshold,
                    rules,
                    model,
                    user_prompt,
                    api_key,
                    conservative=conservative,
                    settings=segment_settings,
                    candidate_options=candidate_options,
                    context_pack=context_pack,
                )
            else:
                chunks = ask_exaone_to_split(
                    text,
                    threshold,
                    rules,
                    model,
                    user_prompt,
                    conservative=conservative,
                    settings=segment_settings,
                    candidate_options=candidate_options,
                    context_pack=context_pack,
                )
        if should_call_llm:
            chunks, segment_lora = _verify_llm_chunks(
                text,
                chunks,
                segment_settings,
                segment_lora,
                fallback="word_timing_split",
                candidate_options=candidate_options,
                duration_sec=max(0.0, float(seg.get("end", 0.0) or 0.0) - float(seg.get("start", 0.0) or 0.0)),
                context_pack=context_pack,
            )


    if chunks:
        chunks, segment_lora = _deep_rerank_chunks(text, chunks, segment_settings, segment_lora)
        if _llm_text_only_timing_lock_enabled(seg, segment_settings):
            return [
                _locked_llm_text_only_row(
                    seg,
                    source_text=text,
                    chunks=chunks,
                    corrections=corrections,
                    speaker=spk,
                    segment_lora=segment_lora,
                    segment_settings=segment_settings,
                    stage="process_one",
                )
            ]
        rewrite_policy = assess_llm_rewrite_policy(text, chunks)
        if rewrite_policy.get("changed"):
            segment_lora = dict(segment_lora or {})
            segment_lora["_llm_rewrite_policy"] = rewrite_policy
        result   = []
        w_idx    = 0
        cur_start = seg["start"]
        for chunk in chunks:
            final_text = _clean(chunk, corrections)
            chunk_clean = _chunk_timing_match_text(final_text or chunk)
            if not chunk_clean:
                continue
            timing_match = _match_chunk_words_to_stt_timing(words, final_text or str(chunk), w_idx)
            if timing_match is None:
                timing_match = _fallback_consume_chunk_words(words, final_text or str(chunk), w_idx, float(cur_start))
            t_start = float(timing_match["start"])
            t_end = float(timing_match["end"])
            chunk_words = list(timing_match.get("words") or [])
            w_idx = int(timing_match.get("next_cursor", w_idx))
            t_start = max(t_start, cur_start)
            if t_end <= t_start:
                t_end = t_start + 0.1
            
            # 텍스트가 유효할 때만 결과에 추가
            if final_text:
                guarded_text, text_guard_policy = _guard_llm_chunk_text_with_stt_words(final_text, chunk_words)
                if text_guard_policy:
                    final_text = _clean(guarded_text, corrections)
                timing_policy = timing_match.get("policy")
                row = {
                    **_stt_selection_metadata(seg),
                    "start":   t_start,
                    "end":     t_end,
                    "text":    final_text,
                    "speaker": spk,
                    "words":   chunk_words,
                }
                if timing_policy:
                    row["_stt_word_match_timing_policy"] = timing_policy
                if text_guard_policy:
                    row["_llm_stt_text_guard_policy"] = text_guard_policy
                _chunk_settings, chunk_lora = _segment_lora_runtime(
                    {**seg, "start": t_start, "end": t_end, "text": final_text, "words": chunk_words},
                    segment_settings,
                    rules,
                )
                result.append(_attach_lora_and_deep_timing(row, chunk_lora or segment_lora, _chunk_settings))
            cur_start = t_end
            
        # 💡 [불필요한 2차 _clean 루프 완전 삭제] 이미 정리된 텍스트의 길이만 확인합니다.
        final_result = [r for r in result if len(r["text"].replace(" ", "").replace("\n", "")) >= 2]
        
        if len(final_result) > 1:
            get_logger().log(f"[분할-LLM] '{text[:15]}...' -> {len(final_result)}조각 분리")
        return final_result

    result = []
    native_groups = _native_builtin_word_groups(
        words,
        rules=rules,
        threshold=threshold,
        gap_break_sec=gap_break_sec,
        default_gap_break_sec=_GAP_BREAK_SEC,
        natural_break_func=is_natural_break,
        visible_len_func=_split_visible_len,
    )
    if native_groups:
        iterable_groups = [words[begin:end] for begin, end in native_groups]
    else:
        iterable_groups = []
        buf = []
        buf_len = 0
        for i, w in enumerate(words):
            buf.append(w)
            buf_len += _split_visible_len(str(w.get("word", "") or ""))
            is_last = (i == len(words) - 1)
            flush = False
            if not is_last:
                nw = words[i + 1]
                gap = nw["start"] - w["end"]
                flush = (
                    gap >= gap_break_sec
                    or (buf_len >= threshold and is_natural_break(w["word"], nw["word"], rules))
                    or buf_len >= int(threshold * _ENFORCE_RATIO)
                )
            else:
                flush = True
            if flush:
                iterable_groups.append(buf)
                buf = []
                buf_len = 0

    for buf in iterable_groups:
        if buf:
            t = " ".join(str(x.get("word", "") or "") for x in buf)
            ct = _clean(t, corrections)
            if ct and len(ct.replace(" ", "").replace("\n", "")) >= 2:
                result.append(_attach_lora_and_deep_timing({
                    **_stt_selection_metadata(seg),
                    "start":   buf[0]["start"],
                    "end":     buf[-1]["end"],
                    "text":    ct,
                    "speaker": buf[0].get("speaker", spk),
                    "words":   buf,
                }, segment_lora, segment_settings))
            
    if len(result) > 1 and _setting_bool(segment_settings, "subtitle_builtin_split_verbose_log", False):
        get_logger().log(f"[분할-내장알고리즘] '{text[:15]}...' -> {len(result)}조각 안전 분리")
    return result


def _process_one_llm_only(args: tuple) -> list[dict]:
    if len(args) == 9:
        seg, rules, threshold, corrections, model, user_prompt, api_key, conservative, runtime_settings = args
    else:
        seg, rules, threshold, corrections, model, user_prompt, api_key, conservative = args
        runtime_settings = None
    llm_disabled = _llm_model_disabled(model)
    spk = seg.get("speaker", "SPEAKER_00")
    raw_text = str(seg.get("text", "") or "")
    text = _strip_stt_control_tokens(raw_text).strip()
    if not text:
        return []
    if text != raw_text.strip():
        seg = {**seg, "text": text}

    duration = float(seg.get("end", 0.0) or 0.0) - float(seg.get("start", 0.0) or 0.0)
    segment_settings, segment_lora = _segment_lora_runtime({**seg, "text": text}, runtime_settings, rules, threshold)

    candidate_selected = False
    if seg.get("stt_candidates") and duration >= 0.35:
        candidate_settings = {**dict(segment_settings or {}), **dict(runtime_settings or _get_user_settings() or {})}
        selected_decision = _select_stt_candidate_text(seg, model, user_prompt, api_key, candidate_settings, rules)
        if selected_decision:
            candidate_selected = True
            seg, _applied = _apply_stt_candidate_decision(seg, selected_decision)
            text = str(seg.get("text", "") or "").strip()
            spk = seg.get("speaker", spk)
            segment_settings, segment_lora = _segment_lora_runtime({**seg, "text": text}, runtime_settings, rules, threshold)

    cleaned_text = _clean(text, None if llm_disabled else corrections)
    if not cleaned_text:
        return []
    truth_text, truth_meta = (cleaned_text, None) if llm_disabled else apply_recent_editor_truth_patterns(cleaned_text, segment_settings)
    if truth_meta:
        cleaned_text = truth_text
        segment_lora = dict(segment_lora or {})
        segment_lora["_editor_truth_runtime_policy"] = truth_meta
        segment_lora = append_accuracy_decision(segment_lora, truth_meta)
        seg = {**seg, "text": cleaned_text}
        refreshed_settings, refreshed_lora = _segment_lora_runtime({**seg, "text": cleaned_text}, segment_settings, rules, threshold)
        if refreshed_lora:
            refreshed_lora = dict(refreshed_lora)
            refreshed_lora["_editor_truth_runtime_policy"] = truth_meta
            refreshed_lora = append_accuracy_decision(refreshed_lora, truth_meta)
            segment_lora = refreshed_lora
            segment_settings = refreshed_settings
    if str(seg.get("text", "") or "").strip() != cleaned_text:
        segment_settings, segment_lora = _segment_lora_runtime({**seg, "text": cleaned_text}, runtime_settings, rules, threshold)
    threshold = _setting_int(segment_settings, "split_length_threshold", threshold)
    if llm_disabled or (
        candidate_selected and len(cleaned_text.replace(" ", "").replace("\n", "")) <= threshold
    ):
        row = {**seg, "text": cleaned_text}
        if llm_disabled:
            row["_stt_no_llm_raw_text"] = cleaned_text
            policy = dict(row.get("_stt_no_llm_raw_candidate_policy") or {})
            policy.update(
                {
                    "task": "stt_no_llm_raw_text_lock",
                    "reason": policy.get("reason") or "subtitle_llm_disabled",
                    "raw_text": cleaned_text,
                }
            )
            row["_stt_no_llm_raw_candidate_policy"] = policy
        return [_attach_lora_and_deep_timing(row, segment_lora, segment_settings)]
    if duration < _LLM_SKIP_DUR or len(cleaned_text.replace(" ", "")) <= (threshold - 5):
        return [_attach_lora_and_deep_timing({**seg, "text": cleaned_text}, segment_lora, segment_settings)]

    words = seg.get("words", [])
    if not words:
        tokens = cleaned_text.split()
        dur = max(0.1, float(seg.get("end", 1.0) or 1.0) - float(seg.get("start", 0.0) or 0.0))
        step = dur / max(1, len(tokens))
        words = [
            {
                "word": token,
                "start": float(seg["start"]) + i * step,
                "end": float(seg["start"]) + (i + 1) * step,
                "speaker": spk,
            }
            for i, token in enumerate(tokens)
        ]
    else:
        for word in words:
            word.setdefault("speaker", spk)

    should_call_llm, segment_lora = _apply_llm_confidence_gate(seg, cleaned_text, threshold, duration, segment_settings, segment_lora)
    context_pack = _segment_llm_context_pack(seg)
    if not should_call_llm:
        chunks = None
    else:
        candidate_options = build_llm_candidate_options(cleaned_text, threshold, rules, segment_settings)
        if "Gemini" in model:
            chunks = ask_gemini_to_split(
                cleaned_text,
                threshold,
                rules,
                model,
                user_prompt,
                api_key,
                conservative=conservative,
                settings=segment_settings,
                candidate_options=candidate_options,
                context_pack=context_pack,
            )
        elif is_openai_model(model):
            chunks = ask_openai_to_split(
                cleaned_text,
                threshold,
                rules,
                model,
                user_prompt,
                api_key,
                conservative=conservative,
                settings=segment_settings,
                candidate_options=candidate_options,
                context_pack=context_pack,
            )
        else:
            chunks = ask_exaone_to_split(
                cleaned_text,
                threshold,
                rules,
                model,
                user_prompt,
                conservative=conservative,
                settings=segment_settings,
                candidate_options=candidate_options,
                context_pack=context_pack,
            )
    if should_call_llm:
        chunks, segment_lora = _verify_llm_chunks(
            cleaned_text,
            chunks,
            segment_settings,
            segment_lora,
            fallback="original_subtitle",
            candidate_options=candidate_options,
            duration_sec=max(0.0, float(seg.get("end", 0.0) or 0.0) - float(seg.get("start", 0.0) or 0.0)),
            context_pack=context_pack,
        )

    if not chunks:
        return [_attach_lora_and_deep_timing({**seg, "text": cleaned_text}, segment_lora, segment_settings)]
    chunks, segment_lora = _deep_rerank_chunks(cleaned_text, chunks, segment_settings, segment_lora)
    if _llm_text_only_timing_lock_enabled(seg, segment_settings):
        return [
            _locked_llm_text_only_row(
                seg,
                source_text=cleaned_text,
                chunks=chunks,
                corrections=corrections,
                speaker=spk,
                segment_lora=segment_lora,
                segment_settings=segment_settings,
                stage="process_one_llm_only",
            )
        ]
    rewrite_policy = assess_llm_rewrite_policy(cleaned_text, chunks)
    if rewrite_policy.get("changed"):
        segment_lora = dict(segment_lora or {})
        segment_lora["_llm_rewrite_policy"] = rewrite_policy

    result = []
    w_idx = 0
    cur_start = float(seg.get("start", 0.0) or 0.0)
    for chunk in chunks:
        final_text = _clean(str(chunk), corrections)
        chunk_clean = _chunk_timing_match_text(final_text or chunk)
        if not chunk_clean:
            continue
        timing_match = _match_chunk_words_to_stt_timing(words, final_text or str(chunk), w_idx)
        if timing_match is None:
            timing_match = _fallback_consume_chunk_words(words, final_text or str(chunk), w_idx, float(cur_start))
        t_start = float(timing_match["start"])
        t_end = float(timing_match["end"])
        chunk_words = list(timing_match.get("words") or [])
        w_idx = int(timing_match.get("next_cursor", w_idx))
        t_start = max(float(t_start), cur_start)
        if float(t_end) <= t_start:
            t_end = t_start + 0.1
        if final_text:
            guarded_text, text_guard_policy = _guard_llm_chunk_text_with_stt_words(final_text, chunk_words)
            if text_guard_policy:
                final_text = _clean(guarded_text, corrections)
            timing_policy = timing_match.get("policy")
            row = {
                **_stt_selection_metadata(seg),
                "start": t_start,
                "end": t_end,
                "text": final_text,
                "speaker": spk,
                "words": chunk_words,
            }
            if timing_policy:
                row["_stt_word_match_timing_policy"] = timing_policy
            if text_guard_policy:
                row["_llm_stt_text_guard_policy"] = text_guard_policy
            _chunk_settings, chunk_lora = _segment_lora_runtime(
                {**seg, "start": t_start, "end": t_end, "text": final_text, "words": chunk_words},
                segment_settings,
                rules,
            )
            result.append(_attach_lora_and_deep_timing(row, chunk_lora or segment_lora, _chunk_settings))
        cur_start = float(t_end)

    if len(result) > 1:
        get_logger().log(f"[분할-LLM] '{cleaned_text[:15]}...' -> {len(result)}조각 분리")
    return result or [_attach_lora_and_deep_timing({**seg, "text": cleaned_text}, segment_lora, segment_settings)]


def _enforce_len(segments: list[dict], threshold: int, rules: dict) -> list[dict]:
    result = []
    lora_meta_keys = (
        "_lora_segment_settings",
        "_lora_gap_settings",
        "_lora_generation_profile",
        "_lora_segment_score",
        "_lora_segment_doc_count",
        "_lora_segment_query",
        "_deep_rerank_policy",
        "_deep_timing_policy",
        "_editor_truth_runtime_policy",
        "_llm_gate_policy",
        "_llm_minimize_policy",
        "_llm_candidate_policy",
        "_llm_verifier_policy",
        "_llm_rollback_policy",
        "_llm_macro_chunk_policy",
        "_accuracy_decision_graph",
    )
    for seg in segments:
        segment_settings = dict(seg.get("_lora_segment_settings") or {})
        segment_threshold = _setting_int(segment_settings, "split_length_threshold", threshold)
        limit = int(segment_threshold * _ENFORCE_RATIO)
        text = seg.get("text", "")
        if len(text.replace(" ", "").replace("\n", "")) <= limit:
            result.append(seg)
            continue
        
        get_logger().log(f"[강제분할] 초과로 분할 시도: '{text[:15]}...'")
        spk   = seg.get("speaker", "SPEAKER_00")
        words = seg.get("words") or [
            {"word": t, "start": seg["start"] + i * max(0.1, (seg["end"]-seg["start"])/max(1,len(text.split()))),
             "end":   seg["start"] + (i+1) * max(0.1, (seg["end"]-seg["start"])/max(1,len(text.split())))}
            for i, t in enumerate(text.split())
        ]
        buf = []
        for i, w in enumerate(words):
            buf.append(w)
            is_last = (i == len(words) - 1)
            clen    = sum(len(x["word"].replace(" ", "").replace("\n", "")) for x in buf)
            flush   = is_last
            if not is_last:
                nw    = words[i+1]
                flush = ((clen >= segment_threshold and is_natural_break(w["word"], nw["word"], rules))
                         or clen >= limit)
            if flush:
                t = " ".join(x["word"] for x in buf).strip()
                ct = _clean(t)
                if ct:
                    lora_meta = {key: seg[key] for key in lora_meta_keys if key in seg}
                    result.append({
                        **_stt_selection_metadata(seg),
                        **lora_meta,
                        "start": buf[0]["start"],
                        "end": buf[-1]["end"],
                        "text": ct,
                        "speaker": spk,
                        "words": buf,
                    })
                buf = []
    return result

def _optimizer_context() -> tuple[dict, list[dict], str, dict, int, str, str, dict, dict]:
    global _EXAONE_WORKERS, _LOCAL_OLLAMA_WORKER_CAP, _GAP_BREAK_SEC, _MIN_DURATION, _MAX_DURATION, _MAX_CPS, _DEDUP_WINDOW

    model = get_selected_llm()
    rules = load_subtitle_rules()
    threshold = 10
    user_prompt = ""
    api_key = ""
    loaded_settings = {}

    s = _get_user_settings()
    loaded_settings = dict(s)
    loaded_settings, adaptation_meta = adapt_runtime_settings_from_deep_events(loaded_settings)
    if adaptation_meta.get("applied"):
        changes = dict(adaptation_meta.get("changes") or {})
        get_logger().log(
            "[딥러닝-런타임보정] "
            + ", ".join(f"{key}: {item.get('old')}→{item.get('new')}" for key, item in list(changes.items())[:6])
        )
    threshold = _setting_int(loaded_settings, "split_length_threshold", 20)
    if _setting_bool(loaded_settings, "subtitle_lora_split_floor_enabled", True):
        threshold = max(threshold, _setting_int(loaded_settings, "subtitle_lora_split_floor_chars", 20))
    _EXAONE_WORKERS = _setting_int(loaded_settings, "llm_threads", 6, fallback_key="llm_workers")
    _LOCAL_OLLAMA_WORKER_CAP = _setting_int(loaded_settings, "local_ollama_llm_max_workers", 2)
    _GAP_BREAK_SEC = _setting_float(loaded_settings, "sub_gap_break_sec", 1.5)
    _MIN_DURATION = _setting_float(loaded_settings, "sub_min_duration", 0.2)
    _MAX_DURATION = _setting_float(loaded_settings, "sub_max_duration", 6.0)
    _MAX_CPS = _setting_int(loaded_settings, "sub_max_cps", 12)
    _DEDUP_WINDOW = _setting_float(loaded_settings, "sub_dedup_window", 0.5)
    _configure_segment_filter(loaded_settings)

    if "user_prompt" in loaded_settings:
        user_prompt = loaded_settings["user_prompt"]
    elif "llm_prompt" in loaded_settings:
        user_prompt = loaded_settings["llm_prompt"]

    if "Gemini" in model:
        api_key = get_api_key("google") or loaded_settings.get("google_api_key", "")
    elif is_openai_model(model):
        api_key = get_api_key("openai") or loaded_settings.get("openai_api_key", "")
    else:
        api_key = ""

    raw_corr = get_local_dataset_corrections()
    corrections: dict = raw_corr if isinstance(raw_corr, dict) else {}
    return loaded_settings, rules, model, corrections, threshold, user_prompt, api_key, raw_corr, loaded_settings


def optimize_stt_candidate_segments(segments: list[dict], vad_segments: list[dict] | None = None) -> list[dict]:
    """Apply STT candidate-only split rules and final Gap settings without LLM."""
    if not segments:
        return segments
    loaded_settings, rules, _model, corrections, threshold, user_prompt, _api_key, _raw_corr, _settings = _optimizer_context()
    args = [
        (dict(seg), rules, threshold, corrections, "사용 안함 (STT 후보 규칙 전용)", user_prompt, "", False, loaded_settings)
        for seg in segments
        if isinstance(seg, dict)
    ]
    optimized: list[dict] = []
    for idx, arg in enumerate(args):
        try:
            optimized.extend(_process_one(arg))
        except Exception as exc:
            get_logger().log(f"STT 후보 규칙 처리 오류: {exc}")
            optimized.append(dict(segments[idx]))
    optimized = _enforce_len(optimized, threshold, rules)
    optimized = regroup_by_word_timestamps(
        optimized,
        max_chars=threshold,
        max_duration=_MAX_DURATION,
        max_cps=_MAX_CPS,
        min_duration=_MIN_DURATION,
        gap_break_sec=_GAP_BREAK_SEC,
        word_gap_break_sec=float(loaded_settings.get("word_timing_gap_break_sec", 0.65) or 0.65),
        vad_segments=vad_segments or [],
        frame_rate=float(loaded_settings.get("video_fps", 0.0) or 0.0),
        rules=rules,
    )
    optimized = adjust_timing(optimized)
    optimized = _smooth_deep_sequence(optimized, loaded_settings)
    optimized = apply_final_gap_settings(optimized, loaded_settings, force=True)
    optimized = _self_review_subtitle_quality(optimized, vad_segments or [], loaded_settings)
    optimized = _annotate_context_consistency(optimized, loaded_settings)
    optimized = _apply_output_variant_selector(optimized, [dict(seg) for seg in segments if isinstance(seg, dict)], vad_segments or [], loaded_settings, stage="stt_candidate")
    optimized = _apply_final_vad_voice_start_priority(optimized, vad_segments or [], loaded_settings, stage="stt_candidate")
    optimized = _annotate_auto_review(optimized, loaded_settings)
    optimized = _apply_lora_card_packaging(optimized, loaded_settings, rules, stage="stt_candidate")
    optimized = _annotate_stage_confidence(optimized, loaded_settings)
    optimized = _annotate_completion_report(optimized, loaded_settings)
    _log_accuracy_metrics(optimized, loaded_settings)
    _record_deep_policy_learning(optimized, loaded_settings)
    return optimized


def _emit_llm_progress(progress_callback, *, active: bool, idx: int = -1, total: int = 0, seg: dict | None = None) -> None:
    if not callable(progress_callback):
        return
    payload = {
        "active": bool(active),
        "idx": int(idx),
        "total": int(total),
    }
    if seg:
        payload.update(
            {
                "start": float(seg.get("start", 0.0) or 0.0),
                "end": float(seg.get("end", seg.get("start", 0.0)) or seg.get("start", 0.0) or 0.0),
                "text": str(seg.get("text", "") or ""),
                "line": int(seg.get("line", -1) or -1),
            }
        )
    try:
        progress_callback(payload)
    except Exception:
        pass


def _emit_processing_preview(
    preview_callback,
    *,
    stage: str,
    stage_label: str,
    segments: list[dict] | None,
    diagnostics: dict | None = None,
) -> None:
    if not callable(preview_callback):
        return
    snapshot: list[dict] = []
    for idx, seg in enumerate(list(segments or [])):
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text", "") or "").strip()
        if not text:
            continue
        if "\n" in text and not _segment_has_multi_speaker_linebreak_permission(seg):
            text = " ".join(_subtitle_text_lines(text))
            if not text:
                continue
        try:
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
        except Exception:
            continue
        if end <= start:
            continue
        row = {
            "start": start,
            "end": end,
            "text": text,
            "line": int(seg.get("line", idx) or idx),
        }
        speaker = str(seg.get("speaker", seg.get("spk_id", "")) or "").strip()
        if speaker:
            row["speaker"] = speaker
        if isinstance(seg.get("quality"), dict):
            row["quality"] = dict(seg.get("quality") or {})
        if isinstance(seg.get("stt_candidates"), list):
            row["stt_candidates"] = [dict(item) for item in seg.get("stt_candidates") if isinstance(item, dict)]
        snapshot.append(row)
    if not snapshot:
        return
    try:
        preview_callback(
            {
                "active": True,
                "stage": str(stage or ""),
                "stage_label": str(stage_label or stage or ""),
                "segments": snapshot,
                **({"diagnostics": dict(diagnostics)} if isinstance(diagnostics, dict) and diagnostics else {}),
            }
        )
    except Exception:
        pass


def _segment_needs_llm_review(seg: dict, rules: dict, threshold: int, settings: dict) -> tuple[bool, dict]:
    text = str(seg.get("text", "") or "").strip()
    if not text:
        return False, dict(seg)
    duration = float(seg.get("end", 0.0) or 0.0) - float(seg.get("start", 0.0) or 0.0)
    segment_settings, segment_lora = _segment_lora_runtime({**seg, "text": text}, settings, rules, threshold)
    segment_threshold = _setting_int(segment_settings, "split_length_threshold", threshold)
    compact_len = len(text.replace(" ", "").replace("\n", ""))
    out = dict(seg)
    if duration < _LLM_SKIP_DUR or compact_len <= segment_threshold - 5:
        return False, out
    should_call, segment_lora = _apply_llm_confidence_gate(out, text, segment_threshold, duration, segment_settings, segment_lora)
    out = _attach_lora_and_deep_timing(out, segment_lora, segment_settings)
    return bool(should_call), out


def _codex_native_fast_path_enabled(model: str, settings: dict | None, segment_count: int) -> bool:
    if not is_codex_model(model):
        return False
    if not _setting_bool(settings, "codex_subtitle_native_fast_path_enabled", True):
        return False
    min_segments = max(1, _setting_int(settings or {}, "codex_subtitle_native_fast_path_min_segments", 80))
    return int(segment_count or 0) >= min_segments


def _codex_native_fast_path_needs_llm(seg: dict, normal_gate_needs: bool, settings: dict | None) -> bool:
    """Keep Codex CLI for true review targets while bulk rows use local rules."""
    if bool(seg.get("stt_ensemble_needs_llm_review")):
        return True
    bucket = str(seg.get("_uncertainty_bucket") or "").strip().lower()
    if bucket == "precision":
        return True
    quality = dict(seg.get("quality") or {})
    quality_label = str(quality.get("confidence_label") or seg.get("subtitle_confidence_label") or "").strip().lower()
    if quality_label == "red":
        return True
    if not normal_gate_needs:
        return False
    text = str(seg.get("text", "") or "")
    compact_len = len(text.replace(" ", "").replace("\n", ""))
    row_settings = dict(seg.get("_lora_segment_settings") or {})
    threshold = max(1, _setting_int({**dict(settings or {}), **row_settings}, "split_length_threshold", 20))
    long_ratio = max(1.0, _setting_float(settings or {}, "codex_subtitle_native_fast_path_long_text_llm_ratio", 2.8))
    return compact_len >= int(threshold * long_ratio)


def _attach_codex_native_fast_path_policy(seg: dict, *, llm_called: bool, reason: str) -> dict:
    out = dict(seg)
    out["_codex_native_fast_path_policy"] = {
        "schema": "ai_subtitle_studio.codex_native_fast_path.v1",
        "task": "subtitle_codex_native_fast_path",
        "llm_called": bool(llm_called),
        "reason": str(reason or ""),
    }
    return out


def _subtitle_native_prepass_worker_plan(settings: dict, workload: int) -> tuple[int, dict]:
    requested = (
        _setting_int(settings, "subtitle_native_prepass_workers", 0)
        or _setting_int(settings, "io_workers", 0)
        or _setting_int(settings, "llm_threads_resource_max", 0)
        or 1
    )
    maximum = (
        _setting_int(settings, "subtitle_native_prepass_workers_resource_max", 0)
        or _setting_int(settings, "io_workers", 0)
        or None
    )
    return runtime_parallel_worker_plan(
        settings=settings,
        task="subtitle_prepass",
        workload=max(1, int(workload or 1)),
        requested=requested,
        minimum=1,
        maximum=maximum,
        reserve_task="subtitle_prepass",
        accelerators=["cpu"],
    )


def _preprocess_lora_deep_without_llm(
    segments: list[dict],
    *,
    rules: dict,
    threshold: int,
    corrections: dict,
    user_prompt: str,
    settings: dict,
) -> list[dict]:
    input_rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    if not input_rows:
        return []

    def run_one(index: int, seg: dict) -> list[dict]:
        try:
            return list(
                _process_one(
                    (
                        dict(seg),
                        rules,
                        threshold,
                        corrections,
                        "사용 안함 (LoRA/Deep fast prepass)",
                        user_prompt,
                        "",
                        False,
                        settings,
                    )
                )
            )
        except Exception as exc:
            get_logger().log(f"[LoRA/Deep-전처리] 실패: {exc}")
            text = _clean(str(seg.get("text", "") or ""), corrections)
            if text:
                return [{**dict(seg), "text": text}]
            return []

    workers, scheduler = _subtitle_native_prepass_worker_plan(settings, len(input_rows))
    if workers <= 1 or len(input_rows) <= 1:
        preprocessed: list[dict] = []
        for index, seg in enumerate(input_rows):
            preprocessed.extend(run_one(index, seg))
        return preprocessed

    get_logger().log(
        f"[LoRA/Deep-전처리] Apple M 병렬 전처리: {workers}개 워커 "
        f"({len(input_rows)}개, {scheduler.get('reason', 'runtime')})"
    )
    result_map: dict[int, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(input_rows))), thread_name_prefix="subtitle-prepass") as ex:
        futures = {ex.submit(run_one, index, seg): index for index, seg in enumerate(input_rows)}
        for fut in as_completed(futures):
            index = futures[fut]
            try:
                result_map[index] = fut.result()
            except Exception as exc:
                get_logger().log(f"[LoRA/Deep-전처리] 병렬 작업 실패: {exc}")
                result_map[index] = []
    preprocessed: list[dict] = []
    for index in range(len(input_rows)):
        preprocessed.extend(result_map.get(index, []))
    return preprocessed


def _build_llm_review_gates(
    rows: list[dict],
    *,
    rules: dict,
    threshold: int,
    settings: dict,
    codex_native_fast_path: bool,
) -> tuple[list[bool], list[dict]]:
    input_rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
    if not input_rows:
        return [], []

    def run_one(index: int, row: dict) -> tuple[bool, dict]:
        needs, gated = _segment_needs_llm_review(row, rules, threshold, settings)
        if codex_native_fast_path:
            fast_needs = _codex_native_fast_path_needs_llm(gated, needs, settings)
            reason = "precision_or_conflict" if fast_needs else "bulk_native_rules"
            gated = _attach_codex_native_fast_path_policy(gated, llm_called=fast_needs, reason=reason)
            needs = fast_needs
        return bool(needs), gated

    workers, scheduler = _subtitle_native_prepass_worker_plan(settings, len(input_rows))
    if workers <= 1 or len(input_rows) <= 1:
        pairs = [run_one(index, row) for index, row in enumerate(input_rows)]
    else:
        get_logger().log(
            f"[LLM-게이트] Apple M 병렬 선별: {workers}개 워커 "
            f"({len(input_rows)}개, {scheduler.get('reason', 'runtime')})"
        )
        result_map: dict[int, tuple[bool, dict]] = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(input_rows))), thread_name_prefix="subtitle-gate") as ex:
            futures = {ex.submit(run_one, index, row): index for index, row in enumerate(input_rows)}
            for fut in as_completed(futures):
                index = futures[fut]
                try:
                    result_map[index] = fut.result()
                except Exception as exc:
                    get_logger().log(f"[LLM-게이트] 병렬 선별 실패: {exc}")
                    result_map[index] = (True, input_rows[index])
        pairs = [result_map.get(index, (True, input_rows[index])) for index in range(len(input_rows))]

    needs_llm = [item[0] for item in pairs]
    gated_rows = [item[1] for item in pairs]
    return needs_llm, gated_rows


def _llm_macro_callbacks() -> dict:
    return {
        "clean_text": _clean,
        "segment_lora_runtime": _segment_lora_runtime,
        "setting_int": _setting_int,
        "apply_llm_confidence_gate": _apply_llm_confidence_gate,
        "attach_lora_and_deep_timing": _attach_lora_and_deep_timing,
        "build_llm_candidate_options": build_llm_candidate_options,
        "ask_gemini_to_split": ask_gemini_to_split,
        "ask_openai_to_split": ask_openai_to_split,
        "ask_exaone_to_split": ask_exaone_to_split,
        "is_openai_model": is_openai_model,
        "verify_llm_chunks": _verify_llm_chunks,
        "deep_rerank_chunks": _deep_rerank_chunks,
        "llm_context_pack_for_rows": _llm_context_pack_for_rows,
        "emit_llm_progress": _emit_llm_progress,
        "logger": get_logger(),
    }


def _llm_macro_response_cache_diagnostics(rows: list[dict]) -> dict:
    policies = [
        dict(row.get("_llm_macro_chunk_policy") or {})
        for row in list(rows or [])
        if isinstance(row, dict) and isinstance(row.get("_llm_macro_chunk_policy"), dict)
    ]
    if not policies:
        return {}

    def groups_with(flag: str) -> set[str]:
        groups: set[str] = set()
        for row_index, policy in enumerate(policies):
            if not bool(policy.get(flag)):
                continue
            group = policy.get("group_index")
            groups.add(str(group if group is not None else row_index))
        return groups

    return {
        "schema": "ai_subtitle_studio.llm_macro_response_cache_diagnostics.v1",
        "response_cache_enabled": any(bool(policy.get("llm_response_cache_enabled")) for policy in policies),
        "response_cache_hit_group_count": len(groups_with("llm_response_cache_hit")),
        "response_cache_write_group_count": len(groups_with("llm_response_cache_write")),
        "provider_called_group_count": len(groups_with("llm_provider_called")),
    }


def optimize_segments(
    segments: list[dict],
    vad_segments: list[dict] | None = None,
    llm_progress_callback=None,
    stage_segments_callback=None,
) -> list[dict]:
    if not segments:
        return segments
    original_segments = [dict(seg) for seg in segments if isinstance(seg, dict)]
    loaded_settings, rules, model, corrections, threshold, user_prompt, api_key, _raw_corr, _settings = _optimizer_context()
    llm_disabled_final = _llm_model_disabled(model)
    short_m = model.split(":")[0].upper()

    def _resolve_model_for_llm_call() -> str:
        nonlocal model, short_m
        model = _resolve_runtime_llm_model(model, logger=get_logger(), context="자막 LLM")
        short_m = model.split(":")[0].upper()
        return model

    def _prepare_llm_workers_for_call() -> tuple[int, str]:
        resolved_model = _resolve_model_for_llm_call()
        max_workers, worker_mode = _effective_llm_workers(resolved_model, _EXAONE_WORKERS, loaded_settings, len(args))
        if worker_mode == "api":
            get_logger().log(f"🤖 {short_m} API 안전 모드: {max_workers}개 워커 순차 처리 중...")
        elif worker_mode == "local_auto":
            warmup_ollama_model(resolved_model, logger=get_logger())
            get_logger().log(
                f"{short_m} 리소스 자동 모드: {max_workers}개 워커 병렬 처리 "
                f"({len(segments)}개, CPU/메모리/작업량 기준)"
            )
        else:
            warmup_ollama_model(resolved_model, logger=get_logger())
            configured_workers = max(1, min(_EXAONE_WORKERS, len(args)))
            if max_workers < configured_workers:
                get_logger().log(
                    f"{short_m} 로컬 Ollama 안전 모드: {max_workers}개 워커 병렬 처리 "
                    f"(설정 {_EXAONE_WORKERS} → 제한 {max_workers}, {len(segments)}개)"
                )
            else:
                get_logger().log(f"{short_m} {max_workers}개 워커 병렬 처리 ({len(segments)}개)...")
        return max_workers, worker_mode

    get_logger().log(f"\n━━━ 자막 최적화 시작 ({len(segments)}개 세그먼트) ━━━")
    get_logger().log(
        f"설정 적용: LLM({model}), 간격 설정은 최종 패스에서 적용"
    )
    segments = _annotate_stt_candidate_context([dict(seg) for seg in original_segments])
    segments, uncertainty_plan = annotate_uncertainty_first_segments(segments, loaded_settings)
    segments = _attach_llm_context_windows(segments, vad_segments or [], loaded_settings)
    process_order = list(uncertainty_plan.get("process_order") or range(len(segments)))
    if uncertainty_plan.get("enabled"):
        counts = dict(uncertainty_plan.get("bucket_counts") or {})
        get_logger().log(
            "[불확실도 스케줄러] "
            f"빠른확정 {counts.get('easy', 0)}개, 일반 {counts.get('normal', 0)}개, "
            f"정밀대상 {counts.get('precision', 0)}개 순서로 처리합니다."
        )

    conservative = _quality_conservative_enabled(loaded_settings)
    if conservative:
        get_logger().log("[LLM-보수Profile] 자막 품질 검사/자동교정 보호 규칙을 적용합니다.")
    if runtime_lora_enabled(loaded_settings):
        get_logger().log("[텍스트 LoRA] 자동 교정 허용: 교정 memory/오답 memory/사용자 단어/줄바꿈 규칙을 최종 LLM에 적용합니다.")

    def _build_process_args() -> list[tuple]:
        return [(seg, rules, threshold, corrections, model, user_prompt, api_key, conservative, loaded_settings) for seg in segments]

    args = _build_process_args()
    optimized: list[dict] = []

    if llm_disabled_final:
        get_logger().log("⏩ LLM 미사용: 최종 자막은 원본 STT 텍스트를 유지하고 간격 패스만 적용합니다...")
        result_map: dict[int, list] = {}
        for idx in process_order:
            a = args[idx]
            try:
                result_map[idx] = _process_one_llm_only(a)
            except Exception as e:
                get_logger().log(f"LLM 처리 오류: {e}")
                result_map[idx] = [segments[idx]]
        for i in range(len(args)):
            optimized.extend(result_map.get(i, []))
        _emit_processing_preview(
            stage_segments_callback,
            stage="proofread_dictionary",
            stage_label="검사/교정/단어사전 반영",
            segments=optimized,
        )

    else:
        codex_native_fast_path = _codex_native_fast_path_enabled(model, loaded_settings, len(args))
        use_macro_chunks = _llm_macro_chunk_enabled(loaded_settings, model, len(segments)) or codex_native_fast_path
        if codex_native_fast_path:
            get_logger().log(
                "[Codex-네이티브가드] 대량 자막은 로컬 규칙/LoRA/Deep으로 먼저 확정하고 "
                "정밀 검수 대상만 Codex CLI로 보냅니다."
            )

        if use_macro_chunks:
            preprocessed = _preprocess_lora_deep_without_llm(
                segments,
                rules=rules,
                threshold=threshold,
                corrections=corrections,
                user_prompt=user_prompt,
                settings=loaded_settings,
            )
            needs_llm, gated_rows = _build_llm_review_gates(
                preprocessed,
                rules=rules,
                threshold=threshold,
                settings=loaded_settings,
                codex_native_fast_path=codex_native_fast_path,
            )
            llm_rows = sum(1 for item in needs_llm if item)
            fast_lane_rows = max(0, len(gated_rows) - llm_rows)
            strong_fast_rows = sum(
                1
                for row in gated_rows
                if dict(row.get("_llm_gate_policy") or {}).get("strong_fast_lane")
            )
            get_logger().log(
                f"[LLM-게이트] 전체 {len(gated_rows)}개 중 LLM 후보 {llm_rows}개, "
                f"LoRA/Deep/STT 확정 {fast_lane_rows}개"
                + (f" (강신뢰 fast-lane {strong_fast_rows}개)" if strong_fast_rows else "")
            )
            if codex_native_fast_path:
                codex_rows = sum(1 for item in needs_llm if item)
                native_rows = max(0, len(gated_rows) - codex_rows)
                get_logger().log(
                    f"[Codex-네이티브가드] Codex 호출 후보 {codex_rows}개, "
                    f"네이티브 확정 {native_rows}개"
                )
            groups = _build_llm_macro_groups(gated_rows, needs_llm, loaded_settings)
            max_workers = 1
            if llm_rows > 0:
                provider_required = _llm_macro_groups_require_provider_call(
                    groups,
                    rules=rules,
                    threshold=threshold,
                    corrections=corrections,
                    model=model,
                    user_prompt=user_prompt,
                    conservative=conservative,
                    settings=loaded_settings,
                    callbacks=_llm_macro_callbacks(),
                )
                if provider_required:
                    max_workers, _worker_mode = _prepare_llm_workers_for_call()
                else:
                    get_logger().log("[LLM-묶음처리] 모든 LLM 후보가 응답 캐시에 있어 Ollama 준비를 생략합니다.")
            optimized = _process_llm_macro_groups(
                groups,
                rules=rules,
                threshold=threshold,
                corrections=corrections,
                model=model,
                user_prompt=user_prompt,
                api_key=api_key,
                conservative=conservative,
                settings=loaded_settings,
                max_workers=max_workers,
                callbacks=_llm_macro_callbacks(),
                llm_progress_callback=llm_progress_callback,
            )
            _emit_processing_preview(
                stage_segments_callback,
                stage="proofread_dictionary_llm",
                stage_label="검사/교정/단어사전/LLM 반영",
                segments=optimized,
                diagnostics=_llm_macro_response_cache_diagnostics(optimized),
            )
        else:
            max_workers, _worker_mode = _prepare_llm_workers_for_call()
            args = _build_process_args()

        if not use_macro_chunks and max_workers == 1:
            result_map: dict[int, list] = {}
            for idx in process_order:
                a = args[idx]
                try:
                    _emit_llm_progress(llm_progress_callback, active=True, idx=idx, total=len(args), seg=segments[idx])
                    result_map[idx] = _process_one_llm_only(a)
                except Exception as e:
                    get_logger().log(f"LLM 처리 오류: {e}")
                    result_map[idx] = [segments[idx]]
            for i in range(len(args)):
                optimized.extend(result_map.get(i, []))
            _emit_processing_preview(
                stage_segments_callback,
                stage="proofread_dictionary_llm",
                stage_label="검사/교정/단어사전/LLM 반영",
                segments=optimized,
            )
        elif not use_macro_chunks:
            try:
                def _process_with_progress(index: int, arg):
                    _emit_llm_progress(llm_progress_callback, active=True, idx=index, total=len(args), seg=segments[index])
                    return _process_one_llm_only(arg)

                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="llm") as ex:
                    futures = {ex.submit(_process_with_progress, i, args[i]): i for i in process_order}
                    result_map: dict[int, list] = {}

                    for fut in as_completed(futures):
                        idx = futures[fut]
                        try:
                            result_map[idx] = fut.result()
                        except Exception as e:
                            get_logger().log(f"LLM 처리 오류: {e}")
                            result_map[idx] = [segments[idx]]

                for i in range(len(args)):
                    optimized.extend(result_map.get(i, []))
                _emit_processing_preview(
                    stage_segments_callback,
                    stage="proofread_dictionary_llm",
                    stage_label="검사/교정/단어사전/LLM 반영",
                    segments=optimized,
                )

            except Exception as e:
                get_logger().log(f"LLM 처리 오류: {e}")
                optimized = segments

    optimized = adjust_timing(optimized)
    _emit_processing_preview(
        stage_segments_callback,
        stage="timing_adjust",
        stage_label="자막 시작/끝 시간 보정",
        segments=optimized,
    )
    if not optimized and any(seg.get("stt_candidates") for seg in original_segments):
        get_logger().log("[STT앙상블-보호] 후보 병합 결과가 모두 제거되어 원본 앙상블 세그먼트로 최종 자막을 복구합니다.")
        fallback = []
        for seg in _annotate_stt_candidate_context(original_segments):
            try:
                processed = _process_one_llm_only((seg, rules, threshold, corrections, model, user_prompt, api_key, conservative, loaded_settings))
            except Exception:
                processed = [{**seg, "text": _clean(str(seg.get("text", "") or ""), corrections)}]
            for item in processed or []:
                if str(item.get("text", "") or "").strip():
                    fallback.append(item)
        optimized = adjust_timing(fallback)
        _emit_processing_preview(
            stage_segments_callback,
            stage="timing_adjust_fallback",
            stage_label="자막 시작/끝 시간 복구",
            segments=optimized,
        )

    high_context_diagnostics: dict = {}
    optimized = refine_high_contextual_boundaries(
        optimized,
        vad_segments=vad_segments or [],
        settings=loaded_settings,
        rules=rules,
        model=model,
        logger=get_logger(),
        diagnostics_out=high_context_diagnostics,
    )
    _emit_processing_preview(
        stage_segments_callback,
        stage="high_context_boundary",
        stage_label="High 문맥 경계/단어 보정",
        segments=optimized,
        diagnostics=high_context_diagnostics,
    )

    optimized = _smooth_deep_sequence(optimized, loaded_settings)
    _emit_processing_preview(
        stage_segments_callback,
        stage="deep_split",
        stage_label="분할/묶음 정리",
        segments=optimized,
    )
    optimized = apply_final_gap_settings(optimized, loaded_settings, force=False)
    _emit_processing_preview(
        stage_segments_callback,
        stage="final_gap",
        stage_label="자막 간격 정리",
        segments=optimized,
    )
    optimized = align_stt_candidates_to_subtitle_segments(optimized)
    optimized = _self_review_subtitle_quality(optimized, vad_segments or [], loaded_settings)
    optimized = _annotate_context_consistency(optimized, loaded_settings)
    if llm_disabled_final:
        optimized = _restore_no_llm_raw_stt_text(optimized, original_segments, loaded_settings)
    else:
        optimized = _apply_output_variant_selector(optimized, original_segments, vad_segments or [], loaded_settings, stage="llm")
    optimized = _enforce_final_subtitle_text_policy(optimized, corrections)
    optimized = _apply_final_sequence_cleanup(optimized, loaded_settings, stage="llm_final")
    optimized = _restore_final_stt_anchor_drift(optimized, original_segments, loaded_settings, stage="llm_final")
    optimized = _restore_final_stt_slot_order_drift(optimized, original_segments, loaded_settings, stage="llm_final")
    optimized = _restore_missing_final_stt_anchor_rows(optimized, original_segments, loaded_settings, stage="llm_final")
    _emit_processing_preview(
        stage_segments_callback,
        stage="context_review",
        stage_label="문맥/출력 보정",
        segments=optimized,
    )
    optimized = _apply_lora_card_packaging(optimized, loaded_settings, rules, stage="llm")
    _emit_processing_preview(
        stage_segments_callback,
        stage="packaging",
        stage_label="줄바꿈/카드 포장",
        segments=optimized,
    )
    optimized = _annotate_auto_review(optimized, loaded_settings)
    optimized = _annotate_stage_confidence(optimized, loaded_settings)
    optimized = _annotate_completion_report(optimized, loaded_settings)
    optimized = _enforce_final_subtitle_text_policy(optimized, None)
    optimized = _expand_non_speaker_multiline_segments(optimized, loaded_settings)
    optimized = _final_transcript_integrity_guard(optimized, original_segments, vad_segments or [], loaded_settings)
    optimized = _restore_final_stt_slot_order_drift(optimized, original_segments, loaded_settings, stage="post_integrity")
    if llm_disabled_final:
        optimized = _restore_no_llm_raw_stt_text(optimized, original_segments, loaded_settings)
        optimized = _restore_missing_final_stt_anchor_rows(
            optimized,
            original_segments,
            loaded_settings,
            stage="no_llm_raw_text_lock",
        )
    optimized = _apply_final_vad_voice_start_priority(optimized, vad_segments or [], loaded_settings, stage="llm_final")
    _emit_processing_preview(
        stage_segments_callback,
        stage="final_integrity_guard",
        stage_label="최종 자막/STT 원문 무결성 확인",
        segments=optimized,
    )
    _log_accuracy_metrics(optimized, loaded_settings)
    _record_deep_policy_learning(optimized, loaded_settings)
    _emit_llm_progress(llm_progress_callback, active=False)
    get_logger().log(f"━━━ 자막 최적화 완료: {len(optimized)}개 ━━━\n")
    return optimized

def save_srt(
    segments: list[dict],
    srt_path: str,
    apply_offset: bool = True,
    fps: float | int | str | None = None,
    write_backup: bool = True,
):
    from core.engine.srt_writer import save_srt as _save_srt
    return _save_srt(
        segments,
        srt_path,
        apply_offset=apply_offset,
        adjust_timing_func=adjust_timing,
        fps=fps,
        write_backup=write_backup,
    )

def ask_gemini_to_split(
    text: str,
    threshold: int,
    rules: dict,
    model_name: str,
    user_prompt: str,
    api_key: str,
    conservative: bool = False,
    settings: dict | None = None,
    candidate_options: list[dict] | None = None,
    context_pack: dict | None = None,
) -> list[str] | None:
    if not api_key:
        get_logger().log("❌ API 키가 없습니다. 환경설정에서 Google API Key를 입력해주세요.")
        return None

    try:
        chunks = gemini_split_text(
            api_key,
            model_name,
            _build_llm_prompt(
                text,
                threshold,
                rules,
                user_prompt,
                conservative=conservative,
                settings=settings,
                candidate_options=candidate_options,
                context_pack=context_pack,
            ),
        )
    except Exception:
        return [text]

    final_chunks = _clean_llm_output_chunks(chunks)
    return final_chunks or None
