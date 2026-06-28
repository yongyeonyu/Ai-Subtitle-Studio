DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio 04.01.00 release review scout

findings:
1. **04.00.18에서 04.01.00으로 bump 시 반드시 같이 바뀌어야 할 파일**:
   - `core/runtime/config.py` : `APP_VERSION = "04.00.18"` -> `APP_VERSION = "04.01.00"` 및 첫 줄 주석 `# Version: 04.00.18` -> `# Version: 04.01.00`
   - `core/project/project_format.py` : `PROJECT_SCHEMA_VERSION = "04.00.18"` -> `PROJECT_SCHEMA_VERSION = "04.01.00"`
   - `AGENTS.md` : `V4_0_18` -> `V4_1_00` 및 버전 기술 부분 일제 업데이트
   - `README.md` : 현재 명기된 버전 표기 업데이트
   - `tests/test_trace_logger.py` : trace json schema 버전 검증 및 trace header version `04.00.18` 비교 string 수정.
2. **App Store/DMG/packaging 과장 위험 문구 경고**:
   - **경고**: `docs/APP_STORE_SUBMISSION_READINESS.md` 또는 packaging 스펙에 "Apple Silicon / macOS Native App Store Deploy Ready" 혹은 "DMG Native Signing Completed" 같은 표현이 있을 경우, 본 프로젝트는 여전히 Python/PyQt6 기반의 read-only NLE 소스 앱 상태이며 persisted NLE disk-format 및 native migration은 의도적으로 차단 및 보류(blocked)하고 있으므로, "App Store Native Distribution" 이나 "macOS Native Sandbox Complete"와 같은 과장/오해의 소지가 있는 문구는 릴리즈 및 배포 패키지 설명에서 완전히 제외해야 함.
3. **태그/릴리즈 검증에 필요한 최소 test shortlist (Minimum Test Shortlist)**:
   - **NLE Timeline/Playhead Fit**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest tests/test_timeline_playhead_fit.py`
   - **NLE State & Dual-Write Parity**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest tests/test_project_nle_snapshot.py tests/test_project_nle_dual_write.py tests/test_project_nle_operations.py`
   - **Persistence Quarantine & Export Parity**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest tests/test_project_nle_persistence_guard.py tests/test_project_nle_render_export_parity.py`
   - **Quick Smoke Runner**: `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick`

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-115644-release-readiness-scout.md` 파일 내용 및 index 맵핑 상태 점검.
