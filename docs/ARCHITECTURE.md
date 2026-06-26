# Architecture

## Entry points

현재 저장소에서 확인되는 대표 진입점은 아래와 같습니다.

- `main.py`: 데스크톱 앱 부트스트랩, 환경 변수 로드, 런타임 예외 로깅, Qt 앱 시작
- `ui/main/main_window.py`: 메인 윈도우와 상위 UI 조립
- `tools/qa_suite_runner.py`: 저장소 표준 검증 진입점
- `tools/appctl.py`: 실행 중 앱 상태/제어 보조 도구

루트 `config.py`는 없고, 앱 기본 런타임 설정의 중심은 `core/runtime/config.py`입니다.

## Top-level layout

- `core/`: 엔진, 파이프라인, 프로젝트, 러프컷, LLM, 오디오, 품질 규칙, 런타임
- `ui/`: 메인 화면, 편집기, 타임라인, 러프컷, 설정, 대화상자, 로그, 프로젝트 화면
- `native/`: macOS/Swift 네이티브 보조 코드와 브리지 빌드 자산
- `tools/`: QA, 실앱 검증, 유지보수 체크, 앱 제어 스크립트
- `tests/`: 기능별 회귀 테스트
- `packaging/`: 패키징 관련 자산
- `config/`, `assets/`, `docs/`, `output/`: 설정, 리소스, 문서, 산출물

## Core layer

`core/`는 제품 동작의 중심입니다.

- `core/engine/`: 자막 생성과 후처리의 핵심 orchestration
- `core/audio/`: 오디오 전처리, STT/VAD 보조 계층
- `core/stt_mode/`: STT 모드 및 품질 프리셋 계층
- `core/llm/`: provider 래퍼, LLM 호출, 정책/정리 로직
- `core/subtitle_quality/`: 환각/반복/경계/정확도 보조 규칙
- `core/project/`: 프로젝트 포맷, 저장, 자산, 재로드
- `core/roughcut/`: 러프컷 초안 생성과 후속 데이터 구조
- `core/runtime/`: 버전, 플랫폼 정책, 디렉터리, 런타임 기본값
- `core/personalization/`: 사전, LoRA, 사용자 규칙 계층
- `core/native/`: 네이티브 보조 모듈과 Python 브리지

`core/engine/subtitle_engine.py`처럼 크고 많은 책임을 가진 owner 파일이 존재하므로, 수정 전 소유 경계를 더 잘게 확인해야 합니다.

## Trace and temporary workspace boundary

Trace diagnostics live under `core/runtime/` and must stay independent from product logging and subtitle generation. `core/runtime/temp_workspace.py` owns the per-user temporary workspace root and required subdirectories for trace, packages, exports, voice, and preview artifacts. `core/runtime/trace_logger.py` owns manifest/latest JSONL trace events and writes them through a bounded asynchronous writer so UI, playback, and editor hot paths do not perform synchronous trace file I/O. `tools/collect_trace_package.py` copies stable trace/package evidence for handoff and QA.

Trace files are diagnostic evidence only. They must not become subtitle timing, cut-boundary, save-file, or UI state owners. Failure modes such as disk full, permission denied, JSON serialization failure, queue overflow, and shutdown flush failure must stay isolated from `AppLogger`, UI logging, and subtitle generation. Forked child processes must not inherit a parent app trace singleton.

## UI layer

`ui/`는 화면과 상호작용을 담당합니다.

- `ui/main/`: 메인 윈도우, 앱 수준 상태
- `ui/editor/`: 편집기 본체, 저장/로드, 비디오 제어, 프로젝트 연결
- `ui/timeline/`: 타임라인, 글로벌 캔버스, 렌더링, 입력 처리
- `ui/roughcut/`: 러프컷 화면과 제어
- `ui/settings/`: 설정 화면
- `ui/project/`: 프로젝트 관련 UI
- `ui/dialogs/`, `ui/log/`, `ui/help/`, `ui/sidebar/`, `ui/queue/`: 보조 UI

UI는 상태를 보여주고 사용자 입력을 core 호출로 연결해야 하며, STT/VAD/LLM 정책을 UI 내부에서 직접 재구현하면 안 됩니다.

## Data/project layer

프로젝트 저장/복원 경계는 주로 `core/project/`에 있습니다.

- 프로젝트 포맷과 버전: `core/project/project_format.py`
- 프로젝트 디스크 I/O: `core/project/project_io.py` (`.aissproj`는 binary envelope에 project payload를 저장하고, 내부 API는 `read_project_file` / `write_project_file`로 통일)
- 자산 관리와 연결: `core/project/project_assets.py`
- 프로젝트 상태 매니저: `core/project_data_manager.py`
- 관련 UI 진입점: `ui/project/`, `ui/editor/editor_project_*`

프로젝트 포맷은 편집기, 자막, 미디어 자산을 잇는 공통 경계이므로, UI 변경이라도 저장 포맷을 건드리면 회귀 테스트 범위를 넓혀야 합니다.

## LLM/provider boundary

