# Version: 03.09.29
# Phase: PHASE2
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.project.subtitle_status import subtitle_detection_score
from ui.timeline.timeline_paint import TimelinePaintMixin
from ui.timeline.timeline_segment_style import (
    SEGMENT_TEXT_KIND_STYLES,
    official_boundary_marker_visual,
    scan_boundary_marker_label,
    scan_boundary_marker_visual,
    segment_text_kind,
    stt_checked_source,
    stt_checked_sources,
    stt_preview_visual_style,
    subtitle_confidence_chips,
    subtitle_render_detail_mode,
    subtitle_segment_visual_style,
)
from ui.timeline.timeline_analysis import (
    MAJOR_SEGMENT_COLORS,
    analysis_markers_for_widget,
    editor_analysis_markers,
    roughcut_major_markers,
    roughcut_major_color,
    roughcut_markers,
    subtitle_generation_silence_segments_for_editor,
    subtitle_review_state,
    subtitle_detection_color,
    subtitle_score_overlay_marker,
    voice_activity_segments_for_editor,
)
from ui.timeline.timeline_scenegraph import build_scenegraph_subtitle_segments
from ui.timeline.timeline_constants import RULER_H, STT1_BOT, STT1_TOP, STT_PREVIEW_VERTICAL_INSET
from ui.timeline.timeline_roughcut_paint import coalesce_roughcut_paint_markers, visible_roughcut_label_span
from ui.timeline.stt_preview_layout import (
    MAX_STT_PREVIEW_SUBLANES,
    assign_stt_preview_lanes,
    dedupe_stt_preview_segments_for_display,
    ensure_stt_preview_lane_numbers,
    stt_preview_lane_geometry,
)
from ui.style import COLORS


class _DummyTimelineRuler(TimelinePaintMixin):
    def __init__(self, pps: float):
        self.pps = float(pps)


