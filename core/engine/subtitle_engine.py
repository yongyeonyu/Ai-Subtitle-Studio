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


def ensure_ollama_server(*args, **kwargs):
    from core.llm.ollama_provider import ensure_ollama_server as _ensure_ollama_server

    return _ensure_ollama_server(*args, **kwargs)


def restart_ollama_server(*args, **kwargs):
    from core.llm.ollama_provider import restart_ollama_server as _restart_ollama_server

    return _restart_ollama_server(*args, **kwargs)


def _clean_llm_output_chunks(chunks) -> list[str]:
    final_chunks: list[str] = []
    for chunk in chunks or []:
        if not isinstance(chunk, str):
            continue
        cleaned = _clean(chunk)
        if cleaned and len(cleaned.replace(" ", "").replace("\n", "")) >= 2:
            final_chunks.append(cleaned)
    return final_chunks


def _short_log_text_preview(text: str, limit: int = 15) -> str:
    return str(text or "")[:limit]


def ollama_split_text(*args, **kwargs):
    from core.llm.ollama_provider import split_text as _ollama_split_text

    return _ollama_split_text(*args, **kwargs)


def warmup_ollama_model(*args, **kwargs):
    from core.llm.ollama_provider import warmup_model as _warmup_ollama_model

    return _warmup_ollama_model(*args, **kwargs)


def _effective_llm_workers(model: str, configured_workers: int, settings: dict, segment_count: int) -> tuple[int, str]:
    return _effective_llm_workers_impl(model, configured_workers, settings, segment_count, local_worker_cap=_LOCAL_OLLAMA_WORKER_CAP)

# ━━━ 🛠️ [시스템 고정 상수] ━━━
_ENFORCE_RATIO   = 1.5   
_LLM_SKIP_DUR    = 1.0
_LOCAL_LLM_BACKOFF_SEC = 60.0
_LOCAL_LLM_UNAVAILABLE_UNTIL = 0.0
_LOCAL_LLM_LOCK = threading.Lock()
_FINAL_FILLER_FRAGMENTS = {
    "네",
    "네네",
    "예",
    "예예",
    "응",
    "음",
    "어",
    "아",
    "오",
    "와",
}
_FINAL_CLOSING_PHRASES = {"감사합니다", "고맙습니다"}
_FINAL_DUPLICATE_BRIDGE_TOKENS = {
    "그래서",
    "여기까지",
    "여기까지고",
    "지금까지",
}
_FINAL_CONTINUATION_TAIL_RE = re.compile(
    r"(고|서|데|는데|니까|지만|면서|려고|라서|해서|이며|이고|하고)$"
)


def _is_local_llm_connection_error(exc: BaseException) -> bool:
    text = str(exc or "").lower()
    return any(
        fragment in text
        for fragment in (
            "connection refused",
            "errno 61",
            "urlopen error",
            "failed to establish",
            "connection aborted",
            "connection reset",
            "timed out",
        )
    )


def _mark_local_llm_unavailable(model: str, context: str, reason: str) -> None:
    global _LOCAL_LLM_UNAVAILABLE_UNTIL
    now = time.monotonic()
    should_log = False
    with _LOCAL_LLM_LOCK:
        if _LOCAL_LLM_UNAVAILABLE_UNTIL <= now:
            should_log = True
        _LOCAL_LLM_UNAVAILABLE_UNTIL = now + _LOCAL_LLM_BACKOFF_SEC
    if should_log:
        get_logger().log(
            f"[{context}] Ollama 연결 실패: {reason}. "
            f"로컬 LLM 단계를 {int(_LOCAL_LLM_BACKOFF_SEC)}초 동안 건너뛰고 STT 결과로 계속 진행합니다. "
            f"Ollama 앱/서버와 모델({model})을 확인해 주세요."
        )


def _local_ollama_ready(model: str, context: str) -> bool:
    now = time.monotonic()
    with _LOCAL_LLM_LOCK:
        if _LOCAL_LLM_UNAVAILABLE_UNTIL > now:
            return False
    if ensure_ollama_server(logger=get_logger(), wait_sec=1.5):
        return True
    if restart_ollama_server(logger=get_logger(), wait_sec=6.0):
        return True
    _mark_local_llm_unavailable(model, context, "서버 응답 없음")
    return False

def is_natural_break(word: str, next_word: str, rules: dict) -> bool:
    w_clean = re.sub(r'[^\w가-힣]', '', word) 
    nw_clean = re.sub(r'[^\w가-힣]', '', next_word)
    
    ew = rules.get("end_words",   [])
    sw = rules.get("start_words", [])
    if ew and re.search(r"(" + "|".join(re.escape(w) for w in ew) + r")$", w_clean):
        return True
    if sw and re.match(r"^(" + "|".join(re.escape(w) for w in sw) + r")", nw_clean):
        return True
    return False


def ask_exaone_to_split(
    text: str,
    threshold: int,
    rules: dict,
    model: str,
    user_prompt: str,
    conservative: bool = False,
    settings: dict | None = None,
    candidate_options: list[dict] | None = None,
    context_pack: dict | None = None,
) -> list[str] | None:
    if "사용 안함" in model:
        return None
    if not _local_ollama_ready(model, "자막 LLM"):
        return None
    model = _resolve_runtime_llm_model(model, logger=get_logger(), context="자막 LLM")

    prompt = _build_llm_prompt(
        text,
        threshold,
        rules,
        user_prompt,
        conservative=conservative,
        settings=settings,
        candidate_options=candidate_options,
        context_pack=context_pack,
    )

    try:
        chunks = ollama_split_text(model, prompt) or []
        final_chunks = _clean_llm_output_chunks(chunks)
        return final_chunks or None

    except Exception as e:
        if _is_local_llm_connection_error(e):
            _mark_local_llm_unavailable(model, "자막 LLM", str(e))
            return None
        get_logger().log(f"[LLM 연결/파싱 실패] 모델={model} / {e}")
        return None

