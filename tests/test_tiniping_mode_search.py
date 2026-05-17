import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.benchmark_tiniping_mode_search import _load_manual_seeds


class TinipingModeSearchTests(unittest.TestCase):
    def test_load_manual_seeds_accepts_mode_keyed_payload(self):
        payload = {
            "seeds": {
                "fast": [
                    {
                        "mode": "fast",
                        "primary_model": "stt1-fast",
                        "secondary_model": "stt2-fast",
                        "method": "stt1_only",
                        "run_llm": False,
                    }
                ],
                "auto": [
                    {
                        "mode": "auto",
                        "primary_model": "stt1-auto",
                        "secondary_model": "stt2-auto",
                        "method": "selective_ensemble",
                        "run_llm": False,
                    }
                ],
                "high": [
                    {
                        "mode": "high",
                        "primary_model": "stt1-high",
                        "secondary_model": "stt2-high",
                        "method": "selective_ensemble",
                        "run_llm": True,
                    }
                ],
            }
        }
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "seeds.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            loaded = _load_manual_seeds(path)

        self.assertEqual(loaded["fast"][0].primary_model, "stt1-fast")
        self.assertEqual(loaded["auto"][0].method, "selective_ensemble")
        self.assertTrue(loaded["high"][0].run_llm)


if __name__ == "__main__":
    unittest.main()
