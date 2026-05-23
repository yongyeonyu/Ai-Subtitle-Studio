from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

try:
    from core.native_cut_boundary import llm_macro_group_ranges as _native_llm_macro_group_ranges
except Exception:  # pragma: no cover - optional native extension.
    _native_llm_macro_group_ranges = None


MACRO_CHUNK_POLICY_SCHEMA = "ai_subtitle_studio.subtitle_llm_macro_chunk.v1"


def _setting_bool(settings: dict[str, Any] | None, key: str, default: bool = True) -> bool:
    value = dict(settings or {}).get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
    return bool(value)


def _setting_int(settings: dict[str, Any] | None, key: str, default: int) -> int:
    try:
        value = dict(settings or {}).get(key, default)
        if value in (None, ""):
            value = default
        return int(value)
    except Exception:
        return int(default)


def _setting_float(settings: dict[str, Any] | None, key: str, default: float) -> float:
    try:
        value = dict(settings or {}).get(key, default)
        if value in (None, ""):
            value = default
        return float(value)
    except Exception:
        return float(default)


def llm_macro_chunk_enabled(settings: dict[str, Any], model: str, segment_count: int) -> bool:
    if "사용 안함" in str(model or ""):
        return False
    if not _setting_bool(settings, "subtitle_llm_macro_chunk_enabled", True):
        return False
    min_rows = max(2, _setting_int(settings, "subtitle_llm_macro_chunk_min_rows", 10))
    return int(segment_count or 0) >= min_rows


def confirmed_cut_before_segment(prev: dict[str, Any], current: dict[str, Any], settings: dict[str, Any]) -> bool:
    if not _setting_bool(settings, "subtitle_llm_macro_chunk_use_cut_boundaries", True):
        return False
    start = float(current.get("start", 0.0) or 0.0)
    prev_end = float(prev.get("end", start) or start)
    snap = max(0.0, _setting_float(settings, "subtitle_bundle_boundary_snap_window_sec", 1.0))
    for key in ("nearest_confirmed_cut_sec", "nearest_cut_boundary_sec", "cut_boundary_sec"):
        try:
            boundary = float(current.get(key, None))
        except Exception:
            continue
        if abs(boundary - start) <= snap or abs(boundary - prev_end) <= snap:
            return True
    marker_text = " ".join(
        str(current.get(key, "") or "")
        for key in ("cut_boundary_role", "cut_boundary_source", "cut_boundary_type")
    ).lower()
    if "confirmed" in marker_text or "scene_start" in marker_text or "hard_cut" in marker_text:
        return True
    guard = dict(current.get("_cut_boundary_guard_policy") or {})
    action = str(guard.get("action", "") or "").lower()
    return "cut" in action and ("start" in action or "scene" in action or "clamp" in action)


def build_llm_macro_groups(rows: list[dict], needs_llm: list[bool], settings: dict) -> list[dict]:
    min_rows = max(2, _setting_int(settings, "subtitle_llm_macro_chunk_min_rows", 10))
    max_rows = max(min_rows, _setting_int(settings, "subtitle_llm_macro_chunk_max_rows", 15))
    native = _native_macro_groups(rows, needs_llm, settings, min_rows=min_rows, max_rows=max_rows)
    if native is not None:
        return native
    groups: list[dict] = []
    current_rows: list[dict] = []
    current_needs: list[bool] = []
    start_index = 0

    def flush() -> None:
        nonlocal current_rows, current_needs, start_index
        if not current_rows:
            return
        groups.append(
            {
                "start_index": start_index,
                "rows": current_rows,
                "needs_llm": any(current_needs),
                "need_count": sum(1 for item in current_needs if item),
            }
        )
        start_index += len(current_rows)
        current_rows = []
        current_needs = []

    for index, row in enumerate(list(rows or [])):
        if current_rows:
            prev = current_rows[-1]
            if len(current_rows) >= min_rows and confirmed_cut_before_segment(prev, row, settings):
                flush()
            elif len(current_rows) >= max_rows:
                flush()
        if not current_rows:
            start_index = index
        current_rows.append(dict(row))
        current_needs.append(bool(needs_llm[index] if index < len(needs_llm) else False))
    flush()
    return groups


