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

    def test_recent_lines_returns_tail_in_original_order(self):
        logger = get_logger()
        logger._terminal_stdout = io.StringIO()
        for idx in range(20):
            logger.log(f"line-{idx}")

        self.assertEqual(logger.recent_lines(3), ["line-17", "line-18", "line-19"])
        self.assertEqual(len(logger.recent_lines(200)), 20)

    def test_recent_lines_and_filtered_returns_both_tails_from_one_scan(self):
        logger = get_logger()
        logger._terminal_stdout = io.StringIO()
        for line in (
            "plain-0",
            "STT 진행 중",
            "plain-1",
            "자막 생성 완료",
            "plain-2",
        ):
            logger.log(line)

        recent, filtered = logger.recent_lines_and_filtered(
            recent_limit=3,
            filtered_scan_limit=5,
            filtered_limit=2,
            predicate=lambda line: ("stt" in str(line).lower()) or ("자막 생성 완료" in str(line)),
        )

        self.assertEqual(recent, ["plain-1", "자막 생성 완료", "plain-2"])
        self.assertEqual(filtered, ["STT 진행 중", "자막 생성 완료"])

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
