import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.autopilot_cache import (
    LRUCacheManager,
    NegativeCache,
    model_hash,
    settings_hash,
    stable_json_dumps,
    read_compressed_jsonl,
    stage_cache_key,
    write_compressed_jsonl,
)
from core.autopilot_policy import (
    apply_autopilot_runtime_policy,
    classify_confidence_lane,
    hybrid_cut_boundary_decision,
    speaker_preflight_decision,
    stage_prewarm_decision,
    unified_confidence_score,
)


class AutoPilotPolicyCacheTests(unittest.TestCase):
    def test_confident_segment_uses_fast_lane_without_llm(self):
        lane = classify_confidence_lane(
            {
                "stt_confidence": 96,
                "lora_score": 93,
                "deep_selector_confidence": 0.94,
                "vad_alignment_score": 91,
                "cut_boundary_confidence": 90,
                "timing_quality": 95,
                "user_history_score": 88,
                "style_match_score": 92,
            }
        )

        self.assertEqual(lane["lane"], "fast")
        self.assertFalse(lane["call_llm"])
        self.assertTrue(lane["finalize_without_llm"])

    def test_risky_segment_routes_to_llm_or_rollback(self):
        lane = classify_confidence_lane(
            {
                "stt_confidence": 81,
                "lora_score": 76,
                "deep_selector_confidence": 0.72,
                "vad_alignment_score": 75,
                "cut_boundary_confidence": 62,
                "timing_quality": 70,
                "stt_candidate_conflict": True,
                "numeric_risk": True,
            }
        )
        self.assertEqual(lane["lane"], "llm")
        self.assertTrue(lane["call_llm"])

        rollback = classify_confidence_lane({"llm_added_unsupported_content": True, "lora_score": 95})
        self.assertEqual(rollback["lane"], "rollback")

    def test_unified_confidence_penalizes_missing_signals(self):
        rich = unified_confidence_score({"stt_confidence": 90, "lora_score": 90, "deep_selector_confidence": 90})
        sparse = unified_confidence_score({"stt_confidence": 90})

        self.assertGreater(rich["score"], sparse["score"])
        self.assertIn("lora_score", sparse["missing_signals"])

    def test_speaker_preflight_skips_or_escalates_diarization(self):
        single = speaker_preflight_decision(
            [{"start": 0.0, "end": 20.0}, {"start": 25.0, "end": 50.0}],
            media_duration_sec=60.0,
        )
        multi = speaker_preflight_decision(
            [{"start": i * 2.0, "end": i * 2.0 + 0.9} for i in range(40)],
            media_duration_sec=90.0,
            speaker_count_hint=2,
        )

        self.assertEqual(single["lane"], "skip_diarization")
        self.assertEqual(multi["lane"], "targeted_diarization")

    def test_hybrid_cut_boundary_keeps_audio_as_provisional(self):
        audio = hybrid_cut_boundary_decision({"source": "audio_gain_provisional", "audio_gain_db_delta": 12.0})
        visual = hybrid_cut_boundary_decision({"source": "visual_cut", "score": 92.0, "has_visual": True})

        self.assertEqual(audio["lane"], "audio_provisional")
        self.assertFalse(audio["hard_cut_allowed"])
        self.assertEqual(audio["line_color"], "#39FF14")
        self.assertEqual(visual["lane"], "fast_confirm")
        self.assertTrue(visual["hard_cut_allowed"])

    def test_stage_prewarm_delays_until_stage_is_near_complete_and_resources_allow(self):
        wait = stage_prewarm_decision("stt", 0.4)
        delayed = stage_prewarm_decision("stt", 0.9, resource={"user_active": True})
        ready = stage_prewarm_decision("stt", 0.9)

        self.assertEqual(wait["action"], "wait")
        self.assertEqual(delayed["action"], "delay")
        self.assertEqual(ready["action"], "prewarm")
        self.assertEqual(ready["next_stage"], "lora")

    def test_runtime_policy_hides_operation_modes_and_uses_hybrid_cut(self):
        settings = apply_autopilot_runtime_policy({"simple_operation_mode": "precise", "cut_boundary_level": "medium"})

        self.assertEqual(settings["simple_operation_mode"], "high")
        self.assertFalse(settings["operation_mode_choices_visible"])
        self.assertEqual(settings["cut_boundary_policy_mode"], "hybrid")
        self.assertEqual(settings["cut_boundary_level"], "medium")

    def test_stage_cache_key_uses_settings_model_and_cut_fingerprint(self):
        base = stage_cache_key(
            media_fingerprint={"path": "/tmp/a.mp4", "size": 10},
            stage="stt",
            settings={"a": 1},
            models={"stt": "large-v3"},
            hard_cut_fingerprint="abc",
        )
        changed = stage_cache_key(
            media_fingerprint={"path": "/tmp/a.mp4", "size": 10},
            stage="stt",
            settings={"a": 2},
            models={"stt": "large-v3"},
            hard_cut_fingerprint="abc",
        )

        self.assertNotEqual(base, changed)

    def test_stable_json_dumps_keeps_sorted_output_without_presorting_dict(self):
        payload = {"z": 1, "a": {"b": 2}}

        self.assertEqual(stable_json_dumps(payload), '{"a":{"b":2},"z":1}')

    def test_settings_and_model_hash_skip_unneeded_copy_paths(self):
        settings = {"z": 1, "a": 2}
        models = {"stt": "large-v3"}

        self.assertEqual(settings_hash(settings), settings_hash(dict(settings)))
        self.assertNotEqual(settings_hash(settings, keys=["a"]), settings_hash(settings, keys=["z"]))
        self.assertEqual(model_hash(models), model_hash(dict(models)))
        self.assertNotEqual(model_hash(models), model_hash(models, llm="codex"))

    def test_compressed_jsonl_and_memory_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = write_compressed_jsonl(Path(tmp) / "diag.jsonl", [{"a": 1}, {"b": 2}], prefer_zstd=False)
            rows = read_compressed_jsonl(out["path"])

        self.assertEqual(rows, [{"a": 1}, {"b": 2}])

        neg = NegativeCache(ttl_sec=30, max_items=2)
        neg.put("ollama:model", "failed")
        self.assertEqual(neg.get("ollama:model"), "failed")

        lru = LRUCacheManager(max_items=2)
        lru.put("a", 1)
        lru.put("b", 2)
        lru.get("a")
        lru.put("c", 3)
        self.assertIsNone(lru.get("b"))
        self.assertEqual(lru.get("a"), 1)

    def test_gzip_jsonl_write_streams_rows_without_materializing_input(self):
        def row_iter():
            yield {"a": 1}
            yield {"b": 2}

        with tempfile.TemporaryDirectory() as tmp:
            out = write_compressed_jsonl(Path(tmp) / "diag.jsonl", row_iter(), prefer_zstd=False)
            rows = read_compressed_jsonl(out["path"])

        self.assertEqual(out["rows"], 2)
        self.assertEqual(rows, [{"a": 1}, {"b": 2}])

    def test_zstd_jsonl_read_streams_without_full_read(self):
        class FakeReader:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def readable(self):
                return True

            def read(self, _size=-1):
                if _size == -1:
                    raise AssertionError("zstd jsonl should not read the full file at once")
                if not hasattr(self, "_lines"):
                    self._lines = [b'{"a":1}\n', b'{"b":2}\n', b""]
                return self._lines.pop(0)

        class FakeDecompressor:
            def stream_reader(self, _raw):
                return FakeReader()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "diag.jsonl.zst"
            path.write_bytes(b"compressed")
            fake_zstd = SimpleNamespace(ZstdDecompressor=lambda: FakeDecompressor())
            with patch.dict("sys.modules", {"zstandard": fake_zstd}):
                rows = read_compressed_jsonl(path)

        self.assertEqual(rows, [{"a": 1}, {"b": 2}])


if __name__ == "__main__":
    unittest.main()
