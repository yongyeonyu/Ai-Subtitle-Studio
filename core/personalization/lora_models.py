from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_path_text(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def line_break_pattern_for_text(text: Any) -> str:
    parts: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip().rstrip(".,!?~")
        if stripped:
            parts.append(str(len(stripped)))
    return "|".join(parts)


@dataclass(slots=True)
class TruthTableRow:
    media_id: str
    media_path: str
    subtitle_path: str
    segment_id: str
    start_sec: float
    end_sec: float
    raw_ground_truth_text: str
    speech_training_text: str
    excluded_parenthetical_text: str = ""
    line_break_pattern: str = ""
    punctuation_pattern: str = ""
    detected_split_rule: str = ""
    speaker_or_voice_hint: str = ""
    source_hash: str = ""
    dedupe_hash: str = ""
    created_at: str = ""
    updated_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        created_at = self.created_at or iso_now()
        updated_at = self.updated_at or created_at
        duration_sec = max(0.0, float(self.end_sec) - float(self.start_sec))
        extra = dict(self.extra or {})
        pattern_features = extra.get("pattern_features") if isinstance(extra.get("pattern_features"), dict) else {}
        speech_text = normalize_text(self.speech_training_text)
        raw_text = str(self.raw_ground_truth_text or "").strip()
        excluded_text = str(self.excluded_parenthetical_text or "").strip()
        char_count = len(speech_text.replace("\n", ""))
        if char_count <= 0:
            try:
                char_count = max(0, int(float(pattern_features.get("char_count", 0) or 0)))
            except Exception:
                char_count = 0
        cps = round(char_count / duration_sec, 3) if duration_sec > 0 else 0.0
        if cps <= 0.0 and pattern_features.get("cps") not in (None, ""):
            try:
                cps = round(max(0.0, float(pattern_features.get("cps") or 0.0)), 3)
            except Exception:
                cps = 0.0
        line_break_pattern = self.line_break_pattern or str(pattern_features.get("line_break_pattern") or "") or line_break_pattern_for_text(speech_text)
        punctuation_pattern = self.punctuation_pattern or "".join(
            ch for ch in raw_text if ch in ".,!?~"
        )
        source_hash = self.source_hash or stable_hash(
            {
                "media_path": normalize_path_text(self.media_path),
                "subtitle_path": normalize_path_text(self.subtitle_path),
                "segment_id": str(self.segment_id or ""),
                "start_sec": round(float(self.start_sec), 3),
                "end_sec": round(float(self.end_sec), 3),
                "raw_ground_truth_text": raw_text,
            }
        )
        dedupe_hash = self.dedupe_hash or stable_hash(
            {
                "media_id": str(self.media_id or ""),
                "segment_id": str(self.segment_id or ""),
                "start_sec": round(float(self.start_sec), 3),
                "end_sec": round(float(self.end_sec), 3),
                "speech_training_text": speech_text,
                "excluded_parenthetical_text": excluded_text,
            }
        )
        record = {
            "schema": "ai_subtitle_studio.truth_table_row.v1",
            "media_id": str(self.media_id or ""),
            "media_path": str(self.media_path or ""),
            "subtitle_path": str(self.subtitle_path or ""),
            "segment_id": str(self.segment_id or ""),
            "start_sec": round(float(self.start_sec), 3),
            "end_sec": round(float(self.end_sec), 3),
            "duration_sec": round(duration_sec, 3),
            "raw_ground_truth_text": raw_text,
            "speech_training_text": speech_text,
            "excluded_parenthetical_text": excluded_text,
            "line_break_pattern": line_break_pattern,
            "punctuation_pattern": punctuation_pattern,
            "char_count": char_count,
            "cps": cps,
            "detected_split_rule": str(self.detected_split_rule or ""),
            "speaker_or_voice_hint": str(self.speaker_or_voice_hint or ""),
            "source_hash": source_hash,
            "dedupe_hash": dedupe_hash,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        record.update(extra)
        return record


@dataclass(slots=True)
class ExcludedParentheticalRow:
    media_id: str
    media_path: str
    subtitle_path: str
    segment_id: str
    original_text: str
    excluded_text: str
    kept_text: str
    reason_code: str = "parenthetical_editorial"
    dedupe_hash: str = ""
    created_at: str = ""

    def to_record(self) -> dict[str, Any]:
        created_at = self.created_at or iso_now()
        dedupe_hash = self.dedupe_hash or stable_hash(
            {
                "media_id": str(self.media_id or ""),
                "segment_id": str(self.segment_id or ""),
                "excluded_text": normalize_text(self.excluded_text),
                "kept_text": normalize_text(self.kept_text),
            }
        )
        return {
            "schema": "ai_subtitle_studio.excluded_parenthetical_row.v1",
            "media_id": str(self.media_id or ""),
            "media_path": str(self.media_path or ""),
            "subtitle_path": str(self.subtitle_path or ""),
            "segment_id": str(self.segment_id or ""),
            "original_text": str(self.original_text or "").strip(),
            "excluded_text": str(self.excluded_text or "").strip(),
            "kept_text": str(self.kept_text or "").strip(),
            "reason_code": str(self.reason_code or "parenthetical_editorial"),
            "dedupe_hash": dedupe_hash,
            "created_at": created_at,
        }


@dataclass(slots=True)
class TrainingQueueItem:
    media_id: str
    media_path: str
    subtitle_path: str
    job_type: str
    status: str = "waiting"
    job_id: str = ""
    priority: int = 100
    progress: float = 0.0
    score: float | None = None
    last_error: str = ""
    attempts: int = 0
    created_at: str = ""
    updated_at: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        created_at = self.created_at or iso_now()
        updated_at = self.updated_at or created_at
        job_id = self.job_id or stable_hash(
            {
                "media_id": str(self.media_id or ""),
                "media_path": normalize_path_text(self.media_path),
                "subtitle_path": normalize_path_text(self.subtitle_path),
                "job_type": str(self.job_type or ""),
            }
        )[:24]
        return {
            "job_id": job_id,
            "media_id": str(self.media_id or ""),
            "media_path": str(self.media_path or ""),
            "subtitle_path": str(self.subtitle_path or ""),
            "job_type": str(self.job_type or ""),
            "status": str(self.status or "waiting"),
            "priority": int(self.priority),
            "progress": round(float(self.progress or 0.0), 4),
            "score": None if self.score is None else round(float(self.score), 4),
            "last_error": str(self.last_error or ""),
            "attempts": int(self.attempts or 0),
            "created_at": created_at,
            "updated_at": updated_at,
            "payload": dict(self.payload or {}),
        }


@dataclass(slots=True)
class LearnedRuleEntry:
    rule_text: str
    rule_type: str
    frequency: int
    confidence: float
    examples: list[str] = field(default_factory=list)
    source_media_refs: list[str] = field(default_factory=list)
    normalized_text: str = ""
    punctuation_pattern: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    rule_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        normalized_text = self.normalized_text or normalize_text(self.rule_text)
        first_seen_at = self.first_seen_at or iso_now()
        last_seen_at = self.last_seen_at or first_seen_at
        rule_id = self.rule_id or stable_hash(
            {
                "rule_text": normalized_text,
                "rule_type": str(self.rule_type or ""),
                "punctuation_pattern": str(self.punctuation_pattern or ""),
            }
        )[:24]
        return {
            "rule_id": rule_id,
            "rule_text": str(self.rule_text or "").strip(),
            "normalized_text": normalized_text,
            "rule_type": str(self.rule_type or ""),
            "punctuation_pattern": str(self.punctuation_pattern or ""),
            "frequency": int(self.frequency or 0),
            "confidence": round(float(self.confidence or 0.0), 4),
            "examples": [str(item or "").strip() for item in list(self.examples or []) if str(item or "").strip()],
            "source_media_refs": [
                str(item or "").strip() for item in list(self.source_media_refs or []) if str(item or "").strip()
            ],
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(slots=True)
class TrialRecord:
    trial_type: str
    media_id: str
    media_path: str
    subtitle_path: str
    config: dict[str, Any]
    status: str = "waiting"
    score: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    prompt_template_id: str = ""
    prompt_text: str = ""
    reason: str = ""
    trial_id: str = ""
    dedupe_hash: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        created_at = self.created_at or iso_now()
        updated_at = self.updated_at or created_at
        dedupe_hash = self.dedupe_hash or stable_hash(
            {
                "trial_type": str(self.trial_type or ""),
                "media_id": str(self.media_id or ""),
                "config": dict(self.config or {}),
                "prompt_template_id": str(self.prompt_template_id or ""),
                "prompt_text": str(self.prompt_text or ""),
            }
        )
        trial_id = self.trial_id or dedupe_hash[:24]
        return {
            "schema": "ai_subtitle_studio.personalization_trial_record.v1",
            "trial_id": trial_id,
            "trial_type": str(self.trial_type or ""),
            "media_id": str(self.media_id or ""),
            "media_path": str(self.media_path or ""),
            "subtitle_path": str(self.subtitle_path or ""),
            "status": str(self.status or "waiting"),
            "score": None if self.score is None else round(float(self.score), 4),
            "metrics": dict(self.metrics or {}),
            "config": dict(self.config or {}),
            "prompt_template_id": str(self.prompt_template_id or ""),
            "prompt_text": str(self.prompt_text or ""),
            "reason": str(self.reason or ""),
            "dedupe_hash": dedupe_hash,
            "created_at": created_at,
            "updated_at": updated_at,
            "metadata": dict(self.metadata or {}),
        }


__all__ = [
    "ExcludedParentheticalRow",
    "LearnedRuleEntry",
    "TrainingQueueItem",
    "TrialRecord",
    "TruthTableRow",
    "iso_now",
    "line_break_pattern_for_text",
    "normalize_path_text",
    "normalize_text",
    "stable_hash",
]
