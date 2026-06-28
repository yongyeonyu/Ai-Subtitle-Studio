DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE adapter cache consistency owner scout

findings:
1. **`project_io` LRU 캐시 갱신 일관성**: 프로젝트를 새로 열거나 저장할 때, `_PROJECT_FILE_CACHE` LRU 캐시 및 mtime/size 시그니처가 정확히 갱신되거나 무효화(`clear_project_file_cache`)되어 펜딩된 메모리 NLEState가 오염되는 것을 막는지 검증.
2. **Runtime `_nle_project_state` Hydration 고유성**: 레거시 프로젝트 로드 시 `attach_project_nle_state`로 바인딩되는 `NLEProjectState`와 UI 에디터 어댑터 인스턴스가 1:1 싱글 레퍼런스로 완벽히 일치하는지 검증.
3. **Storage Payload Strip 동작**: `project_io.write` 연산 시 `strip_unapproved_nle_persistence_fields`가 unapproved NLE 필드를 완벽히 제거하여 `.aissproj` 파일 구조 하위 호환성을 해치지 않는지 검증.
4. **LRU Cache Limit 메모리 누수 제어**: `_PROJECT_FILE_CACHE_MAX = 4` 경계 내에서 여러 프로젝트를 교차 오픈할 때, 제거 대상 NLEState 참조가 leak 없이 GC에 의해 즉시 해제되는지 체크.
5. **NLE-Legacy Projection Parity 정합성**: NLE 투영 세그먼트와 레거시 세그먼트 간의 개수, 순서, 타임스탬프 drift가 정확히 `0`에 수렴하는지 Parity 검증.
6. **Save-Reload ID Canonicalization**: 저장 후 불러오기를 반복해도 자막 ID(`caption_1` 등)가 canonicalize 규약을 벗어나 비정상 증식하지 않는지 무결성 검사.

defer:
- **NLE 디스크 포맷 영구 저장화 (persisted nle disk fields)**: 오너의 별도 지시 전까지 `.aissproj` 스키마 자체의 영구 변경은 금지하며 read-only strip 정책을 엄격히 고수함.
- **실시간 드래그 단위 NLE 쓰기 (per-pixel drag write)**: 드래그 중인 미세 픽셀 단위로 NLE 상태에 매번 쓰는 것은 timeline Canvas 오버헤드가 크므로 커밋 릴리즈 바운더리에만 일괄 쓰도록 제한하고 이외의 실시간 드래그 쓰기는 Defer 함.
- **UI/QML 전환**: timeline paint passes를 제외한 일체의 UI/UX 라벨, 메뉴 구성, QML/SceneGraph 2D 전환 시도는 Defer 함.
