DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio docs relocation link-risk scout

findings:
1. **루트 개발문서 이동 시 반드시 갱신해야 할 스크립트 경로**:
   - `tools/jammini_delegate.sh` (라인 137-146) : 협업을 위한 bootstrap check 대상 문서 경로 목록 (`AGENTS.md`, `ACTION_ITEMS.md`, `docs/README.md` 등) 수정 필요.
   - `tools/cooperation_bootstrap.sh` (라인 79) : `AGENTS.md`, `ACTION_ITEMS.md`, `docs/HANDOFF.md`, `README.md` 등을 읽으라는 check 안내 경로 수정 필요.
2. **반드시 갱신해야 할 단위 테스트 및 소유권 맵 파일**:
   - `tests/test_subtitle_generation_domain_map.py` (라인 4-6) : `SUBTITLE_GENERATION_DOMAIN_MAP.md` 및 `LONG_FILE_OWNERSHIP_MAP.md` 가 docs/ 하위로 이동할 경우, `MAP_PATH` 와 `LONG_FILE_MAP_PATH` 변수의 absolute Path resolve 로직을 docs 하위 상대경로로 동기화 갱신해주어야 테스트 실패를 막을 수 있음.
3. **문서 내부 상대 경로 및 마크다운 링크 갱신**:
   - `docs/README.md` 와 `docs/*/README.md` 내에 기재된 `AGENTS.md`, `ACTION_ITEMS.md`, `cooperation.md` 상대 링크들 (`../AGENTS.md` -> `../planning_queue/AGENTS.md` 등) 일제 수정 필요.
4. **치명적인 호환성 리스크 경고 (AGENTS.md 및 ACTION_ITEMS.md)**:
   - **경고**: 에이전트 구동의 핵심 앵커인 `AGENTS.md` 와 `ACTION_ITEMS.md` 를 루트 디렉토리 외부(예: `docs/planning_queue/`)로 옮길 경우, 외부 툴체인 및 watchdog 백그라운드 프로세스가 루트에서 이 두 파일을 찾지 못해 boot block 이 발생하는 치명적인 호환성 리스크가 존재함.
   - **대책**: `AGENTS.md` 와 `ACTION_ITEMS.md` 의 최상위 루트 위치는 **절대 보존(Preserved)**하고, 그 외의 도메인 맵 문서나 개별 릴리즈 노트, 피처 대장 등 보조 개발 문서 위주로만 안전하게 `docs/` 하위로 이동할 것을 추천함.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-211046-docs-relocation-risk-scout.md` 파일 내용 및 index 맵핑 상태 점검.
