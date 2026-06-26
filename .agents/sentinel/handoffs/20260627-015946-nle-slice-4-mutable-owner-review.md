DEX_REVIEW_READY
역할: 한결 (Senior Developer Reviewer)
범위: NLE Slice 4 mutable owner pilot architecture review
읽은 파일:
- [NLE_Action.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/NLE_Action.md)
- [core/project/nle_snapshot.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/nle_snapshot.py)
- [core/project/project_io.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/project_io.py)
- [core/project/project_manager.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/project_manager.py)
- [core/project/project_context.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/project_context.py)
- [tests/test_project_nle_snapshot.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_snapshot.py)

결론:
Slice 4 Mutable Owner Pilot을 위한 클래스 추가 및 런타임 연동에 대해 **타이밍 상태의 중복 위험, 디스크 파일 저장 시 역호환성 오염 리스크, 단독 SRT 오픈 시 격리 파괴**의 3대 아키텍처적 위험 요소를 규명하고, 이를 방어하기 위한 4가지 Focused Test List를 수립하였습니다.

findings:
### 1. NLE vs Editor State 간 타이밍 싱크 오프셋 (Timing Drift)
* **위험**: 현재 편집기 모델은 `editor_state` 하위의 `segments`와 `timeline.tracks`에 타이밍 정보가 이중 수록되어 동작합니다. 파일럿 단계에서 `NLEProjectState`를 메모리 상의 primary owner로 선언할 때, 마그넷 자석 스냅이나 E2E 편집 조작 후 NLE state와 editor state 간의 갱신 시점 차이(float precision rounding 오차 포함)로 인해 자막 타이밍이 미세하게 어긋나는 drift 리스크가 있습니다.
* **대책**: 파일럿 단계에서는 NLEProjectState에 직접 쓰기 전에, 동시 갱신 후 정밀도를 대조하는 "Dual-Write & Assert" 런타임 유효성 검증 레이어를 임시 탑재해야 합니다.

### 2. `.aissproj` 디스크 지속성 오염 및 역호환성 파괴 (Leak to Disk)
* **위험**: `project_manager.py`의 `save_project`는 최하단에서 `_write_json`을 통해 디스크에 최종 프로젝트 데이터를 직렬화합니다. 만약 런타임 주입 대상인 `_nle_project_state`, `nle`, `nle_snapshot` 필드가 `project_io.py`의 `_PROJECT_RUNTIME_KEYS`에 등록되어 누락(strip)되도록 보장받지 못한다면, 디스크의 `.aissproj` 내부로 유입 저장됩니다. 이는 파일럿이 탑재되지 않은 이전 버전(04.00.17 이하)의 앱에서 프로젝트를 열 때 스키마 에러나 크래시를 야기하여 역호환성이 영구히 파괴됩니다.
* **대책**: `project_io.py`의 `_PROJECT_RUNTIME_KEYS`에 해당 NLE 런타임 키들을 선제 하드코딩하고, `_sanitize_project_workspace_fields`에도 제거(strip) 필터 방어막을 추가해야 합니다.

### 3. 단독 SRT 오픈(Direct SRT Open) 워크플로우 예외 격리 유실
* **위험**: 세션이 없는 단독 SRT 로드 시에도 `NLEProjectState` 수명 주기가 결합하여 무조건 hydration을 강제하게 되면, 미디어나 사이드카 EDL이 결여되었을 때 생성 예외(Exception)로 인해 자막 단독 오픈 기능 자체가 마비되는 위험이 존재합니다.
* **대책**: 단독 SRT 상태인 경우 NLEProjectState를 빈 객체로 안전하게 우회(Bypass)시키는 격리 설계를 구축해야 합니다.

### 4. Roughcut EDL / Render Plan Parity 유실
* **위험**: EDL exact join 마커가 NLE sequence markers에 기인하므로, 투영(projection) 시 오차가 발생하면 roughcut 내보내기 시 영상 컷 접합면 싱크가 엇나갑니다.

---

### Focused Test List (필요 테스트 후보 목록)
1. **NLE State Hydration & Leak Guard Test**:
   * legacy `.aissproj` 로드 시 `NLEProjectState`가 메모리 상에 정상 생성(`hydrate`)되는지 테스트.
   * `save_project` 완료 후 디스크에 실제 쓰여진 파일 payload 내부를 직접 파싱하여 `nle`, `nle_snapshot`, `_nle_project_state` 키가 단 하나도 누출되지 않았음을 단언(`assertNotIn`)하는 라운드트립 검증 테스트.
2. **Direct SRT Open Bypass Test**:
   * 미디어/사이드카가 아예 없는 상황에서 단독 SRT 파일을 열 때 NLE 레이어가 무해하게 예외 처리 및 격리(Bypass)되는지 확인하는 격리 유닛 테스트.
3. **Dual-Write Consistency Test**:
   * 임의의 자막 편집(`segments`)을 save_project에 주입했을 때 NLEProjectState에 동기화되는 과정에서 타이밍 drift 오차가 `0.0`초로 유지됨을 보증하는 일관성 테스트.
4. **Roughcut Marker Parity Test**:
   * roughcut_state를 지닌 세션에서 NLEProjectState를 투영했을 때, EDL exact join 마커의 개수와 구조가 기존 legacy EDL sidecar와 완벽하게 1대1 일치하는지 판별하는 테스트.

defer: 없음
덱스 확인 포인트:
1. `core/project/project_io.py` 내 `_PROJECT_RUNTIME_KEYS` 필터링 목록에 NLE 파일럿 필드를 선제 등록하는 시점 확보.
2. NLEProjectState의 런타임 생명주기를 `attach_project_session`에 제한하여 단독 SRT 동작 시 바이패스 안전성 확인.
