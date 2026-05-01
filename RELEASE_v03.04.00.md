<!--
Document-Version: 03.04.00
Phase: PHASE2
Last-Updated: 2026-05-01
Updated-By: Codex with 대표님
Previous-Release: v03.03.00
-->
# RELEASE v03.04.00

## 핵심 요약
- v03.03.01 리팩토링 작업을 v03.04.00 릴리즈로 고정했습니다.
- 기능 수정 없이 리팩토링, 리네이밍, 리폴더링, 클린코드만 반영했습니다.
- 사용하지 않는 것으로 확인된 legacy 데이터 위치는 즉시 삭제하지 않고 `.codex_work/`에 보관한 뒤 제품 소스에서는 제거했습니다.

## 리팩토링 / 리네이밍
- `core/roughcut/editor_draft.py`의 private helper 이름을 역할 중심으로 정리했습니다.
- 자막 prompt row 생성, candidate EDL 계산, candidate output payload 생성을 작은 helper로 분리했습니다.
- public API, 설정 key, candidate schema, 러프컷 state 저장 구조는 변경하지 않았습니다.

## 리폴더링 / 보관
- 정적 참조가 없고 루트 `dataset/`로 통합된 legacy `core/dataset/` JSON 3개를 제품 소스에서 제거했습니다.
- 제거 전 보관본은 로컬 `.codex_work/refactor_unused_2026-05-01/core_dataset/`에 남겼습니다.
- `.codex_work/`는 Codex 전용 로컬 작업 메모이므로 GitHub 릴리즈 커밋에는 포함하지 않습니다.

## 유지한 호환 경로
- `core/audio/worker_threads.py`는 정적 참조가 없어도 legacy PyQt worker import 가능성을 고려해 유지했습니다.
- `core/project/project_snapshot.py`는 정적 참조가 없어도 project snapshot public helper 가능성을 고려해 유지했습니다.
- `core/roughcut/roughcut_pipeline.py`와 `core/audio/whisper_worker.py`는 호환 wrapper / Windows subprocess entry 성격이 있어 유지했습니다.

## 삭제 / 영향 범위
- 삭제된 public `def`, `class`, UI action, signal, slot은 없습니다.
- 제품 소스에서 제거된 파일:
  - `core/dataset/dataset_correction.json`
  - `core/dataset/subtitle_rule.json`
  - `core/dataset/user_settings.json`
- 영향 범위:
  - 현재 설정/교정/규칙 로드는 루트 `dataset/`와 `config.DATASET_DIR`를 사용하므로 앱 동작 영향은 없습니다.
  - 과거에 `core/dataset/` JSON을 직접 열던 외부 수동 스크립트가 있다면 루트 `dataset/` 경로를 사용해야 합니다.

## 검증
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests` 통과: 153개
- Python AST 검사 통과: 213개 파일
- offscreen UI smoke 통과: MainWindow / SettingsDialog / AdvancedSettingsDialog / ExportDialog / RoughcutWidget
- `git diff --check` 통과
- 루트 금지 파일 검사 통과
