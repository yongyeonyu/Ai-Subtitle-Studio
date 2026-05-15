import io
import sys
import unittest

from core.runtime.logger import get_logger


class RuntimeLoggerTests(unittest.TestCase):
    def setUp(self):
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        logger = get_logger()
        clearer = getattr(logger, "clear_recent_lines", None)
        if callable(clearer):
            clearer()
        logger._terminal_stdout = None
        logger._terminal_stderr = None
        logger._stream_capture_installed = False

    def tearDown(self):
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr

    def test_log_keeps_raw_recent_line_but_prints_structured_terminal_line(self):
        logger = get_logger()
        raw_line = "  ⚠️ [컷 경계] 캐시 저장 실패: boom"
        buffer = io.StringIO()
        logger._terminal_stdout = buffer

        logger.log(raw_line)

        self.assertEqual(logger.recent_lines(1), [raw_line])
        printed_line = buffer.getvalue().strip()
        self.assertIn("WARN", printed_line)
        self.assertIn("cut-boundary", printed_line)
        self.assertIn("캐시 저장 실패: boom", printed_line)
        self.assertIn("#", printed_line)

    def test_multiline_log_prints_one_structured_terminal_line_per_nonempty_line(self):
        logger = get_logger()
        raw_block = "\n━━━ 자막 최적화 시작 ━━━\n🤖 Codex CLI 구독 인증으로 자막 LLM을 실행합니다.\n"
        buffer = io.StringIO()
        logger._terminal_stdout = buffer

        logger.log(raw_block)

        printed_lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(printed_lines), 2)
        self.assertIn("subtitle-llm", printed_lines[0])
        self.assertIn("subtitle-llm", printed_lines[1])
        self.assertEqual(logger.recent_lines(1), [raw_block])

    def test_stream_capture_prefixes_direct_stdout_and_stderr_writes(self):
        logger = get_logger()
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        logger.install_stream_capture(stdout=stdout_buffer, stderr=stderr_buffer)
        sys.stdout.write("plain stdout line\n")
        sys.stdout.flush()
        sys.stderr.write("plain stderr line\n")
        sys.stderr.flush()

        stdout_line = stdout_buffer.getvalue().strip()
        stderr_line = stderr_buffer.getvalue().strip()
        self.assertIn("INFO", stdout_line)
        self.assertIn("plain stdout line", stdout_line)
        self.assertIn("ERROR", stderr_line)
        self.assertIn("plain stderr line", stderr_line)
        self.assertIn("#", stdout_line)
        self.assertIn("#", stderr_line)


if __name__ == "__main__":
    unittest.main()
