from __future__ import annotations

from pathlib import Path

from core.engine.subtitle_dictionary import (
    SUBTITLE_DICTIONARY_LOOKUP_SCHEMA,
    SUBTITLE_DICTIONARY_UPDATE_SCHEMA,
    build_subtitle_dictionary_lookup_request,
    build_subtitle_dictionary_text_update,
    compact_subtitle_dictionary_text,
    remove_subtitle_dictionary_wrong_phrases,
)
from core.subtitle_quality.candidate_generator import generate_quality_candidates
from core.subtitle_quality.correction_memory import add_correction_memory_item
from core.subtitle_quality.wrong_answer_memory import add_wrong_answer_memory_item


def test_dictionary_lookup_request_preserves_settings_and_paths(tmp_path: Path):
    correction_path = tmp_path / "correction.json"
    wrong_path = tmp_path / "wrong.json"

    request = build_subtitle_dictionary_lookup_request(
        " hello ",
        settings={
            "correction_memory_enabled": "off",
            "wrong_answer_memory_enabled": "on",
            "dictionary_memory_lookup_limit": "7",
            "correction_memory_min_confidence": "0.65",
        },
        context={
            "correction_memory_path": correction_path,
            "wrong_answer_memory_path": wrong_path,
        },
    )

    payload = request.to_dict()
    assert payload["schema"] == SUBTITLE_DICTIONARY_LOOKUP_SCHEMA
    assert payload["text"] == " hello "
    assert payload["correction_enabled"] is False
    assert payload["wrong_answer_enabled"] is True
    assert payload["correction_memory_path"] == str(correction_path)
    assert payload["wrong_answer_memory_path"] == str(wrong_path)
    assert payload["limit"] == 7
    assert payload["min_confidence"] == 0.65


def test_dictionary_update_result_keeps_immutable_before_after_snapshot():
    applied = [{"original": "abc", "corrected": "ABC"}]
    update = build_subtitle_dictionary_text_update(
        source="correction_memory",
        before_text="abc def",
        after_text="ABC def",
        applied_items=applied,
    )
    applied[0]["corrected"] = "mutated"

    payload = update.to_dict()
    assert payload["schema"] == SUBTITLE_DICTIONARY_UPDATE_SCHEMA
    assert payload["changed"] is True
    assert payload["before_text"] == "abc def"
    assert payload["after_text"] == "ABC def"
    assert payload["applied_items"][0]["corrected"] == "ABC"


def test_wrong_answer_phrase_removal_prefers_longer_phrases():
    cleaned, applied = remove_subtitle_dictionary_wrong_phrases(
        "hello bad phrase world",
        [
            {"phrase": "bad"},
            {"phrase": "bad phrase"},
        ],
    )

    assert cleaned == "hello world"
    assert [item["phrase"] for item in applied] == ["bad phrase"]


def test_quality_candidate_generator_uses_dictionary_facade_metadata(tmp_path: Path):
    correction_path = tmp_path / "correction_memory.json"
    wrong_path = tmp_path / "wrong_answer_memory.json"
    add_correction_memory_item("소설가유모씨", "u_mo_c", path=correction_path, source="unit")
    add_wrong_answer_memory_item("Thank you for watching", path=wrong_path, context="silent")

    correction_candidates = generate_quality_candidates(
        {"line": 3, "start": 0.0, "end": 1.0, "text": "소설가유모씨입니다"},
        context={"correction_memory_path": correction_path, "wrong_answer_memory_path": wrong_path},
    )
    wrong_candidates = generate_quality_candidates(
        {"line": 4, "start": 0.0, "end": 1.0, "text": "Thank you for watching 지금"},
        context={"correction_memory_path": correction_path, "wrong_answer_memory_path": wrong_path},
    )

    correction = next(item for item in correction_candidates if item["candidate_id"] == "correction_memory")
    wrong = next(item for item in wrong_candidates if item["candidate_id"] == "wrong_answer_memory_remove")
    assert correction["text"] == "u_mo_c입니다"
    assert correction["metadata"]["dictionary_update"]["before_text"] == "소설가유모씨입니다"
    assert correction["metadata"]["dictionary_update"]["after_text"] == "u_mo_c입니다"
    assert wrong["text"] == "지금"
    assert wrong["metadata"]["dictionary_update"]["source"] == "wrong_answer_memory"


def test_compact_dictionary_text_ignores_spacing_only_changes():
    assert compact_subtitle_dictionary_text("a b\nc") == compact_subtitle_dictionary_text("abc")
