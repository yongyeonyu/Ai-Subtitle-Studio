# Version: 03.01.28
# Phase: PHASE2
from __future__ import annotations

import json
from typing import Any


ROUGH_CUT_PROMPT_ID = "roughcut_page3b_v1"

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
    "build_roughcut_prompt",
    "validate_roughcut_action_response",
]
