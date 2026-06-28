DEX_REVIEW_READY
역할: 유진 (editor workflow reviewer)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio 04.01.00 release workflow review

findings:
1. **UI/UX 변경 및 App Store 제출 완료 오해 검증**:
   - 릴리즈 노트(`RELEASE_v04.00.18.md` 및 차기 `RELEASE_v04.01.00.md` 초안) 및 `README.md` 가 사용자에게 불필요한 UI 개조(단축키, 레이아웃 변경 등)를 암시하지 않으며, Local Source-app 런타임 보완 단계임에도 "App Store 제출 완료"와 같은 배포 오해를 주지 않도록 용어의 중립성을 유지하고 있음.
2. **Taption-derived NLE 자막 편집 워크플로우 Parity 점검**:
   - NLE neighbor collision guard, voice-silence drag magnet parity 와 같은 핵심 자막 편집 런타임 규약이, 실제 단위 테스트 결과 및 180s HeyDealer NAS pipeline test (`accepted=true`) 데이터와 과장 없이 100% 정합성을 형성하고 있음을 검증함.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-120241-release-workflow-review-yujin.md` 파일 내용 및 index 맵핑 상태 점검.
