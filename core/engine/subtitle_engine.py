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
import re
import difflib  
import threading
import time

from core.llm.secure_keys import get_api_key
from core.llm.gemini_provider import split_text as gemini_split_text
from core.llm.ollama_provider import (
    ensure_ollama_server,
    restart_ollama_server,
    split_text as ollama_split_text,
    warmup_model as warmup_ollama_model,
)
from core.llm.openai_provider import is_codex_model, is_openai_model, split_text as openai_split_text
from core.audio.stt_lattice import select_stt_lattice_text
from core.engine.llm_correction_guard import assess_llm_rewrite_policy, safe_llm_chunks, validate_llm_chunks
from core.engine.llm_candidate_policy import (
    build_llm_candidate_options,
    validate_candidate_locked_chunks,
)
from core.engine.subtitle_macro_chunks import (
    build_llm_macro_groups as _build_llm_macro_groups,
    llm_macro_chunk_enabled as _llm_macro_chunk_enabled,
    process_llm_macro_groups as _process_llm_macro_groups,
)
from core.engine.subtitle_accuracy_pipeline import (
    append_accuracy_decision,
    annotate_subtitle_auto_review,
    annotate_subtitle_completion_report,
    annotate_subtitle_context_consistency,
    annotate_subtitle_lora_style_consistency,
    annotate_subtitle_stage_confidence,
    llm_gate_decision,
    llm_minimize_decision,
    repair_subtitle_context_consistency,
    rollback_decision,
    select_best_subtitle_output,
    subtitle_accuracy_metrics,
    verify_llm_chunks_for_subtitle,
)
from core.engine.subtitle_uncertainty import annotate_uncertainty_first_segments
from core.subtitle_quality.timestamp_regrouper import regroup_by_word_timestamps
from core.personalization.deep_subtitle_policy import (
    adjust_subtitle_timing as deep_adjust_subtitle_timing,
    rerank_subtitle_candidates,
    select_stt_candidate as deep_select_stt_candidate,
    smooth_subtitle_sequence,
)
from core.personalization.deep_policy_learning import record_deep_policy_events_for_segments
from core.personalization.deep_runtime_adaptation import adapt_runtime_settings_from_deep_events
from core.personalization.editor_truth_memory import apply_recent_editor_truth_patterns
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


def _effective_llm_workers(model: str, configured_workers: int, settings: dict, segment_count: int) -> tuple[int, str]:
    return _effective_llm_workers_impl(model, configured_workers, settings, segment_count, local_worker_cap=_LOCAL_OLLAMA_WORKER_CAP)

# ━━━ 🛠️ [시스템 고정 상수] ━━━
_MIN_CHARS       = 5     
_PRE_MERGE_MULT  = 3.0   
_ENFORCE_RATIO   = 1.5   
_HALLUC_MIN_DUR  = 0.8   
_HALLUC_MAX_CHARS = 10   
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

# 💡 [신규 이식] media_processor에서 이사 온 환각 방지 리스트
_HALLUC_PHRASES = [
    "한국어 대화", "자막 생성",
    "번역 중", "처리 중", "대화 내용", "Korean conversation",
    "subtitle", "transcription", "Thank you for watching"
]

_TS_BRACKET = re.compile(r'\[\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*\]\s*')
_TS_NO_BRACKET = re.compile(r'^\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s+') 
_JUNK_PATTERN = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')

def _clean(text: str, corrections: dict | None = None) -> str:
    original = text
    text = _TS_BRACKET.sub(' ', text)
    text = _TS_NO_BRACKET.sub(' ', text)
    
    if text != original:
        get_logger().log(f"[정제-시간태그] 삭제: '{original[:15]}' => '{text[:15]}'")
    
    text = _JUNK_PATTERN.sub("", text)
    text = text.replace(".", "").replace("\r", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split('\n')]
    text = "\n".join(line for line in lines if line)
    
    if corrections:
        for old, new in corrections.items():
            if old and old in text:
                text = text.replace(old, new)
                get_logger().log(f"[정제-교정사전] 적용: '{old}' => '{new}'")
    return text

