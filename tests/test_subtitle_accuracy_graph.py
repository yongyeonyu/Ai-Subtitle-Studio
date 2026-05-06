import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.engine.subtitle_accuracy_graph import (
    SUBTITLE_ACCURACY_GRAPH_SCHEMA,
    build_subtitle_accuracy_graph,
    persist_subtitle_accuracy_graph,
)
from core.engine.subtitle_accuracy_pipeline import append_accuracy_decision


class SubtitleAccuracyGraphTests(unittest.TestCase):
    def _segment(self):
        row = {
            "id": "seg-1",
            "start": 0.0,
            "end": 1.5,
            "text": "BMW X5 테스트",
            "stt_candidates": [{"source": "STT1", "text": "BMW X5 테스트", "score": 0.91}],
            "_lora_generation_profile": {"top_score": 94.0, "used_kinds": {"truth_table": 2}, "examples": [{"text": "BMW X5 테스트", "score": 94}]},
            "_lora_segment_settings": {"split_length_threshold": 14},
            "_llm_gate_policy": {"task": "llm_gate", "call_llm": False, "reason": "skip_llm:high_lora_confidence"},
            "_deep_timing_policy": {"task": "subtitle_timing_adjustment", "start_shift": 0.01},
        }
        row = append_accuracy_decision(row, {"task": "llm_gate", "call_llm": False, "confidence": 0.91})
        return row

    def test_builds_full_graph_rows_from_runtime_metadata(self):
        graph = build_subtitle_accuracy_graph([self._segment()], {"sub_max_cps": 12}, media_path="/tmp/a.mp4", project_path="/tmp/p.json")

        self.assertEqual(graph["schema"], SUBTITLE_ACCURACY_GRAPH_SCHEMA)
        self.assertEqual(graph["segment_count"], 1)
        segment_graph = graph["segments"][0]
        self.assertEqual(segment_graph["raw_stt_outputs"]["stt_candidates"][0]["source"], "STT1")
        self.assertEqual(segment_graph["lora"]["profile"]["top_score"], 94.0)
        self.assertEqual(segment_graph["llm"]["llm_gate_policy"]["reason"], "skip_llm:high_lora_confidence")
        self.assertEqual(segment_graph["decision_graph"]["decisions"][0]["task"], "llm_gate")
        self.assertIn("final_explanation", segment_graph)

    def test_persists_graph_artifact_next_to_project_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = str(Path(tmpdir) / "sample.json")
            result = persist_subtitle_accuracy_graph([self._segment()], {"sub_max_cps": 12}, project_path=project_path)

            graph_path = Path(result["path"])
            payload = json.loads(graph_path.read_text(encoding="utf-8"))

            self.assertTrue(graph_path.exists())
            self.assertEqual(payload["schema"], SUBTITLE_ACCURACY_GRAPH_SCHEMA)
            self.assertEqual(payload["segments"][0]["segment_id"], "seg-1")

    def test_save_project_links_persisted_accuracy_graph_in_analysis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from core.project import project_manager

            with patch.object(project_manager, "PROJECTS_DIR", tmpdir):
                project_path = project_manager.create_project(
                    "graph_project",
                    user_settings={"accuracy_graph_persist_enabled": True, "sub_max_cps": 12},
                )
                project_manager.save_project(
                    filepath=project_path,
                    segments=[self._segment()],
                    user_settings={"accuracy_graph_persist_enabled": True, "sub_max_cps": 12},
                )
                project = project_manager.load_project(project_path)

            analysis = project["analysis"]
            graph_path = Path(analysis["subtitle_accuracy_graph_path"])
            self.assertTrue(graph_path.exists())
            self.assertEqual(analysis["subtitle_accuracy_graph_segment_count"], 1)
            self.assertEqual(project["editor_state"]["analysis"]["subtitle_accuracy_graph_path"], str(graph_path))


if __name__ == "__main__":
    unittest.main()
