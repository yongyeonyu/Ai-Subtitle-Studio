# Version: 03.02.03
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
import os
import json
import re
import difflib  

from core.llm.secure_keys import get_api_key
from core.llm.gemini_provider import split_text as gemini_split_text
from core.llm.ollama_provider import split_text as ollama_split_text, warmup_model as warmup_ollama_model
from core.llm.openai_provider import is_openai_model, split_text as openai_split_text
from core.engine.llm_correction_guard import safe_llm_chunks, validate_llm_chunks
from core.subtitle_quality.llm_guarded_corrector import build_conservative_prompt
from core.subtitle_quality.timestamp_regrouper import regroup_by_word_timestamps

from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from logger import get_logger
from core.utils import load_subtitle_rules

# 💡 [설정 데이터 로드]
def _get_user_settings():
    import json
    path = os.path.join(config.DATASET_DIR, "user_settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f: 
            return json.load(f)
    except: 
        return {}

_S = _get_user_settings() # 설정 데이터 스냅샷 로드

def _setting_int(settings: dict, key: str, default: int, fallback_key: str | None = None) -> int:
    value = settings.get(key, None)
    if value in (None, "") and fallback_key:
        value = settings.get(fallback_key, None)
    if value in (None, ""):
        value = default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _setting_float(settings: dict, key: str, default: float) -> float:
    value = settings.get(key, default)
    if value in (None, ""):
        value = default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ━━━ 📋 [UI 설정 연동 변수] 숫자를 직접 적지 않고 설정값에서 실시간으로 가져옵니다 ━━━
_EXAONE_WORKERS  = _setting_int(_S, "llm_threads", 6, fallback_key="llm_workers")  # (AI -> 에디터 LLM 처리 스레드)
_GAP_BREAK_SEC   = _setting_float(_S, "sub_gap_break_sec", 1.5) # (간격 -> 문장 분리 간격)
_MIN_DURATION    = _setting_float(_S, "sub_min_duration", 0.3)  # (간격 -> 최소 자막 유지 시간)
_MAX_DURATION    = _setting_float(_S, "sub_max_duration", 6.0)  # (간격 -> 최대 자막 유지 시간)
_MAX_CPS         = _setting_int(_S, "sub_max_cps", 12)          # (간격 -> 최대 발음 속도 CPS)
_DEDUP_WINDOW    = _setting_float(_S, "sub_dedup_window", 0.5)  # (간격 -> 중복 자막 방어 범위)

# ━━━ 🛠️ [시스템 고정 상수] ━━━
_MIN_CHARS       = 5     
_PRE_MERGE_MULT  = 3.0   
_ENFORCE_RATIO   = 1.5   
_HALLUC_MIN_DUR  = 0.8   
_HALLUC_MAX_CHARS = 10   
_LLM_SKIP_DUR    = 1.0

# 💡 [신규 이식] media_processor에서 이사 온 환각 방지 리스트
_HALLUC_PHRASES = [
    "한국어 대화", "자막 생성",
    "번역 중", "처리 중", "대화 내용", "Korean conversation",
    "subtitle", "transcription", "Thank you for watching"
]

_TS_BRACKET = re.compile(r'\[\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*\]\s*')
_TS_NO_BRACKET = re.compile(r'^\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s+') 
_JUNK_PATTERN = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')        

DEFAULT_SYSTEM_PROMPT = getattr(config, "DEFAULT_LLM_PROMPT", "")

_HARDCODED_LLM_RULES = """
[절대 규칙 - 엄격준수]
0. [우선순위] 사용자 추가 지시문이 있어도 아래 절대 규칙을 완화하거나 덮어쓸 수 없습니다.
1. [무결성] 단어 및 문장의 추가, 삭제, 의미 변경, 의역, 요약을 엄격히 금지합니다.
2. [원문 우선] 불확실한 단어는 추측하지 말고 원문 그대로 유지하세요.
3. [허용 작업] 오탈자, 띄어쓰기, 문장부호만 최소한으로 보정하세요.
4. [구어체 유지] 말투, 반복, 감탄, 어미, 구어체 표현을 문어체로 바꾸지 마세요.
5. [타임코드 금지] 시간값, 시작/종료 시간, 인덱스, 타임코드를 만들거나 출력하지 마세요.
6. [마침표 제거] 마침표(.)는 모두 제거하세요.
7. [물결 추가] 원문에 길게 끄는 감탄이 명확할 때만 물결(~) 기호를 유지/보정하세요.
8. [쉼표 추가] 의미가 바뀌지 않는 범위에서만 자연스럽게 쉼표(,)를 추가하세요.
9. [언어 제한] 한국어와 영어 이외의 언어(중국어, 일본어 등)는 절대 사용하지 마세요.
10. [창작 금지] 절대 부가 설명이나 인사말을 넣지 말고, 오직 분리된 결과 문자열만 출력하세요.

[출력 형식]
인사말이나 부연 설명 없이, 반드시 아래의 JSON 형식으로만 응답해야 합니다:
{
  "result": ["첫 번째 문장", "두 번째 문장", "세 번째 문장"]
}

원본 텍스트: {text}
"""

def get_local_dataset_corrections() -> dict:
    settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
    try:
        # 💡 [치명적 버그 수정] path -> settings_path 로 변수명 오타 교정!
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_selected_llm() -> str:
    settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
    try:
        # 💡 [치명적 버그 수정] path -> settings_path 로 변수명 오타 교정!
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f).get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
    except Exception:
        return getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b")

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