def _sanitize(segments: list[dict], corrections: dict) -> list[dict]:
    result = []
    for seg in segments:
        text = _clean(seg.get("text", ""), corrections)
        if not text: continue
            
        # 💡 [환각 문구 검사]
        is_halluc = False
        for phrase in _HALLUC_PHRASES:
            if phrase in text:
                get_logger().log(f"[삭제-환각문구] '{text[:15]}...'")
                is_halluc = True
                break
        if is_halluc: continue
            
        if not re.search(r"[가-힣a-zA-Z]", text): continue
            
        clean_len = len(text.replace(" ", "").replace("\n", ""))
        duration = seg.get("end", 0) - seg.get("start", 0)
        
        # 💡 [환청/복사 버그 필터]
        if duration < _HALLUC_MIN_DUR and len(text) > _HALLUC_MAX_CHARS:
             get_logger().log(f"[삭제-환청지어내기] 짧은 구간 과다 텍스트 제거({duration:.2f}초): '{text[:10]}...'")
             continue

        # 💡 [초단문 차단]
        if duration <= _MIN_DURATION: 
            get_logger().log(f"[삭제-초단문] {_MIN_DURATION}초 이하 차단({duration:.2f}초): '{text[:15]}...'")
            continue
            
        # 💡 [발음 속도(CPS) 차단]
        cps = clean_len / max(0.01, duration)
        if cps > _MAX_CPS:
            get_logger().log(f"[삭제-환각복붙] 발음 속도({_MAX_CPS}자 초과) 차단(CPS:{cps:.1f}): '{text[:15]}...'")
            continue
            
        result.append({**seg, "text": text})
    return result
    
def _dedup_close(segments: list[dict]) -> list[dict]:
    if not segments:
        return segments
    result = [segments[0]]
    for seg in segments[1:]:
        prev = result[-1]
        gap  = seg["start"] - prev["end"]
        t    = seg["text"].replace(" ", "").replace("\n", "")
        pt   = prev["text"].replace(" ", "").replace("\n", "")

        if t == pt:
            continue
            
        if gap < _DEDUP_WINDOW and t and pt and (t in pt or pt in t):
            get_logger().log(f"[삭제-근접포함] 이전 텍스트 겹침 삭제 (Gap: {gap:.2f}s): '{seg['text'][:15]}...'")
            continue
            
        if gap < 2.0 and len(t) >= 3 and len(pt) >= 3:
            match = difflib.SequenceMatcher(None, pt, t).find_longest_match(0, len(pt), 0, len(t))
            matched_len = match.size
            if matched_len >= 5 and (matched_len / len(t)) >= 0.8:
                get_logger().log(f"[삭제-유사중복] 꼬리물기 중복 삭제: '{seg['text'][:15]}...'")
                continue

        if gap < 0.15 and len(t) < 4:
            continue
            
        result.append(seg)
    return result

def _global_dedup(segments: list[dict]) -> list[dict]:
    result = []
    history = []
    for seg in segments:
        t = seg["text"].replace(" ", "").replace("\n", "")
        if len(t) < 5:
            result.append(seg)
            history.append(t)
            continue
        
        is_halluc = False
        for past_t in reversed(history[-40:]):
            if len(past_t) < 5: continue
            if t in past_t or past_t in t:
                is_halluc = True
                break
            match = difflib.SequenceMatcher(None, past_t, t).find_longest_match(0, len(past_t), 0, len(t))
            if match.size >= 8 and (match.size / len(t)) >= 0.7:
                is_halluc = True
                break
                
        if is_halluc:
            get_logger().log(f"[삭제-과거복붙] 앵무새 환각 삭제: '{seg['text'][:15]}...'")
            continue
            
        result.append(seg)
        history.append(t)
    return result

def _absorb_tiny(segments: list[dict], threshold: int) -> list[dict]:
    tiny = max(_MIN_CHARS, int(threshold * 0.3))
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(segments):
            seg = segments[i]
            clen = len(seg["text"].replace(" ", "").replace("\n", ""))
            if clen > tiny:
                i += 1
                continue

            if i > 0:
                prev = segments[i - 1]
                gap  = seg["start"] - prev["end"]
                if gap < _GAP_BREAK_SEC:
                    merged_text = (prev["text"] + " " + seg["text"]).strip()
                    get_logger().log(f"[흡수-앞] 파편 -> 앞 문장 병합: '{merged_text[:15]}...'")
                    segments[i - 1] = {**prev,
                                       "end":  seg["end"],
                                       "text": merged_text,
                                       "words": prev.get("words", []) + seg.get("words", [])}
                    segments.pop(i)
                    changed = True
                    continue

            if i < len(segments) - 1:
                nxt = segments[i + 1]
                gap = nxt["start"] - seg["end"]
                if gap < _GAP_BREAK_SEC:
                    merged_text = (seg["text"] + " " + nxt["text"]).strip()
                    get_logger().log(f"[흡수-뒤] 파편 -> 뒤 문장 병합: '{merged_text[:15]}...'")
                    segments[i + 1] = {**nxt,
                                       "start": seg["start"],
                                       "text":  merged_text,
                                       "words": seg.get("words", []) + nxt.get("words", [])}
                    segments.pop(i)
                    changed = True
                    continue

            i += 1
    return segments

