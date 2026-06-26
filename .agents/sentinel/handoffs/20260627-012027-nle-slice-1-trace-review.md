DEX_REVIEW_READY
역할: 한결 (Senior Developer Reviewer)
범위: NLE Slice 1 trace workspace baseline review
읽은 파일:
- [NLE_Action.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/NLE_Action.md)
- [core/runtime/temp_workspace.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/runtime/temp_workspace.py)
- [core/runtime/trace_logger.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/runtime/trace_logger.py)
- [tools/collect_trace_package.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tools/collect_trace_package.py)
- [tests/test_trace_logger.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_trace_logger.py)

결론:
Slice 1 Trace Workspace Baseline 구현체에 대해 런타임 오너십(Multi-user/Multi-process), 리소스 생명주기(Resource Lifetime), 롤백 안정성(Rollback Safety) 측면의 잠재적 위험 요소를 식별하고 아키텍처적 개선안을 도출했습니다. 특히 다중 사용자 환경에서의 경로 충돌 가능성과 동기식 디스크 쓰기로 인한 UI 락 켄텐션(Lock Contention)이 주요 위협 요소입니다.

findings:
### 1. Temp Workspace - 다중 사용자(Multi-user) 환경 소유권(Ownership) 충돌
* **현황**: `tempfile.gettempdir() / "AISubtitleStudioTemporaryWorkspace"`를 모든 유저가 고정 경로로 공유합니다.
* **위험**: macOS/Linux 다중 사용자 환경에서 다른 사용자가 먼저 해당 디렉토리를 소유자 권한으로 생성했을 경우, 현재 사용자는 `mkdir` Permission Error로 앱 실행이 차단되거나 타 사용자 로그 접근 권한 충돌이 발생합니다.
* **대책**: 임시 경로 명칭에 사용자 식별자(UID 또는 username)를 접미사로 붙여 격리해야 합니다 (예: `AISubtitleStudioTemporaryWorkspace-<uid>`).

### 2. Trace Logger - 동기식 I/O Lock Contention으로 인한 UI 프리징
* **현황**: `log_event`는 `RLock`을 쥔 채 `_append_jsonl`과 `_atomic_write_jsonl` 동기식 디스크 I/O를 수행합니다.
* **위험**: 백그라운드 스레드 혹은 메인 스레드에서 I/O 지연(디스크 고부하, 네트워크 드라이브 등) 발생 시 Lock Contention으로 인해 메인 UI 루프가 블로킹되어 실시간 플레이백이나 편집 동작 중 프리징이 생길 수 있습니다.
* **대책**: 실시간 핫패스(Hotpath)가 아닌 경우, 비동기 큐 스레드나 일괄 기록(buffered flush) 방식으로 I/O 동작을 격리하는 개선이 필요합니다.

### 3. Multi-processing (Spawn/Fork) 환경의 자원 상속 문제 (Fork-safety)
* **현황**: 부모 프로세스에서 `initialize_app_trace`로 전역 싱글톤 `_APP_TRACE_LOGGER`를 주입합니다.
* **위험**: STT 워커 등 멀티프로세스(`multi_process.py`) 구동 시 부모 프로세스의 파일 핸들과 소켓 락 객체가 자식 프로세스로 그대로 복제 상속되어, 자식 워커들이 동일한 로그 파일 포인터에 무질서하게 동시 쓰기를 감행하여 파일이 깨지거나 데드락이 유발될 수 있습니다.
* **대책**: 자식 프로세스 초기화 진입점(worker entrypoint)에서 부모의 글로벌 로거 인스턴스를 무효화(`None`)하고 프로세스 격리용 독립 로거를 시작하도록 방어 코드가 보강되어야 합니다.

### 4. Active Log Copy Concurrency (Race Condition)
* **현황**: `collect_trace_package`가 동작 중인 `events.jsonl`을 `shutil.copy2`로 직접 복사합니다.
* **위험**: 로거가 파일 끝에 쓰기 작업을 수행하는 찰나에 복사(read)가 겹쳐지면 동시성 레이스가 일어나 일부 줄이 유실되거나 손상된 JSON 데이터가 복사될 수 있습니다.
* **대책**: 복사 시점에 임시 덤프 스냅샷을 활용하거나, 파일의 안전한 오프셋까지만 읽도록 보장하는 락 메커니즘이 필요합니다.

defer: 없음
덱스 확인 포인트:
1. `core/runtime/temp_workspace.py` 경로 생성 시 사용자별 격리 접미사(UID) 반영 검토.
2. `core/runtime/trace_logger.py` 디스크 동기 쓰기 락 구간의 비동기 큐 전환 검토.
3. 멀티프로세스 워커 스폰 시 부모 로거 초기화(reset) 로직 확보 여부.