def ask_openai_to_split(
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
    if not api_key and not is_codex_model(model_name):
        get_logger().log("❌ API 키가 없습니다. 환경설정에서 OpenAI API Key를 입력해주세요.")
        return None
    if is_codex_model(model_name):
        get_logger().log("🤖 Codex CLI 구독 인증으로 자막 LLM을 실행합니다. 자막 텍스트가 Codex/OpenAI로 전송될 수 있습니다.")
    try:
        chunks = openai_split_text(
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
    except Exception as e:
        get_logger().log(f"[OpenAI 연결/파싱 실패] {e}")
        return None
    final_chunks = _clean_llm_output_chunks(chunks)
    return final_chunks or None


def _profile_from_settings(settings: dict | None) -> dict:
    return dict((settings or {}).get("_lora_generation_profile") or {})


def _setting_bool(settings: dict | None, key: str, default: bool = True) -> bool:
    value = (settings or {}).get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
    return bool(value)


def _accuracy_graph_enabled(settings: dict | None) -> bool:
    return _setting_bool(settings, "accuracy_decision_graph_enabled", True)


def _append_accuracy_decision_for_settings(lora_meta: dict | None, decision: dict | None, settings: dict | None) -> dict:
    if not _accuracy_graph_enabled(settings):
        return dict(lora_meta or {})
    return append_accuracy_decision(lora_meta or {}, decision)


def _deep_rerank_chunks(text: str, chunks: list[str] | None, settings: dict | None, lora_meta: dict | None) -> tuple[list[str] | None, dict]:
    if not chunks:
        return chunks, dict(lora_meta or {})
    original_chunks = list(chunks)
    candidates = [list(chunks)]
    compact_original = re.sub(r"\s+", "", str(text or ""))
    compact_chunks = re.sub(r"\s+", "", "".join(str(chunk or "") for chunk in chunks))
    if compact_original and compact_original != compact_chunks:
        candidates.append([str(text or "").strip()])
    ranked, meta = rerank_subtitle_candidates(text, candidates, settings or {}, _profile_from_settings(settings))
    out_meta = dict(lora_meta or {})
    if meta:
        out_meta["_deep_rerank_policy"] = meta
    if not ranked:
        return original_chunks, out_meta

    guard_settings = {
        **dict(settings or {}),
        "llm_verifier_enabled": True,
        "llm_verifier_block_added_content_tokens": True,
        "llm_verifier_preserve_numbers": True,
        "llm_verifier_preserve_interjections": True,
        "llm_verifier_min_similarity": max(
            0.9,
            _setting_float(settings or {}, "llm_verifier_min_similarity", 0.86),
        ),
        "llm_verifier_max_length_delta_ratio": min(
            0.10,
            _setting_float(settings or {}, "llm_verifier_max_length_delta_ratio", 0.16),
        ),
    }
    verified, decision = verify_llm_chunks_for_subtitle(
        text,
        ranked,
        guard_settings,
        _profile_from_settings(settings),
    )
    out_meta = _append_accuracy_decision_for_settings(out_meta, decision, settings)
    out_meta["_deep_rerank_verifier_policy"] = decision
    if verified is None:
        rollback = rollback_decision(str(decision.get("reason") or "deep_rerank_integrity_rejected"), fallback="pre_verified_chunks")
        out_meta = _append_accuracy_decision_for_settings(out_meta, rollback, settings)
        out_meta["_deep_rerank_rollback_policy"] = rollback
        rerank_policy = dict(out_meta.get("_deep_rerank_policy") or {})
        rerank_policy.update(
            {
                "accepted": False,
                "reason": str(decision.get("reason") or "deep_rerank_integrity_rejected"),
                "fallback": "pre_verified_chunks",
            }
        )
        out_meta["_deep_rerank_policy"] = rerank_policy
        get_logger().log(
            "[딥러닝-재정렬차단] 검증 이후 청크가 STT 원문을 벗어나 이전 안전 청크로 복구 "
            f"({describe_llm_verifier_decision(decision)}): '{_short_log_text_preview(text)}...'"
        )
        return original_chunks, out_meta
    return verified, out_meta


def _apply_llm_confidence_gate(
    seg: dict,
    text: str,
    threshold: int,
    duration: float,
    settings: dict | None,
    lora_meta: dict | None,
) -> tuple[bool, dict]:
    decision = llm_gate_decision(
        seg,
        settings or {},
        _profile_from_settings(settings),
        text=text,
        threshold=threshold,
        duration=duration,
    )
    out_meta = _append_accuracy_decision_for_settings(lora_meta or {}, decision, settings)
    out_meta["_llm_gate_policy"] = decision
    minimize = llm_minimize_decision(seg, settings or {}, decision)
    out_meta = _append_accuracy_decision_for_settings(out_meta, minimize, settings)
    out_meta["_llm_minimize_policy"] = minimize
    if not decision.get("call_llm", True):
        lora_score = float(decision.get("lora_score", 0.0) or 0.0)
        combined_signal = float(decision.get("combined_signal_score", lora_score) or 0.0)
        deep_score = float(decision.get("deep_score", 0.0) or 0.0)
        stt_score = float(decision.get("stt_score", 0.0) or 0.0)
        confidence = float(decision.get("confidence", 0.0) or 0.0)
        compact_ratio = float(decision.get("compact_ratio", 0.0) or 0.0)
        get_logger().log(
            f"[LLM-게이트] LoRA/딥러닝 신뢰로 LLM 생략 "
            f"(lora={lora_score:.1f}, signal={combined_signal:.1f}, deep={deep_score:.1f}, "
            f"stt={stt_score:.1f}, confidence={confidence:.2f}, ratio={compact_ratio:.4f}): "
            f"'{str(text or '')[:15]}...'"
        )
    return bool(decision.get("call_llm", True)), out_meta


def _verify_llm_chunks(
    text: str,
    chunks: list[str] | None,
    settings: dict | None,
    lora_meta: dict | None,
    *,
    fallback: str,
    candidate_options: list[dict] | None = None,
    duration_sec: float | None = None,
    context_pack: dict | None = None,
) -> tuple[list[str] | None, dict]:
    out_meta = dict(lora_meta or {})
    if not chunks:
        _verified, decision = verify_llm_chunks_for_subtitle(
            text,
            [],
            settings or {},
            _profile_from_settings(settings),
            duration_sec=duration_sec,
        )
        out_meta = _append_accuracy_decision_for_settings(out_meta, decision, settings)
        out_meta["_llm_verifier_policy"] = decision
        rollback = rollback_decision(str(decision.get("reason") or "empty_chunks"), fallback=fallback)
        out_meta = _append_accuracy_decision_for_settings(out_meta, rollback, settings)
        out_meta["_llm_rollback_policy"] = rollback
        get_logger().log(
            f"[LLM-롤백] 실제 빈 출력/파싱 실패({decision.get('reason')}), "
            f"안전 분할로 복구: '{_short_log_text_preview(text)}...'"
        )
        return None, out_meta
    candidate_checked, candidate_decision = validate_candidate_locked_chunks(
        text,
        chunks,
        candidate_options,
        settings or {},
    )
    out_meta = _append_accuracy_decision_for_settings(out_meta, candidate_decision, settings)
    out_meta["_llm_candidate_policy"] = candidate_decision
    if candidate_checked is None:
        rollback = rollback_decision(str(candidate_decision.get("reason") or "candidate_policy_rejected"), fallback=fallback)
        out_meta = _append_accuracy_decision_for_settings(out_meta, rollback, settings)
        out_meta["_llm_rollback_policy"] = rollback
        get_logger().log(
            "[LLM-후보잠금] 후보 밖 출력 차단 "
            f"({candidate_decision.get('reason')}): '{str(text or '')[:15]}...'"
        )
        return None, out_meta

    if context_pack and _setting_bool(settings, "subtitle_llm_prev_next_context_enabled", True):
        context_decision = evaluate_subtitle_llm_context_gate_via_swift(
            text,
            candidate_checked,
            context_pack,
            settings=settings or {},
        )
        out_meta = _append_accuracy_decision_for_settings(out_meta, context_decision, settings)
        out_meta["_llm_context_gate_policy"] = context_decision
        if not bool(context_decision.get("accepted", False)):
            rollback = rollback_decision(str(context_decision.get("reason") or "llm_context_gate_rejected"), fallback=fallback)
            out_meta = _append_accuracy_decision_for_settings(out_meta, rollback, settings)
            out_meta["_llm_rollback_policy"] = rollback
            get_logger().log(
                "[LLM-문맥잠금] 이전/현재/다음 STT/VAD 문맥과 어긋난 출력 차단 "
                f"({context_decision.get('reason')}): '{str(text or '')[:15]}...'"
            )
            return None, out_meta

    verified, decision = verify_llm_chunks_for_subtitle(
        text,
        candidate_checked,
        settings or {},
        _profile_from_settings(settings),
        duration_sec=duration_sec,
    )
    out_meta = _append_accuracy_decision_for_settings(out_meta, decision, settings)
    out_meta["_llm_verifier_policy"] = decision
    if verified is None and chunks:
        rollback = rollback_decision(str(decision.get("reason") or "unknown"), fallback=fallback)
        out_meta = _append_accuracy_decision_for_settings(out_meta, rollback, settings)
        out_meta["_llm_rollback_policy"] = rollback
        detail = describe_llm_verifier_decision(decision)
        get_logger().log(f"[LLM-보정차단] 원문 무결성 검사 실패({detail}): '{_short_log_text_preview(text)}...'")
        get_logger().log(f"[LLM-롤백] 검증 실패 후 복구({detail}), 안전 분할로 복구: '{_short_log_text_preview(text)}...'")
    return verified, out_meta


def _log_accuracy_metrics(segments: list[dict], settings: dict | None) -> dict:
    summary = subtitle_accuracy_metrics(segments, settings or {})
    if summary.get("enabled") and summary.get("total_segments", 0):
        quality = summary.get("avg_quality_score")
        quality_text = f", 품질 {quality}" if isinstance(quality, (int, float)) else ""
        style = summary.get("lora_style_score")
        style_text = f", LoRA스타일 {style}" if isinstance(style, (int, float)) else ""
        get_logger().log(
            "[자막정확도-요약] "
            f"avg CPS {summary.get('avg_cps', 0)}, "
            f"LoRA {summary.get('lora_applied_segments', 0)}/{summary.get('total_segments', 0)}, "
            f"LLM 생략 {summary.get('llm_gate_skipped_segments', 0)}, "
            f"롤백 {summary.get('llm_verifier_rollbacks', 0)}"
            f"{quality_text}"
            f"{style_text}"
        )
    return summary


def _attach_llm_context_windows(
    segments: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
) -> list[dict]:
    rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    if not rows or not _setting_bool(settings, "subtitle_llm_prev_next_context_enabled", True):
        return rows
    try:
        packs = build_subtitle_llm_context_packs_via_swift(rows, vad_segments or [], settings=settings or {})
    except Exception:
        packs = []
    if len(packs) != len(rows):
        return rows
    out: list[dict] = []
    for row, pack in zip(rows, packs, strict=False):
        item = dict(row)
        item["_llm_context_pack"] = dict(pack)
        out.append(item)
    return out


def _segment_llm_context_pack(seg: dict | None) -> dict | None:
    pack = dict((seg or {}).get("_llm_context_pack") or {})
    return pack or None


def _current_context_text_from_pack(pack: dict) -> str:
    current = dict(dict(pack.get("window") or {}).get("current") or {})
    return str(current.get("text") or "").strip()


def _llm_context_pack_for_rows(rows: list[dict] | None) -> dict | None:
    packs = [dict(row.get("_llm_context_pack") or {}) for row in list(rows or []) if isinstance(row, dict) and row.get("_llm_context_pack")]
    if not packs:
        return None
    if len(packs) == 1:
        return packs[0]
    current_texts = [_current_context_text_from_pack(pack) for pack in packs]
    current_texts = [text for text in current_texts if text]
    return {
        "schema": "ai_subtitle_studio.subtitle_llm_context_pack.v1",
        "mode": "macro_group",
        "source_pack_count": len(packs),
        "window": {
            "previous": dict(packs[0].get("window") or {}).get("previous") or {},
            "current": {
                "role": "current",
                "exists": True,
                "text": " ".join(current_texts).strip(),
                "candidates": [{"source": "STT_ROWS", "text": text} for text in current_texts],
            },
            "next": dict(packs[-1].get("window") or {}).get("next") or {},
        },
        "constraints": {
            "llm_role": "advisory_only",
            "previous_next_are_context_only": True,
            "current_subtitle_required": True,
        },
    }


def _annotate_context_consistency(segments: list[dict], settings: dict | None) -> list[dict]:
    rows = annotate_subtitle_context_consistency(segments, settings or {})
    risky = sum(1 for row in rows if isinstance(row, dict) and row.get("_context_consistency_policy"))
    if risky:
        get_logger().log(f"[자막문맥-딥러닝진단] 반복/겹침/순서 위험 {risky}개 표시")
    rows = annotate_subtitle_lora_style_consistency(rows, settings or {})
    style_risky = sum(1 for row in rows if isinstance(row, dict) and row.get("_lora_style_policy"))
    if style_risky:
        get_logger().log(f"[LoRA스타일-딥러닝진단] 기존 자막 스타일 이탈 위험 {style_risky}개 표시")
    return rows


def _annotate_auto_review(segments: list[dict], settings: dict | None) -> list[dict]:
    rows = annotate_subtitle_auto_review(segments, settings or {})
    if not rows:
        return rows
    summary = dict(rows[0].get("subtitle_auto_review_summary") or {})
    issue_count = int(summary.get("issue_count", 0) or 0)
    if issue_count:
        severities = dict(summary.get("severity_counts") or {})
        get_logger().log(
            "[자동검수-요약] "
            f"확인 필요 자막 {issue_count}개 "
            f"(빨강 {int(severities.get('red', 0) or 0)}, 노랑 {int(severities.get('yellow', 0) or 0)}), "
            f"예상 검수 {summary.get('estimated_review_min', 0)}분"
        )
    return rows


def _annotate_stage_confidence(segments: list[dict], settings: dict | None) -> list[dict]:
    rows = annotate_subtitle_stage_confidence(segments, settings or {})
    if not rows:
        return rows
    summary = dict(rows[0].get("subtitle_confidence_summary") or {})
    counts = dict(summary.get("label_counts") or {})
    red = int(counts.get("red", 0) or 0)
    yellow = int(counts.get("yellow", 0) or 0)
    if red or yellow:
        get_logger().log(f"[자막신뢰도-단계표시] 빨강 {red}개, 노랑 {yellow}개를 타임라인 표시용으로 저장")
    return rows


def _annotate_completion_report(segments: list[dict], settings: dict | None) -> list[dict]:
    rows = annotate_subtitle_completion_report(segments, settings or {})
    if not rows:
        return rows
    report = dict(rows[0].get("subtitle_completion_report") or {})
    if report:
        get_logger().log(
            "[완료리포트] "
            f"자막 {report.get('total_subtitles', 0)}개, "
            f"빨강 {report.get('red_risk_rows', 0)}개, "
            f"노랑 {report.get('yellow_risk_rows', 0)}개, "
            f"LLM 롤백 {report.get('llm_rollback_count', 0)}개, "
            f"LoRA 적용률 {float(report.get('lora_application_rate', 0.0) or 0.0) * 100:.1f}%, "
            f"예상 검수 {report.get('estimated_review_min', 0)}분"
        )
    return rows


def _compact_output_selector_decision(decision: dict | None, *, stage: str = "") -> dict:
    payload = dict(decision or {})
    compact_variants = []
    for item in list(payload.get("variants") or [])[:4]:
        if not isinstance(item, dict):
            continue
        score_meta = dict(item.get("score_meta") or {})
        metrics = dict(score_meta.get("metrics") or {})
        compact_variants.append(
            {
                "index": item.get("index"),
                "name": item.get("name"),
                "score": item.get("score"),
                "metrics": {
                    "total_segments": metrics.get("total_segments"),
                    "avg_cps": metrics.get("avg_cps"),
                    "avg_quality_score": metrics.get("avg_quality_score"),
                    "high_cps_segments": metrics.get("high_cps_segments"),
                    "llm_verifier_rollbacks": metrics.get("llm_verifier_rollbacks"),
                    "context_consistency_score": metrics.get("context_consistency_score"),
                    "context_repeat_segments": metrics.get("context_repeat_segments"),
                    "context_overlap_segments": metrics.get("context_overlap_segments"),
                    "context_shadow_duplicate_segments": metrics.get("context_shadow_duplicate_segments"),
                    "lora_style_score": metrics.get("lora_style_score"),
                    "lora_style_drift_segments": metrics.get("lora_style_drift_segments"),
                },
            }
        )
    return {
        "schema": payload.get("schema") or "ai_subtitle_studio.subtitle_accuracy_pipeline.v1",
        "task": payload.get("task") or "output_variant_selector",
        "stage": stage,
        "selected_index": payload.get("selected_index"),
        "selected_name": payload.get("selected_name"),
        "selected_score": payload.get("selected_score"),
        "reason": payload.get("reason", ""),
        "variants": compact_variants,
    }


def _attach_output_selector_policy(segments: list[dict], decision: dict | None, settings: dict | None, *, stage: str = "") -> list[dict]:
    rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    if not rows or not isinstance(decision, dict) or not decision:
        return rows
    payload = dict(decision or {})
    variants = list(payload.get("variants") or [])
    if payload.get("task") == "output_variant_selector" and all(
        isinstance(item, dict) and "score_meta" not in item for item in variants
    ):
        compact = dict(payload)
        compact.setdefault("stage", stage)
    else:
        compact = _compact_output_selector_decision(decision, stage=stage)
    rows[0]["_output_selector_policy"] = compact
    if _accuracy_graph_enabled(settings):
        rows[0] = append_accuracy_decision(rows[0], compact)
    return rows


def _attach_context_repair_policy(segments: list[dict], decision: dict | None, settings: dict | None) -> list[dict]:
    rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    if not rows or not isinstance(decision, dict) or not decision:
        return rows
    compact = {
        "schema": decision.get("schema"),
        "task": decision.get("task", "context_repair"),
        "model": decision.get("model"),
        "applied": bool(decision.get("applied")),
        "reason": decision.get("reason", ""),
        "dropped_repeats": decision.get("dropped_repeats", 0),
        "dropped_empty": decision.get("dropped_empty", 0),
        "dropped_hallucinations": decision.get("dropped_hallucinations", 0),
        "dropped_shadow_duplicates": decision.get("dropped_shadow_duplicates", 0),
        "shifted_starts": decision.get("shifted_starts", 0),
        "extended_ends": decision.get("extended_ends", 0),
        "extended_cps_segments": decision.get("extended_cps_segments", 0),
        "before_score": decision.get("before_score"),
        "after_score": decision.get("after_score"),
    }
    rows[0]["_context_repair_policy"] = compact
    if _accuracy_graph_enabled(settings):
        rows[0] = append_accuracy_decision(rows[0], compact)
    return rows


def _bool_setting(settings: dict, key: str, default: bool = True) -> bool:
    value = settings.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔", "미사용"}
    return bool(value)


def _lora_style_merge_settings(settings: dict | None) -> dict:
    settings = dict(settings or {})
    lora_floor_chars = max(8, _setting_int(settings, "subtitle_lora_split_floor_chars", 20))
    max_chars = max(lora_floor_chars, _setting_int(settings, "split_length_threshold", 20))
    min_duration = max(
        _setting_float(settings, "sub_min_duration", 0.3),
        _setting_float(settings, "subtitle_lora_micro_merge_min_duration", 0.8),
    )
    gap_break = max(
        _setting_float(settings, "sub_gap_break_sec", 1.5),
        _setting_float(settings, "subtitle_lora_micro_merge_gap_sec", 1.8),
    )
    word_gap = max(
        _setting_float(settings, "word_timing_gap_break_sec", 0.65),
        _setting_float(settings, "subtitle_lora_micro_merge_word_gap_sec", 1.2),
    )
    continuous = max(
        _setting_float(settings, "continuous_threshold", 2.0),
        _setting_float(settings, "subtitle_lora_micro_merge_continuous_sec", 3.0),
        gap_break,
    )
    return {
        "split_length_threshold": max_chars,
        "sub_min_duration": round(min_duration, 3),
        "sub_gap_break_sec": round(gap_break, 3),
        "word_timing_gap_break_sec": round(word_gap, 3),
        "continuous_threshold": round(continuous, 3),
    }


def _lora_style_merge_mode(settings: dict | None) -> str:
    raw = str(dict(settings or {}).get("subtitle_lora_micro_merge_mode") or "full").strip().lower()
    if raw in {"readability", "readability_selective", "selective"}:
        return "readability_selective"
    return "full"


def _segment_quality_label(segment: dict) -> str:
    quality = dict(segment.get("quality") or {})
    return str(quality.get("confidence_label") or segment.get("subtitle_confidence_label") or "").strip().lower()


def _segment_quality_score(segment: dict) -> float:
    quality = dict(segment.get("quality") or {})
    score = quality.get("confidence_score", segment.get("subtitle_confidence_score"))
    try:
        value = float(score)
    except Exception:
        return 0.0
    if 0.0 <= value <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def _segment_compact_len(segment: dict) -> int:
    return len(re.sub(r"\s+", "", str(segment.get("text", "") or "")))


def _segment_duration(segment: dict) -> float:
    start = _setting_float(segment, "start", 0.0)
    end = _setting_float(segment, "end", start)
    return max(0.0, end - start)


def _lora_readability_merge_reasons(segment: dict, settings: dict | None, merge_settings: dict) -> list[str]:
    threshold = max(8, int(merge_settings.get("split_length_threshold", 20) or 20))
    chars = _segment_compact_len(segment)
    duration = max(0.1, _segment_duration(segment))
    cps = chars / duration
    max_cps = max(1, _setting_int(settings or {}, "sub_max_cps", _MAX_CPS))
    min_duration = max(0.05, float(merge_settings.get("sub_min_duration", _MIN_DURATION) or _MIN_DURATION))
    floor_chars = max(2, int(threshold * 0.45))
    quality_label = _segment_quality_label(segment)
    quality_score = _segment_quality_score(segment)
    uncertainty = dict(segment.get("_uncertainty_policy") or {})
    uncertainty_bucket = str(uncertainty.get("bucket") or "").strip().lower()
    uncertainty_reasons = {
        str(item.get("reason") or "").strip().lower()
        for item in list(uncertainty.get("reasons") or [])
        if isinstance(item, dict)
    }

    reasons: list[str] = []
    if duration < min_duration or chars <= floor_chars:
        reasons.append("micro_fragment")
    if cps > max_cps * 1.04:
        reasons.append("high_cps")
    if chars > int(threshold * 1.12):
        reasons.append("long_text")
    if quality_label in {"yellow", "red"}:
        reasons.append(f"quality_{quality_label}")
    elif 0.0 < quality_score < float((settings or {}).get("subtitle_lora_selective_quality_max_score", 82.0) or 82.0):
        reasons.append("low_quality_score")
    if uncertainty_bucket == "precision":
        reasons.append("precision_bucket")
    for key in ("high_cps", "long_text", "quality_red", "quality_yellow"):
        if key in uncertainty_reasons and key not in reasons:
            reasons.append(key)
    return reasons


def _selective_lora_merge_indexes(rows: list[dict], settings: dict | None, merge_settings: dict) -> tuple[set[int], dict[int, list[str]]]:
    selected: set[int] = set()
    reasons_map: dict[int, list[str]] = {}
    for idx, row in enumerate(rows):
        reasons = _lora_readability_merge_reasons(row, settings, merge_settings)
        if not reasons:
            continue
        reasons_map[idx] = reasons
        selected.add(idx)
        if idx > 0:
            selected.add(idx - 1)
        if idx + 1 < len(rows):
            selected.add(idx + 1)
    return selected, reasons_map


def _apply_lora_style_micro_merge_selective(
    rows: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    merge_settings = _lora_style_merge_settings(settings)
    selected_indexes, reasons_map = _selective_lora_merge_indexes(rows, settings, merge_settings)
    if not selected_indexes:
        return rows

    for idx, row in enumerate(rows):
        policy = dict(row.get("_lora_style_merge_policy") or {})
        policy["mode"] = "readability_selective"
        if idx in reasons_map:
            policy["selective_reasons"] = list(reasons_map[idx])
        row["_lora_style_merge_policy"] = policy

    merged_rows: list[dict] = []
    merge_saved = 0
    index = 0
    while index < len(rows):
        if index not in selected_indexes:
            merged_rows.append(rows[index])
            index += 1
            continue
        tail = index + 1
        while tail < len(rows) and tail in selected_indexes:
            tail += 1
        chunk = [dict(item) for item in rows[index:tail]]
        if len(chunk) >= 2:
            out_chunk = merge_short_segments_by_gap(
                chunk,
                min_duration=float(merge_settings["sub_min_duration"]),
                max_chars=int(merge_settings["split_length_threshold"]),
                gap_break_sec=min(float(merge_settings["sub_gap_break_sec"]), 0.8),
                vad_segments=vad_segments or [],
                word_gap_break_sec=float(merge_settings["word_timing_gap_break_sec"]),
            )
            merge_saved += max(0, len(chunk) - len(out_chunk))
            merged_rows.extend(out_chunk)
        else:
            merged_rows.extend(chunk)
        index = tail

    if merge_saved > 0:
        get_logger().log(
            f"[LoRA자막묶음] {stage}: readability selective로 {merge_saved}개 미세 자막 병합"
        )
    return merged_rows


def _seed_lora_style_merge_context(segments: list[dict], settings: dict | None, *, stage: str) -> list[dict]:
    merge_settings = _lora_style_merge_settings(settings)
    rows: list[dict] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        row = dict(seg)
        segment_settings = dict(row.get("_lora_segment_settings") or {})
        gap_settings = dict(row.get("_lora_gap_settings") or {})
        for key in ("split_length_threshold", "sub_min_duration", "sub_gap_break_sec", "word_timing_gap_break_sec"):
            segment_settings.setdefault(key, merge_settings[key])
        gap_settings.setdefault("continuous_threshold", merge_settings["continuous_threshold"])
        gap_settings.setdefault("sub_gap_break_sec", merge_settings["sub_gap_break_sec"])
        row["_lora_segment_settings"] = segment_settings
        row["_lora_gap_settings"] = gap_settings
        row["_lora_style_merge_policy"] = {
            "task": "lora_style_micro_merge",
            "stage": stage,
            "source": "runtime_lora_style_settings",
            "settings": merge_settings,
        }
        rows.append(row)
    return rows


def _apply_lora_style_micro_merge(
    segments: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    settings = dict(settings or {})
    if not segments or not _bool_setting(settings, "subtitle_lora_micro_merge_enabled", True):
        return segments
    rows = _seed_lora_style_merge_context(segments, settings, stage=stage)
    merge_mode = _lora_style_merge_mode(settings)
    if merge_mode == "readability_selective":
        return _apply_lora_style_micro_merge_selective(rows, vad_segments, settings, stage=stage)
    merge_settings = _lora_style_merge_settings(settings)
    before_count = len(rows)
    try:
        merged = regroup_by_word_timestamps(
            rows,
            max_chars=int(merge_settings["split_length_threshold"]),
            max_duration=_setting_float(settings, "sub_max_duration", _MAX_DURATION),
            max_cps=_setting_int(settings, "sub_max_cps", _MAX_CPS),
            min_duration=float(merge_settings["sub_min_duration"]),
            gap_break_sec=float(merge_settings["sub_gap_break_sec"]),
            word_gap_break_sec=float(merge_settings["word_timing_gap_break_sec"]),
            vad_segments=vad_segments or [],
            frame_rate=float(settings.get("video_fps", 0.0) or 0.0),
            rules=load_subtitle_rules(),
        )
    except Exception as exc:
        get_logger().log(f"[LoRA자막묶음] 실패({stage}): {exc}")
        return segments
    if len(merged) < before_count:
        get_logger().log(f"[LoRA자막묶음] {stage}: 짧은 자막 {before_count}개 → {len(merged)}개로 병합")
    return merged


def _lora_packaging_mode(settings: dict | None) -> str:
    raw = str(dict(settings or {}).get("subtitle_lora_packaging_mode") or "full").strip().lower()
    if raw in {"readability", "readability_selective", "selective"}:
        return "readability_selective"
    return "full"


def _subtitle_text_lines(text: str) -> list[str]:
    normalized = _normalize_subtitle_text_lines(text)
    return [line.strip() for line in str(normalized or "").splitlines() if line.strip()]


def _packaging_target_patterns(settings: dict | None) -> list[str]:
    return list(_llm_lora_line_break_patterns(dict(settings or {}), limit=4) or [])


def _lora_packaging_reasons(segment: dict, settings: dict | None) -> list[str]:
    text = str(segment.get("text", "") or "")
    if not text.strip():
        return []
    threshold = max(8, _setting_int(settings or {}, "split_length_threshold", 20))
    chars = _split_visible_len(text)
    lines = _subtitle_text_lines(text)
    current_pattern = line_break_pattern_for_text(text)
    target_patterns = _packaging_target_patterns(settings)
    target_line_count = max(0, _setting_int(settings or {}, "subtitle_target_line_count", 0))
    quality_label = _segment_quality_label(segment)
    quality_score = _segment_quality_score(segment)
    reasons: list[str] = []
    if len(lines) <= 1 and chars >= max(10, int(threshold * 0.88)):
        reasons.append("single_line_overflow")
    if target_patterns and current_pattern not in target_patterns:
        reasons.append("pattern_mismatch")
    if target_line_count >= 2 and len(lines) < target_line_count:
        reasons.append("line_count_target")
    if quality_label in {"yellow", "red"}:
        reasons.append(f"quality_{quality_label}")
    elif 0.0 < quality_score < float((settings or {}).get("subtitle_lora_packaging_quality_max_score", 84.0) or 84.0):
        reasons.append("low_quality_score")
    return reasons


def _packaging_candidate_score(
    chunks: list[str],
    *,
    strategy: str,
    current_pattern: str,
    target_patterns: list[str],
    target_line_count: int,
    threshold: int,
) -> float:
    if not chunks:
        return float("-inf")
    pattern = line_break_pattern_for_text("\n".join(chunks))
    line_lengths = [max(1, _split_visible_len(chunk)) for chunk in chunks if str(chunk).strip()]
    if not line_lengths:
        return float("-inf")
    max_line = max(line_lengths)
    min_line = min(line_lengths)
    score = 0.0
    if target_patterns:
        if pattern == target_patterns[0]:
            score += 240.0
        elif pattern in target_patterns:
            score += 180.0
    if target_line_count > 0:
        score += max(0.0, 48.0 - abs(len(chunks) - target_line_count) * 20.0)
    if strategy == "lora_ground_truth_line_break":
        score += 30.0
    elif strategy == "lora_line_count":
        score += 18.0
    elif strategy == "balanced":
        score += 8.0
    elif strategy == "rule_greedy":
        score += 4.0
    overflow = max(0, max_line - max(1, threshold))
    score -= float(overflow) * 10.0
    if len(chunks) > 2:
        score -= float(len(chunks) - 2) * 24.0
    score -= float(max_line - min_line) * 0.6
    if len(chunks) >= 2:
        score += 6.0
    if pattern == current_pattern:
        score -= 6.0
    return score


def _apply_lora_card_packaging(
    segments: list[dict],
    settings: dict | None,
    rules: dict | None,
    *,
    stage: str,
) -> list[dict]:
    if not segments or not _bool_setting(settings or {}, "subtitle_lora_packaging_enabled", False):
        return segments
    mode = _lora_packaging_mode(settings)
    rows: list[dict] = []
    changed = 0
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        row = dict(seg)
        text = _normalize_subtitle_text_lines(str(row.get("text", "") or ""))
        if not text:
            rows.append(row)
            continue
        allow_multiline = _segment_has_multi_speaker_linebreak_permission(row)
        if not allow_multiline:
            single_line_text = " ".join(_subtitle_text_lines(text))
            if single_line_text and single_line_text != text:
                row["text"] = single_line_text
                row["_lora_packaging_policy"] = {
                    "task": "lora_card_packaging",
                    "stage": stage,
                    "mode": mode,
                    "strategy": "single_line_enforced",
                    "reason": "single_speaker_no_line_break",
                }
                changed += 1
            rows.append(row)
            continue
        row_settings = {**dict(settings or {}), **dict(row.get("_lora_segment_settings") or {})}
        if row.get("_lora_generation_profile"):
            row_settings["_lora_generation_profile"] = row.get("_lora_generation_profile")
        reasons = _lora_packaging_reasons(row, row_settings)
        if mode == "readability_selective" and not reasons:
            rows.append(row)
            continue
        threshold = max(8, _setting_int(row_settings, "split_length_threshold", 20))
        candidates = build_llm_candidate_options(text, threshold, rules or {}, row_settings)
        current_chunks = _subtitle_text_lines(text)
        current_pattern = line_break_pattern_for_text(text)
        target_patterns = _packaging_target_patterns(row_settings)
        target_line_count = max(0, _setting_int(row_settings, "subtitle_target_line_count", 0))
        best_chunks = list(current_chunks)
        best_strategy = "current"
        best_score = _packaging_candidate_score(
            best_chunks,
            strategy=best_strategy,
            current_pattern=current_pattern,
            target_patterns=target_patterns,
            target_line_count=target_line_count,
            threshold=threshold,
        )
        for candidate in list(candidates or []):
            chunks = [str(chunk).strip() for chunk in list(candidate.get("chunks") or []) if str(chunk).strip()]
            if not chunks:
                continue
            candidate_text = "\n".join(chunks)
            if re.sub(r"\s+", "", candidate_text) != re.sub(r"\s+", "", text):
                continue
            score = _packaging_candidate_score(
                chunks,
                strategy=str(candidate.get("strategy") or ""),
                current_pattern=current_pattern,
                target_patterns=target_patterns,
                target_line_count=target_line_count,
                threshold=threshold,
            )
            if score > best_score + 1e-6:
                best_chunks = list(chunks)
                best_strategy = str(candidate.get("strategy") or "")
                best_score = score
        packaged_text = "\n".join(best_chunks)
        if packaged_text != text:
            row["text"] = packaged_text
            row["_lora_packaging_policy"] = {
                "task": "lora_card_packaging",
                "stage": stage,
                "mode": mode,
                "strategy": best_strategy,
                "reasons": list(reasons),
                "target_line_count": target_line_count,
                "target_patterns": list(target_patterns[:3]),
                "before_pattern": current_pattern,
                "after_pattern": line_break_pattern_for_text(packaged_text),
            }
            changed += 1
        rows.append(row)
    if changed > 0:
        get_logger().log(f"[LoRA자막포장] {stage}: timing 유지 + 줄바꿈/카드 포장 {changed}개 조정")
    return rows


def _segment_has_multi_speaker_linebreak_permission(row: dict) -> bool:
    speakers = [
        str(item).strip()
        for item in list(row.get("speaker_list") or [])
        if str(item).strip()
    ]
    return len(set(speakers)) >= 2


def _canonical_speaker_id(value) -> str:
    speaker = str(value or "").strip()
    if speaker.startswith("SPEAKER_"):
        speaker = speaker.replace("SPEAKER_", "", 1)
    return speaker


def _speaker_values_from_row(row: dict | None) -> list[str]:
    if not isinstance(row, dict):
        return []
    values: list[str] = []
    for item in list(row.get("speaker_list") or []):
        speaker = _canonical_speaker_id(item)
        if speaker:
            values.append(speaker)
    for key in ("speaker", "speaker2", "spk", "spk_id"):
        speaker = _canonical_speaker_id(row.get(key))
        if speaker:
            values.append(speaker)
    out: list[str] = []
    seen: set[str] = set()
    for speaker in values:
        if speaker in seen:
            continue
        seen.add(speaker)
        out.append(speaker)
        if len(out) >= 2:
            break
    return out


def _stt_text_has_speaker_marker(text: str) -> bool:
    raw = str(text or "").replace("\u2028", "\n").strip()
    if not raw:
        return False
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) >= 2 and all(line.startswith("-") for line in lines[:2]):
        return True
    compact = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()
    if not compact.startswith("-"):
        return False
    return len(re.findall(r"(?:^|\s)-\s*[^-\s]", compact)) >= 2


def _stt_decision_speaker_fields(row: dict | None, fallback: dict | None = None) -> dict:
    speakers = _speaker_values_from_row(row)
    if not speakers:
        speakers = _speaker_values_from_row(fallback)
    fields: dict = {}
    if speakers:
        fields["speaker"] = speakers[0]
        fields["speaker_list"] = speakers
        if len(speakers) >= 2:
            fields["speaker2"] = speakers[1]
    text = str((row or {}).get("text", "") or "")
    if _stt_text_has_speaker_marker(text) or len(set(speakers)) >= 2:
        fields["_stt_speaker_marker_preserved"] = True
    return fields


def _find_matching_stt_candidate_for_decision(seg: dict, decision: dict) -> dict | None:
    decision_text = re.sub(r"\s+", "", str((decision or {}).get("text", "") or "")).strip().lower()
    decision_source = str((decision or {}).get("source", "") or "").strip().upper()
    if not decision_text:
        return None
    best: dict | None = None
    best_score = -1
    for candidate in list((seg or {}).get("stt_candidates") or []):
        if not isinstance(candidate, dict):
            continue
        cand_text = re.sub(r"\s+", "", str(candidate.get("text", "") or "")).strip().lower()
        if not cand_text:
            continue
        cand_source = str(candidate.get("source", "") or "").strip().upper()
        score = 0
        if cand_text == decision_text:
            score += 4
        elif decision_text in cand_text or cand_text in decision_text:
            score += 2
        if decision_source and cand_source == decision_source:
            score += 1
        if score > best_score:
            best = candidate
            best_score = score
    return best if best_score >= 2 else None


def _is_speaker_split_multiline_segment(row: dict) -> bool:
    lines = _subtitle_text_lines(str(row.get("text", "") or ""))
    if len(lines) <= 1:
        return False
    return _segment_has_multi_speaker_linebreak_permission(row)


def _clear_split_timing_projection_fields(row: dict) -> None:
    for key in (
        "timeline_start",
        "timeline_end",
        "timeline_start_frame",
        "timeline_end_frame",
        "start_frame",
        "end_frame",
        "frame_range",
    ):
        row.pop(key, None)


def _multiline_word_groups_for_lines(row: dict, lines: list[str]) -> list[list[dict]] | None:
    words = [
        dict(word)
        for word in list(row.get("words") or [])
        if isinstance(word, dict) and str(word.get("word", "") or "").strip()
    ]
    if len(words) < len(lines):
        return None

    targets = [max(1, _split_visible_len(line)) for line in lines]
    groups: list[list[dict]] = []
    cursor = 0
    for idx, target in enumerate(targets):
        remaining_lines = len(targets) - idx
        remaining_words = len(words) - cursor
        if remaining_words < remaining_lines:
            return None
        if idx == len(targets) - 1:
            groups.append(words[cursor:])
            break

        group: list[dict] = []
        char_count = 0
        while cursor < len(words):
            remaining_words = len(words) - cursor
            if group and remaining_words <= remaining_lines - 1:
                break
            word = words[cursor]
            group.append(word)
            char_count += max(1, _split_visible_len(str(word.get("word", "") or "")))
            cursor += 1
            remaining_words = len(words) - cursor
            if char_count >= target and remaining_words >= remaining_lines - 1:
                break
        if not group:
            return None
        groups.append(group)
    if len(groups) != len(lines) or any(not group for group in groups):
        return None
    return groups


def _multiline_split_boundaries_from_groups(
    start: float,
    end: float,
    groups: list[list[dict]],
) -> list[float] | None:
    if len(groups) <= 1:
        return []
    boundaries: list[float] = []
    min_duration = 0.05
    for idx in range(len(groups) - 1):
        left = groups[idx]
        right = groups[idx + 1]
        try:
            left_end = float(left[-1].get("end", left[-1].get("start", start)) or start)
            right_start = float(right[0].get("start", left_end) or left_end)
        except Exception:
            return None
        if right_start >= left_end:
            boundary = (left_end + right_start) / 2.0
        else:
            boundary = max(left_end, right_start)
        min_boundary = start + min_duration * (idx + 1)
        max_boundary = end - min_duration * (len(groups) - idx - 1)
        boundary = max(min_boundary, min(max_boundary, boundary))
        boundaries.append(boundary)
    if any(boundaries[idx] <= boundaries[idx - 1] for idx in range(1, len(boundaries))):
        return None
    return boundaries


def _multiline_split_boundaries_from_weights(
    start: float,
    end: float,
    lines: list[str],
) -> list[float]:
    if len(lines) <= 1:
        return []
    weights = [max(1, _split_visible_len(line)) for line in lines]
    total_weight = max(1, sum(weights))
    min_duration = 0.05
    duration = max(float(end) - float(start), min_duration * len(lines))
    boundaries: list[float] = []
    consumed = 0
    for idx, weight in enumerate(weights[:-1]):
        consumed += weight
        proposed = start + duration * (consumed / total_weight)
        min_boundary = start + min_duration * (idx + 1)
        max_boundary = end - min_duration * (len(lines) - idx - 1)
        boundaries.append(max(min_boundary, min(max_boundary, proposed)))
    return boundaries


def _expand_non_speaker_multiline_segments(
    segments: list[dict],
    settings: dict | None = None,
) -> list[dict]:
    rows: list[dict] = []
    flattened_segments = 0
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        row = dict(seg)
        lines = _subtitle_text_lines(str(row.get("text", "") or ""))
        if len(lines) <= 1 or _is_speaker_split_multiline_segment(row):
            row["text"] = "\n".join(lines) if lines else str(row.get("text", "") or "").strip()
            rows.append(row)
            continue
        row["text"] = " ".join(lines)
        row.pop("words", None)
        policy = dict(row.get("_lora_packaging_policy") or {})
        policy.update(
            {
                "task": "lora_card_packaging",
                "output_mode": "single_line_flatten",
                "reason": "single_speaker_no_line_break",
            }
        )
        row["_lora_packaging_policy"] = policy
        rows.append(row)
        flattened_segments += 1

    if flattened_segments > 0:
        get_logger().log(f"[자막줄정리] 일반 줄바꿈 자막 {flattened_segments}개를 한 줄로 정리")
    return rows


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


def _sequence_text_for_integrity(segments: list[dict] | None) -> str:
    return " ".join(
        " ".join(_subtitle_text_lines(str(seg.get("text", "") or "")))
        for seg in list(segments or [])
        if isinstance(seg, dict) and str(seg.get("text", "") or "").strip() and not seg.get("is_gap")
    ).strip()


def _segment_scope_key_local(segment: dict | None) -> tuple[str, str] | None:
    if not isinstance(segment, dict):
        return None
    clip_idx = segment.get("_clip_idx")
    if clip_idx is not None:
        return ("clip_idx", str(clip_idx))
    clip_file = segment.get("_clip_file") or segment.get("clip_file")
    if clip_file:
        return ("clip_file", str(clip_file))
    return None


def _same_segment_scope_local(left: dict | None, right: dict | None) -> bool:
    if not left or not right:
        return False
    left_key = _segment_scope_key_local(left)
    right_key = _segment_scope_key_local(right)
    if left_key is None and right_key is None:
        return True
    return left_key == right_key


def _speaker_signature(row: dict | None) -> tuple[str, ...]:
    if not isinstance(row, dict):
        return ()
    speakers = [
        str(item).strip()
        for item in list(row.get("speaker_list") or [])
        if str(item).strip()
    ]
    if not speakers:
        speaker = str(row.get("speaker") or row.get("spk") or "").strip()
        if speaker:
            speakers = [speaker]
    return tuple(sorted(set(speakers)))


def _compatible_speaker_signature(left: dict | None, right: dict | None) -> bool:
    left_sig = _speaker_signature(left)
    right_sig = _speaker_signature(right)
    if left_sig and right_sig:
        return left_sig == right_sig
    return True


def _compact_subtitle_text(text: str) -> str:
    return re.sub(r"\s+", "", " ".join(_subtitle_text_lines(text)))


def _subtitle_tokens(text: str) -> list[str]:
    return [token for token in " ".join(_subtitle_text_lines(text)).split() if token]


def _token_compact_len(tokens: list[str]) -> int:
    return len(re.sub(r"\s+", "", "".join(tokens)))


def _overlap_token_count(left_tokens: list[str], right_tokens: list[str], *, mode: str) -> int:
    max_size = min(len(left_tokens), len(right_tokens), 8)
    for size in range(max_size, 0, -1):
        if mode == "prefix":
            matched = left_tokens[-size:] == right_tokens[:size]
        else:
            matched = right_tokens[-size:] == left_tokens[:size]
        if matched:
            return size
    return 0


def _normalize_short_closing_phrase(text: str) -> str:
    tokens = _subtitle_tokens(text)
    if len(tokens) != 2:
        return " ".join(tokens).strip()
    if tokens[0] in _FINAL_CLOSING_PHRASES and tokens[1] in _FINAL_FILLER_FRAGMENTS:
        return tokens[0]
    if tokens[1] in _FINAL_CLOSING_PHRASES and tokens[0] in _FINAL_FILLER_FRAGMENTS:
        return tokens[1]
    return " ".join(tokens).strip()


def _is_low_value_duplicate_bridge_tokens(tokens: list[str]) -> bool:
    if not tokens:
        return False
    for token in tokens:
        if token in _FINAL_FILLER_FRAGMENTS:
            continue
        if token in _FINAL_DUPLICATE_BRIDGE_TOKENS:
            continue
        if _FINAL_CONTINUATION_TAIL_RE.search(token):
            continue
        return False
    return True


def _merge_adjacent_rows(left: dict, right: dict, *, stage: str, reason: str) -> dict:
    left_text = " ".join(_subtitle_text_lines(str(left.get("text", "") or "")))
    right_text = " ".join(_subtitle_text_lines(str(right.get("text", "") or "")))
    merged = dict(left)
    merged["end"] = max(_setting_float(right, "end", 0.0), _setting_float(left, "end", 0.0))
    merged["text"] = f"{left_text} {right_text}".strip()
    if "timeline_end" in merged or "timeline_start" in merged:
        merged["timeline_start"] = _setting_float(merged, "start", 0.0)
        merged["timeline_end"] = merged["end"]
    if isinstance(left.get("words"), list) and isinstance(right.get("words"), list):
        merged["words"] = [dict(word) for word in left.get("words", [])] + [dict(word) for word in right.get("words", [])]
    policy = {
        "task": "final_sequence_cleanup",
        "stage": stage,
        "action": "merge",
        "reason": reason,
    }
    merged["_final_sequence_cleanup_policy"] = policy
    _clear_split_timing_projection_fields(merged)
    return merged


def _drop_shadowed_short_rows(rows: list[dict], settings: dict | None, *, stage: str) -> tuple[list[dict], int]:
    del stage
    if not rows:
        return rows, 0
    max_chars = max(4, _setting_int(settings or {}, "subtitle_final_shadow_drop_max_chars", 8))
    max_gap = max(0.0, _setting_float(settings or {}, "subtitle_final_shadow_drop_gap_sec", 0.08))
    min_growth = max(2, _setting_int(settings or {}, "subtitle_final_shadow_drop_growth_chars", 4))
    result: list[dict] = []
    dropped = 0
    count = len(rows)
    for index, raw_row in enumerate(rows):
        row = dict(raw_row)
        if index + 1 >= count:
            result.append(row)
            continue
        nxt = rows[index + 1]
        text = " ".join(_subtitle_text_lines(str(row.get("text", "") or "")))
        next_text = " ".join(_subtitle_text_lines(str(nxt.get("text", "") or "")))
        compact = _compact_subtitle_text(text)
        next_compact = _compact_subtitle_text(next_text)
        gap = _setting_float(nxt, "start", 0.0) - _setting_float(row, "end", 0.0)
        if (
            compact
            and next_compact
            and len(compact) <= max_chars
            and len(next_compact) >= len(compact) + min_growth
            and next_compact.startswith(compact)
            and gap <= max_gap
            and _same_segment_scope_local(row, nxt)
            and _compatible_speaker_signature(row, nxt)
            and not _is_speaker_split_multiline_segment(row)
            and not _is_speaker_split_multiline_segment(nxt)
        ):
            dropped += 1
            continue
        result.append(row)
    return result, dropped


def _merge_likely_oversplit_rows(rows: list[dict], settings: dict | None, *, stage: str) -> tuple[list[dict], int]:
    if not rows:
        return rows, 0
    max_gap = max(0.0, _setting_float(settings or {}, "subtitle_final_micro_merge_gap_sec", 0.08))
    split_threshold = max(12, _setting_int(settings or {}, "split_length_threshold", 20))
    max_chars = max(18, int(split_threshold * 1.45))
    max_cps = max(1.0, _setting_float(settings or {}, "sub_max_cps", _MAX_CPS))
    continuation_max_chars = max(6, _setting_int(settings or {}, "subtitle_final_micro_merge_continuation_max_chars", 14))
    result: list[dict] = []
    merged_count = 0
    for raw_row in rows:
        row = dict(raw_row)
        if not result:
            result.append(row)
            continue
        previous = result[-1]
        if previous.get("_final_sequence_cleanup_policy", {}).get("action") == "merge":
            result.append(row)
            continue
        prev_text = " ".join(_subtitle_text_lines(str(previous.get("text", "") or "")))
        text = " ".join(_subtitle_text_lines(str(row.get("text", "") or "")))
        prev_compact = _compact_subtitle_text(prev_text)
        compact = _compact_subtitle_text(text)
        gap = _setting_float(row, "start", 0.0) - _setting_float(previous, "end", 0.0)
        if (
            not prev_compact
            or not compact
            or gap > max_gap
            or _is_speaker_split_multiline_segment(previous)
            or _is_speaker_split_multiline_segment(row)
            or not _same_segment_scope_local(previous, row)
            or not _compatible_speaker_signature(previous, row)
        ):
            result.append(row)
            continue
        merged_text = f"{prev_text} {text}".strip()
        merged_compact_len = len(_compact_subtitle_text(merged_text))
        duration = max(0.05, _setting_float(row, "end", 0.0) - _setting_float(previous, "start", 0.0))
        merged_cps = merged_compact_len / duration
        reason = None
        if prev_compact in _FINAL_FILLER_FRAGMENTS or compact in _FINAL_FILLER_FRAGMENTS:
            reason = "filler_fragment"
        elif (
            len(prev_compact) <= continuation_max_chars
            and _FINAL_CONTINUATION_TAIL_RE.search(prev_compact)
            and not re.search(r"[?!…~]$", prev_text)
        ):
            reason = "continuation_tail"
        if reason and merged_compact_len <= max_chars and merged_cps <= max_cps * 1.12:
            result[-1] = _merge_adjacent_rows(previous, row, stage=stage, reason=reason)
            merged_count += 1
            continue
        result.append(row)
    return result, merged_count


def _trim_recent_overlap_rows(rows: list[dict], settings: dict | None, *, stage: str) -> tuple[list[dict], int]:
    del settings
    if not rows:
        return rows, 0
    result: list[dict] = []
    changed = 0
    for raw_row in rows:
        row = dict(raw_row)
        text = " ".join(_subtitle_text_lines(str(row.get("text", "") or "")))
        tokens = _subtitle_tokens(text)
        if (
            not tokens
            or not result
            or _is_speaker_split_multiline_segment(row)
        ):
            result.append(row)
            continue
        recent_rows = [item for item in result[-2:] if isinstance(item, dict)]
        recent_tokens = [
            token
            for item in recent_rows
            for token in _subtitle_tokens(str(item.get("text", "") or ""))
        ]
        updated_tokens = list(tokens)
        if recent_tokens:
            prefix_overlap = _overlap_token_count(recent_tokens, updated_tokens, mode="prefix")
            if prefix_overlap and (prefix_overlap >= 3 or _token_compact_len(updated_tokens[:prefix_overlap]) >= 8):
                updated_tokens = updated_tokens[prefix_overlap:]
            suffix_overlap = _overlap_token_count(recent_tokens, updated_tokens, mode="suffix")
            if suffix_overlap and (suffix_overlap >= 3 or _token_compact_len(updated_tokens[-suffix_overlap:]) >= 8):
                updated_tokens = updated_tokens[:-suffix_overlap]
        trimmed_text = _normalize_short_closing_phrase(" ".join(updated_tokens).strip())
        if trimmed_text != text:
            changed += 1
        if not trimmed_text:
            continue
        previous = result[-1]
        gap = _setting_float(row, "start", 0.0) - _setting_float(previous, "end", 0.0)
        previous_tokens = _subtitle_tokens(str(previous.get("text", "") or ""))
        if (
            previous_tokens
            and len(updated_tokens) > len(previous_tokens)
            and updated_tokens[-len(previous_tokens):] == previous_tokens
            and _is_low_value_duplicate_bridge_tokens(updated_tokens[:-len(previous_tokens)])
            and any(token in _FINAL_CLOSING_PHRASES for token in previous_tokens)
            and gap <= 0.35
            and _same_segment_scope_local(previous, row)
            and _compatible_speaker_signature(previous, row)
        ):
            changed += 1
            continue
        if (
            updated_tokens
            and _is_low_value_duplicate_bridge_tokens(updated_tokens)
            and any(token in _FINAL_CLOSING_PHRASES for token in previous_tokens)
            and gap <= 0.35
            and _same_segment_scope_local(previous, row)
            and _compatible_speaker_signature(previous, row)
        ):
            changed += 1
            continue
        if (
            _compact_subtitle_text(trimmed_text) == _compact_subtitle_text(str(previous.get("text", "") or ""))
            and gap <= 0.08
            and _same_segment_scope_local(previous, row)
            and _compatible_speaker_signature(previous, row)
        ):
            changed += 1
            continue
        row["text"] = trimmed_text
        if trimmed_text != text:
            row["_final_sequence_cleanup_policy"] = {
                "task": "final_sequence_cleanup",
                "stage": stage,
                "action": "trim_recent_overlap",
            }
        result.append(row)
    return result, changed


def _apply_final_sequence_cleanup(
    segments: list[dict],
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    if not segments or not _bool_setting(settings or {}, "subtitle_final_sequence_cleanup_enabled", True):
        return segments
    rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    if not rows:
        return segments
    rows, dropped_shadow = _drop_shadowed_short_rows(rows, settings, stage=stage)
    rows, merged = _merge_likely_oversplit_rows(rows, settings, stage=stage)
    rows, trimmed = _trim_recent_overlap_rows(rows, settings, stage=stage)
    if dropped_shadow or merged or trimmed:
        get_logger().log(
            "[자막후단보정] "
            f"{stage}: 그림자 삭제 {dropped_shadow}개, 과분할 병합 {merged}개, 최근중복 정리 {trimmed}개"
        )
    return rows


def _safe_source_integrity_variant(source_segments: list[dict], settings: dict | None) -> list[dict]:
    rows = [
        dict(seg)
        for seg in list(source_segments or [])
        if isinstance(seg, dict) and str(seg.get("text", "") or "").strip() and not seg.get("is_gap")
    ]
    if not rows:
        return []
    rows = adjust_timing(rows)
    rows = apply_final_gap_settings(rows, settings or {}, force=True)
    rows = align_stt_candidates_to_subtitle_segments(rows)
    raw_corr = get_local_dataset_corrections()
    corrections: dict = raw_corr if isinstance(raw_corr, dict) else {}
    rows = _enforce_final_subtitle_text_policy(rows, corrections)
    rows = _apply_final_sequence_cleanup(rows, settings or {}, stage="source_integrity")
    return _expand_non_speaker_multiline_segments(rows, settings or {})


def _source_stt_anchor_rows(source_segments: list[dict]) -> list[dict]:
    anchors: list[dict] = []
    for source_index, raw_seg in enumerate(list(source_segments or [])):
        if not isinstance(raw_seg, dict):
            continue
        seg = dict(raw_seg)
        selected_source_name = str(seg.get("stt_selected_source") or seg.get("stt_ensemble_source") or "").strip().upper()
        selected_source_base = selected_source_name.split("_", 1)[0]
        candidates = [seg]
        candidates.extend(c for c in list(seg.get("stt_candidates") or []) if isinstance(c, dict))
        for cand_index, candidate in enumerate(candidates):
            text = str(candidate.get("text", "") or "").strip()
            if not text or _stt_candidate_compact_text(text) in {"", "-"}:
                continue
            span = _stt_decision_timing_span(candidate) or _stt_decision_timing_span(seg)
            if span is None:
                continue
            start, end = span
            if end <= start:
                continue
            source_name = str(
                candidate.get("source")
                or candidate.get("stt_selected_source")
                or seg.get("stt_selected_source")
                or seg.get("stt_ensemble_source")
                or "STT"
            ).strip().upper()
            source_base = source_name.split("_", 1)[0]
            anchor_priority = 0.0
            if cand_index == 0:
                anchor_priority += 4.0
            if selected_source_base and source_base == selected_source_base:
                anchor_priority += 2.0
            anchor_priority += min(1.0, _stt_candidate_score100(candidate) / 100.0)
            anchors.append(
                {
                    **{key: seg[key] for key in _stt_selection_metadata(seg).keys() if key in seg},
                    **dict(candidate),
                    "text": text,
                    "start": float(start),
                    "end": float(end),
                    "source": source_name,
                    "_anchor_priority": round(anchor_priority, 4),
                    "_source_segment_index": source_index,
                    "_source_candidate_index": cand_index,
                }
            )
    anchors.sort(key=lambda item: (float(item.get("start", 0.0) or 0.0), float(item.get("end", 0.0) or 0.0)))
    return anchors


_FINAL_STT_ANCHOR_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*(?:[%％]|[A-Za-z가-힣]+)?")


def _subtitle_number_tokens(text: str) -> set[str]:
    return {
        _stt_candidate_compact_text(token)
        for token in _FINAL_STT_ANCHOR_NUMBER_RE.findall(str(text or ""))
        if _stt_candidate_compact_text(token)
    }


def _stt_anchor_guard_key(anchor: dict) -> tuple:
    return (
        anchor.get("_source_segment_index"),
        anchor.get("_source_candidate_index"),
        round(float(anchor.get("start", 0.0) or 0.0), 3),
        round(float(anchor.get("end", 0.0) or 0.0), 3),
        _stt_candidate_compact_text(str(anchor.get("text", "") or "")),
    )


def _subtitle_row_span(row: dict) -> tuple[float, float] | None:
    try:
        start = float(row.get("start"))
        end = float(row.get("end"))
    except (TypeError, ValueError):
        return None
    if end <= start:
        return None
    return start, end


def _best_stt_anchor_for_final_row(row: dict, anchors: list[dict], settings: dict | None) -> tuple[dict | None, dict]:
    row_span = _subtitle_row_span(row)
    if row_span is None:
        return None, {}
    row_start, row_end = row_span
    row_mid = (row_start + row_end) / 2.0
    row_duration = max(0.05, row_end - row_start)
    max_mid_delta = max(0.8, _setting_float(settings or {}, "subtitle_final_stt_anchor_guard_max_mid_delta_sec", 1.9))
    best: tuple[float, dict, dict] | None = None
    for anchor in anchors:
        anchor_span = _subtitle_row_span(anchor)
        if anchor_span is None:
            continue
        anchor_start, anchor_end = anchor_span
        anchor_duration = max(0.05, anchor_end - anchor_start)
        overlap = max(0.0, min(row_end, anchor_end) - max(row_start, anchor_start))
        overlap_ratio = overlap / max(0.05, min(row_duration, anchor_duration))
        anchor_mid = (anchor_start + anchor_end) / 2.0
        mid_delta = abs(anchor_mid - row_mid)
        if overlap_ratio <= 0.0 and mid_delta > max(max_mid_delta, row_duration + 0.65, anchor_duration + 0.65):
            continue
        temporal_score = (overlap_ratio * 4.0) + max(0.0, 1.0 - (mid_delta / max(0.05, max_mid_delta)))
        text_similarity = _stt_candidate_similarity(str(row.get("text", "") or ""), str(anchor.get("text", "") or ""))
        anchor_priority = float(anchor.get("_anchor_priority", 0.0) or 0.0)
        score = temporal_score + (text_similarity * 0.35) + (anchor_priority * 0.12)
        meta = {
            "overlap_ratio": round(overlap_ratio, 4),
            "mid_delta_sec": round(mid_delta, 4),
            "text_similarity": round(text_similarity, 4),
            "temporal_score": round(temporal_score, 4),
            "anchor_priority": round(anchor_priority, 4),
        }
        if best is None or score > best[0]:
            best = (score, anchor, meta)
    if best is None:
        return None, {}
    return best[1], best[2]


def _stt_anchor_is_represented(anchor: dict, rows: list[dict], settings: dict | None) -> bool:
    anchor_span = _subtitle_row_span(anchor)
    if anchor_span is None:
        return False
    anchor_start, anchor_end = anchor_span
    anchor_mid = (anchor_start + anchor_end) / 2.0
    anchor_duration = max(0.05, anchor_end - anchor_start)
    anchor_text = str(anchor.get("text", "") or "").strip()
    anchor_compact = _stt_candidate_compact_text(anchor_text)
    if not anchor_compact:
        return False
    min_similarity = max(
        0.05,
        min(0.95, _setting_float(settings or {}, "subtitle_final_stt_anchor_guard_present_similarity", 0.64)),
    )
    max_mid_delta = max(
        0.25,
        _setting_float(settings or {}, "subtitle_final_stt_anchor_guard_present_mid_delta_sec", 1.1),
    )
    for row in list(rows or []):
        row_span = _subtitle_row_span(row)
        if row_span is None:
            continue
        row_start, row_end = row_span
        row_mid = (row_start + row_end) / 2.0
        row_duration = max(0.05, row_end - row_start)
        overlap = max(0.0, min(row_end, anchor_end) - max(row_start, anchor_start))
        overlap_ratio = overlap / max(0.05, min(row_duration, anchor_duration))
        mid_delta = abs(row_mid - anchor_mid)
        if overlap_ratio <= 0.0 and mid_delta > max_mid_delta:
            continue
        row_text = str(row.get("text", "") or "").strip()
        row_compact = _stt_candidate_compact_text(row_text)
        if len(anchor_compact) >= 4 and anchor_compact in row_compact:
            return True
        if _stt_candidate_similarity(anchor_text, row_text) >= min_similarity:
            return True
    return False


def _trim_rows_for_inserted_stt_anchor(rows: list[dict], anchor: dict, settings: dict | None) -> list[dict]:
    anchor_span = _subtitle_row_span(anchor)
    if anchor_span is None:
        return rows
    anchor_start, anchor_end = anchor_span
    min_duration = max(0.15, min(0.5, _setting_float(settings or {}, "sub_min_duration", 0.3)))
    trimmed: list[dict] = []
    for raw_row in list(rows or []):
        row = dict(raw_row)
        row_span = _subtitle_row_span(row)
        if row_span is None:
            trimmed.append(row)
            continue
        row_start, row_end = row_span
        overlap = max(0.0, min(row_end, anchor_end) - max(row_start, anchor_start))
        if overlap <= 0.0:
            trimmed.append(row)
            continue
        old_start, old_end = row_start, row_end
        if row_start < anchor_start < row_end:
            row_end = min(row_end, anchor_start)
            if row_end - row_start >= min_duration:
                row["end"] = row_end
                row["_final_stt_anchor_trim_policy"] = {
                    "task": "final_stt_anchor_guard",
                    "action": "trim_end_for_inserted_stt_anchor",
                    "old_start": round(old_start, 3),
                    "old_end": round(old_end, 3),
                    "new_start": round(row_start, 3),
                    "new_end": round(row_end, 3),
                    "inserted_text": str(anchor.get("text", "") or "")[:80],
                }
        elif row_start < anchor_end < row_end:
            row_start = max(row_start, anchor_end)
            if row_end - row_start >= min_duration:
                row["start"] = row_start
                row["_final_stt_anchor_trim_policy"] = {
                    "task": "final_stt_anchor_guard",
                    "action": "trim_start_for_inserted_stt_anchor",
                    "old_start": round(old_start, 3),
                    "old_end": round(old_end, 3),
                    "new_start": round(row_start, 3),
                    "new_end": round(row_end, 3),
                    "inserted_text": str(anchor.get("text", "") or "")[:80],
                }
        trimmed.append(row)
    return trimmed


def _restore_final_stt_anchor_drift(
    optimized: list[dict],
    source_segments: list[dict],
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    settings = dict(settings or {})
    if not optimized or not source_segments:
        return optimized
    if not _bool_setting(settings, "subtitle_final_stt_anchor_guard_enabled", True):
        return optimized
    anchors = _source_stt_anchor_rows(source_segments)
    if not anchors:
        return optimized
    min_similarity = max(
        0.05,
        min(0.95, _setting_float(settings, "subtitle_final_stt_anchor_guard_min_similarity", 0.38)),
    )
    min_source_chars = max(2, _setting_int(settings, "subtitle_final_stt_anchor_guard_min_source_chars", 3))
    min_overlap_ratio = max(
        0.0,
        min(0.95, _setting_float(settings, "subtitle_final_stt_anchor_guard_min_overlap_ratio", 0.35)),
    )
    strict_mid_delta = max(
        0.1,
        _setting_float(settings, "subtitle_final_stt_anchor_guard_strict_mid_delta_sec", 0.45),
    )
    restored_count = 0
    rows: list[dict] = []
    used_anchor_keys: set[tuple] = set()
    for raw_row in list(optimized or []):
        row = dict(raw_row) if isinstance(raw_row, dict) else {}
        text = str(row.get("text", "") or "").strip()
        if not text or row.get("is_gap"):
            rows.append(row)
            continue
        anchor, meta = _best_stt_anchor_for_final_row(row, anchors, settings)
        if not anchor:
            rows.append(row)
            continue
        anchor_key = _stt_anchor_guard_key(anchor)
        if anchor_key in used_anchor_keys:
            rows.append(row)
            continue
        anchor_text = str(anchor.get("text", "") or "").strip()
        if len(_stt_candidate_compact_text(anchor_text)) < min_source_chars:
            rows.append(row)
            continue
        text_numbers = _subtitle_number_tokens(text)
        anchor_numbers = _subtitle_number_tokens(anchor_text)
        if text_numbers and not text_numbers.issubset(anchor_numbers):
            rows.append(row)
            continue
        similarity = float(meta.get("text_similarity", 0.0) or 0.0)
        if similarity >= min_similarity:
            rows.append(row)
            continue
        overlap_ratio = float(meta.get("overlap_ratio", 0.0) or 0.0)
        mid_delta = float(meta.get("mid_delta_sec", 999.0) or 999.0)
        if overlap_ratio < min_overlap_ratio and mid_delta > strict_mid_delta:
            rows.append(row)
            continue
        restored = {
            **row,
            "text": anchor_text,
            "start": float(anchor.get("start", row.get("start", 0.0)) or 0.0),
            "end": float(anchor.get("end", row.get("end", row.get("start", 0.0))) or 0.0),
            "stt_selected_source": str(anchor.get("source") or row.get("stt_selected_source") or "STT"),
            "_stt_original_candidate_start": float(anchor.get("start", row.get("start", 0.0)) or 0.0),
            "_stt_original_candidate_end": float(anchor.get("end", row.get("end", row.get("start", 0.0))) or 0.0),
            "_final_stt_anchor_guard_policy": {
                "task": "final_stt_anchor_guard",
                "stage": stage,
                "action": "restore_stt_anchor",
                "old_text": text,
                "new_text": anchor_text,
                "source": str(anchor.get("source") or "STT"),
                "source_segment_index": anchor.get("_source_segment_index"),
                "source_candidate_index": anchor.get("_source_candidate_index"),
                **meta,
            },
        }
        restored_count += 1
        used_anchor_keys.add(anchor_key)
        rows.append(restored)
    if restored_count:
        get_logger().log(f"[자막무결성-STT앵커] {stage}: STT 후보와 어긋난 최종 자막 {restored_count}개 복구")
    return rows


def _restore_missing_final_stt_anchor_rows(
    optimized: list[dict],
    source_segments: list[dict],
    settings: dict | None,
    *,
    stage: str,
) -> list[dict]:
    settings = dict(settings or {})
    if not optimized or not source_segments:
        return optimized
    if not _bool_setting(settings, "subtitle_final_stt_anchor_guard_enabled", True):
        return optimized
    if not _bool_setting(settings, "subtitle_final_stt_anchor_guard_insert_missing_enabled", True):
        return optimized
    anchors = _source_stt_anchor_rows(source_segments)
    if not anchors:
        return optimized
    min_source_chars = max(2, _setting_int(settings, "subtitle_final_stt_anchor_guard_min_source_chars", 3))
    rows = [dict(row) for row in list(optimized or []) if isinstance(row, dict)]
    inserted_count = 0
    for anchor in anchors:
        if int(anchor.get("_source_candidate_index", 0) or 0) != 0:
            continue
        anchor_text = str(anchor.get("text", "") or "").strip()
        if len(_stt_candidate_compact_text(anchor_text)) < min_source_chars:
            continue
        if _stt_anchor_is_represented(anchor, rows, settings):
            continue
        anchor_span = _subtitle_row_span(anchor)
        if anchor_span is None:
            continue
        anchor_start, anchor_end = anchor_span
        rows = _trim_rows_for_inserted_stt_anchor(rows, anchor, settings)
        rows.append(
            {
                **_stt_selection_metadata(anchor),
                "start": float(anchor_start),
                "end": float(anchor_end),
                "text": anchor_text,
                "stt_selected_source": str(anchor.get("source") or anchor.get("stt_selected_source") or "STT"),
                "_stt_original_candidate_start": float(anchor_start),
                "_stt_original_candidate_end": float(anchor_end),
                "_final_stt_anchor_guard_policy": {
                    "task": "final_stt_anchor_guard",
                    "stage": stage,
                    "action": "insert_missing_stt_anchor",
                    "new_text": anchor_text,
                    "source": str(anchor.get("source") or "STT"),
                    "source_segment_index": anchor.get("_source_segment_index"),
                    "source_candidate_index": anchor.get("_source_candidate_index"),
                },
            }
        )
        inserted_count += 1
    if inserted_count:
        rows.sort(key=lambda item: (float(item.get("start", 0.0) or 0.0), float(item.get("end", 0.0) or 0.0)))
        get_logger().log(f"[자막무결성-STT앵커] {stage}: 최종 자막에서 누락된 STT 앵커 {inserted_count}개 복구")
    return rows


def _attach_final_integrity_policy(rows: list[dict], policy: dict) -> list[dict]:
    if not rows:
        return rows
    out = [dict(row) for row in rows]
    out[0]["_final_transcript_integrity_policy"] = dict(policy)
    return out


def _nonempty_subtitle_segment_count(rows: list[dict] | None) -> int:
    return sum(
        1
        for seg in rows or []
        if isinstance(seg, dict) and str(seg.get("text", "") or "").strip()
    )


def _final_transcript_integrity_guard(
    optimized: list[dict],
    source_segments: list[dict],
    vad_segments: list[dict] | None,
    settings: dict | None,
) -> list[dict]:
    del vad_segments
    settings = dict(settings or {})
    if not _bool_setting(settings, "subtitle_final_integrity_guard_enabled", True):
        return optimized
    if not optimized or not source_segments:
        return optimized
    source_text = _sequence_text_for_integrity(source_segments)
    final_text = _sequence_text_for_integrity(optimized)
    if not source_text or not final_text:
        return optimized

    guard_settings = {
        **settings,
        "llm_verifier_enabled": True,
        "llm_verifier_block_added_content_tokens": True,
        "llm_verifier_preserve_numbers": True,
        "llm_verifier_preserve_interjections": True,
        "llm_verifier_min_similarity": max(
            0.9,
            _setting_float(settings, "subtitle_final_integrity_min_similarity", 0.9),
            _setting_float(settings, "llm_verifier_min_similarity", 0.86),
        ),
        "llm_verifier_max_length_delta_ratio": min(
            0.12,
            _setting_float(settings, "subtitle_final_integrity_max_length_delta_ratio", 0.12),
            _setting_float(settings, "llm_verifier_max_length_delta_ratio", 0.16),
        ),
        "llm_verifier_max_chunks": max(1, _setting_int(settings, "llm_verifier_max_chunks", 8)),
    }
    verified, decision = verify_llm_chunks_for_subtitle(
        source_text,
        [final_text],
        guard_settings,
        _profile_from_settings(settings),
    )
    policy = {
        "task": "final_transcript_integrity_guard",
        "accepted": bool(verified),
        "reason": str(decision.get("reason") or "ok"),
        "source_segments": _nonempty_subtitle_segment_count(source_segments),
        "final_segments": _nonempty_subtitle_segment_count(optimized),
        "source_compact_len": decision.get("source_compact_len"),
        "candidate_compact_len": decision.get("candidate_compact_len"),
        "similarity": decision.get("similarity"),
        "length_delta_ratio": decision.get("length_delta_ratio"),
    }
    if verified is not None:
        return _attach_final_integrity_policy(optimized, policy)

    fallback = _safe_source_integrity_variant(source_segments, settings)
    if not fallback:
        get_logger().log(
            "[자막무결성-경고] 최종 자막이 STT 원문과 불일치하지만 복구할 STT 원문 세그먼트가 없습니다 "
            f"({describe_llm_verifier_decision(decision)})"
        )
        return _attach_final_integrity_policy(optimized, {**policy, "fallback": "unavailable"})
    get_logger().log(
        "[자막무결성-롤백] 최종 자막이 STT1/2 원문 흐름과 불일치하여 STT 원문 기반 결과로 복구 "
        f"({describe_llm_verifier_decision(decision)})"
    )
    return _attach_final_integrity_policy(
        fallback,
        {
            **policy,
            "fallback": "source_stt_segments",
            "accepted": False,
        },
    )


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


def _attach_lora_and_deep_timing(row: dict, lora_meta: dict | None, settings: dict | None) -> dict:
    adjusted, timing_meta = deep_adjust_subtitle_timing(row, settings or {}, _profile_from_settings(settings))
    merged_meta = dict(lora_meta or {})
    if timing_meta:
        merged_meta["_deep_timing_policy"] = timing_meta
    attached = attach_segment_lora_settings(adjusted, merged_meta)
    for meta_key in (
        "_deep_rerank_policy",
        "_deep_candidate_selector_policy",
        "_deep_timing_policy",
        "_editor_truth_runtime_policy",
        "_stt_lattice_policy",
        "_llm_gate_policy",
        "_llm_minimize_policy",
        "_llm_candidate_policy",
        "_llm_verifier_policy",
        "_llm_rollback_policy",
        "_llm_rewrite_policy",
        "_llm_macro_chunk_policy",
        "_accuracy_decision_graph",
    ):
        if meta_key in merged_meta:
            attached[meta_key] = merged_meta[meta_key]
    return attached


def _select_stt_candidate_fast(seg: dict, settings: dict | None = None) -> dict | None:
    settings = settings or _get_user_settings()
    candidates = [
        c for c in list(seg.get("stt_candidates") or [])
        if isinstance(c, dict) and str(c.get("text", "") or "").strip()
    ]
    unique: list[dict] = []
    seen = set()
    for cand in candidates:
        key = re.sub(r"\s+", "", str(cand.get("text", "") or "")).lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(cand)
    if len(unique) < 2:
        return None

    raw_guard_decision = _select_raw_stt_candidate_when_current_is_unbacked(
        seg,
        unique,
        settings,
        selector="stt_raw_candidate_guard",
    )
    if raw_guard_decision:
        return raw_guard_decision

    lattice_decision, lattice_meta = select_stt_lattice_text(seg, settings, _profile_from_settings(settings))
    if lattice_decision:
        lattice_meta = dict(lattice_meta or {})
        raw_ok, raw_meta = _stt_decision_matches_raw_candidate(lattice_decision, unique, settings)
        lattice_meta["raw_candidate_guard"] = raw_meta
        if not raw_ok:
            get_logger().log(
                "[STT격자-딥러닝판정] STT1/STT2 원문과 의미 거리가 커서 자동 선택 보류: "
                f"similarity={raw_meta.get('similarity_to_raw_candidate', '-')}"
            )
        else:
            selected = dict(lattice_decision)
            selected["_stt_lattice_policy"] = lattice_meta
            selected.setdefault("selector", "stt_lattice")
            get_logger().log(
                f"[STT격자-딥러닝판정] 단어 {lattice_meta.get('replacements', 0)}개 교체 "
                f"confidence={lattice_meta.get('confidence', '-')}: "
                f"'{str(selected.get('text', '') or '')[:18]}...'"
            )
            return selected

    if seg.get("stt_ensemble_primary_locked"):
        return None
    deep_decision = deep_select_stt_candidate({**seg, "stt_candidates": unique}, settings, _profile_from_settings(settings))
    if deep_decision:
        raw_ok, raw_meta = _stt_decision_matches_raw_candidate(deep_decision, unique, settings)
        if not raw_ok:
            get_logger().log(
                "[STT앙상블-딥러닝판정] STT1/STT2 원문과 의미 거리가 커서 자동 선택 보류: "
                f"similarity={raw_meta.get('similarity_to_raw_candidate', '-')}"
            )
            return None
        deep_decision = {**deep_decision, "_stt_raw_candidate_guard": raw_meta}
        source = str(deep_decision.get("source", "") or "").strip().upper()
        label = str(deep_decision.get("label", "") or "").strip()
        get_logger().log(
            f"[STT앙상블-딥러닝판정] {label or '-'}({source or '-'}) 선택 "
            f"score={deep_decision.get('score', '-')} margin={deep_decision.get('margin', '-')}: "
            f"'{str(deep_decision.get('text', '') or '')[:18]}...'"
        )
        return deep_decision
    if _setting_bool(settings, "stt_selection_score_fallback_enabled", True):
        best_candidate = _best_scored_stt_candidate(unique)
        best_score = _stt_candidate_score100(best_candidate)
        current_score = _stt_current_candidate_score(seg, unique)
        min_score = _setting_float(settings, "stt_selection_score_fallback_min_score", 84.0)
        min_margin = _setting_float(settings, "stt_selection_score_fallback_min_margin", 12.0)
        if (
            best_candidate
            and best_score >= min_score
            and (best_score - current_score) >= min_margin
            and _stt_candidate_similarity(str(best_candidate.get("text", "") or ""), str(seg.get("text", "") or "")) < 0.995
        ):
            selected_text = str(best_candidate.get("text", "") or "").strip()
            selected_source = str(best_candidate.get("source", "") or "").strip().upper()
            get_logger().log(
                "[STT앙상블-점수판정] 최고 STT 점수 후보 우선 선택: "
                f"{selected_source or '-'} score={best_score:.1f} margin={best_score - current_score:.1f} "
                f"'{selected_text[:18]}...'"
            )
            return {
                "text": selected_text,
                "source": selected_source,
                "label": str(best_candidate.get("label") or best_candidate.get("stt_label") or "score").strip(),
                "start": best_candidate.get("start"),
                "end": best_candidate.get("end"),
                "words": list(best_candidate.get("words") or []),
                "score": best_candidate.get("score", best_candidate.get("stt_score")),
                "selector": "stt_candidate_score_fallback",
                **_stt_decision_speaker_fields(best_candidate, seg),
            }
    return None


def _llm_model_disabled(model: str | None) -> bool:
    return not str(model or "").strip() or "사용 안함" in str(model or "")


def _raw_stt_candidates(candidates: list[dict] | tuple[dict, ...]) -> list[dict]:
    rows = []
    for candidate in list(candidates or []):
        if not isinstance(candidate, dict):
            continue
        source = str(
            candidate.get("source")
            or candidate.get("stt_preview_source")
            or candidate.get("stt_source")
            or candidate.get("engine")
            or ""
        ).strip().upper()
        text = str(candidate.get("text", candidate.get("output", "")) or "").strip()
        if source in {"STT1", "STT2"} and text:
            item = dict(candidate)
            item["source"] = source
            item["text"] = text
            rows.append(item)
    return rows


def _candidate_decision_from_raw_stt(candidate: dict, selector: str, reason: str) -> dict:
    selected_text = str(candidate.get("text", "") or "").strip()
    selected_source = str(candidate.get("source", "") or "").strip().upper()
    return {
        "text": selected_text,
        "source": selected_source,
        "label": str(candidate.get("label") or candidate.get("stt_label") or reason or selected_source or "raw").strip(),
        "start": candidate.get("start"),
        "end": candidate.get("end"),
        "words": list(candidate.get("words") or []),
        "score": candidate.get("score", candidate.get("stt_score")),
        "selector": selector,
        "_stt_no_llm_raw_candidate_policy": {
            "task": "stt_no_llm_raw_candidate_lock",
            "reason": reason,
            "source": selected_source,
            "raw_text": selected_text,
        },
        **_stt_decision_speaker_fields(candidate, {}),
    }


def _select_stt_candidate_without_llm(seg: dict, candidates: list[dict], settings: dict | None) -> dict | None:
    raw_candidates = _raw_stt_candidates(candidates)
    if not raw_candidates:
        return None

    selected_sources = []
    for key in (
        "manual_stt_candidate_source",
        "stt_selected_source",
        "stt_ensemble_llm_selected_source",
        "stt_ensemble_fast_selected_source",
        "stt_ensemble_source",
    ):
        source = str(seg.get(key, "") or "").strip().upper()
        if source in {"STT1", "STT2"} and source not in selected_sources:
            selected_sources.append(source)
    for source in selected_sources:
        matches = [candidate for candidate in raw_candidates if str(candidate.get("source", "") or "").strip().upper() == source]
        if matches:
            chosen = max(matches, key=_stt_candidate_score100)
            return _candidate_decision_from_raw_stt(chosen, "stt_raw_candidate_no_llm", "selected_source")

    raw_guard_decision = _select_raw_stt_candidate_when_current_is_unbacked(
        seg,
        raw_candidates,
        settings,
        selector="stt_raw_candidate_guard_no_llm",
    )
    if raw_guard_decision:
        return raw_guard_decision

    current_text = str(seg.get("text", "") or "").strip()
    if current_text:
        current_key = _stt_candidate_compact_text(current_text)
        if any(_stt_candidate_compact_text(str(candidate.get("text", "") or "")) == current_key for candidate in raw_candidates):
            return None

    if _setting_bool(settings or {}, "stt_selection_score_fallback_enabled", True):
        best_candidate = _best_scored_stt_candidate(raw_candidates)
        best_score = _stt_candidate_score100(best_candidate)
        current_score = _stt_current_candidate_score(seg, raw_candidates)
        min_score = _setting_float(settings or {}, "stt_selection_score_fallback_min_score", 84.0)
        min_margin = _setting_float(settings or {}, "stt_selection_score_fallback_min_margin", 12.0)
        if (
            best_candidate
            and best_score >= min_score
            and (best_score - current_score) >= min_margin
            and _stt_candidate_similarity(str(best_candidate.get("text", "") or ""), current_text) < 0.995
        ):
            get_logger().log(
                "[STT앙상블-LLM꺼짐] raw STT 후보만 보수 선택: "
                f"{str(best_candidate.get('source', '') or '-')} score={best_score:.1f} "
                f"'{str(best_candidate.get('text', '') or '')[:18]}...'"
            )
            return _candidate_decision_from_raw_stt(best_candidate, "stt_candidate_score_fallback_no_llm", "score_fallback")
    return None


def _stt_candidate_compact_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE).lower()


def _stt_candidate_similarity(left: str, right: str) -> float:
    ltxt = _stt_candidate_compact_text(left)
    rtxt = _stt_candidate_compact_text(right)
    if not ltxt and not rtxt:
        return 1.0
    if not ltxt or not rtxt:
        return 0.0
    return difflib.SequenceMatcher(None, ltxt, rtxt).ratio()


def _stt_candidate_score100(candidate: dict | None) -> float:
    candidate = candidate or {}
    for key in ("stt_score", "score", "confidence", "probability", "avg_confidence"):
        if candidate.get(key) is None:
            continue
        try:
            value = float(candidate.get(key))
        except (TypeError, ValueError):
            continue
        if value <= 1.0:
            value *= 100.0
        return max(0.0, min(100.0, value))
    return 0.0


def _selected_decision_word_span(decision: dict | None) -> tuple[float, float] | None:
    words = [word for word in list((decision or {}).get("words") or []) if isinstance(word, dict)]
    if not words:
        return None
    starts = []
    ends = []
    for word in words:
        try:
            starts.append(float(word.get("start")))
            ends.append(float(word.get("end")))
        except (TypeError, ValueError):
            continue
    if not starts or not ends:
        return None
    start = min(starts)
    end = max(ends)
    if end <= start:
        return None
    return start, end


def _looks_like_relative_word_span(word_span: tuple[float, float], selected_span: tuple[float, float] | None) -> bool:
    if selected_span is None:
        return False
    selected_start, selected_end = selected_span
    duration = max(0.05, selected_end - selected_start)
    word_start, word_end = word_span
    return bool(
        selected_start > 5.0
        and word_start < 2.0
        and word_end <= max(2.0, duration + 1.0)
        and abs(word_start - selected_start) > 2.0
    )


def _candidate_span_from_decision(decision: dict | None) -> tuple[float, float] | None:
    try:
        start = float((decision or {}).get("start"))
        end = float((decision or {}).get("end"))
    except (TypeError, ValueError):
        return None
    return (start, end) if end > start else None


def _stt_decision_timing_span(decision: dict | None) -> tuple[float, float] | None:
    selected_span = _candidate_span_from_decision(decision)
    word_span = _selected_decision_word_span(decision)
    if word_span is None or _looks_like_relative_word_span(word_span, selected_span):
        return selected_span
    if selected_span is None:
        return word_span
    selected_start, selected_end = selected_span
    word_start, word_end = word_span
    overlap = max(0.0, min(selected_end, word_end) - max(selected_start, word_start))
    word_dur = max(0.001, word_end - word_start)
    selected_dur = max(0.001, selected_end - selected_start)
    overlap_ratio = overlap / min(word_dur, selected_dur)
    if overlap_ratio < 0.25 and max(abs(word_start - selected_start), abs(word_end - selected_end)) > 0.35:
        return word_span
    return selected_span


def _best_scored_stt_candidate(candidates: list[dict] | tuple[dict, ...]) -> dict | None:
    rows = [c for c in list(candidates or []) if isinstance(c, dict) and str(c.get("text", "") or "").strip()]
    if not rows:
        return None
    return max(
        rows,
        key=lambda candidate: (
            _stt_candidate_score100(candidate),
            len(_stt_candidate_compact_text(str(candidate.get("text", "") or ""))),
        ),
    )


def _stt_current_candidate_score(seg: dict, candidates: list[dict] | tuple[dict, ...]) -> float:
    current_text = str((seg or {}).get("text", "") or "")
    current_score = _stt_candidate_score100(seg)
    best_match_score = 0.0
    best_match_similarity = 0.0
    for candidate in list(candidates or []):
        if not isinstance(candidate, dict):
            continue
        similarity = _stt_candidate_similarity(current_text, str(candidate.get("text", "") or ""))
        if similarity > best_match_similarity:
            best_match_similarity = similarity
            best_match_score = _stt_candidate_score100(candidate)
    if best_match_similarity >= 0.96:
        return best_match_score
    return current_score


def _select_raw_stt_candidate_when_current_is_unbacked(
    seg: dict,
    candidates: list[dict] | tuple[dict, ...],
    settings: dict | None,
    *,
    selector: str,
) -> dict | None:
    if not _setting_bool(settings or {}, "stt_selection_raw_guard_enabled", True):
        return None
    raw_candidates = _raw_stt_candidates(candidates)
    if not raw_candidates:
        return None
    current_text = str((seg or {}).get("text", "") or "").strip()
    if not current_text:
        return None
    best_similarity = max(_stt_candidate_similarity(current_text, str(candidate.get("text", "") or "")) for candidate in raw_candidates)
    compact_len = len(_stt_candidate_compact_text(current_text))
    min_similarity = _setting_float(settings or {}, "stt_selection_raw_guard_min_similarity", 0.68)
    if compact_len <= 12:
        min_similarity = max(min_similarity, 0.76)
    elif compact_len <= 24:
        min_similarity = max(min_similarity, 0.72)
    if best_similarity >= min_similarity:
        return None
    best_candidate = _best_scored_stt_candidate(raw_candidates)
    if not best_candidate:
        return None
    min_score = _setting_float(settings or {}, "stt_selection_raw_guard_min_score", 0.0)
    best_score = _stt_candidate_score100(best_candidate)
    if best_score < min_score:
        return None
    source = str(best_candidate.get("source", "") or "").strip().upper()
    selected_text = str(best_candidate.get("text", "") or "").strip()
    get_logger().log(
        "[STT원문가드] 현재 자막이 STT1/STT2 후보와 멀어 raw 후보로 복구: "
        f"{source or '-'} similarity={best_similarity:.3f}/{min_similarity:.3f} "
        f"score={best_score:.1f} '{selected_text[:18]}...'"
    )
    return _candidate_decision_from_raw_stt(best_candidate, selector, "current_not_stt_candidate")


def _stt_decision_matches_raw_candidate(decision: dict | None, candidates: list[dict], settings: dict | None) -> tuple[bool, dict]:
    decision_text = str((decision or {}).get("text", "") or "").strip()
    if not decision_text:
        return False, {"accepted": False, "reason": "empty_decision"}
    raw = [
        c for c in list(candidates or [])
        if isinstance(c, dict)
        and str(c.get("text", "") or "").strip()
        and str(c.get("source", "") or "").strip().upper() in {"STT1", "STT2"}
    ]
    if not raw:
        raw = [c for c in list(candidates or []) if isinstance(c, dict) and str(c.get("text", "") or "").strip()]
    if not raw:
        return False, {"accepted": False, "reason": "no_raw_candidates"}
    best_similarity = max(_stt_candidate_similarity(decision_text, str(c.get("text", "") or "")) for c in raw)
    compact_len = len(_stt_candidate_compact_text(decision_text))
    min_similarity = _setting_float(settings or {}, "stt_selection_min_raw_candidate_similarity", 0.72)
    if compact_len <= 12:
        min_similarity = max(min_similarity, 0.82)
    elif compact_len <= 24:
        min_similarity = max(min_similarity, 0.76)
    ok = best_similarity >= min_similarity
    return ok, {
        "accepted": ok,
        "reason": "raw_candidate_similarity" if ok else "too_far_from_stt1_stt2",
        "similarity_to_raw_candidate": round(best_similarity, 4),
        "min_similarity": round(min_similarity, 4),
    }


def _stt_candidate_risk_flags(seg: dict, candidates: list[dict]) -> set[str]:
    flags: set[str] = set()
    for row in [seg, *candidates]:
        for flag in row.get("stt_score_flags") or []:
            flags.add(str(flag))
        quality = dict(row.get("quality") or {})
        for flag in quality.get("flags") or []:
            flags.add(str(flag))
    return flags


def _should_run_stt_candidate_llm_judge(seg: dict, candidates: list[dict], settings: dict | None) -> bool:
    settings = settings or {}
    if not _setting_bool(settings, "stt_ensemble_llm_judge_require_risk", True):
        return True
    if len(candidates) < 2:
        return False

    texts = [str(c.get("text", "") or "").strip() for c in candidates]
    if len({_stt_candidate_compact_text(text) for text in texts if text}) < 2:
        return False

    if seg.get("stt_ensemble_primary_locked") or seg.get("stt_ensemble_needs_llm_review"):
        return True
    if seg.get("stt_ensemble_inserted_from_stt2") or str(seg.get("_uncertainty_bucket") or "") == "precision":
        return True

    scores = [_stt_candidate_score100(c) for c in candidates]
    current_score = _stt_candidate_score100(seg)
    low_threshold = _setting_float(settings, "stt_ensemble_llm_judge_low_score_threshold", 78.0)
    if current_score and current_score < low_threshold:
        return True
    if any(score and score < low_threshold for score in scores):
        return True

    score_span = max(scores or [0.0]) - min(scores or [0.0])
    min_delta = _setting_float(settings, "stt_ensemble_llm_judge_min_score_delta", 10.0)
    if score_span >= min_delta:
        return True

    max_similarity = _setting_float(settings, "stt_ensemble_llm_judge_max_similarity", 0.94)
    pair_similarity = min(
        _stt_candidate_similarity(texts[i], texts[j])
        for i in range(len(texts))
        for j in range(i + 1, len(texts))
    )
    if pair_similarity <= max_similarity:
        return True

    risky_flags = {
        "low_avg_logprob",
        "high_no_speech_prob",
        "high_compression_ratio",
        "low_word_confidence",
        "peer_text_disagreement",
        "repetition_hallucination_risk",
        "known_hallucination_phrase",
        "outside_vad_speech",
    }
    return bool(_stt_candidate_risk_flags(seg, candidates).intersection(risky_flags))


def _parse_stt_candidate_llm_label(raw_decision: str, labels: list[str]) -> str | None:
    text = str(raw_decision or "").strip()
    if not text:
        return None
    valid = {label.upper(): label for label in labels}

    def _from_value(value) -> str | None:
        if isinstance(value, str):
            compact = value.strip().upper()
            if compact in valid:
                return valid[compact]
            match = re.search(r"\b([A-Z])\b", compact)
            if match and match.group(1) in valid:
                return valid[match.group(1)]
        if isinstance(value, list):
            for item in value:
                found = _from_value(item)
                if found:
                    return found
        if isinstance(value, dict):
            for key in ("selected", "selection", "label", "choice", "answer", "winner"):
                found = _from_value(value.get(key))
                if found:
                    return found
            for item in value.values():
                found = _from_value(item)
                if found:
                    return found
        return None

    try:
        parsed = json.loads(text)
        found = _from_value(parsed)
        if found:
            return found
    except Exception:
        pass

    match = re.search(r"(?:선택|selected|selection|choice|answer|winner)\s*[:=]?\s*[\"']?([A-Z])", text, re.IGNORECASE)
    if match and match.group(1).upper() in valid:
        return valid[match.group(1).upper()]
    leading = re.match(r"^\s*(?:\[)?\s*[\"']?([A-Z])\b", text)
    if leading and leading.group(1).upper() in valid:
        return valid[leading.group(1).upper()]
    matches = [m.group(1).upper() for m in re.finditer(r"\b([A-Z])\b", text)]
    usable = [valid[label] for label in matches if label in valid]
    if len(usable) == 1:
        return usable[0]
    return None


def _apply_stt_candidate_decision(seg: dict, selected_decision: dict | None) -> tuple[dict, bool]:
    if not selected_decision:
        return dict(seg or {}), False
    selected_text = str(selected_decision.get("text", "") or "").strip()
    if not selected_text:
        return dict(seg or {}), False
    selected_source = str(selected_decision.get("source", "") or "").strip().upper()
    selector_name = str(selected_decision.get("selector") or "")
    is_deep_selector = bool(selector_name) and selector_name not in {
        "stt_lattice",
        "stt_candidate_llm_judge",
        "stt_candidate_score_fallback",
    }
    matched_candidate = _find_matching_stt_candidate_for_decision(seg, selected_decision)
    speaker_fields = _stt_decision_speaker_fields(selected_decision, matched_candidate or seg)
    out = {
        **dict(seg or {}),
        "text": selected_text,
        "stt_ensemble_llm_selected_source": selected_source,
        "stt_ensemble_llm_selected_label": str(selected_decision.get("label", "") or ""),
        "stt_ensemble_fast_selected_source": selected_source,
        "stt_ensemble_fast_selected_label": str(selected_decision.get("label", "") or ""),
        "stt_ensemble_deep_selected_source": selected_source if is_deep_selector else "",
        "stt_ensemble_deep_selected_label": str(selected_decision.get("label", "") or "") if is_deep_selector else "",
        "stt_ensemble_deep_selected_score": selected_decision.get("score") if is_deep_selector else None,
        "stt_ensemble_deep_selected_margin": selected_decision.get("margin") if is_deep_selector else None,
        "_stt_lattice_policy": selected_decision.get("_stt_lattice_policy") or seg.get("_stt_lattice_policy"),
        "_stt_no_llm_raw_candidate_policy": selected_decision.get("_stt_no_llm_raw_candidate_policy") or seg.get("_stt_no_llm_raw_candidate_policy"),
        "_deep_candidate_selector_policy": selected_decision.get("_deep_candidate_selector_policy") or seg.get("_deep_candidate_selector_policy"),
        "_llm_gate_policy": selected_decision.get("_llm_gate_policy") or seg.get("_llm_gate_policy"),
        **speaker_fields,
    }
    if selected_decision.get("words"):
        out["words"] = list(selected_decision.get("words") or [])
    selected_span = _stt_decision_timing_span(selected_decision)
    if selected_span is not None:
        selected_start, selected_end = selected_span
        out["start"] = selected_start
        out["end"] = selected_end
        out["_stt_original_candidate_start"] = selected_start
        out["_stt_original_candidate_end"] = selected_end
        out["original_start"] = selected_start
        out["original_end"] = selected_end
        word_span = _selected_decision_word_span(selected_decision)
        raw_span = _candidate_span_from_decision(selected_decision)
        if word_span is not None and raw_span is not None and selected_span == word_span:
            out["_stt_candidate_word_timing_anchor_policy"] = {
                "task": "stt_candidate_word_timing_anchor",
                "old_start": round(raw_span[0], 3),
                "old_end": round(raw_span[1], 3),
                "word_start": round(word_span[0], 3),
                "word_end": round(word_span[1], 3),
            }
    return out, True


def _select_stt_candidate_text(
    seg: dict,
    model: str,
    user_prompt: str,
    api_key: str,
    settings: dict | None = None,
    rules: dict | None = None,
) -> dict | None:
    settings = settings or _get_user_settings()
    if not settings.get("stt_ensemble_llm_judge_enabled", True):
        return None
    candidates = [
        c for c in list(seg.get("stt_candidates") or [])
        if str(c.get("text", "") or "").strip()
    ]
    unique: list[dict] = []
    seen = set()
    for cand in candidates:
        key = re.sub(r"\s+", "", str(cand.get("text", "") or "")).lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(cand)
    if len(unique) < 2:
        return None
    if _llm_model_disabled(model):
        return _select_stt_candidate_without_llm(seg, unique, settings)
    fast_decision = _select_stt_candidate_fast({**seg, "stt_candidates": unique}, settings)
    if fast_decision:
        return fast_decision
    if not _should_run_stt_candidate_llm_judge(seg, unique, settings):
        return None
    if not model or "사용 안함" in model:
        return None
    if _setting_bool(settings, "stt_ensemble_llm_judge_local_only", True) and (
        "Gemini" in model or is_openai_model(model) or is_codex_model(model)
    ):
        get_logger().log(f"[STT앙상블-LLM판정] 로컬 LLM 전용 정책으로 외부/CLI 모델 생략: {model}")
        return None

    unique = unique[:2]
    labels = ["A", "B"]
    lines = []
    for label, cand in zip(labels, unique):
        lines.append(
            f"{label}. [{cand.get('source', label)} / score {cand.get('score', '-')}] "
            f"{str(cand.get('text', '')).strip()}"
        )
    prompt = (
        "당신은 한국어 영상 자막 검수자입니다.\n"
        "아래 앞뒤 문맥을 참고해서 STT 후보 중 실제 발화와 가장 가까운 후보 하나만 고르세요.\n"
        "없는 말을 새로 만들거나 두 후보를 섞지 말고, 후보의 뜻을 바꾸는 추론은 하지 마세요.\n"
        "애매하면 score가 더 높은 STT 원문 후보를 고르세요.\n"
        "반드시 JSON 배열로만 답하세요. 예: [\"A\"] 또는 [\"B\"]\n\n"
        f"시간: {float(seg.get('start', 0) or 0):.2f}s ~ {float(seg.get('end', 0) or 0):.2f}s\n"
        f"이전 문맥: {str(seg.get('stt_ensemble_context_prev', '') or '').strip()[:220] or '(없음)'}\n"
        f"다음 문맥: {str(seg.get('stt_ensemble_context_next', '') or '').strip()[:220] or '(없음)'}\n"
        + "\n".join(lines)
    )
    if user_prompt.strip():
        prompt += f"\n\n사용자 지시 참고: {user_prompt.strip()[:500]}"
    lora_context = build_runtime_lora_prompt(
        " ".join(
            [
                str(seg.get("text", "") or ""),
                str(seg.get("stt_ensemble_context_prev", "") or ""),
                str(seg.get("stt_ensemble_context_next", "") or ""),
                " ".join(str(candidate.get("text", "") or "") for candidate in unique),
            ]
        ),
        rules or {},
        settings,
        include_retrieval=False,
    )
    if lora_context:
        prompt += f"\n\n[STT 후보 선택용 LoRA 근거]\n{lora_context}"

    gate_text = " ".join(str(candidate.get("text", "") or "") for candidate in unique)
    stt_llm_gate = llm_gate_decision(
        {**seg, "stt_ensemble_needs_llm_review": True},
        settings,
        _profile_from_settings(settings),
        text=gate_text,
        threshold=max(1, _setting_int(settings, "split_length_threshold", 16)),
        duration=max(0.0, float(seg.get("end", 0) or 0) - float(seg.get("start", 0) or 0)),
    )
    if not stt_llm_gate.get("call_llm", True):
        get_logger().log(
            f"[STT앙상블-LLM게이트] LoRA/딥러닝 신뢰로 후보 LLM 생략: "
            f"'{str(seg.get('text', '') or '')[:18]}...'"
        )
        return None

    try:
        if "Gemini" in model:
            chunks = gemini_split_text(api_key, model, prompt)
        elif is_openai_model(model):
            chunks = openai_split_text(api_key, model, prompt)
        else:
            if not _local_ollama_ready(model, "STT 앙상블 LLM"):
                return None
            model = _resolve_runtime_llm_model(model, logger=get_logger(), context="STT 앙상블 LLM")
            chunks = ollama_split_text(model, prompt)
    except Exception as exc:
        if _is_local_llm_connection_error(exc):
            _mark_local_llm_unavailable(model, "STT 앙상블 LLM", str(exc))
            return None
        get_logger().log(f"[STT앙상블-LLM판정 실패] {exc}")
        return None

    decision = " ".join(str(x) for x in (chunks or []))
    selected_label = _parse_stt_candidate_llm_label(decision, labels)
    if selected_label not in labels:
        fallback_candidate = _best_scored_stt_candidate(unique)
        if not fallback_candidate:
            get_logger().log(f"[STT앙상블-LLM판정] 응답 파싱 실패, 자동 선택 보류: {decision[:120]}")
            return None
        selected = str(fallback_candidate.get("text", "") or "").strip()
        if not selected:
            return None
        selected_source = str(fallback_candidate.get("source", "") or "").strip().upper()
        fallback_label = str(fallback_candidate.get("label") or fallback_candidate.get("stt_label") or "score").strip()
        get_logger().log(
            "[STT앙상블-LLM판정] 응답 파싱 실패, 최고 STT 점수 후보로 보수 선택: "
            f"{selected_source or '-'} score={_stt_candidate_score100(fallback_candidate):.1f} '{selected[:18]}...'"
        )
        return {
            "text": selected,
            "source": selected_source,
            "label": fallback_label,
            "start": fallback_candidate.get("start"),
            "end": fallback_candidate.get("end"),
            "words": list(fallback_candidate.get("words") or []),
            "score": fallback_candidate.get("score", fallback_candidate.get("stt_score")),
            "selector": "stt_candidate_score_fallback",
            "_llm_gate_policy": stt_llm_gate,
            **_stt_decision_speaker_fields(fallback_candidate, seg),
        }
    selected_index = labels.index(selected_label)
    selected_candidate = unique[selected_index]
    selected = str(selected_candidate.get("text", "") or "").strip()
    selected_source = str(selected_candidate.get("source", "") or "").strip().upper()
    if selected:
        get_logger().log(f"[STT앙상블-LLM판정] {labels[selected_index]}({selected_source or '-'}) 선택: '{selected[:18]}...'")
    if not selected:
        return None
    return {
        "text": selected,
        "source": selected_source,
        "label": labels[selected_index],
        "start": selected_candidate.get("start"),
        "end": selected_candidate.get("end"),
        "words": list(selected_candidate.get("words") or []),
        "score": selected_candidate.get("score", selected_candidate.get("stt_score")),
        "selector": "stt_candidate_llm_judge",
        "_llm_gate_policy": stt_llm_gate,
        **_stt_decision_speaker_fields(selected_candidate, seg),
    }


def _stt_selection_metadata(seg: dict) -> dict:
    keys = (
        "stt_candidates",
        "stt_ensemble_source",
        "stt_ensemble_similarity",
        "stt_ensemble_needs_llm_review",
        "stt_ensemble_inserted_from_stt2",
        "stt_ensemble_primary_region",
        "stt_ensemble_primary_locked",
        "stt_ensemble_word_rover",
        "stt_ensemble_llm_selected_source",
        "stt_ensemble_llm_selected_label",
        "stt_ensemble_deep_selected_source",
        "stt_ensemble_deep_selected_label",
        "stt_ensemble_deep_selected_score",
        "stt_ensemble_deep_selected_margin",
        "stt_selected_source",
        "score",
        "stt_score",
        "score_color",
        "stt_score_color",
        "stt_score_label",
        "stt_score_flags",
        "stt_score_components",
        "speaker_list",
        "speaker2",
        "_stt_speaker_marker_preserved",
        "_stt_original_candidate_start",
        "_stt_original_candidate_end",
        "_stt_original_candidate_start_frame",
        "_stt_original_candidate_end_frame",
        "_stt_candidate_word_timing_anchor_policy",
        "_stt_word_match_timing_policy",
        "_llm_stt_text_guard_policy",
        "_stt_no_llm_raw_candidate_policy",
        "_stt_no_llm_raw_text",
        "original_start",
        "original_end",
        "_stt_lattice_policy",
        "_deep_candidate_selector_policy",
        "_llm_gate_policy",
        "_uncertainty_policy",
        "_uncertainty_bucket",
        "_uncertainty_risk_score",
        "_codex_native_fast_path_policy",
    )
    return {key: seg[key] for key in keys if key in seg}


def _sanitize(segments: list[dict] | None) -> list[dict]:
    """Backward-compatible test hook for legacy subtitle filter overrides."""
    return [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]


def _restore_no_llm_raw_stt_text(segments: list[dict] | None) -> list[dict]:
    rows = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        row = dict(seg)
        policy = dict(row.get("_stt_no_llm_raw_candidate_policy") or {})
        raw_text = str(row.get("_stt_no_llm_raw_text") or policy.get("raw_text") or "").strip()
        if raw_text and str(row.get("text", "") or "").strip() != raw_text:
            row["text"] = raw_text
            policy.update(
                {
                    "task": "stt_no_llm_raw_text_lock",
                    "restored_after_postprocess": True,
                    "raw_text": raw_text,
                }
            )
            row["_stt_no_llm_raw_candidate_policy"] = policy
        rows.append(row)
    return rows


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
    model = _resolve_runtime_llm_model(model, logger=get_logger(), context="자막 LLM")
    short_m = model.split(":")[0].upper()
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

    args = [(seg, rules, threshold, corrections, model, user_prompt, api_key, conservative, loaded_settings) for seg in segments]
    optimized: list[dict] = []

    if "사용 안함" in model:
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
        max_workers, worker_mode = _effective_llm_workers(model, _EXAONE_WORKERS, loaded_settings, len(args))
        codex_native_fast_path = _codex_native_fast_path_enabled(model, loaded_settings, len(args))
        if worker_mode == "api":
            get_logger().log(f"🤖 {short_m} API 안전 모드: {max_workers}개 워커 순차 처리 중...")
        elif worker_mode == "local_auto":
            warmup_ollama_model(model, logger=get_logger())
            get_logger().log(
                f"{short_m} 리소스 자동 모드: {max_workers}개 워커 병렬 처리 "
                f"({len(segments)}개, CPU/메모리/작업량 기준)"
            )
        else:
            warmup_ollama_model(model, logger=get_logger())
            configured_workers = max(1, min(_EXAONE_WORKERS, len(args)))
            if max_workers < configured_workers:
                get_logger().log(
                    f"{short_m} 로컬 Ollama 안전 모드: {max_workers}개 워커 병렬 처리 "
                    f"(설정 {_EXAONE_WORKERS} → 제한 {max_workers}, {len(segments)}개)"
                )
            else:
                get_logger().log(f"{short_m} {max_workers}개 워커 병렬 처리 ({len(segments)}개)...")

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
            )
        elif max_workers == 1:
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
        else:
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

    optimized = refine_high_contextual_boundaries(
        optimized,
        vad_segments=vad_segments or [],
        settings=loaded_settings,
        rules=rules,
        model=model,
        logger=get_logger(),
    )
    _emit_processing_preview(
        stage_segments_callback,
        stage="high_context_boundary",
        stage_label="High 문맥 경계/단어 보정",
        segments=optimized,
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
    optimized = _apply_output_variant_selector(optimized, original_segments, vad_segments or [], loaded_settings, stage="llm")
    optimized = _enforce_final_subtitle_text_policy(optimized, corrections)
    optimized = _apply_final_sequence_cleanup(optimized, loaded_settings, stage="llm_final")
    optimized = _restore_final_stt_anchor_drift(optimized, original_segments, loaded_settings, stage="llm_final")
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
    if _llm_model_disabled(model):
        optimized = _restore_no_llm_raw_stt_text(optimized)
        optimized = _restore_missing_final_stt_anchor_rows(
            optimized,
            original_segments,
            loaded_settings,
            stage="no_llm_raw_text_lock",
        )
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
