DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE trace bundle retention contract scout 20260628

findings:
1. **현재 구현된 coverage**:
   - `core/runtime/trace_logger.py` : trace run 디렉터리 보유 개수를 제한하는 `TRACE_RUN_RETENTION_LIMIT = 20` 상수가 적용되어 있음.
   - `core/runtime/temp_workspace.py` : temp workspace 내 사용하지 않는 오래된 디렉터리를 지워주는 `prune_trace_run_directories` 로직이 탑재됨.
2. **증거/검증이 약한 retention/cleanup/package-only 계약**:
   - **미흡 부분**: 20개의 limit을 초과하여 새로운 trace run이 실행될 때, 가장 오래된 디렉터리 및 index manifest 파일이 물리적으로 디스크에서 완전히 삭제(cleanup)되는지 단언하는 assertions 와, 용량 한도 초과 시 non-destructive package-only 정책(임시 decode wav 즉시 소거 등)의 정상 작동을 확인하는 자동화 진단 수단이 누락됨.
3. **오너 파일 및 함수 (Owner Files/Functions)**:
   - `core/runtime/trace_logger.py` : TraceLogger 클래스
   - `core/runtime/temp_workspace.py` : `prune_trace_run_directories` 및 `workspace_usage`
4. **추가해야 할 가장 좁은 audit/test 후보**:
   - `tests/test_trace_logger_retention.py` [NEW] : trace run 디렉터리를 25회 연속 생성한 직후, 가장 오래된 5개의 trace 디렉터리가 디스크에서 흔적 없이 소거되고 최신 20개만 보존되고 있음을 검증하는 unit test.
   - `tools/audit_trace_logger_retention.py` [NEW] : static 분석 및 loop simulation을 돌려 trace storage capacity retention rule이 block 없이 잘 수행되는지 진단하는 script.
5. **NAS 필요 여부 (NAS HeyDealer validation)**:
   - **불필요 (No)**: 자막 생성 알고리즘이나 음성/텍스트 모델과 무관한 순수 로깅 디스크 공간 cleanup 관리 기능이므로 HeyDealer benchmark validation 이 불필요함.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-091806-trace-bundle-retention-scout.md` 파일 내용 및 index 맵핑 상태 점검.

DEX_REVIEW_CLASSIFICATION:
- verdict: ACCEPTED_WITH_NARROW_EXTENSION
- accepted scout scope: trace retention remains a safe NLE diagnostic slice because it does not touch UI/layout, subtitle generation, STT/STT2, `.aissproj` format, App Store packaging, or per-pixel NLE writes.
- implemented extension: retained-run coverage was kept, and package-directory retention was added so `Diagnostics/Packages/AISSTrace-*` cannot grow without a bounded cleanup policy.
- evidence: `output/manual_verification/latest/trace_package_retention_contract_20260628/trace_log_bundle_audit.md`
- NAS: not required because this is trace/temp-workspace disk-management behavior only.
