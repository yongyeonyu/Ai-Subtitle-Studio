# Version: 02.03.00
# Phase: PHASE1-B
import os
import json
import re
from typing import Dict, Tuple, List, Any

from core.runtime.logger import get_logger
from core.runtime.config import (
    DATASET_DIR,
    CORRECTIONS_FILE,
    RULES_FILE,
    DEFAULT_SPLIT_RULES,
    DEFAULT_SPLIT_PUNCTUATION,
    DEFAULT_MAX_CHARS,
)

# ─────────────────────────────────────────────────────────────
# 자막 분리 규칙(End/Start words) 관리
# RULES_FILE(subtitle_rule.json)을 단일 소스로 사용합니다.
# ─────────────────────────────────────────────────────────────

DEFAULT_RULES = {
    "end_words": [
        "고요", "거든요", "는데요", "다", "요", "고", "서", "네", "지", "데", "만", "까", "나", "야지"
    ],
    "start_words": [
        "어우", "아", "오", "와", "헐", "헉", "근데", "그리고", "그래서", "하지만", "그러면", "이런", "진짜", "너무"
    ]
}


def _unique_sorted_words(items: list[str] | tuple[str, ...] | None) -> list[str]:
    out = []
    seen = set()
    for item in items or []:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return sorted(out)


def _normalize_rule_payload(file_rules: dict[str, Any] | None) -> Dict[str, Any]:
    file_rules = dict(file_rules or {})
    return {
        "end_words": _unique_sorted_words(
            list(DEFAULT_RULES["end_words"]) + list(file_rules.get("end_words") or [])
        ),
        "start_words": _unique_sorted_words(
            list(DEFAULT_RULES["start_words"]) + list(file_rules.get("start_words") or [])
        ),
        # split_* 계열은 subtitle_rule.json이 있으면 우선 사용하고, 없으면 config fallback 사용
        "split_rules": _unique_sorted_words(
            file_rules.get("split_rules") or DEFAULT_SPLIT_RULES
        ),
        "split_punctuation": _unique_sorted_words(
            file_rules.get("split_punctuation") or DEFAULT_SPLIT_PUNCTUATION
        ),
        "max_chars": int(file_rules.get("max_chars") or DEFAULT_MAX_CHARS),
    }


def _ensure_dataset_dir():
    """dataset 폴더 존재 보장 (안전장치)"""
    os.makedirs(DATASET_DIR, exist_ok=True)

def load_subtitle_rules() -> Dict[str, Any]:
    """
    subtitle_rule.json을 단일 소스로 읽고, 비어 있는 값은 config fallback으로 채웁니다.
    반환값에는 다음이 모두 포함됩니다.
    - end_words
    - start_words
    - split_rules
    - split_punctuation
    - max_chars
    """
    _ensure_dataset_dir()

    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                file_rules = json.load(f)
            if isinstance(file_rules, dict):
                return _normalize_rule_payload(file_rules)
        except Exception as e:
            get_logger().log(f"⚠️ 규칙 파일 로드 중 오류: {e}")

    return _normalize_rule_payload({})

def _write_rules_file(rules: Dict[str, Any]) -> None:
    """RULES_FILE에 규칙 payload를 안전하게 저장"""
    _ensure_dataset_dir()

    normalized = _normalize_rule_payload(rules)
    payload = {
        "end_words": normalized.get("end_words", []),
        "start_words": normalized.get("start_words", []),
        "split_rules": normalized.get("split_rules", []),
        "split_punctuation": normalized.get("split_punctuation", []),
        "max_chars": normalized.get("max_chars", DEFAULT_MAX_CHARS),
    }

    try:
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        get_logger().log(f"❌ 규칙 저장 실패: {e}")

def add_split_rule(word: str) -> None:
    """사용자가 엔터를 칠 때 새로운 종료 어미(end_words)를 누적 저장"""
    rules = load_subtitle_rules()

    clean_word = word.replace(".", "").strip()
    if not clean_word:
        return

    if clean_word not in rules["end_words"]:
        rules["end_words"].append(clean_word)
        rules["end_words"] = sorted(set(rules["end_words"]))
        _write_rules_file(rules)
        get_logger().log(f"📝 자막 분할 규칙 누적 완료: {clean_word}")

def remove_split_rule(word: str) -> None:
    """사용자가 자막을 합칠 때 해당 토큰을 end_words/start_words에서 제거"""
    rules = load_subtitle_rules()

    clean_word = word.replace(".", "").strip()
    if not clean_word:
        return

    changed = False
    for key in ("end_words", "start_words"):
        if clean_word in rules.get(key, []):
            rules[key] = sorted({w for w in rules[key] if w != clean_word})
            changed = True

    if changed:
        _write_rules_file(rules)
        get_logger().log(f"📝 자막 분할 규칙 제거: {clean_word}")

