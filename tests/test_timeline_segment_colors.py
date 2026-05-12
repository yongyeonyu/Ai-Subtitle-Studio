# Version: 03.09.29
# Phase: PHASE2
import unittest
from types import SimpleNamespace

from core.audio.stt_candidate_scorer import stt_score_to_color
from ui.timeline.timeline_paint import (
    SEGMENT_TEXT_KIND_STYLES,
    scan_boundary_marker_label,
    segment_text_kind,
    scan_boundary_marker_visual,
    subtitle_confidence_chips,
    subtitle_render_detail_mode,
    subtitle_segment_visual_style,
    stt_preview_visual_style,
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
    voice_activity_segments_for_editor,
)


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
        self.assertEqual(compact_style["fill"], "#4A1F24")
        self.assertEqual(compact_style["border"], "#FF453A")

    def test_subtitle_segment_visual_style_keeps_text_kind_over_zoom(self):
        seg = {"start": 0.0, "end": 1.0, "text": "음성"}

        style = subtitle_segment_visual_style(seg, active=True, hover=True, quality_filter="all")

        self.assertEqual(style["fill"], SEGMENT_TEXT_KIND_STYLES["speech"]["fill"])
        self.assertEqual(style["border"], SEGMENT_TEXT_KIND_STYLES["speech"]["border"])

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

        self.assertEqual(style["fill"], "#203A2A")
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

        self.assertEqual(style["fill"], "#3B341D")
        self.assertEqual(style["border"], "#FFCC00")
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
        self.assertEqual(style["fill"], "#3B341D")
        self.assertEqual(style["border"], "#FFCC00")

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
        self.assertEqual(style["fill"], "#4A1F24")
        self.assertEqual(style["border"], "#FF453A")

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
        self.assertEqual(style["fill"], "#2F343A")
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
        self.assertEqual(style["fill"], "#203A2A")
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
        self.assertEqual(chips[1]["color"], "#FFCC00")
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
            "dense",
        )
        self.assertEqual(
            subtitle_render_detail_mode(visible_segment_count=48, pps=20.0, editing=False, scenegraph=False, playback_active=True),
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

        self.assertEqual(
            generation,
            [{
                "start": 1.0,
                "end": 3.0,
                "kind": "generation_silence",
                "label": "무음구간",
                "color": "#FF6B6B",
                "priority": 78,
                "alpha": 138,
            }],
        )
        self.assertTrue(any(item["kind"] == "linked_silence" for item in detection))
        self.assertEqual(
            detection,
            [{
                "start": 1.0,
                "end": 3.0,
                "kind": "linked_silence",
                "label": "무음",
                "color": "#34C759",
                "priority": 82,
                "alpha": 142,
                "source": "silence",
                "score": None,
                "selection_state": "linked_silence",
            }],
        )
        self.assertNotEqual(generation[0]["label"], detection[0]["label"])

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
        self.assertEqual(voice_segments[0]["color"], "#FFCC00")
        self.assertEqual(voice_segments[1]["kind"], "recheck")
        self.assertIn("재검사", voice_segments[1]["label"])
        self.assertEqual(voice_segments[1]["color"], "#FF453A")

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

        voice_segments = voice_activity_segments_for_editor(segments, [], [], 1000.0)

        self.assertEqual(len(voice_segments), 1)
        self.assertEqual(voice_segments[0]["kind"], "subtitle_score")
        self.assertEqual((voice_segments[0]["start"], voice_segments[0]["end"]), (0.0, 1000.0))

    def test_subtitle_detection_score_color_steps_from_red_to_green(self):
        self.assertEqual(subtitle_detection_color(0), "#FF453A")
        self.assertEqual(subtitle_detection_color(50), "#FFCC00")
        self.assertEqual(subtitle_detection_color(100), "#34C759")

    def test_unselected_stt_candidate_keeps_score_color(self):
        style = stt_preview_visual_style(
            {"start": 0.0, "end": 1.0, "text": "후보", "stt_score": 82},
            selection_state="unselected",
            fill_hex="#173524",
            border_hex="#34C759",
            text_hex="#D7FFE4",
        )

        self.assertEqual(style["fill"], subtitle_detection_color(82))
        self.assertEqual(style["border"], subtitle_detection_color(82))
        self.assertEqual(style["alpha"], 96)

    def test_stt1_only_preview_uses_score_gradient_without_stt2(self):
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

        self.assertEqual(high["fill"], stt_score_to_color(100))
        self.assertEqual(high["border"], stt_score_to_color(100))
        self.assertEqual(low["fill"], stt_score_to_color(0))
        self.assertEqual(low["border"], stt_score_to_color(0))

    def test_stt_preview_can_fallback_to_quality_score_for_color(self):
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

        self.assertEqual(style["fill"], stt_score_to_color(76))
        self.assertEqual(style["border"], stt_score_to_color(76))

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

    def test_scan_boundary_visual_marks_follower_work_without_blue_confirmed_line(self):
        style = scan_boundary_marker_visual(
            {
                "timeline_sec": 1.2,
                "status": "verifying",
                "detector_stage": "follower",
                "follower_active": True,
            }
        )

        self.assertEqual(style, {"color": "#FFCC00", "width": 2, "style": "dash"})

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
        self.assertEqual([marker["color"] for marker in markers], ["#34C759", "#FFCC00", "#FF453A"])


if __name__ == "__main__":
    unittest.main()