def _pre_merge(segments: list[dict], threshold: int) -> list[dict]:
    if len(segments) < 2:
        return segments
    max_chars = threshold * _PRE_MERGE_MULT
    groups    = [[segments[0]]]

    for seg in segments[1:]:
        prev = groups[-1][-1]
        gap  = seg["start"] - prev["end"]
        g_len = sum(len(s["text"].replace(" ", "").replace("\n", "")) for s in groups[-1])
        c_len = len(seg["text"].replace(" ", "").replace("\n", ""))
        p_len = len(prev["text"].replace(" ", "").replace("\n", ""))

        if (gap < _GAP_BREAK_SEC
                and (c_len <= threshold * 0.5 or p_len <= threshold * 0.5 or g_len <= threshold)
                and g_len + c_len <= max_chars):
            groups[-1].append(seg)
        else:
            groups.append([seg])

    result = []
    for grp in groups:
        if len(grp) == 1:
            result.append(grp[0])
        else:
            all_words = []
            for s in grp:
                all_words.extend(s.get("words", []))
            merged_text = " ".join(s["text"].strip() for s in grp).strip()
            get_logger().log(f"[병합-문맥] {len(grp)}개 합체: '{merged_text[:15]}...'")
            result.append({
                "start":   grp[0]["start"],
                "end":     grp[-1]["end"],
                "text":    merged_text,
                "speaker": grp[0].get("speaker", "SPEAKER_00"),
                "words":   all_words,
            })
    return result

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
    )

    try:
        chunks = ollama_split_text(model, prompt) or []
        final_chunks = []
        for c in chunks:
            if not isinstance(c, str):
                continue
            c = _clean(c)
            if c and len(c.replace(" ", "").replace("\n", "")) >= 2:
                final_chunks.append(c)

        guarded = safe_llm_chunks(text, final_chunks)
        if guarded is None and final_chunks:
            ok, reason = validate_llm_chunks(text, final_chunks)
            get_logger().log(f"[LLM-보정차단] 원문 무결성 검사 실패({reason}): '{text[:15]}...'")
        return guarded if guarded else None

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
            ),
        )
    except Exception as e:
        get_logger().log(f"[OpenAI 연결/파싱 실패] {e}")
        return None
    final_chunks = []
    for c in chunks or []:
        if not isinstance(c, str):
            continue
        c = _clean(c)
        if c and len(c.replace(" ", "").replace("\n", "")) >= 2:
            final_chunks.append(c)
    guarded = safe_llm_chunks(text, final_chunks)
    if guarded is None and final_chunks:
        ok, reason = validate_llm_chunks(text, final_chunks)
        get_logger().log(f"[OpenAI-보정차단] 원문 무결성 검사 실패({reason}): '{text[:15]}...'")
    return guarded if guarded else None


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
    candidates = [list(chunks)]
    compact_original = re.sub(r"\s+", "", str(text or ""))
    compact_chunks = re.sub(r"\s+", "", "".join(str(chunk or "") for chunk in chunks))
    if compact_original and compact_original != compact_chunks:
        candidates.append([str(text or "").strip()])
    ranked, meta = rerank_subtitle_candidates(text, candidates, settings or {}, _profile_from_settings(settings))
    out_meta = dict(lora_meta or {})
    if meta:
        out_meta["_deep_rerank_policy"] = meta
    return ranked or chunks, out_meta


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
        get_logger().log(
            f"[LLM-게이트] LoRA/딥러닝 신뢰로 LLM 생략 "
            f"(score={decision.get('lora_score', 0)}, ratio={decision.get('compact_ratio', 0)}): "
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
) -> tuple[list[str] | None, dict]:
    out_meta = dict(lora_meta or {})
    if not chunks:
        _verified, decision = verify_llm_chunks_for_subtitle(
            text,
            [],
            settings or {},
            _profile_from_settings(settings),
        )
        out_meta = _append_accuracy_decision_for_settings(out_meta, decision, settings)
        out_meta["_llm_verifier_policy"] = decision
        rollback = rollback_decision(str(decision.get("reason") or "empty_chunks"), fallback=fallback)
        out_meta = _append_accuracy_decision_for_settings(out_meta, rollback, settings)
        out_meta["_llm_rollback_policy"] = rollback
        get_logger().log(f"[LLM-롤백] 출력 없음/파싱 실패({decision.get('reason')}), 안전 분할로 복구: '{str(text or '')[:15]}...'")
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

    verified, decision = verify_llm_chunks_for_subtitle(
        text,
        candidate_checked,
        settings or {},
        _profile_from_settings(settings),
    )
    out_meta = _append_accuracy_decision_for_settings(out_meta, decision, settings)
    out_meta["_llm_verifier_policy"] = decision
    if verified is None and chunks:
        rollback = rollback_decision(str(decision.get("reason") or "unknown"), fallback=fallback)
        out_meta = _append_accuracy_decision_for_settings(out_meta, rollback, settings)
        out_meta["_llm_rollback_policy"] = rollback
        get_logger().log(f"[LLM-롤백] 검증 실패({decision.get('reason')}), 안전 분할로 복구: '{str(text or '')[:15]}...'")
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