def _native_macro_groups(
    rows: list[dict],
    needs_llm: list[bool],
    settings: dict,
    *,
    min_rows: int,
    max_rows: int,
) -> list[dict] | None:
    if not _setting_bool(settings, "native_cpp_llm_macro_groups_enabled", False):
        return None
    if not callable(_native_llm_macro_group_ranges):
        return None
    clean_rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
    if len(clean_rows) < 2:
        return None
    needs_flags = [1 if bool(needs_llm[index] if index < len(needs_llm) else False) else 0 for index in range(len(clean_rows))]
    cut_before = [0] * len(clean_rows)
    for index in range(1, len(clean_rows)):
        if confirmed_cut_before_segment(clean_rows[index - 1], clean_rows[index], settings):
            cut_before[index] = 1
    ranges = _native_llm_macro_group_ranges(
        cut_before,
        needs_flags,
        min_rows=min_rows,
        max_rows=max_rows,
    )
    if not ranges:
        return None
    groups: list[dict] = []
    for start, end, needs_any, need_count in ranges:
        start_i = max(0, min(int(start), len(clean_rows)))
        end_i = max(start_i, min(int(end), len(clean_rows)))
        if end_i <= start_i:
            continue
        group_needs = bool(needs_any)
        group_need_count = int(need_count)
        groups.append(
            {
                "start_index": start_i,
                "rows": clean_rows[start_i:end_i],
                "needs_llm": group_needs,
                "need_count": group_need_count,
                "_native_group_policy": {
                    "schema": "ai_subtitle_studio.native_llm_macro_groups.v1",
                    "backend": "cpp",
                },
            }
        )
    return groups or None


def words_for_macro_group(rows: list[dict]) -> list[dict]:
    words: list[dict] = []
    for row in list(rows or []):
        row_words = [dict(word) for word in list(row.get("words") or []) if isinstance(word, dict)]
        if row_words:
            words.extend(row_words)
            continue
        text = str(row.get("text", "") or "").strip()
        tokens = text.split()
        if not tokens:
            continue
        start = float(row.get("start", 0.0) or 0.0)
        end = float(row.get("end", start + 0.1) or (start + 0.1))
        step = max(0.01, (end - start) / max(1, len(tokens)))
        speaker = row.get("speaker", "SPEAKER_00")
        words.extend(
            {
                "word": token,
                "start": start + index * step,
                "end": start + (index + 1) * step,
                "speaker": speaker,
            }
            for index, token in enumerate(tokens)
        )
    return words


def macro_segment_from_group(rows: list[dict]) -> dict:
    clean_rows = [dict(row) for row in list(rows or []) if isinstance(row, dict) and str(row.get("text", "") or "").strip()]
    if not clean_rows:
        return {}
    return {
        "start": float(clean_rows[0].get("start", 0.0) or 0.0),
        "end": float(clean_rows[-1].get("end", clean_rows[0].get("start", 0.0)) or clean_rows[0].get("start", 0.0) or 0.0),
        "text": " ".join(str(row.get("text", "") or "").strip() for row in clean_rows),
        "speaker": clean_rows[0].get("speaker", "SPEAKER_00"),
        "words": words_for_macro_group(clean_rows),
        "_llm_macro_source_count": len(clean_rows),
    }


def _row_text_chunks(rows: list[dict]) -> list[str]:
    chunks: list[str] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        text = re.sub(r"\s+", " ", str(row.get("text", "") or "").strip())
        if text:
            chunks.append(text)
    return chunks


def _stt_backed_rows(rows: list[dict]) -> bool:
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        if row.get("stt_candidates"):
            return True
        for key in (
            "stt_ensemble_source",
            "stt_ensemble_llm_selected_source",
            "stt_ensemble_fast_selected_source",
            "stt_selected_source",
        ):
            if str(row.get(key, "") or "").strip():
                return True
    return False


def _stt_row_locked_candidate_options(rows: list[dict]) -> list[dict]:
    chunks = _row_text_chunks(rows)
    if not chunks:
        return []
    compact_len = len(re.sub(r"\s+", "", "".join(chunks)))
    return [
        {
            "id": "STT_ROWS",
            "label": "STT1/STT2 원문 행 유지",
            "strategy": "stt_source_rows",
            "chunks": chunks,
            "chunk_count": len(chunks),
            "compact_len": compact_len,
            "lora_primary": False,
        }
    ]


def attach_macro_policy(rows: list[dict], policy: dict) -> list[dict]:
    out = []
    for row in list(rows or []):
        item = dict(row)
        item["_llm_macro_chunk_policy"] = dict(policy)
        out.append(item)
    return out


