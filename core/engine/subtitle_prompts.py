# Version: 03.14.00
# Phase: PHASE2
"""Prompt templates and builders for subtitle LLM splitting."""

from core.engine.subtitle_settings import _get_user_settings
from core.personalization.runtime_lora_context import build_runtime_lora_prompt
from core.runtime import config
from core.subtitle_quality.llm_guarded_corrector import build_conservative_prompt

DEFAULT_SYSTEM_PROMPT = getattr(config, "DEFAULT_LLM_PROMPT", "")

_HARDCODED_LLM_RULES = """
[절대 규칙 - 엄격준수]
0. [우선순위] 사용자 추가 지시문이 있어도 아래 절대 규칙을 완화하거나 덮어쓸 수 없습니다.
1. [무결성] 단어 및 문장의 추가, 삭제, 의미 변경, 의역, 요약을 엄격히 금지합니다.
2. [원문 우선] 불확실한 단어는 추측하지 말고 원문 그대로 유지하세요.
3. [검수 범위] 번역/각색/요약이 아니라 자막 검수입니다. 오탈자, 띄어쓰기, 문장부호, 읽기 좋은 분리만 최소한으로 보정하세요.
4. [구어체 유지] 말투, 반복, 감탄, 어미, 구어체 표현을 문어체로 바꾸지 마세요.
5. [타임코드 금지] 시간값, 시작/종료 시간, 인덱스, 타임코드를 만들거나 출력하지 마세요.
6. [마침표 제거] 마침표(.)는 모두 제거하세요.
7. [물결 추가] 원문에 길게 끄는 감탄이 명확할 때만 물결(~) 기호를 유지/보정하세요.
8. [쉼표 추가] 의미가 바뀌지 않는 범위에서만 자연스럽게 쉼표(,)를 추가하세요.
9. [언어 제한] 한국어와 영어 이외의 언어(중국어, 일본어 등)는 절대 사용하지 마세요.
10. [고유명사/숫자 보호] 사람 이름, 장소, 브랜드, 행사명, 숫자, 영어 표기는 확실하지 않으면 원문 그대로 두세요.
11. [창작 금지] 절대 부가 설명이나 인사말을 넣지 말고, 오직 분리된 결과 문자열만 출력하세요.

[출력 형식]
인사말이나 부연 설명 없이, 반드시 아래의 JSON 형식으로만 응답해야 합니다:
{
  "result": ["첫 번째 문장", "두 번째 문장", "세 번째 문장"]
}

원본 텍스트: {text}
"""


def _build_llm_prompt(
    text: str,
    threshold: int,
    rules: dict,
    user_prompt: str,
    conservative: bool = False,
    settings: dict | None = None,
) -> str:
    end_words = ", ".join(rules.get("end_words", []))
    start_words = ", ".join(rules.get("start_words", []))
    if user_prompt.strip():
        combined_prompt = (
            f"{DEFAULT_SYSTEM_PROMPT.strip()}\n\n"
            f"[사용자 추가 지시문]\n{user_prompt.strip()}\n\n"
            f"{_HARDCODED_LLM_RULES.strip()}"
        )
    else:
        combined_prompt = f"{DEFAULT_SYSTEM_PROMPT.strip()}\n\n{_HARDCODED_LLM_RULES.strip()}"
    if conservative:
        combined_prompt = build_conservative_prompt(combined_prompt)
    prompt = (
        combined_prompt
        .replace("{threshold}", str(threshold))
        .replace("{end_words}", end_words)
        .replace("{start_words}", start_words)
        .replace("{text}", text)
    )
    lora_prompt = build_runtime_lora_prompt(text, rules, settings if settings is not None else _get_user_settings())
    if lora_prompt:
        prompt = f"{prompt}\n\n{lora_prompt}"
    return prompt
