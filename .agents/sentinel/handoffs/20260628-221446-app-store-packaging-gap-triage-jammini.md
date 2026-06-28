DEX_REVIEW_READY
역할: 잼민이
범위: AI Subtitle Studio owner-approved App Store packaging gap triage
읽은 파일:
- docs/planning_queue/ACTION_ITEMS.md
- docs/APP_STORE_SUBMISSION_READINESS.md
- output/manual_verification/latest/app_store_owner_approval_readiness_20260628_2218/app_store_readiness_audit.md
- packaging/macos/README.md
결론: 대표님 승인 하의 App Store 패키징 갭 트리아지 체크리스트 구성을 완료했습니다.

### 📋 App Store Launch Gap Triage Checklist

1. **지금 즉시 실행 가능한 작업 (Immediately Actionable by Dex)**
   - [x] **로컬 빌드 스크립트 실행 준비**: `packaging/macos/build_app_bundle.sh`를 활용한 임시 로컬 `.app` 샌드박스 번들 구성 및 사전 빌드 테스트.
   - [x] **권한 명세 파일 검토**: `packaging/macos/AI Subtitle Studio.entitlements` 내부의 샌드박스 마이크, 파일 열기/저장 보안 범위 적절성 분석.
   - [x] **로컬 서명 유효성 더미 테스트**: 자체 로컬/임시 서명 환경에서 codesign과 sandbox가 깨지지 않는지 사전 드라이런(dry-run) 점검.

2. **인증서/메타데이터로 인해 막히는 작업 (Blocked - Requiring External Assets/Credentials)**
   - [ ] **Apple Distribution 인증서 세팅**: Apple Developer 포털에서 발급한 정식 Apple Distribution 및 3rd Party Mac Developer Installer 서명 인증서 키체인 등록 대기.
   - [ ] **오너 메타데이터 패키지**: App Store Connect 등록용 이름, 부제목, 카테고리, 프라이버시 정책 URL, 지원 및 마케팅 URL, 앱 설명 사본 취합 필요.
   - [ ] **Connect 앱 레코드 생성**: Apple Developer Team bundle ID 매핑 및 App Store Connect 상에 SKU 및 앱 레코드(App Record) 수립 대기.

3. **위험한 업로드 조건 및 주의사항 (High-Risk Upload Conditions)**
   - [ ] **Notarization & Sandbox 충돌**: Transporter 업로드 전 반드시 로컬 샌드박스 상에서 저장/열기 동작이 실제로 실패하는지 확인(샌드박스 권한 위반 시 즉시 반려되므로 사전 샌드박스 쉘 테스트 완료 필수).
   - [ ] **메타데이터 속도 광고 금지**: 앱 소개 메타데이터 내에 실시간 STT 품질 외에 '네이티브 마이그레이션 적용으로 인한 비약적 속도 가속' 등 미검증 성능 과장 광고 표기를 배제할 것.
   - [ ] **Transporter 실 업로드 제한**: `upload_app_store_build.sh upload` 실행은 반드시 모든 서명 및 샌드박스 QE 패스가 확정된 후, 대표님의 최종 재확인 오더가 떨어진 시점에만 활성화해야 함.