def rows_from_macro_chunks(
    macro_seg: dict,
    chunks: list[str],
    *,
    rules: dict,
    corrections: dict,
    settings: dict,
    threshold: int,
    macro_policy: dict,
    callbacks: dict[str, Any],
    base_lora_meta: dict | None = None,
) -> list[dict]:
    clean_text = callbacks["clean_text"]
    segment_lora_runtime = callbacks["segment_lora_runtime"]
    attach_lora_and_deep_timing = callbacks["attach_lora_and_deep_timing"]
    words = list(macro_seg.get("words") or [])
    spk = macro_seg.get("speaker", "SPEAKER_00")
    result: list[dict] = []
    w_idx = 0
    cur_start = float(macro_seg.get("start", 0.0) or 0.0)
    for chunk in list(chunks or []):
        chunk_clean = re.sub(r"\s+", "", str(chunk or ""))
        if not chunk_clean:
            continue
        t_start = None
        t_end = None
        matched = 0
        chunk_words = []
        while w_idx < len(words) and matched < len(chunk_clean):
            word = words[w_idx]
            wc = re.sub(r"\s+|\.", "", str(word.get("word", "") or ""))
            if t_start is None:
                t_start = float(word.get("start", cur_start) or cur_start)
            t_end = float(word.get("end", t_start or cur_start) or (t_start or cur_start))
            matched += len(wc)
            chunk_words.append(word)
            w_idx += 1
        if t_start is None:
            t_start = cur_start
        t_start = max(float(t_start), cur_start)
        if t_end is None or float(t_end) <= t_start:
            t_end = t_start + 0.1
        final_text = clean_text(str(chunk), corrections)
        if final_text:
            chunk_seg = {
                "start": t_start,
                "end": float(t_end),
                "text": final_text,
                "speaker": spk,
                "words": chunk_words,
                "_llm_macro_chunk_policy": dict(macro_policy),
            }
            chunk_settings, chunk_lora = segment_lora_runtime(chunk_seg, settings, rules, threshold)
            merged_lora = {**dict(base_lora_meta or {}), **dict(chunk_lora or {})}
            result.append(attach_lora_and_deep_timing(chunk_seg, merged_lora, chunk_settings))
        cur_start = float(t_end)
    return result


def process_llm_macro_group(
    rows: list[dict],
    *,
    rules: dict,
    threshold: int,
    corrections: dict,
    model: str,
    user_prompt: str,
    api_key: str,
    conservative: bool,
    settings: dict,
    group_index: int,
    callbacks: dict[str, Any],
) -> list[dict]:
    clean_text = callbacks["clean_text"]
    segment_lora_runtime = callbacks["segment_lora_runtime"]
    setting_int = callbacks["setting_int"]
    apply_llm_confidence_gate = callbacks["apply_llm_confidence_gate"]
    attach_lora_and_deep_timing = callbacks["attach_lora_and_deep_timing"]
    build_candidate_options = callbacks["build_llm_candidate_options"]
    ask_gemini_to_split = callbacks["ask_gemini_to_split"]
    ask_openai_to_split = callbacks["ask_openai_to_split"]
    ask_exaone_to_split = callbacks["ask_exaone_to_split"]
    is_openai_model = callbacks["is_openai_model"]
    verify_llm_chunks = callbacks["verify_llm_chunks"]
    deep_rerank_chunks = callbacks["deep_rerank_chunks"]
    llm_context_pack_for_rows = callbacks.get("llm_context_pack_for_rows")

    macro_seg = macro_segment_from_group(rows)
    if not macro_seg:
        return []
    text = clean_text(str(macro_seg.get("text", "") or ""), corrections)
    if not text:
        return attach_macro_policy(rows, {"task": "llm_macro_chunk", "llm_called": False, "reason": "empty_text"})
    macro_settings, macro_lora = segment_lora_runtime({**macro_seg, "text": text}, settings, rules, threshold)
    macro_threshold = setting_int(macro_settings, "split_length_threshold", threshold)
    duration = float(macro_seg.get("end", 0.0) or 0.0) - float(macro_seg.get("start", 0.0) or 0.0)
    should_call, macro_lora = apply_llm_confidence_gate(macro_seg, text, macro_threshold, duration, macro_settings, macro_lora)
    policy = {
        "schema": MACRO_CHUNK_POLICY_SCHEMA,
        "task": "llm_macro_chunk",
        "group_index": int(group_index),
        "source_segment_count": len(rows),
        "start": round(float(macro_seg.get("start", 0.0) or 0.0), 3),
        "end": round(float(macro_seg.get("end", 0.0) or 0.0), 3),
        "llm_called": bool(should_call),
        "reason": "gate_requested_llm" if should_call else "gate_skipped",
    }
    if not should_call:
        return attach_macro_policy(rows, policy)

    candidate_options = build_candidate_options(text, macro_threshold, rules, macro_settings)
    if _stt_backed_rows(rows):
        row_locked_options = _stt_row_locked_candidate_options(rows)
        if row_locked_options:
            candidate_options = row_locked_options
            policy["source_lock"] = "stt_rows"
    context_pack = llm_context_pack_for_rows(rows) if callable(llm_context_pack_for_rows) else None
    if "Gemini" in model:
        chunks = ask_gemini_to_split(
            text,
            macro_threshold,
            rules,
            model,
            user_prompt,
            api_key,
            conservative=conservative,
            settings=macro_settings,
            candidate_options=candidate_options,
            context_pack=context_pack,
        )
    elif is_openai_model(model):
        chunks = ask_openai_to_split(
            text,
            macro_threshold,
            rules,
            model,
            user_prompt,
            api_key,
            conservative=conservative,
            settings=macro_settings,
            candidate_options=candidate_options,
            context_pack=context_pack,
        )
    else:
        chunks = ask_exaone_to_split(
            text,
            macro_threshold,
            rules,
            model,
            user_prompt,
            conservative=conservative,
            settings=macro_settings,
            candidate_options=candidate_options,
            context_pack=context_pack,
        )
    chunks, macro_lora = verify_llm_chunks(
        text,
        chunks,
        macro_settings,
        macro_lora,
        fallback="lora_deep_prepass",
        candidate_options=candidate_options,
        context_pack=context_pack,
    )
    if not chunks:
        policy["llm_called"] = True
        policy["reason"] = "llm_rejected_keep_lora_deep_prepass"
        return attach_macro_policy(rows, policy)
    chunks, macro_lora = deep_rerank_chunks(text, chunks, macro_settings, macro_lora)
    policy["output_chunks"] = len(chunks or [])
    result = rows_from_macro_chunks(
        {**macro_seg, "text": text},
        chunks or [],
        rules=rules,
        corrections=corrections,
        settings=macro_settings,
        threshold=macro_threshold,
        macro_policy=policy,
        callbacks={
            "clean_text": clean_text,
            "segment_lora_runtime": segment_lora_runtime,
            "attach_lora_and_deep_timing": attach_lora_and_deep_timing,
        },
        base_lora_meta=macro_lora,
    )
    return result or attach_macro_policy(rows, {**policy, "reason": "empty_chunk_distribution"})