class TimelineSegmentColorTests(unittest.TestCase):
    def test_voice_and_silence_labels_use_distinct_kinds(self):
        self.assertEqual(segment_text_kind("음성"), "speech")
        self.assertEqual(segment_text_kind(" 무 음 "), "silence")
        self.assertEqual(segment_text_kind("일반 자막"), "")

    def test_voice_and_silence_styles_are_visually_distinct(self):
        speech = SEGMENT_TEXT_KIND_STYLES["speech"]
        silence = SEGMENT_TEXT_KIND_STYLES["silence"]
        self.assertNotEqual(speech["fill"], silence["fill"])
        self.assertNotEqual(speech["border"], silence["border"])
        self.assertNotEqual(speech["text"], silence["text"])

    def test_subtitle_segment_visual_style_is_zoom_stable_for_quality_colors(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "일반 자막",
            "quality": {"confidence_label": "red"},
        }

        compact_style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")
        expanded_style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")

        self.assertEqual(compact_style["fill"], expanded_style["fill"])
        self.assertEqual(compact_style["border"], expanded_style["border"])
        self.assertEqual(compact_style["fill"], COLORS["danger_surface"])
        self.assertEqual(compact_style["border"], "#FF453A")

    def test_subtitle_segment_visual_style_keeps_text_kind_over_zoom(self):
        seg = {"start": 0.0, "end": 1.0, "text": "음성"}

        style = subtitle_segment_visual_style(seg, active=True, hover=True, quality_filter="all")

        self.assertEqual(style["fill"], SEGMENT_TEXT_KIND_STYLES["speech"]["fill"])
        self.assertEqual(style["border"], SEGMENT_TEXT_KIND_STYLES["speech"]["border"])

    def test_subtitle_segment_visual_style_keeps_active_fill_during_playback(self):
        seg = {"start": 0.0, "end": 1.0, "text": "일반 자막"}

        active_style = subtitle_segment_visual_style(seg, active=True, hover=False, quality_filter="all")
        playback_style = subtitle_segment_visual_style(
            seg,
            active=True,
            hover=False,
            playback_active=True,
            quality_filter="all",
        )

        self.assertEqual(playback_style["fill"], active_style["fill"])
        self.assertEqual(playback_style["border"], active_style["border"])

    def test_subtitle_render_detail_mode_keeps_density_profile_during_playback(self):
        paused = subtitle_render_detail_mode(
            visible_segment_count=96,
            pps=18.0,
            playback_active=False,
        )
        playing = subtitle_render_detail_mode(
            visible_segment_count=96,
            pps=18.0,
            playback_active=True,
        )

        self.assertEqual(paused, "ultra")
        self.assertEqual(playing, paused)

    def test_active_conflict_subtitle_gets_active_accent_instead_of_plain_gray(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "충돌 자막",
            "stt_ensemble_needs_llm_review": True,
            "stt_candidates": [
                {"source": "STT1", "text": "여기로 가자", "score": 0.84},
                {"source": "STT2", "text": "이거로 하자", "score": 0.82},
            ],
        }

        idle = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")
        active = subtitle_segment_visual_style(seg, active=True, hover=False, quality_filter="all")

        self.assertEqual(idle["fill"], COLORS["neutral_soft"])
        self.assertEqual(idle["border"], "#8E8E93")
        self.assertNotEqual(active["fill"], idle["fill"])
        self.assertEqual(active["border"], "#8AB8FF")

    def test_scenegraph_keeps_selected_segment_style_during_playback(self):
        objects = build_scenegraph_subtitle_segments(
            [
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "앞",
                    "line": 0,
                    "stt_ensemble_needs_llm_review": True,
                },
                {
                    "start": 2.0,
                    "end": 3.0,
                    "text": "뒤",
                    "line": 1,
                    "stt_ensemble_needs_llm_review": True,
                },
            ],
            pps=100.0,
            fps=30.0,
            visible_start_sec=0.0,
            visible_end_sec=4.0,
            active_start=1.0,
            active_line=0,
            playback_active=True,
            playhead_sec=2.4,
            quality_filter="all",
        )

        by_line = {obj["line"]: obj for obj in objects}
        active_first = subtitle_segment_visual_style(objects[0] | {"stt_ensemble_needs_llm_review": True}, active=True, hover=False, quality_filter="all")
        idle_second = subtitle_segment_visual_style(objects[1] | {"stt_ensemble_needs_llm_review": True}, active=False, hover=False, quality_filter="all")
        self.assertEqual(by_line[0]["fill"], active_first["fill"])
        self.assertEqual(by_line[1]["fill"], idle_second["fill"])
        self.assertEqual(by_line[0]["borderWidth"], 2)
        self.assertEqual(by_line[1]["borderWidth"], 1)

    def test_fps_ruler_uses_per_frame_ticks_when_zoom_allows_it(self):
        ruler = _DummyTimelineRuler(pps=1600.0)

        self.assertEqual(ruler._fps_ruler_minor_step_frames(25.0), 1)
        self.assertEqual(ruler._fps_ruler_major_step_seconds(), 1)
        self.assertEqual(ruler._fps_ruler_reference_label_step_seconds(), 1)
        self.assertTrue(ruler._fps_ruler_should_draw_minor_ticks(1, 1, 25.0))

    def test_fps_ruler_coarsens_minor_ticks_when_zoom_is_tight(self):
        ruler = _DummyTimelineRuler(pps=40.0)

        self.assertEqual(ruler._fps_ruler_major_step_seconds(), 2)
        self.assertEqual(ruler._fps_ruler_minor_step_frames(25.0), 25)
        self.assertEqual(ruler._fps_ruler_reference_label_step_seconds(), 2)
        self.assertFalse(ruler._fps_ruler_should_draw_minor_ticks(2, 25, 25.0))

    def test_fps_ruler_scales_major_ticks_for_zoomed_out_long_media(self):
        ruler = _DummyTimelineRuler(pps=0.8)

        self.assertEqual(ruler._fps_ruler_major_step_seconds(), 60)
        self.assertEqual(ruler._fps_ruler_reference_label_step_seconds(), 120)
        self.assertFalse(ruler._fps_ruler_should_draw_minor_ticks(60, 60, 60.0))

    def test_ruler_time_label_background_covers_tick_line(self):
        ruler = _DummyTimelineRuler(pps=200.0)

        rect = ruler._ruler_time_label_background_rect(
            120,
            34,
            baseline_y=RULER_H - 9,
            font_ascent=10,
            font_descent=3,
            clip_left=0,
            clip_right=240,
        )

        self.assertLessEqual(rect.left(), 120)
        self.assertGreaterEqual(rect.right(), 120)
        self.assertGreaterEqual(rect.width(), 44)
        self.assertLess(rect.top(), RULER_H - 9)
        self.assertLess(rect.bottom(), RULER_H)

    def test_scenegraph_splits_overlapping_stt_preview_candidates_to_two_rows_per_source(self):
        objects = build_scenegraph_subtitle_segments(
            [
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "STT1 첫 후보",
                    "line": 0,
                    "stt_pending": True,
                    "stt_preview_source": "STT1",
                    "stt_score_color": "#FF453A",
                },
                {
                    "start": 1.2,
                    "end": 2.2,
                    "text": "STT1 둘 후보",
                    "line": 1,
                    "stt_pending": True,
                    "stt_preview_source": "STT1",
                    "stt_score_color": "#34C759",
                },
            ],
            pps=160.0,
            fps=30.0,
            visible_start_sec=0.0,
            visible_end_sec=3.0,
        )

        self.assertEqual(len(objects), 2)
        by_text = {row["text"]: row for row in objects}
        first = by_text["STT1 첫 후보"]
        second = by_text["STT1 둘 후보"]
        first_y, first_h = stt_preview_lane_geometry(
            STT1_TOP,
            STT1_BOT,
            0,
            2,
            inset=STT_PREVIEW_VERTICAL_INSET,
        )
        second_y, second_h = stt_preview_lane_geometry(
            STT1_TOP,
            STT1_BOT,
            1,
            2,
            inset=STT_PREVIEW_VERTICAL_INSET,
        )
        self.assertEqual(first["y"], first_y)
        self.assertEqual(second["y"], second_y)
        self.assertEqual(first["h"], first_h)
        self.assertEqual(second["h"], second_h)
        self.assertLess(first["y"], second["y"])
        self.assertLess(first["y"] + first["h"], second["y"])
        self.assertEqual(first["fill"], "#163223")
        self.assertEqual(second["fill"], "#163223")

    def test_scenegraph_stt_preview_uses_word_span_for_timeline_position(self):
        objects = build_scenegraph_subtitle_segments(
            [
                {
                    "start": 62.0,
                    "end": 66.0,
                    "text": "아 이게 시림프 갈릭 소스",
                    "line": 0,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT1",
                    "words": [
                        {"word": "아", "start": 67.1, "end": 67.25},
                        {"word": "소스", "start": 68.2, "end": 68.9},
                    ],
                },
            ],
            pps=300.0,
            fps=30.0,
            visible_start_sec=66.0,
            visible_end_sec=70.0,
        )

        self.assertEqual(len(objects), 1)
        self.assertGreaterEqual(objects[0]["startSec"], 67.0)
        self.assertLess(objects[0]["startSec"], 67.2)

    def test_stt_preview_lane_assignment_caps_visible_split_count_to_bounded_rows(self):
        segments = [
            {"start": 1.0, "end": 2.0, "text": "a"},
            {"start": 1.0, "end": 2.0, "text": "b"},
            {"start": 1.0, "end": 2.0, "text": "c"},
            {"start": 1.0, "end": 2.0, "text": "d"},
        ]

        lane_map, lane_count = assign_stt_preview_lanes(segments)

        self.assertEqual(lane_count, MAX_STT_PREVIEW_SUBLANES)
        self.assertEqual({lane_map[id(seg)] for seg in segments}, set(range(MAX_STT_PREVIEW_SUBLANES)))

        slot_heights = {
            stt_preview_lane_geometry(STT1_TOP, STT1_BOT, lane_map[id(seg)], lane_count, inset=STT_PREVIEW_VERTICAL_INSET)[1]
            for seg in segments
        }
        expected_slot_h = stt_preview_lane_geometry(
            STT1_TOP,
            STT1_BOT,
            0,
            MAX_STT_PREVIEW_SUBLANES,
            inset=STT_PREVIEW_VERTICAL_INSET,
        )[1]
        self.assertEqual(len(slot_heights), 1)
        self.assertEqual(next(iter(slot_heights)), expected_slot_h)

    def test_stt_preview_lane_assignment_preserves_explicit_two_row_metadata(self):
        segments = [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "bottom only",
                "stt_preview_source": "STT1",
                "stt_preview_sublane": 1,
                "stt_preview_sublane_count": 2,
            }
        ]

        lane_map, lane_count = assign_stt_preview_lanes(segments)

        self.assertEqual(lane_count, 2)
        self.assertEqual(lane_map[id(segments[0])], 1)

    def test_stt_preview_lane_assignment_repairs_overlapping_stale_explicit_metadata(self):
        segments = [
            {
                "start": 1.0,
                "end": 3.0,
                "text": "long",
                "stt_preview_source": "STT1",
                "stt_preview_sublane": 0,
                "stt_preview_sublane_count": 2,
            },
            {
                "start": 2.0,
                "end": 4.0,
                "text": "overlap",
                "stt_preview_source": "STT1",
                "stt_preview_sublane": 0,
                "stt_preview_sublane_count": 2,
            },
            {
                "start": 3.2,
                "end": 5.0,
                "text": "third",
                "stt_preview_source": "STT1",
                "stt_preview_sublane": 0,
                "stt_preview_sublane_count": 2,
            },
        ]

        lane_map, lane_count = assign_stt_preview_lanes(segments)

        self.assertEqual(lane_count, 2)
        self.assertEqual(lane_map[id(segments[0])], 0)
        self.assertEqual(lane_map[id(segments[1])], 1)
        self.assertEqual(lane_map[id(segments[2])], 0)

    def test_stt_preview_lane_assignment_splits_near_touching_candidates(self):
        segments = [
            {"start": 28.10, "end": 29.54, "text": "왜? 왜? 왜? 아", "stt_preview_source": "STT1"},
            {"start": 29.57, "end": 30.10, "text": "아 현금 아 현금", "stt_preview_source": "STT1"},
            {"start": 30.22, "end": 31.40, "text": "현금 계산 아 현금", "stt_preview_source": "STT1"},
        ]

        lane_map, lane_count = assign_stt_preview_lanes(segments)

        self.assertEqual(lane_count, 2)
        self.assertEqual(lane_map[id(segments[0])], 0)
        self.assertEqual(lane_map[id(segments[1])], 1)
        self.assertEqual(lane_map[id(segments[2])], 0)

    def test_scenegraph_preview_segments_keep_inner_gap_between_adjacent_boxes(self):
        objects = build_scenegraph_subtitle_segments(
            [
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "앞",
                    "line": 0,
                    "stt_pending": True,
                    "stt_preview_source": "STT1",
                },
                {
                    "start": 2.2,
                    "end": 3.0,
                    "text": "뒤",
                    "line": 1,
                    "stt_pending": True,
                    "stt_preview_source": "STT1",
                },
            ],
            pps=100.0,
            fps=25.0,
            visible_start_sec=0.0,
            visible_end_sec=4.0,
        )

        self.assertEqual(len(objects), 2)
        by_text = {row["text"]: row for row in objects}
        front = by_text["앞"]
        self.assertEqual(front["startSec"], 1.0)
        self.assertEqual(front["endSec"], 2.0)
        self.assertAlmostEqual(front["x"], 101.0, delta=0.01)
        self.assertAlmostEqual(front["w"], 98.0, delta=0.01)

    def test_ensure_stt_preview_lane_numbers_stamps_overlapping_source_rows(self):
        segments = [
            {"start": 1.0, "end": 2.0, "text": "top", "stt_preview_source": "STT1", "stt_pending": True},
            {"start": 1.1, "end": 2.1, "text": "bottom", "stt_preview_source": "STT1", "stt_pending": True},
        ]

        ensure_stt_preview_lane_numbers(segments, mutate=True)

        self.assertEqual({seg["stt_preview_sublane_count"] for seg in segments}, {2})
        self.assertEqual({seg["stt_preview_sublane"] for seg in segments}, {0, 1})

    def test_ensure_stt_preview_lane_numbers_repairs_stale_same_lane_metadata(self):
        segments = [
            {
                "start": 1.0,
                "end": 3.0,
                "text": "long",
                "stt_preview_source": "STT1",
                "stt_pending": True,
                "stt_preview_sublane": 0,
                "stt_preview_sublane_count": 2,
            },
            {
                "start": 2.0,
                "end": 4.0,
                "text": "overlap",
                "stt_preview_source": "STT1",
                "stt_pending": True,
                "stt_preview_sublane": 0,
                "stt_preview_sublane_count": 2,
            },
        ]

        ensure_stt_preview_lane_numbers(segments, mutate=True)

        self.assertEqual({seg["stt_preview_sublane_count"] for seg in segments}, {2})
        self.assertEqual([seg["stt_preview_sublane"] for seg in segments], [0, 1])

    def test_stt_preview_display_dedupes_same_source_duplicate_text_only(self):
        segments = [
            {"start": 1.0, "end": 3.0, "text": "시트도 편하고", "stt_preview_source": "STT1", "stt_score": 70},
            {"start": 1.05, "end": 3.05, "text": "시트도 편하고", "stt_preview_source": "STT1", "stt_score": 88},
            {"start": 1.05, "end": 3.05, "text": "헤드레스트도 편하고", "stt_preview_source": "STT1", "stt_score": 60},
            {"start": 1.05, "end": 3.05, "text": "시트도 편하고", "stt_preview_source": "STT2", "stt_score": 55},
        ]

        visible = dedupe_stt_preview_segments_for_display(segments)

        self.assertEqual(
            [(seg["stt_preview_source"], seg["text"], seg["stt_score"]) for seg in visible],
            [
                ("STT1", "시트도 편하고", 88),
                ("STT1", "헤드레스트도 편하고", 60),
                ("STT2", "시트도 편하고", 55),
            ],
        )

    def test_manual_confirmed_subtitle_keeps_green_border_under_filters(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "확정 자막",
            "quality": {
                "confidence_label": "green",
                "manual_confirmed": True,
                "flags": ["manual_confirmed"],
            },
        }

        style = subtitle_segment_visual_style(seg, active=True, hover=True, quality_filter="needs_review")

        self.assertEqual(style["fill"], "#1B2C22")
        self.assertEqual(style["border"], "#34C759")
        self.assertFalse(style["muted"])

    def test_unknown_quality_filter_does_not_mute_subtitle_colors(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "자동 선택 자막",
            "quality": {"confidence_label": "green", "confidence_score": 96},
            "stt_ensemble_llm_selected_source": "STT1",
            "stt_candidates": [{"source": "STT1", "score": 0.96}],
        }

        style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="보통")

        self.assertEqual(style["fill"], COLORS["warning_surface"])
        self.assertEqual(style["border"], COLORS["warning"])
        self.assertFalse(style["muted"])

    def test_unconfirmed_high_score_subtitle_is_yellow_not_green(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "자동 선택 자막",
            "quality": {"confidence_label": "green", "confidence_score": 96},
            "stt_ensemble_llm_selected_source": "STT1",
            "stt_candidates": [{"source": "STT1", "score": 0.96}],
        }

        style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")

        self.assertEqual(subtitle_review_state(seg), "pending")
        self.assertEqual(style["fill"], COLORS["warning_surface"])
        self.assertEqual(style["border"], COLORS["warning"])

    def test_fractional_quality_confidence_score_does_not_force_recheck(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "비율 점수 자막",
            "quality": {"confidence_label": "green", "confidence_score": 0.96},
            "stt_ensemble_llm_selected_source": "STT1",
            "stt_candidates": [{"source": "STT1", "score": 0.96}],
        }

        style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")

        self.assertEqual(subtitle_detection_score(seg), 96.0)
        self.assertEqual(subtitle_review_state(seg), "pending")
        self.assertEqual(style["fill"], COLORS["warning_surface"])
        self.assertEqual(style["border"], COLORS["warning"])

    def test_low_score_subtitle_is_recheck_red(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "낮은 점수",
            "quality": {"confidence_label": "yellow", "confidence_score": 52},
            "stt_ensemble_llm_selected_source": "STT1",
            "stt_candidates": [{"source": "STT1", "score": 0.52}],
        }

        style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")

        self.assertEqual(subtitle_review_state(seg), "recheck")
        self.assertEqual(style["fill"], COLORS["danger_surface"])
        self.assertEqual(style["border"], "#FF453A")

    def test_fractional_low_quality_confidence_score_stays_recheck(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "낮은 비율 점수",
            "quality": {"confidence_label": "yellow", "confidence_score": 0.52},
            "stt_ensemble_llm_selected_source": "STT1",
            "stt_candidates": [{"source": "STT1", "score": 0.52}],
        }

        self.assertEqual(subtitle_detection_score(seg), 52.0)
        self.assertEqual(subtitle_review_state(seg), "recheck")

    def test_unresolved_stt_conflict_subtitle_is_gray(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "판단 필요",
            "stt_ensemble_needs_llm_review": True,
            "stt_candidates": [
                {"source": "STT1", "text": "여기로 가자", "score": 0.84},
                {"source": "STT2", "text": "이거로 하자", "score": 0.82},
            ],
        }

        style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")

        self.assertEqual(subtitle_review_state(seg), "conflict")
        self.assertEqual(style["fill"], COLORS["neutral_soft"])
        self.assertEqual(style["border"], "#8E8E93")

    def test_selected_stt_conflict_does_not_fall_back_to_gray(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "선택된 자막",
            "stt_ensemble_needs_llm_review": True,
            "stt_selected_source": "STT1",
            "stt_candidates": [
                {"source": "STT1", "text": "선택된 자막", "score": 0.86},
                {"source": "STT2", "text": "다른 후보", "score": 0.82},
            ],
            "quality": {
                "confidence_label": "green",
                "confidence_score": 86,
                "manual_confirmed": True,
                "flags": ["manual_confirmed"],
            },
        }

        style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")

        self.assertEqual(subtitle_review_state(seg), "confirmed")
        self.assertEqual(style["fill"], "#1B2C22")
        self.assertEqual(style["border"], "#34C759")

    def test_subtitle_confidence_chips_map_stage_labels_to_colors(self):
        chips = subtitle_confidence_chips(
            {
                "subtitle_stage_confidence": {
                    "stage_order": ["cut", "stt", "llm", "lora", "final"],
                    "stages": {
                        "cut": {"label": "red", "score": 40},
                        "stt": {"label": "yellow", "score": 70},
                        "llm": {"label": "green", "score": 92},
                        "lora": {"label": "gray", "score": None},
                        "final": {"label": "green", "score": 90},
                    },
                }
            }
        )

        self.assertEqual([chip["stage"] for chip in chips], ["cut", "stt", "llm", "lora", "final"])
        self.assertEqual(chips[0]["color"], "#FF453A")
        self.assertEqual(chips[1]["color"], COLORS["warning"])
        self.assertEqual(chips[2]["color"], "#34C759")
        self.assertEqual(chips[3]["color"], "#8E8E93")

    def test_subtitle_render_detail_mode_scales_down_for_dense_timelines(self):
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=24, pps=80.0, editing=False, scenegraph=False),
            "full",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=96, pps=28.0, editing=False, scenegraph=False),
            "dense",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=40, pps=8.0, editing=False, scenegraph=False),
            "ultra",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=56, pps=80.0, editing=False, scenegraph=False),
            "dense",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=240, pps=12.0, editing=False, scenegraph=False),
            "ultra",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=24, pps=80.0, editing=False, scenegraph=False, playback_active=True),
            "full",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=48, pps=20.0, editing=False, scenegraph=False, playback_active=True),
            "dense",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=240, pps=12.0, editing=False, scenegraph=False, playback_active=True),
            "ultra",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=240, pps=12.0, editing=False, scenegraph=True),
            "gpu",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=240, pps=12.0, editing=True, scenegraph=False),
            "full",
        )

    def test_analysis_voice_and_silence_markers_use_distinct_colors(self):
        markers = editor_analysis_markers(
            [],
            [{"start": 0.0, "end": 1.0}],
            [{"start": 1.0, "end": 2.0}],
            2.0,
        )
        colors = {marker["label"]: marker["color"] for marker in markers}
        self.assertEqual(colors["음성"], "#34C759")
        self.assertEqual(colors["무음"], "#FF9500")

    def test_analysis_lane_contains_only_speech_and_silence_regions(self):
        markers = editor_analysis_markers(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "확인 필요",
                    "quality": {"confidence_label": "red", "confidence_score": 20},
                },
                {"start": 3.0, "end": 9.5, "text": "긴 자막입니다"},
            ],
            [],
            [{"start": 1.0, "end": 3.0}],
            5.0,
        )

        self.assertEqual([marker["kind"] for marker in markers], ["speech", "silence", "speech"])
        self.assertEqual([marker["label"] for marker in markers], ["음성", "무음", "음성"])
        self.assertNotIn("확인", {marker["label"] for marker in markers})
        self.assertNotIn("장문", {marker["label"] for marker in markers})

    def test_analysis_lane_links_silence_to_gap_segments_without_covering_subtitles(self):
        markers = editor_analysis_markers(
            [
                {"start": 2.0, "end": 4.0, "text": "자막"},
            ],
            [],
            [{"start": 0.0, "end": 6.0, "is_gap": True}],
            6.0,
        )

        self.assertEqual([marker["kind"] for marker in markers], ["silence", "speech", "silence"])
        self.assertEqual(
            [(round(marker["start"], 1), round(marker["end"], 1)) for marker in markers],
            [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)],
        )

    def test_analysis_lane_uses_explicit_gap_segments_as_silence_ranges(self):
        markers = editor_analysis_markers(
            [
                {"start": 0.0, "end": 1.0, "text": "앞"},
                {"start": 3.0, "end": 4.0, "text": "뒤"},
            ],
            [],
            [{"start": 1.0, "end": 3.0, "is_gap": True, "quality": {"linked_silence": True}}],
            4.0,
        )

        self.assertEqual([marker["kind"] for marker in markers], ["speech", "silence", "speech"])
        self.assertEqual((markers[1]["start"], markers[1]["end"], markers[1]["label"]), (1.0, 3.0, "무음"))

    def test_generation_silence_lane_is_separate_from_lower_audio_silence_lane(self):
        gap_segments = [{"start": 1.0, "end": 3.0, "is_gap": True, "quality": {"linked_silence": True}}]

        generation = subtitle_generation_silence_segments_for_editor(gap_segments, 4.0)
        detection = voice_activity_segments_for_editor([], [], gap_segments, 4.0)

        self.assertEqual(generation, [])
        self.assertEqual(
            detection,
            [{
                "start": 0.0,
                "end": 4.0,
                "kind": "idle",
                "label": "음성",
                "color": "#34C759",
                "priority": 0,
                "alpha": 92,
                "source": "subtitle_detection",
                "score": None,
                "selection_state": "",
            }],
        )

    def test_analysis_lane_keeps_short_silence_ranges_visible(self):
        markers = editor_analysis_markers(
            [
                {"start": 0.0, "end": 1.0, "text": "앞"},
                {"start": 1.12, "end": 2.0, "text": "뒤"},
            ],
            [],
            [{"start": 1.0, "end": 1.12, "is_gap": True}],
            2.0,
        )

        self.assertEqual([marker["kind"] for marker in markers], ["speech", "silence", "speech"])
        self.assertEqual((round(markers[1]["start"], 2), round(markers[1]["end"], 2)), (1.0, 1.12))

    def test_analysis_lane_generates_silence_from_vad_when_gap_segments_are_missing(self):
        markers = editor_analysis_markers(
            [],
            [{"start": 0.0, "end": 1.0, "kind": "speech"}, {"start": 3.0, "end": 4.0, "kind": "speech"}],
            [],
            4.0,
        )

        self.assertEqual([marker["kind"] for marker in markers], ["speech", "silence", "speech"])
        self.assertEqual((markers[1]["start"], markers[1]["end"]), (1.0, 3.0))

    def test_analysis_widget_lane_stays_voice_silence_even_when_roughcut_exists(self):
        result = SimpleNamespace(
            edit_decisions=[
                SimpleNamespace(source_start=0.0, source_end=2.0, action="remove", safety="risky"),
            ]
        )
        widget = SimpleNamespace(
            _editor_roughcut_result=result,
            parent=lambda: None,
            window=lambda: SimpleNamespace(_editor_roughcut_result=result),
        )

        markers = analysis_markers_for_widget(
            widget,
            [{"start": 0.0, "end": 1.0, "text": "앞"}],
            [],
            [{"start": 1.0, "end": 2.0, "is_gap": True}],
            2.0,
        )

        self.assertEqual([marker["label"] for marker in markers], ["음성", "무음"])

    def test_analysis_lane_defaults_to_speech_without_silence(self):
        markers = editor_analysis_markers([], [], [], 4.0)

        self.assertEqual(markers, [{
            "start": 0.0,
            "end": 4.0,
            "kind": "speech",
            "label": "음성",
            "color": "#34C759",
            "priority": 10,
            "alpha": 74,
        }])

    def test_subtitle_detection_segments_show_llm_choice_score_and_review_state(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "선택됨",
                "stt_ensemble_llm_selected_source": "STT2",
                "stt_candidates": [{"source": "STT2", "score": 0.82}],
            },
            {
                "start": 1.0,
                "end": 2.0,
                "text": "확인",
                "quality": {"confidence_label": "red", "confidence_score": 40},
            },
        ]

        voice_segments = voice_activity_segments_for_editor(segments, [], [], 2.0)

        self.assertTrue(all(voice_segments[i]["end"] <= voice_segments[i + 1]["start"] for i in range(len(voice_segments) - 1)))
        self.assertEqual(voice_segments[0]["kind"], "llm_selected")
        self.assertEqual(voice_segments[0]["source"], "STT2")
        self.assertEqual(voice_segments[0]["label"], "STT2 미확정 82점")
        self.assertEqual(voice_segments[0]["color"], COLORS["warning"])
        self.assertEqual(voice_segments[1]["kind"], "recheck")
        self.assertIn("재검사", voice_segments[1]["label"])
        self.assertEqual(voice_segments[1]["color"], "#FF453A")

    def test_subtitle_score_overlay_reuses_detection_label_without_bottom_box(self):
        seg = {
            "start": 1.0,
            "end": 2.0,
            "text": "재검사",
            "quality": {"confidence_label": "red", "confidence_score": 31},
        }

        marker = subtitle_score_overlay_marker(seg, recheck_threshold=60.0)

        self.assertEqual(marker["kind"], "recheck")
        self.assertEqual(marker["label"], "재검사 31점")
        self.assertEqual(marker["color"], "#FF453A")

    def test_subtitle_detection_conflict_state_is_gray(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "판단 필요",
                "stt_ensemble_needs_llm_review": True,
                "stt_candidates": [
                    {"source": "STT1", "text": "여기로 가자", "score": 0.84},
                    {"source": "STT2", "text": "이거로 하자", "score": 0.82},
                ],
            },
        ]

        voice_segments = voice_activity_segments_for_editor(segments, [], [], 1.0)

        self.assertEqual(voice_segments[0]["kind"], "conflict")
        self.assertIn("판단불가", voice_segments[0]["label"])
        self.assertEqual(voice_segments[0]["color"], "#8E8E93")

    def test_manual_confirmed_subtitle_detection_label_overrides_selection_needed(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "수정 확정",
                "stt_candidates": [
                    {"source": "STT1", "text": "수정 확전", "score": 0.8},
                    {"source": "STT2", "text": "수정 확정", "score": 0.7},
                ],
                "quality": {
                    "confidence_label": "green",
                    "confidence_score": 80,
                    "manual_confirmed": True,
                    "flags": ["manual_confirmed"],
                },
            },
        ]

        voice_segments = voice_activity_segments_for_editor(segments, [], [], 1.0)

        self.assertEqual(voice_segments[0]["kind"], "subtitle_confirmed")
        self.assertEqual(voice_segments[0]["label"], "자막확정")
        self.assertEqual(voice_segments[0]["color"], "#34C759")

    def test_subtitle_detection_idle_label_is_voice(self):
        voice_segments = voice_activity_segments_for_editor([], [], [], 1.0)

        self.assertEqual(voice_segments[0]["label"], "음성")
        self.assertEqual(voice_segments[0]["color"], "#34C759")

    def test_subtitle_detection_overlap_resolution_keeps_high_priority_window(self):
        with patch("ui.timeline.timeline_analysis._cached_recheck_threshold", return_value=60.0):
            voice_segments = voice_activity_segments_for_editor(
                [
                    {
                        "start": 0.0,
                        "end": 4.0,
                        "text": "낮은 우선순위",
                        "quality": {"confidence_label": "yellow", "confidence_score": 72},
                    },
                    {
                        "start": 1.0,
                        "end": 2.0,
                        "text": "재검사",
                        "quality": {"confidence_label": "red", "confidence_score": 31},
                    },
                ],
                [],
                [],
                4.0,
            )

        self.assertEqual(
            [(item["kind"], round(item["start"], 1), round(item["end"], 1)) for item in voice_segments],
            [
                ("subtitle_score", 0.0, 1.0),
                ("recheck", 1.0, 2.0),
                ("subtitle_score", 2.0, 4.0),
            ],
        )

    def test_subtitle_detection_large_dense_input_stays_compact(self):
        segments = [
            {
                "start": i * 0.5,
                "end": i * 0.5 + 0.5,
                "text": f"dense {i}",
                "quality": {"confidence_label": "yellow", "confidence_score": 75},
            }
            for i in range(2000)
        ]

        with patch("ui.timeline.timeline_analysis._cached_recheck_threshold", return_value=60.0):
            voice_segments = voice_activity_segments_for_editor(segments, [], [], 1000.0)

        self.assertEqual(len(voice_segments), 1)
        self.assertEqual(voice_segments[0]["kind"], "subtitle_score")
        self.assertEqual((voice_segments[0]["start"], voice_segments[0]["end"]), (0.0, 1000.0))

    def test_subtitle_detection_score_color_steps_from_red_to_green(self):
        self.assertEqual(subtitle_detection_color(0), "#FF453A")
        self.assertEqual(subtitle_detection_color(50), COLORS["warning"])
        self.assertEqual(subtitle_detection_color(100), "#34C759")

    def test_unselected_stt_candidate_keeps_source_fill(self):
        style = stt_preview_visual_style(
            {"start": 0.0, "end": 1.0, "text": "후보", "stt_score": 82},
            selection_state="unselected",
            fill_hex="#173524",
            border_hex="#34C759",
            text_hex="#D7FFE4",
        )

        self.assertEqual(style["fill"], "#173524")
        self.assertEqual(style["border"], "#34C759")
        self.assertEqual(style["alpha"], 96)

    def test_stt_preview_ignores_score_color_for_fill_and_border(self):
        white = stt_preview_visual_style(
            {"start": 0.0, "end": 1.0, "text": "후보", "stt_score_color": "#FFFFFF"},
            fill_hex="#173524",
            border_hex="#34C759",
            text_hex="#D7FFE4",
        )
        gray = stt_preview_visual_style(
            {"start": 0.0, "end": 1.0, "text": "후보", "stt_score_color": "#8E8E93"},
            fill_hex="#173524",
            border_hex="#34C759",
            text_hex="#D7FFE4",
        )

        self.assertEqual(white["fill"], "#173524")
        self.assertEqual(gray["fill"], "#173524")
        self.assertEqual(white["border"], "#34C759")
        self.assertEqual(gray["border"], "#34C759")

    def test_stt1_only_preview_keeps_fixed_source_color_without_score_gradient(self):
        high = stt_preview_visual_style(
            {"start": 0.0, "end": 1.0, "text": "STT1 단독 고점", "stt_preview_source": "STT1", "stt_score": 100},
            fill_hex="#173524",
            border_hex="#34C759",
            text_hex="#D7FFE4",
        )
        low = stt_preview_visual_style(
            {"start": 1.0, "end": 2.0, "text": "STT1 단독 저점", "stt_preview_source": "STT1", "stt_score": 0},
            fill_hex="#173524",
            border_hex="#34C759",
            text_hex="#D7FFE4",
        )

        self.assertEqual(high["fill"], "#173524")
        self.assertEqual(high["border"], "#34C759")
        self.assertEqual(low["fill"], "#173524")
        self.assertEqual(low["border"], "#34C759")

    def test_stt_checked_sources_include_candidate_and_recheck_metadata(self):
        sources = stt_checked_sources(
            {
                "start": 0.0,
                "end": 1.0,
                "text": "최종",
                "stt_selected_source": "STT1",
                "stt_candidates": [{"source": "STT1"}, {"source": "STT2"}],
                "stt_recheck_original_scores": {"STT2": 82},
            }
        )

        self.assertEqual(sources, frozenset({"STT1", "STT2"}))
        self.assertEqual(
            stt_checked_source({"stt_candidates": [{"source": "STT2", "score": 0.82}]}),
            "STT2",
        )

    def test_stt_preview_does_not_use_quality_score_for_color(self):
        style = stt_preview_visual_style(
            {
                "start": 0.0,
                "end": 1.0,
                "text": "점수 후보",
                "stt_preview_source": "STT1",
                "quality": {"confidence_score": 76},
            },
            fill_hex="#173524",
            border_hex="#34C759",
            text_hex="#D7FFE4",
        )

        self.assertEqual(style["fill"], "#173524")
        self.assertEqual(style["border"], "#34C759")

    def test_scan_boundary_visual_distinguishes_provisional_from_verified(self):
        provisional = scan_boundary_marker_visual({"timeline_sec": 1.2, "status": "provisional"})
        verified = scan_boundary_marker_visual({"timeline_sec": 1.2, "status": "checked", "scan_checked": True})

        self.assertEqual(provisional, {"color": "#00B7FF", "width": 1, "style": "solid"})
        self.assertEqual(verified, {"color": "#8E8E93", "width": 1, "style": "dot"})

    def test_scan_boundary_visual_uses_audio_gain_neon_green_hint(self):
        style = scan_boundary_marker_visual(
            {
                "timeline_sec": 1.2,
                "status": "provisional",
                "source": "audio_gain_provisional",
                "line_color": "#39FF14",
                "line_style": "solid",
            }
        )

        self.assertEqual(style, {"color": "#39FF14", "width": 1, "style": "solid"})

    def test_scan_boundary_visual_honors_gray_dotted_provisional_style(self):
        style = scan_boundary_marker_visual(
            {"timeline_sec": 1.2, "status": "provisional", "line_color": "gray", "line_style": "dotted"}
        )

        self.assertEqual(style, {"color": "#8E8E93", "width": 1, "style": "dot"})

    def test_scan_boundary_hover_uses_neon_blue_highlight(self):
        style = scan_boundary_marker_visual({"timeline_sec": 1.2, "status": "verified"}, hover=True)

        self.assertEqual(style, {"color": "#00B7FF", "width": 3, "style": "solid"})

    def test_official_boundary_visual_hides_stale_audio_provisional_paint(self):
        style = official_boundary_marker_visual(
            {
                "timeline_sec": 180.21336750307566,
                "timeline_frame": 10802,
                "source": "visual",
                "status": "verified",
                "verified": True,
                "boundary_kind": "audio",
                "provisional_type": "audio_gain",
                "line_color": "#39FF14",
                "line_style": "solid",
            }
        )

        self.assertFalse(style.get("visible", True))

    def test_official_boundary_visual_hides_checked_audio_provisional_rows(self):
        style = official_boundary_marker_visual(
            {
                "timeline_sec": 613.346,
                "timeline_frame": 36796,
                "source": "audio_gain_provisional",
                "status": "checked",
                "scan_checked": True,
                "boundary_kind": "audio",
                "line_color": "#39FF14",
            }
        )

        self.assertFalse(style.get("visible", True))

    def test_official_boundary_visual_hides_sanitized_verified_auto_rows(self):
        style = official_boundary_marker_visual(
            {
                "timeline_sec": 648.048,
                "timeline_frame": 38964,
                "source": "visual",
                "reason": "visual_cut_boundary",
                "verified": True,
                "cut_boundary_algorithm_id": "cut_boundary_auto",
            }
        )

        self.assertFalse(style.get("visible", True))

    def test_official_boundary_visual_keeps_non_cut_verified_visual_rows(self):
        style = official_boundary_marker_visual(
            {
                "timeline_sec": 648.048,
                "timeline_frame": 38964,
                "source": "visual",
                "reason": "verified_reference_marker",
                "verified": True,
                "line_color": "#F5F7FA",
            }
        )

        self.assertEqual(style, {"color": "#F5F7FA", "width": 1, "style": "solid"})

    def test_official_boundary_visual_hides_terminal_end_rows(self):
        style = official_boundary_marker_visual(
            {
                "timeline_sec": 904.13,
                "source": "visual",
                "status": "confirmed",
                "reason": "timeline_end_frame",
                "timeline_end_boundary": True,
            }
        )

        self.assertFalse(style.get("visible", True))

    def test_scan_boundary_visual_marks_follower_work_without_blue_confirmed_line(self):
        style = scan_boundary_marker_visual(
            {
                "timeline_sec": 1.2,
                "status": "verifying",
                "detector_stage": "follower",
                "follower_active": True,
            }
        )

        self.assertEqual(style, {"color": COLORS["warning"], "width": 2, "style": "dash"})

    def test_scan_boundary_labels_keep_temporary_and_audio_as_lines_only(self):
        self.assertEqual(
            scan_boundary_marker_label(
                {
                    "timeline_sec": 1.2,
                    "status": "provisional",
                    "source": "audio_gain_provisional",
                }
            ),
            "",
        )
        self.assertEqual(
            scan_boundary_marker_label(
                {
                    "timeline_sec": 1.2,
                    "status": "provisional",
                    "source": "visual_provisional",
                }
            ),
            "",
        )
        self.assertEqual(
            scan_boundary_marker_label(
                {
                    "timeline_sec": 1.2,
                    "status": "verifying",
                    "detector_stage": "follower",
                    "follower_active": True,
                }
            ),
            "",
        )

    def test_roughcut_major_markers_accept_project_dict_segments(self):
        markers = roughcut_major_markers(
            {
                "segments": [
                    {
                        "major_id": "A",
                        "title": "주제없음",
                        "start": 0.0,
                        "end": 10.0,
                        "status": "provisional",
                    }
                ]
            }
        )

        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["label"], "A")
        self.assertEqual(markers[0]["title"], "주제없음")
        self.assertEqual(markers[0]["display_label"], "A")

    def test_roughcut_major_markers_prefer_explicit_display_and_color(self):
        markers = roughcut_major_markers(
            {
                "segments": [
                    {
                        "major_id": "A",
                        "title": "주제없음",
                        "display_title": "A - 주제없음",
                        "color": "#8E8E93",
                        "start": 0.0,
                        "end": 10.0,
                        "status": "needs_review",
                        "is_topicless_placeholder": True,
                    }
                ]
            }
        )

        self.assertEqual(markers[0]["display_label"], "A - 주제없음")
        self.assertEqual(markers[0]["color"], "#8E8E93")
        self.assertNotEqual(markers[0]["color"], roughcut_major_color("A", 0))

    def test_roughcut_major_markers_expose_display_label_with_topic(self):
        markers = roughcut_major_markers(
            {
                "segments": [
                    {
                        "major_id": "B",
                        "title": "X5 실내인테리어 소개 부분",
                        "start": 10.0,
                        "end": 22.0,
                        "status": "confirmed",
                    }
                ]
            }
        )

        self.assertEqual(markers[0]["label"], "B")
        self.assertEqual(markers[0]["display_label"], "B - X5 실내인테리어 소개 부분")
        self.assertEqual(markers[0]["color"], roughcut_major_color("B", 0))

    def test_roughcut_major_palette_has_distinct_a_to_z_colors(self):
        colors = [roughcut_major_color(chr(65 + i), i) for i in range(26)]

        self.assertEqual(len(MAJOR_SEGMENT_COLORS), 26)
        self.assertEqual(len(set(colors)), 26)
        self.assertEqual(colors, list(MAJOR_SEGMENT_COLORS))

    def test_roughcut_paint_markers_merge_adjacent_identical_rows(self):
        markers = [
            {
                "kind": "roughcut_major",
                "label": "A",
                "display_label": "A",
                "color": "#34C759",
                "start": 0.0,
                "end": 1.0,
            },
            {
                "kind": "roughcut_major",
                "label": "A",
                "display_label": "A",
                "color": "#34C759",
                "start": 1.01,
                "end": 2.0,
            },
            {
                "kind": "roughcut_major",
                "label": "B",
                "display_label": "B",
                "color": "#34C759",
                "start": 2.01,
                "end": 3.0,
            },
        ]

        merged = coalesce_roughcut_paint_markers(markers, pps=100.0, max_gap_px=2.0)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["start"], 0.0)
        self.assertEqual(merged[0]["end"], 2.0)
        self.assertEqual(merged[1]["label"], "B")

    def test_roughcut_label_span_pins_to_visible_marker_area(self):
        self.assertEqual(
            visible_roughcut_label_span(0, 5000, clip_left=3400, clip_right=4300),
            (3408, 4292),
        )
        self.assertIsNone(
            visible_roughcut_label_span(0, 5000, clip_left=3400, clip_right=3435),
        )

    def test_roughcut_paint_markers_do_not_merge_different_statuses(self):
        markers = [
            {
                "kind": "roughcut_major",
                "label": "A",
                "status": "confirmed",
                "color": "#34C759",
                "start": 0.0,
                "end": 1.0,
            },
            {
                "kind": "roughcut_major",
                "label": "A",
                "status": "needs_review",
                "color": "#34C759",
                "start": 1.0,
                "end": 2.0,
            },
        ]

        merged = coalesce_roughcut_paint_markers(markers, pps=100.0, max_gap_px=2.0)

        self.assertEqual(len(merged), 2)

    def test_roughcut_cut_safety_labels_and_colors_are_distinct(self):
        result = SimpleNamespace(
            edit_decisions=[
                SimpleNamespace(source_start=0.0, source_end=1.0, action="keep", safety="ideal"),
                SimpleNamespace(source_start=1.0, source_end=2.0, action="keep", safety="acceptable"),
                SimpleNamespace(source_start=2.0, source_end=3.0, action="keep", safety="risky"),
            ]
        )

        markers = roughcut_markers(result)

        self.assertEqual([marker["label"] for marker in markers], ["정상", "주의", "위험"])
        self.assertEqual([marker["color"] for marker in markers], ["#34C759", COLORS["warning"], "#FF453A"])


if __name__ == "__main__":
    unittest.main()