def _context_repair_output_variant(segments: list[dict], vad_segments: list[dict] | None, settings: dict | None) -> list[dict]:
    repaired, decision = repair_subtitle_context_consistency(segments, settings or {})
    if not decision.get("applied"):
        return []
    get_logger().log(
        "[자막문맥-자동복구] "
        f"반복 삭제 {decision.get('dropped_repeats', 0)}개, "
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
    return [dict(seg) for seg in result.segments]


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

    lattice_decision, lattice_meta = select_stt_lattice_text(seg, settings, _profile_from_settings(settings))
    if lattice_decision:
        lattice_meta = dict(lattice_meta or {})
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
        source = str(deep_decision.get("source", "") or "").strip().upper()
        label = str(deep_decision.get("label", "") or "").strip()
        get_logger().log(
            f"[STT앙상블-딥러닝판정] {label or '-'}({source or '-'}) 선택 "
            f"score={deep_decision.get('score', '-')} margin={deep_decision.get('margin', '-')}: "
            f"'{str(deep_decision.get('text', '') or '')[:18]}...'"
        )
        return deep_decision
    return None


def _apply_stt_candidate_decision(seg: dict, selected_decision: dict | None) -> tuple[dict, bool]:
    if not selected_decision:
        return dict(seg or {}), False
    selected_text = str(selected_decision.get("text", "") or "").strip()
    if not selected_text:
        return dict(seg or {}), False
    selected_source = str(selected_decision.get("source", "") or "").strip().upper()
    is_deep_selector = bool(selected_decision.get("selector")) and str(selected_decision.get("selector")) != "stt_lattice"
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
        "_deep_candidate_selector_policy": selected_decision.get("_deep_candidate_selector_policy") or seg.get("_deep_candidate_selector_policy"),
        "_llm_gate_policy": selected_decision.get("_llm_gate_policy") or seg.get("_llm_gate_policy"),
    }
    if selected_decision.get("words"):
        out["words"] = list(selected_decision.get("words") or [])
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
    fast_decision = _select_stt_candidate_fast({**seg, "stt_candidates": unique}, settings)
    if fast_decision:
        return fast_decision
    if not model or "사용 안함" in model:
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
        "아래 앞뒤 문맥을 참고해서 STT 후보 중 실제 발화로 가장 자연스럽고, 한국어 구어체로 가장 그럴듯한 후보 하나만 고르세요.\n"
        "없는 말을 새로 만들거나 두 후보를 섞지 마세요.\n"
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

    decision = " ".join(str(x) for x in (chunks or [])).upper()
    selected_index = 1 if "B" in decision and "A" not in decision else 0
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
        "_llm_gate_policy": stt_llm_gate,
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
        "_stt_lattice_policy",
        "_deep_candidate_selector_policy",
        "_llm_gate_policy",
        "_uncertainty_policy",
        "_uncertainty_bucket",
        "_uncertainty_risk_score",
        "_codex_native_fast_path_policy",
    )
    return {key: seg[key] for key in keys if key in seg}


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

    spk  = seg.get("speaker", "SPEAKER_00")
    text = seg.get("text", "").strip()
    if not text:
        return []

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
    if "사용 안함" in str(model or ""):
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
                )
        if should_call_llm:
            chunks, segment_lora = _verify_llm_chunks(
                text,
                chunks,
                segment_settings,
                segment_lora,
                fallback="word_timing_split",
                candidate_options=candidate_options,
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
            chunk_clean = re.sub(r"\s+", "", chunk)
            if not chunk_clean:
                continue
            t_start = None
            t_end   = None
            matched = 0
            chunk_words = []
            while w_idx < len(words) and matched < len(chunk_clean):
                w = words[w_idx]
                wc = re.sub(r"\s+|\.", "", w["word"])
                if t_start is None:
                    t_start = w["start"]
                t_end   = w["end"]
                matched += len(wc)
                chunk_words.append(w)
                w_idx   += 1
            if t_start is None:
                t_start = cur_start
            t_start = max(t_start, cur_start)
            if t_end is None or t_end <= t_start:
                t_end = t_start + 0.1
                
            # 💡 [최적화 완료] 여기서 _clean을 딱 한 번만 확실하게 호출합니다!
            final_text = _clean(chunk, corrections)
            
            # 텍스트가 유효할 때만 결과에 추가
            if final_text:
                _chunk_settings, chunk_lora = _segment_lora_runtime(
                    {**seg, "start": t_start, "end": t_end, "text": final_text, "words": chunk_words},
                    segment_settings,
                    rules,
                )
                result.append(_attach_lora_and_deep_timing({
                    **_stt_selection_metadata(seg),
                    "start":   t_start,
                    "end":     t_end,
                    "text":    final_text,
                    "speaker": spk,
                    "words":   chunk_words,
                }, chunk_lora or segment_lora, _chunk_settings))
            cur_start = t_end
            
        # 💡 [불필요한 2차 _clean 루프 완전 삭제] 이미 정리된 텍스트의 길이만 확인합니다.
        final_result = [r for r in result if len(r["text"].replace(" ", "").replace("\n", "")) >= 2]
        
        if len(final_result) > 1:
            get_logger().log(f"[분할-LLM] '{text[:15]}...' -> {len(final_result)}조각 분리")
        return final_result

    result = []
    buf    = []
    for i, w in enumerate(words):
        buf.append(w)
        is_last = (i == len(words) - 1)
        flush   = False
        if not is_last:
            nw   = words[i + 1]
            gap  = nw["start"] - w["end"]
            clen = sum(len(x["word"].replace(" ", "").replace("\n", "")) for x in buf)
            flush = (gap >= gap_break_sec
                     or (clen >= threshold and is_natural_break(w["word"], nw["word"], rules))
                     or clen >= int(threshold * _ENFORCE_RATIO))
        else:
            flush = True
        if flush:
            t = " ".join(x["word"] for x in buf)
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
            buf = []
            
    if len(result) > 1:
        get_logger().log(f"[분할-내장알고리즘] '{text[:15]}...' -> {len(result)}조각 안전 분리")
    return result


def _process_one_llm_only(args: tuple) -> list[dict]:
    if len(args) == 9:
        seg, rules, threshold, corrections, model, user_prompt, api_key, conservative, runtime_settings = args
    else:
        seg, rules, threshold, corrections, model, user_prompt, api_key, conservative = args
        runtime_settings = None
    spk = seg.get("speaker", "SPEAKER_00")
    text = str(seg.get("text", "") or "").strip()
    if not text:
        return []

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
            segment_settings, segment_lora = _segment_lora_runtime({**seg, "text": text}, runtime_settings, rules, threshold)

    cleaned_text = _clean(text, corrections)
    if not cleaned_text:
        return []
    truth_text, truth_meta = apply_recent_editor_truth_patterns(cleaned_text, segment_settings)
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
    if "사용 안함" in str(model or "") or (
        candidate_selected and len(cleaned_text.replace(" ", "").replace("\n", "")) <= threshold
    ):
        return [_attach_lora_and_deep_timing({**seg, "text": cleaned_text}, segment_lora, segment_settings)]
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
            )
    if should_call_llm:
        chunks, segment_lora = _verify_llm_chunks(
            cleaned_text,
            chunks,
            segment_settings,
            segment_lora,
            fallback="original_subtitle",
            candidate_options=candidate_options,
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
        chunk_clean = re.sub(r"\s+", "", str(chunk or ""))
        if not chunk_clean:
            continue
        t_start = None
        t_end = None
        matched = 0
        chunk_words = []
        while w_idx < len(words) and matched < len(chunk_clean):
            word = words[w_idx]
            wc = re.sub(r"\s+|\.", "", str(word.get("word", "") or ""))
            if t_start is None:
                t_start = float(word.get("start", cur_start) or cur_start)
            t_end = float(word.get("end", t_start or cur_start) or (t_start or cur_start))
            matched += len(wc)
            chunk_words.append(word)
            w_idx += 1
        if t_start is None:
            t_start = cur_start
        t_start = max(float(t_start), cur_start)
        if t_end is None or float(t_end) <= t_start:
            t_end = t_start + 0.1
        final_text = _clean(str(chunk), corrections)
        if final_text:
            _chunk_settings, chunk_lora = _segment_lora_runtime(
                {**seg, "start": t_start, "end": t_end, "text": final_text, "words": chunk_words},
                segment_settings,
                rules,
            )
            result.append(_attach_lora_and_deep_timing({
                **_stt_selection_metadata(seg),
                "start": t_start,
                "end": t_end,
                "text": final_text,
                "speaker": spk,
                "words": chunk_words,
            }, chunk_lora or segment_lora, _chunk_settings))
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
    threshold = _setting_int(loaded_settings, "split_length_threshold", 10)
    _EXAONE_WORKERS = _setting_int(loaded_settings, "llm_threads", 6, fallback_key="llm_workers")
    _LOCAL_OLLAMA_WORKER_CAP = _setting_int(loaded_settings, "local_ollama_llm_max_workers", 2)
    _GAP_BREAK_SEC = _setting_float(loaded_settings, "sub_gap_break_sec", 1.5)
    _MIN_DURATION = _setting_float(loaded_settings, "sub_min_duration", 0.2)
    _MAX_DURATION = _setting_float(loaded_settings, "sub_max_duration", 6.0)
    _MAX_CPS = _setting_int(loaded_settings, "sub_max_cps", 12)
    _DEDUP_WINDOW = _setting_float(loaded_settings, "sub_dedup_window", 0.5)

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
    corrections: dict = {}
    if raw_corr:
        corrections = dict(
            sorted(
                {k: v for k, v in raw_corr.items() if k}.items(),
                key=lambda x: len(x[0]),
                reverse=True,
            )
        )
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
    threshold = max(1, _setting_int({**dict(settings or {}), **row_settings}, "split_length_threshold", 10))
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
        "emit_llm_progress": _emit_llm_progress,
        "logger": get_logger(),
    }


