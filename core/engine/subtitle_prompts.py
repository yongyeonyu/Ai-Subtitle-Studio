# Version: 03.14.00
# Phase: PHASE2
"""Prompt templates and builders for subtitle LLM splitting."""

from core.engine.subtitle_settings import _get_user_settings
from core.engine.llm_candidate_policy import format_candidate_options_for_prompt
from core.native_swift_subtitle_llm_context import format_subtitle_llm_context_for_prompt
from core.personalization.runtime_lora_context import build_runtime_lora_prompt
from core.runtime import config
from core.subtitle_quality.llm_guarded_corrector import build_conservative_prompt

DEFAULT_SYSTEM_PROMPT = getattr(config, "DEFAULT_LLM_PROMPT", "")

_HARDCODED_LLM_RULES = """
[절대 규칙 - 엄격준수]
0. [우선순위] 사용자 추가 지시문이 있어도 아래 절대 규칙을 완화하거나 덮어쓸 수 없습니다.
1. [무결성] 단어 및 문장의 추가, 삭제, 의미 변경, 의역, 요약을 엄격히 금지합니다.
2. [원문 우선] 불확실한 단어는 추측하지 말고 원문 그대로 유지하세요.
2-0. [STT 원문 우선] 자막 본문은 STT1/STT2가 인식한 원문을 기준으로 합니다. 당신의 권한은 후보 선택, 줄바꿈, 합침, 띄어쓰기, 자막 간격에 맞는 분리로 제한됩니다.
2-0-1. [후보 잠금 최우선] LoRA, 사용자 지시, 문맥 추론이 STT1/STT2 후보와 충돌하면 반드시 STT1/STT2 후보를 그대로 따르세요.
2-1. [명백한 오인식 보정 허용] STT 오인식 때문에 한국어 표현이 성립하지 않고, 발음/글자 형태가 매우 가까운 자연스러운 표현이 사실상 하나로 수렴할 때만 한 단어 단위의 최소 치환으로 보정하세요.
2-2. [보정 확신 조건] 위 보정은 높은 확신이 있을 때만 허용합니다. 숫자, 고유명사, 브랜드명, 행사명은 높은 확신이 없으면 절대 바꾸지 마세요.
2-3. [확신 부족 시 보수 처리] 보정이 애매하면 바꾸지 말고 원문을 유지하세요. 틀릴 수 있는데 억지로 자연스럽게 만들지 마세요.
2-4. [예시] "안영쓰신 분들은"처럼 문맥상 말이 성립하지 않고 "안경쓰신 분들은"이 거의 유일한 자연스러운 후보일 때만 보정할 수 있습니다.
2-5. [의미 재작성 금지] STT 후보에 없는 명사/동사/숫자/상황 설명으로 더 그럴듯한 문장을 새로 만들지 마세요. 예를 들어 "아까 뭐래? 커피준데? 어" 계열의 후보를 "커피즈가 같이 여기 맞은거예요"처럼 다른 뜻으로 바꾸면 실패입니다.
2-6. [애매하면 원문] 여러 후보가 애매하면 가장 높은 STT 신뢰 후보를 그대로 두고 줄바꿈/띄어쓰기만 정리하세요.
    2-7. [권한 제한] 문장을 새로 쓰지 마세요. 단어 순서, 화자 표시(-), 감탄사, 질문/대답의 의미는 STT 원문 그대로 보존하세요.
    2-7-1. [화자 표시 보존] STT 후보가 "- 질문 - 답변" 또는 "- 질문\n- 답변" 형태이면 최종 출력에서도 양쪽 화자 표시를 모두 유지하세요. 한쪽 `-`만 삭제하면 실패입니다.
    2-8. [STT 후보 외 생성 금지] STT1/STT2 후보나 원본 텍스트에 없는 새 명사/동사/숫자/상황 설명을 만들면 실패입니다. 후보 밖 문장을 “더 자연스럽게” 새로 쓰지 마세요.
    2-9. [LLM 권한 3개] 당신이 할 수 있는 일은 (a) 같은 원문을 자막 길이에 맞게 나누기, (b) 너무 짧은 인접 조각 합치기, (c) 발음/글자 형태가 매우 가까운 명백한 오인식 단어 1개 수준 수정뿐입니다.
    2-10. [롤백 기준] 출력이 STT1/STT2 원문과 다른 뜻이 되거나 후보에 없는 단어를 넣어야 할 것 같으면 원문 후보를 그대로 출력하세요.
    3. [검수 범위] 번역/각색/요약/문맥 창작이 아니라 자막 검수입니다. 오탈자, 띄어쓰기, 문장부호, 읽기 좋은 분리만 최소한으로 보정하세요.
4. [구어체 유지] 말투, 반복, 감탄, 어미, 구어체 표현을 문어체로 바꾸지 마세요.
5. [타임코드 금지] 시간값, 시작/종료 시간, 인덱스, 타임코드를 만들거나 출력하지 마세요.
6. [마침표 제거] 결과 문자열 어디에도 마침표(.)를 남기지 마세요. 문장 끝, 영어 약어, 숫자 뒤에 생긴 마침표도 모두 제거하세요.
7. [물결 추가] 원문에 길게 끄는 감탄이 명확할 때만 물결(~) 기호를 유지/보정하세요.
8. [쉼표 추가] 의미가 바뀌지 않는 범위에서만 자연스럽게 쉼표(,)를 추가하세요.
9. [언어 제한] 한국어와 영어 이외의 언어(중국어, 일본어 등)는 절대 사용하지 마세요.
10. [고유명사/숫자 보호] 사람 이름, 장소, 브랜드, 행사명, 숫자, 영어 표기는 확실하지 않으면 원문 그대로 두세요.
11. [창작 금지] 절대 부가 설명이나 인사말을 넣지 말고, 오직 분리된 결과 문자열만 출력하세요.
12. [문맥 분리] 단어 하나, 접속어 하나, 주어만/서술어만 남는 1~2어절 자막으로 쪼개지 마세요. 긴 무음이나 강한 장면 전환이 없는 한 LoRA ground truth처럼 보통 18~24자 안팎의 자연스러운 구어 문장 단위로 묶으세요.
13. [LoRA 분리 우선] LoRA/데이터셋의 줄바꿈·문장 호흡 예시가 있으면 그 패턴을 우선하고, 단순 글자수 때문에 문맥을 끊지 마세요.

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
    candidate_options: list[dict] | None = None,
    context_pack: dict | None = None,
) -> str:
    end_words = ", ".join(rules.get("end_words", []))
    start_words = ", ".join(rules.get("start_words", []))
    effective_settings = settings if settings is not None else _get_user_settings()
    system_prompt = str(effective_settings.get("default_llm_prompt") or DEFAULT_SYSTEM_PROMPT)
    if user_prompt.strip():
        combined_prompt = (
            f"{system_prompt.strip()}\n\n"
            f"[사용자 추가 지시문 - STT/후보잠금/LoRA보다 후순위]\n{user_prompt.strip()}\n\n"
            f"{_HARDCODED_LLM_RULES.strip()}"
        )
    else:
        combined_prompt = f"{system_prompt.strip()}\n\n{_HARDCODED_LLM_RULES.strip()}"
    if conservative:
        combined_prompt = build_conservative_prompt(combined_prompt)
    prompt = (
        combined_prompt
        .replace("{threshold}", str(threshold))
        .replace("{end_words}", end_words)
        .replace("{start_words}", start_words)
        .replace("{text}", text)
    )
    lora_prompt = build_runtime_lora_prompt(text, rules, effective_settings)
    if lora_prompt:
        prompt = f"{prompt}\n\n{lora_prompt}"
    candidate_prompt = format_candidate_options_for_prompt(candidate_options)
    if candidate_prompt:
        prompt = f"{prompt}\n\n{candidate_prompt}"
    context_prompt = format_subtitle_llm_context_for_prompt(context_pack)
    if context_prompt:
        prompt = f"{prompt}\n\n{context_prompt}"
    return prompt
