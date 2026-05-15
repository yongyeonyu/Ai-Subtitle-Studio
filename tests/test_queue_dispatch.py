import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QTableWidgetItem

from ui.queue.queue_dispatch import dispatch_queue_header, dispatch_queue_status
from ui.queue.queue_dispatch import find_queue_row_for_media, sync_saved_queue_state
from ui.queue.queue_dispatch import queue_active_row_index, queue_progress_state
from ui.queue_widget import QueueMixin


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, *args):
        self.emissions.append(args)


class _SignalTarget:
    def __init__(self):
        self._sig_update_queue_payload = _Signal()
        self._sig_update_queue_header_payload = _Signal()
        self.status_calls = []
        self.header_calls = []

    def update_queue_status(self, payload):
        self.status_calls.append(payload)

    def update_queue_header(self, payload):
        self.header_calls.append(payload)


class _FallbackTarget:
    def __init__(self):
        self.status_calls = []
        self.header_calls = []

    def update_queue_status(self, payload):
        self.status_calls.append(payload)

    def update_queue_header(self, payload):
        self.header_calls.append(payload)


class QueueDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dispatch_queue_status_prefers_payload_signal(self):
        target = _SignalTarget()

        self.assertTrue(dispatch_queue_status(target, 2, "대기 중", "15:54", "1920x1080", "24:10"))
        self.assertEqual(target.status_calls, [])
        self.assertEqual(len(target._sig_update_queue_payload.emissions), 1)
        payload = target._sig_update_queue_payload.emissions[0][0]
        self.assertEqual(payload["idx"], 2)
        self.assertEqual(payload["status"], "대기 중")

    def test_dispatch_queue_header_prefers_payload_signal(self):
        target = _SignalTarget()

        self.assertTrue(dispatch_queue_header(target, 1, 3, 20, "2분 10초"))
        self.assertEqual(target.header_calls, [])
        self.assertEqual(len(target._sig_update_queue_header_payload.emissions), 1)
        payload = target._sig_update_queue_header_payload.emissions[0][0]
        self.assertEqual(payload["current"], 1)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["pct"], 20)

    def test_dispatch_queue_status_falls_back_to_updater(self):
        target = _FallbackTarget()

        self.assertTrue(dispatch_queue_status(target, {"row": 1, "status": "✅ 완료"}))
        self.assertEqual(target.status_calls[0]["idx"], 1)
        self.assertEqual(target.status_calls[0]["status"], "✅ 완료")

    def test_dispatch_queue_header_falls_back_to_updater(self):
        target = _FallbackTarget()

        self.assertTrue(dispatch_queue_header(target, {"idx": 2, "total": 2, "pct": 100, "eta": ""}))
        self.assertEqual(target.header_calls[0]["current"], 2)
        self.assertEqual(target.header_calls[0]["pct"], 100)

    def test_find_queue_row_for_media_prefers_matching_incomplete_row(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        queue.update_queue_status(0, "✅ 완료")
        row = find_queue_row_for_media(queue, media_path="/tmp/clip_b.mp4")
        self.assertEqual(row, 1)
        self.assertEqual(queue.queue_row_count(), 2)
        self.assertEqual(queue.queue_row_status_text(1), "대기 중")

    def test_sync_saved_queue_state_completes_single_row(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self.backend = None
                self.backend_fast = None
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "저장 준비 중")
        row = sync_saved_queue_state(queue, media_path="/tmp/clip_a.mp4")
        self.assertEqual(row, 0)
        self.assertEqual(queue.queue_table.item(0, 0).text(), "✅ 완료")
        self.assertEqual(queue.queue_header_lbl.text(), "큐 리스트 : (1/1) - 100% 완료")

    def test_queue_row_expected_and_elapsed_helpers_use_queue_state(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {0: 75.0}
                self._file_start_times = {0: 100.0}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self.backend = None
                self.backend_fast = None
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "자막 생성 중", "01:15", "1920x1080", "01:15")
        queue._file_start_times[0] = 100.0
        self.assertEqual(queue.queue_row_expected_seconds(0), 75.0)
        self.assertEqual(queue.queue_row_elapsed_seconds(0, now_ts=125.0), 25.0)

    def test_queue_row_metrics_collects_status_expected_elapsed_and_label(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {0: 75.0}
                self._file_start_times = {0: 100.0}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self.backend = None
                self.backend_fast = None
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "자막 생성 중", "01:15", "1920x1080", "01:15")
        queue._file_start_times[0] = 100.0

        metrics = queue.queue_row_metrics(0, now_ts=125.0)
        self.assertEqual(metrics["status"], "자막 생성 중")
        self.assertFalse(metrics["done"])
        self.assertTrue(metrics["status_active"])
        self.assertTrue(metrics["started"])
        self.assertEqual(metrics["expected"], 75.0)
        self.assertEqual(metrics["elapsed"], 25.0)
        self.assertEqual(metrics["expected_label"], "01:15")

    def test_queue_progress_metrics_exposes_completion_counts(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 2
                self._total_files = 3
                self._real_pct = 33
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4", "/tmp/clip_c.mp4"])
        queue.update_queue_status(0, "✅ 완료")
        queue.update_queue_status(1, "✅기존자막")
        queue.update_queue_status(2, "대기 중")

        metrics = queue.queue_progress_metrics(now_ts=125.0, running=False)
        self.assertEqual(metrics["done_count"], 1)
        self.assertEqual(metrics["reuse_count"], 1)
        self.assertEqual(metrics["completion_percent"], 50)

    def test_queue_completion_status_records_elapsed_and_expected_eta(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue._file_start_times[0] = 100.0
        queue._expected_seconds[0] = 20.0

        with patch("ui.queue_widget.time.time", return_value=130.0):
            queue.update_queue_status(0, "✅ 완료", "00:20", "1920x1080", "00:20")

        self.assertEqual(queue.queue_row_status_text(0), "✅ 완료")
        self.assertEqual(queue.queue_table.item(0, 4).text(), "00:30 / 00:20")
        self.assertEqual(queue.queue_header_lbl.text(), "큐 리스트 : (1/1) - 100% 완료")

    def test_completed_row_ignores_non_restart_status_updates(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "✅ 완료", "00:20", "1920x1080", "00:20")
        queue.update_queue_status(0, "후처리 준비 중", "00:15", "1280x720", "00:15")

        self.assertEqual(queue.queue_row_status_text(0), "✅ 완료")
        self.assertEqual(queue.queue_table.item(0, 2).text(), "1920x1080")

    def test_completed_row_allows_restart_status_updates(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 100
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "✅ 완료", "00:20", "1920x1080", "00:20")
        queue.update_queue_status(0, "재시작 준비 중", "00:15", "1280x720", "00:15")

        self.assertEqual(queue.queue_row_status_text(0), "재시작 준비 중")
        self.assertEqual(queue.queue_table.item(0, 2).text(), "1280x720")
        self.assertEqual(queue.queue_table.item(0, 4).text(), "00:00 / 00:15")

    def test_completed_row_reopens_for_roughcut_followup_without_resetting_elapsed(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 1
                self._real_pct = 100
                self._expected_seconds = {0: 120.0}
                self._file_start_times = {0: 100.0}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self.backend = None
                self.backend_fast = None
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue._expected_seconds[0] = 120.0
        queue._file_start_times[0] = 100.0
        with patch("ui.queue_widget.time.time", return_value=130.0):
            queue.update_queue_status(0, "✅ 완료", "02:00", "1920x1080", "02:00")
        with patch("ui.queue_widget.time.time", return_value=140.0):
            queue.update_queue_status(0, "🤖 [러프컷 LLM] 후처리 중", "02:00", "1920x1080", "02:00")
            queue._update_live_queue_header()

        self.assertEqual(queue.queue_row_status_text(0), "🤖 [러프컷 LLM] 후처리 중")
        self.assertEqual(queue._file_start_times[0], 100.0)
        self.assertNotIn(0, queue._file_complete_times)
        self.assertEqual(queue.queue_table.item(0, 4).text(), "00:40 / 02:00")
        self.assertEqual(queue.queue_header_lbl.text(), "큐 리스트 : (1/1) - 33% 완료")

    def test_queue_sidebar_helpers_expose_header_items_probe_and_completion(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        queue.update_queue_status(0, "✅ 완료")
        queue.update_queue_status(1, "⏳ [STT] Whisper 중", "20", "1920x1080", "00:10")
        queue.update_queue_header(2, 2, 50, "")

        header = queue.queue_sidebar_header_text()
        items = queue.queue_sidebar_items()
        probe = queue.queue_status_probe_parts(1, (0, 4))
        completion = queue.queue_completion_state()

        self.assertEqual(header, "큐 리스트 : (2/2) - 50% 완료")
        self.assertEqual(items[0]["statusDisplay"], "완료")
        self.assertTrue(items[0]["done"])
        self.assertTrue(items[1]["active"])
        self.assertIn("Whisper", probe[0])
        self.assertEqual(probe[1], "00:00 / 00:20")
        self.assertEqual(completion["row_count"], 2)
        self.assertEqual(completion["done_rows"], 1)
        self.assertFalse(completion["all_done"])

        queue._refresh_sidebar_queue_cache()
        queue.queue_table = None
        cached_items = queue.queue_sidebar_items()
        cached_probe = queue.queue_status_probe_parts(1, (0, 2, 4))

        self.assertEqual(cached_items[1]["info"], "1920x1080")
        self.assertIn("Whisper", cached_probe[0])
        self.assertEqual(cached_probe[1], "1920x1080")
        self.assertEqual(cached_probe[2], "00:00 / 00:20")

    def test_queue_row_snapshot_reads_table_and_cache(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "⏳ [STT] Whisper 중", "20", "1920x1080", "00:10")

        table_snapshot = queue.queue_row_snapshot(0)
        self.assertEqual(table_snapshot["status"], "⏳ [STT] Whisper 중")
        self.assertEqual(table_snapshot["file"], "clip_a.mp4")
        self.assertEqual(table_snapshot["info"], "1920x1080")
        self.assertEqual(table_snapshot["eta"], "00:00 / 00:20")

        queue._refresh_sidebar_queue_cache()
        queue.queue_table = None
        cache_snapshot = queue.queue_row_snapshot(0)
        self.assertEqual(cache_snapshot["status"], "⏳ [STT] Whisper 중")
        self.assertEqual(cache_snapshot["file"], "clip_a.mp4")
        self.assertEqual(cache_snapshot["info"], "1920x1080")
        self.assertEqual(cache_snapshot["eta"], "00:00 / 00:20")

    def test_queue_row_visual_state_uses_row_items_and_palette_helpers(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4"])
        queue.update_queue_status(0, "✅ 완료")

        items = queue._queue_row_items(0)
        self.assertEqual(len(items), 5)
        fg, bg = queue._queue_row_visual_palette(0)
        for item in items:
            self.assertEqual(item.foreground().color().name(), fg.name())
            self.assertEqual(item.background().color().name(), bg.name())

    def test_init_queue_list_seeds_row_cache_and_sidebar_payload(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])

        self.assertEqual(queue.queue_row_count(), 2)
        self.assertEqual(len(queue._queue_row_cache), 2)
        self.assertEqual(queue._queue_row_cache[0]["file"], "clip_a.mp4")
        self.assertEqual(queue._queue_row_cache[1]["file"], "clip_b.mp4")
        self.assertEqual(queue._queue_row_cache[0]["statusDisplay"], "대기 중")

        payload = queue.queue_sidebar_panel_payload()
        self.assertEqual(payload["header"], "큐 리스트 : (1/2) - 0% 완료")
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["statusDisplay"], "대기 중")
        self.assertFalse(payload["items"][0]["active"])
        self.assertFalse(payload["items"][1]["active"])

    def test_queue_sidebar_panel_payload_uses_explicit_header_and_items_helpers(self):
        class _DummyQueue(QueueMixin):
            def _queue_sidebar_panel_header(self):
                return "helper-header"

            def _queue_sidebar_panel_items(self):
                return [{"file": "helper-row.mp4", "statusDisplay": "대기 중"}]

        queue = _DummyQueue()
        payload = queue.queue_sidebar_panel_payload()
        self.assertEqual(payload["header"], "helper-header")
        self.assertEqual(payload["items"][0]["file"], "helper-row.mp4")

    def test_apply_queue_sidebar_panel_payload_prefers_payload_setter(self):
        class _Panel:
            def __init__(self):
                self.payloads = []
                self.legacy_calls = []

            def set_queue_payload(self, payload):
                self.payloads.append(dict(payload or {}))

            def set_queue(self, header, items):
                self.legacy_calls.append((header, list(items or [])))

        panel = _Panel()
        queue = type("_QueueOwner", (QueueMixin,), {})()

        applied = queue._apply_queue_sidebar_panel_payload(
            panel,
            {"header": "helper-header", "items": [{"file": "helper-row.mp4"}]},
        )
        self.assertTrue(applied)
        self.assertEqual(panel.payloads[0]["header"], "helper-header")
        self.assertEqual(panel.legacy_calls, [])

    def test_apply_queue_sidebar_panel_payload_falls_back_to_legacy_setter(self):
        class _Panel:
            def __init__(self):
                self.calls = []

            def set_queue(self, header, items):
                self.calls.append((header, list(items or [])))

        panel = _Panel()
        queue = type("_QueueOwner", (QueueMixin,), {})()

        applied = queue._apply_queue_sidebar_panel_payload(
            panel,
            {"header": "helper-header", "items": [{"file": "helper-row.mp4"}]},
        )
        self.assertTrue(applied)
        self.assertEqual(panel.calls[0][0], "helper-header")
        self.assertEqual(panel.calls[0][1][0]["file"], "helper-row.mp4")

    def test_sync_sidebar_queue_panel_clears_panel_reference_after_runtime_error(self):
        class _Panel:
            def set_queue_payload(self, payload):
                raise RuntimeError("deleted")

        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.sidebar_queue_panel = _Panel()

            def _queue_sidebar_panel_header(self):
                return "helper-header"

            def _queue_sidebar_panel_items(self):
                return [{"file": "helper-row.mp4"}]

        queue = _DummyQueue()
        self.assertFalse(queue.sync_sidebar_queue_panel())
        self.assertIsNone(queue.sidebar_queue_panel)

    def test_sync_queue_row_cache_from_table_row_backfills_placeholder_entries(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = []
                self._sidebar_queue_cache_items = []
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        queue.init_queue_list(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        queue._queue_row_cache = []

        queue._sync_queue_row_cache_from_table_row(1)

        self.assertEqual(len(queue._queue_row_cache), 2)
        self.assertEqual(queue._queue_row_cache[0]["file"], "-")
        self.assertEqual(queue._queue_row_cache[1]["file"], "clip_b.mp4")
        self.assertEqual(queue._queue_row_cache[1]["statusDisplay"], "대기 중")

    def test_queue_sidebar_items_prefers_row_cache_then_sidebar_cache(self):
        class _DummyQueue(QueueMixin):
            def __init__(self):
                self.queue_table = None
                self.queue_header_lbl = QLabel("")
                self._current_file_idx = 1
                self._total_files = 0
                self._real_pct = 0
                self._expected_seconds = {}
                self._file_start_times = {}
                self._file_complete_times = {}
                self._queue_row_cache = [{"file": "row-cache.mp4", "statusDisplay": "대기 중"}]
                self._sidebar_queue_cache_items = [{"file": "sidebar-cache.mp4", "statusDisplay": "완료"}]
                self._sidebar_queue_cache_header = ""
                self._live_timer = type("_Timer", (), {"start": lambda _self, _interval: None, "stop": lambda _self: None})()

            def _show_bottom_queue_table(self):
                pass

            def _sync_sidebar_queue_panel(self):
                pass

        queue = _DummyQueue()
        items = queue.queue_sidebar_items()
        self.assertEqual(items[0]["file"], "sidebar-cache.mp4")

        queue._queue_row_cache = []
        items = queue._queue_sidebar_items_from_cache()
        self.assertEqual(items[0]["file"], "sidebar-cache.mp4")

    def test_sync_saved_queue_state_prefers_queue_mixin_method_when_available(self):
        class _QueueOwner:
            def __init__(self):
                self.calls = []

            def sync_saved_queue_state_for_media(self, media_path="", current_row_hint=None):
                self.calls.append((str(media_path or ""), current_row_hint))
                return 7

        owner = _QueueOwner()
        row = sync_saved_queue_state(owner, media_path="/tmp/clip_a.mp4", current_row_hint=2)
        self.assertEqual(row, 7)
        self.assertEqual(owner.calls, [("/tmp/clip_a.mp4", 2)])

    def test_sync_saved_queue_state_prefers_public_refresh_queue_views(self):
        class _QueueOwner:
            def __init__(self):
                self.queue_table = QTableWidget(0, 5)
                self.queue_header_lbl = QLabel("")
                self.refreshed = 0

            def update_queue_status(self, payload):
                self.last_status = dict(payload or {})

            def refresh_queue_views(self):
                self.refreshed += 1

        owner = _QueueOwner()
        owner.queue_table.setRowCount(2)
        owner.queue_table.setItem(0, 0, QTableWidgetItem("대기 중"))
        owner.queue_table.setItem(0, 1, QTableWidgetItem("clip_a.mp4"))
        owner.queue_table.setItem(1, 0, QTableWidgetItem("저장 준비 중"))
        owner.queue_table.setItem(1, 1, QTableWidgetItem("clip_b.mp4"))

        row = sync_saved_queue_state(owner, media_path="/tmp/clip_b.mp4", current_row_hint=1)
        self.assertEqual(row, 1)
        self.assertEqual(owner.refreshed, 1)
        self.assertEqual(owner.last_status["status"], "✅ 완료")

    def test_queue_state_helpers_prefer_target_methods(self):
        class _QueueOwner:
            def queue_active_row_index(self):
                return 4

            def queue_progress_state(self):
                return {"current": 5, "total": 9, "pct": 33}

        owner = _QueueOwner()
        self.assertEqual(queue_active_row_index(owner), 4)
        self.assertEqual(
            queue_progress_state(owner, current_default=1, total_default=2, pct_default=0),
            {"current": 5, "total": 9, "pct": 33},
        )

    def test_queue_progress_state_falls_back_to_attributes(self):
        owner = type("_Owner", (), {"_current_file_idx": 2, "_total_files": 7, "_real_pct": 14})()
        self.assertEqual(
            queue_progress_state(owner, current_default=1, total_default=1, pct_default=0),
            {"current": 2, "total": 7, "pct": 14},
        )


if __name__ == "__main__":
    unittest.main()