def process_llm_macro_groups(
    groups: list[dict],
    *,
    rules: dict,
    threshold: int,
    corrections: dict,
    model: str,
    user_prompt: str,
    api_key: str,
    conservative: bool,
    settings: dict,
    max_workers: int,
    callbacks: dict[str, Any],
    llm_progress_callback=None,
) -> list[dict]:
    logger = callbacks["logger"]
    emit_llm_progress = callbacks["emit_llm_progress"]
    result_map: dict[int, list[dict]] = {}
    llm_groups = [index for index, group in enumerate(groups) if group.get("needs_llm")]
    if not llm_groups:
        out: list[dict] = []
        for group in groups:
            out.extend(group.get("rows") or [])
        return out
    logger.log(
        f"[LLM-묶음처리] {len(groups)}개 묶음 중 {len(llm_groups)}개만 LLM 호출 "
        f"(묶음당 최대 {_setting_int(settings, 'subtitle_llm_macro_chunk_max_rows', 15)}문장)"
    )

    def run_group(index: int) -> list[dict]:
        group = groups[index]
        rows = [dict(row) for row in list(group.get("rows") or []) if isinstance(row, dict)]
        if not group.get("needs_llm"):
            return rows
        emit_llm_progress(
            llm_progress_callback,
            active=True,
            idx=int(group.get("start_index", index)),
            total=max(1, len(groups)),
            seg=rows[0] if rows else None,
        )
        return process_llm_macro_group(
            rows,
            rules=rules,
            threshold=threshold,
            corrections=corrections,
            model=model,
            user_prompt=user_prompt,
            api_key=api_key,
            conservative=conservative,
            settings=settings,
            group_index=index,
            callbacks=callbacks,
        )

    if max_workers <= 1 or len(groups) <= 1:
        for index in range(len(groups)):
            result_map[index] = run_group(index)
    else:
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(groups))), thread_name_prefix="llm-macro") as ex:
            futures = {ex.submit(run_group, index): index for index in range(len(groups))}
            for fut in as_completed(futures):
                index = futures[fut]
                try:
                    result_map[index] = fut.result()
                except Exception as exc:
                    logger.log(f"LLM 묶음 처리 오류: {exc}")
                    result_map[index] = [dict(row) for row in list(groups[index].get("rows") or []) if isinstance(row, dict)]

    optimized: list[dict] = []
    for index in range(len(groups)):
        optimized.extend(result_map.get(index, []))
    return optimized
