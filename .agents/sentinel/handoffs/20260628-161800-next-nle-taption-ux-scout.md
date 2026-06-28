DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next NLE/Taption UX safe slice scout 20260628

findings:
1. **차기 NLE/Taption UX 비파괴 슬라이스 추천**:
   - **추천 항목**: **"NLE Preview/Skimming Cache Miss UI Thread Block Prevention Tooling" (비디오 플레이어 스키밍 시 UI 스레드 비차단 무결성 검증 도구 및 테스트 보강)**
2. **선정 사유 및 안전성**:
   - **안전성**: UI/UX layout, buttons, labels, colors 변경이 일체 없는 비파괴 썸네일 캐시 miss 시의 비동기 block-free 동작 진단 도구 및 tests이므로 오너 승인 없이 매우 안전함.
3. **owner-map-backed source**:
   - `core/runtime/preview_frame_cache.py` (비동기 miss 처리 및 nearest frame grid 연동)
   - `ui/editor/ux/editor_timeline_video.py` : playhead fit 및 skimming 시 main UI thread block-free callback 루틴.
4. **필요한 테스트 (Tests)**:
   - `tests/test_video_player_widget.py` : skimming 시 cache miss 시점에 UI thread가 동기 디코드에 걸려 block되는지 여부를 `time.monotonic()` 격차를 통해 0.1ms 수준으로 검사하는 유닛 테스트 보강.
5. **문서 업데이트 위치**:
   - `docs/VALIDATION.md` 및 `NLE_Action.md` 에 preview cache miss 진단 가이드 추가.
6. **위험 및 Rollback 계획**:
   - **위험**: 비동기 워커가 쓰레드를 점유해 CPU core 부하를 줄 위험.
   - **Rollback**: `tools/audit_nle_preview_skimming_cache.py`를 실행하여 peak memory/CPU 점유율이 criteria를 통과하지 못하면 해당 preview caching logic만을 disabled 상태(`stt_primary_collect_cache_enabled=false`와 마찬가지로 default false)로 즉시 롤백.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-161800-next-nle-taption-ux-scout.md` 파일 내용 및 index 맵핑 상태 점검.
