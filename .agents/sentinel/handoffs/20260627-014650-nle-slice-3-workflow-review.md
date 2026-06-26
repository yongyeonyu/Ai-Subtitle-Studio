DEX_REVIEW_READY
역할: 유진 (Editor Workflow Reviewer)
범위: NLE Slice 3 preview cache implementation workflow review
읽은 파일:
- [NLE_Action.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/NLE_Action.md)
- [core/runtime/preview_frame_cache.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/runtime/preview_frame_cache.py)
- [tests/test_preview_frame_cache.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_preview_frame_cache.py)
- [ui/editor/video_player_widget.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/video_player_widget.py)
- [ui/editor/video_player_surface.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/video_player_surface.py)

결론:
Slice 3 Preview Cache / Skimming 구현체 파일에 대해 편집자 작업 흐름(Workflow), 비블로킹 반응성, UI 보존 준수 여부를 검토했습니다. 백그라운드 데몬 스레드를 통한 비동기 썸네일 확보 구조는 넌블로킹 원칙을 준수하지만, 동기식 `setPosition`과의 중첩 리소스 경쟁 및 썸네일 캐시 오용 차단 영역에서 주의가 필요합니다.

findings:
### 1. 데몬 스레드 비동기 생성과 넌블로킹(Non-blocking) 검증
* **현황**: `ui/editor/video_player_surface.py`의 `_schedule_preview_frame_cache_prepare`가 `threading.Thread(daemon=True)`를 띄워 `ensure_preview_frame` 및 `ffmpeg` 프레임 추출을 처리하고, 완료 시 메인 스레드에 시그널(`preview_thumbnail_ready`)로 전달합니다.
* **워크플로우 분석**: 무거운 프레임 추출이 백그라운드 스레드로 격리되어 UI 스레드의 즉각적인 락업(Lockup)은 회사되었습니다.

### 2. 동기식 `QMediaPlayer.setPosition` 호출과의 리소스 경쟁(Contention)
* **위험**: 타임라인 드래그(Scrubbing) 시 `VideoPlayerWidget.preview_seek`는 플레이어 백엔드의 `setPosition`을 메인 스레드에서 동기적으로 연발 호출합니다. 백그라운드 스레드에서 `ffmpeg` 프레임 추출을 병렬 구동하는 도중에 메인 프로세스가 동시에 동일 미디어 파일의 디코딩 탐색을 시도하게 되므로, CPU/디스크 I/O 경쟁이 가속되어 편집 조작 반응성이 저하되는 오버헤드가 발생할 수 있습니다.
* **대책**: 드래그가 활발히 일어나는 중에는 백엔드 seek 빈도를 스로틀링(Throttling)하거나 캐시 Hit된 이미지만 교체 드로잉하는 완충 제어가 권장됩니다.

### 3. UI/UX 미변경 원칙 준수 확인
* **현황**: 프리뷰 캐시 생성 실패나 디코딩 대기(Miss) 시, UI에 추가적인 팝업, 텍스트 라벨("캐시 생성 중" 등) 또는 오버레이 아이콘을 임의로 노출하지 않는 침묵형 설계를 유지하고 있습니다.
* **평가**: 대표님 사전 승인 없는 레이아웃 변경 금지 규정을 정상 충족합니다.

### 4. Preview Cache의 Cut-Boundary Scorer 오용 완벽 차단
* **현황**: `preview_frame_cache.py`에 확보되는 썸네일 파일들은 오직 `FrameThumbnails` 임시 폴더에만 격리 적재됩니다.
* **평가**: 컷 경계 스냅/스플릿 검출 로직(`cut_boundary_auto_scan.py`)이 저해상도 열화 캐시 이미지를 인식 증거로 잘못 오용하여 검출 정밀도를 무너뜨릴 우려가 없음을 구조적으로 확인했습니다.

defer: 없음
덱스 확인 포인트:
1. 고속 드래그 조작 시 백그라운드 `ffmpeg` 호출 누적으로 인한 프로세스 폭주를 제어하기 위해, 스레드 호출 전 `_preview_frame_active_request_key` 중복 검증 외에 Throttling 타이머 도입 필요성 검토.
2. 캐시 Miss 시 썸네일 서피스에 이전 프레임을 잔류시키거나 부드러운 전환을 적용하여 시각적 싱크 어긋남 혼동 방지.
