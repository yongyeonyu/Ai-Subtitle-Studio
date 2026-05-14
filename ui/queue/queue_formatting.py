from __future__ import annotations

import re
from typing import Any


DEFAULT_QUEUE_HEADER = "큐 리스트 : (0/0) - 0% 완료"

QUEUE_UNKNOWN_EXPECTED_TEXTS = frozenset(
    {
        "",
        "-",
        "?",
        "0",
        "0.0",
        "00:00",
        "00:00:00",
        "계산 중",
        "분석 중..",
        "예상불가",
        "학습 중",
    }
)


def format_queue_header(current: Any, total: Any, pct: Any) -> str:
    try:
        current_num = max(0, int(current))
    except Exception:
        current_num = 0
    try:
        total_num = max(0, int(total))
    except Exception:
        total_num = 0
    try:
        pct_num = max(0, min(100, int(pct)))
    except Exception:
        pct_num = 0
    return f"큐 리스트 : ({current_num}/{total_num}) - {pct_num}% 완료"


def build_queue_status_payload(
    idx: Any,
    status: Any,
    time_txt: Any = "",
    info_txt: Any = "",
    len_txt: Any = "",
) -> dict[str, Any]:
    return {
        "idx": idx,
        "status": str(status or ""),
        "time_txt": str(time_txt or ""),
        "info_txt": str(info_txt or ""),
        "len_txt": str(len_txt or ""),
    }


def normalize_queue_status_payload(
    payload_or_idx: Any,
    status: Any = None,
    time_txt: Any = "",
    info_txt: Any = "",
    len_txt: Any = "",
) -> dict[str, Any]:
    if isinstance(payload_or_idx, dict):
        payload = dict(payload_or_idx)
        return build_queue_status_payload(
            payload.get("idx", payload.get("row", 0)),
            payload.get("status", status or ""),
            payload.get("time_txt", payload.get("eta", time_txt)),
            payload.get("info_txt", payload.get("info", info_txt)),
            payload.get("len_txt", payload.get("duration", len_txt)),
        )
    return build_queue_status_payload(payload_or_idx, status, time_txt, info_txt, len_txt)


def build_queue_header_payload(
    current: Any,
    total: Any,
    pct: Any,
    eta_str: Any = "",
) -> dict[str, Any]:
    return {
        "current": current,
        "total": total,
        "pct": pct,
        "eta_str": str(eta_str or ""),
    }


def normalize_queue_header_payload(
    payload_or_current: Any,
    total: Any = None,
    pct: Any = None,
    eta_str: Any = "",
) -> dict[str, Any]:
    if isinstance(payload_or_current, dict):
        payload = dict(payload_or_current)
        return build_queue_header_payload(
            payload.get("current", payload.get("idx", 0)),
            payload.get("total", total if total is not None else 0),
            payload.get("pct", pct if pct is not None else 0),
            payload.get("eta_str", payload.get("eta", eta_str)),
        )
    return build_queue_header_payload(payload_or_current, total, pct, eta_str)


def normalize_queue_header_text(
    raw: Any,
    *,
    current: Any = 0,
    total: Any = 0,
    pct: Any = 0,
) -> str:
    text = str(raw or "").strip()
    if text:
        text = text.replace("📋 처리할 파일 리스트", "큐 리스트").replace("진행 중", "").strip()
        text = re.sub(r"\s+", " ", text).strip()
        match = re.search(r"\((\d+)\s*/\s*(\d+)\)\s*-\s*(\d+)%", text)
        if match:
            return format_queue_header(match.group(1), match.group(2), match.group(3))
        return text or format_queue_header(current, total, pct)
    return format_queue_header(current, total, pct)


def format_queue_clock(sec: Any) -> str:
    try:
        total = max(0, int(float(sec)))
    except Exception:
        return "00:00"
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"


def parse_queue_seconds_value(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        pass
    if ":" not in text:
        return None
    parts = [part.strip() for part in text.split(":")]
    if not parts or any(not part.isdigit() for part in parts):
        return None
    try:
        units = [int(part) for part in parts]
    except ValueError:
        return None
    if len(units) == 2:
        minutes, seconds = units
        return float((minutes * 60) + seconds)
    if len(units) == 3:
        hours, minutes, seconds = units
        return float((hours * 3600) + (minutes * 60) + seconds)
    return None


def queue_expected_time_is_unknown(value: Any) -> bool:
    text = str(value or "").strip()
    if text in QUEUE_UNKNOWN_EXPECTED_TEXTS:
        return True
    parsed = parse_queue_seconds_value(text)
    return parsed is not None and parsed <= 0


def queue_expected_display_text(value: Any) -> str:
    text = str(value or "").strip()
    return "예상불가" if queue_expected_time_is_unknown(text) else text


def format_queue_card_time(eta_text: Any, duration_text: Any) -> str:
    eta = str(eta_text or "-").strip() or "-"
    if "/" in eta:
        left, right = [part.strip() for part in eta.split("/", 1)]
        left = left or "00:00"
        right = queue_expected_display_text(right)
        return f"{left} / {right}"
    if queue_expected_time_is_unknown(eta):
        return "예상불가"
    return f"00:00 / {eta}"


def build_queue_sidebar_item(
    *,
    order: Any,
    raw_status: Any,
    file_text: Any,
    info_text: Any = "",
    eta_text: Any,
    duration_text: Any,
    active: bool = False,
) -> dict[str, Any]:
    done, error, status_active = queue_status_flags(raw_status)
    status = plain_queue_status(raw_status)
    return {
        "order": str(order or "-"),
        "status": status,
        "statusRaw": str(raw_status or "-"),
        "statusDisplay": "완료" if done else status,
        "done": bool(done),
        "active": bool(active and status_active and not done and not error),
        "error": bool(error),
        "file": str(file_text or "-"),
        "fileRaw": str(file_text or "-"),
        "info": str(info_text or "-"),
        "infoRaw": str(info_text or "-"),
        "duration": str(duration_text or "-"),
        "etaRaw": str(eta_text or "-"),
        "eta": format_queue_card_time(eta_text, duration_text),
    }


def queue_status_flags(status: Any) -> tuple[bool, bool, bool]:
    text = str(status or "")
    stripped = text.strip()
    stage_done_only = "컷 경계" in stripped and "완료" in stripped
    done = (
        not stage_done_only
        and "미완료" not in stripped
        and (
            stripped in {"완료", "✅기존자막", "기존자막"}
            or stripped.startswith("✅")
            and "완료" in stripped
            or "기존자막" in stripped
        )
    )
    error = any(token in text for token in ("오류", "실패", "중단"))
    active = not done and not error and not any(token in text for token in ("대기", "-"))
    return done, error, active


def plain_queue_status(status: Any) -> str:
    text = str(status or "").strip()
    text = re.sub(r"^[^\w가-힣\[]+\s*", "", text)
    text = re.sub(r"[\u2600-\u27BF\U0001F300-\U0001FAFF]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "-"
