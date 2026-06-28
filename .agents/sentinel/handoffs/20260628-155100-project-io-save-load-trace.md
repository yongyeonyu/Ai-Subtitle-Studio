DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio project IO trace NLE save-load scout 20260628

findings:
1. **Raw Path 유출 방지 설계**:
   - **보안**: trace event 로깅 시 절대 경로(`filepath`)를 직접 포함하지 않고, `_short_hash(filepath)` 또는 `Path(filepath).name` (basename)만을 로깅하여 로컬 파일 경로 유출을 완벽하게 방어함.
2. **Project IO Open/Save Trace Fields**:
   - `event_type`: `"project_io_read"`, `"project_io_write"`
   - `project_id`: `_short_hash(filepath)` (익명화된 project key)
   - `codec`: `"msgpack"` / `"json"`
   - `compression`: `"zlib"` / `"none"`
   - `nle_state_present`: bool (hydration 및 strip 상태 검증용)
   - `elapsed_ms`: read/write 처리 경과 시간 (float)
3. **NLE Hydration / Storage Clean 검증 지표**:
   - `nle_hydration_success`: bool (`attach_project_nle_state` 연동 성공 여부)
   - `nle_stripped_fields`: int (저장 시 strip된 runtime keys 및 persistent field 개수)
4. **추천 다음 슬라이스**:
   - **추천 항목**: **"Project IO Serialization Trace Instrumentation" (프로젝트 IO 직렬화 이력 진단용 Trace Logger 장착)**
5. **compatibility & test gaps**:
   - 현재 `tests/test_project_nle_snapshot.py` 와 `tests/test_trace_logger.py` 에 project read/write 시 trace log event 수신 여부 및 mock file save roundtrip 시의 strip/hydration sequence 검증 assert가 부재(gap)함.

defer:
- **실제 .aissproj 파일 포맷의 스키마 구조 변경**: Defer 함.
- **실제 디렉토리 structure 변경, UI/QML 개조**: Defer 함.
- **WhisperKit 모델 및 STT 백엔드 변경**: Defer 함.
- **App Store 메타데이터 빌드 및 deployment**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-155100-project-io-save-load-trace.md` 파일 내용 및 index 맵핑 상태 점검.
