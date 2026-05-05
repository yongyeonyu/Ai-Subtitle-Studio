from __future__ import annotations

import re
from collections import Counter
from typing import Any


SCENE_KEYWORDS = {
    "car": (
        "차안",
        "차 안",
        "차량",
        "자동차",
        "시승",
        "주행",
        "운전",
        "운전석",
        "뒷좌석",
        "고속도로",
        "도로",
        "엔진",
        "트렁크",
        "실내 공간",
        "ev",
        "suv",
        "bmw",
        "benz",
        "현대",
        "기아",
    ),
    "outdoor": (
        "실외",
        "야외",
        "밖",
        "거리",
        "공원",
        "바람",
        "해변",
        "바다",
        "산",
        "캠핑",
        "산책",
        "주차장",
        "공항",
        "여행",
        "하늘",
    ),
    "indoor": (
        "실내",
        "집",
        "방",
        "사무실",
        "회의실",
        "스튜디오",
        "카페",
        "매장",
        "전시장",
        "호텔",
        "부엌",
        "주방",
        "룸",
    ),
}

TOPIC_KEYWORDS = {
    "vehicle_review": (
        "차량",
        "자동차",
        "시승",
        "리뷰",
        "주행",
        "운전",
        "엔진",
        "전기차",
        "하이브리드",
        "suv",
        "ev",
        "bmw",
        "트렁크",
        "실내 공간",
        "외관",
        "승차감",
        "연비",
    ),
    "travel": (
        "여행",
        "공항",
        "호텔",
        "숙소",
        "관광",
        "해변",
        "바다",
        "도시",
        "일정",
        "비행기",
        "기차",
        "맛집",
        "투어",
    ),
    "daily_life": (
        "일상",
        "브이로그",
        "오늘은",
        "하루",
        "집",
        "카페",
        "아침",
        "저녁",
        "친구",
        "가족",
    ),
    "tech_review": (
        "ai",
        "모델",
        "앱",
        "소프트웨어",
        "카메라",
        "마이크",
        "기기",
        "노트북",
        "폰",
        "리뷰",
        "설정",
        "업데이트",
    ),
    "food": (
        "음식",
        "맛집",
        "요리",
        "식당",
        "메뉴",
        "커피",
        "빵",
        "고기",
        "디저트",
    ),
    "tutorial": (
        "방법",
        "사용법",
        "설정",
        "튜토리얼",
        "강의",
        "설명",
        "알려드릴게요",
        "따라",
    ),
    "event": (
        "행사",
        "축제",
        "공연",
        "컨퍼런스",
        "발표",
        "무대",
        "페스티벌",
        "fest",
    ),
    "conversation": (
        "인터뷰",
        "질문",
        "대답",
        "대화",
        "이야기",
        "말씀",
        "토크",
    ),
}

