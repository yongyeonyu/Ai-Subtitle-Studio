# Version: 03.24.01
# Phase: PHASE2
import json
import unittest
from unittest import mock

from core.roughcut.editor_draft import build_editor_roughcut_draft_prompt
from core.roughcut import (
    DEFAULT_ROUGHCUT_PROMPT_V1,
    RoughCutDraftState,
    RoughCutSegment,
    RoughCutMinorGroup,
    SubtitleSegment,
    RoughCutTitleSuggestion,
    apply_major_topic_labels,
    build_roughcut_prompt,
    merge_roughcut_settings,
    roughcut_result_from_dict,
    resolve_roughcut_context_policy,
    resolve_roughcut_llm_config,
    run_roughcut_llm_action,
    trim_roughcut_payload_for_context,
)


class RoughCutModelsV2Tests(unittest.TestCase):
    def test_roughcut_result_restores_v1_payload_with_v2_defaults(self):
        result = roughcut_result_from_dict({
            "segments": [{"segment_id": "chapter_0001", "start": 0.0, "end": 2.0}],
            "chapters": [{"chapter_id": "chapter_0001", "title": "소개", "start": 0.0, "end": 2.0}],
            "edl": [{
                "source_path": "sample.mp4",
                "segment_id": "chapter_0001",
                "source_start": 0.0,
                "source_end": 2.0,
                "output_start": 0.0,
                "output_end": 2.0,
            }],
            "markdown_guide": "# guide",
        })

        self.assertEqual(result.schema_version, "roughcut_result.v1")
        self.assertEqual(result.markdown_guide, "# guide")
        self.assertEqual(result.segments[0].status, "confirmed")
        self.assertEqual(result.segments[0].minor_groups, ())

    def test_roughcut_result_restores_v2_minor_title_and_draft_state(self):
        result = roughcut_result_from_dict({
            "schema_version": "roughcut_result.v2",
            "segments": [{
                "segment_id": "major_A",
                "start": 0.0,
                "end": 10.0,
                "major_id": "A",
                "minor_groups": [{
                    "minor_id": "A1",
                    "major_id": "A",
                    "code": "A1",
                    "title": "외부",
                    "start": 0.0,
                    "end": 4.0,
                    "subtitle_ids": [1, 2],
                    "chapter_ids": ["chapter_0001"],
                    "tags": ["외부"],
                }],
            }],
            "chapters": [{
                "chapter_id": "chapter_0001",
                "title": "외부",
                "start": 0.0,
                "end": 4.0,
                "major_id": "A",
                "minor_code": "A1",
                "confidence": 0.82,
                "boundary_status": "provisional",
            }],
            "title_suggestions": [{
                "title_id": "title_001",
                "title": "EV6 외부 리뷰",
                "score": 0.91,
                "tags": ["EV6", "외부"],
            }],
            "draft_state": {
                "draft_id": "draft_001",
                "status": "review",
                "selected_major_id": "A",
            },
        })

        self.assertEqual(result.schema_version, "roughcut_result.v2")
        self.assertIsInstance(result.segments[0].minor_groups[0], RoughCutMinorGroup)
        self.assertEqual(result.chapters[0].minor_code, "A1")
        self.assertIsInstance(result.title_suggestions[0], RoughCutTitleSuggestion)
        self.assertIsInstance(result.draft_state, RoughCutDraftState)
        self.assertEqual(result.draft_state.selected_major_id, "A")

    def test_roughcut_settings_and_llm_fallback_contract(self):
        settings = merge_roughcut_settings({"roughcut_llm_enabled": False})
        prompt = build_roughcut_prompt("propose_major_segment", {"chunks": []}, token_budget=128)
        result = run_roughcut_llm_action("propose_major_segment", {"chunks": []}, settings=settings)

        self.assertIn("propose_major_segment", prompt)
        self.assertIn("중분류는 실제 러프컷 편집 최소 단위", prompt)
        self.assertIn("화면 전환, 주제 전환, 장소 전환", prompt)
        self.assertFalse(result.ok)
        self.assertFalse(result.used_llm)
        self.assertEqual(result.error, "llm_disabled")

    def test_roughcut_llm_config_inherits_or_overrides_subtitle_model(self):
        inherited = resolve_roughcut_llm_config({
            "selected_llm_provider": "openai",
            "selected_model": "gpt-test",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": False,
        })
        self.assertTrue(inherited.enabled)
        self.assertEqual(inherited.provider, "openai")
        self.assertEqual(inherited.model, "gpt-test")
        self.assertIn("응답은 반드시 JSON", inherited.prompt)

        override = resolve_roughcut_llm_config({
            "selected_llm_provider": "openai",
            "selected_model": "gpt-test",
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "exaone-test",
            "roughcut_llm_prompt": "custom roughcut prompt",
            "roughcut_llm_temperature": 1.5,
            "roughcut_llm_threads_auto_enabled": False,
            "roughcut_llm_threads": 7,
        })
        self.assertEqual(override.provider, "ollama")
        self.assertEqual(override.model, "exaone-test")
        self.assertEqual(override.prompt, "custom roughcut prompt")
        self.assertEqual(override.temperature, 1.0)
        self.assertEqual(override.threads, 7)
        self.assertTrue(override.context_policy["auto_enabled"])
        self.assertIn("중분류 A/B/C/D", DEFAULT_ROUGHCUT_PROMPT_V1)
        self.assertIn("합치거나 분리할 수 있다", DEFAULT_ROUGHCUT_PROMPT_V1)
        self.assertIn("자막 전체와 영상 흐름을 이해", DEFAULT_ROUGHCUT_PROMPT_V1)
        self.assertIn("실외에서 실내로 들어가거나", DEFAULT_ROUGHCUT_PROMPT_V1)
        self.assertIn("음향 환경 전환도 강한 중분류 후보", DEFAULT_ROUGHCUT_PROMPT_V1)
        self.assertIn("단순한 말 끊김", DEFAULT_ROUGHCUT_PROMPT_V1)

    def test_editor_roughcut_prompt_treats_reference_middle_segments_as_revisable(self):
        prompt = json.loads(
            build_editor_roughcut_draft_prompt(
                [
                    {"start": 0.0, "end": 2.0, "text": "도입 설명"},
                    {"start": 2.0, "end": 4.0, "text": "실내 기능 소개"},
                ],
                reference_major_segments=[
                    {
                        "major_id": "A",
                        "title": "임시 중분류",
                        "summary": "초안",
                        "start": 0.0,
                        "end": 4.0,
                        "tags": ["초안"],
                    }
                ],
            )
        )

        instructions = prompt["editor_instructions"]
        self.assertIn("reference_major_segments는 고정 답안이 아니라 참고 초안", instructions)
        self.assertIn("필요하면 여러 구간을 합치거나 하나를 둘 이상으로 분리", instructions)
        self.assertIn("최종 판단 기준은 reference가 아니라 전체 subtitle_rows", instructions)
        self.assertIn("실외→실내", instructions)
        self.assertIn("1. subtitle_rows 전체를 끝까지 읽고 전체 내용을 확인한다.", instructions)
        self.assertEqual(prompt["reference_major_segments"][0]["tags"], ["초안"])

    def test_roughcut_context_policy_uses_lora_deep_auto_rows(self):
        payload = {
            "chunks": [
                {"start": float(index * 3), "end": float(index * 3 + 2), "text": f"row {index}"}
                for index in range(140)
            ],
            "cut_boundaries": [{"time": 30.0}, {"time": 60.0}, {"time": 90.0}, {"time": 120.0}],
        }

        policy = resolve_roughcut_context_policy(
            {
                "roughcut_llm_rows_auto_enabled": True,
                "roughcut_llm_rows_lora_enabled": True,
                "roughcut_llm_rows_lora_blend": 0.25,
                "roughcut_llm_max_context_rows": 96,
                "roughcut_llm_chunk_rows": 10,
                "roughcut_llm_lookahead_rows": 6,
                "roughcut_llm_rows_exploration_rate": 0.0,
            },
            payload=payload,
        )

        self.assertTrue(policy["auto_enabled"])
        self.assertGreaterEqual(policy["max_context_rows"], 96)
        self.assertLessEqual(policy["max_context_rows"], 160)
        self.assertGreaterEqual(policy["chunk_rows"], 8)
        self.assertIn("lora_blend", policy["reason"])

        trimmed = trim_roughcut_payload_for_context(payload, policy)
        self.assertLessEqual(len(trimmed["chunks"]), policy["max_context_rows"])
        self.assertIn("_roughcut_context_policy", trimmed)

    def test_roughcut_context_policy_keeps_manual_compat_when_auto_disabled(self):
        policy = resolve_roughcut_context_policy(
            {
                "roughcut_llm_rows_auto_enabled": False,
                "roughcut_llm_max_context_rows": 5,
                "roughcut_llm_chunk_rows": 3,
                "roughcut_llm_lookahead_rows": 2,
            },
            subtitle_rows=[{"text": "a"} for _ in range(12)],
        )

        self.assertFalse(policy["auto_enabled"])
        self.assertEqual(policy["max_context_rows"], 5)
        self.assertEqual(policy["chunk_rows"], 3)
        self.assertEqual(policy["lookahead_rows"], 2)

    def test_roughcut_action_unloads_different_subtitle_ollama_before_loading_roughcut(self):
        settings = {
            "selected_llm_provider": "ollama",
            "selected_model": "subtitle-local",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "roughcut-local",
        }

        with mock.patch("core.roughcut.roughcut_llm.running_local_llm_models", return_value={"subtitle-local"}), \
             mock.patch("core.roughcut.roughcut_llm.stop_local_llm_models", return_value=["subtitle-local"]) as stop_llm, \
             mock.patch("core.roughcut.roughcut_llm.warmup_model") as warmup, \
             mock.patch("core.roughcut.roughcut_llm._clear_runtime_memory_caches") as clear_memory, \
             mock.patch(
                 "core.roughcut.roughcut_llm._default_roughcut_llm_client",
                 return_value=lambda _prompt: {"titles": []},
             ):
            result = run_roughcut_llm_action("title_suggestions", {}, settings=settings)

        self.assertTrue(result.ok)
        self.assertTrue(result.used_llm)
        stop_llm.assert_called_once()
        self.assertEqual(stop_llm.call_args.args[0], ["subtitle-local"])
        self.assertEqual(stop_llm.call_args.kwargs["log_context"], "러프컷 LLM 전환")
        clear_memory.assert_called_once()
        warmup.assert_called_once()
        self.assertEqual(warmup.call_args.args[0], "roughcut-local")

    def test_roughcut_action_keeps_loaded_roughcut_model_for_followup_actions(self):
        settings = {
            "selected_llm_provider": "ollama",
            "selected_model": "subtitle-local",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "roughcut-local",
        }

        with mock.patch("core.roughcut.roughcut_llm.running_local_llm_models", return_value={"roughcut-local"}), \
             mock.patch("core.roughcut.roughcut_llm.stop_local_llm_models") as stop_llm, \
             mock.patch("core.roughcut.roughcut_llm.warmup_model") as warmup, \
             mock.patch("core.roughcut.roughcut_llm._clear_runtime_memory_caches") as clear_memory, \
             mock.patch(
                 "core.roughcut.roughcut_llm._default_roughcut_llm_client",
                 return_value=lambda _prompt: {"titles": []},
             ):
            result = run_roughcut_llm_action("title_suggestions", {}, settings=settings)

        self.assertTrue(result.ok)
        stop_llm.assert_not_called()
        clear_memory.assert_not_called()
        warmup.assert_not_called()

    def test_roughcut_action_does_not_unload_for_cloud_subtitle_model(self):
        settings = {
            "selected_llm_provider": "openai",
            "selected_model": "custom-openai-deployment",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "roughcut-local",
        }

        with mock.patch("core.roughcut.roughcut_llm.running_local_llm_models") as running, \
             mock.patch("core.roughcut.roughcut_llm.stop_local_llm_models") as stop_llm, \
             mock.patch("core.roughcut.roughcut_llm.warmup_model") as warmup, \
             mock.patch(
                 "core.roughcut.roughcut_llm._default_roughcut_llm_client",
                 return_value=lambda _prompt: {"titles": []},
             ):
            result = run_roughcut_llm_action("title_suggestions", {}, settings=settings)

        self.assertTrue(result.ok)
        running.assert_not_called()
        stop_llm.assert_not_called()
        warmup.assert_not_called()

    def test_major_topic_labels_use_all_subtitles_for_one_line_major_title(self):
        captured = {}

        def llm_client(prompt: str):
            captured["prompt"] = json.loads(prompt)
            payload = captured["prompt"]["payload"]
            major = payload["major_segments"][0]
            rows = major["subtitle_rows"]
            self.assertEqual([row["text"] for row in rows], [
                "오늘은 카메라를 들고 촬영을 시작합니다",
                "렌즈 선택과 조명 세팅을 먼저 확인합니다",
                "야간 촬영에서 노이즈를 줄이는 방법을 봅니다",
            ])
            self.assertEqual(major["topic_level"], "middle_category")
            self.assertEqual(major["candidate_topic_hint"], "촬영 장비 세팅")
            self.assertIn("중분류 주제", payload["task_instruction"])
            self.assertIn("14~30자", payload["task_instruction"])
            self.assertIn("더 일반적인 표현으로 축약하지 말고", payload["task_instruction"])
            self.assertIn("tags도 반드시 함께 작성", payload["task_instruction"])
            self.assertIn("tags", captured["prompt"]["output_contract"]["schema"]["item_recommended"])
            return {
                "topics": [
                    {
                        "major_id": "A",
                        "topic": "야간 촬영 장비 세팅",
                        "summary": "카메라 렌즈와 조명을 준비해 야간 촬영 품질을 높이는 구간",
                        "tags": ["카메라", "야간촬영"],
                    }
                ]
            }

        segments = (
            RoughCutSegment(
                segment_id="A",
                major_id="A",
                start=0.0,
                end=6.0,
                subtitle_ids=(0, 1, 2),
                title="오늘은 카메라를 들고 촬영을 시작합니다",
            ),
        )
        subtitles = (
            SubtitleSegment(0.0, 1.5, "오늘은 카메라를 들고 촬영을 시작합니다", subtitle_id=0),
            SubtitleSegment(2.0, 3.5, "렌즈 선택과 조명 세팅을 먼저 확인합니다", subtitle_id=1),
            SubtitleSegment(4.0, 5.5, "야간 촬영에서 노이즈를 줄이는 방법을 봅니다", subtitle_id=2),
        )

        labeled = apply_major_topic_labels(
            segments,
            subtitles,
            settings={"roughcut_llm_enabled": True},
            llm_client=llm_client,
        )

        self.assertEqual(labeled[0].title, "야간 촬영 장비 세팅")
        self.assertEqual(labeled[0].summary, "카메라 렌즈와 조명을 준비해 야간 촬영 품질을 높이는 구간")
        self.assertEqual(labeled[0].tags, ("카메라", "야간촬영"))

    def test_major_topic_labels_normalize_string_tags_from_llm(self):
        segments = (
            RoughCutSegment(
                segment_id="A",
                major_id="A",
                start=0.0,
                end=6.0,
                subtitle_ids=(0, 1, 2),
                title="실내 소개",
            ),
        )
        subtitles = (
            SubtitleSegment(0.0, 1.5, "시트 착좌감과 조절 기능을 먼저 봅니다", subtitle_id=0),
            SubtitleSegment(2.0, 3.5, "센터패시아와 수납 구성도 함께 확인합니다", subtitle_id=1),
            SubtitleSegment(4.0, 5.5, "실내 마감과 디자인 특징을 정리합니다", subtitle_id=2),
        )

        labeled = apply_major_topic_labels(
            segments,
            subtitles,
            settings={"roughcut_llm_enabled": True},
            llm_client=lambda _prompt: {
                "topics": [
                    {
                        "major_id": "A",
                        "topic": "차량 실내 리뷰",
                        "summary": "실내 편의와 마감 포인트를 정리하는 구간",
                        "tags": "시트, 기능, 디자인 특징, 수납공간",
                    }
                ]
            },
        )

        self.assertEqual(labeled[0].tags, ("시트", "기능", "디자인 특징", "수납공간"))

    def test_major_topic_labels_do_not_accept_raw_first_subtitle_copy(self):
        first_text = "오늘은 BMW 차량 외장 디자인을 자세히 살펴보겠습니다"
        segments = (
            RoughCutSegment(
                segment_id="A",
                major_id="A",
                start=0.0,
                end=4.0,
                subtitle_ids=(0, 1),
                title=first_text,
            ),
        )
        subtitles = (
            SubtitleSegment(0.0, 1.5, first_text, subtitle_id=0),
            SubtitleSegment(2.0, 3.5, "그릴과 헤드램프의 변화 포인트를 비교합니다", subtitle_id=1),
        )

        labeled = apply_major_topic_labels(
            segments,
            subtitles,
            settings={"roughcut_llm_enabled": True},
            llm_client=lambda _prompt: {"topics": [{"major_id": "A", "topic": first_text}]},
        )

        self.assertNotEqual(labeled[0].title, first_text)
        self.assertEqual(labeled[0].title, "BMW 차량 외장 디자인 점검")

    def test_major_topic_labels_replace_generic_llm_topic_with_middle_category(self):
        captured = {}
        segments = (
            RoughCutSegment(
                segment_id="A",
                major_id="A",
                start=0.0,
                end=8.0,
                subtitle_ids=(0, 1, 2),
                title="오늘은 이 차량 고속 주행 연비를 확인합니다",
            ),
        )
        subtitles = (
            SubtitleSegment(0.0, 2.0, "오늘은 이 차량 고속 주행 연비를 확인합니다", subtitle_id=0),
            SubtitleSegment(2.2, 4.5, "리터당 17.8km가 나왔고 효율이 꽤 좋습니다", subtitle_id=1),
            SubtitleSegment(5.0, 7.0, "주유 후 같은 구간을 다시 달리면서 수치를 비교합니다", subtitle_id=2),
        )

        def llm_client(prompt: str):
            captured["prompt"] = json.loads(prompt)
            major = captured["prompt"]["payload"]["major_segments"][0]
            self.assertEqual(major["candidate_topic_hint"], "주행 연비 평가")
            return {"topics": [{"major_id": "A", "topic": "리뷰"}]}

        labeled = apply_major_topic_labels(
            segments,
            subtitles,
            settings={"roughcut_llm_enabled": True},
            llm_client=llm_client,
        )

        self.assertEqual(labeled[0].title, "차량 고속 주행 연비 확인")

    def test_major_topic_labels_fall_back_to_subtitle_topics_when_llm_disabled(self):
        segments = (
            RoughCutSegment(
                segment_id="A",
                major_id="A",
                start=0.0,
                end=8.0,
                subtitle_ids=(0, 1, 2),
                title="주제없음",
            ),
        )
        subtitles = (
            SubtitleSegment(0.0, 2.0, "이제 BMW X5 실내 버튼 구성과 수납 공간을 살펴보겠습니다", subtitle_id=0),
            SubtitleSegment(2.2, 4.5, "센터 디스플레이와 시트 조작 편의성도 함께 확인합니다", subtitle_id=1),
            SubtitleSegment(5.0, 7.0, "뒷좌석 공간과 실내 마감 품질까지 정리합니다", subtitle_id=2),
        )

        labeled = apply_major_topic_labels(
            segments,
            subtitles,
            settings={"roughcut_llm_enabled": False},
        )

        self.assertEqual(labeled[0].title, "BMW X5 실내 버튼 구성과 수납 공간 점검")
        self.assertIn("실내", labeled[0].summary)

    def test_major_topic_labels_keep_specific_existing_title_when_llm_phrase_is_broader(self):
        segments = (
            RoughCutSegment(
                segment_id="A",
                major_id="A",
                start=0.0,
                end=7.0,
                subtitle_ids=(0, 1, 2),
                title="현대모토 스튜디오 넥소 전시 공개",
            ),
        )
        subtitles = (
            SubtitleSegment(0.0, 2.0, "현대모토 스튜디오에 도착해서 올해 전시를 보러 왔습니다", subtitle_id=0),
            SubtitleSegment(2.2, 4.5, "이번에는 넥소 전시가 메인이라 바로 공개 구역으로 이동합니다", subtitle_id=1),
            SubtitleSegment(5.0, 6.5, "넥소 공개 포인트와 전시장 동선을 먼저 살펴봅니다", subtitle_id=2),
        )

        labeled = apply_major_topic_labels(
            segments,
            subtitles,
            settings={"roughcut_llm_enabled": True},
            llm_client=lambda _prompt: {"topics": [{"major_id": "A", "topic": "전시 소개"}]},
        )

        self.assertEqual(labeled[0].title, "현대모토 스튜디오 넥소 전시 공개")


if __name__ == "__main__":
    unittest.main()
