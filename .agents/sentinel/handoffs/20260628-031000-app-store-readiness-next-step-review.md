DEX_REVIEW_READY
역할: 한결 (architecture & rollback safety)
범위: Mac App Store readiness non-destructive next step
읽은 파일:
- `ACTION_ITEMS.md` ([ACTION_ITEMS.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ACTION_ITEMS.md))
- `docs/APP_STORE_SUBMISSION_READINESS.md` ([docs/APP_STORE_SUBMISSION_READINESS.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/docs/APP_STORE_SUBMISSION_READINESS.md))
- `tools/audit_app_store_readiness.py` ([tools/audit_app_store_readiness.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tools/audit_app_store_readiness.py))
- `tests/test_app_store_readiness_audit.py` ([tests/test_app_store_readiness_audit.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_app_store_readiness_audit.py))
- `packaging/macos/build_app_bundle.sh` ([packaging/macos/build_app_bundle.sh](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/packaging/macos/build_app_bundle.sh))
- `packaging/macos/sign_app_bundle.sh` ([packaging/macos/sign_app_bundle.sh](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/packaging/macos/sign_app_bundle.sh))

결론: Mac App Store 제출 준비를 위해 파괴적 빌드/서명 없이 로컬에서 선제 적용할 수 있는 정적 검증 및 문서 수립 단계와, 실제 빌드/공증 hold 사유를 정의하였습니다.

findings:
1) **대표님 요청에서 추론 가능한 submission target**:
   - `docs/APP_STORE_SUBMISSION_READINESS.md` 기준: **Mac App Store package(샌드박스 활성화된 `.pkg`)** 및 내부 배포용 **Beta DMG**.
   - PyQt6 python source app을 App Sandbox 권한하에서 안전하게 동작하도록 패키징 템플릿(Entitlements, Info.plist) 무결성을 확보하는 것이며, 실제 서명 배포는 제외됩니다.
2) **지금 가능한 문서/검증 조각**:
   - **Info.plist.template 및 Entitlements 정적 무결성 검증**: `tools/audit_app_store_readiness.py`를 수동으로 실행(비동작 변경)하여 `app_store_readiness_audit.md` 갱신.
   - **비코드 제출 메타데이터(Non-code submission items) 텍스트 수립**: `docs/APP_STORE_SUBMISSION_READINESS.md` 파일 내의 Privacy Policy URL, App Privacy Data Type Answers, Support URL, Release Notes 등의 공란에 미리 초안을 보완해두는 작업.
   - **패키징 셸 스크립트 실행 권한 확인 및 template mapping**: Info.plist의 버그성 placeholder가 정상 치환(`__APP_VERSION__`)되는지 확인 및 스크립트 실행 권한 부여(`chmod +x`).
3) **금지할 packaging/signing actions**:
   - `build_app_bundle.sh`, `sign_app_bundle.sh`, `build_app_store_pkg.sh` 를 임의 실행하여 실제 `.app`, `.pkg` 바이너리를 생성하거나 서명 서명(signing) 작업을 시도하는 행위 (서명 키 부재로 인한 빌드 에러 방지).
   - `upload_app_store_build.sh` 또는 Transporter 툴로 App Store Connect에 빌드를 전송하는 행위.
   - `notarize_app_bundle.sh` 또는 `notarize_dmg.sh` 를 통해 외부 공증 서버로 업로드 요청을 날리는 행위.
   - `build_beta_dmg.sh` 또는 `create_dmg.sh` 로 `.dmg` 설치 이미지를 빌드하는 것.
4) **accept/hold verdict**:
   - **VERDICT: HOLD**
   - 사유: 실제 패키징 및 서명, 배포 검증은 Apple Developer Program 등록 계정 정보와 머신에 구성된 `Apple Distribution` 서명 인증서(`CODESIGN_IDENTITY`, `INSTALLER_IDENTITY`)에 강하게 종속됩니다. 현재 local environment에는 서명 프로필이 부재하여(`codesign_identity_configured=false`) 빌드가 정상 완료될 수 없으므로, 로컬 정적 검증 및 App Store Connect 제출 메타데이터 정보 문서화 단계에만 국한해야 합니다.

defer: (none)
덱스 확인 포인트:
- 실제 빌드와 서명, 공증, 업로드는 non-destructive 범위를 넘어서고 인증서 부재 리스크가 크므로, 덱스가 packaging/signing 명령을 명시 승인 없이 수행하지 않도록 hold 판정을 지지하는지 확인.
