DEX_REVIEW_READY

# NLE Snapshot QA Promotion Blocker - Technical Analysis & Fix Recommendation

본 문서는 NLE 내부 스냅샷 작업의 QA 프로모션 진행을 가로막는 두 가지 물리 차단 요인(X5 미디어 로드 실패 및 다이아몬드 커맨드 해제 누락)에 대한 검토 및 픽스 가이드라인 보고서입니다.

---

## QA Blocker & Parity Findings (2가지 주요 블로커 분석)

### [Finding 1] X5 미디어 파일명 하드코딩으로 인한 FileNotFound 오류
- **현상**:
  - `qa_suite_full` 구동 시 X5 시승기 검증 단계(`x5_high_rolling_180s`)에서 `test video/X5_시승기_후반.MP4` 파일을 찾을 수 없다는 FileNotFound 예외가 발생하여 전체 QA가 실패합니다.
  - 현재 로컬 디렉터리(`test video/`)에는 `X5_시승기_후반_자막소스.mov` 형식으로만 비디오 소스가 존재합니다.
- **원인 분석**:
  - `tools/qa_suite_runner.py` 자체는 `_x5_media_for_suite`를 통해 `.mov` 폴백을 정상적으로 매핑하여 넘겨주지만,
  - 하위에서 실행되는 `tools/subtitle_regression_pack.py` 내 26라인에 `DEFAULT_X5_MEDIA` 기본값 경로가 `X5_시승기_후반.MP4`로 하드코딩되어 있어, 해당 스크립트 실행 과정에서 디스크에 존재하지 않는 파일명을 읽으려다 붕괴됩니다.
- **Validation-only Fix 제안**:
  - `subtitle_regression_pack.py`의 `DEFAULT_X5_MEDIA` 정의 부분을 `qa_suite_runner.py`처럼 `.MP4`와 `.mov` 후보군 중 실존하는 파일을 탐색하여 반환하도록 동적 폴백 로직으로 보완해 주어야 합니다.

### [Finding 2] 다이아몬드 편집 명령어 반환 시 Null(None) 명령 유출 버그
- **현상**:
  - 에디터 다이아몬드 스냅 컷 조율 단계(`move_diamond`)에서 `diamond_pair_missing`과 함께 status 해제 예외가 발생합니다.
- **원인 분석**:
  - `tools/qa_suite_runner.py`의 `_resolve_editor_compact_diamond_command` 함수에서 `pair`가 빈 딕셔너리로 존재하거나 `boundary_start`가 `None`인 상태로 조건문을 돌면, `if pair and boundary_start is not None:`에 진입하지 못합니다.
  - 그 뒤의 `elif not pair:` 및 `elif code != 0 or not runtime:` 분기 또한 모두 참이 되지 않아(status 자체는 ok이므로), 최종적으로 `command = None`이 반환되는 논리적 홀(Hole)이 발생합니다.
- **Validation-only Fix 제안**:
  - 모든 if/elif 조건을 타지 못하고 내려왔을 때의 안전을 보장하기 위해, 함수 반환문 직전의 기본값 처리 또는 마지막 `else:` 분기에 `command = [command_name, "--side", "closest"]` 폴백 지정을 명시해 주어야 합니다.
