DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio cut-boundary trace gap scout

findings:
1. **NLE Cut-Boundary Trace Gap 스카우트 검토**:
   - **현재 상태**: 자막 생성 파이프라인에서 cut confirmed, snap, split, drop 처리가 일어날 때 그 세부 결정 근거(drop_reason 등)를 trace logger에 기록하는 로깅 코드가 누락(gap) 상태임.
   - **안전성 판정**: **안전함 (Accept 권장)**. FFmpeg 씬 디텍션이나 스냅 알고리즘 본체를 손대지 않고, 의사결정 분기점에 비동기 trace log 발송 코드만 장착(instrumentation)하는 비파괴 진단 보강이기 때문임.
2. **추천 다음 슬라이스**:
   - **추천 항목**: **"Cut-Boundary Transition Decisions Trace Logger Instrumentation" (컷 경계 결정 진단용 Trace Logger 장착)**
3. **Event Field Shortlist**:
   - `event_type`: `"cut_boundary_decision"`
   - `subtitle_id`: 자막 ID (string)
   - `decision`: `"snap"`, `"split"`, `"drop"`
   - `provisional_frame`: 대상 confirmed 컷 프레임 번호 (int)
   - `drop_reason`: 드롭 사유 (예: `"distance_exceeds_tolerance"`, `"no_visual_cut_found"`)
   - `original_time`: 보정 전 시작/종료 초 (float)
   - `snapped_time`: 보정 후 초 (float)
4. **위험 및 검증 포인트**:
   - **메모리/I/O 부하 방어**: VAD와 마찬가지로 대용량 media 처리 시 수백 개의 boundary snap 결정이 순간 폭발할 수 있으므로, TraceLogger 비동기 큐를 통해 UI thread와 오디오 프로세싱 스레드를 차단하지 않고 non-blocking으로 기록해야 함.
5. **focused tests**:
   - `tests/test_subtitle_boundary_alignment.py` (snap/split/drop 발생 시 trace logger에 해당 event_type이 올바른 schema로 수신되는지 mocking 검증)
   - `tests/test_trace_log_bundle_audit.py` (cut decision 로그 덤프 결과 manifest 무결성 테스트)

defer:
- **실제 cut-boundary snap/split/drop 거리 임계값(tolerance)의 수치 튜닝**: 자막 품질 drift를 유발하므로 Defer 함.
- **FFmpeg scene change detection threshold 값 변경**: Defer 함.
- **QML/UI 전환 시도**: 일체 Defer 함.
