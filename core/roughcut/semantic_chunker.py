# Version: 03.00.00
# Phase: PHASE2
from __future__ import annotations

from typing import Iterable

from .models import ChapterMetadata, PackedPhrase, SemanticChunk
from .topic_detector import extract_keywords, topic_shift_score


def _snippet(text: str, limit: int = 80) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."


def _make_chunk(index: int, phrases: list[PackedPhrase], shift_score: float = 0.0) -> SemanticChunk:
    text = " ".join(phrase.text for phrase in phrases).strip()
    keywords = extract_keywords(text, top_k=8)
    title = " / ".join(keywords[:3]) if keywords else f"Chunk {index}"
    source_indices: list[int] = []
    for phrase in phrases:
        source_indices.extend(phrase.source_indices)
    return SemanticChunk(
        chunk_id=f"chunk_{index:04d}",
        start=phrases[0].start,
        end=phrases[-1].end,
        phrase_ids=tuple(phrase.phrase_id for phrase in phrases),
        source_indices=tuple(source_indices),
        text=text,
        keywords=keywords,
        topic_shift_score=shift_score,
        title=title,
        summary=_snippet(text, limit=120),
    )


def _merge_short_chunks(chunks: list[SemanticChunk], min_chunk_duration: float) -> list[SemanticChunk]:
    minimum = max(0.0, float(min_chunk_duration))
    if minimum <= 0.0 or len(chunks) <= 1:
        return chunks

    merged: list[SemanticChunk] = []
    carry: list[SemanticChunk] = []

    def flush_carry() -> None:
        nonlocal carry
        if not carry:
            return
        text = " ".join(chunk.text for chunk in carry).strip()
        keywords = extract_keywords(text, top_k=8)
        phrase_ids: list[str] = []
        source_indices: list[int] = []
        for chunk in carry:
            phrase_ids.extend(chunk.phrase_ids)
            source_indices.extend(chunk.source_indices)
        merged.append(
            SemanticChunk(
                chunk_id=f"chunk_{len(merged) + 1:04d}",
                start=carry[0].start,
                end=carry[-1].end,
                phrase_ids=tuple(phrase_ids),
                source_indices=tuple(source_indices),
                text=text,
                keywords=keywords,
                topic_shift_score=max(chunk.topic_shift_score for chunk in carry),
                title=" / ".join(keywords[:3]) if keywords else f"Chunk {len(merged) + 1}",
                summary=_snippet(text, limit=120),
            )
        )
        carry = []

    for chunk in chunks:
        carry.append(chunk)
        if sum(item.duration for item in carry) >= minimum:
            flush_carry()

    if carry:
        if merged:
            previous = merged.pop()
            carry.insert(0, previous)
        flush_carry()

    return merged


def build_semantic_chunks(
    phrases: Iterable[PackedPhrase],
    topic_shift_threshold: float = 0.55,
    max_chunk_duration: float = 180.0,
    min_chunk_duration: float = 15.0,
) -> list[SemanticChunk]:
    ordered = sorted(phrases, key=lambda phrase: (phrase.start, phrase.end))
    if not ordered:
        return []

    threshold = max(0.0, min(1.0, float(topic_shift_threshold)))
    max_duration = max(1.0, float(max_chunk_duration))

    chunks: list[SemanticChunk] = []
    current: list[PackedPhrase] = []
    pending_shift_score = 0.0

    for phrase in ordered:
        if not current:
            current.append(phrase)
            continue

        score = topic_shift_score(current[-1].text, phrase.text)
        exceeds_duration = phrase.end - current[0].start > max_duration
        if score >= threshold or exceeds_duration:
            chunks.append(_make_chunk(len(chunks) + 1, current, shift_score=pending_shift_score))
            current = [phrase]
            pending_shift_score = score
        else:
            current.append(phrase)
            pending_shift_score = max(pending_shift_score, score)

    if current:
        chunks.append(_make_chunk(len(chunks) + 1, current, shift_score=pending_shift_score))

    return _merge_short_chunks(chunks, min_chunk_duration=min_chunk_duration)


def chunks_to_chapters(chunks: Iterable[SemanticChunk]) -> list[ChapterMetadata]:
    chapters: list[ChapterMetadata] = []
    for index, chunk in enumerate(chunks, start=1):
        chapters.append(
            ChapterMetadata(
                chapter_id=f"chapter_{index:04d}",
                title=chunk.title or f"Chapter {index}",
                start=chunk.start,
                end=chunk.end,
                summary=chunk.summary,
                tags=chunk.keywords,
                segment_ids=(chunk.chunk_id,),
                importance_score=0.5,
                narrative_function="roughcut_seed",
                needs_review=chunk.topic_shift_score < 0.25,
            )
        )
    return chapters
