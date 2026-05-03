# Version: 03.10.02
# Phase: PHASE2
"""
ui/editor_segments.py
EditorWidget의 자막 에디터 조작, 큐 처리, 세그먼트 I/O 메서드 모음.
[수정] core 폴더 이동에 따른 데이터 매니저 경로 및 상대 경로 최적화 완료
"""
import hashlib, json, re, os, threading, time
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor

from logger import get_logger

# 💡 [경로 수정] editor_data_manager -> core.data_manager
from core.project.data_manager import save_correction as _dm_save_correction

# 수정 — 절대 import로 통일 (editor_widget.py, editor_timeline_video.py와 동일)
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_helpers import get_sub_block_indices

class EditorSegmentsMixin:
    """자막 에디터 조작 / 큐 처리 / 세그먼트 I/O"""
    # ---------------------------------------------------------
    # Common Helpers (여러 Mixin에서 공용)
    # ---------------------------------------------------------
    def _frame_time(self, sec: float) -> float:
        if hasattr(self, "_snap_to_frame"):
            return self._snap_to_frame(sec)
        return round(float(sec), 6)

    def _mark_dirty(self):
        if hasattr(self, "_has_unsaved_changes") and not self._has_unsaved_changes():
            return
        if hasattr(self, "sm"):
            if hasattr(self.sm, "start_editing") and not getattr(self.sm, "is_locked", False):
                self.sm.start_editing()
            else:
                self.sm.is_dirty = True
        else:
            self._is_dirty = True
        try:
            main_w = self.window()
            if hasattr(main_w, "_refresh_saved_status_label"):
                main_w._refresh_saved_status_label(is_dirty=True)
        except Exception:
            pass

    def _finalize_edit(self):
        self.text_edit.update_margins()
        if hasattr(self.text_edit, 'timestampArea'):
            self.text_edit.timestampArea.update()
        self._schedule_timeline()

    def _segment_quality_signature(self, seg: dict) -> str:
        payload = {
            "start": round(float(seg.get("start", 0.0) or 0.0), 3),
            "end": round(float(seg.get("end", seg.get("start", 0.0)) or 0.0), 3),
            "text": str(seg.get("text", "") or ""),
            "speaker": str(seg.get("speaker", seg.get("spk", "")) or ""),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _quality_kwargs_from_segment(self, seg: dict, *, signature: str | None = None) -> dict:
        quality = dict(seg.get("quality") or {})
        history = list(seg.get("quality_history") or [])
        candidates = list(seg.get("quality_candidates") or [])
        return {
            "quality": quality,
            "quality_history": history,
            "quality_candidates": candidates,
            "quality_signature": signature or str(seg.get("quality_signature", "") or ""),
        }

    def _quality_tooltip(self, seg: dict) -> str:
        quality = dict(seg.get("quality") or {})
        if not quality:
            return ""
        score = quality.get("confidence_score")
        label = str(quality.get("confidence_label") or "gray")
        reason = str(quality.get("confidence_reason") or "")
        flags = ", ".join(str(flag) for flag in (quality.get("flags") or ())[:6])
        candidates = len(seg.get("quality_candidates") or [])
        stale = " / stale" if seg.get("quality_stale") else ""
        score_text = "-" if score is None else f"{float(score):.1f}"
        return f"품질 {label}{stale} · {score_text}점\n사유: {reason or flags or 'ok'}\n후보: {candidates}개"

    # ---------------------------------------------------------
    # Segment Queue
    # ---------------------------------------------------------
    def preview_stt_segments(self, segments: list[dict]):
        try:
            if hasattr(self, "status_lbl"):
                self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda s=list(segments): self.preview_stt_segments(s))
            return

        preview = []
        for seg in segments or []:
            try:
                start = self._frame_time(max(0.0, float(seg.get("start", 0.0) or 0.0)))
                end = self._frame_time(max(start + 0.05, float(seg.get("end", start + 0.5) or start + 0.5)))
            except Exception:
                continue
            text = str(seg.get("text", "") or "").strip()
            if not text:
                continue
            item = dict(seg)
            item["start"] = start
            item["end"] = end
            item["text"] = text
            item["stt_preview_source"] = str(
                seg.get("stt_preview_source")
                or seg.get("stt_source")
                or seg.get("stt_ensemble_source")
                or "STT1"
            )
            item["stt_pending"] = True
            item["_live_stt_preview"] = True
            preview.append(item)

        if not preview:
            return

        existing_preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        existing_preview = self._drop_overlapping_preview(existing_preview, preview, same_source_only=True)
        self._live_stt_preview_segments = existing_preview + preview
        self._redraw_timeline_with_live_preview()

    def _drop_overlapping_preview(self, preview: list[dict], final_segments: list[dict], *, same_source_only: bool = False) -> list[dict]:
        if not preview or not final_segments:
            return list(preview or [])
        ranges = []
        for seg in final_segments or []:
            try:
                ranges.append((
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", 0.0) or 0.0),
                    str(seg.get("stt_preview_source") or seg.get("stt_source") or "").upper(),
                ))
            except Exception:
                continue
        if not ranges:
            return list(preview or [])

        kept = []
        for seg in preview:
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
                source = str(seg.get("stt_preview_source") or seg.get("stt_source") or "").upper()
            except Exception:
                continue
            overlaps = any(
                (not same_source_only or not r_source or not source or r_source == source)
                and start < r_end + 0.05
                and end > r_start - 0.05
                for r_start, r_end, r_source in ranges
            )
            if not overlaps:
                kept.append(seg)
        return kept

    def _stt_candidate_source(self, seg: dict) -> str:
        source = (
            seg.get("stt_preview_source")
            or seg.get("stt_source")
            or seg.get("stt_ensemble_source")
            or "STT1"
        )
        return str(source or "STT1").strip().upper()

    def _segment_overlap_ratio(self, left: dict, right: dict) -> float:
        try:
            l_start = float(left.get("start", 0.0) or 0.0)
            l_end = float(left.get("end", l_start) or l_start)
            r_start = float(right.get("start", 0.0) or 0.0)
            r_end = float(right.get("end", r_start) or r_start)
        except Exception:
            return 0.0
        overlap = max(0.0, min(l_end, r_end) - max(l_start, r_start))
        base = max(0.001, min(max(0.001, l_end - l_start), max(0.001, r_end - r_start)))
        return overlap / base

    def _segment_overlaps_time_range(self, seg: dict, start: float, end: float, pad: float = 0.001) -> bool:
        try:
            seg_start = float(seg.get("start", 0.0) or 0.0)
            seg_end = float(seg.get("end", seg_start) or seg_start)
        except Exception:
            return False
        return seg_start < end - pad and seg_end > start + pad

    def _trim_final_segments_around_candidate(self, segments: list[dict], candidate: dict) -> list[dict]:
        try:
            cand_start = self._frame_time(float(candidate.get("start", 0.0) or 0.0))
            cand_end = self._frame_time(float(candidate.get("end", cand_start) or cand_start))
        except Exception:
            return list(segments or [])
        min_keep = max(0.08, float(getattr(self, "video_fps", 30.0) and (2.0 / max(1.0, float(getattr(self, "video_fps", 30.0) or 30.0)))))
        trimmed: list[dict] = []
        for seg in segments or []:
            try:
                start = self._frame_time(float(seg.get("start", 0.0) or 0.0))
                end = self._frame_time(float(seg.get("end", start) or start))
            except Exception:
                continue
            if not self._segment_overlaps_time_range(seg, cand_start, cand_end):
                trimmed.append(dict(seg))
                continue
            if start < cand_start and cand_start - start >= min_keep:
                left = dict(seg)
                left["start"] = start
                left["end"] = self._frame_time(cand_start)
                trimmed.append(left)
            if cand_end < end and end - cand_end >= min_keep:
                right = dict(seg)
                right["start"] = self._frame_time(cand_end)
                right["end"] = end
                trimmed.append(right)
        return trimmed

    def _final_segment_from_stt_candidate(self, candidate: dict) -> dict:
        source = self._stt_candidate_source(candidate)
        start = self._frame_time(max(0.0, float(candidate.get("start", 0.0) or 0.0)))
        end = self._frame_time(max(start + 0.05, float(candidate.get("end", start + 0.5) or start + 0.5)))
        text = str(candidate.get("text", "") or "").strip()
        seg = {
            "start": start,
            "end": end,
            "text": text,
            "speaker": str(candidate.get("speaker", candidate.get("spk", "00")) or "00"),
            "stt_selected_source": source,
            "quality": {
                "confidence_label": "green",
                "confidence_reason": f"{source} 후보 수동 확정",
                "manual_confirmed": True,
                "flags": ["manual_confirmed", "stt_candidate_selected"],
            },
        }
        for key in ("_clip_idx", "_clip_file"):
            if key in candidate:
                seg[key] = candidate[key]
        return seg

    def select_stt_candidate_as_subtitle(self, candidate: dict):
        try:
            if hasattr(self, "status_lbl"):
                self.status_lbl.text()
        except RuntimeError:
            return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda c=dict(candidate): self.select_stt_candidate_as_subtitle(c))
            return
        if not candidate:
            return

        # ---------------------------------------------------------
        # 1. 튕김 방지: 현재 스크롤 및 플레이헤드 위치 캡처
        # ---------------------------------------------------------
        saved_sec = None
        saved_h_scroll = None
        saved_v_scroll = 0
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            try:
                saved_sec = float(getattr(self.timeline.canvas, "playhead_sec", 0.0) or 0.0)
            except Exception:
                saved_sec = None
            try:
                saved_h_scroll = int(self.timeline.scroll.horizontalScrollBar().value())
            except Exception:
                saved_h_scroll = None
        if hasattr(self, "text_edit"):
            saved_v_scroll = self.text_edit.verticalScrollBar().value()

        try:
            if hasattr(self, "_undo_mgr"):
                self._undo_mgr.push_immediate()
        except Exception:
            pass

        current = [dict(seg) for seg in self._get_current_segments() if not seg.get("is_gap")]
        
        # ---------------------------------------------------------
        # 2. 클릭한 후보 정보 추출
        # ---------------------------------------------------------
        cand_text = str(candidate.get("text", "")).strip()
        cand_start = float(candidate.get("start", 0.0) or 0.0)
        cand_end = float(candidate.get("end", 0.0) or 0.0)
        
        cand_source = ""
        if hasattr(self, "_stt_candidate_source"):
            cand_source = self._stt_candidate_source(candidate)
        else:
            cand_source = str(candidate.get("stt_preview_source") or candidate.get("stt_source") or candidate.get("stt_ensemble_source") or "").strip().upper()

        if not cand_text or not cand_source:
            return

        # ---------------------------------------------------------
        # 3. 겹치는 최종 자막을 후보 경계 기준으로 잘라내고 새 확정 자막 삽입
        # ---------------------------------------------------------
        current = self._trim_final_segments_around_candidate(current, candidate)
        current.append(self._final_segment_from_stt_candidate(candidate))
        current.sort(key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))

        # ---------------------------------------------------------
        # 4. 화면 반영 및 위치 복원
        # ---------------------------------------------------------
        for line, seg in enumerate(current):
            seg["line"] = line

        if hasattr(self, "text_edit"):
            self.text_edit.blockSignals(True)

        if hasattr(self, "_reload_segments_from_list"):
            self._reload_segments_from_list(current, preserve_view=True)
            self._update_timeline_with_confirmed_and_preview(current)
        else:
            self._cached_segs = current
            if hasattr(self, "reload_segments"):
                self.reload_segments()

        if hasattr(self, "text_edit"):
            self.text_edit.blockSignals(False)
            self.text_edit.verticalScrollBar().setValue(saved_v_scroll)
        if hasattr(self, "timeline"):
            try:
                if saved_sec is not None and hasattr(self.timeline, "set_playhead"):
                    self.timeline.set_playhead(saved_sec, preserve_center_lock=True)
                if saved_h_scroll is not None:
                    self.timeline.scroll.horizontalScrollBar().setValue(int(saved_h_scroll))
            except Exception:
                pass
    def _update_timeline_with_confirmed_and_preview(self, confirmed_segments: list[dict]):
        if not hasattr(self, "timeline"):
            return
        confirmed = [seg for seg in list(confirmed_segments or []) if not seg.get("is_gap")]
        preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        combined = sorted(
            confirmed + preview,
            key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
        )
        total_dur = combined[-1]["end"] if combined else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(combined, self._active_seg_start, total_dur)

    def _redraw_timeline_with_live_preview(self):
        if not hasattr(self, "timeline"):
            return
        try:
            confirmed = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
        except Exception:
            confirmed = list(getattr(self, "_cached_segs", []) or [])
        preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        if not preview:
            self._redraw_timeline()
            return
        combined = sorted(confirmed + preview, key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))
        total_dur = combined[-1]["end"] if combined else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(combined, self._active_seg_start, total_dur)

    def append_segments(self, segments: list[dict]):
        try: self.status_lbl.text()
        except RuntimeError: return
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda s=list(segments): self.append_segments(s))
            return
        self._segment_queue.extend(segments)
        if not self._queue_timer.isActive():
            self._queue_timer.start(80)

    def _flush_queue(self):
        try: self.text_edit.toPlainText()
        except RuntimeError: return

        if not self._segment_queue:
            return

        cont_thresh = float(self.settings.get("continuous_threshold", 2.0))
        pull_rate = float(self.settings.get("gap_pull_rate", 0.3))
        push_rate = float(self.settings.get("gap_push_rate", 0.7))
        single_ext = float(self.settings.get("single_subtitle_end", 0.2))
        is_initial = getattr(self, '_is_initial_load', False)
        final_gap_ready = bool(self._segment_queue) and all(
            bool(seg.get("_final_gap_settings_applied")) for seg in self._segment_queue
        )

        doc = self.text_edit.document()
        orig_cursor = self.text_edit.textCursor()
        is_at_bottom = (orig_cursor.position() >= doc.characterCount() - 5)

        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.End)

        # 💡 1. [핵심 버그 수정] 꼬리(Gap)를 지우기 전에 이전 자막의 끝 시간을 미리 확보!
        prev_end_orig = -1.0
        has_prev_gap = False
        
        if not is_initial and doc.blockCount() > 0:
            lb = doc.lastBlock()
            ud = lb.userData()
            # 마지막 줄이 빈 줄(Gap)이라면 순수한 끝 시간을 기억합니다.
            if not lb.text().strip() and isinstance(ud, SubtitleBlockData) and ud.is_gap:
                has_prev_gap = True
                prev_end_orig = max(0.0, ud.start_sec - single_ext)

        # 💡 2. 꼬리 지우기 (여기서 기존 Gap 블록이 화면에서 정리됨)
        while doc.blockCount() > 0:
            last_block = doc.lastBlock(); last_text = last_block.text()
            if not last_text.strip():
                cur.setPosition(last_block.position())
                cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cur.removeSelectedText()
                if doc.blockCount() > 1: cur.deletePreviousChar()
                else: break
            else: break

        cur.movePosition(QTextCursor.MoveOperation.End)

        # 💡 3. [핵심 로직 복구] 삭제된 Gap 정보를 바탕으로 대표님이 설정한 미루기/당기기 비율 적용!
        if has_prev_gap and self._segment_queue and not is_initial:
            curr_start = self._segment_queue[0]['start']
            gap = curr_start - prev_end_orig
            
            if 0 < gap <= cont_thresh:
                new_prev_end = prev_end_orig + gap * push_rate
                # 🎯 드디어 대표님이 설정한 '당기기' 비율만큼 자막 시작 시간이 앞당겨집니다!
                self._segment_queue[0]['start'] = prev_end_orig + gap - (gap * pull_rate)
                
                # 당기고 남은 빈 공간이 있다면 다시 Gap 블록 재생성
                if self._segment_queue[0]['start'] > new_prev_end + 0.05:
                    if doc.lastBlock().text().strip(): cur.insertText("\n")
                    cur.insertText("\n")
                    cur.block().setUserData(SubtitleBlockData("00", self._frame_time(new_prev_end), is_gap=True))
                    cur.insertText("\n") # 다음 자막이 쓸 줄 확보
                    
            elif gap > cont_thresh:
                new_prev_end = prev_end_orig + single_ext
                self._segment_queue[0]['start'] = max(0.0, curr_start - single_ext)
                if self._segment_queue[0]['start'] > new_prev_end + 0.05:
                    if doc.lastBlock().text().strip(): cur.insertText("\n")
                    cur.insertText("\n")
                    cur.block().setUserData(SubtitleBlockData("00", self._frame_time(new_prev_end), is_gap=True))
                    cur.insertText("\n")

        # 💡 4. 내부 청크들 간의 간격 연산
        last_end = -1.0
        for i in range(len(self._segment_queue)):
            curr = self._segment_queue[i]
            
            if not is_initial and not final_gap_ready:
                if curr['start'] < last_end: curr['start'] = last_end
                
                if i + 1 < len(self._segment_queue):
                    nxt = self._segment_queue[i+1]
                    gap = nxt['start'] - curr['end']
                    if 0 < gap <= cont_thresh:
                        curr['end'] += gap * push_rate
                        nxt['start'] -= gap * pull_rate
                    elif gap > cont_thresh:
                        curr['end'] += min(single_ext, gap / 2.0)
                        nxt['start'] -= min(single_ext, gap / 2.0)
                else: 
                    curr['end'] += single_ext
            elif curr['end'] <= curr['start']:
                curr['end'] = curr['start'] + 0.5
                    
            last_end = curr['end']

        if doc.lastBlock().text().strip(): cur.insertText("\n")
        added_end = self._segment_queue[-1]['end'] if self._segment_queue else 0.0

        # 💡 [여기서부터 수정: 화자 분리 로직]
        spk1_id = self.settings.get("spk1_id", "00")
        spk2_id = self.settings.get("spk2_id", "01")

        for i in range(len(self._segment_queue)):
            seg = self._segment_queue[i]; text = str(seg.get("text", "") or "").replace("\u2028", "\n")
            spk_list = seg.get("speaker_list", [spk1_id])
            
            text = self._JUNK_TS_RE.sub('', text)
            text = self._JUNK_NO_BRACKET_3PART.sub('', text)
            text = self._JUNK_NO_BRACKET_3PART_END.sub('', text)
            text = self._JUNK_START_RE.sub('', text).strip()
            text = text.replace('\r', '')
            # ✅ HTML 태그 제거
            text = re.sub(r'<[^>]+>', '', text)

            parts = [re.sub(r'[ \t\f\v]+', ' ', p).strip() for p in text.split('\n')]
            parts = [p for p in parts if p]
            if not parts: continue
            
            start_sec = self._frame_time(max(0, seg.get("start", 0)))
            
            # 💡 첫 번째 줄 삽입
            current_spk = spk_list[0] if len(spk_list) > 0 else spk1_id
            stt_kwargs = {
                "stt_mode": bool(seg.get("stt_mode", False)),
                "stt_pending": bool(seg.get("stt_pending", False)),
                "original_text": str(seg.get("original_text", "") or ""),
                "dictated_text": str(seg.get("dictated_text", "") or ""),
                "stt_selected_source": str(seg.get("stt_selected_source", "") or ""),
                "stt_ensemble_llm_selected_source": str(seg.get("stt_ensemble_llm_selected_source", "") or ""),
                "stt_candidates": list(seg.get("stt_candidates") or []),
                "stt_ensemble_source": str(seg.get("stt_ensemble_source", "") or ""),
                "stt_ensemble_llm_selected_label": str(seg.get("stt_ensemble_llm_selected_label", "") or ""),
                "stt_ensemble_similarity": seg.get("stt_ensemble_similarity"),
                "stt_ensemble_needs_llm_review": bool(seg.get("stt_ensemble_needs_llm_review", False)),
                "stt_ensemble_inserted_from_stt2": bool(seg.get("stt_ensemble_inserted_from_stt2", False)),
                "stt_ensemble_word_rover": dict(seg.get("stt_ensemble_word_rover") or {}),
            }
            clip_idx = seg.get("_clip_idx")
            try:
                clip_idx = int(clip_idx) if clip_idx is not None else None
            except Exception:
                clip_idx = None
            clip_kwargs = {
                "clip_idx": clip_idx,
                "clip_file": str(seg.get("_clip_file", "") or ""),
            }
            quality_kwargs = self._quality_kwargs_from_segment(seg, signature=self._segment_quality_signature({
                "start": start_sec,
                "end": seg.get("end", start_sec),
                "text": parts[0],
                "speaker": current_spk,
            }))
            cur.insertText(parts[0])
            cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
            
            # 💡 두 번째 줄부터의 처리 (- 기호 유무로 완벽 통제)
            for p_idx in range(1, len(parts)):
                line_text = parts[p_idx]
                
                if line_text.startswith('-'):
                    # 🚨 '-' 기호가 있으면: 진짜 엔터(\n)를 쳐서 블록을 나누고 화자를 교체합니다.
                    current_spk = spk2_id if current_spk == spk1_id else spk1_id
                    cur.insertText("\n" + line_text)
                    cur.block().setUserData(SubtitleBlockData(current_spk, start_sec, **stt_kwargs, **quality_kwargs, **clip_kwargs))
                else:
                    # 🚨 '-' 기호가 없으면: 화자를 유지하고 소프트 줄바꿈(\u2028)만 삽입하여 1개의 블록으로 묶습니다.
                    cur.insertText("\u2028" + line_text)
            
            if i + 1 < len(self._segment_queue):
                nxt = self._segment_queue[i+1]
                if seg['end'] < nxt['start'] - 0.05:
                    gap_start = self._frame_time(seg['end'])
                    cur.insertText("\n") 
                    cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))
                    # 💡 [핵심 해결] 무음 블록(빈 줄)을 확보했으니, 다음 자막이 쓸 새로운 줄을 한 번 더 만들어 줍니다!
                    cur.insertText("\n") 
                else:
                    cur.insertText("\n")
            else:
                gap_start = self._frame_time(seg['end'])
                cur.insertText("\n")
                cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))

        self._segment_queue.clear()
        self.text_edit.update_margins()
        cur.endEditBlock()

        self._sync_lock = True
        if is_at_bottom: self.text_edit.setTextCursor(cur)
        else: self.text_edit.setTextCursor(orig_cursor)
        self._sync_lock = False

        self._schedule_timeline()
        self._refresh_video_subtitle_context()

        if is_initial:
            self._is_initial_load = False
            if hasattr(self, 'timeline'):
                self.timeline.set_playhead(0.0); self.timeline.center_to_sec(0.0, smooth=True)
            if hasattr(self, 'video_player'):
                self.video_player.seek(0.0)
        elif added_end > 0.0:
            if hasattr(self, 'timeline'):
                self.timeline.set_playhead(added_end); self.timeline.center_to_sec(added_end, smooth=True)
            if hasattr(self, 'video_player'):
                self.video_player.seek(added_end)
            if self.settings.get("subtitle_quality_auto_check_after_generate") and hasattr(self, "_run_quality_review"):
                QTimer.singleShot(300, lambda: self._run_quality_review(auto_correct=bool(self.settings.get("subtitle_quality_auto_correct_enabled", False))))

    # ---------------------------------------------------------
    # Segment I/O
    # ---------------------------------------------------------

    def _get_current_segments(self) -> list[dict]:
        segments = []
        block = self.text_edit.document().begin()
        line_idx = 0
        
        while block.isValid():
            data = block.userData()
            text = block.text().replace("\u2028", "\n").strip()
            is_gap = getattr(data, 'is_gap', False) if data else False
            
            # ✅ [#1 핵심 수정] 갭 블록도 포함 — 무음구간이 End Time 계산에 반영됩니다
            include_empty_stt = bool(getattr(data, 'stt_pending', False) or getattr(data, 'stt_mode', False))
            if data is not None and (text or is_gap or include_empty_stt):
                # ✅ 갭 블록은 절대 이전 세그먼트에 병합하지 않음 (갭↔자막 병합 방지)
                if (not is_gap
                    and segments
                    and not segments[-1].get("is_gap")
                    and abs(segments[-1]["start"] - data.start_sec) < 0.05):
                    segments[-1]["text"] += "\n" + text
                else:
                    item = {
                        "line": line_idx,
                        "start": data.start_sec,
                        "end": getattr(data, 'end_sec', None),
                        "text": text,
                        "is_gap": is_gap,
                        "spk": getattr(data, 'spk_id', 'SPEAKER_00'),
                        "stt_mode": bool(getattr(data, 'stt_mode', False)),
                        "stt_pending": bool(getattr(data, 'stt_pending', False)),
                        "original_text": getattr(data, 'original_text', '') or '',
                        "dictated_text": getattr(data, 'dictated_text', '') or '',
                        "stt_selected_source": getattr(data, 'stt_selected_source', '') or '',
                        "stt_ensemble_llm_selected_source": getattr(data, 'stt_ensemble_llm_selected_source', '') or '',
                    }
                    if getattr(data, "stt_candidates", None):
                        item["stt_candidates"] = list(getattr(data, "stt_candidates", []) or [])
                    for attr in (
                        "stt_ensemble_source",
                        "stt_ensemble_llm_selected_label",
                        "stt_ensemble_similarity",
                        "stt_ensemble_needs_llm_review",
                        "stt_ensemble_inserted_from_stt2",
                        "stt_ensemble_word_rover",
                    ):
                        value = getattr(data, attr, None)
                        if value not in (None, "", [], {}):
                            item[attr] = value
                    if getattr(data, "clip_idx", None) is not None:
                        item["_clip_idx"] = int(getattr(data, "clip_idx"))
                    if getattr(data, "clip_file", ""):
                        item["_clip_file"] = str(getattr(data, "clip_file", "") or "")
                    if getattr(data, "quality", None):
                        item["quality"] = dict(getattr(data, "quality", {}) or {})
                        item["quality_history"] = list(getattr(data, "quality_history", []) or [])
                        item["quality_candidates"] = list(getattr(data, "quality_candidates", []) or [])
                        signature = self._segment_quality_signature({
                            "start": item["start"],
                            "end": item.get("end") if item.get("end") is not None else item["start"],
                            "text": item["text"],
                            "speaker": item["spk"],
                        })
                        if getattr(data, "quality_signature", "") and signature != getattr(data, "quality_signature", ""):
                            item["quality_stale"] = True
                            quality = dict(item["quality"])
                            flags = list(quality.get("flags") or [])
                            if "quality_stale" not in flags:
                                flags.append("quality_stale")
                            quality["flags"] = flags
                            item["quality"] = quality
                    segments.append(item)
            
            block = block.next()
            line_idx += 1

        # 2. 끝 시간(End Time) 계산
        for i, seg in enumerate(segments):
            is_last = (i + 1 == len(segments))
            
            if is_last:
                if hasattr(self, 'video_player') and getattr(self.video_player, 'total_time', 0) > seg["start"]:
                    next_start = self.video_player.total_time if seg.get("is_gap") else min(seg["start"] + 3.0, self.video_player.total_time)
                else:
                    next_start = seg["start"] + 3.0
            else:
                next_start = segments[i+1]["start"]
                
            c_end = seg.get("end") 
            if c_end is not None and seg["start"] < c_end <= next_start + 0.05:
                seg["end"] = c_end
            else:
                seg["end"] = next_start
            if seg.get("quality") and not seg.get("quality_signature"):
                seg["quality_signature"] = self._segment_quality_signature(seg)
                
        return segments

    # ---------------------------------------------------------
    # Text Editor Event Handlers
    # ---------------------------------------------------------
    def _trigger_editor_popup(self, word, anchor, end_c, gpos):
        self.editor_popup.trigger(word, anchor, end_c, gpos)

    def _on_selection_changed(self):
        if hasattr(self, "_timeline_lock_edit_enabled") and self._timeline_lock_edit_enabled():
            cur = self.text_edit.textCursor()
            if cur.hasSelection():
                cur.clearSelection()
                self.text_edit.setTextCursor(cur)
            return
        if self.text_edit.textCursor().hasSelection():
            self._on_cursor_moved()
        elif self.editor_popup.is_visible():
            self.editor_popup.close_popup()

    def _save_correction(self, old_word, new_word):
        _dm_save_correction(self.corrections, old_word, new_word)
        try:
            from core.subtitle_quality.correction_memory import add_correction_memory_item
            add_correction_memory_item(
                old_word,
                new_word,
                source="manual_popup",
                context=self.text_edit.textCursor().block().text()[:500],
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 교정 memory 저장 실패: {exc}")
        get_logger().log(f"🔄 교정 사전 등록 및 저장: {old_word} -> {new_word}")

    def _on_enter_pressed(self, last_word: str, line_num: int):
        self._undo_mgr.push() # 💡 실행취소 스냅샷 추가
        try: from utils import add_split_rule; add_split_rule(last_word)
        except Exception: pass
        self._schedule_timeline()

    def _on_backspace_merged(self, removed_word: str):
        self._undo_mgr.push() # 💡 실행취소 스냅샷 추가
        try: from utils import remove_split_rule; remove_split_rule(removed_word)
        except Exception: pass
        self._schedule_timeline()

    def _on_cursor_moved(self):
        if self._sync_lock: return
        if hasattr(self, "_timeline_lock_edit_enabled") and self._timeline_lock_edit_enabled():
            return
        line_num = self.text_edit.textCursor().blockNumber()
        # [크PD] 캐시 사용 — 커서 이동마다 전체 문서 재파싱 방지
        segs = getattr(self, '_cached_segs', None) or self._get_current_segments()
        for seg in reversed(segs):
            if seg["line"] <= line_num:
                if self._active_seg_start != seg["start"]:
                    if hasattr(self, 'video_player'): self.video_player.pause_video()
                    self._active_seg_start = seg["start"]
                    self.timeline.set_active(seg["start"])
                    self.timeline.set_playhead(seg["start"])
                    self.timeline.center_to_sec((seg["start"] + seg["end"]) / 2, smooth=True)
                    self._highlighter.set_current_line(line_num)
                    tip = self._quality_tooltip(seg)
                    if tip:
                        self.text_edit.setToolTip(tip)
                    else:
                        self.text_edit.setToolTip("")
                    if hasattr(self, 'video_player'): self.video_player.seek(seg["start"])
                break

    def _on_esc_pressed(self):
        if hasattr(self.timeline, 'canvas'): self.timeline.canvas.update()

    # ---------------------------------------------------------
    # Timeline Schedule
    # ---------------------------------------------------------
    def _redraw_timeline(self):
        segs = self._get_current_segments()
        self._cached_segs = segs  # [크PD] 캐시 저장
        timeline_segs = segs
        preview = list(getattr(self, "_live_stt_preview_segments", []) or [])
        if preview:
            timeline_segs = sorted(
                [seg for seg in segs if not seg.get("is_gap")] + preview,
                key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)),
            )
        if hasattr(self, "_highlighter"):
            quality_map = {
                int(seg.get("line", -1)): dict(seg.get("quality") or {})
                for seg in segs
                if seg.get("quality") and int(seg.get("line", -1)) >= 0
            }
            self._highlighter.set_quality_map(quality_map)
        total_dur = timeline_segs[-1]["end"] if timeline_segs else 0.0
        if hasattr(self, 'video_player') and self.video_player.total_time > 0.0:
            total_dur = max(total_dur, self.video_player.total_time)
        self.timeline.update_segments(timeline_segs, self._active_seg_start, total_dur)
        if hasattr(self, 'video_player') and hasattr(self.video_player, "set_context_segments"):
            _canvas = getattr(getattr(self, "timeline", None), "canvas", None)
            _mc_boxes = list(getattr(_canvas, '_multiclip_boxes', []) or []) if _canvas is not None else []
            if _mc_boxes and hasattr(self, '_resolve_active_context'):
                try:
                    _gsec = float(getattr(_canvas, 'playhead_sec', 0.0) or 0.0)
                    _ctx = self._resolve_active_context(global_sec=_gsec)
                    self.video_player.set_context_segments(list(_ctx.get('local_segments', []) or []))
                except Exception:
                    self.video_player.set_context_segments(segs)
            else:
                self.video_player.set_context_segments(segs)

        # ✅ 최초 로드 시 화면에 맞춤
        if getattr(self, '_needs_fit_view', True) and segs and hasattr(self.timeline, "fit_to_view"):
            self.timeline.fit_to_view()
            self._needs_fit_view = False

    def _refresh_video_subtitle_context(self):
        if not hasattr(self, 'video_player'):
            return
        segs = self._video_subtitle_context_for_player()
        try:
            if hasattr(self.video_player, 'refresh_subtitle_context'):
                self.video_player.refresh_subtitle_context(segs)
            else:
                self.video_player.set_context_segments(segs)
        except Exception:
            pass

    def _video_subtitle_context_for_player(self):
        segs = getattr(self, '_cached_segs', None)
        if segs is None:
            segs = self._get_current_segments()
            self._cached_segs = segs
        try:
            _mc_boxes = list(getattr(self.timeline.canvas, '_multiclip_boxes', []) or []) if hasattr(self, 'timeline') else []
            if _mc_boxes and hasattr(self, '_resolve_active_context'):
                _gsec = float(getattr(self.timeline.canvas, 'playhead_sec', 0.0) or 0.0)
                ctx = self._resolve_active_context(global_sec=_gsec)
                if ctx:
                    return list(ctx.get('local_segments', []) or [])
        except Exception:
            pass
        return [
            s for s in list(segs or [])
            if not s.get('is_gap') and str(s.get('text', '') or '').strip()
        ]

    def _schedule_timeline(self):
        if getattr(self, '_inline_updating', False): return
        if not self._timeline_timer.isActive(): self._timeline_timer.start(150)  # [크PD] 300→150ms 실시간성 개선

    def _draft_settings_snapshot(self) -> dict:
        settings = dict(getattr(self, "settings", {}) or {})
        try:
            from core.settings import load_settings

            settings.update(load_settings())
        except Exception:
            pass
        return settings

    def _roughcut_draft_runtime_enabled(self) -> bool:
        try:
            from core.roughcut import editor_roughcut_draft_enabled

            return editor_roughcut_draft_enabled(self._draft_settings_snapshot())
        except Exception:
            return False

    def _set_roughcut_draft_status(self, status: str, count: int | None = None):
        self._roughcut_draft_status = str(status or "idle")
        if count is not None:
            self._last_roughcut_draft_major_count = int(count)
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            main_w = self.window()
            if hasattr(main_w, "_refresh_saved_status_label"):
                main_w._refresh_saved_status_label()
        except Exception:
            pass

    def _schedule_post_generation_roughcut_draft(self, force: bool = False):
        if not self._roughcut_draft_runtime_enabled():
            self._set_roughcut_draft_status("disabled")
            return
        timer = getattr(self, "_roughcut_draft_timer", None)
        if timer is None:
            return
        if force or not timer.isActive():
            self._set_roughcut_draft_status("queued")
            timer.start(120 if force else 300)

    def _run_post_generation_roughcut_draft(self):
        if not self._roughcut_draft_runtime_enabled():
            self._set_roughcut_draft_status("disabled")
            return
        thread = getattr(self, "_roughcut_draft_thread", None)
        if thread is not None and thread.is_alive():
            return

        segments = [
            dict(seg)
            for seg in self._get_current_segments()
            if not seg.get("is_gap") and str(seg.get("text", "") or "").strip()
        ]
        if not segments:
            self._set_roughcut_draft_status("idle")
            return
        self._set_roughcut_draft_status("running")

        settings = self._draft_settings_snapshot()
        try:
            min_count = max(1, int(settings.get("roughcut_major_min_subtitle_count", 5) or 5))
        except Exception:
            min_count = 5
        main_w = self.window()
        media_path = str(getattr(self, "media_path", "") or "")
        media_files = list(getattr(main_w, "_multiclip_files", []) or [])
        if not media_files and media_path:
            media_files = [media_path]
        clip_boundaries = list(getattr(main_w, "_multiclip_boundaries", []) or [])
        editor_mode = "multiclip" if len(media_files) > 1 else "single"
        media_duration = max((float(seg.get("end", 0.0) or 0.0) for seg in segments), default=0.0)
        try:
            media_duration = max(media_duration, float(getattr(getattr(self, "video_player", None), "total_time", 0.0) or 0.0))
        except Exception:
            pass
        source_media = f"멀티클립 {len(media_files)}개" if len(media_files) > 1 else os.path.basename(media_path or "")
        self._roughcut_draft_generation += 1
        generation = int(self._roughcut_draft_generation)

        def emit_candidate(llm_payload, refinement_source: str):
            from core.roughcut import build_editor_roughcut_candidate_payload, build_editor_roughcut_draft_result

            result = build_editor_roughcut_draft_result(
                segments,
                media_duration=media_duration,
                source_path=media_path,
                settings=settings,
                llm_payload=llm_payload,
            )
            payload = build_editor_roughcut_candidate_payload(
                result,
                source_segments=segments,
                settings=settings,
                source_path=media_path,
                source_media=source_media,
                media_files=media_files,
                clip_boundaries=clip_boundaries,
                editor_mode=editor_mode,
            )
            payload["_generation"] = generation
            payload["refinement_source"] = refinement_source
            self.sig_roughcut_draft_ready.emit(result, segments, payload)

        model = str(settings.get("selected_model", "") or "").strip()
        if len(segments) < min_count or not model or "사용 안함" in model:
            try:
                emit_candidate(None, "local_after_generation")
            except Exception as exc:
                self._set_roughcut_draft_status("failed")
                get_logger().log(f"⚠️ 에디터 러프컷 로컬 초안 생성 실패: {exc}")
            return
        try:
            from core.roughcut import editor_roughcut_draft_llm_allowed

            if not editor_roughcut_draft_llm_allowed(segments, settings):
                max_rows = int(settings.get("roughcut_llm_max_context_rows", 80) or 80)
                get_logger().log(
                    "⏩ 긴 영상 러프컷: 자막 row가 "
                    f"{len(segments)}개라 LLM 초안({max_rows}개 제한)을 건너뛰고 로컬 세그먼트를 즉시 생성합니다."
                )
                emit_candidate(None, "local_after_generation_long_video")
                return
        except Exception as exc:
            get_logger().log(f"⚠️ 러프컷 LLM 길이 판단 실패, 로컬 초안으로 진행: {exc}")
            emit_candidate(None, "local_after_generation_length_guard")
            return
        if time.time() < float(getattr(self, "_roughcut_llm_cooldown_until", 0.0) or 0.0):
            try:
                emit_candidate(None, "local_after_generation")
            except Exception as exc:
                self._set_roughcut_draft_status("failed")
                get_logger().log(f"⚠️ 에디터 러프컷 로컬 초안 생성 실패: {exc}")
            return

        def worker():
            try:
                from core.roughcut import run_editor_roughcut_llm_draft

                llm_payload = run_editor_roughcut_llm_draft(segments, settings=settings)
                if llm_payload is None:
                    self._roughcut_llm_cooldown_until = time.time() + 10.0
                    emit_candidate(None, "local_after_generation_fallback")
                else:
                    self._roughcut_llm_cooldown_until = 0.0
                    emit_candidate(llm_payload, "llm_refined")
            except Exception as exc:
                self.sig_roughcut_draft_ready.emit(None, [], {"_generation": generation, "refinement_source": "failed"})
                try:
                    get_logger().log(f"⚠️ 에디터 러프컷 초안 생성 실패: {exc}")
                except Exception:
                    pass

        self._roughcut_draft_pending = False
        self._roughcut_draft_thread = threading.Thread(target=worker, daemon=True, name="editor-post-generation-roughcut-draft")
        self._roughcut_draft_thread.start()

    def _apply_post_generation_roughcut_draft(self, result, segments: list, candidate: dict):
        refinement_source = str(candidate.get("refinement_source") or "")
        try:
            if int(candidate.get("_generation", -1)) != int(getattr(self, "_roughcut_draft_generation", 0)):
                return
        except Exception:
            pass
        if refinement_source == "failed":
            self._set_roughcut_draft_status("failed")
            self._roughcut_draft_thread = None
            return
        self._set_roughcut_draft_status("saving")
        try:
            major_count = len(getattr(result, "segments", ()) or ())
            max_major = int(self._draft_settings_snapshot().get("editor_roughcut_draft_max_major_segments", 10) or 10)
            if major_count > max(1, min(26, max_major)):
                from core.roughcut import build_editor_roughcut_candidate_payload, build_editor_roughcut_draft_result

                settings = self._draft_settings_snapshot()
                media_path = str(getattr(self, "media_path", "") or "")
                main_w = self.window()
                media_files = list(getattr(main_w, "_multiclip_files", []) or [])
                if not media_files and media_path:
                    media_files = [media_path]
                result = build_editor_roughcut_draft_result(
                    segments,
                    media_duration=max((float(seg.get("end", 0.0) or 0.0) for seg in segments), default=0.0),
                    source_path=media_path,
                    settings=settings,
                    llm_payload=None,
                )
                candidate = build_editor_roughcut_candidate_payload(
                    result,
                    source_segments=segments,
                    settings=settings,
                    source_path=media_path,
                    source_media=os.path.basename(media_path or "") or "현재 에디터",
                    media_files=media_files,
                    clip_boundaries=list(getattr(main_w, "_multiclip_boundaries", []) or []),
                    editor_mode="multiclip" if len(media_files) > 1 else "single",
                )
                candidate["refinement_source"] = refinement_source or "local_capped"
        except Exception:
            pass
        try:
            self._auto_save_project(segments)
        except Exception as exc:
            get_logger().log(f"⚠️ 러프컷 초안 프로젝트 선저장 실패: {exc}")
        main_w = self.window()
        project_path = str(getattr(main_w, "_current_project_path", "") or "")
        if not project_path:
            self._set_roughcut_draft_status("failed")
            return
        try:
            from core.project.project_manager import save_project
            from core.roughcut import EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID, merge_editor_roughcut_draft_state
            from core.work_mode import EDITOR_MODE

            existing_state = {}
            if os.path.exists(project_path):
                try:
                    with open(project_path, "r", encoding="utf-8") as f:
                        existing_state = json.load(f).get("roughcut_state", {}) or {}
                except Exception:
                    existing_state = {}
            candidate.pop("_generation", None)
            roughcut_state = merge_editor_roughcut_draft_state(existing_state, candidate)
            save_project(
                project_path,
                segments=segments,
                user_settings=dict(getattr(self, "settings", {}) or {}),
                roughcut_state=roughcut_state,
                active_work_mode=EDITOR_MODE,
            )
            setattr(main_w, "_editor_roughcut_result", result)
            roughcut = getattr(main_w, "_roughcut_widget", None)
            if roughcut is not None:
                try:
                    roughcut._result = result
                    roughcut._source_signature = str(candidate.get("source_signature") or "")
                    roughcut._selected_candidate_id = EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID
                    roughcut._roughcut_candidates = list(roughcut_state.get("candidates", []) or [])
                    if hasattr(roughcut, "_refresh_candidate_combo"):
                        roughcut._refresh_candidate_combo()
                    if hasattr(roughcut, "_populate_result"):
                        roughcut._populate_result()
                except RuntimeError:
                    pass
                except Exception:
                    pass
            self._redraw_timeline()
            count = len(getattr(result, "segments", ()) or ())
            last_count = getattr(self, "_last_roughcut_draft_major_count", None)
            if last_count != count:
                self._last_roughcut_draft_major_count = count
                get_logger().log(f"자막 생성 후 러프컷 초안 생성: 중분류 {count}개")
            self._set_roughcut_draft_status("done", count)
        except Exception as exc:
            self._set_roughcut_draft_status("failed")
            get_logger().log(f"⚠️ 러프컷 초안 저장 실패: {exc}")
        finally:
            if refinement_source in {"llm_refined", "local_after_generation_fallback"}:
                self._roughcut_draft_thread = None

    def _on_drag_started(self): 
        # 💡 드래그를 시작하기 직전의 전체 뷰 스냅샷 저장!
        self._undo_mgr.push_immediate()
        
        self._drag_cursor = QTextCursor(self.text_edit.document())
        self._drag_cursor.beginEditBlock()
        
    def _on_drag_finished(self): 
        if hasattr(self, '_drag_cursor') and self._drag_cursor:
            self._drag_cursor.endEditBlock()
            self._drag_cursor = None
        self._schedule_timeline()

    # 💡 [신규] 특정 시간대의 블록을 지우고 새 자막으로 교체하는 외과 수술 로직
    # 💡 1. 선제적 삭제 및 위치 기억 (버튼 누르자마자 즉시 실행)
    def clear_segments_in_range(self, target_start: float, target_end: float):
        self._undo_mgr.push_immediate()
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        
        start_block, end_block = None, None
        for i in range(doc.blockCount()):
            b = doc.findBlockByNumber(i)
            ud = b.userData()
            if ud and hasattr(ud, 'start_sec'):
                if ud.start_sec >= target_start and start_block is None:
                    start_block = b
                if ud.start_sec >= target_end and start_block is not None:
                    end_block = b; break
        
        cur.beginEditBlock()
        if start_block:
            # 🚨 [쓰레기 자막 방지] 삭제 후 뒤로 밀려날 블록의 고유 시간 데이터를 백업합니다.
            end_ud = end_block.userData() if end_block else None
            
            cur.setPosition(start_block.position())
            if end_block: cur.setPosition(end_block.position(), QTextCursor.MoveMode.KeepAnchor)
            else: cur.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            
            cur.removeSelectedText()
            
            # 단면이 붙지 않게 빈 줄(방화벽) 생성 후 백업 데이터 복구
            if end_block:
                cur.insertText("\n")
                if end_ud:
                    cur.block().setUserData(SubtitleBlockData(end_ud.spk_id, end_ud.start_sec, end_ud.is_gap))
                cur.movePosition(QTextCursor.MoveOperation.PreviousBlock)
            else:
                while cur.block().text().strip() == "" and doc.blockCount() > 1:
                    cur.deletePreviousChar()
            
            # 삽입될 '절대 위치' 기억
            self._partial_insert_pos = cur.position() 
        else:
            cur.movePosition(QTextCursor.MoveOperation.End)
            if not cur.atBlockStart(): cur.insertText("\n")
            self._partial_insert_pos = cur.position()
            
        self.text_edit.update_margins()
        cur.endEditBlock()
        self._schedule_timeline()
    
    # 💡 2. 기억된 위치에 정밀 삽입 (자동저장 차단)
    # [ui/editor_segments.py] insert_partial_segments 함수 교체
    def insert_partial_segments(self, new_segments: list[dict]):
        try:
            self._undo_mgr.push_immediate()
            doc = self.text_edit.document()
            cur = QTextCursor(doc)
            if hasattr(self, '_partial_insert_pos'): cur.setPosition(self._partial_insert_pos)
            else: cur.movePosition(QTextCursor.MoveOperation.End)
                
            cur.beginEditBlock()
            spk1_id = self.settings.get("spk1_id", "00")
            spk2_id = self.settings.get("spk2_id", "01")
            from ui.editor.subtitle_text_edit import SubtitleBlockData
            
            for i, seg in enumerate(new_segments):
                if not cur.atBlockStart(): cur.insertBlock()
                text = seg.get("text", "").replace("\r", "")
                parts = [p.strip() for p in text.split('\n') if p.strip()]
                if not parts: continue
                
                start_sec = self._frame_time(seg.get("start", 0))
                current_spk = seg.get("speaker_list", [spk1_id])[0] if seg.get("speaker_list") else spk1_id
                
                cur.insertText(parts[0])
                cur.block().setUserData(SubtitleBlockData(current_spk, start_sec))
                
                # 💡 [복구] 줄바꿈 및 화자 분리 로직 완벽 구현
                for p_idx in range(1, len(parts)):
                    line_text = parts[p_idx]
                    if line_text.startswith('-'):
                        current_spk = spk2_id if current_spk == spk1_id else spk1_id
                        cur.insertBlock() 
                        cur.insertText(line_text)
                        cur.block().setUserData(SubtitleBlockData(current_spk, start_sec))
                    else:
                        cur.insertText("\u2028" + line_text) 
                
                # Gap 처리
                gap_start = self._frame_time(seg['end'])
                if i + 1 < len(new_segments):
                    if seg['end'] < new_segments[i+1]['start'] - 0.05:
                        cur.insertBlock()
                        cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))
                else:
                    cur.insertBlock()
                    cur.block().setUserData(SubtitleBlockData("00", gap_start, is_gap=True))

            # 💡 [핵심 수정] 상태 머신의 더티 플래그를 활성화합니다!
            self._mark_dirty()
                
            self.text_edit.update_margins()
            cur.endEditBlock()
            self._schedule_timeline()
        except Exception as e:
            from logger import get_logger
            get_logger().log(f"⚠️ 정밀 삽입 오류: {e}")

    
    def split_segment_with_text(self, line_num: int, split_sec: float, cursor: int):
        """
        플레이헤드 시간(split_sec) + 텍스트 커서(cursor) 기준으로
        현재 세그먼트를 2개로 분리한다.

        [v01.00.04]
        - block.text() 직접 사용 (canvas stale 데이터 참조 제거)
        - secondary_block_positions 삭제 로직 제거
          (현재 _get_current_segments()는 블록별 독립 세그먼트로 관리하므로
           같은 start_sec인 인접 블록을 지우면 다른 자막이 삭제되는 버그 발생)
        - '-' 화자 구분자 제거
        """
        doc = self.text_edit.document()
        block = doc.findBlockByNumber(int(line_num))
        if not block.isValid():
            return

        try:
            self._undo_mgr.push_immediate()
        except Exception:
            pass

        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            return

        start_sec = self._frame_time(ud.start_sec)
        spk_id    = ud.spk_id
        split_sec = self._frame_time(split_sec)

        # 범위 체크
        try:
            canvas_segs = self.timeline.canvas.segments
            end_map = {s.get("line"): float(s.get("end", 0.0))
                       for s in canvas_segs if s.get("line") is not None}
            end_sec = end_map.get(int(line_num))
            if end_sec is not None:
                if split_sec <= start_sec + 0.05 or split_sec >= end_sec - 0.05:
                    return
            else:
                if split_sec <= start_sec + 0.05:
                    return
        except Exception:
            if split_sec <= start_sec + 0.05:
                return

        # block.text() 직접 사용 (sig_inline_text_changed로 항상 최신 상태 보장)
        full_text = block.text().replace("\u2028", "\n")

        cursor = max(0, min(int(cursor), len(full_text)))
        left  = full_text[:cursor].rstrip()
        right = full_text[cursor:].lstrip()

        # ✅ 수정: right가 비어있으면 "새자막"으로 대체
        if not left:
            return
        if not right:
            right = "새자막"

        def _strip_leading_dash(t: str) -> str:
            lines = [l.strip() for l in t.splitlines() if l.strip()]
            if not lines:
                return ""
            if lines[0].startswith("-"):
                lines[0] = lines[0].lstrip("-").strip()
            return "\n".join(lines)

        left  = _strip_leading_dash(left)
        right = _strip_leading_dash(right)

        # ✅ 수정: right가 비어있으면 "새자막"으로 대체
        if not left:
            return
        if not right:
            right = "새자막"

        left_doc  = left.replace("\n", "\u2028")
        right_doc = right.replace("\n", "\u2028")

        cur = QTextCursor(block)
        cur.beginEditBlock()

        # primary block → left 파트로 교체 (StartOfBlock~EndOfBlock 범위만 선택)
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                         QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(left_doc)
        cur.block().setUserData(
            SubtitleBlockData(spk_id, start_sec, is_gap=False)
        )

        # 새 블록 삽입 → right 파트
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertBlock()
        cur.insertText(right_doc)
        cur.block().setUserData(
            SubtitleBlockData(spk_id, split_sec, is_gap=False)
        )

        cur.endEditBlock()

        # 💡 [타임라인 튕김 완벽 방지] 커서 이동 시 화면이 중앙으로 강제 점프하는 것을 잠급니다.
        self._sync_lock = True  # 자동 센터링 방지 잠금
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.text_edit.setTextCursor(cur)
        
        self._active_seg_start = split_sec
        if hasattr(self, 'timeline'):
            self.timeline.set_active(self._active_seg_start)
            # 🎯 자막의 중간이 아니라, 대표님이 우클릭한 그 시점(split_sec)을 중앙으로!
            self.timeline.center_to_sec(split_sec, smooth=True)
        self._sync_lock = False

        self._mark_dirty()
        self._finalize_edit()
