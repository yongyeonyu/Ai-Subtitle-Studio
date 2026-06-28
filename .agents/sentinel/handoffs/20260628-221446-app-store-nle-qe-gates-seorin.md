DEX_REVIEW_READY
역할: 서린
범위: AI Subtitle Studio owner-approved App Store and NLE QE gates
읽은 파일:
- docs/planning_queue/ACTION_ITEMS.md
- docs/nle_engine/NLE_Action.md
- output/manual_verification/latest/app_store_owner_approval_readiness_20260628_2218/app_store_readiness_audit.md
결론: 대표님 승인에 따른 App Store 릴리스 및 Persisted NLE 통합 QE 게이트(Misleading Green 방지 포함)를 구성했습니다.

### 🍎 1. App Store Release QE Gates (Strict)
*   **코드 서명 및 패키징 검증 (Signing & Package Proof)**:
    - [ ] `codesign --verify --deep --strict --verbose=2 AppName.app` 통과.
    - [ ] `pkgutil --check-signature AppName.pkg` 통과 및 개발자 서명 신뢰성 증적 보존.
*   **샌드박스 런타임 검증 (Sandbox Smoke)**:
    - [ ] 샌드박스 보안 프로필 하에서 미디어 파일 IO, STT 실행, 저장/오픈, SRT 내보내기, 렌더링 자막 출력이 정상 작동하고 권한 예외가 발생하지 않는가?
*   **App Store Connect 유효성 (Validation)**:
    - [ ] Transporter / `upload_app_store_build.sh validate`를 경고 없이 통과하는가?
*   **거짓 양성 방지 (Misleading Green Audit Prevention)**:
    - [ ] 코드 서명 혹은 샌드박스 권한 획득에 실패했을 때, 오디트 도구가 이를 감지하지 못하고 무조건 녹색(Green/Pass) 보고서를 작성하는 오탐 현상이 배제되었는가? (실패 시 명시적으로 Audit Status=BLOCKED 또는 FAIL 판정하는 단위 테스트 수립 필수)

### 💾 2. Persisted NLE Storage & NAS Regression QE Gates
*   **기존 포맷 호환성 (Save/Reopen Compatibility)**:
    - [ ] 저장 파일 스키마에 신규 `nle` 및 `nle_snapshot` 필드가 기록될 때, 구버전 프로젝트 파서가 이를 오류 없이 스킵하고 원본 자막 행을 유지하여 열 수 있는가?
    - [ ] 3회 이상의 연속적인 Save -> Reopen 싸이클 후 자막 내용 및 정확한 프레임 단위 타임라인 정보가 비트 단위로 동일한가?
*   **NAS HeyDealer 180s 회귀 검사 (NAS Regression)**:
    - [ ] `/Volumes/photo/...` NAS real-media HeyDealer 180초 검증을 수행하여, 캐시 히트(Hit) 시 최종 품질 및 시간 편차 MAE 결과가 기존 합격 수치(`quality >= 93.766`, `timing MAE <= 0.5808s`) 대비 1% 미만의 미세 오차 범위 내인지 또는 완전히 일치하는지 검증한다.

### 🎯 3. 자막 무결성 게이트 (Integrity Rules)
- [ ] `invalid_duration_count = 0` (0.3초 미만 자막 차단)
- [ ] `non_monotonic_count = 0` (시간 축 역전 방지)
- [ ] `overlap_count = 0` (겹침 자막 완전 배제)
- [ ] `max_active_segments <= 1` (동시 활성 자막 트랙 개수 1개 이하 보장)
