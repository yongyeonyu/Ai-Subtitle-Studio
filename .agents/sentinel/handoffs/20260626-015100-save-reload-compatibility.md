DEX_REVIEW_READY

# NLE Snapshot Save/Reload & Media Compatibility Risk Review

본 문서는 read-only NLE snapshot 어댑터 적용 시, 기존 `.aissproj` 저장/복원 흐름, 미디어 누락 처리 및 가변 타이밍 상태 간에 발생할 수 있는 호환성 갭(Gap)을 QE/QA 관점에서 분석한 리포트입니다.

---

## Save/Reload Compatibility Findings (4가지 잠재적 위험 분석)

### [Finding 1] NLE 스냅샷 런타임 필드의 디스크 유출 및 오염 위험 (Snapshot Field Spillover)
- **위험 요소**:
  - `project_io.py`의 `_project_payload_for_disk`는 `_PROJECT_RUNTIME_KEYS`에 선언된 특정 런타임 캐시 키들만 소거하여 디스크에 씁니다.
- **호환성 리스크**:
  - 만약 NLE snapshot 변환 결과물이나 런타임 어댑터 매핑 임시 정보(예: `nle_snapshot`, `sequence_view` 등)가 프로젝트 최상위 딕셔너리에 잔존할 경우, 소거 필터에 걸러지지 않고 `.aissproj` 파일 본체에 그대로 바이너리 패킹되어 저장됩니다.
  - 이는 구 버전 및 타 브랜치에서 해당 프로젝트 파일을 로드할 때 파싱 오류를 내거나 스키마 호환성을 오염시키는 결과를 유발합니다.

### [Finding 2] 미디어 파일 누락(Missing Media) 시 시간 정보 붕괴 리스크
- **위험 요소**:
  - 로컬에 영상 소스 파일이 유실(`missing media`)된 상황에서 프로젝트를 로드하면, `ProjectAsset`으로 매핑 시 실시간 ffprobe(미디어 프로빙)를 수행하지 못해 `fps` 및 `duration`을 0 또는 `None`으로 받아옵니다.
- **호환성 리스크**:
  - 이 상태에서 프로젝트 저장을 시도할 경우, 비디오 헤더에 비정상적인 시간/프레임 값(0.0초, 0fps)이 덮어써져 저장되고, 시퀀스 프레임 계산 로직이 전부 무너져서 멀쩡히 살아 있던 sidecar 및 자막 파일의 프레임 스냅 정합성이 파괴되는 데이터 유실 위험이 존재합니다.

### [Finding 3] 중복 가변 타이밍 상태(Duplicate Mutable Timing State) 저장 충돌
- **위험 요소**:
  - 타임라인 드래그 등 편집이 완료된 상태를 저장할 때, `editor_save_manager.py`는 `editor_state`와 자막 파일의 물리 정합성을 맞춰 저장합니다.
- **호환성 리스크**:
  - NLE snapshot 내에 복사된 `CaptionSegment` 시간 정보와 실제 UI 레이어의 `editor_state` 내부 타이밍 데이터가 비동기 상황에서 어긋나 있는 와중에 스냅샷 정보를 역참조하여 저장을 보정하려 한다면, 잘못된 1프레임 미세 지연이 물리 자막 파일에 덮어써져 영구적인 자막 싱크 탈조가 발생합니다.

### [Finding 4] 로컬 프록시/캐시 메타데이터 재매핑 시 ID 손실 위험
- **위험 요소**:
  - 로컬 캐시 디렉터리 경로 및 썸네일 캐시는 각 디바이스(macOS 머신)마다 동적으로 할당됩니다.
- **호환성 리스크**:
  - read-only NLE snapshot이 `ProjectAsset`을 Relink/Proxy 검증할 때 로컬 절대 경로를 고정 참조하려 할 경우, 파일이 타 디바이스로 공유되어 재열기(`reopen`)되었을 때 썸네일 캐시 및 프록시 메타데이터 매칭이 오동작하여 UI에 로딩 경고 팝업이 무한 루프로 출력되는 위험이 있습니다.
