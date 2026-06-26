DEX_REVIEW_READY
역할: 잼민이
범위: NLE Slice 3 preview cache owner-map prep
읽은 파일:
- [NLE_Action.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/NLE_Action.md)
- [core/video_preview_proxy.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/video_preview_proxy.py)
- [tests/test_video_preview_proxy.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_video_preview_proxy.py)
- [ui/editor/video_player_widget.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/video_player_widget.py)
- [ui/editor/ux/editor_timeline_video.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_timeline_video.py)
- [ui/editor/video_playback_backend.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/video_playback_backend.py)

결론:
Slice 3 Preview Cache / Skimming 기능 설계를 위한 기존 저해상도 프록시 캐시, 드래그/호버/시크 관련 프리뷰 연동 오너 파일 및 단위 테스트 후보들을 매핑 완료했습니다.

findings:
### 1. 기존 저해상도 프리뷰/프록시/캐시 오너 파일
* **[core/video_preview_proxy.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/video_preview_proxy.py)**:
  * `preview_proxy_cache_dir()`를 통해 `video_preview_cache` 폴더를 데이터셋 하위에 생성 및 관리.
  * `media_fingerprint_digest`를 이용해 고유한 `*_preview_720p_hevc.mp4` 프록시 파일명을 자동 지정.
  * `ffprobe`를 이용한 비디오 유효성 검사(`preview_proxy_is_valid`) 및 캐시 예산 범위(512MB~4GB) 초과 시 자동 청소(`prune_preview_proxy_cache`)가 구현되어 있음.
  * 컷 스캔 시 이 프록시가 존재하면 파이프라인에서 원본 대신 프록시 파일을 디코딩 소스로 자동 스위칭(`cut_boundary_scan_source`).

### 2. Drag/Hover/Seek 프리뷰 오너 파일
* **[ui/editor/video_player_widget.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/video_player_widget.py)**:
  * `VideoPlayerWidget` 클래스가 프리뷰 렌더링 및 재생 위치 탐색의 최종 오너십을 가짐.
  * 타임라인 스크러빙(Scrubbing)에 사용되는 `preview_seek(sec)` 메소드를 제공하며, 내부적으로 `_apply_seek_state(...)`를 통해 미디어 플레이어의 위치를 설정(`setPosition(pos_ms)`)하고 썸네일 노출 로직을 유발.
  * 프레임 정밀 탐색을 위해 `< / >` 키 및 스캔 버튼과 바인딩된 `frame_step_seek(sec)`와 일반 `seek(sec)`, `seek_direct(sec)` 제공.
* **[ui/editor/ux/editor_timeline_video.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/ux/editor_timeline_video.py)**:
  * 타임라인 드래그, 호버 등의 마우스 조작을 비디오 플레이어 동작과 중개.
  * `_preview_seek_video_player`를 구현하여 마우스 움직임에 맞춰 플레이어의 `preview_seek`, `frame_step_seek` 또는 `seek_direct`를 동적으로 스위칭 호출.
* **[ui/editor/video_playback_backend.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ui/editor/video_playback_backend.py)**:
  * 환경설정 및 모듈 로딩 가용성에 따라 default인 `QtMultimedia (QMediaPlayer)` 또는 외장 렌더러 `mpv`(`MpvPlaybackBackend`), `vlc`(`VlcPlaybackBackend`) 백엔드를 생성 및 바인딩하는 구조.

### 3. 관련 테스트 후보 리스트
* **[tests/test_video_preview_proxy.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_video_preview_proxy.py)**: 캐시 등록, 유효성 판별 및 청소 유닛 테스트.
* **[tests/test_editor_timeline_drag_release.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_editor_timeline_drag_release.py)**: 타임라인 드래그 조작 완료 릴리즈 시의 재생 연동 검증.
* **[tests/test_video_player_widget.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_video_player_widget.py)**: 비디오 플레이어 위젯의 프레임 연산 및 seek/frame_step_seek 관련 로직 테스트.

defer: 없음
덱스 확인 포인트:
1. `core/video_preview_proxy.py`에서 기존 720p 프록시 MP4 외에, 추가적으로 low-resolution thumbnail/frame preview 캐시를 별도로 `/tmp` 임시 폴더에 구조화할 것인지 아니면 기존 프록시 mp4를 seek하여 프레임을 실시간 파싱 디코딩할 것인지 결정.
2. `video_player_widget.py` 내의 `preview_seek` 에 디코딩 딜레이 방지를 위한 caching/pre-decoding logic 적용 범위 결정.
