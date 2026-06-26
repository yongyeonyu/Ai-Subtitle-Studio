DEX_REVIEW_READY
역할: 잼민이
범위: NLE_Action.md draft/risk review
읽은 파일:
- NLE_Action.md
- docs/ARCHITECTURE.md
- docs/HANDOFF.md
- docs/FEATURE_REGISTRY.md
결론: NLE_Action.md 계획서에 근거하여 NLE mutable-owner 갭, 59.94fps 기반 프레임 2766/2677 컷 검증 위험, trace-log 임시 워크스페이스 위험 및 검증 명령 shortlist를 분석 완료했습니다.
findings:
1. **NLE Mutable-Owner Compatibility Gaps**:
   - **timing state 중복 위험**: `editor_state` 및 legacy timeline이 기존 타이밍 정보의 실시간 source of truth인 상태에서, NLEProjectState를 별도의 mutable owner로 동시 사용하면 두 객체 간 타이밍 싱크가 어긋나는 동기화 지연 및 timing state duplicate 버그 위험이 있습니다.
   - **legacy .aissproj 호환성 유실**: 저장(Save) 시 NLE 프로젝트 상태에서 레거시 저장 포맷으로 역직렬화(reverse-write)할 때, frame-quantized 데이터나 custom metadata 필드가 소실되어 타 기기에서 재개(reopen) 시 프로젝트가 깨질 수 있습니다.
2. **Cut-boundary Fixture Frame 2766/2677 Validation Risks**:
   - **59.94fps 드롭프레임 변환 오차**: 타겟 프레임인 2766(approx 46.1461s)과 2677(approx 44.6613s)은 NTSC 규격인 60000/1001 fps 기반입니다. 정수 60으로 계산하거나 드롭프레임 보정 공식을 잘못 타면 시간-프레임 매핑 시 1프레임 미세 편차가 발생해 컷 경계가 어긋나거나 magnets 스냅 시 segment 시작점이 뒤흔들릴 수 있습니다.
   - **컷 엣지 스냅 충돌**: 프레임 2766/2677에서 하드 컷이 강제 발생할 때, 해당 컷 근처에 겹친 자막의 시작점을 강제 분리(split) 및 스냅하게 되는데, 만약 자막이 컷 경계 바로 1프레임 직전에 위치해 있다면 스냅 시 자막의 최소 유지 시간(`sub_min_duration`) 요건을 침범하여 자막이 축소 유실될 위험이 있습니다.
3. **Trace-log Temp Workspace Risks**:
   - **디스크 용량 폭증 및 파일 잠금**: 시스템 temp 디렉토리에 실시간 성능/UI 트레이스 로그 및 오디오 윈도우 조각을 저장할 때, 프로세스 종료 시 자동 정리(garbage collection) 로직이 실패하면 macOS wired memory 및 디스크 공간 임시 파일이 무한 누적될 수 있습니다.
   - **멀티 프로세스 접근 충돌**: 임시 파일 쓰기 시 임의의 캐시 키나 충돌 방지 난수 획득이 안 되면, 동시 실행 중인 타 프로세스(STT worker, FFmpeg 등)와 디렉토리 접근 경합 및 쓰기 락(write lock) 크래시가 발생할 수 있습니다.
4. **Validation Command Shortlist**:
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py` (NLE 베이스라인 정상 작동 확인)
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py` (컷 경계 정합 및 hard-cut 스냅 검사)
   - `./venv/bin/python tools/qa_suite_runner.py quick` (전체 소스앱 빠른 검증)
   - `git diff --check -- .` (공백 및 포맷 오염 사전 확인)
defer: 없음
덱스 확인 포인트: 본 분석 자료는 덱스(Codex) 측에서 NLE_Action.md 실행 계획의 1단계 mutable NLE 이식 및 2단계 59.94fps 프레임 단위 정합 보정 시, 호환성 깨짐 및 미세 프레임 편차를 선제적으로 방어하기 위해 참조될 수 있습니다.
