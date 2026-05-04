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
from core.llm.openai_provider import is_openai_model, split_text as openai_split_text
from core.engine.llm_correction_guard import safe_llm_chunks, validate_llm_chunks
from core.subtitle_quality.timestamp_regrouper import regroup_by_word_timestamps
from core.personalization.runtime_lora_context import runtime_lora_enabled
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
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.runtime.logger import get_logger
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
) -> list[str] | None:
    if "사용 안함" in model:
        return None
    if not _local_ollama_ready(model, "자막 LLM"):
        return None
    model = _resolve_runtime_llm_model(model, logger=get_logger(), context="자막 LLM")

    prompt = _build_llm_prompt(text, threshold, rules, user_prompt, conservative=conservative, settings=settings)

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
) -> list[str] | None:
    if not api_key:
        get_logger().log("❌ API 키가 없습니다. 환경설정에서 OpenAI API Key를 입력해주세요.")
        return None
    try:
        chunks = openai_split_text(api_key, model_name, _build_llm_prompt(text, threshold, rules, user_prompt, conservative=conservative, settings=settings))
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


def _select_stt_candidate_text(seg: dict, model: str, user_prompt: str, api_key: str) -> dict | None:
    settings = _get_user_settings()
    if not settings.get("stt_ensemble_llm_judge_enabled", True):
        return None
    if not model or "사용 안함" in model:
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
        "stt_selected_source",
        "score",
        "stt_score",
        "score_color",
        "stt_score_color",
        "stt_score_label",
        "stt_score_flags",
        "stt_score_components",
    )
    return {key: seg[key] for key in keys if key in seg}


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

    if seg.get("stt_candidates") and duration >= 0.35:
        selected_decision = _select_stt_candidate_text(seg, model, user_prompt, api_key)
        if selected_decision:
            selected_text = str(selected_decision.get("text", "") or "").strip()
            selected_source = str(selected_decision.get("source", "") or "").strip().upper()
            seg = {
                **seg,
                "text": selected_text,
                "stt_ensemble_llm_selected_source": selected_source,
                "stt_ensemble_llm_selected_label": str(selected_decision.get("label", "") or ""),
            }
            text = selected_text

    # 💡 [환각 방지] 너무 짧은 자막은 LLM 교정을 생략합니다.
    if duration < _LLM_SKIP_DUR or len(text.replace(" ", "")) <= (threshold - 5):
        return [{**seg, "text": _clean(text, corrections)}]

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
        return [{**seg, "text": _clean(text, corrections)}]
    # [수정] LLM 호출 분기 부분
    if "사용 안함" in str(model or ""):
        chunks = None
    elif "Gemini" in model:
        chunks = ask_gemini_to_split(text, threshold, rules, model, user_prompt, api_key, conservative=conservative, settings=runtime_settings)
    elif is_openai_model(model):
        chunks = ask_openai_to_split(text, threshold, rules, model, user_prompt, api_key, conservative=conservative, settings=runtime_settings)
    else:
        chunks = ask_exaone_to_split(text, threshold, rules, model, user_prompt, conservative=conservative, settings=runtime_settings)


    if chunks:
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
                result.append({
                    **_stt_selection_metadata(seg),
                    "start":   t_start,
                    "end":     t_end,
                    "text":    final_text,
                    "speaker": spk,
                    "words":   chunk_words,
                })
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
            flush = (gap >= _GAP_BREAK_SEC
                     or (clen >= threshold and is_natural_break(w["word"], nw["word"], rules))
                     or clen >= int(threshold * _ENFORCE_RATIO))
        else:
            flush = True
        if flush:
            t = " ".join(x["word"] for x in buf)
            ct = _clean(t, corrections)
            if ct and len(ct.replace(" ", "").replace("\n", "")) >= 2:
                result.append({
                    **_stt_selection_metadata(seg),
                    "start":   buf[0]["start"],
                    "end":     buf[-1]["end"],
                    "text":    ct,
                    "speaker": buf[0].get("speaker", spk),
                    "words":   buf,
                })
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
    if seg.get("stt_candidates") and duration >= 0.35:
        selected_decision = _select_stt_candidate_text(seg, model, user_prompt, api_key)
        if selected_decision:
            text = str(selected_decision.get("text", "") or "").strip()
            seg = {
                **seg,
                "text": text,
                "stt_ensemble_llm_selected_source": str(selected_decision.get("source", "") or "").strip().upper(),
                "stt_ensemble_llm_selected_label": str(selected_decision.get("label", "") or ""),
            }

    cleaned_text = _clean(text, corrections)
    if not cleaned_text:
        return []
    if "사용 안함" in str(model or ""):
        return [{**seg, "text": cleaned_text}]
    if duration < _LLM_SKIP_DUR or len(cleaned_text.replace(" ", "")) <= (threshold - 5):
        return [{**seg, "text": cleaned_text}]

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

    if "Gemini" in model:
        chunks = ask_gemini_to_split(cleaned_text, threshold, rules, model, user_prompt, api_key, conservative=conservative, settings=runtime_settings)
    elif is_openai_model(model):
        chunks = ask_openai_to_split(cleaned_text, threshold, rules, model, user_prompt, api_key, conservative=conservative, settings=runtime_settings)
    else:
        chunks = ask_exaone_to_split(cleaned_text, threshold, rules, model, user_prompt, conservative=conservative, settings=runtime_settings)

    if not chunks:
        return [{**seg, "text": cleaned_text}]

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
            result.append({
                **_stt_selection_metadata(seg),
                "start": t_start,
                "end": t_end,
                "text": final_text,
                "speaker": spk,
                "words": chunk_words,
            })
        cur_start = float(t_end)

    if len(result) > 1:
        get_logger().log(f"[분할-LLM] '{cleaned_text[:15]}...' -> {len(result)}조각 분리")
    return result or [{**seg, "text": cleaned_text}]


