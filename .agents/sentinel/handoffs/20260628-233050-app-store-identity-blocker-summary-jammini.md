DEX_REVIEW_READY
역할: 잼민이
범위: AI Subtitle Studio App Store identity blocker summary
읽은 파일:
- docs/APP_STORE_SUBMISSION_READINESS.md
- output/manual_verification/latest/app_store_owner_approval_identity_check_20260629_0026/app_store_readiness_audit.md
결론: Mac App Store 제출을 가로막고 있는 13가지 블로커(Blocker) 리스트 조사를 완료했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🚫 Mac App Store 출시 블로커 요약 (13 Blocker Summary)

현재 App Store 배포는 총 **13가지 Blocker**로 인해 제출 불가(Status=blocked) 상태입니다.

1. **서명 인증서 키체인 누락 (Signing Identities Missing)**
   - Apple Distribution 코드서명 인증서 미지정 (`apple_distribution_codesign_identity_not_configured`)
   - 3rd Party Mac Developer Installer 설치 프로그램 인증서 미지정 (`installer_identity_not_configured`)
2. **릴리스 패키징 및 스모크 검증 누락 (Artifacts & Verification Missing)**
   - 배포용 `.pkg` 패키지 파일 누락 (`signed_app_store_pkg_missing`)
   - 샌드박스(Sandbox) 환경하의 정상 작동 스모크 테스트 증적 누락 (`sandbox_smoke_missing`)
   - App Store Connect / Transporter의 API 유효성 검증 누락 (`app_store_connect_validation_missing`)
3. **오너 입력 메타데이터 미정 (8/8 Owner Metadata Pending)**
   - 개인정보 처리방침 URL (`privacy_policy_url`)
   - 개인정보 수집 데이터 유형 답변 (analytics, diagnostics 수집 여부 등) (`privacy_data_type_answers`)
   - 암호화 및 수출 규정 적합성 답변 (`export_compliance_answers`)
   - App Store 제출용 실제 UI 스크린샷 캡쳐 파일 (`mac_app_store_screenshots`)
   - 고객 지원 URL (`support_url`)
   - 심사용 자막 생성/샌드박스 설명 등의 리뷰 메모 (`app_review_notes`)
   - 연령 등급 심사지 답변 (`age_rating_answers`)
   - 해당 버전에 대한 릴리스 노트 사본 (`release_notes`)
