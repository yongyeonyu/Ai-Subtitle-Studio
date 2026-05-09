import os
import tempfile
import unittest

from core.audio.native_ffmpeg_manager import NativeAudioPreprocessJob, NativeAudioPreprocessManager


class NativeFFmpegManagerTests(unittest.TestCase):
    def test_manager_pipelines_extract_and_enhance_in_input_order(self):
        progress = []
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs = [
                NativeAudioPreprocessJob(
                    index=i,
                    start_sec=float(i * 10),
                    end_sec=float((i + 1) * 10),
                    raw_wav=os.path.join(tmpdir, f"raw_{i}.wav"),
                    enhanced_wav=os.path.join(tmpdir, f"enhanced_{i}.wav"),
                )
                for i in range(4)
            ]

            def extract(job):
                self.assertGreater(job.duration_sec, 0)
                with open(job.raw_wav, "wb") as f:
                    f.write(b"raw")
                return True

            def enhance(job):
                self.assertTrue(os.path.exists(job.raw_wav))
                with open(job.enhanced_wav, "wb") as f:
                    f.write(b"enhanced")
                return True

            result = NativeAudioPreprocessManager(
                jobs=jobs,
                workers=2,
                extract_func=extract,
                enhance_func=enhance,
                progress_callback=lambda phase, done, total: progress.append((phase, done, total)),
            ).run()

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.extracted_count, 4)
        self.assertEqual(result.enhanced_count, 4)
        self.assertEqual(result.results, [job.enhanced_wav for job in jobs])
        self.assertIn(("extract", 4, 4), progress)
        self.assertIn(("enhance", 4, 4), progress)

    def test_manager_reports_extract_failure_without_enhance(self):
        enhanced = []
        with tempfile.TemporaryDirectory() as tmpdir:
            jobs = [
                NativeAudioPreprocessJob(
                    index=i,
                    start_sec=0.0,
                    end_sec=1.0,
                    raw_wav=os.path.join(tmpdir, f"raw_{i}.wav"),
                    enhanced_wav=os.path.join(tmpdir, f"enhanced_{i}.wav"),
                )
                for i in range(2)
            ]

            def extract(job):
                return job.index == 0

            def enhance(job):
                enhanced.append(job.index)
                return True

            result = NativeAudioPreprocessManager(
                jobs=jobs,
                workers=2,
                extract_func=extract,
                enhance_func=enhance,
            ).run()

        self.assertFalse(result.ok)
        self.assertTrue(any(error == "extract:1" for error in result.errors))
        self.assertLessEqual(enhanced.count(0), 1)
        self.assertNotIn(1, enhanced)


if __name__ == "__main__":
    unittest.main()
