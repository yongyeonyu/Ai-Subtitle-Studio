import unittest

from ui.queue.queue_formatting import (
    build_queue_sidebar_item,
    build_queue_header_payload,
    build_queue_status_payload,
    DEFAULT_QUEUE_HEADER,
    format_queue_card_time,
    format_queue_clock,
    format_queue_header,
    normalize_queue_header_payload,
    normalize_queue_status_payload,
    normalize_queue_header_text,
    parse_queue_seconds_value,
    plain_queue_status,
    queue_expected_display_text,
    queue_expected_time_is_unknown,
    queue_status_flags,
)


class QueueFormattingTests(unittest.TestCase):
    def test_format_queue_header_clamps_and_formats(self):
        self.assertEqual(format_queue_header(1, 3, 17), "큐 리스트 : (1/3) - 17% 완료")
        self.assertEqual(format_queue_header(-1, "x", 120), "큐 리스트 : (0/0) - 100% 완료")

    def test_normalize_queue_header_text_reuses_existing_text(self):
        self.assertEqual(
            normalize_queue_header_text("📋 처리할 파일 리스트 : (1/2) - 30% 진행 중"),
            "큐 리스트 : (1/2) - 30% 완료",
        )
        self.assertEqual(normalize_queue_header_text("", current=2, total=5, pct=40), "큐 리스트 : (2/5) - 40% 완료")

    def test_parse_and_display_queue_time_values(self):
        self.assertEqual(parse_queue_seconds_value("01:15"), 75.0)
        self.assertEqual(parse_queue_seconds_value("01:02:03"), 3723.0)
        self.assertTrue(queue_expected_time_is_unknown("00:00"))
        self.assertEqual(queue_expected_display_text("계산 중"), "예상불가")
        self.assertEqual(format_queue_clock(125), "02:05")

    def test_format_queue_card_time_prefers_elapsed_over_expected(self):
        self.assertEqual(format_queue_card_time("01:35 / 02:59", "02:59"), "01:35 / 02:59")
        self.assertEqual(format_queue_card_time("계산 중", "02:59"), "예상불가")
        self.assertEqual(format_queue_card_time("02:59", "02:59"), "00:00 / 02:59")

    def test_plain_queue_status_and_flags_strip_decorators(self):
        self.assertEqual(plain_queue_status("✅ 자막 생성 완료"), "자막 생성 완료")
        self.assertEqual(queue_status_flags("✅ 자막 생성 완료"), (True, False, False))
        self.assertEqual(queue_status_flags("오류 발생"), (False, True, False))
        self.assertEqual(queue_status_flags("자막 생성 중"), (False, False, True))

    def test_build_queue_sidebar_item_normalizes_display_payload(self):
        item = build_queue_sidebar_item(
            order=2,
            raw_status="⏳ 오디오 추출 중",
            file_text="sample.mp4",
            eta_text="00:05 / 15:54",
            duration_text="15:54",
            active=True,
        )
        self.assertEqual(item["order"], "2")
        self.assertEqual(item["status"], "오디오 추출 중")
        self.assertEqual(item["statusDisplay"], "오디오 추출 중")
        self.assertTrue(item["active"])
        self.assertFalse(item["done"])
        self.assertEqual(item["eta"], "00:05 / 15:54")

    def test_queue_status_payload_accepts_dict_aliases(self):
        built = build_queue_status_payload(1, "대기 중", "20", "1920x1080", "00:10")
        self.assertEqual(built["idx"], 1)
        normalized = normalize_queue_status_payload(
            {
                "row": 2,
                "status": "🎯 자막 생성 중",
                "eta": "15:54",
                "info": "3840x2160",
                "duration": "24:10",
            }
        )
        self.assertEqual(normalized["idx"], 2)
        self.assertEqual(normalized["time_txt"], "15:54")
        self.assertEqual(normalized["info_txt"], "3840x2160")
        self.assertEqual(normalized["len_txt"], "24:10")

    def test_queue_header_payload_accepts_dict_aliases(self):
        built = build_queue_header_payload(1, 3, 5, "2분 10초")
        self.assertEqual(built["pct"], 5)
        normalized = normalize_queue_header_payload({"idx": 2, "total": 4, "pct": 50, "eta": "1분 20초"})
        self.assertEqual(normalized["current"], 2)
        self.assertEqual(normalized["total"], 4)
        self.assertEqual(normalized["pct"], 50)
        self.assertEqual(normalized["eta_str"], "1분 20초")


if __name__ == "__main__":
    unittest.main()