LLM/provider 경계는 `core/llm/`이 owner입니다. 이 계층은 OpenAI, Ollama, 기타 provider 래퍼와 자막 후처리 로직을 모읍니다. `core/engine/`와 `core/roughcut/`는 이 계층을 사용하지만, UI가 provider 세부사항을 직접 알아서는 안 됩니다.

provider 정책이나 fallback을 바꿀 때는 아래를 같이 봐야 합니다.

- 호출 실패 시 복구 경로
- 문맥 제한과 가드 정책
- 자막 split/correction과 품질 규칙의 결합

## STT/subtitle boundary

STT와 자막 엔진 경계는 대체로 아래 조합으로 보입니다.

- 오디오 입력/분석: `core/audio/`
- STT 모드/모델 선택: `core/stt_mode/`
- 자막 생성 orchestration: `core/engine/`
- 품질 및 경계 보정: `core/subtitle_quality/`

UI는 이 결과를 소비하고 편집해야 하며, 알고리즘 정책 자체는 core에 남겨 두는 편이 안전합니다.

## Roughcut boundary

러프컷 경계는 `core/roughcut/`과 `ui/roughcut/`입니다. 파일명과 테스트를 보면 러프컷 초안 생성, LLM 기반 섹션/구조화, 편집기 연결이 이미 구현 범위에 들어와 있습니다. 다만 러프컷 데이터가 곧바로 편집기 프로젝트 상태와 연결될 수 있으므로, 두 경계를 동시에 보는 것이 안전합니다.

## Source-app internal NLE timeline contract

현재 `Source-App Internal NLE Timeline Architecture Plan`은 사용자에게 보이는 UI/UX 변경이 아니라, 기존 project/editor/roughcut/export 상태를 읽기 전용 snapshot으로 설명하기 위한 내부 계약입니다. `core/project/nle_snapshot.py`가 이 계약의 첫 read-only adapter입니다. 이 계약은 새 저장 포맷이나 새 mutable timing owner가 아니며, 기존 `.aissproj`, direct SRT open, roughcut sidecar, rendered roughcut reopen 경로를 유지해야 합니다.

### Current owner map

| Area | Current owner | Existing source of truth | NLE snapshot rule |
| --- | --- | --- | --- |
| Project payloads | `core/project/project_format.py`, `core/project/project_io.py` | `.aissproj` binary envelope, `timeline`, `subtitles`, `asset_storage`, `editor_state`, `analysis`, `roughcut_state` | Read from hydrated payload only; do not write `nle` fields until a later explicit compatibility gate exists. |
| Media assets | `core/project/project_format.py`, `core/project/project_context.py`, `core/project/project_assets.py` | `timeline.tracks[0].clips`, runtime `media`, `video.clips`, external subtitle asset refs | Model as `ProjectAsset`; asset identity/path is separate from sequence placement. |
| Editor segments | `core/project/project_context.py`, `ui/editor/editor_save_manager.py` | `editor_state.rendering.subtitle_canvas`, external SRT tracks, `subtitles`, current editor rows | Model as `CaptionSegment` in sequence time; preserve frame-quantized fields and segment count. |
| Roughcut candidates | `ui/roughcut/roughcut_state.py`, `core/project/project_roughcut_store.py`, `core/roughcut/models.py` | `roughcut_state.candidates`, selected candidate id, `RoughCutResult` payloads | Model selected candidate as a read-only roughcut sequence view; do not mutate candidate order or selected id. |
| Cut-boundary seeds | `core/cut_boundary.py`, `core/project/project_context.py`, `ui/roughcut/roughcut_state.py` | `analysis.cut_boundaries`, editor multiclip cut boundary rows, provisional cut boundary rows | Model point evidence as `TimelineMarker`; never treat a cut boundary point as a clip boundary span. |
| Clip boundary spans | `core/project/project_context.py`, `core/roughcut/edl_generator.py`, `ui/roughcut/roughcut_state.py` | multiclip `boundaries`, `timeline.tracks[0].clips`, EDL clip mapping | Model as `Clip` source/sequence spans; this is separate from cut point markers. |
| Render plans | `core/roughcut/renderer_skeleton.py`, `core/roughcut/render_executor.py`, `ui/roughcut/roughcut_export.py` | `RenderCommandPlan`, `_render_plan.json`, render result manifest | Model as `RenderPlan`; output duration and sidecar metadata must remain byte/metadata-equivalent. Roughcut SRT/video export plan builders now route through `build_concat_render_plan_from_snapshot`, while sidecar writers/readers stay legacy-compatible. |
| Sidecars | `core/roughcut/edl_generator.py`, `ui/editor/editor_project_open_native.py`, `ui/roughcut/roughcut_export.py` | `_edl.json`, `_render_plan.json`, `stitched_cut_boundaries` | Import only as markers/render-plan evidence; sidecar readers stay compatibility sources. `markers_from_roughcut_sidecar_payload` mirrors current payload shapes without becoming a new runtime reader. |
| Timeline canvas state | `ui/timeline/timeline_canvas.py`, `ui/timeline/timeline_analysis.py` | live canvas segments, playhead, marker caches, roughcut marker cache | Keep live state outside the domain snapshot; snapshot must not drive paint caches or UI layout. |
| Save/reopen behavior | `ui/editor/editor_save_manager.py`, `ui/editor/editor_project_open_native.py`, `core/project/project_manager.py` | project save snapshot, project open hydration, direct SRT metadata merge | Snapshot generation must not change save files, reopen order, subtitle timing, or project matching rules. |
| NLE snapshot adapter | `core/project/nle_snapshot.py` | hydrated project dict plus selected roughcut candidate output evidence | Build frozen read-only dataclasses only; no save/write hook owns this snapshot. |

