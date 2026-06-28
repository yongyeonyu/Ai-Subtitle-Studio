DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE preview trace event scout

findings:
1. **NLE Preview Trace Event 로그 추가 제안 검토**:
   - **안전성 판정**: **안전함 (Accept 권장)**.
   - **근거**: 실 디코더 변경이나 UI 렌더링에 일체 개입하지 않고, 기존의 `TraceLogger` 비동기 이벤트를 통해 preview 캐시 hit/miss/ready 메트릭만을 덤프하는 진단 보강 작업이므로 위험이 전혀 없음.
2. **Event Field Shortlist**:
   - `event_type`: `"preview_cache_query"`, `"preview_frame_ready"`, `"preview_decode_scheduled"`
   - `timestamp_utc`: UTC ISO8601 string
   - `source_media_hash`: `_short_hash(media_path)`
   - `requested_seconds`: 요청된 영상 타임코드 (float)
   - `snapped_seconds`: nearest frame snap 타임코드 (float)
   - `cache_hit`: 캐시 적중 여부 (bool)
   - `elapsed_ms`: 썸네일 조회/디코드 경과시간 (float)
   - `status`: `"hit"`, `"miss"`, `"decoding"`, `"ready"`
3. **위험 및 방어 포인트 (Risks & Guard)**:
   - **UI thread block 리스크 (Critical)**: 플레이헤드를 고속 드래그할 때 1초에 60회 이상의 query 로그가 동기적으로 파일에 써지면 playback UI가 stuttering에 걸림.
   - **해결책**: 반드시 `TraceLogger` 의 전역 비동기 queue 및 worker 스레드를 거쳐 write해야 하며, query/response 등의 high-frequency 이벤트를 trace bundle에 실을 때는 logging level 제한 또는 throttle/sampling 처리를 거치도록 가드해야 함.
   - **디스크 소모**: Pruning limit(`TRACE_RUN_RETENTION_LIMIT = 20`)이 정상 작동하는지 체크 필수.
4. **focused tests**:
   - `tests/test_trace_logger.py` (비동기 trace log 수신 속도 및 부하 테스트)
   - `tests/test_trace_log_bundle_audit.py` (프레임 썸네일 trace 스키마 정합성 유닛 테스트)

defer:
- **실제 video player UI의 layout, labels, menu 변경**: Defer 함.
- **실제 frame thumbnail 디코딩 알고리즘 튜닝**: Defer 함.
- **QML/UI 전환 시도**: 일체 Defer 함.