def optimize_segments(
    segments: list[dict],
    vad_segments: list[dict] | None = None,
    llm_progress_callback=None,
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

            except Exception as e:
                get_logger().log(f"LLM 처리 오류: {e}")
                optimized = segments

    optimized = adjust_timing(optimized)
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

    optimized = _smooth_deep_sequence(optimized, loaded_settings)
    optimized = apply_final_gap_settings(optimized, loaded_settings, force=False)
    optimized = align_stt_candidates_to_subtitle_segments(optimized)
    optimized = _self_review_subtitle_quality(optimized, vad_segments or [], loaded_settings)
    optimized = _annotate_context_consistency(optimized, loaded_settings)
    optimized = _apply_output_variant_selector(optimized, original_segments, vad_segments or [], loaded_settings, stage="llm")
    optimized = _annotate_auto_review(optimized, loaded_settings)
    optimized = _annotate_stage_confidence(optimized, loaded_settings)
    optimized = _annotate_completion_report(optimized, loaded_settings)
    _log_accuracy_metrics(optimized, loaded_settings)
    _record_deep_policy_learning(optimized, loaded_settings)
    _emit_llm_progress(llm_progress_callback, active=False)
    get_logger().log(f"━━━ 자막 최적화 완료: {len(optimized)}개 ━━━\n")
    return optimized

def save_srt(segments: list[dict], srt_path: str, apply_offset: bool = True):
    from core.engine.srt_writer import save_srt as _save_srt
    return _save_srt(segments, srt_path, apply_offset=apply_offset, adjust_timing_func=adjust_timing)

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
            ),
        )
    except Exception:
        return [text]

    final_chunks = []
    for c in chunks or []:
        if not isinstance(c, str):
            continue
        c = _clean(c)
        if c and len(c.replace(" ", "").replace("\n", "")) >= 2:
            final_chunks.append(c)
    guarded = safe_llm_chunks(text, final_chunks)
    if guarded is None and final_chunks:
        ok, reason = validate_llm_chunks(text, final_chunks)
        get_logger().log(f"[Gemini-보정차단] 원문 무결성 검사 실패({reason}): '{text[:15]}...'")
    return guarded if guarded else [text]