def reset_split_rules() -> None:
    """규칙을 기본값 + split fallback 값으로 초기화"""
    _ensure_dataset_dir()
    _write_rules_file({})
    get_logger().log("♻️ 자막 분할 규칙이 기본값으로 초기화되었습니다.")

# ─────────────────────────────────────────────────────────────
# 시간/표기 유틸
# ─────────────────────────────────────────────────────────────

def seconds_to_srt_time(seconds: float) -> str:
    """초 → SRT 표준 포맷 HH:MM:SS,mmm (반올림 오버플로우 방지 포함)"""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))

    if ms >= 1000:
        ms -= 1000
        s += 1
        if s >= 60:
            s -= 60
            m += 1
        if m >= 60:
            m -= 60
            h += 1

    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def netflix_style(text: str) -> str:
    """마침표/중복 마침표 정리 등 간단 정규화"""
    text = text.strip()
    text = re.sub(r"[.。]+\s*$", "", text)
    text = re.sub(r"[.。]\s+", " ", text)
    return text.strip()

# ─────────────────────────────────────────────────────────────
# 교정사전 관리 (dataset_correction.json)
# ─────────────────────────────────────────────────────────────

def load_corrections() -> Dict[str, str]:
    """교정사전 로드"""
    try:
        if os.path.exists(CORRECTIONS_FILE):
            with open(CORRECTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception as e:
        get_logger().log(f"⚠️ 교정사전 로드 실패: {e}")
    return {}

def save_corrections(corrections: Dict[str, str]) -> None:
    """
    교정사전 저장(merge)
    - 기존 내용 유지 + 신규 업데이트
    """
    _ensure_dataset_dir()

    try:
        existing = load_corrections()
        existing.update(corrections or {})
        with open(CORRECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as e:
        get_logger().log(f"❌ 교정사전 저장 실패: {e}")

def apply_corrections(text: str, corrections: Dict[str, str]) -> str:
    """단순 치환 기반 교정 적용"""
    for wrong, right in (corrections or {}).items():
        text = text.replace(wrong, right)
    return text

# ─────────────────────────────────────────────────────────────
# 분할 로직용 config 룰 로드 (subtitle_rule.json의 split_rules 등)
# ─────────────────────────────────────────────────────────────

def load_rules() -> Tuple[List[str], List[str], int]:
    """
    subtitle_rule.json에서 분할 관련 설정을 읽어 반환합니다.
    실질 소스는 load_subtitle_rules()를 재사용하고, config 상수는 fallback으로만 사용합니다.
    """
    rules = load_subtitle_rules()
    return (
        list(rules.get("split_rules") or DEFAULT_SPLIT_RULES),
        list(rules.get("split_punctuation") or DEFAULT_SPLIT_PUNCTUATION),
        int(rules.get("max_chars") or DEFAULT_MAX_CHARS),
    )

# ─────────────────────────────────────────────────────────────
# 환각/반복 제거
# ─────────────────────────────────────────────────────────────

def remove_hallucinations(segments: List[Dict[str, Any]], repeat_threshold: int = 3) -> List[Dict[str, Any]]:
    """
    - 뉴스/구독 유도 등 환각 문구 제거
    - 텍스트가 비어있거나 유효 문자가 전혀 없는 세그먼트 제거
    - 동일 텍스트 반복이 threshold 초과면 제거
    """
    if not segments:
        return segments

    hallucinations = [
        "시청해 주셔서 감사합니다", "구독과 좋아요", "Thank you for watching",
        "MBC 뉴스", "SBS 뉴스", "KBS 뉴스", "JTBC 뉴스",
    ]

    cleaned: List[Dict[str, Any]] = []
    repeat_count = 1

    for seg in segments:
        text_clean = (seg.get("text") or "").strip()

        is_hallu = any(h in text_clean for h in hallucinations)
        if not is_hallu and not re.search(r"[가-힣a-zA-Z0-9]", text_clean):
            is_hallu = True

        if is_hallu:
            continue

        prev_text = (cleaned[-1].get("text") or "").strip() if cleaned else ""
        if text_clean == prev_text:
            repeat_count += 1
            if repeat_count <= repeat_threshold:
                cleaned.append(seg)
        else:
            repeat_count = 1
            cleaned.append(seg)

    removed = len(segments) - len(cleaned)
    if removed > 0:
        get_logger().log(f"🧹 반복/환각 구간 {removed}개 제거됨")

    return cleaned
