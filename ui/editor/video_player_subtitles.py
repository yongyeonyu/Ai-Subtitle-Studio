from __future__ import annotations

import hashlib
import time
from bisect import bisect_right


class VideoPlayerSubtitleMixin:
    def set_subtitle_display_time(self, sec: float | None, refresh: bool = True):
        if sec is None:
            self._subtitle_display_time_sec = None
        else:
            self._subtitle_display_time_sec = self.snap_sec_to_frame(sec)
        if refresh:
            self._refresh_provider_for_subtitle_time()
            self._refresh_subtitle_now()

    def _subtitle_context_covers_time(self, sec: float) -> bool:
        if int(getattr(self, "_subtitle_count", 0) or 0) <= 0:
            return False
        starts = getattr(self, "_subtitle_starts", []) or []
        ends = getattr(self, "_subtitle_ends", []) or []
        if not starts or not ends:
            return False
        try:
            lookup = max(0.0, float(sec or 0.0))
            return float(starts[0]) - 0.001 <= lookup <= float(ends[-1]) + 0.001
        except Exception:
            return False

    def _refresh_provider_for_subtitle_time(self):
        provider = getattr(self, "_subtitle_provider", None)
        if not callable(provider):
            return
        lookup_time = self._subtitle_lookup_time()
        now = time.monotonic()
        if not self._subtitle_context_covers_time(lookup_time):
            last_force = float(getattr(self, "_last_subtitle_context_miss_force_at", 0.0) or 0.0)
            last_lookup = getattr(self, "_last_subtitle_context_miss_lookup", None)
            try:
                moved_far = last_lookup is None or abs(float(last_lookup) - lookup_time) >= 0.5
            except Exception:
                moved_far = True
            if moved_far or (now - last_force) >= 0.75:
                self._last_subtitle_context_miss_force_at = now
                self._last_subtitle_context_miss_lookup = lookup_time
                self._refresh_provider_segments(force=True)
            return
        self._refresh_provider_segments(force=False)
        if self._find_subtitle_at(lookup_time):
            return
        last_force = float(getattr(self, "_last_empty_subtitle_provider_force_at", 0.0) or 0.0)
        if (now - last_force) >= 0.75:
            self._last_empty_subtitle_provider_force_at = now
            self._refresh_provider_segments(force=True)

    def _subtitle_overlay_needs_reapply(self, text: str) -> bool:
        if not text:
            return False
        quick_overlay = getattr(self, "quick_subtitle_overlay", None)
        if quick_overlay is not None:
            try:
                if quick_overlay.text() != text:
                    return True
                return bool(quick_overlay.isHidden())
            except Exception:
                return False
        label = getattr(self, "sub_label", None)
        if label is not None:
            try:
                if label.text() != text:
                    return True
                return bool(label.isHidden())
            except Exception:
                return False
        item = self._scene_subtitle_item()
        if item is not None:
            try:
                if item.text() != text:
                    return True
                return not bool(item.isVisible())
            except Exception:
                return False
        return False

    def _refresh_subtitle_now(self):
        cur_sub = self._find_subtitle_at(self._subtitle_lookup_time())
        if cur_sub == self._last_sub and not self._subtitle_overlay_needs_reapply(cur_sub):
            return
        self._last_sub = cur_sub
        self._set_subtitle_overlay_text(cur_sub)

    @staticmethod
    def _display_text_for_video_subtitle_segment(seg) -> str:
        if not isinstance(seg, dict):
            return ""
        text = str(seg.get("text", "") or "")
        speakers = [
            str(item or "").strip()
            for item in list(seg.get("speaker_list") or [])
            if str(item or "").strip()
        ]
        if len(set(speakers)) < 2:
            return text
        lines = [line.strip() for line in text.replace("\u2028", "\n").splitlines() if line.strip()]
        if len(lines) < 2:
            return text
        if all(line.startswith("-") for line in lines[:2]):
            return "\n".join(lines)
        return "\n".join(f"- {line.lstrip('- ').strip()}" for line in lines[:2])

    @staticmethod
    def _normalize_video_subtitle_segment(seg):
        try:
            return {
                "start": float(seg.get("start", 0.0) or 0.0),
                "end": float(seg.get("end", 0.0) or 0.0),
                "text": VideoPlayerSubtitleMixin._display_text_for_video_subtitle_segment(seg),
            }
        except Exception:
            return None

    @staticmethod
    def _update_subtitle_digest(digest, start: float, end: float, text: str, speaker: str) -> None:
        digest.update(f"{start:.3f}\x1f{end:.3f}\x1f".encode("utf-8"))
        digest.update(str(text or "").encode("utf-8", errors="replace"))
        digest.update(b"\x1f")
        digest.update(str(speaker or "").encode("utf-8", errors="replace"))
        digest.update(b"\x1e")

    @staticmethod
    def _overlay_preview_row(seg) -> bool:
        if not isinstance(seg, dict):
            return False
        return bool(seg.get("_live_subtitle_preview") or seg.get("_live_stt_preview") or seg.get("stt_pending"))

    @staticmethod
    def _row_time_range(seg: dict) -> tuple[float, float] | None:
        try:
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
        except Exception:
            return None
        if end <= start:
            return None
        return start, end

    def _filter_overlay_rows(self, segments) -> list[dict]:
        rows = [seg for seg in list(segments or []) if isinstance(seg, dict)]
        if not rows:
            return []
        final_ranges = [
            rng for seg in rows
            if not self._overlay_preview_row(seg)
            for rng in [self._row_time_range(seg)]
            if rng is not None
        ]
        if not final_ranges:
            return rows
        filtered: list[dict] = []
        for seg in rows:
            if not self._overlay_preview_row(seg):
                filtered.append(seg)
                continue
            rng = self._row_time_range(seg)
            if rng is None:
                continue
            start, end = rng
            overlaps_final = any(start < f_end - 0.001 and end > f_start + 0.001 for f_start, f_end in final_ranges)
            if not overlaps_final:
                filtered.append(seg)
        return filtered

    def _segments_signature_fast(self, segments) -> str:
        digest = hashlib.sha256()
        count = 0
        for seg in (() if segments is None else segments):
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", 0.0) or 0.0)
                text = str(seg.get("text", "") or "")
                speaker = str(seg.get("speaker", seg.get("spk", "")) or "")
            except Exception:
                continue
            self._update_subtitle_digest(digest, start, end, text, speaker)
            count += 1
        digest.update(f"count:{count}".encode("ascii"))
        return digest.hexdigest()

    def _normalized_segments_context(self, segments, *, signature_override: str | None = None):
        cleaned = []
        starts = []
        ends = []
        texts = []
        digest = None if signature_override is not None else hashlib.sha256()
        sorted_ok = True
        prev_start = None
        count = 0
        source = self._filter_overlay_rows(segments)
        for seg in source:
            item = self._normalize_video_subtitle_segment(seg)
            if item is None:
                continue
            start = float(item["start"])
            end = float(item["end"])
            if prev_start is not None and start < prev_start:
                sorted_ok = False
            prev_start = start
            cleaned.append(item)
            starts.append(start)
            ends.append(end)
            texts.append(item["text"])
            count += 1
            if digest is not None:
                speaker = str(seg.get("speaker", seg.get("spk", "")) or "")
                self._update_subtitle_digest(digest, start, end, item["text"], speaker)
        signature = str(signature_override or "")
        if digest is not None:
            digest.update(f"count:{count}".encode("ascii"))
            signature = digest.hexdigest()
        return cleaned, signature, sorted_ok, starts, ends, texts

    def _normalized_segments_and_signature(self, segments):
        cleaned, signature, sorted_ok, _starts, _ends, _texts = self._normalized_segments_context(segments)
        return cleaned, signature, sorted_ok

    @staticmethod
    def _adopt_list_buffer(values):
        return values if isinstance(values, list) else list(values or [])

    def _set_segments(
        self,
        segments,
        *,
        normalized=None,
        signature: str | None = None,
        sorted_ok: bool | None = None,
        starts=None,
        ends=None,
        texts=None,
    ):
        if normalized is None or signature is None or sorted_ok is None:
            existing_signature = str(getattr(self, "_context_segments_signature", "") or "")
            if existing_signature:
                signature = self._segments_signature_fast(segments or [])
                if signature == existing_signature:
                    self._context_segments_ref = segments
                    return False
                cleaned, signature, sorted_ok, starts, ends, texts = self._normalized_segments_context(
                    segments or [],
                    signature_override=signature,
                )
            else:
                cleaned, signature, sorted_ok, starts, ends, texts = self._normalized_segments_context(segments or [])
        else:
            cleaned = self._adopt_list_buffer(normalized)
        if signature and signature == getattr(self, "_context_segments_signature", ""):
            self._context_segments_ref = segments
            return False
        self.segments = cleaned if sorted_ok else sorted(cleaned, key=lambda s: s["start"])
        if sorted_ok and starts is not None and ends is not None and texts is not None:
            self._subtitle_starts = self._adopt_list_buffer(starts)
            self._subtitle_ends = self._adopt_list_buffer(ends)
            self._subtitle_texts = self._adopt_list_buffer(texts)
        else:
            self._subtitle_starts = [s["start"] for s in self.segments]
            self._subtitle_ends = [s["end"] for s in self.segments]
            self._subtitle_texts = [s["text"] for s in self.segments]
        self._subtitle_count = len(self._subtitle_starts)
        self._subtitle_cache_idx = -1
        self._context_segments_ref = segments
        self._context_segments_signature = signature
        return True

    def set_subtitle_provider(self, provider):
        self._subtitle_provider = provider
        self._provider_refresh_requested = True
        self._refresh_provider_segments(force=True)

    def apply_export_subtitle_style(self, style: dict | None):
        self._set_subtitle_overlay_style(style or {})
        self._refresh_provider_segments(force=True)
        self._refresh_subtitle_now()
        try:
            self.sub_label.update()
        except Exception:
            pass

    def _refresh_provider_segments(self, force: bool = False):
        provider = getattr(self, "_subtitle_provider", None)
        if not callable(provider):
            return
        now = time.monotonic()
        if not force and (now - float(getattr(self, "_last_provider_refresh_at", 0.0) or 0.0)) < 0.50:
            return
        self._last_provider_refresh_at = now
        try:
            segments = provider()
        except Exception:
            return
        if segments is None:
            return
        if not force and getattr(self, "_subtitle_provider_signature", ""):
            signature = self._segments_signature_fast(segments)
            if signature == getattr(self, "_subtitle_provider_signature", ""):
                self._subtitle_provider_segments_ref = segments
                self._provider_refresh_requested = False
                return
        cleaned, signature, sorted_ok, starts, ends, texts = self._normalized_segments_context(
            segments,
            signature_override=signature if not force and signature else None,
        )
        if signature and signature == getattr(self, "_subtitle_provider_signature", ""):
            self._subtitle_provider_segments_ref = segments
            self._provider_refresh_requested = False
            return
        self._subtitle_provider_segments_ref = segments
        self._subtitle_provider_signature = signature
        self._set_segments(
            segments,
            normalized=cleaned,
            signature=signature,
            sorted_ok=sorted_ok,
            starts=starts,
            ends=ends,
            texts=texts,
        )
        self._provider_refresh_requested = False
        self._refresh_subtitle_now()

    def _segments_signature(self, segments: list[dict]) -> str:
        _cleaned, signature, _sorted_ok = self._normalized_segments_and_signature(segments or [])
        return signature

    def _find_subtitle_at(self, now: float) -> str:
        idx = int(self._subtitle_cache_idx)
        starts = self._subtitle_starts
        ends = self._subtitle_ends
        texts = self._subtitle_texts
        count = int(self._subtitle_count)
        if 0 <= idx < count:
            if starts[idx] <= now < ends[idx]:
                return texts[idx]
            next_idx = idx + 1
            if next_idx < count:
                if starts[next_idx] <= now < ends[next_idx]:
                    self._subtitle_cache_idx = idx + 1
                    return texts[next_idx]

        idx = bisect_right(starts, now) - 1
        self._subtitle_cache_idx = idx
        if 0 <= idx < count:
            if starts[idx] <= now < ends[idx]:
                return texts[idx]
        return ""

    def set_context_segments(self, segments: list[dict] | None = None):
        self._set_segments(segments or [])
        self._refresh_subtitle_now()

    def refresh_subtitle_context(self, segments: list[dict] | None = None):
        if segments is not None:
            self._set_segments(segments)
        self._refresh_subtitle_now()
