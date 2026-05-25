# Version: 03.14.29
# Phase: PHASE2
"""LLM runtime, context, and verifier helpers for subtitle generation.

Behavior-preserving split from subtitle_engine.py.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time

from core.llm.secure_keys import get_api_key
from core.llm.gemini_provider import split_text as gemini_split_text
from core.llm.openai_provider import is_codex_model, is_openai_model, split_text as openai_split_text
from core.engine.llm_correction_guard import assess_llm_rewrite_policy
from core.engine.llm_candidate_policy import validate_candidate_locked_chunks
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
from core.engine.subtitle_native_word_split import native_builtin_word_groups as _native_builtin_word_groups
from core.engine.subtitle_prompts import _build_llm_prompt
from core.engine.subtitle_settings import (
    _effective_llm_workers as _effective_llm_workers_impl,
    _get_user_settings,
    _quality_conservative_enabled,
    _resolve_runtime_llm_model,
    _setting_float,
    _setting_int,
)
from core.engine.subtitle_text_policy import clean_subtitle_text as _clean
from core.engine.subtitle_text_policy import split_visible_len as _split_visible_len
from core.native_swift_subtitle_llm_context import (
    build_subtitle_llm_context_packs_via_swift,
    evaluate_subtitle_llm_context_gate_via_swift,
)
from core.personalization.deep_subtitle_policy import rerank_subtitle_candidates
from core.runtime.logger import get_logger

_S = _get_user_settings()
_LOCAL_OLLAMA_WORKER_CAP = _setting_int(_S, "local_ollama_llm_max_workers", 2)


def _engine_attr(name: str, fallback):
    owner = sys.modules.get("core.engine.subtitle_engine")
    return getattr(owner, name, fallback)


def _patched_engine_attr(name: str, current):
    attr = _engine_attr(name, current)
    return None if attr is current else attr


_get_logger_fallback = get_logger


def get_logger(*args, **kwargs):
    return _engine_attr("get_logger", _get_logger_fallback)(*args, **kwargs)


_rerank_subtitle_candidates_fallback = rerank_subtitle_candidates


def rerank_subtitle_candidates(*args, **kwargs):
    return _engine_attr("rerank_subtitle_candidates", _rerank_subtitle_candidates_fallback)(*args, **kwargs)


_llm_gate_decision_fallback = llm_gate_decision


def llm_gate_decision(*args, **kwargs):
    return _engine_attr("llm_gate_decision", _llm_gate_decision_fallback)(*args, **kwargs)


_llm_minimize_decision_fallback = llm_minimize_decision


def llm_minimize_decision(*args, **kwargs):
    return _engine_attr("llm_minimize_decision", _llm_minimize_decision_fallback)(*args, **kwargs)


_verify_llm_chunks_for_subtitle_fallback = verify_llm_chunks_for_subtitle


def verify_llm_chunks_for_subtitle(*args, **kwargs):
    return _engine_attr("verify_llm_chunks_for_subtitle", _verify_llm_chunks_for_subtitle_fallback)(*args, **kwargs)


_validate_candidate_locked_chunks_fallback = validate_candidate_locked_chunks


def validate_candidate_locked_chunks(*args, **kwargs):
    return _engine_attr("validate_candidate_locked_chunks", _validate_candidate_locked_chunks_fallback)(*args, **kwargs)


_assess_llm_rewrite_policy_fallback = assess_llm_rewrite_policy


def assess_llm_rewrite_policy(*args, **kwargs):
    return _engine_attr("assess_llm_rewrite_policy", _assess_llm_rewrite_policy_fallback)(*args, **kwargs)


def ensure_ollama_server(*args, **kwargs):
    patched = _patched_engine_attr("ensure_ollama_server", ensure_ollama_server)
    if patched is not None:
        return patched(*args, **kwargs)
    from core.llm.ollama_provider import ensure_ollama_server as _ensure_ollama_server

    return _ensure_ollama_server(*args, **kwargs)


def restart_ollama_server(*args, **kwargs):
    patched = _patched_engine_attr("restart_ollama_server", restart_ollama_server)
    if patched is not None:
        return patched(*args, **kwargs)
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
    patched = _patched_engine_attr("ollama_split_text", ollama_split_text)
    if patched is not None:
        return patched(*args, **kwargs)
    from core.llm.ollama_provider import split_text as _ollama_split_text

    return _ollama_split_text(*args, **kwargs)


def warmup_ollama_model(*args, **kwargs):
    patched = _patched_engine_attr("warmup_ollama_model", warmup_ollama_model)
    if patched is not None:
        return patched(*args, **kwargs)
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
        owner = sys.modules.get("core.engine.subtitle_engine")
        if owner is not None:
            setattr(owner, "_LOCAL_LLM_UNAVAILABLE_UNTIL", _LOCAL_LLM_UNAVAILABLE_UNTIL)
    if should_log:
        get_logger().log(
            f"[{context}] Ollama 연결 실패: {reason}. "
            f"로컬 LLM 단계를 {int(_LOCAL_LLM_BACKOFF_SEC)}초 동안 건너뛰고 STT 결과로 계속 진행합니다. "
            f"Ollama 앱/서버와 모델({model})을 확인해 주세요."
        )


def _local_ollama_ready(model: str, context: str) -> bool:
    global _LOCAL_LLM_UNAVAILABLE_UNTIL
    owner = sys.modules.get("core.engine.subtitle_engine")
    if owner is not None and hasattr(owner, "_LOCAL_LLM_UNAVAILABLE_UNTIL"):
        try:
            _LOCAL_LLM_UNAVAILABLE_UNTIL = float(getattr(owner, "_LOCAL_LLM_UNAVAILABLE_UNTIL"))
        except Exception:
            pass
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
