import os
import tempfile
import unittest
from unittest.mock import patch

from core.audio import stt_recheck_service, stt_rescue
from core.audio.stt_backend_router import select_stt_backend
from core.native_stt_recheck import duration_desc_order_indices, stt_recheck_backend


class STTRecheckServiceTests(unittest.TestCase):
    def test_normalize_scored_tracks_filters_both_labels_and_reports_drops(self):
        tracks = {
            "STT1": [{"text": "유지", "stt_score": 70}, {"text": "제외", "stt_score": 10}],
            "STT2": [{"text": "유지2", "stt_score": 80}, {"text": "제외2", "stt_score": 20}],
        }

        normalized, dropped = stt_recheck_service.normalize_scored_tracks(
            tracks,
            keep_score=30,
            filter_fn=lambda items, min_score: [
                item for item in items if float(item.get("stt_score", 0.0) or 0.0) >= float(min_score)
            ],
        )

        self.assertEqual([seg["text"] for seg in normalized["STT1"]], ["유지"])
        self.assertEqual([seg["text"] for seg in normalized["STT2"]], ["유지2"])
        self.assertEqual(dropped, {"STT1": 1, "STT2": 1})

    def test_route_hint_recheck_ranges_carries_scores_and_budgets(self):
        ranges = stt_recheck_service.route_hint_recheck_ranges(
            [
                {"start": 0.0, "end": 1.0, "text": "첫 구간", "stt_route_secondary_recheck_hint": True, "stt_score": 28},
                {"start": 2.0, "end": 3.0, "text": "둘째", "stt_route_secondary_recheck_hint": False, "stt_score": 10},
            ],
            {"stt_low_score_recheck_max_segments": 1},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
        )

        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].primary_text, "첫 구간")
        self.assertEqual(ranges[0].primary_score, 28.0)

    def test_route_hint_recheck_ranges_can_skip_budget_for_later_merge(self):
        ranges = stt_recheck_service.route_hint_recheck_ranges(
            [
                {"start": 0.0, "end": 1.0, "text": "첫 구간", "stt_route_secondary_recheck_hint": True, "stt_score": 28},
                {"start": 2.0, "end": 3.0, "text": "둘째 구간", "stt_route_secondary_recheck_hint": True, "stt_score": 18},
            ],
            {"stt_low_score_recheck_max_segments": 1},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            apply_budget=False,
        )

        self.assertEqual(len(ranges), 2)
        self.assertEqual([item.primary_text for item in ranges], ["첫 구간", "둘째 구간"])

    def test_budget_recheck_ranges_match_python_fallback_when_native_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_RECHECK")
        ranges = [
            stt_rescue.SttRecheckRange(
                start=5.0,
                end=6.0,
                primary_score=80.0,
                secondary_score=0.0,
                primary_text="후순위",
                secondary_text="",
                primary={},
                secondary={},
            ),
            stt_rescue.SttRecheckRange(
                start=10.0,
                end=13.0,
                primary_score=0.0,
                secondary_score=0.0,
                primary_text="",
                secondary_text="",
                primary={},
                secondary={},
            ),
            stt_rescue.SttRecheckRange(
                start=1.0,
                end=3.0,
                primary_score=40.0,
                secondary_score=0.0,
                primary_text="저점 짧음",
                secondary_text="",
                primary={},
                secondary={},
            ),
            stt_rescue.SttRecheckRange(
                start=3.0,
                end=6.0,
                primary_score=40.0,
                secondary_score=0.0,
                primary_text="저점 김",
                secondary_text="",
                primary={},
                secondary={},
            ),
        ]
        settings = {
            "stt_low_score_recheck_max_segments": 3,
            "stt_low_score_recheck_max_audio_sec": 10.0,
        }
        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "0"
            python_out = stt_rescue.budget_recheck_ranges(ranges, settings)
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "1"
            native_out = stt_rescue.budget_recheck_ranges(ranges, settings)
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_RECHECK", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = previous

        self.assertEqual(
            [(item.start, item.end, item.primary_text) for item in native_out],
            [(item.start, item.end, item.primary_text) for item in python_out],
        )
        self.assertEqual([item.primary_text for item in native_out], ["저점 짧음", "저점 김", ""])

    def test_native_duration_desc_order_prioritizes_long_chunks_stably(self):
        order = duration_desc_order_indices(
            starts=[4.0, 0.0, 2.0, 6.0],
            durations=[1.0, 3.0, 3.0, 0.5],
        )

        if stt_recheck_backend() == "cpp":
            self.assertEqual(order, [1, 2, 0, 3])
        else:
            self.assertIsNone(order)

    def test_missing_voice_recheck_ranges_skips_covered_vad_segments(self):
        ranges = stt_recheck_service.missing_voice_recheck_ranges(
            primary_segments=[{"start": 0.0, "end": 0.6, "text": "기존"}],
            vad_segments=[
                {"start": 0.0, "end": 0.5},
                {"start": 2.0, "end": 2.8},
            ],
            settings={"stt_low_score_recheck_max_segments": 4},
            min_duration=0.5,
            chunk_path_for_time=lambda target: "/tmp/chunk.wav" if target > 1.0 else "",
        )

        self.assertEqual(len(ranges), 1)
        self.assertAlmostEqual(ranges[0].start, 2.0)
        self.assertTrue(ranges[0].primary["asr_metadata"]["missing_voice_candidate"])

    def test_missing_voice_recheck_ranges_splits_internal_stt_holes_inside_long_vad(self):
        routed_times = []

        ranges = stt_recheck_service.missing_voice_recheck_ranges(
            primary_segments=[
                {"start": 100.0, "end": 103.0, "text": "앞 음성"},
                {"start": 116.0, "end": 120.0, "text": "뒤 음성"},
            ],
            vad_segments=[{"start": 100.0, "end": 120.0}],
            settings={
                "stt_low_score_recheck_max_segments": 4,
                "stt_missing_voice_internal_gap_min_duration_sec": 1.0,
            },
            min_duration=0.55,
            chunk_path_for_time=lambda target: routed_times.append(target) or "/tmp/chunk.wav",
        )

        self.assertEqual(len(ranges), 1)
        self.assertAlmostEqual(ranges[0].start, 103.0)
        self.assertAlmostEqual(ranges[0].end, 116.0)
        self.assertAlmostEqual(routed_times[0], 103.01)
        self.assertEqual(ranges[0].primary_text, "")
        self.assertTrue(ranges[0].primary["asr_metadata"]["missing_voice_candidate"])

    def test_low_score_recheck_ranges_match_expected_pairing(self):
        ranges = stt_recheck_service.low_score_recheck_ranges(
            [
                {"start": 0.0, "end": 1.2, "text": "망고 보여 봐", "stt_score": 42},
                {"start": 2.0, "end": 3.0, "text": "정상 문장", "stt_score": 91},
            ],
            [
                {"start": 0.05, "end": 1.25, "text": "방금 보여 봐", "stt_score": 47},
                {"start": 2.0, "end": 3.0, "text": "정상 문장", "stt_score": 48},
            ],
            {"stt_low_score_recheck_threshold": 50},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
        )

        self.assertEqual(len(ranges), 1)
        self.assertAlmostEqual(ranges[0].start, 0.0)
        self.assertAlmostEqual(ranges[0].end, 1.25)
        self.assertEqual(ranges[0].best_original_score, 47)

    def test_primary_low_score_recheck_ranges_match_expected_primary_candidates(self):
        ranges = stt_recheck_service.primary_low_score_recheck_ranges(
            [
                {"start": 0.0, "end": 1.2, "text": "저점 후보", "stt_score": 42},
                {"start": 2.0, "end": 3.0, "text": "정상 문장", "stt_score": 91},
            ],
            {"stt_low_score_recheck_threshold": 54},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
        )

        self.assertEqual(len(ranges), 1)
        self.assertAlmostEqual(ranges[0].start, 0.0)
        self.assertAlmostEqual(ranges[0].end, 1.2)
        self.assertEqual(ranges[0].best_original_score, 42)

    def test_word_precision_ranges_prioritize_selected_low_score_segments(self):
        ranges = stt_recheck_service.word_precision_ranges(
            [
                {
                    "start": 5.0,
                    "end": 6.0,
                    "text": "후순위",
                    "stt_score": 88,
                    "quality": {"confidence_label": "yellow", "flags": []},
                },
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "우선",
                    "stt_score": 42,
                    "selected": True,
                    "quality": {"confidence_label": "red", "flags": ["word_timestamps_missing"]},
                },
            ],
            {
                "stt_word_timestamps_precision_enabled": True,
                "stt_word_timestamps_precision_max_segments": 1,
                "stt_word_timestamps_precision_max_audio_sec": 30.0,
            },
            needs_precision_fn=lambda seg, _settings: True,
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            has_score_fn=lambda _seg: True,
        )

        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].primary_text, "우선")

    def test_word_precision_ranges_match_python_fallback_when_native_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_RECHECK")
        segments = [
            {
                "start": 5.0,
                "end": 6.0,
                "text": "노란 후보",
                "stt_score": 78,
                "quality": {"confidence_label": "yellow", "flags": ["word_timestamps_missing"]},
            },
            {
                "start": 1.0,
                "end": 2.0,
                "text": "선택 후보",
                "stt_score": 62,
                "selected": True,
                "quality": {"confidence_label": "green", "flags": []},
            },
            {
                "start": 3.0,
                "end": 4.0,
                "text": "빨간 후보",
                "stt_score": 44,
                "quality": {"confidence_label": "red", "flags": ["outside_vad_speech"]},
            },
            {
                "start": 7.0,
                "end": 8.0,
                "text": "제외",
                "stt_score": 15,
                "quality": {"confidence_label": "red", "flags": []},
                "skip_precision": True,
            },
        ]
        settings = {
            "stt_word_timestamps_precision_enabled": True,
            "stt_word_timestamps_precision_max_segments": 2,
            "stt_word_timestamps_precision_max_audio_sec": 30.0,
        }

        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "0"
            python_out = stt_recheck_service.word_precision_ranges(
                segments,
                settings,
                needs_precision_fn=lambda seg, _settings: not seg.get("skip_precision"),
                score_fn=lambda seg: seg.get("stt_score", 0.0),
                has_score_fn=lambda _seg: True,
            )
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "1"
            native_out = stt_recheck_service.word_precision_ranges(
                segments,
                settings,
                needs_precision_fn=lambda seg, _settings: not seg.get("skip_precision"),
                score_fn=lambda seg: seg.get("stt_score", 0.0),
                has_score_fn=lambda _seg: True,
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_RECHECK", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = previous

        self.assertEqual(
            [(item.start, item.end, item.primary_text, item.primary_score) for item in native_out],
            [(item.start, item.end, item.primary_text, item.primary_score) for item in python_out],
        )
        self.assertEqual([item.primary_text for item in native_out], ["선택 후보", "빨간 후보"])

    def test_resolve_precision_model_prefers_explicit_then_selected_then_primary(self):
        self.assertEqual(
            stt_recheck_service.resolve_precision_model(
                {
                    "stt_word_timestamps_precision_model": "explicit-model",
                    "selected_whisper_model": "selected-model",
                },
                primary_model="primary-model",
            ),
            "explicit-model",
        )
        self.assertEqual(
            stt_recheck_service.resolve_precision_model(
                {"selected_whisper_model": "selected-model"},
                primary_model="primary-model",
            ),
            "selected-model",
        )
        self.assertEqual(
            stt_recheck_service.resolve_precision_model(
                {},
                primary_model="primary-model",
            ),
            "primary-model",
        )

    def test_override_profiles_keep_expected_runtime_flags(self):
        precision = stt_recheck_service.precision_pass_overrides()
        low_score = stt_recheck_service.low_score_recheck_overrides()
        selective = stt_recheck_service.selective_secondary_recheck_overrides()

        self.assertTrue(precision["stt_word_timestamp_precision_pass"])
        self.assertEqual(precision["stt_backend_policy"], "native")
        self.assertTrue(precision["whisperkit_native_auto_enabled"])
        self.assertTrue(precision["stt_npu_prefer_enabled"])
        self.assertTrue(precision["stt_whisperkit_precision_aggressive_gpu_enabled"])
        self.assertEqual(precision["stt_whisperkit_gpu_saturation_max_workers"], 10)
        self.assertEqual(precision["stt_word_timestamp_worker_straggler_max_missing_chunks"], 3)
        self.assertTrue(precision["stt_duration_first_submission_enabled"])
        self.assertFalse(low_score["stt_ensemble_enabled"])
        self.assertEqual(low_score["whisper_chunk_overlap_sec"], 0.0)
        self.assertEqual(selective["stt_word_timestamps_mode"], "off")
        self.assertFalse(selective["stt_word_timestamps_precision_enabled"])
        self.assertFalse(selective["stt_persistent_runtime_reuse_enabled"])
        self.assertTrue(selective["stt_duration_first_submission_enabled"])

    def test_precision_overrides_route_supported_mlx_alias_to_whisperkit_native(self):
        with patch("core.audio.stt_backend_router.config.IS_MAC", True), \
             patch("core.audio.stt_backend_router._whisperkit_ready", return_value=True), \
             patch("core.audio.stt_backend_router._whisperkit_supported_model", return_value=True):
            choice = select_stt_backend(
                "mlx-community/whisper-large-v3-mlx",
                stt_recheck_service.precision_pass_overrides(),
            )

        self.assertEqual(choice.backend, "whisperkit_persistent")
        self.assertTrue(choice.model.startswith("whisperkit-persistent:"))

    def test_collect_prepared_recheck_clips_skips_empty_results(self):
        item = stt_rescue.SttRecheckRange(
            start=0.0,
            end=1.0,
            primary_score=10.0,
            secondary_score=0.0,
            primary_text="",
            secondary_text="",
            primary={},
            secondary={},
        )
        prepared = stt_recheck_service.collect_prepared_recheck_clips(
            ranges=[item, item],
            out_dir="/tmp/out",
            settings={"x": 1},
            prepare_clip_fn=lambda _item, _out_dir, idx, _settings: None if idx == 0 else {"start": 1.0, "end": 2.0},
        )

        self.assertEqual(prepared, [{"start": 1.0, "end": 2.0}])

    def test_annotate_candidate_segments_returns_error_and_original_segments(self):
        original = [{"text": "원본"}]
        annotated, error = stt_recheck_service.annotate_candidate_segments(
            original,
            annotate_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
            source="RECHECK",
            settings={},
            vad_segments=[],
        )

        self.assertEqual(annotated, original)
        self.assertEqual(error, "boom")

    def test_collect_and_annotate_segments_applies_collect_then_annotation(self):
        collected, error = stt_recheck_service.collect_and_annotate_segments(
            collect_fn=lambda *_args, **_kwargs: [{"text": "기본"}],
            chunk_dir="/tmp/chunks",
            model="demo-model",
            label="DEMO",
            settings_overrides={"x": 1},
            annotate_fn=lambda segments, **_kwargs: [{**segments[0], "text": "주석됨"}],
            annotate_source="RECHECK",
            settings={"a": 1},
            vad_segments=[],
            peer_segments=[],
            is_single=False,
        )

        self.assertIsNone(error)
        self.assertEqual(collected, [{"text": "주석됨"}])

    def test_prepare_and_collect_recheck_segments_returns_prepared_and_collected_rows(self):
        item = stt_rescue.SttRecheckRange(
            start=0.0,
            end=1.0,
            primary_score=10.0,
            secondary_score=0.0,
            primary_text="원본",
            secondary_text="",
            primary={},
            secondary={},
        )
        batch = stt_recheck_service.prepare_and_collect_recheck_segments(
            ranges=[item],
            out_dir="/tmp/recheck",
            settings={"a": 1},
            prepare_clip_fn=lambda _item, _out_dir, _idx, _settings: {"range": item, "path": "/tmp/clip.wav"},
            collect_fn=lambda *_args, **_kwargs: [{"text": "수집됨"}],
            model="demo-model",
            label="DEMO",
            settings_overrides={"x": 1},
            annotate_fn=lambda segments, **_kwargs: [{**segments[0], "text": "주석됨"}],
            annotate_source="RECHECK",
            vad_segments=[],
            peer_segments=[],
            is_single=False,
        )

        self.assertEqual(batch.prepared_clips, [{"range": item, "path": "/tmp/clip.wav"}])
        self.assertEqual(batch.collected_segments, [{"text": "주석됨"}])
        self.assertIsNone(batch.annotate_error)
        self.assertGreaterEqual(batch.prepare_elapsed_sec, 0.0)
        self.assertGreaterEqual(batch.collect_elapsed_sec, 0.0)
        self.assertGreaterEqual(batch.annotate_elapsed_sec, 0.0)
        self.assertGreaterEqual(batch.total_elapsed_sec, 0.0)
        self.assertFalse(batch.collect_cache_enabled)
        self.assertFalse(batch.collect_cache_hit)
        self.assertFalse(batch.collect_cache_write)
        self.assertTrue(batch.collect_provider_called)

    def test_prepare_and_collect_recheck_segments_replays_cached_collect_then_reannotates(self):
        item = stt_rescue.SttRecheckRange(
            start=0.0,
            end=1.0,
            primary_score=10.0,
            secondary_score=0.0,
            primary_text="원본",
            secondary_text="",
            primary={},
            secondary={},
        )
        with tempfile.TemporaryDirectory() as tmp:
            clip_path = os.path.join(tmp, "clip.wav")
            cache_path = os.path.join(tmp, "collect_cache.json")
            with open(clip_path, "wb") as handle:
                handle.write(b"deterministic-audio")
            settings = {
                "stt_recheck_collect_cache_enabled": True,
                "stt_recheck_collect_cache_path": cache_path,
            }
            calls = {"collect": 0, "annotate": 0}

            def prepare_clip(_item, _out_dir, _idx, _settings):
                return {"range": item, "path": clip_path, "start": 0.0, "end": 1.0}

            def collect_fn(*_args, **_kwargs):
                calls["collect"] += 1
                return [{"start": 0.0, "end": 1.0, "text": "수집됨"}]

            def annotate_fn(segments, **_kwargs):
                calls["annotate"] += 1
                return [{**dict(segments[0]), "text": f"주석됨-{calls['annotate']}"}]

            first = stt_recheck_service.prepare_and_collect_recheck_segments(
                ranges=[item],
                out_dir=tmp,
                settings=settings,
                prepare_clip_fn=prepare_clip,
                collect_fn=collect_fn,
                model="demo-model",
                label="DEMO",
                settings_overrides={"x": 1},
                annotate_fn=annotate_fn,
                annotate_source="RECHECK",
                vad_segments=[],
                peer_segments=[],
                is_single=False,
            )

            second = stt_recheck_service.prepare_and_collect_recheck_segments(
                ranges=[item],
                out_dir=tmp,
                settings=settings,
                prepare_clip_fn=prepare_clip,
                collect_fn=lambda *_args, **_kwargs: self.fail("collect_fn must not run on cache hit"),
                model="demo-model",
                label="DEMO",
                settings_overrides={"x": 1},
                annotate_fn=annotate_fn,
                annotate_source="RECHECK",
                vad_segments=[],
                peer_segments=[],
                is_single=False,
            )

        self.assertEqual(calls["collect"], 1)
        self.assertEqual(calls["annotate"], 2)
        self.assertTrue(first.collect_cache_enabled)
        self.assertFalse(first.collect_cache_hit)
        self.assertTrue(first.collect_cache_write)
        self.assertTrue(first.collect_provider_called)
        self.assertEqual(first.collected_segments, [{"start": 0.0, "end": 1.0, "text": "주석됨-1"}])
        self.assertTrue(second.collect_cache_enabled)
        self.assertTrue(second.collect_cache_hit)
        self.assertFalse(second.collect_cache_write)
        self.assertFalse(second.collect_provider_called)
        self.assertEqual(second.collect_elapsed_sec, 0.0)
        self.assertEqual(second.collected_segments, [{"start": 0.0, "end": 1.0, "text": "주석됨-2"}])

    def test_recheck_collect_cache_key_ignores_unrelated_cache_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip_path = os.path.join(tmp, "clip.wav")
            with open(clip_path, "wb") as handle:
                handle.write(b"deterministic-audio")
            prepared = [{"path": clip_path, "start": 0.0, "end": 1.0}]
            base_settings = {
                "stt_quality_preset": "high",
                "stt_recheck_collect_cache_enabled": True,
                "stt_recheck_collect_cache_path": os.path.join(tmp, "recheck_a.json"),
                "stt_primary_collect_cache_enabled": False,
                "subtitle_llm_macro_response_cache_enabled": False,
                "subtitle_llm_context_keep_cache_path": os.path.join(tmp, "keep_a.json"),
            }
            toggled_settings = {
                **base_settings,
                "stt_recheck_collect_cache_path": os.path.join(tmp, "recheck_b.json"),
                "stt_primary_collect_cache_enabled": True,
                "stt_primary_collect_cache_path": os.path.join(tmp, "primary.json"),
                "subtitle_llm_macro_response_cache_enabled": True,
                "subtitle_llm_macro_response_cache_path": os.path.join(tmp, "macro.json"),
                "subtitle_llm_context_keep_cache_path": os.path.join(tmp, "keep_b.json"),
            }

            base_key = stt_recheck_service._recheck_collect_cache_key(
                prepared_clips=prepared,
                settings=base_settings,
                model="demo-model",
                label="STT2",
                settings_overrides={"word_timestamps": False},
                annotate_source="STT2",
                is_single=False,
            )
            toggled_key = stt_recheck_service._recheck_collect_cache_key(
                prepared_clips=prepared,
                settings=toggled_settings,
                model="demo-model",
                label="STT2",
                settings_overrides={"word_timestamps": False},
                annotate_source="STT2",
                is_single=False,
            )
            model_changed_key = stt_recheck_service._recheck_collect_cache_key(
                prepared_clips=prepared,
                settings=toggled_settings,
                model="other-model",
                label="STT2",
                settings_overrides={"word_timestamps": False},
                annotate_source="STT2",
                is_single=False,
            )

        self.assertEqual(base_key, toggled_key)
        self.assertNotEqual(base_key, model_changed_key)

    def test_prepare_and_collect_recheck_segments_short_circuits_when_prepare_is_empty(self):
        item = stt_rescue.SttRecheckRange(
            start=0.0,
            end=1.0,
            primary_score=10.0,
            secondary_score=0.0,
            primary_text="원본",
            secondary_text="",
            primary={},
            secondary={},
        )
        batch = stt_recheck_service.prepare_and_collect_recheck_segments(
            ranges=[item],
            out_dir="/tmp/recheck",
            settings={},
            prepare_clip_fn=lambda *_args, **_kwargs: None,
            collect_fn=lambda *_args, **_kwargs: [{"text": "호출되면 안됨"}],
            model="demo-model",
            label="DEMO",
            settings_overrides={},
            annotate_fn=lambda segments, **_kwargs: segments,
            annotate_source="RECHECK",
            vad_segments=[],
            is_single=False,
        )

        self.assertEqual(batch.prepared_clips, [])
        self.assertEqual(batch.collected_segments, [])
        self.assertIsNone(batch.annotate_error)
        self.assertGreaterEqual(batch.prepare_elapsed_sec, 0.0)
        self.assertEqual(batch.collect_elapsed_sec, 0.0)
        self.assertEqual(batch.annotate_elapsed_sec, 0.0)
        self.assertGreaterEqual(batch.total_elapsed_sec, 0.0)

    def test_native_uncovered_vad_indices_match_python_fallback_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_RECHECK")
        vad_segments = [
            {"start": 0.0, "end": 0.4},
            {"start": 1.0, "end": 1.8},
            {"start": 3.0, "end": 3.7},
        ]
        primary_segments = [
            {"start": 0.0, "end": 0.5, "text": "커버"},
            {"start": 1.1, "end": 1.3, "text": ""},
        ]
        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "0"
            python_out = stt_recheck_service.uncovered_vad_indices(
                vad_segments,
                primary_segments,
                min_duration=0.3,
            )
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "1"
            native_out = stt_recheck_service.uncovered_vad_indices(
                vad_segments,
                primary_segments,
                min_duration=0.3,
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_RECHECK", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = previous

        if stt_recheck_backend() == "cpp":
            self.assertEqual(native_out, python_out)
        else:
            self.assertEqual(native_out, python_out)

    def test_overlap_segment_groups_match_python_fallback_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_RECHECK")
        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "0"
            python_out = stt_recheck_service.overlap_segment_groups(
                range_starts=[0.0, 5.0],
                range_ends=[1.0, 6.0],
                segment_starts=[0.0, 0.7, 5.2],
                segment_ends=[1.0, 1.3, 5.8],
            )
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "1"
            native_out = stt_recheck_service.overlap_segment_groups(
                range_starts=[0.0, 5.0],
                range_ends=[1.0, 6.0],
                segment_starts=[0.0, 0.7, 5.2],
                segment_ends=[1.0, 1.3, 5.8],
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_RECHECK", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = previous

        self.assertEqual(native_out, python_out)
        self.assertEqual(python_out, [[0, 1], [2]])

    def test_overlap_range_components_match_python_fallback_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_RECHECK")
        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "0"
            python_out = stt_recheck_service.overlap_range_components(
                range_starts=[0.0, 0.02, 5.0],
                range_ends=[1.0, 1.01, 6.0],
                min_overlap_ratio=0.92,
            )
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "1"
            native_out = stt_recheck_service.overlap_range_components(
                range_starts=[0.0, 0.02, 5.0],
                range_ends=[1.0, 1.01, 6.0],
                min_overlap_ratio=0.92,
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_RECHECK", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = previous

        self.assertEqual(native_out, python_out)
        self.assertEqual(python_out, [[0, 1], [2]])

    def test_low_score_recheck_ranges_match_python_fallback_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_RECHECK")
        primary = [
            {"start": 0.0, "end": 1.2, "text": "망고 보여 봐", "stt_score": 42},
            {"start": 2.0, "end": 3.0, "text": "정상 문장", "stt_score": 91},
        ]
        secondary = [
            {"start": 0.05, "end": 1.25, "text": "방금 보여 봐", "stt_score": 47},
            {"start": 2.0, "end": 3.0, "text": "정상 문장", "stt_score": 48},
        ]
        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "0"
            python_out = stt_recheck_service.low_score_recheck_ranges(
                primary,
                secondary,
                {"stt_low_score_recheck_threshold": 50},
                score_fn=lambda seg: seg.get("stt_score", 0.0),
            )
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "1"
            native_out = stt_recheck_service.low_score_recheck_ranges(
                primary,
                secondary,
                {"stt_low_score_recheck_threshold": 50},
                score_fn=lambda seg: seg.get("stt_score", 0.0),
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_RECHECK", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = previous

        self.assertEqual(
            [(item.start, item.end, item.primary_score, item.secondary_score) for item in native_out],
            [(item.start, item.end, item.primary_score, item.secondary_score) for item in python_out],
        )

    def test_primary_low_score_recheck_ranges_match_python_fallback_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_RECHECK")
        primary = [
            {"start": 0.0, "end": 1.2, "text": "저점 후보", "stt_score": 42},
            {"start": 2.0, "end": 3.0, "text": "정상 문장", "stt_score": 91},
        ]
        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "0"
            python_out = stt_recheck_service.primary_low_score_recheck_ranges(
                primary,
                {"stt_low_score_recheck_threshold": 54},
                score_fn=lambda seg: seg.get("stt_score", 0.0),
            )
            os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = "1"
            native_out = stt_recheck_service.primary_low_score_recheck_ranges(
                primary,
                {"stt_low_score_recheck_threshold": 54},
                score_fn=lambda seg: seg.get("stt_score", 0.0),
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_RECHECK", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_RECHECK"] = previous

        self.assertEqual(
            [(item.start, item.end, item.primary_score) for item in native_out],
            [(item.start, item.end, item.primary_score) for item in python_out],
        )

    def test_selective_secondary_recheck_ranges_deduplicate_overlapping_candidates_before_budget(self):
        ranges, raw_count = stt_recheck_service.selective_secondary_recheck_ranges(
            primary_segments=[
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "저점 후보",
                    "stt_score": 20,
                    "stt_route_secondary_recheck_hint": True,
                }
            ],
            vad_segments=[{"start": 0.02, "end": 0.98}],
            settings={
                "stt_low_score_recheck_threshold": 40,
                "stt_low_score_recheck_max_segments": 4,
                "stt_missing_voice_min_duration_sec": 0.4,
            },
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            chunk_path_for_time=lambda _target: "/tmp/chunk.wav",
        )

        self.assertEqual(raw_count, 1)
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].primary_text, "저점 후보")
        self.assertAlmostEqual(ranges[0].start, 0.0)
        self.assertAlmostEqual(ranges[0].end, 1.0)

    def test_collapsed_recheck_keeps_missing_voice_source_when_text_candidate_starts_later(self):
        early_chunk = "/tmp/vad_000_0.000.wav"
        late_chunk = "/tmp/vad_001_112.000.wav"
        missing = stt_rescue.SttRecheckRange(
            start=104.512,
            end=164.592,
            primary_score=0.0,
            secondary_score=0.0,
            primary_text="",
            secondary_text="",
            primary={
                "start": 104.512,
                "end": 164.592,
                "text": "",
                "chunk_path": early_chunk,
                "asr_metadata": {
                    "chunk_path": early_chunk,
                    "missing_voice_candidate": True,
                },
            },
            secondary={},
        )
        late_text = stt_rescue.SttRecheckRange(
            start=112.0,
            end=164.592,
            primary_score=22.0,
            secondary_score=0.0,
            primary_text="아 시트 되게 편해요",
            secondary_text="",
            primary={
                "start": 112.0,
                "end": 164.592,
                "text": "아 시트 되게 편해요",
                "chunk_path": late_chunk,
                "asr_metadata": {"chunk_path": late_chunk},
            },
            secondary={},
        )

        collapsed = stt_recheck_service.collapse_duplicate_recheck_ranges([missing, late_text])

        self.assertEqual(len(collapsed), 1)
        self.assertAlmostEqual(collapsed[0].start, 104.512)
        self.assertAlmostEqual(collapsed[0].end, 164.592)
        self.assertEqual(collapsed[0].primary.get("chunk_path"), early_chunk)
        self.assertTrue(collapsed[0].primary["asr_metadata"]["missing_voice_candidate"])

    def test_select_recheck_replacements_marks_and_decorates_matching_segments(self):
        item = stt_rescue.SttRecheckRange(
            start=0.0,
            end=1.0,
            primary_score=30.0,
            secondary_score=20.0,
            primary_text="원본1",
            secondary_text="원본2",
            primary={"text": "원본1"},
            secondary={"text": "원본2"},
        )
        batch = stt_recheck_service.select_recheck_replacements(
            prepared_clips=[{"range": item, "start": 0.0, "end": 1.0}],
            rescue_segments=[{"start": 0.05, "end": 0.95, "text": "교체", "stt_score": 92}],
            settings={"stt_low_score_recheck_threshold": 50},
            replacement_is_better_fn=stt_rescue.replacement_is_better,
            mark_segments_fn=stt_rescue.mark_rescue_segments,
            decorate_segment_fn=lambda seg: {**seg, "stt_ensemble_source": "RECHECK"},
        )

        self.assertEqual(len(batch.applied_ranges), 1)
        self.assertEqual(len(batch.applied_segments), 1)
        self.assertEqual(batch.applied_segments[0]["text"], "교체")
        self.assertEqual(batch.applied_segments[0]["stt_ensemble_source"], "RECHECK")
        self.assertTrue(batch.applied_segments[0]["stt_recheck_applied"])
        self.assertEqual(batch.skipped_ranges, [])

    def test_apply_recheck_selection_to_tracks_merges_multiple_tracks(self):
        item = stt_rescue.SttRecheckRange(
            start=0.0,
            end=1.0,
            primary_score=30.0,
            secondary_score=20.0,
            primary_text="원본1",
            secondary_text="원본2",
            primary={"text": "원본1"},
            secondary={"text": "원본2"},
        )
        result = stt_recheck_service.apply_recheck_selection_to_tracks(
            prepared_clips=[{"range": item, "start": 0.0, "end": 1.0}],
            rescue_segments=[{"start": 0.05, "end": 0.95, "text": "교체", "stt_score": 92}],
            settings={"stt_low_score_recheck_threshold": 50},
            replacement_is_better_fn=stt_rescue.replacement_is_better,
            mark_segments_fn=stt_rescue.mark_rescue_segments,
            base_tracks={
                "STT1": [{"start": 0.0, "end": 1.0, "text": "제거"}],
                "STT2": [{"start": 0.0, "end": 1.0, "text": "제거2"}],
            },
            decorate_segment_fn=lambda seg: {**seg, "stt_ensemble_source": "RECHECK"},
        )

        self.assertEqual(len(result.selection.applied_ranges), 1)
        self.assertIsNotNone(result.merged_tracks)
        self.assertEqual([seg["text"] for seg in result.merged_tracks["STT1"]], ["교체"])
        self.assertEqual([seg["text"] for seg in result.merged_tracks["STT2"]], ["교체"])

    def test_apply_recheck_selection_to_tracks_reports_retention_failure_with_preview(self):
        item = stt_rescue.SttRecheckRange(
            start=0.0,
            end=3.0,
            primary_score=10.0,
            secondary_score=0.0,
            primary_text="원본",
            secondary_text="",
            primary={},
            secondary={},
        )
        result = stt_recheck_service.apply_recheck_selection_to_tracks(
            prepared_clips=[{"range": item, "start": 0.0, "end": 3.0}],
            rescue_segments=[{"start": 0.0, "end": 3.0, "text": "one", "stt_score": 95}],
            settings={"stt_low_score_recheck_threshold": 50},
            replacement_is_better_fn=stt_rescue.replacement_is_better,
            mark_segments_fn=stt_rescue.mark_rescue_segments,
            base_tracks={
                "primary": [
                    {"start": 0.0, "end": 1.0, "text": "a"},
                    {"start": 1.0, "end": 2.0, "text": "b"},
                    {"start": 2.0, "end": 3.0, "text": "c"},
                ]
            },
            retention_ratios={"primary": 0.9},
        )

        self.assertEqual(len(result.selection.applied_ranges), 1)
        self.assertIsNone(result.merged_tracks)
        self.assertEqual([seg["text"] for seg in result.preview_tracks["primary"]], ["one"])

    def test_merge_segments_with_replacements_drops_overlapping_segments_and_sorts(self):
        merged = stt_recheck_service.merge_segments_with_replacements(
            base_segments=[
                {"start": 2.0, "end": 3.0, "text": "유지"},
                {"start": 0.0, "end": 1.0, "text": "제거"},
            ],
            applied_ranges=[
                stt_rescue.SttRecheckRange(
                    start=0.0,
                    end=1.0,
                    primary_score=30.0,
                    secondary_score=25.0,
                    primary_text="제거",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            applied_segments=[{"start": 0.1, "end": 0.9, "text": "대체"}],
        )

        self.assertEqual([seg["text"] for seg in merged], ["대체", "유지"])

    def test_merge_segments_with_replacements_keeps_uncovered_stt1_text_inside_wide_recheck_range(self):
        merged = stt_recheck_service.merge_segments_with_replacements(
            base_segments=[
                {"start": 104.76, "end": 110.38, "text": "그리고 지금 제가 한 시간 정도 운전을 했는데"},
                {"start": 110.38, "end": 113.76, "text": "정말 마음에 드는 것 중에 하나는 뭐냐면"},
                {"start": 113.76, "end": 116.0, "text": "아 이 시트 시트 되게 편해요"},
            ],
            applied_ranges=[
                stt_rescue.SttRecheckRange(
                    start=104.512,
                    end=116.0,
                    primary_score=22.0,
                    secondary_score=0.0,
                    primary_text="넓은 재검사 범위",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            applied_segments=[
                {
                    "start": 115.2,
                    "end": 116.68,
                    "text": "아 시트 되게 편해요",
                    "asr_metadata": {
                        "stt_low_score_recheck": {
                            "range_start": 104.512,
                            "range_end": 116.0,
                        }
                    },
                }
            ],
        )

        self.assertEqual(
            [seg["text"] for seg in merged],
            [
                "그리고 지금 제가 한 시간 정도 운전을 했는데",
                "정말 마음에 드는 것 중에 하나는 뭐냐면",
                "아 시트 되게 편해요",
            ],
        )

    def test_merge_segments_with_replacements_respects_retention_guard(self):
        merged = stt_recheck_service.merge_segments_with_replacements(
            base_segments=[
                {"start": 0.0, "end": 1.0, "text": "a"},
                {"start": 1.0, "end": 2.0, "text": "b"},
                {"start": 2.0, "end": 3.0, "text": "c"},
            ],
            applied_ranges=[
                stt_rescue.SttRecheckRange(
                    start=0.0,
                    end=3.0,
                    primary_score=10.0,
                    secondary_score=0.0,
                    primary_text="",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            applied_segments=[{"start": 0.0, "end": 3.0, "text": "one"}],
            min_retention_ratio=0.9,
        )

        self.assertIsNone(merged)

    def test_apply_word_precision_segments_updates_timing_and_keeps_text_by_default(self):
        updated, applied = stt_recheck_service.apply_word_precision_segments(
            base_segments=[
                {"start": 0.0, "end": 1.0, "text": "원본 문장", "asr_metadata": {}},
                {"start": 2.0, "end": 3.0, "text": "유지"},
            ],
            precision_segments=[
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "바뀐 문장",
                    "stt_score": 95,
                    "stt_selected_source": "WORD_PRECISION",
                    "words": [
                        {"word": "바뀐", "start": 0.1, "end": 0.4},
                        {"word": "문장", "start": 0.4, "end": 0.9},
                    ],
                }
            ],
            ranges=[
                stt_rescue.SttRecheckRange(
                    start=0.0,
                    end=1.0,
                    primary_score=30.0,
                    secondary_score=0.0,
                    primary_text="원본 문장",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            settings={"stt_word_timestamps_precision_keep_text": True},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            text_similarity_fn=lambda _left, _right: 0.95,
        )

        self.assertEqual(applied, 1)
        self.assertEqual(updated[0]["text"], "원본 문장")
        self.assertAlmostEqual(updated[0]["start"], 0.1)
        self.assertAlmostEqual(updated[0]["end"], 0.9)
        self.assertTrue(updated[0]["stt_word_precision_applied"])
        self.assertEqual(updated[1]["text"], "유지")

    def test_apply_word_precision_segments_splits_long_base_when_precision_returns_multiple_parts(self):
        updated, applied = stt_recheck_service.apply_word_precision_segments(
            base_segments=[
                {
                    "start": 0.0,
                    "end": 5.8,
                    "text": "지금 에코프로를 놓은 상태고 크루즈 컨트롤 걸어볼게요 80으로 크루즈 컨트롤 걸었고요",
                    "asr_metadata": {},
                    "stt_selected_source": "STT1",
                }
            ],
            precision_segments=[
                {
                    "start": 0.0,
                    "end": 1.7,
                    "text": "지금 에코프로를 놓은 상태고",
                    "stt_score": 91,
                    "stt_selected_source": "WORD_PRECISION",
                    "words": [
                        {"word": "지금", "start": 0.05, "end": 0.35},
                        {"word": "상태고", "start": 1.25, "end": 1.62},
                    ],
                },
                {
                    "start": 1.7,
                    "end": 3.5,
                    "text": "크루즈 컨트롤 걸어볼게요",
                    "stt_score": 90,
                    "stt_selected_source": "WORD_PRECISION",
                    "words": [
                        {"word": "크루즈", "start": 1.74, "end": 2.1},
                        {"word": "걸어볼게요", "start": 3.0, "end": 3.42},
                    ],
                },
                {
                    "start": 3.5,
                    "end": 5.8,
                    "text": "80으로 크루즈 컨트롤 걸었고요",
                    "stt_score": 92,
                    "stt_selected_source": "WORD_PRECISION",
                    "words": [
                        {"word": "80으로", "start": 3.55, "end": 3.9},
                        {"word": "걸었고요", "start": 5.15, "end": 5.62},
                    ],
                },
            ],
            ranges=[
                stt_rescue.SttRecheckRange(
                    start=0.0,
                    end=5.8,
                    primary_score=22.0,
                    secondary_score=0.0,
                    primary_text="지금 에코프로를 놓은 상태고 크루즈 컨트롤 걸어볼게요 80으로 크루즈 컨트롤 걸었고요",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            settings={
                "stt_word_timestamps_precision_keep_text": True,
                "stt_word_timestamps_precision_split_min_similarity": 0.62,
            },
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            text_similarity_fn=lambda left, right: 0.96 if "80으로" in left and "80으로" in right else 0.2,
        )

        self.assertEqual(applied, 3)
        self.assertEqual([seg["text"] for seg in updated], [
            "지금 에코프로를 놓은 상태고",
            "크루즈 컨트롤 걸어볼게요",
            "80으로 크루즈 컨트롤 걸었고요",
        ])
        self.assertTrue(all(seg["stt_word_precision_split_applied"] for seg in updated))
        self.assertAlmostEqual(updated[0]["start"], 0.05)
        self.assertAlmostEqual(updated[-1]["end"], 5.62)

    def test_apply_word_precision_segments_rejects_split_that_drops_base_text(self):
        updated, applied = stt_recheck_service.apply_word_precision_segments(
            base_segments=[
                {
                    "start": 113.46,
                    "end": 116.0,
                    "text": "아 이 시트! 시트 되게 편해요",
                    "asr_metadata": {},
                    "stt_selected_source": "STT1",
                }
            ],
            precision_segments=[
                {
                    "start": 113.71,
                    "end": 115.01,
                    "text": "이 시트",
                    "stt_score": 83.25,
                    "stt_selected_source": "WORD_PRECISION",
                    "words": [
                        {"word": "이", "start": 113.71, "end": 113.85},
                        {"word": "시트", "start": 114.4, "end": 115.01},
                    ],
                },
                {
                    "start": 115.03,
                    "end": 115.75,
                    "text": "시트",
                    "stt_score": 87.04,
                    "stt_selected_source": "WORD_PRECISION",
                    "words": [
                        {"word": "시트", "start": 115.03, "end": 115.75},
                    ],
                },
            ],
            ranges=[
                stt_rescue.SttRecheckRange(
                    start=113.46,
                    end=116.0,
                    primary_score=22.0,
                    secondary_score=0.0,
                    primary_text="아 이 시트! 시트 되게 편해요",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            settings={"stt_word_timestamps_precision_keep_text": True},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            text_similarity_fn=lambda _left, _right: 0.625,
        )

        self.assertEqual(applied, 0)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["text"], "아 이 시트! 시트 되게 편해요")

    def test_apply_word_precision_segments_keeps_short_base_as_one_subtitle(self):
        updated, applied = stt_recheck_service.apply_word_precision_segments(
            base_segments=[
                {
                    "start": 150.7,
                    "end": 152.98,
                    "text": "그리고 이 차가 좋은 게",
                    "asr_metadata": {},
                    "stt_selected_source": "STT1",
                }
            ],
            precision_segments=[
                {
                    "start": 150.93,
                    "end": 151.61,
                    "text": "그리고 이 차가",
                    "stt_score": 90,
                    "stt_selected_source": "WORD_PRECISION",
                    "words": [
                        {"word": "그리고", "start": 150.93, "end": 151.15},
                        {"word": "차가", "start": 151.35, "end": 151.61},
                    ],
                },
                {
                    "start": 152.39,
                    "end": 152.53,
                    "text": "좋은 게",
                    "stt_score": 90,
                    "stt_selected_source": "WORD_PRECISION",
                    "words": [
                        {"word": "좋은", "start": 152.39, "end": 152.45},
                        {"word": "게", "start": 152.46, "end": 152.53},
                    ],
                },
            ],
            ranges=[
                stt_rescue.SttRecheckRange(
                    start=150.7,
                    end=152.98,
                    primary_score=22.0,
                    secondary_score=0.0,
                    primary_text="그리고 이 차가 좋은 게",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            settings={"stt_word_timestamps_precision_keep_text": True},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            text_similarity_fn=lambda _left, _right: 1.0,
        )

        self.assertEqual(applied, 0)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["text"], "그리고 이 차가 좋은 게")

    def test_apply_word_precision_segments_can_replace_text_when_allowed(self):
        updated, applied = stt_recheck_service.apply_word_precision_segments(
            base_segments=[{"start": 0.0, "end": 1.0, "text": "원본"}],
            precision_segments=[
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "교체 텍스트",
                    "stt_score": 90,
                    "stt_ensemble_source": "WORD_PRECISION",
                    "words": [{"word": "교체", "start": 0.05, "end": 0.95}],
                }
            ],
            ranges=[
                stt_rescue.SttRecheckRange(
                    start=0.0,
                    end=1.0,
                    primary_score=10.0,
                    secondary_score=0.0,
                    primary_text="원본",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            settings={"stt_word_timestamps_precision_keep_text": False},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            text_similarity_fn=lambda _left, _right: 0.99,
        )

        self.assertEqual(applied, 1)
        self.assertEqual(updated[0]["text"], "교체 텍스트")

    def test_apply_word_precision_segments_skips_when_similarity_is_too_low(self):
        base = [{"start": 0.0, "end": 1.0, "text": "원본", "asr_metadata": {}}]
        updated, applied = stt_recheck_service.apply_word_precision_segments(
            base_segments=base,
            precision_segments=[
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "전혀 다름",
                    "stt_score": 99,
                    "words": [{"word": "전혀", "start": 0.1, "end": 0.9}],
                }
            ],
            ranges=[
                stt_rescue.SttRecheckRange(
                    start=0.0,
                    end=1.0,
                    primary_score=15.0,
                    secondary_score=0.0,
                    primary_text="원본",
                    secondary_text="",
                    primary={},
                    secondary={},
                )
            ],
            settings={"stt_word_timestamps_precision_min_similarity": 0.8},
            score_fn=lambda seg: seg.get("stt_score", 0.0),
            text_similarity_fn=lambda _left, _right: 0.2,
        )

        self.assertEqual(applied, 0)
        self.assertEqual(updated, base)


if __name__ == "__main__":
    unittest.main()
