# Version: 02.03.00
# Phase: PHASE1-B
import os
import time
import threading
from logger import get_logger
from core.auto_tracker import AutoTracker


class CloudSyncManager:
    def __init__(self, folder_path, callback, is_busy_callback=None, *, mode="flat", scan_interval=None, stable_seconds=None, exclude_callback=None):
        self.dropzone_path = folder_path
        self.callback = callback
        self.is_busy_callback = is_busy_callback
        self.mode = mode
        self.scan_interval = 60 if mode == "nas" else (scan_interval or 3)
        self.stable_seconds = 300 if mode == "nas" else (stable_seconds or 3)
        self.exclude_callback = exclude_callback
        self._running = False
        self._thread = None
        self.tracker = AutoTracker()
        self.valid_extensions = ('.m4a', '.wav', '.mp3', '.mp4', '.mov', '.MOV', '.MP4')
        self._size_cache = {}
        self._in_flight = set()
        self._folder_jobs = {}
        self._file_to_folder = {}

    def configure(self, *, mode=None, scan_interval=None, stable_seconds=None, exclude_callback=None):
        if mode is not None:
            self.mode = mode
        if scan_interval is not None:
            self.scan_interval = scan_interval
        if stable_seconds is not None:
            self.stable_seconds = stable_seconds
        if exclude_callback is not None:
            self.exclude_callback = exclude_callback

    def start(self):
        if not self.dropzone_path or not os.path.exists(self.dropzone_path):
            return
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._scan_loop, daemon=True, name=f"CloudSyncScanner-{self.mode}")
            self._thread.start()
            label = "NAS" if self.mode == "nas" else "iCloud"
            get_logger().log(f"☁️  {label} 스마트 감시 가동 중: {os.path.basename(self.dropzone_path)}")

    def stop(self):
        self._running = False

    def _scan_loop(self):
        initial_files = self._get_valid_files()
        self.tracker.clean_up(initial_files)
        while self._running:
            self.tracker.data = self.tracker._load()
            if self.mode == "nas":
                self._scan_nas_once()
            else:
                self._scan_flat_once()
            time.sleep(max(1, int(self.scan_interval)))

    def _is_busy(self):
        return bool(self.is_busy_callback and self.is_busy_callback())

    def _scan_flat_once(self):
        current_files = self._get_valid_files()
        new_ready_files = []
        now = time.time()
        for filepath in current_files:
            if filepath in self._in_flight:
                continue
            status = self.tracker.get_status(filepath)
            if status in ("완료", "처리중"):
                continue
            current_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            if current_size == 0:
                continue
            last_size, last_time = self._size_cache.get(filepath, (0, 0))
            if current_size == last_size:
                if now - last_time >= self.stable_seconds:
                    new_ready_files.append(filepath)
            else:
                if status != "업로드중":
                    self.tracker.update_status(filepath, current_size, "업로드중")
                self._size_cache[filepath] = (current_size, now)
        actual_targets = [f for f in new_ready_files if f not in self._in_flight]
        if actual_targets and not self._is_busy():
            get_logger().log(f"🚀 {len(actual_targets)}개 파일의 작업을 시작합니다.")
            for f in actual_targets:
                self.tracker.update_status(f, os.path.getsize(f), "처리중")
                self._in_flight.add(f)
                self._size_cache.pop(f, None)
            self.callback(actual_targets)

    def _scan_nas_once(self):
        if self._is_busy() or self._in_flight:
            return
        now = time.time()
        for folder in self._get_nas_leaf_folders():
            status = self.tracker.get_status(folder)
            if status in ("완료", "처리중"):
                continue
            files = self._files_in_folder(folder)
            if not files:
                continue
            size = self._folder_size(files)
            if size <= 0:
                continue
            last_size, last_time = self._size_cache.get(folder, (0, 0))
            if size == last_size:
                if now - last_time >= self.stable_seconds:
                    self._start_nas_folder_job(folder, files, size)
                    return
            else:
                if status != "업로드중":
                    self.tracker.update_status(folder, size, "업로드중")
                self._size_cache[folder] = (size, now)

    def _start_nas_folder_job(self, folder, files, size):
        folder_name = os.path.basename(folder.rstrip(os.sep)) or folder
        self.tracker.update_status(folder, size, "처리중")
        self._folder_jobs[folder] = {"files": set(files), "done": set(), "size": size, "started_at": time.time()}
        for f in files:
            self.tracker.update_status(f, os.path.getsize(f) if os.path.exists(f) else 0, "처리중")
            self._in_flight.add(f)
            self._file_to_folder[f] = folder
        self._size_cache.pop(folder, None)
        get_logger().log(f"🚀 NAS 자동 시작: {folder_name} / 파일 {len(files)}개 / {self._format_size(size)}")
        self.callback(files)

    def mark_done(self, filepath):
        if filepath in self._in_flight:
            self._in_flight.remove(filepath)
        self.tracker.update_status(filepath, os.path.getsize(filepath) if os.path.exists(filepath) else 0, "완료")
        if self.mode != "nas":
            return
        folder = self._file_to_folder.pop(filepath, None)
        if not folder or folder not in self._folder_jobs:
            return
        job = self._folder_jobs[folder]
        job["done"].add(filepath)
        if job["files"] and job["done"] >= job["files"]:
            self.tracker.update_status(folder, int(job.get("size", 0)), "완료")
            elapsed = max(0, time.time() - float(job.get("started_at", time.time())))
            get_logger().log(f"✅ NAS 작업완료: {os.path.basename(folder)} / 파일 {len(job['files'])}개 / {self._format_size(int(job.get('size', 0)))} / {elapsed:.1f}초")
            del self._folder_jobs[folder]

    def _get_valid_files(self) -> list:
        if self.mode == "nas":
            files = []
            for folder in self._get_nas_leaf_folders():
                files.extend(self._files_in_folder(folder))
            return sorted(files)
        try:
            files = [os.path.join(self.dropzone_path, f) for f in os.listdir(self.dropzone_path) if not f.startswith('.') and f.lower().endswith(self.valid_extensions) and "_자막소스.mov" not in f]
            return sorted(files)
        except Exception:
            return []

    def _get_excluded_folders(self):
        try:
            excluded = self.exclude_callback() if self.exclude_callback else []
            return {os.path.normpath(p) for p in excluded if p}
        except Exception:
            return set()

    def _is_excluded(self, path, excluded):
        norm = os.path.normpath(path)
        for ex in excluded:
            if norm == ex or norm.startswith(ex + os.sep):
                return True
        return False

    def _get_nas_leaf_folders(self):
        root = self.dropzone_path
        if not root or not os.path.exists(root):
            return []
        excluded = self._get_excluded_folders()
        leaf = []
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted([d for d in dirs if not d.startswith('.')])
            if self._is_excluded(current, excluded):
                dirs[:] = []
                continue
            valid_here = any((not f.startswith('.')) and f.lower().endswith(self.valid_extensions) and "_자막소스.mov" not in f for f in files)
            valid_child_dir = False
            for d in dirs:
                dp = os.path.join(current, d)
                if self._is_excluded(dp, excluded):
                    continue
                try:
                    child_files = os.listdir(dp)
                except Exception:
                    continue
                if any((not cf.startswith('.')) and cf.lower().endswith(self.valid_extensions) for cf in child_files):
                    valid_child_dir = True
            if valid_here and not valid_child_dir:
                leaf.append(current)
        return sorted(leaf, key=lambda p: [part.lower() for part in os.path.relpath(p, root).split(os.sep)])

    def _files_in_folder(self, folder):
        try:
            return sorted(os.path.join(folder, f) for f in os.listdir(folder) if not f.startswith('.') and f.lower().endswith(self.valid_extensions) and "_자막소스.mov" not in f)
        except Exception:
            return []

    def _folder_size(self, files):
        total = 0
        for f in files:
            try:
                total += os.path.getsize(f)
            except Exception:
                pass
        return total

    def _format_size(self, size):
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f}{unit}"
            value /= 1024
