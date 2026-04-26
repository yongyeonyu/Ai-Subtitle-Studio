# Version: 02.03.00
# Phase: PHASE1-B
import os
import json
import time
import threading  # 💡 [추가] 스레드 동시 접근 방지를 위한 모듈 임포트
from logger import get_logger

# dataset 폴더 위치 정의
TRACKER_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset", "auto_tracker.json")

class AutoTracker:
    def __init__(self):
        self._lock = threading.Lock()  # 💡 [추가] 파일 I/O 충돌 방지용 자물쇠 생성
        self.data = self._load()

    def _load(self) -> dict:
        with self._lock:  # 💡 [추가] 파일을 읽을 때 자물쇠 잠금
            if os.path.exists(TRACKER_FILE):
                try:
                    with open(TRACKER_FILE, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    return {}
            return {}

    def _save(self):
        with self._lock:  # 💡 [추가] 파일에 쓸 때 자물쇠 잠금
            os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
            try:
                with open(TRACKER_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                get_logger().log(f"⚠️ 추적기 저장 실패: {e}")

    # ... (이 아래의 clean_up 등 나머지 함수들은 그대로 유지하시면 됩니다) ...

    def clean_up(self, current_real_files: list):
        """앱 실행 시 상태 정리"""
        deleted_count = 0
        reset_count = 0
        keys_to_delete = [path for path in self.data.keys() if path not in current_real_files]
        
        for key in keys_to_delete:
            del self.data[key]
            deleted_count += 1
            
        for path, info in self.data.items():
            if info.get("status") in ["처리중", "업로드중"]:
                info["status"] = "신규"
                reset_count += 1
                
        if deleted_count > 0 or reset_count > 0:
            self._save()

    def sync_with_directory(self, current_real_files: list):
        """폴더에 있는 파일들을 장부에 '신규'로 강제 등록"""
        recovered_count = 0
        for filepath in current_real_files:
            if filepath not in self.data:
                try:
                    size = os.path.getsize(filepath)
                except: size = 0
                self.data[filepath] = {
                    "size": size,
                    "status": "신규",
                    "updated_at": time.time()
                }
                recovered_count += 1
        if recovered_count > 0:
            get_logger().log(f"♻️  트래커 복구: {recovered_count}개의 파일을 다시 작업 목록에 추가했습니다.")
            self._save()

    def check_and_reload(self, current_real_files: list) -> bool:
        """JSON 삭제 시 메모리 즉시 초기화"""
        if not os.path.exists(TRACKER_FILE):
            self.data = {} # 메모리 초기화
            self.sync_with_directory(current_real_files)
            return True
        return False

    def get_status(self, filepath: str) -> str:
        return self.data.get(filepath, {}).get("status")

    def update_status(self, filepath: str, size: int, status: str):
        self.data[filepath] = {"size": size, "status": status, "updated_at": time.time()}
        self._save()

    def mark_completed(self, filepath: str):
        if filepath in self.data:
            self.data[filepath]["status"] = "완료"
            self.data[filepath]["updated_at"] = time.time()
            self._save()