### Domain object definitions

- `ProjectAsset`: a media or text asset known to the project. It owns stable asset id, path, kind, duration, frame rate, optional dimensions, and missing/relink metadata. It does not own sequence placement.
- `Sequence`: an ordered read-only timeline view with id, name, timebase, duration, tracks, and source project references. The source-app default sequence mirrors the current project timeline.
- `Track`: a logical grouping inside a sequence, such as media, captions, markers, or roughcut plan evidence. A track is not a visible UI lane until the owner explicitly approves UI work.
- `Clip`: a sequence span that references a `ProjectAsset` and records `source_start`, `source_end`, `sequence_start`, `sequence_end`, clip index, and clip boundary span metadata.
- `CaptionSegment`: a subtitle row in sequence time with text, speaker, frame range, source clip reference when known, and existing metadata copied read-only from project/editor rows.
- `TimelineMarker`: point evidence on sequence or output time. Cut-boundary points, roughcut exact joins, and provisional markers belong here. Markers do not define media spans.
- `RenderPlan`: a read-only render/export plan with selected sequence references, EDL segments, output path, output duration, render mode, segment manifest, and exact-join metadata.

### Time model

- `source_time`: local time inside one `ProjectAsset`, used by EDL source ranges and clip-local subtitle metadata.
- `sequence_time`: project timeline time after clips are placed. Editor segments, clip spans, and timeline canvas rows are interpreted here.
- `output_time`: rendered/exported result time after EDL decisions are applied. Roughcut `output_start` / `output_end` and `stitched_cut_boundaries.timeline_sec` are interpreted here.
- `exact_join`: metadata derived from roughcut `stitched_cut_boundaries`. It maps an output-time point to before/after EDL segments and source paths. It is a marker/edit-point candidate, not a replacement for clip boundary spans.

Implementation order must remain docs/schema first, then read-only adapters, then roughcut exact-join marker projection, then render/export routing parity. The initial adapter currently projects existing state into frozen dataclasses and has no save/write hook. Roughcut exact joins can be projected from top-level `stitched_cut_boundaries`, nested `edl.stitched_cut_boundaries`, nested `render_plan.stitched_cut_boundaries`, or selected candidate `outputs`; all are output-time markers, not clip boundary spans. Render/export parity is currently proven by rebuilding the existing concat command plan from `NLESnapshot.render_plans[*].segments` and comparing it with `build_concat_render_plan`; roughcut SRT/video plan construction uses that adapter as a read-only route. This does not change roughcut UI ownership, `_render_plan.json` / `_edl.json` schemas, sidecar readers, save files, or visible UI behavior. Any duplicate mutable timing state, subtitle count drift, first/last time drift, output duration drift, or sidecar metadata drift stops the slice.

## Config/settings boundary

설정 경계는 크게 둘입니다.

- 런타임 기본값과 플랫폼 정책: `core/runtime/config.py`
- 사용자 설정과 모드/UI 연결: `core/settings.py`, `core/mode_manager.py`, `ui/settings/`

설정 UI를 수정할 때는 단순 표시 텍스트뿐 아니라 실제 런타임 적용 지점을 확인해야 합니다.

## Import boundaries

현재 구조에서 안전한 기본 원칙은 아래와 같습니다.

- `ui/*`는 `core/*`를 호출할 수 있습니다.
- `core/*`는 가능하면 `ui/*`에 의존하지 않아야 합니다.
- 프로젝트 포맷/저장은 `core/project/*`를 중심으로 유지합니다.
- 테스트는 owner 파일을 직접 겨냥하되, UI 회귀는 `QT_QPA_PLATFORM=offscreen` 경로를 우선 고려합니다.

저장소에 mixin, helper, bridge 파일이 많아서 실제 import coupling은 완전히 느슨하지 않습니다. 그래서 경계를 문서로 먼저 확인하고 최소 범위 수정으로 접근하는 것이 중요합니다.

## Known coupling and risks

- `core/engine/subtitle_engine.py`, `ui/editor/editor_widget.py`, `ui/timeline/*`는 큰 owner 파일과 세부 helper가 함께 있어 수정 반경이 예상보다 커질 수 있습니다.
- Python 경로와 macOS native 보조 모듈이 함께 존재하므로, 한쪽만 보고 “죽은 코드”로 판단하면 위험합니다.
- `ui/qml/` 디렉터리가 존재하지만 현재 운영 규칙은 Qt Widgets 중심 경로를 기본으로 봅니다.
- 편집기, 타임라인, 프로젝트 재로드는 서로 깊게 연결되어 있어 시각 수정도 저장/seek/playhead 회귀로 번질 수 있습니다.
