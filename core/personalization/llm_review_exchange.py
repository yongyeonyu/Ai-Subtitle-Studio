from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.personalization.lora_models import LearnedRuleEntry, TrialRecord, iso_now, normalize_text, stable_hash
from core.personalization.lora_storage import (
    append_prompt_trials,
    initialize_lora_personalization_store,
    load_best_settings,
    load_learned_rules,
    refresh_lora_personalization_manifest,
    save_best_settings,
    save_learned_rules,
    store_paths,
)


LLM_REVIEW_REQUEST_SCHEMA = "ai_subtitle_studio.personalization_llm_review_request.v1"
LLM_REVIEW_RESULT_SCHEMA = "ai_subtitle_studio.personalization_llm_review_result.v1"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def _tail_rows(rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    limit = max(1, int(max_rows or 1))
    return list(rows or [])[-limit:]


def _adapter_inventory(trained_adapters_dir: Path) -> list[dict[str, Any]]:
    if not trained_adapters_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(trained_adapters_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append(
            {
                "path": str(path),
                "name": path.name,
                "size_bytes": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return items


def _review_prompt() -> str:
    return "\n".join(
        [
            "You are reviewing subtitle personalization data for AI Subtitle Studio.",
            "Do not invent new facts, timings, media names, or model scores.",
            "Review the supplied truth-table samples, learned rules, trials, and best settings.",
            "Return only valid JSON using schema ai_subtitle_studio.personalization_llm_review_result.v1.",
            "Prefer conservative changes: accept rules only when examples support them.",
            "Use accepted_split_rules for useful split punctuation/phrase rules.",
            "Use accepted_line_break_rules for stable line-break patterns.",
            "Use prompt_trials for improved subtitle QA/personalization prompts.",
            "Use setting_recommendations only for settings supported by the provided data.",
        ]
    )


def result_json_template(review_id: str = "") -> dict[str, Any]:
    return {
        "schema": LLM_REVIEW_RESULT_SCHEMA,
        "review_id": str(review_id or ""),
        "accepted_split_rules": [],
        "accepted_line_break_rules": [],
        "prompt_trials": [],
        "setting_recommendations": {
            "global_recommended_defaults": {},
            "by_media_id": {},
            "by_media_path": {},
            "by_audio_profile": {},
            "by_style_cluster": {},
        },
        "notes": [],
    }


def build_llm_review_request(
    *,
    store_dir: str | Path | None = None,
    max_rows_per_section: int = 40,
) -> dict[str, Any]:
    initialize_lora_personalization_store(store_dir)
    paths = store_paths(store_dir)
    manifest = refresh_lora_personalization_manifest(store_dir)
    truth_rows = _read_jsonl(paths["truth_table"])
    setting_trials = _read_jsonl(paths["setting_trials"])
    prompt_trials = _read_jsonl(paths["prompt_trials"])
    excluded_rows = _read_jsonl(paths["excluded_parentheticals"])
    review_seed = {
        "counts": manifest.get("counts") or {},
        "latest_truth": _tail_rows(truth_rows, min(5, max_rows_per_section)),
        "latest_prompt_trials": _tail_rows(prompt_trials, min(5, max_rows_per_section)),
    }
    review_id = stable_hash(review_seed)[:24]
    result_template = result_json_template(review_id)
    return {
        "schema": LLM_REVIEW_REQUEST_SCHEMA,
        "created_at": iso_now(),
        "review_id": review_id,
        "workflow": {
            "mode": "manual_chat_json_exchange",
            "supported_reviewers": ["ChatGPT", "Gemini", "Claude", "local LLM"],
            "privacy_note": "This file can contain subtitle text and local media paths. Remove sensitive rows before pasting into an external chat service.",
        },
        "llm_usage_guidance": {
            "can_help": [
                "Judge whether learned split and line-break rules are semantically reasonable.",
                "Refine prompt templates for subtitle QA and personalization.",
                "Flag suspicious parenthetical exclusions or weak training examples.",
                "Summarize setting recommendations from trial metrics.",
            ],
            "cannot_help_reliably": [
                "Inspect LoRA adapter binary weights directly.",
                "Replace ground-truth validation or real scoring runs.",
                "Guarantee better subtitle output without re-running local evaluation.",
            ],
        },
        "chat_prompt": _review_prompt(),
        "return_json_template": result_template,
        "data": {
            "manifest_counts": manifest.get("counts") or {},
            "truth_table_recent_rows": _tail_rows(truth_rows, max_rows_per_section),
            "excluded_parentheticals_recent_rows": _tail_rows(excluded_rows, max_rows_per_section),
            "setting_trials_recent_rows": _tail_rows(setting_trials, max_rows_per_section),
            "prompt_trials_recent_rows": _tail_rows(prompt_trials, max_rows_per_section),
            "learned_split_rules": load_learned_rules("split", store_dir),
            "learned_line_break_rules": load_learned_rules("line_break", store_dir),
            "best_settings": load_best_settings(store_dir),
            "trained_adapter_inventory": _adapter_inventory(paths["trained_adapters"]),
        },
    }


def export_llm_review_request(
    *,
    store_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    max_rows_per_section: int = 40,
) -> dict[str, Any]:
    payload = build_llm_review_request(store_dir=store_dir, max_rows_per_section=max_rows_per_section)
    paths = store_paths(store_dir)
    target = Path(output_path) if output_path else paths["llm_review_request"]
    _write_json(paths["llm_review_request"], payload)
    _write_json(target, payload)
    refresh_lora_personalization_manifest(store_dir)
    return {
        "path": str(target),
        "store_path": str(paths["llm_review_request"]),
        "review_id": payload.get("review_id", ""),
        "schema": payload.get("schema", ""),
        "counts": dict((payload.get("data") or {}).get("manifest_counts") or {}),
    }


def _coerce_float(value: Any, default: float = 0.75) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    if number > 1.0:
        number = number / 100.0
    return max(0.0, min(1.0, number))


def _coerce_int(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _coerce_rule_record(raw: Any, *, rule_kind: str, review_id: str) -> dict[str, Any] | None:
    if isinstance(raw, str):
        item = {"rule_text": raw}
    elif isinstance(raw, dict):
        item = dict(raw)
    else:
        return None
    rule_text = str(
        item.get("rule_text")
        or item.get("text")
        or item.get("pattern")
        or item.get("rule")
        or ""
    ).strip()
    if not rule_text:
        return None
    rule_type = "split_rule" if rule_kind == "split" else "line_break_rule"
    metadata = dict(item.get("metadata") or {})
    metadata.update(
        {
            "source": "manual_llm_review",
            "review_id": str(review_id or ""),
            "llm_reason": str(item.get("reason") or item.get("rationale") or ""),
        }
    )
    return LearnedRuleEntry(
        rule_text=rule_text,
        rule_type=rule_type,
        frequency=max(1, _coerce_int(item.get("frequency") or item.get("support_count") or 1, 1)),
        confidence=_coerce_float(item.get("confidence"), 0.75),
        examples=_list_texts(item.get("examples")),
        source_media_refs=_list_texts(item.get("source_media_refs") or item.get("media_refs")),
        punctuation_pattern=str(item.get("punctuation_pattern") or ""),
        metadata=metadata,
    ).to_record()


def _merge_rule_items(
    *,
    rule_kind: str,
    incoming: list[dict[str, Any]],
    store_dir: str | Path | None,
) -> int:
    if not incoming:
        return 0
    existing_payload = load_learned_rules(rule_kind, store_dir)
    existing_items = list(existing_payload.get("items") or [])
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in existing_items:
        key = normalize_text(item.get("normalized_text") or item.get("rule_text") or item.get("rule_id") or "")
        if not key:
            continue
        by_key[key] = dict(item)
        order.append(key)
    inserted = 0
    for item in incoming:
        key = normalize_text(item.get("normalized_text") or item.get("rule_text") or item.get("rule_id") or "")
        if not key:
            continue
        if key in by_key:
            current = dict(by_key[key])
            current["frequency"] = max(
                _coerce_int(current.get("frequency"), 0),
                _coerce_int(item.get("frequency"), 0),
            )
            current["confidence"] = max(
                _coerce_float(current.get("confidence"), 0.0),
                _coerce_float(item.get("confidence"), 0.0),
            )
            current["examples"] = _list_texts(list(current.get("examples") or []) + list(item.get("examples") or []))[:8]
            metadata = dict(current.get("metadata") or {})
            metadata.update(dict(item.get("metadata") or {}))
            current["metadata"] = metadata
            current["last_seen_at"] = iso_now()
            by_key[key] = current
            continue
        by_key[key] = dict(item)
        order.append(key)
        inserted += 1
    save_learned_rules(
        rule_kind,
        [by_key[key] for key in order if key in by_key],
        store_dir=store_dir,
        metadata=dict(existing_payload.get("metadata") or {}),
    )
    return inserted


def _coerce_prompt_trial(raw: Any, *, review_id: str) -> dict[str, Any] | None:
    if isinstance(raw, str):
        item = {"prompt_text": raw}
    elif isinstance(raw, dict):
        item = dict(raw)
    else:
        return None
    prompt_text = str(item.get("prompt_text") or item.get("prompt") or "").strip()
    if not prompt_text:
        return None
    config = dict(item.get("config") or {})
    config.setdefault("source", "manual_llm_review")
    score_value = item.get("score")
    try:
        score = None if score_value is None else float(score_value)
    except Exception:
        score = None
    return TrialRecord(
        trial_type="prompt",
        media_id=str(item.get("media_id") or ""),
        media_path=str(item.get("media_path") or ""),
        subtitle_path=str(item.get("subtitle_path") or ""),
        config=config,
        status=str(item.get("status") or "reviewed"),
        score=score,
        metrics=dict(item.get("metrics") or {}),
        prompt_template_id=str(item.get("prompt_template_id") or "manual_llm_review"),
        prompt_text=prompt_text,
        reason=str(item.get("reason") or item.get("rationale") or ""),
        metadata={"source": "manual_llm_review", "review_id": str(review_id or "")},
    ).to_record()


def _merge_best_settings_recommendations(
    recommendations: Any,
    *,
    store_dir: str | Path | None,
) -> bool:
    if not isinstance(recommendations, dict) or not recommendations:
        return False
    current = load_best_settings(store_dir)
    touched = False
    for key in (
        "global_recommended_defaults",
        "by_media_id",
        "by_media_path",
        "by_audio_profile",
        "by_style_cluster",
    ):
        incoming = recommendations.get(key)
        if not isinstance(incoming, dict) or not incoming:
            continue
        target = dict(current.get(key) or {})
        for subkey, value in incoming.items():
            target[str(subkey)] = value
        current[key] = target
        touched = True
    if touched:
        metadata = dict(current.get("metadata") or {})
        metadata["last_manual_llm_review_at"] = iso_now()
        current["metadata"] = metadata
        save_best_settings(current, store_dir)
    return touched


def import_llm_review_result(
    payload: dict[str, Any],
    *,
    store_dir: str | Path | None = None,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("LLM review result must be a JSON object.")
    if str(payload.get("schema") or "") != LLM_REVIEW_RESULT_SCHEMA:
        raise ValueError(f"Unsupported LLM review result schema: {payload.get('schema')!r}")
    initialize_lora_personalization_store(store_dir)
    review_id = str(payload.get("review_id") or "")
    split_rules = [
        record
        for raw in list(payload.get("accepted_split_rules") or [])
        if (record := _coerce_rule_record(raw, rule_kind="split", review_id=review_id)) is not None
    ]
    line_break_rules = [
        record
        for raw in list(payload.get("accepted_line_break_rules") or [])
        if (record := _coerce_rule_record(raw, rule_kind="line_break", review_id=review_id)) is not None
    ]
    prompt_trials = [
        record
        for raw in list(payload.get("prompt_trials") or [])
        if (record := _coerce_prompt_trial(raw, review_id=review_id)) is not None
    ]
    inserted_split = _merge_rule_items(rule_kind="split", incoming=split_rules, store_dir=store_dir)
    inserted_line_break = _merge_rule_items(rule_kind="line_break", incoming=line_break_rules, store_dir=store_dir)
    prompt_result = append_prompt_trials(prompt_trials, store_dir) if prompt_trials else {"appended_rows": 0}
    settings_updated = _merge_best_settings_recommendations(
        payload.get("setting_recommendations"),
        store_dir=store_dir,
    )
    paths = store_paths(store_dir)
    raw_result = dict(payload)
    raw_result["imported_at"] = iso_now()
    if source_path:
        raw_result["source_path"] = str(source_path)
    _write_json(paths["llm_review_result"], raw_result)
    manifest = refresh_lora_personalization_manifest(store_dir)
    return {
        "review_id": review_id,
        "inserted_split_rules": inserted_split,
        "inserted_line_break_rules": inserted_line_break,
        "appended_prompt_trials": int(prompt_result.get("appended_rows", 0) or 0),
        "settings_updated": settings_updated,
        "result_path": str(paths["llm_review_result"]),
        "manifest": manifest,
    }


def import_llm_review_result_file(
    path: str | Path,
    *,
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(path)
    payload = _read_json(source, None)
    if not isinstance(payload, dict):
        raise ValueError("선택한 파일이 올바른 JSON 객체가 아닙니다.")
    return import_llm_review_result(payload, store_dir=store_dir, source_path=source)


__all__ = [
    "LLM_REVIEW_REQUEST_SCHEMA",
    "LLM_REVIEW_RESULT_SCHEMA",
    "build_llm_review_request",
    "export_llm_review_request",
    "import_llm_review_result",
    "import_llm_review_result_file",
    "result_json_template",
]
