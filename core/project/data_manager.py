# Version: 02.03.00
# Phase: PHASE1-B
"""
editor_data_manager.py
─────────────────────────────────────────────
# [크PD] vrew_editor_ui.py에서 분리한 데이터 관리 모듈
# 설정, 교정사전, subtitle_rule 파일 I/O 및 cleanup 로직만 담당
# vrew_editor_ui.py의 길이를 줄이고 단일 책임 원칙 적용

담당:
  - user_settings.json 로드/저장
  - dataset_correction.json 로드/저장
  - subtitle_rule.json 로드/저장
  - _cleanup_rules (저장시 정렬·중복제거·threshold 갱신)
"""

# [editor_data_manager.py] 상단 파일 경로 설정 부분

# [editor_data_manager.py] 상단
import os # 💡 [필수 추가] 이게 빠져서 에러가 났습니다!
import json
import re
import shutil

import config
from logger import get_logger

# 수정 — 설정 경로를 앱 공통 경로(config.DATASET_DIR)로 통일
DATASET_DIR = config.DATASET_DIR
if not os.path.exists(DATASET_DIR):
    os.makedirs(DATASET_DIR)

# 💡 [경로 설정] 상수로 관리하여 경로 꼬임을 방지합니다.
CORRECTION_FILE      = os.path.join(DATASET_DIR, "dataset_correction.json")
SUBTITLE_RULE_FILE   = os.path.join(DATASET_DIR, "subtitle_rule.json")
SETTINGS_FILE        = os.path.join(DATASET_DIR, "user_settings.json")
CUSTOM_DEFAULTS_FILE = os.path.join(DATASET_DIR, "custom_defaults.json")


# ── 설정 로드 ──────────────────────────────────────────────────────────────
def load_settings() -> dict:
    logger = get_logger()
    
    # [자동 이사] 최상위 폴더에 옛날 파일이 보이면 dataset 폴더로 강제 이동
    old_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_defaults.json")
    if os.path.exists(old_file):
        try:
            shutil.move(old_file, CUSTOM_DEFAULTS_FILE)
            logger.log("🚚 custom_defaults.json을 dataset 폴더로 이동 완료!")
        except: pass

    # 1. 기본값(custom_defaults.json) 불러오기
    defaults = {}
    if os.path.exists(CUSTOM_DEFAULTS_FILE):
        try:
            with open(CUSTOM_DEFAULTS_FILE, 'r', encoding='utf-8') as f:
                defaults = json.load(f)
        except: pass

    # 2. 사용자 설정(user_settings.json) 불러오기
    user_settings = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
        except: pass

    # 3. 💡 [병합] 기본값 위에 사용자 설정을 덮어씌움
    merged_settings = defaults.copy()
    merged_settings.update(user_settings)

    return merged_settings

# ── 설정 저장 (분리됨) ──────────────────────────────────────────────────────

# 💡 [요청 1] 일반 저장 -> user_settings.json에 저장
def save_settings(settings: dict) -> None:
    os.makedirs(DATASET_DIR, exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# 💡 [요청 2] 기본값으로 저장 -> custom_defaults.json에 저장
def save_default_settings(settings: dict) -> None:
    os.makedirs(DATASET_DIR, exist_ok=True)
    with open(CUSTOM_DEFAULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)
    get_logger().log("⭐ 현재 설정을 시스템 기본값(custom_defaults)으로 저장했습니다.")

# ── 교정사전 ──────────────────────────────────────────────────────────────
def load_corrections() -> dict:
    if os.path.exists(CORRECTION_FILE):
        try:
            with open(CORRECTION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"소설가유모씨": "u_mo_c"}

def save_correction(corrections: dict, original: str, corrected: str) -> dict:
    corrections[original] = corrected
    os.makedirs(DATASET_DIR, exist_ok=True)
    with open(CORRECTION_FILE, 'w', encoding='utf-8') as f:
        json.dump(corrections, f, ensure_ascii=False, indent=4)
    return corrections


# ── subtitle_rule ─────────────────────────────────────────────────────────
def load_subtitle_rules() -> dict:
    if os.path.exists(SUBTITLE_RULE_FILE):
        try:
            with open(SUBTITLE_RULE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def update_split_rule(subtitle_rules: dict, word: str, add: bool = True) -> dict:
    if not word:
        return subtitle_rules
    clean_word = re.sub(r'[^\w가-힣]', '', word)
    if not clean_word:
        return subtitle_rules

    try:
        if add:
            from utils import add_split_rule
            add_split_rule(clean_word)
        else:
            try:
                from utils import remove_split_rule
                remove_split_rule(clean_word)
            except ImportError:
                pass
    except Exception:
        pass
    return subtitle_rules


# ── cleanup (저장/종료시 정리) ────────────────────────────────────────────
def cleanup_rules(corrections: dict, subtitle_rules: dict,
                  settings: dict, get_segments_fn) -> tuple:
    logger = get_logger()
    logger.log("\n  ━━━ 데이터셋 정리 시작 ━━━")

    # 1. corrections 정렬·저장
    if isinstance(corrections, dict):
        before_count = len(corrections)
        corrections = {k: v for k, v in corrections.items() if k and k.strip()}
        corrections = dict(sorted(corrections.items(), key=lambda x: len(x[0]), reverse=True))
        after_count = len(corrections)
        removed = before_count - after_count
        try:
            os.makedirs(DATASET_DIR, exist_ok=True)
            with open(CORRECTION_FILE, 'w', encoding='utf-8') as f:
                json.dump(corrections, f, ensure_ascii=False, indent=4)
            if removed > 0:
                logger.log(f"  🧹 교정사전: 빈 키 {removed}개 제거 → {after_count}개 항목 저장")
            else:
                logger.log(f"  ✅ 교정사전: {after_count}개 항목 정렬 저장")
        except Exception as e:
            logger.log(f"  ❌ 교정사전 저장 실패: {e}")

    # 2. subtitle_rules 중복제거·정렬·저장
    if isinstance(subtitle_rules, dict):
        changes = []
        for k in subtitle_rules:
            if isinstance(subtitle_rules[k], list):
                before = len(subtitle_rules[k])
                subtitle_rules[k] = sorted(list(set(subtitle_rules[k])), key=len, reverse=True)
                after = len(subtitle_rules[k])
                if before != after:
                    changes.append(f"{k}: {before}→{after}개")
        try:
            os.makedirs(DATASET_DIR, exist_ok=True)
            with open(SUBTITLE_RULE_FILE, 'w', encoding='utf-8') as f:
                json.dump(subtitle_rules, f, ensure_ascii=False, indent=4)
            if changes:
                logger.log(f"  🧹 subtitle_rule 중복 제거: {', '.join(changes)}")
            else:
                total = sum(len(v) for v in subtitle_rules.values() if isinstance(v, list))
                logger.log(f"  ✅ subtitle_rule: 총 {total}개 항목 정렬 저장")
        except Exception as e:
            logger.log(f"  ❌ subtitle_rule 저장 실패: {e}")

    # 3. threshold 갱신
    # 💡 [핵심 반영] 평균 글자 수를 계산해서 몰래 덮어씌우던 '자동 변경 로직'을 완전히 삭제했습니다!
    # 이제 오직 설정창(SettingsDialog)에서 설정한 값만 유지됩니다.
    old_threshold = settings.get("split_length_threshold", 10)
    logger.log(f"  📐 threshold 유지 (수동 설정값): {old_threshold}자")

    logger.log("  ━━━ 데이터셋 정리 완료 ━━━\n")
    return corrections, subtitle_rules, settings