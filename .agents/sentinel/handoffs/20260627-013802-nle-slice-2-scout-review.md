DEX_REVIEW_READY
역할: 서린 (Strict QE Reviewer)
범위: NLE Slice 2 source-fps cut-boundary scout review
읽은 파일:
- [NLE_Action.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/NLE_Action.md)
- [core/cut_boundary_auto_scan.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/cut_boundary_auto_scan.py)
- [tests/test_cut_boundary_auto_scan_backend.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_cut_boundary_auto_scan_backend.py)
- [tools/verify_cut_boundary_source_fps_scout.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tools/verify_cut_boundary_source_fps_scout.py)
- [output/manual_verification/latest/nle_slice2_source_fps_scout_20260627/source_fps_scout.json](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/nle_slice2_source_fps_scout_20260627/source_fps_scout.json)

결론:
`source_fps_scout.json` 증거를 기반으로 분석한 결과, target frame 2766/2677에 대한 스카우터의 검출 능력이 한계(False Negative 위험)에 도달해 있음을 감지했습니다. 또한 60fps 오버헤드, 트레이스 제한, 광학 흐름 및 split/snap 경계 조건의 5가지 핵심 QE Acceptance Risk를 발굴하였습니다.

findings:
### 1. 2766/2677 Target Frame 스카우터 미검출(False Negative) 리스크
* **QE 실증 데이터**: `source_fps_scout.json` 상에서 두 컷 프레임의 검출 점수(`score`)가 각각 `2.059` 및 `1.997`로 판명되어, 감지 기준(threshold >= 40.0)을 한참 하회하여 `fast_gate_skip` (candidate_detected: false) 처리되었습니다.
* **위험**: timing 공식에 의해 프레임 번호 자체는 보존(preserved)되었으나 스카우터 단계에서 실질적으로 '감지'에 실패했기 때문에, 실제 영상 자동 스캔 시 해당 1프레임 visual hard cut을 찾지 못하고 지나쳐 자막이 화면 컷 경계를 가로지르게 되는 품질 저하가 생길 수 있습니다.

### 2. `source-fps 60fps` Opt-in 시 macOS I/O 병목 및 메모리 압박
* **현황**: 60fps 비디오의 스캔을 위해 FPS 스로틀링을 60.0으로 상향 조정합니다.
* **위험**: 30fps 대비 연산 및 디코딩량이 2배 증가합니다. FFmpeg gray rawvideo 파이프를 통해 수많은 프레임을 파이썬 루프로 덤프할 때 싱글 스레드 I/O 병목이 유발되며, 특히 80분 이상의 장편 4K 60fps 영상 구동 시 메모리 압박(Wired memory pressure) 및 스로틀링으로 전체 분석 파이프라인이 멈추거나 중단될 수 있습니다.

### 3. Trace Event `rows[:20]` 제한으로 인한 사후 분석 블라인드 현상
* **현황**: `_trace_cut_boundary_rows` 내에서 상위 20개 로우만 슬라이싱하여 로깅합니다.
* **위험**: 영상 전체에서 수백 개의 후보군이 검출될 텐데, 인덱스 앞부분의 20개만 기록되면 영상의 뒷부분(예: 2766, 2677 프레임 등)에 배치된 컷 후보 정보와 점수 정보가 트레이스에 영구 누락되어 컷 감지 실패의 원인 파악 및 튜닝이 불가능해집니다.

### 4. Dense-flow False-Positive Guard의 오작동 리스크
* **현황**: 카메라 패닝/줌 등 빠른 모션으로 인한 오탐지를 방지하기 위해 광학 흐름(dense-flow) 지표를 활용합니다.
* **위험**: 플래시 깜빡임, 페이드 인/아웃, 하단 배너 자막 등 영상 속 일부 텍스트 요소가 변화할 때 이를 카메라 모션으로 잘못 해석하여 진짜 visual hard cut을 기각(False Negative)할 우려가 있습니다.

### 5. Final Split/Snap 시 자막 유실 및 무한 쪼개짐
* **현황**: 컷 경계에 맞춘 자막 자동 분할 및 스냅 동작이 이뤄집니다.
* **위험**:
  * 분할 과정에서 세그먼트가 최소 자막 길이 기준(Min Duration Policy) 미만으로 줄어들 때 발생할 수 있는 데이터 누락(Caption Drop) 및 싱크 밀림 현상의 예외 안전장치가 검증되지 않았습니다.
  * 60fps rational timing 연산 오차로 자막이 1프레임 단위로 조각나는 Jitter-Split 현상에 대한 QE 방어 케이스가 부족합니다.

defer: 없음
덱스 확인 포인트:
1. `fast_gate_skip` 임계값을 target 2766/2677 프레임이 Pioneer 단계에서 통과할 수 있도록 현실화할 것인지 여부.
2. 트레이스 로깅 대상 후보군 수를 20개 하드코딩에서 주요 관심 시간대 혹은 전체 후보 기록(단, 용량 제어 포함)으로 유연화할 것인지 검토.
3. 최소 자막 길이 충돌 시 drop 대신 trim/move 등으로 자막 텍스트 소실을 차단하는 E2E UI 통합 검증 확보 필요성.
