DEX_REVIEW_READY
역할: 서린 (strict QE reviewer)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio 04.01.00 release QA review

findings:
1. **검증 충분성 판정 (Validation Surface Sufficiency)**:
   - `v04.01.00` 소스 앱 릴리즈 클레임 대비 검증 범위는 **충분(Sufficient)**함. `test_result.md` 에 기록된 2026-06-28 KST 기준 이력 및 PyTest 통과 이력(`test_project_nle_dual_write.py`, `test_timeline_hit_targets.py`), 180초 HeyDealer NAS dynamic pipeline verification (`accepted=true`, overlap `0`) 등의 물리 증적 데이터를 통해 무결성이 확실히 입증됨.
2. **부문별 QA 상태 진단**:
   - **Quick QA**: 스모크 테스트 및 python py_compile 정적 분석 통과 완료.
   - **NLE PyTest**: 42개의 dual-write 및 11개의 projection tests 정상 패스 완료.
   - **App Store Readiness Audit**: `config.py` 의 OS_NAME, APP_STORE_TARGET 플래그 및 외부 relink/isolation 패스 검증 완료.
   - **Version Assert**: `config.py` 및 `project_format.py` 의 04.01.00 버전 스트링 동기화 및 `tests/test_trace_logger.py` 의 schema version 검증 패밀리 통과 완료.
   - **Trace Manifest**: `trace_logger.py` 의 manifest schema v1 index 정합성 검증 확인 완료.
3. **App Store 제출 완료 과장 경고 (Strict QE Warnings)**:
   - **지적**: 릴리즈 노트나 `docs/APP_STORE_SUBMISSION_READINESS.md` 에 "App Store 제출 완료", "Sandbox 심사 통과" 등의 완성형/오해 유발 문구가 기술될 경우 엄격히 배제할 것. 현재 소스 앱은 Python/PyQt6 기반으로 App Store Submission을 대비한 코드/설정 준비 단계(Preparation State)일 뿐이며 실제 바이너리 제출이나 패키징이 끝난 상태가 아니므로 과장 서술을 철저히 막아야 함.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-120230-release-qa-review-seorin.md` 파일 내용 및 index 맵핑 상태 점검.
