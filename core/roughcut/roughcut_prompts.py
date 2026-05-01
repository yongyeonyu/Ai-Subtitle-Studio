# Version: 03.02.01
# Phase: PHASE2
from __future__ import annotations

import json
from typing import Any


ROUGH_CUT_PROMPT_ID = "roughcut_page3b_v1"

DEFAULT_ROUGHCUT_PROMPT_V1 = """너는 유튜브 러프컷 에디터의 챕터 분석 보조자다.
자막을 위에서 아래로 순차적으로 읽되, 먼저 전체 자막 흐름을 파악한 뒤 중분류를 나눈다.
중분류 A/B/C/D는 화면 전환, 주제 전환, 장소 전환, 행동 단계 전환처럼 시청자가 장면이 바뀌었다고 느끼는 큰 흐름 단위다.
중분류는 실제 러프컷 편집 최소 단위다.
단순한 말 끊김, 짧은 침묵, 같은 주제 안의 문장 변화, 단어 반복, 말투 변화만으로는 새 중분류를 만들지 않는다.
경계가 애매하면 자막 개수를 늘려도 하나의 중분류로 유지하고, 명확한 전환점이 있을 때만 나눈다.
중분류는 가능하면 최소 5개 이상의 자막 줄을 포함한다.
소분류 1/2/3/4는 중분류 내부의 세부 흐름이다.
소분류는 1개 자막 줄도 허용된다.
UI에서 테두리로 묶이는 단위는 중분류뿐이다.
소분류는 별도 세그먼트 박스로 만들지 않는다.
태그, 주제, 요약은 중분류 기준으로 작성한다.
중분류가 끝났다고 판단해도 즉시 최종 확정하지 말고 provisional로 둔다.
다음 중분류 후보를 읽은 뒤 이전 중분류 경계를 재검증한다.
경계가 잘못되었다면 move_boundary, merge_segments, split_current, needs_user_review 중 하나를 반환한다.
전체 중분류 흐름을 기반으로 유튜브 제목 후보를 추천한다.
응답은 반드시 JSON으로 반환한다."""

ROUGH_CUT_ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "propose_major_segment": {
        "required": ["major_segments"],
        "item_required": ["major_id", "title", "start", "end", "minor_codes"],
    },
    "verify_boundary": {
        "required": ["boundaries"],
        "item_required": ["major_id", "status", "confidence"],
    },
    "title_suggestions": {
        "required": ["titles"],
        "item_required": ["title", "score", "reason"],
    },
}


def build_roughcut_prompt(
    action: str,
    payload: dict[str, Any],
    *,
    prompt_id: str = ROUGH_CUT_PROMPT_ID,
    token_budget: int = 4096,
    user_prompt: str = "",
) -> str:
    schema = ROUGH_CUT_ACTION_SCHEMAS.get(action, {})
    body = {
        "prompt_id": prompt_id or ROUGH_CUT_PROMPT_ID,
        "action": action,
        "language": "ko",
        "token_budget": max(512, int(token_budget or 4096)),
        "output_contract": {
            "json_only": True,
            "schema": schema,
        },
        "editor_instructions": (user_prompt or DEFAULT_ROUGHCUT_PROMPT_V1).strip(),
        "payload": payload or {},
    }
    return json.dumps(body, ensure_ascii=False, indent=2)


def validate_roughcut_action_response(action: str, response: dict[str, Any]) -> tuple[bool, str]:
    schema = ROUGH_CUT_ACTION_SCHEMAS.get(action)
    if schema is None:
        return False, f"unsupported_action:{action}"
    if not isinstance(response, dict):
        return False, "response_not_object"
    for key in schema.get("required", []):
        if key not in response:
            return False, f"missing:{key}"
        if not isinstance(response.get(key), list):
            return False, f"not_list:{key}"
    return True, ""


__all__ = [
    "ROUGH_CUT_ACTION_SCHEMAS",
    "ROUGH_CUT_PROMPT_ID",
    "DEFAULT_ROUGHCUT_PROMPT_V1",
    "build_roughcut_prompt",
    "validate_roughcut_action_response",
]
