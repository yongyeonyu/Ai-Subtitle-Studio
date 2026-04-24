# Version: 02.02.01
# Phase: PHASE1-B
import os, time, threading
from logger import get_logger
from core.auto_tracker import AutoTracker

class CloudSyncManager:
    def __init__(self, folder_path, callback, is_busy_callback=None):
        self.dropzone_path = folder_path  # 💡 수정 완료
        self.callback = callback          # 💡 수정 완료
        self.is_busy_callback = is_busy_callback
        self._running = False
        self._thread = None
        self.tracker = AutoTracker()
        self.valid_extensions = ('.m4a', '.wav', '.mp3', '.mp4', '.mov', '.MOV', '.MP4')
        self._size_cache = {}
        self._in_flight = set()
        
    def start(self):
        if not os.path.exists(self.dropzone_path): return
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._scan_loop, daemon=True, name="CloudSyncScanner")
            self._thread.start()
            get_logger().log(f"☁️  스마트 감시 가동 중: {os.path.basename(self.dropzone_path)}")

    def stop(self): self._running = False

    def _scan_loop(self):
        initial_files = self._get_valid_files()
        self.tracker.clean_up(initial_files)   # 앱 재시작 시 "처리중" → "신규" 리셋
        while self._running:
            current_files = self._get_valid_files()
            
            # 1. 캐시 리로드 체크
            # 변경 후 (매 반복마다 disk에서 reload — 백엔드가 저장한 "완료" 상태를 반영)
            self.tracker.data = self.tracker._load()
            
            new_ready_files = []
            now = time.time()
            
            # 2. 파일 용량 및 상태 검사
            for filepath in current_files:
                if filepath in self._in_flight: continue
                status = self.tracker.get_status(filepath)
                if status in ("완료", "처리중"): continue
                
                current_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                if current_size == 0: continue
                
                last_size, last_time = self._size_cache.get(filepath, (0, 0))
                
                if current_size == last_size:
                    if now - last_time > 3.0: # 용량 변화가 3초간 없으면 완료로 간주
                        new_ready_files.append(filepath)
                else:
                    if status != "업로드중":
                        self.tracker.update_status(filepath, current_size, "업로드중")
                    self._size_cache[filepath] = (current_size, now)

            is_busy = False
            if self.is_busy_callback and self.is_busy_callback():
                is_busy = True

            # 3. 작업 전달
            if new_ready_files:
                actual_targets = [f for f in new_ready_files if f not in self._in_flight]
                
                if actual_targets and not is_busy:
                    get_logger().log(f"🚀 {len(actual_targets)}개 파일의 작업을 시작합니다.")
                    for f in actual_targets:
                        self.tracker.update_status(f, os.path.getsize(f), "처리중")
                        self._in_flight.add(f)
                        if f in self._size_cache: del self._size_cache[f]
                    
                    # 🚨 [핵심 버그 수정] 비디오 플레이어 등 UI를 켜는 콜백 함수는 
                    # 반드시 QTimer.singleShot을 이용해 메인 UI 스레드로 토스해야 앱이 멈추지 않습니다!
                    # [수정 후] QTimer를 제거하고 직접 콜백 함수 호출
                    self.callback(actual_targets)
                elif actual_targets and is_busy:
                    pass 

            time.sleep(3)

    # 💡 작업이 완전히 끝났을 때 호출되는 메서드 (여기서 메모리 차단막을 풀어줌)
    def mark_done(self, filepath):
        if filepath in self._in_flight:
            self._in_flight.remove(filepath)
        self.tracker.update_status(filepath, os.path.getsize(filepath) if os.path.exists(filepath) else 0, "완료")

    def _get_valid_files(self) -> list:
        try:
            # 💡 [교정] os.listdir 결과를 sorted()로 감싸서 항상 이름순으로 정렬합니다.
            files = [os.path.join(self.dropzone_path, f) for f in os.listdir(self.dropzone_path) 
                    if not f.startswith('.') and f.lower().endswith(self.valid_extensions) and "_자막소스.mov" not in f]
            
            return sorted(files) # 👈 이 부분을 추가하여 순서를 고정합니다.
        except: return []