def _quality_conservative_enabled(settings: dict | None) -> bool:
    settings = settings or {}
    return bool(
        settings.get("subtitle_quality_enabled")
        or settings.get("subtitle_quality_auto_check_after_generate")
        or settings.get("subtitle_quality_auto_correct_enabled")
    )


def ask_exaone_to_split(text: str, threshold: int, rules: dict, model: str, user_prompt: str, conservative: bool = False) -> list[str] | None:
    if "사용 안함" in model:
        return None

    end_words = ", ".join(rules.get("end_words", []))
    start_words = ", ".join(rules.get("start_words", []))

    if user_prompt.strip():
        combined_prompt = f"{DEFAULT_SYSTEM_PROMPT.strip()}\n\n[사용자 추가 지시문]\n{user_prompt.strip()}\n\n{_HARDCODED_LLM_RULES.strip()}"
    else:
        combined_prompt = f"{DEFAULT_SYSTEM_PROMPT.strip()}\n\n{_HARDCODED_LLM_RULES.strip()}"

    if conservative:
        combined_prompt = build_conservative_prompt(combined_prompt)

    prompt = combined_prompt.replace("{threshold}", str(threshold)).replace("{end_words}", end_words).replace("{start_words}", start_words).replace("{text}", text)

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
        get_logger().log(f"[LLM 연결/파싱 실패] {e}")
        return None

def _build_llm_prompt(text: str, threshold: int, rules: dict, user_prompt: str, conservative: bool = False) -> str:
    end_words = ", ".join(rules.get("end_words", []))
    start_words = ", ".join(rules.get("start_words", []))
    if user_prompt.strip():
        combined_prompt = f"{DEFAULT_SYSTEM_PROMPT.strip()}\n\n[사용자 추가 지시문]\n{user_prompt.strip()}\n\n{_HARDCODED_LLM_RULES.strip()}"
    else:
        combined_prompt = f"{DEFAULT_SYSTEM_PROMPT.strip()}\n\n{_HARDCODED_LLM_RULES.strip()}"
    if conservative:
        combined_prompt = build_conservative_prompt(combined_prompt)
    return (
        combined_prompt
        .replace("{threshold}", str(threshold))
        .replace("{end_words}", end_words)
        .replace("{start_words}", start_words)
        .replace("{text}", text)
    )


def ask_openai_to_split(text: str, threshold: int, rules: dict, model_name: str, user_prompt: str, api_key: str, conservative: bool = False) -> list[str] | None:
    if not api_key:
        get_logger().log("❌ API 키가 없습니다. 환경설정에서 OpenAI API Key를 입력해주세요.")
        return None
    try:
        chunks = openai_split_text(api_key, model_name, _build_llm_prompt(text, threshold, rules, user_prompt, conservative=conservative))
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


def _process_one(args: tuple) -> list[dict]:
    if len(args) == 8:
        seg, rules, threshold, corrections, model, user_prompt, api_key, conservative = args
    elif len(args) == 7:
        seg, rules, threshold, corrections, model, user_prompt, api_key = args
        conservative = False
    else:
        seg, rules, threshold, corrections, model, user_prompt = args
        api_key = ""
        conservative = False

    spk  = seg.get("speaker", "SPEAKER_00")
    text = seg.get("text", "").strip()
    if not text:
        return []

    # 💡 [추가] duration 정의
    duration = seg.get("end", 0) - seg.get("start", 0)

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
    if "Gemini" in model:
        chunks = ask_gemini_to_split(text, threshold, rules, model, user_prompt, api_key, conservative=conservative)
    elif is_openai_model(model):
        chunks = ask_openai_to_split(text, threshold, rules, model, user_prompt, api_key, conservative=conservative)
    else:
        chunks = ask_exaone_to_split(text, threshold, rules, model, user_prompt, conservative=conservative)


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
            while w_idx < len(words) and matched < len(chunk_clean):
                w = words[w_idx]
                wc = re.sub(r"\s+|\.", "", w["word"])
                if t_start is None:
                    t_start = w["start"]
                t_end   = w["end"]
                matched += len(wc)
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
                    "start":   t_start,
                    "end":     t_end,
                    "text":    final_text,
                    "speaker": spk,
                    "words":   [],
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
                    result.append({"start": buf[0]["start"], "end": buf[-1]["end"],
                                   "text": ct, "speaker": spk, "words": buf})
                buf = []
    return result

