<!--
Document-Version: 02.06.00
Phase: PHASE1-C
Last-Updated: 2026-04-28
Updated-By: Codex with 대표님
Previous-Content: v02.04.00 PHASE1-C Apple 스타일 UI 릴리즈 노트
This-Update: P6 멀티클립 STT/LLM 병렬 파이프라인, 안정화 및 성능 개선
Copilot-Handoff: v02.06.00 커밋 기준 릴리즈 노트입니다. 다음 개발 버전은 v02.07.00부터 진행합니다.
-->
# RELEASE v02.06.00

## 핵심 변경
- P6 멀티클립 Whisper/LLM 클립 단위 파이프라인 병렬화를 구현했습니다.
- 클립1 Whisper 완료 후 LLM 최적화가 진행되는 동안 클립2 Whisper가 바로 시작됩니다.
- 에디터 append 순서는 단일 LLM 순서 큐로 클립1 → 클립2 → 클립3을 유지합니다.
- 기존 자막 reuse도 같은 파이프라인 큐를 거치도록 정리해 신규 STT 결과와 순서가 섞이지 않게 했습니다.

## 안정화 / 성능
- 멀티클립 처리 상태를 `오디오 추출 중` → `Whisper 중` → `LLM 대기` → `LLM 최적화 중` → `완료`로 세분화했습니다.
- Whisper worker와 LLM worker를 분리해 MLX Whisper, Ollama/LLM 후처리, 오디오 prefetch가 더 잘 겹치도록 했습니다.
- LLM 실패 시 전체 파이프라인을 중단하지 않고 Whisper 결과를 유지하는 fallback을 추가했습니다.
- 세그먼트 시간값을 append 직전에 정규화해 음수 시작/역전 구간으로 인한 UI 불안정을 줄였습니다.

## 문서
- `ACTION_ITEMS.md`에서 P6 구현 항목을 제거하고 실사용 확인용 `CHECKPOINT-P6-PARALLEL`만 남겼습니다.
- `AGENTS.md`와 `File_structure.txt`를 v02.06.00 기준으로 업데이트했습니다.

## 검증
- Python AST/compile 검사
- SettingsDialog offscreen 생성
- MainWindow offscreen 생성
- `git diff --check`
- 루트 금지 파일 확인
