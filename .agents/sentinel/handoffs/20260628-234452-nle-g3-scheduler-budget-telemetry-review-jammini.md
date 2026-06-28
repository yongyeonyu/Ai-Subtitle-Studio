DEX_REVIEW_READY
역할: jammini
범위: AI Subtitle Studio G3 live NLE projection scheduler budget review
읽은 파일:
- core/runtime/subtitle_resource_manager.py
- core/runtime/multi_process.py
- core/automation/app_command_server.py
결론: G3 스케줄러-버젯 텔레메트리(scheduler-budget telemetry) 슬라이스의 자원 제어 격리 상태 및 데이터 정화 규격을 검토 완료했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🛡️ 1. 스레드 풀 격리 검증 (Worker Pool Isolation)

*   **워커 풀 간섭 차단**:
    - `subtitle_resource_manager.py` 내 `live_nle_projection_scheduler_budget(...)` 함수는 `"shares_subtitle_worker_pool": False`, `"dedicated_worker_count": 0`, `"max_projection_workers": 0`, `"uses_existing_row_snapshots": True` 사양을 명시적으로 확정하고 있습니다.
    - 이로 인해 live NLE projection 시각화 레이어가 자 자막 변환 파이프라인의 백그라운드 워커 스레드를 잠식하거나 스레드 할당을 방해하지 않는 아키텍처적 격리가 확보되었습니다.

---

### ⏳ 2. 부하 제어 메커니즘 (Pressure & Coalesce Throttling)

*   **포그라운드 신호 연동**:
    - 포그라운드 작업 라벨(`save`, `export`, `close`, `exit` 등)이 감지되거나, 메모리 부하 상태(`pressure_stage`가 `warning` 이상)인 경우, 스냅샷 병합 주기(`coalesce_interval_ms`)를 즉각 **450ms에서 900ms로 스로틀링(Throttling)**하여 부하를 낮춥니다.
    - 특히 `critical` 혹은 `exit` 라벨 활성화 시에는 `"projection_allowed": False`를 반환하여 NLE 프로젝션을 즉각 차단함으로써 시스템 자원을 원천 보호합니다.

---

### 📊 3. UDP 전송 최적화 및 텔레메트리 보존 (UDP Compact Parity)

*   **수치 데이터 한정 전송**:
    - `app_command_server.py`의 UDP 압축기(`_compact_status_data`)는 `subtitle_count`, `editor_aux_counts`, `editor_stt` 등 숫자/불리언 중심의 telemetry 메트릭만 포함하여 UDP Safe size인 8192바이트(또는 60000바이트) 이하로 패키징합니다.
    - 대량의 raw STT/VAD 자막행 데이터는 통신 페이로드에서 완벽히 배제되어 대역폭을 보존합니다.
*   **컴팩트 카운트 보존**:
    - 컴팩트 변환 시에도 `nle_runtime_track_counts`가 소실되지 않고 `compact["nle_runtime_track_counts"]`로 정확히 보존되므로, 전송 정합성이 유지됩니다.
*   **품질 정책 보호**:
    - `"quality_policy": "final_authority_unchanged"` 가이드가 그대로 투영되어 실시간 텔레메트리 정보 획득 중에도 저장소 및 자막의 본질적인 품질 규격이 100% 보장됩니다.
