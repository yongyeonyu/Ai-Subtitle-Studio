DEX_REVIEW_READY
역할: 한결 (senior developer reviewer)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio 04.01.00 release architecture review

findings:
1. **State Ownership & Version Bump**:
   - `config.py` 및 `project_format.py` 의 `04.01.00` 버전 bump 가 일관성 있게 정렬됨을 단언함.
   - NLE state 가 디스크 저장(write) 시점에 철저히 strip 되는 `nle_persistence_guard` 격리 아키텍처가 구조적으로 유지되고 있음.
2. **App Store/DMG 경계 및 persisted NLE 과장 경고**:
   - **아키텍처 경고**: 디스크 저장 구조 및 네이티브 빌드가 여전히 차단(blocked) 상태이므로, 릴리즈 청구에서 "App Store 배포 완성" 이나 "NLE 디스크 구조 영구 저장 완료"와 같이 모바일/네이티브 경계를 침범하는 모호성/과장 서술을 차단하고 "App Store readiness local prep" 상태로 제한 명기할 것을 권고.
3. **Rollback Safety**:
   - 새롭게 탑재된 collision guard 및 isolation 기능이 오작동하더라도, legacy editor default logic 및 warning bypass 로 안전하게 fallback 이 기능하여 롤백 안정성이 높게 검증됨.
4. **최종 판정**: **Accept** (v04.01.00 릴리즈 진행 동의).

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-120244-release-architecture-review-hangyeol.md` 파일 내용 및 index 맵핑 상태 점검.