def adjust_timing(segments: list[dict]) -> list[dict]:
    if not segments:
        return segments
    adj = sorted([dict(s) for s in segments], key=lambda x: x["start"])
    for i in range(1, len(adj)):
        prev = adj[i - 1]
        cur = adj[i]
        
        if prev["end"] > cur["start"]:
            prev["end"] = max(prev["start"] + 0.1, cur["start"] - 0.02)
            
        if cur["end"] <= cur["start"]:
            cur["end"] = cur["start"] + 0.3
    return adj

def optimize_segments(segments: list[dict]) -> list[dict]:
    if not segments:
        return segments

    global _EXAONE_WORKERS, _GAP_BREAK_SEC, _MIN_DURATION, _MAX_DURATION, _MAX_CPS, _DEDUP_WINDOW

    model = get_selected_llm()
    short_m = model.split(":")[0].upper()
    rules = load_subtitle_rules()
    threshold = 10
    user_prompt = ""
    api_key = ""
    loaded_settings = {}

    settings_path = os.path.join(config.DATASET_DIR, "user_settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                s = json.load(f)
                loaded_settings = dict(s)
                threshold = _setting_int(s, "split_length_threshold", 10)
                _EXAONE_WORKERS = _setting_int(s, "llm_threads", 6, fallback_key="llm_workers")
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
        except Exception:
            pass

    get_logger().log(f"\n━━━ 자막 최적화 시작 ({len(segments)}개 세그먼트) ━━━")
    get_logger().log(
        f"설정 적용: 분할({threshold}자), 최대길이({_MAX_DURATION}초), "
        f"CPS({_MAX_CPS}), 차단({_MIN_DURATION}초), 앵무새방어({_DEDUP_WINDOW}초)"
    )

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

    segments = _sanitize(segments, corrections)
    segments = _dedup_close(segments)
    segments = _absorb_tiny(segments, threshold)
    segments = _global_dedup(segments)
    segments = _pre_merge(segments, threshold)

    conservative = _quality_conservative_enabled(loaded_settings)
    if conservative:
        get_logger().log("[LLM-보수Profile] 자막 품질 검사/자동교정 보호 규칙을 적용합니다.")

    args = [(seg, rules, threshold, corrections, model, user_prompt, api_key, conservative) for seg in segments]
    optimized: list[dict] = []

    if "사용 안함" in model:
        get_logger().log("⏩ LLM 미사용: 스레드풀 없이 파이썬 내장 알고리즘만 즉시 적용합니다...")
        for idx, a in enumerate(args):
            try:
                optimized.extend(_process_one(a))
            except Exception as e:
                get_logger().log(f"LLM 처리 오류: {e}")
                optimized.append(segments[idx])

    else:
        if "Gemini" in model or is_openai_model(model):
            _EXAONE_WORKERS = 1
            get_logger().log(f"🤖 {short_m} API 안전 모드: {_EXAONE_WORKERS}개 워커 순차 처리 중...")
        else:
            warmup_ollama_model(model, logger=get_logger())
            get_logger().log(f"{short_m} {min(_EXAONE_WORKERS, len(args))}개 워커 병렬 처리 ({len(segments)}개)...")

        max_workers = max(1, min(_EXAONE_WORKERS, len(args)))

        if max_workers == 1:
            for idx, a in enumerate(args):
                try:
                    optimized.extend(_process_one(a))
                except Exception as e:
                    get_logger().log(f"LLM 처리 오류: {e}")
                    optimized.append(segments[idx])
        else:
            try:
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="llm") as ex:
                    futures = {ex.submit(_process_one, a): i for i, a in enumerate(args)}
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

    optimized = _absorb_tiny(optimized, threshold)
    optimized = _enforce_len(optimized, threshold, rules)
    optimized = regroup_by_word_timestamps(
        optimized,
        max_chars=threshold,
        max_duration=_MAX_DURATION,
        max_cps=_MAX_CPS,
        min_duration=_MIN_DURATION,
        gap_break_sec=_GAP_BREAK_SEC,
        rules=rules,
    )
    optimized = _absorb_tiny(optimized, threshold)
    optimized = adjust_timing(optimized)
    optimized = _global_dedup(optimized)

    get_logger().log(f"━━━ 자막 최적화 완료: {len(optimized)}개 ━━━\n")
    return optimized

def save_srt(segments: list[dict], srt_path: str, apply_offset: bool = True):
    from core.engine.srt_writer import save_srt as _save_srt
    return _save_srt(segments, srt_path, apply_offset=apply_offset, adjust_timing_func=adjust_timing)

def ask_gemini_to_split(text: str, threshold: int, rules: dict, model_name: str, user_prompt: str, api_key: str, conservative: bool = False) -> list[str] | None:
    if not api_key:
        get_logger().log("❌ API 키가 없습니다. 환경설정에서 Google API Key를 입력해주세요.")
        return None

    try:
        chunks = gemini_split_text(api_key, model_name, _build_llm_prompt(text, threshold, rules, user_prompt, conservative=conservative))
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
