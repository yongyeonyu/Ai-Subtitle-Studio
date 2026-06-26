from __future__ import annotations

REFERENCE_SPLIT_PROTOCOL_ID = "nas_50_reference_split.v1"
REFERENCE_SPLIT_TARGET_COMPACT_CHARS = 13
REFERENCE_SPLIT_NORMAL_MIN_COMPACT_CHARS = 9
REFERENCE_SPLIT_NORMAL_MAX_COMPACT_CHARS = 17
REFERENCE_SPLIT_SOFT_UPPER_COMPACT_CHARS = 22
REFERENCE_SPLIT_LINE_SOFT_UPPER_COMPACT_CHARS = 16


def reference_split_protocol_summary() -> str:
    return (
        f"{REFERENCE_SPLIT_PROTOCOL_ID}: 50개 정답 SRT 기준 목표 "
        f"{REFERENCE_SPLIT_TARGET_COMPACT_CHARS}자, 정상 대역 "
        f"{REFERENCE_SPLIT_NORMAL_MIN_COMPACT_CHARS}~{REFERENCE_SPLIT_NORMAL_MAX_COMPACT_CHARS}자, "
        f"p90 상한 {REFERENCE_SPLIT_SOFT_UPPER_COMPACT_CHARS}자"
    )


def reference_split_protocol_llm_rule() -> str:
    return (
        "단어 하나, 접속어 하나, 주어만/서술어만 남는 의미 없는 1~2어절 자막으로 쪼개지 마세요. "
        f"50개 정답 SRT 분포({REFERENCE_SPLIT_PROTOCOL_ID})처럼 기본 목표는 "
        f"공백 제외 {REFERENCE_SPLIT_TARGET_COMPACT_CHARS}자이고, 보통 "
        f"{REFERENCE_SPLIT_NORMAL_MIN_COMPACT_CHARS}~{REFERENCE_SPLIT_NORMAL_MAX_COMPACT_CHARS}자 "
        "구어 호흡으로 묶으세요. "
        f"{REFERENCE_SPLIT_SOFT_UPPER_COMPACT_CHARS}자를 넘으면 자연스러운 어절/쉼표/질문/대답 경계에서 "
        "우선 분리하되, 고유명사·숫자·브랜드명 내부는 끊지 마세요. "
        "5~8자 반응/대답 자막은 무음, 컷 경계, 실제 발화 시작이 분리될 때 허용합니다. "
        "괄호 안 주석과 화자 대시는 텍스트 학습/정확도 기준에서 제외하고, 시작 시간 정합을 최우선으로 보존하세요."
    )


def reference_split_protocol_runtime_line() -> str:
    return (
        f"정답 자막 분할 기준={REFERENCE_SPLIT_PROTOCOL_ID}, "
        f"목표={REFERENCE_SPLIT_TARGET_COMPACT_CHARS}자, "
        f"정상대역={REFERENCE_SPLIT_NORMAL_MIN_COMPACT_CHARS}~{REFERENCE_SPLIT_NORMAL_MAX_COMPACT_CHARS}자, "
        f"긴자막 우선분리={REFERENCE_SPLIT_SOFT_UPPER_COMPACT_CHARS}자 초과, "
        f"줄 단위 상한={REFERENCE_SPLIT_LINE_SOFT_UPPER_COMPACT_CHARS}자"
    )


__all__ = [
    "REFERENCE_SPLIT_LINE_SOFT_UPPER_COMPACT_CHARS",
    "REFERENCE_SPLIT_NORMAL_MAX_COMPACT_CHARS",
    "REFERENCE_SPLIT_NORMAL_MIN_COMPACT_CHARS",
    "REFERENCE_SPLIT_PROTOCOL_ID",
    "REFERENCE_SPLIT_SOFT_UPPER_COMPACT_CHARS",
    "REFERENCE_SPLIT_TARGET_COMPACT_CHARS",
    "reference_split_protocol_llm_rule",
    "reference_split_protocol_runtime_line",
    "reference_split_protocol_summary",
]
