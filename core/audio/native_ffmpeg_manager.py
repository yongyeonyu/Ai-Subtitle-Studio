from __future__ import annotations

"""Native FFmpeg job orchestration for overlapped audio preprocessing."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import queue
import threading
from typing import Callable


@dataclass(frozen=True)
class NativeAudioPreprocessJob:
    index: int
    start_sec: float
    end_sec: float
    raw_wav: str
    enhanced_wav: str

    @property
    def duration_sec(self) -> float:
        return max(0.0, float(self.end_sec or 0.0) - float(self.start_sec or 0.0))


@dataclass(frozen=True)
class NativeAudioPreprocessResult:
    ok: bool
    results: list[str | None]
    errors: list[str]
    extracted_count: int
    enhanced_count: int


ProgressCallback = Callable[[str, int, int], None]
JobFunc = Callable[[NativeAudioPreprocessJob], bool]


class NativeAudioPreprocessManager:
    """Pipeline FFmpeg extraction into native audio enhancement workers."""

    def __init__(
        self,
        *,
        jobs: list[NativeAudioPreprocessJob],
        workers: int,
        extract_func: JobFunc,
        enhance_func: JobFunc,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.jobs = list(jobs)
        self.workers = max(1, min(int(workers or 1), max(1, len(self.jobs) or 1)))
        self.extract_func = extract_func
        self.enhance_func = enhance_func
        self.progress_callback = progress_callback

    def run(self) -> NativeAudioPreprocessResult:
        total = len(self.jobs)
        if total <= 0:
            return NativeAudioPreprocessResult(True, [], [], 0, 0)

        work_queue: queue.Queue[tuple[int, NativeAudioPreprocessJob] | None] = queue.Queue(
            maxsize=max(1, self.workers * 2)
        )
        stop_event = threading.Event()
        state_lock = threading.Lock()
        errors: list[str] = []
        results: list[str | None] = [None] * total
        extracted_count = 0
        enhanced_count = 0

        def add_error(message: str) -> None:
            with state_lock:
                errors.append(message)

        def mark_progress(phase: str) -> None:
            nonlocal extracted_count, enhanced_count
            with state_lock:
                if phase == "extract":
                    extracted_count += 1
                    done = extracted_count
                else:
                    enhanced_count += 1
                    done = enhanced_count
            if self.progress_callback is not None:
                self.progress_callback(phase, done, total)

        def producer() -> None:
            try:
                for position, job in enumerate(self.jobs):
                    if stop_event.is_set():
                        break
                    try:
                        ok = bool(self.extract_func(job))
                    except Exception as exc:
                        add_error(f"extract:{job.index}:{exc}")
                        stop_event.set()
                        break
                    if not ok:
                        add_error(f"extract:{job.index}")
                        stop_event.set()
                        break
                    mark_progress("extract")
                    work_queue.put((position, job))
            finally:
                for _ in range(self.workers):
                    work_queue.put(None)

        def consumer() -> None:
            while True:
                item = work_queue.get()
                try:
                    if item is None:
                        return
                    position, job = item
                    if stop_event.is_set():
                        continue
                    try:
                        ok = bool(self.enhance_func(job))
                    except Exception as exc:
                        add_error(f"enhance:{job.index}:{exc}")
                        stop_event.set()
                        continue
                    if not ok:
                        add_error(f"enhance:{job.index}")
                        stop_event.set()
                        continue
                    results[position] = job.enhanced_wav
                    mark_progress("enhance")
                finally:
                    work_queue.task_done()

        producer_thread = threading.Thread(target=producer, name="native-audio-producer", daemon=True)
        producer_thread.start()
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="native-audio-filter") as executor:
            futures = [executor.submit(consumer) for _ in range(self.workers)]
            producer_thread.join()
            work_queue.join()
            for future in futures:
                future.result()

        return NativeAudioPreprocessResult(
            ok=not errors and all(path for path in results),
            results=results,
            errors=list(errors),
            extracted_count=extracted_count,
            enhanced_count=enhanced_count,
        )
