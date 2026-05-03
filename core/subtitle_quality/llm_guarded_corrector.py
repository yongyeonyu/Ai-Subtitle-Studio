# Version: 03.01.23
# Phase: PHASE2
"""Guarded LLM correction helpers for conservative quality review mode."""

from __future__ import annotations

from typing import Iterable

from core.engine.llm_correction_guard import safe_llm_chunks, validate_llm_chunks

CONSERVATIVE_PROFILE_RULES = """
[검사/자동교정 보수 profile]
1. 원문에 없는 단어, 설명, 추정, 문맥 보강을 절대 추가하지 마세요.
2. 원문 단어를 삭제하거나 더 짧게 요약하지 마세요.
3. 의미가 바뀔 수 있는 표현 변경, 문어체 변환, 높임말 변환을 금지합니다.
4. 불확실한 단어는 원문 그대로 두고, 띄어쓰기와 명백한 오탈자만 최소 교정하세요.
5. 고유명사, 숫자, 영어 표기, 브랜드/행사명은 확실하지 않으면 원문 그대로 두세요.
6. 시간값, 번호, 타임코드, 후보 설명을 출력하지 마세요.
"""


def limited_negative_hints(memory_items: Iterable[str] | None, limit: int = 5) -> list[str]:
    hints: list[str] = []
    for item in memory_items or ():
        text = str(item or "").strip()
        if not text or text in hints:
            continue
        hints.append(text[:80])
        if len(hints) >= limit:
            break
    return hints


def build_conservative_prompt(base_prompt: str, wrong_answer_hints: Iterable[str] | None = None) -> str:
    prompt = f"{str(base_prompt or '').strip()}\n\n{CONSERVATIVE_PROFILE_RULES.strip()}"
    hints = limited_negative_hints(wrong_answer_hints)
    if hints:
        lines = "\n".join(f"- {hint}" for hint in hints)
        prompt = f"{prompt}\n\n[피해야 할 기존 오답 후보]\n{lines}"
    return prompt


def guarded_llm_chunks(source_text: str, chunks: Iterable[str] | None) -> list[str] | None:
    return safe_llm_chunks(source_text, chunks)

__all__ = [
    "CONSERVATIVE_PROFILE_RULES",
    "build_conservative_prompt",
    "guarded_llm_chunks",
    "limited_negative_hints",
    "validate_llm_chunks",
]
