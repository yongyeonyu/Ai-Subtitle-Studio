# Version: 01.00.00
import os
from logger import get_logger
from config import CORRECTIONS_FILE
import json
import re
from config import (
    CORRECTIONS_DIR, CORRECTIONS_FILE, RULES_FILE,
    DEFAULT_SPLIT_RULES, DEFAULT_SPLIT_PUNCTUATION, DEFAULT_MAX_CHARS,
    DATASET_DIR
)

# dataset 폴더 내 규칙 파일 경로
RULE_FILE = os.path.join(DATASET_DIR, "subtitle_rule.json")

# 시스템 기본 자막 분할 규칙
DEFAULT_RULES = {
    "end_words": ["고요","거든요","는데요","다","요","고","서","네","지","데","만","까","나","야지"],
    "start_words": ["어우","아","오","와","헐","헉","근데","그리고","그래서","하지만","그러면","이런","진짜","너무"]
}

def load_subtitle_rules():
    """기본 규칙과 저장된 파일의 규칙을 합쳐서 반환 (누적 방식)"""
    os.makedirs(DATASET_DIR, exist_ok=True)
    
    # 1. 기본값으로 시작
    rules = {
        "end_words": list(DEFAULT_RULES["end_words"]),
        "start_words": list(DEFAULT_RULES["start_words"])
    }
    
    # 2. 파일이 존재하면 읽어서 기존 리스트에 합침 (중복 제거)
    if os.path.exists(RULE_FILE):
        try:
            with open(RULE_FILE, 'r', encoding='utf-8') as f:
                file_rules = json.load(f)
                for key in ["end_words", "start_words"]:
                    if key in file_rules and isinstance(file_rules[key], list):
                        # set을 이용해 중복을 없애고 합친 뒤 정렬하여 저장
                        combined = set(rules[key]) | set(file_rules[key])
                        rules[key] = sorted(list(combined))
        except Exception as e:
            get_logger().log(f"  ⚠️ 규칙 파일 로드 중 오류: {e}")
            
    return rules

def add_split_rule(word):
    """사용자가 에디터에서 엔터를 칠 때 새로운 종료 어미를 파일에 누적 저장"""
    rules = load_subtitle_rules() # 기존에 누적된 규칙들을 먼저 불러옴 (파일+기본값)
    
    clean_word = word.replace(".", "").strip()
    if not clean_word:
        return

    # 이미 존재하지 않는 경우에만 추가
    if clean_word not in rules["end_words"]:
        rules["end_words"].append(clean_word)
        # 다시 한번 중복 제거 및 정렬
        rules["end_words"] = sorted(list(set(rules["end_words"])))
        
        try:
            with open(RULE_FILE, 'w', encoding='utf-8') as f:
                json.dump(rules, f, ensure_ascii=False, indent=2)
            get_logger().log(f"  📝 자막 분할 규칙 누적 완료: {clean_word}")
        except Exception as e:
            get_logger().log(f"  ❌ 규칙 저장 실패: {e}")

def remove_split_rule(word):
    """사용자가 에디터에서 자막을 합칠 때 해당 어미를 end_words에서 제거"""
    rules = load_subtitle_rules()

    clean_word = word.replace(".", "").strip()
    if not clean_word:
        return

    changed = False
    for key in ["end_words", "start_words"]:
        if clean_word in rules.get(key, []):
            rules[key] = sorted(list(set(w for w in rules[key] if w != clean_word)))
            changed = True

    if changed:
        try:
            with open(RULE_FILE, 'w', encoding='utf-8') as f:
                json.dump(rules, f, ensure_ascii=False, indent=2)
            get_logger().log(f"  📝 자막 분할 규칙 제거: {clean_word}")
        except Exception as e:
            get_logger().log(f"  ❌ 규칙 제거 실패: {e}")

def reset_split_rules():
    """필요 시 규칙을 기본값으로 초기화 (수동 호출용)"""
    os.makedirs(DATASET_DIR, exist_ok=True)
    with open(RULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_RULES, f, ensure_ascii=False, indent=2)
    get_logger().log("  ♻️ 자막 분할 규칙이 기본값으로 초기화되었습니다.")

# --- 이하 기타 유틸리티 함수들 ---

def seconds_to_srt_time(seconds: float) -> str:
    """초 → SRT 표준 포맷 HH:MM:SS,mmm (반올림 오버플로우 버그 수정)"""
    seconds = max(0.0, seconds)
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:           # 반올림으로 ms=1000 되는 경우 방지
        ms -= 1000; s += 1
        if s >= 60: s -= 60; m += 1
        if m >= 60: m -= 60; h += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def netflix_style(text):
    text = text.strip()
    text = re.sub(r'[.。]+\s*$', '', text)
    text = re.sub(r'[.。]\s+', ' ', text)
    return text.strip()

def load_corrections():
    if os.path.exists(CORRECTIONS_FILE):
        with open(CORRECTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_corrections(corrections):
    os.makedirs(CORRECTIONS_DIR, exist_ok=True)
    existing = load_corrections()
    existing.update(corrections)
    with open(CORRECTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2, sort_keys=True)

def apply_corrections(text, corrections):
    for wrong, right in corrections.items():
        text = text.replace(wrong, right)
    return text

def load_rules():
    """config의 기본 규칙 로드 (분할 로직용)"""
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                rules = json.load(f)
                return (
                    rules.get("split_rules", DEFAULT_SPLIT_RULES),
                    rules.get("split_punctuation", DEFAULT_SPLIT_PUNCTUATION),
                    rules.get("max_chars", DEFAULT_MAX_CHARS)
                )
        except:
            pass
    return DEFAULT_SPLIT_RULES, DEFAULT_SPLIT_PUNCTUATION, DEFAULT_MAX_CHARS

def remove_hallucinations(segments, repeat_threshold=3):
    if not segments:
        return segments
    hallucinations = [
        "시청해 주셔서 감사합니다","구독과 좋아요","Thank you for watching",
        "MBC 뉴스","SBS 뉴스","KBS 뉴스","JTBC 뉴스"
    ]
    cleaned = []
    repeat_count = 1
    for i, seg in enumerate(segments):
        text_clean = seg.get("text","").strip()
        is_hallucination = any(h in text_clean for h in hallucinations)
        if not is_hallucination and not re.search(r'[가-힣a-zA-Z0-9]', text_clean):
            is_hallucination = True
        if is_hallucination:
            continue
        if i == 0:
            cleaned.append(seg); continue
        prev_text = segments[i-1].get("text","").strip()
        if text_clean == prev_text:
            repeat_count += 1
            if repeat_count <= repeat_threshold:
                cleaned.append(seg)
        else:
            repeat_count = 1
            cleaned.append(seg)
    removed = len(segments) - len(cleaned)
    if removed > 0:
        get_logger().log(f"  🧹 반복/환각 구간 {removed}개 제거됨")
    return cleaned