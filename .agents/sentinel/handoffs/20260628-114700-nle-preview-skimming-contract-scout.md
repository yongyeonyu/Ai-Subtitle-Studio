DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE preview/skimming contract scout

findings:
1. **NLE 차기 안전 Preview/Skimming 슬라이스 추천**:
   - **추천 항목**: **"Video Player Skimming Non-Blocking Async Frame Cache Preflight Tooling" (스키밍 비차단 비동기 프레임 캐시 일관성 진단 도구)**
2. **선정 사유 및 안전성**:
   - **안전성**: 3D view, OpenGL/Metal UI surface, layout, labels 변경이 일체 없는 비파괴 프레임 캐시 비동기 flow 무결성 진단 도구 및 tests이므로 오너 승인 없이 매우 안전하게 수행 가능.
3. **핵심 확인 항목 및 무결성 검증 요건**:
   - **Temp Preview Workspace 사용**: `preview_frame_cache_dir`가 `/tmp/AISubtitleStudioTemporaryWorkspace/Diagnostics/Trace` 등 임시 격리 디렉토리를 안전하게 바라보고 있는지 확인.
   - **Nearest-Frame Grid**: `sec_to_nearest_frame`을 통해 fps(60000/1001 등) 기준 그리드 단위로 정렬되어 근접 오프셋(tolerance) 썸네일을 찾는지 검증.
   - **UI thread block 방어**: 캐시 miss 시 UI 메인 스레드 내에서 동기 `ensure_preview_frame`이 찔려 stuttering을 유발하지 않도록, `nearest_cached_preview_frame`이 캐시 미스 시 즉시 빈 경로를 리턴하고 백그라운드 비동기 디코더를 구동하는 비차단 위임 flow 검사.
   - **캐시 격리**: visual cut-boundary 프레임 썸네일 경로와 video player preview/skimming용 캐시 경로가 격리된 하위 폴더 구조를 지니는지 검증.
4. **focused tests**:
   - `tests/test_preview_frame_cache.py` (비동기 miss 리턴 속도 및 nearest frame grid 검증)
   - `tests/test_video_player_widget.py` (UI 스레드 block-free 상태 검증)
5. **결론**: 비차단 비동기 프레임 캐싱 무결성 진단 도구 도입을 **수용(Accept)** 권장.

defer:
- **실제 3D rendering view, OpenGL/Metal-backed timeline canvas UI surface 도입**: 렌더링 엔진 전면 변경 리스크가 크므로 Defer 함.
- **video player widget 의 layout/UX/메뉴/라벨 변경**: Defer 함.