NOISE_KEYWORDS = {
    "music": ("음악", "노래", "bgm", "뮤직", "공연", "박수"),
    "crowd": ("사람들", "대화", "웅성", "관중", "군중", "소리", "시장"),
    "wind": ("바람", "강풍", "야외", "실외"),
    "traffic": ("도로", "차량", "자동차", "주행", "경적", "고속도로"),
    "engine": ("엔진", "노면", "차안", "차 안", "주행음", "저역"),
    "quiet": ("조용", "정숙", "실내", "스튜디오"),
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _joined_text(values: list[Any]) -> str:
    return _normalize_text(" ".join(str(value or "") for value in values if str(value or "").strip()))


def _keyword_scores(text: str, keyword_map: dict[str, tuple[str, ...]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for label, keywords in keyword_map.items():
        score = 0.0
        evidence = set()
        for keyword in keywords:
            key = str(keyword or "").casefold()
            if not key:
                continue
            count = text.count(key)
            if count:
                evidence.add(key)
                score += count * (1.0 + min(1.0, len(key) / 8.0))
        if evidence:
            score += min(2.0, len(evidence) * 0.35)
        scores[label] = round(score, 4)
    return scores


def _top_label(scores: dict[str, float], default: str = "unknown") -> tuple[str, float]:
    if not scores:
        return default, 0.0
    label, score = max(scores.items(), key=lambda item: (float(item[1]), item[0]))
    if score <= 0:
        return default, 0.0
    total = sum(max(0.0, float(value)) for value in scores.values()) or score
    confidence = max(0.35, min(0.98, float(score) / max(1.0, total)))
    return label, round(confidence, 4)


def _keyword_evidence(text: str, keyword_map: dict[str, tuple[str, ...]], label: str, limit: int = 8) -> list[str]:
    evidence = []
    for keyword in keyword_map.get(label, ()):
        key = str(keyword or "").casefold()
        if key and key in text and key not in evidence:
            evidence.append(key)
    return evidence[:limit]


def _audio_profile_scene_hint(audio_profile: dict[str, Any]) -> str:
    env = str((audio_profile or {}).get("environment") or "").strip()
    if env in {"indoor", "outdoor", "car"}:
        return env
    return ""


def _scene_classification(text: str, audio_profile: dict[str, Any]) -> dict[str, Any]:
    scores = _keyword_scores(text, SCENE_KEYWORDS)
    env_hint = _audio_profile_scene_hint(audio_profile)
    if env_hint:
        scores[env_hint] = round(float(scores.get(env_hint, 0.0) or 0.0) + 3.5, 4)
    label, confidence = _top_label(scores)
    return {
        "label": label,
        "confidence": confidence,
        "scores": scores,
        "evidence": _keyword_evidence(text, SCENE_KEYWORDS, label),
        "source": "audio_profile+subtitle_text" if env_hint else "subtitle_text+filename",
    }


def _topic_classification(text: str) -> dict[str, Any]:
    scores = _keyword_scores(text, TOPIC_KEYWORDS)
    label, confidence = _top_label(scores)
    sorted_scores = sorted(scores.items(), key=lambda item: float(item[1]), reverse=True)
    secondary = [name for name, score in sorted_scores[1:4] if score > 0]
    return {
        "primary": label,
        "secondary": secondary,
        "confidence": confidence,
        "scores": scores,
        "evidence": _keyword_evidence(text, TOPIC_KEYWORDS, label),
    }


def _noise_sources(text: str, audio_profile: dict[str, Any]) -> list[str]:
    scores = _keyword_scores(text, NOISE_KEYWORDS)
    if bool((audio_profile or {}).get("low_rumble")):
        scores["engine"] = float(scores.get("engine", 0.0) or 0.0) + 2.0
        scores["traffic"] = float(scores.get("traffic", 0.0) or 0.0) + 1.0
    if bool((audio_profile or {}).get("quiet")):
        scores["quiet"] = float(scores.get("quiet", 0.0) or 0.0) + 2.0
    return [name for name, score in sorted(scores.items(), key=lambda item: float(item[1]), reverse=True) if score > 0][:5]


def _microphone_classification(text: str, audio_profile: dict[str, Any], media_profile: dict[str, Any]) -> dict[str, Any]:
    profile = dict(audio_profile or {})
    media_audio = dict((media_profile or {}).get("audio") or {})
    mic_present = profile.get("mic_present")
    if mic_present is None:
        # Stereo/48kHz often means camera or external recorder, but this is only a weak hint.
        sample_rate = int(media_audio.get("sample_rate", 0) or 0)
        channels = int(media_audio.get("channels", 0) or 0)
        mic_present = bool(sample_rate >= 44100 and channels >= 1) if sample_rate else None
    if mic_present is True:
        mic_type = "external_or_close"
    elif mic_present is False:
        mic_type = "builtin_or_far"
    else:
        mic_type = "unknown"

    noise_level = str(profile.get("noise_level") or "").strip()
    if not noise_level:
        sources = _noise_sources(text, profile)
        if any(item in sources for item in ("wind", "traffic", "engine", "crowd", "music")):
            noise_level = "high" if len(sources) >= 2 else "medium"
        else:
            noise_level = "unknown"
    sources = _noise_sources(text, profile)
    confidence = 0.82 if profile else (0.55 if media_audio else 0.35)
    return {
        "mic_present": mic_present,
        "mic_type": mic_type,
        "noise_level": noise_level,
        "noise_sources": sources,
        "speech_density": profile.get("speech_density"),
        "speech_confidence": profile.get("speech_confidence"),
        "low_rumble": bool(profile.get("low_rumble", "engine" in sources)),
        "quiet": bool(profile.get("quiet", "quiet" in sources)),
        "confidence": round(float(confidence), 4),
        "source": "audio_profile" if profile else "media_metadata+subtitle_text",
    }


def _training_focus(scene: str, topic: str, microphone: dict[str, Any]) -> list[str]:
    focus = ["preserve_spoken_text", "avoid_invented_context", "exclude_editorial_brackets"]
    noise_level = str(microphone.get("noise_level") or "")
    noise_sources = set(str(item) for item in list(microphone.get("noise_sources") or []))
    if scene == "car":
        focus.extend(["handle_low_rumble", "prefer_precise_stt", "protect_vehicle_terms"])
    if scene == "outdoor" or noise_level == "high":
        focus.extend(["strong_noise_reduction", "robust_vad", "short_safe_segments"])
    if "music" in noise_sources:
        focus.append("ignore_music_as_speech")
    if "crowd" in noise_sources:
        focus.append("handle_overlapping_conversation")
    if topic == "vehicle_review":
        focus.extend(["protect_brand_model_names", "protect_numbers_and_specs"])
    if topic == "travel":
        focus.extend(["protect_place_names", "preserve_narration_style"])
    if topic == "daily_life":
        focus.append("preserve_casual_speech_style")
    return list(dict.fromkeys(focus))


def _topic_terms(text: str, limit: int = 16) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_+-]*|[가-힣]{2,}", text)
    stopwords = {
        "오늘은",
        "그리고",
        "그래서",
        "이렇게",
        "저희",
        "제가",
        "있는",
        "없는",
        "합니다",
        "해요",
        "입니다",
    }
    counter = Counter(token for token in tokens if token not in stopwords)
    return [token for token, _count in counter.most_common(limit)]


def classify_lora_context(
    *,
    media_profile: dict[str, Any] | None = None,
    subtitle_profile: dict[str, Any] | None = None,
    texts: list[Any] | None = None,
    file_hints: list[Any] | None = None,
    audio_profile: dict[str, Any] | None = None,
    generation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    media_profile = dict(media_profile or {})
    subtitle_profile = dict(subtitle_profile or {})
    generation_context = dict(generation_context or {})
    merged_audio_profile = dict(audio_profile or {})
    embedded_audio_profile = dict(generation_context.get("audio_profile") or {})
    if embedded_audio_profile:
        merged_audio_profile.update(embedded_audio_profile)

    text = _joined_text(list(texts or []) + list(file_hints or []))
    scene = _scene_classification(text, merged_audio_profile)
    topic = _topic_classification(text)
    microphone = _microphone_classification(text, merged_audio_profile, media_profile)
    scene_label = str(scene.get("label") or "unknown")
    topic_label = str(topic.get("primary") or "unknown")
    return {
        "schema": "ai_subtitle_studio.lora_context_classification.v1",
        "scene_environment": scene,
        "microphone_environment": microphone,
        "topic": topic,
        "topic_terms": _topic_terms(text),
        "training_focus": _training_focus(scene_label, topic_label, microphone),
        "subtitle_density": {
            "speech_segments": int(subtitle_profile.get("speech_segments", 0) or 0),
            "excluded_parenthetical_ratio": float(subtitle_profile.get("excluded_parenthetical_ratio", 0.0) or 0.0),
            "reading_speed": dict(subtitle_profile.get("reading_speed") or {}),
        },
    }


__all__ = ["classify_lora_context"]