def _enforce_len(segments: list[dict], threshold: int, rules: dict) -> list[dict]:
    limit  = int(threshold * _ENFORCE_RATIO)
    result = []
    for seg in segments:
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
                flush = ((clen >= threshold and is_natural_break(w["word"], nw["word"], rules))
                         or clen >= limit)
            if flush:
                t = " ".join(x["word"] for x in buf).strip()
                ct = _clean(t)
                if ct:
                    result.append({
                        **_stt_selection_metadata(seg),
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
    threshold = _setting_int(s, "split_length_threshold", 10)
    _EXAONE_WORKERS = _setting_int(s, "llm_threads", 6, fallback_key="llm_workers")
    _LOCAL_OLLAMA_WORKER_CAP = _setting_int(s, "local_ollama_llm_max_workers", 2)
    _GAP_BREAK_SEC = _setting_float(s, "sub_gap_break_sec", 1.5)
    _MIN_DURATION = _setting_float(s, "sub_min_duration", 0.2)
    _MAX_DURATION = _setting_float(s, "sub_max_duration", 6.0)
    _MAX_CPS = _setting_int(s, "sub_max_cps", 12)
    _DEDUP_WINDOW = _setting_float(s, "sub_dedup_window", 0.5)

    if "user_prompt" in s:
        user_prompt = s["user_prompt"]
    elif "llm_prompt" in s:
        user_prompt = s["llm_prompt"]

    if "Gemini" in model:
        api_key = get_api_key("google") or s.get("google_api_key", "")
    elif is_openai_model(model):
        api_key = get_api_key("openai") or s.get("openai_api_key", "")
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
        (dict(seg), rules, threshold, corrections, "사용 안함 (STT 후보 규칙 전용)", user_prompt, "", False)
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
    optimized = apply_final_gap_settings(optimized, force=True)
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

    conservative = _quality_conservative_enabled(loaded_settings)
    if conservative:
        get_logger().log("[LLM-보수Profile] 자막 품질 검사/자동교정 보호 규칙을 적용합니다.")
    if runtime_lora_enabled(loaded_settings):
        get_logger().log("[텍스트 LoRA] 자동 교정 허용: 교정 memory/오답 memory/사용자 단어/줄바꿈 규칙을 최종 LLM에 적용합니다.")

    args = [(seg, rules, threshold, corrections, model, user_prompt, api_key, conservative, loaded_settings) for seg in segments]
    optimized: list[dict] = []

    if "사용 안함" in model:
        get_logger().log("⏩ LLM 미사용: 최종 자막은 원본 STT 텍스트를 유지하고 간격 패스만 적용합니다...")
        for idx, a in enumerate(args):
            try:
                optimized.extend(_process_one_llm_only(a))
            except Exception as e:
                get_logger().log(f"LLM 처리 오류: {e}")
                optimized.append(segments[idx])

    else:
        max_workers, worker_mode = _effective_llm_workers(model, _EXAONE_WORKERS, loaded_settings, len(args))
        if worker_mode == "api":
            get_logger().log(f"🤖 {short_m} API 안전 모드: {max_workers}개 워커 순차 처리 중...")
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

        if max_workers == 1:
            for idx, a in enumerate(args):
                try:
                    _emit_llm_progress(llm_progress_callback, active=True, idx=idx, total=len(args), seg=segments[idx])
                    optimized.extend(_process_one_llm_only(a))
                except Exception as e:
                    get_logger().log(f"LLM 처리 오류: {e}")
                    optimized.append(segments[idx])
        else:
            try:
                def _process_with_progress(index: int, arg):
                    _emit_llm_progress(llm_progress_callback, active=True, idx=index, total=len(args), seg=segments[index])
                    return _process_one_llm_only(arg)

                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="llm") as ex:
                    futures = {ex.submit(_process_with_progress, i, a): i for i, a in enumerate(args)}
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

    optimized = apply_final_gap_settings(optimized, loaded_settings, force=False)
    optimized = align_stt_candidates_to_subtitle_segments(optimized)
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
) -> list[str] | None:
    if not api_key:
        get_logger().log("❌ API 키가 없습니다. 환경설정에서 Google API Key를 입력해주세요.")
        return None

    try:
        chunks = gemini_split_text(api_key, model_name, _build_llm_prompt(text, threshold, rules, user_prompt, conservative=conservative, settings=settings))
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
