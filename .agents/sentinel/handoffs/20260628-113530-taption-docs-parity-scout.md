DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio Taption docs parity scout

findings:
1. **AI Subtitle Studio 에 클린룸으로 반영할 개발문서 정리 규칙 5개**:
   - **폴더 기반의 역할 격리**: 모든 개발 문서는 용도별(기획, 검증, 설계 등) 전용 하위 폴더에만 배치하며, `docs/` 루트에는 `README.md` 내비게이션 파일 1개만 유지한다.
   - **레거시 문서의 명확한 격리**: 낡거나 유효하지 않은 기획/설계 문서는 `docs/archive_legacy/` 폴더로 즉시 이동시켜 최신 작업 시 혼선을 완벽하게 격리 차단한다.
   - **검증 증거의 구조화 보존**: 수동/자동 검증 결과 파일(evidence)은 `quality_validation/` 또는 `validation_evidence/` 폴더에 타임스탬프와 함께 보관하여 단일 파일 덮어쓰기 유실을 방지한다.
   - **네비게이션 앵커 유지**: 모든 하위 개발 문서의 상단에는 `docs/README.md` 에 기재된 폴더 맵 및 스타트업 가이드 앵커 링크 구조와 1:1 일치하는 상대 경로 이동 메뉴를 기재한다.
   - **임시 개발 작업실 분리**: 미커밋 스크립트, 로컬 테스트 덤프 등은 `.gitignore` 에 등록된 임시 디렉토리(예: `.codex_work/` 또는 artifacts) 내에서만 생성하여 레포지토리 클린 상태를 수호한다.
2. **AGENTS.md 에 추가할 규칙 5개**:
   - **단일 부트스트랩 파일 정책**: `AGENTS.md` 는 새 채팅 세션 시작 시 파일 하나만으로도 즉시 에이전트를 구동하고 이전 히스토리를 파악할 수 있는 유일한 부트스트랩 문서로 유지한다.
   - **물리 파일 Handoff 우선 합의**: 에이전트 간 handoff 정합성 판단은 채팅방의 ACK/WORKING 메시지가 아닌, `.agents/sentinel/handoffs/` 폴더의 물리 파일 생성을 신뢰의 단일 원천으로 규정한다.
   - **비파괴 검증 우선 원칙**: 런타임 수정을 포함하는 모든 에이전트 태스크는 source-app 비파괴 검증 및 단위 테스트 패스를 필수 관문으로 지정하며, DMG 빌드 및 패키징 등은 명시 승인 없이는 제한한다.
   - **UI/UX 임의 변경 제약**: 오너(대표님)가 명시적으로 지시한 상세 레이아웃, 단축키, 라벨, 색상 이외의 UI/UX 디자인 요소는 에이전트가 임의로 수정하거나 제안하지 않는다.
   - **에이전트 역할 간 경계 보호**: 덱스(Dex)는 최종 패치 적용 및 사용자 보고를 총괄하고, 잼민이(Jammini)는 좁고 검토 가능한 단위의 support/review/draft 태스크만 비파괴적으로 수행하여 dirty worktree를 보호한다.
3. **호환성 리스크 경고 (ACTION_ITEMS.md 이동 관련)**:
   - **경고**: root 디렉토리의 `ACTION_ITEMS.md` 를 `docs/planning_queue/ACTION_ITEMS.md` 등 하위 폴더로 강제 이동시키는 제안은, 기존 덱스/잼민이의 자동화 통신 스크립트 및 런타임 watchdog 파일 파서가 참조하는 절대/상대 경로를 깨뜨려 watchdog route match 실패 및 boot block 크래시를 유발할 **치명적인 호환성 리스크**가 있습니다. 따라서 root `ACTION_ITEMS.md` 의 물리적 이동은 절대 금지하고 현 위치를 엄격히 보존해야 합니다.

defer:
- **실제 UI/UX 디자인 변경, 뷰어 개조, QML/GPU UI 도입**: Defer 함.
- **실제 .aissproj 파일의 디스크 저장 스키마 변경 (persisted NLE fields)**: Defer 함.
- **per-pixel NLE writes 실시간 디스크/DB 동기화**: Defer 함.
- **STT policy/default cache promotion**: Defer 함.
- **App Store packaging, DMG 빌드**: Defer 함.

덱스 확인 포인트:
- `.agents/sentinel/handoffs/20260628-113530-taption-docs-parity-scout.md` 파일 내용 및 index 맵핑 상태 점검.
